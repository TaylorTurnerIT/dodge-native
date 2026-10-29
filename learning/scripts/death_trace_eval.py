"""Frozen-policy death-trace evaluator (inference only; no training, no checkpoint writes).

Mirrors the complete-game loop of the control-frequency confirmation
(`learning/runs/v2/control-frequency-confirmation-luna-20261029-r1/screen.py`,
`_production_rows`) so that per-game outcomes can be replay-checked against the
saved rows, and adds the observation-only gameplay trace per game.

One invocation evaluates one group: a condition (argmax or sampled, repeat 1 or
4) over one ordered seed list, writing one JSON file of per-game rows.

Run with the repo venv and `/usr/bin/caffeinate -ims` on AC power.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch

CHECKPOINT_SHA256 = "7e0de8640f1337261412d91cde6bc692772ff212fbd360f5aad415dc6bc7ed4b"
MODEL_FINGERPRINT = "575b415434a3dbfe9a99021101d517f015c71415efd3f3f6255e4d4cd5d4d534"
NEURAL_INPUTS = ("global_feats", "entity_feats", "entity_types", "entity_mask")
# Evaluation exclusions registered by the control-frequency confirmation (its D8
# parity cohort, 3623878656-3623878911, is deliberately NOT excluded here).
EXCLUDED_RANGES = [
    [2952790016, 2952791015], [3489660928, 3489661055], [3506438144, 3506439167],
    [3523215360, 3523217407], [3539992576, 3539993599], [3556769792, 3556770815],
    [3573547008, 3573549055], [3590324224, 3590325247], [3607101440, 3607101695],
    [3758096384, 3758097383],
]
GIB = 1 << 30


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class Guard:
    """Fail closed on RSS/MPS ceilings and loss of AC power."""

    def __init__(self, torch_module, backend: str, cap_bytes: int = 6 * GIB):
        self.torch, self.backend, self.cap = torch_module, backend, cap_bytes
        self.peak_rss = self.peak_mps = 0
        self.last = 0.0

    def __call__(self) -> None:
        now = time.monotonic()
        if now - self.last < 1.0:
            return
        self.last = now
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss = int(rss) * (1 if sys.platform == "darwin" else 1024)
        mps = int(self.torch.mps.driver_allocated_memory()) if self.backend == "mps" else 0
        self.peak_rss, self.peak_mps = max(self.peak_rss, rss), max(self.peak_mps, mps)
        if rss > self.cap or mps > self.cap:
            raise RuntimeError(f"resource ceiling exceeded: rss={rss} mps={mps}")
        batt = subprocess.run(["/usr/bin/pmset", "-g", "batt"], capture_output=True, text=True, timeout=20).stdout
        if "AC Power" not in batt.splitlines()[0]:
            raise RuntimeError("AC power lost")


def load_model(path: Path, backend: str):
    from dodge_rl import checkpoints as ckpt
    from dodge_rl.models import teacher
    if sha256(path) != CHECKPOINT_SHA256:
        raise RuntimeError("checkpoint sha256 differs")
    state = ckpt.load_checkpoint(path, expected_sha256=CHECKPOINT_SHA256)
    ckpt.require_complete_update(state)
    if state.get("global_update") != 420:
        raise RuntimeError("checkpoint update differs")
    model = teacher.OmniscientEntityTeacher().to(backend)
    model.load_state_dict(state["model"], strict=True)
    model.eval()
    model._expanded_eval_device = backend
    return model


def weights_digest(model) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        digest.update(name.encode())
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def collect_rows(model, env_factory, seeds, *, repeat, mode, backend, guard, batch_size=64,
                 progress=None):
    """Complete normal-start games; same loop and ordering as the saved evaluator."""
    rows = []
    for offset in range(0, len(seeds), batch_size):
        chunk = seeds[offset:offset + batch_size]
        envs, obs, done, started = {}, {}, {}, {}
        for local, seed in enumerate(chunk):
            guard()
            env = env_factory(
                batch_size=1, action_repeat=repeat, difficulty=2, patterns_enabled=True,
                powerups_enabled=True, raw_frame_cap=18000, num_threads=1, chunk_size=1,
                render_pixels=False, auxiliary_targets=False, seeds_by_slot=[[seed]],
                excluded_seed_ranges=[tuple(pair) for pair in EXCLUDED_RANGES], trace=True)
            info = env.episode_info()[0]
            if not (info["seed"]["evaluation"] is True and info["seed"]["actual_seed"] == seed
                    and info["startup_frames"] == 13 and info["gameplay_frames"] == 0):
                raise RuntimeError("constructor seed/startup differs")
            envs[local], obs[local], started[local] = env, env.observations(), time.monotonic()
        while envs:
            guard()
            active = sorted(envs)
            tensors = {name: torch.from_numpy(np.concatenate([obs[i][name] for i in active], axis=0)).to(backend)
                       for name in NEURAL_INPUTS}
            with torch.no_grad():
                logits = model(*(tensors[name] for name in NEURAL_INPUTS)).logits
            if tuple(logits.shape) != (len(envs), 9) or not bool(torch.isfinite(logits).all()):
                raise RuntimeError("nonfinite or malformed policy output")
            actions = (torch.distributions.Categorical(logits=logits).sample()
                       if mode == "sampled" else torch.argmax(logits, dim=-1)).cpu().numpy()
            del tensors, logits
            for pos, i in enumerate(active):
                result = envs[i].step(np.array([actions[pos]], dtype=np.int64))
                info = result["info"][0]
                terminated, truncated = bool(result["terminated"][0]), bool(result["truncated"][0])
                if info["seed"]["actual_seed"] != chunk[i] or (terminated and truncated):
                    raise RuntimeError("seed/boundary differs")
                if terminated or truncated:
                    done[i] = dict(
                        episode_index=offset + i, seed=chunk[i], action_repeat=repeat,
                        score_raw_fixed=info["score_raw_fixed"], alive_frames=info["alive_frames"],
                        gameplay_frames=info["gameplay_frames"], terminated=terminated,
                        truncated=truncated, death_cause=info["death_cause"],
                        fatal_gameplay_frame=info["fatal_gameplay_frame"],
                        death_observed_lethal_contacts=info["death_observed_lethal_contacts"],
                        trace=info["trace"])
                    del envs[i], obs[i]
                else:
                    obs[i] = result["observations"]
        rows.extend(done[i] for i in range(len(chunk)))
        if progress:
            progress(len(rows), len(seeds))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--mode", choices=("argmax", "sampled"), required=True)
    parser.add_argument("--repeat", type=int, choices=(1, 4), required=True)
    parser.add_argument("--seeds-json", type=Path, help="JSON list of seeds (ordered)")
    parser.add_argument("--seed-start", type=int)
    parser.add_argument("--count", type=int)
    parser.add_argument("--controller-seed", type=int, help="required for sampled mode")
    parser.add_argument("--backend", choices=("mps", "cpu"), default="mps")
    parser.add_argument("--torch-threads", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite {args.out}")
    if args.seeds_json:
        seeds = json.loads(args.seeds_json.read_text())
    else:
        seeds = list(range(args.seed_start, args.seed_start + args.count))
    if not (seeds == sorted(seeds) and len(set(seeds)) == len(seeds)):
        raise SystemExit("seeds must be sorted and unique")
    if args.mode == "sampled" and args.controller_seed is None:
        raise SystemExit("sampled mode needs --controller-seed")

    from dodge_rl import VecDodgeEnv
    torch.set_num_threads(args.torch_threads)
    if args.backend == "mps" and not torch.backends.mps.is_available():
        raise SystemExit("MPS unavailable")
    model = load_model(args.checkpoint, args.backend)
    before = weights_digest(model)
    guard = Guard(torch, args.backend)
    guard()
    if args.mode == "sampled":
        s = args.controller_seed
        random.seed(s)
        np.random.seed(s % 2**32)
        torch.manual_seed(s)
        if args.backend == "mps":
            torch.mps.manual_seed(s)
    started = time.monotonic()
    last = [0.0]

    def progress(done, total):
        if time.monotonic() - last[0] > 30 or done == total:
            last[0] = time.monotonic()
            print(f"{args.out.name}: {done}/{total} games, {last[0] - started:.0f}s", flush=True)

    rows = collect_rows(model, VecDodgeEnv, seeds, repeat=args.repeat, mode=args.mode,
                        backend=args.backend, guard=guard, batch_size=args.batch_size, progress=progress)
    after = weights_digest(model)
    if after != before or sha256(args.checkpoint) != CHECKPOINT_SHA256:
        raise RuntimeError("weights or checkpoint changed during evaluation")
    result = dict(
        schema="death_trace_group_v1", checkpoint_sha256=CHECKPOINT_SHA256, weights_digest=before,
        mode=args.mode, action_repeat=args.repeat, backend=args.backend, torch_threads=args.torch_threads,
        batch_size=args.batch_size, controller_seed=args.controller_seed, seeds=seeds,
        elapsed_seconds=time.monotonic() - started, peak_rss_bytes=guard.peak_rss,
        peak_mps_driver_bytes=guard.peak_mps, rows=rows,
        versions=dict(python=sys.version.split()[0], numpy=np.__version__, torch=torch.__version__))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, separators=(",", ":"), allow_nan=False))
    os.replace(tmp, args.out)
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "seeds")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
