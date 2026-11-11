"""Export velocity-flow-v2-best for the browser, plus a PyTorch reference.

Run from dodge-native/learning with the repo venv:
    ..\\.venv\\Scripts\\python reports\\timeline\\web\\tools\\export_cnn.py

Writes, next to this script's parent (web/):
  cnn_weights.bin   little-endian f32 tensors, in the order of TENSORS below
  parity/cnn_ref.bin  for N frames of seed 1 (hard, patterns, powerups):
                      per frame 3076 observation floats, 9 log-probs, 1 value,
                      then the action taken (as f32)
  parity/cnn_ref.json  frame count and the PyTorch survival on seeds 1..3
"""
import io
import json
import struct
import sys
import zipfile
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent.parent
LEARNING = HERE.parents[2]
sys.path.insert(0, str(LEARNING))

from dodge_rl._native import VecDodgeEnv  # noqa: E402
from stable_baselines3 import PPO  # noqa: E402
import dodge.velocity  # noqa: E402,F401

MODEL = LEARNING / "artifacts" / "models" / "velocity-flow-v2-best.zip"
FE = "features_extractor."
TENSORS = [
    FE + "offsets", FE + "sample_weights",
    FE + "field_net.stem.0.weight", FE + "field_net.stem.0.bias",
    FE + "field_net.body.0.weight", FE + "field_net.body.0.bias",
    FE + "field_net.body.2.weight", FE + "field_net.body.2.bias",
    FE + "field_net.body.4.weight", FE + "field_net.body.4.bias",
    FE + "context_net.0.weight", FE + "context_net.0.bias",
    FE + "context_net.2.weight", FE + "context_net.2.bias",
    FE + "field_head.weight", FE + "field_head.bias",
    FE + "value_pool.weight", FE + "value_pool.bias",
    FE + "value_net.0.weight", FE + "value_net.0.bias",
    FE + "value_net.2.weight", FE + "value_net.2.bias",
    "mlp_extractor.value_net.0.weight", "mlp_extractor.value_net.0.bias",
    "value_net.weight", "value_net.bias",
    "action_net.log_temperature",
]


def export_weights():
    z = zipfile.ZipFile(MODEL)
    sd = torch.load(io.BytesIO(z.read("policy.pth")), map_location="cpu", weights_only=True)
    out = bytearray()
    sizes = []
    for name in TENSORS:
        t = sd[name].detach().to(torch.float32).contiguous().numpy().ravel()
        sizes.append((name, t.size))
        out += t.astype("<f4").tobytes()
    (HERE / "cnn_weights.bin").write_bytes(bytes(out))
    print("weights", len(out), "bytes")
    for name, n in sizes:
        print(f"  {name}: {n}")


def make_env(n, cap):
    return VecDodgeEnv(batch_size=n, action_repeat=1, difficulty=3, patterns_enabled=True,
                       powerups_enabled=True, raw_frame_cap=cap, num_threads=1,
                       observation="velocity_flow", step_info="none")


def reference(frames):
    model = PPO.load(MODEL, device="cpu")
    policy = model.policy
    env = make_env(1, 18000)
    obs = env.reset_all(seeds=[1])["observations"]["observation"]
    rows = []
    with torch.no_grad():
        for _ in range(frames):
            o = torch.as_tensor(np.asarray(obs, dtype=np.float32))
            log_pmf, values = policy._distribution_inputs(o)
            action = int(log_pmf.argmax(dim=-1)[0])
            rows.append(np.concatenate([o[0].numpy(), log_pmf[0].numpy(),
                                        values[0].numpy(), [float(action)]]).astype("<f4"))
            out = env.step(np.array([action], dtype=np.int64))
            if out["terminated"][0] or out["truncated"][0]:
                break
            obs = out["observations"]["observation"]
    (HERE / "parity").mkdir(exist_ok=True)
    (HERE / "parity" / "cnn_ref.bin").write_bytes(b"".join(r.tobytes() for r in rows))
    return len(rows)


def survival(seeds):
    model = PPO.load(MODEL, device="cpu")
    result = {}
    for seed in seeds:
        env = make_env(1, 18000)
        obs = env.reset_all(seeds=[seed])["observations"]["observation"]
        while True:
            action, _ = model.predict(obs, deterministic=True)
            out = env.step(np.asarray(action, dtype=np.int64))
            if out["terminated"][0] or out["truncated"][0]:
                result[seed] = int(out["counters"]["survival_frames"][0])
                break
            obs = out["observations"]["observation"]
    return result


if __name__ == "__main__":
    torch.set_num_threads(1)
    export_weights()
    n = reference(int(sys.argv[1]) if len(sys.argv) > 1 else 400)
    surv = survival([1, 2, 3])
    meta = {"frames": n, "row_floats": 3076 + 9 + 1 + 1, "survival": surv}
    (HERE / "parity" / "cnn_ref.json").write_text(json.dumps(meta, indent=1))
    print(meta)
