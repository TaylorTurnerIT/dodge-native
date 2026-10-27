"""Preparation-only paired endpoint evaluator. Import has no runtime side effects."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Callable, Iterable

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "seed-manifest.json"
EXPECTED_MANIFEST_SHA256 = "e11e9d6accb79fcafd1b0e6049c322356edf16601007d2af62da6b59539c886c"
SEEDS = tuple(range(0xD0000040, 0xD0000080))
LABEL = "unselected training-excluded upper-D development block; prior nonuse not proven"
DEATH_CAUSES = ("normal_enemy", "kamikaze_enemy", "kamikaze_explosion",
                "static_pattern_rect", "moving_pattern_rect", "unknown")
UNAVAILABLE = "unavailable"
CONSTANT = {
    "run_id": "D2-retained324-continuation-20261026-r1",
    "checkpoint_sha256": "e25117bf52f14629a3d2ffada319c49a10c6344763a25506a5f124a76a62199b",
    "endpoint_phase_update": 384,
    "cumulative_update": 432,
}

class ValidationError(ValueError):
    pass

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValidationError(message)

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def load_manifest(path: Path = MANIFEST) -> dict:
    raw = path.read_bytes()
    require(sha256(raw) == EXPECTED_MANIFEST_SHA256, "seed manifest byte SHA-256 differs")
    obj = json.loads(raw)
    require(obj.get("schema") == "paired_LR_supplemental_development_seed_manifest_v1", "manifest schema differs")
    require(obj.get("seed_class") == "upper_D64_unselected_development_namespace", "manifest seed class differs")
    require(obj.get("training_excluded") is True and obj.get("prior_nonuse_proven") is False
            and obj.get("qualification_or_sealed_claim") is False, "manifest claim limits differ")
    require(obj.get("seeds") == list(SEEDS), "manifest ordered seeds differ")
    require(len(set(obj["seeds"])) == 64 and all(type(s) is int and 0 <= s <= 0xffffffff for s in obj["seeds"]),
            "manifest seeds are not unique unsigned 32-bit integers")
    return obj

def _integer(value, name, minimum=0):
    require(type(value) is int and value >= minimum, f"{name} must be integer >= {minimum}")

def validate_rows(rows: Iterable[dict], manifest: dict | None = None) -> list[dict]:
    manifest = manifest or load_manifest()
    rows = list(rows)
    require(len(rows) == 64, "evaluation must contain exactly 64 rows")
    require([r.get("seed") for r in rows] == manifest["seeds"], "rows missing, reordered, duplicated, or outside manifest")
    for row in rows:
        require(row.get("episode_index") == row["seed"] - SEEDS[0], "episode index/seed identity differs")
        _integer(row.get("seed"), "seed")
        for key in ("alive_frames", "gameplay_frames", "score_raw_fixed"):
            _integer(row.get(key), key)
        require(0 <= row["alive_frames"] <= row["gameplay_frames"] <= 18000, "frame bounds differ")
        require(type(row.get("terminated")) is bool and type(row.get("truncated")) is bool
                and row["terminated"] != row["truncated"], "episode boundary flags invalid")
        require(row["score"] == row["score_raw_fixed"] / 65536 and math.isfinite(row["score"]),
                "fixed-point score identity or finiteness differs")
        cause = row.get("death_cause")
        if row["terminated"]:
            require(cause in (*DEATH_CAUSES, UNAVAILABLE), "terminated row death cause unavailable/invalid")
            if cause == UNAVAILABLE:
                require(row.get("fatal_gameplay_frame") is None and row.get("death_observed_lethal_contacts") is None,
                        "unavailable cause carries inferred telemetry")
            else:
                contacts = row.get("death_observed_lethal_contacts")
                require(type(row.get("fatal_gameplay_frame")) is int
                        and row["fatal_gameplay_frame"] == row["gameplay_frames"]
                        and isinstance(contacts, dict) and set(contacts) == set(DEATH_CAUSES)
                        and all(type(v) is int and v >= 0 for v in contacts.values())
                        and (cause == "unknown" or contacts[cause] >= 1), "death telemetry differs")
        else:
            require(cause is None and row.get("fatal_gameplay_frame") is None
                    and row.get("death_observed_lethal_contacts") is None, "truncated row has death telemetry")
    return rows

def summarize_arm(rows: Iterable[dict]) -> dict:
    rows = validate_rows(rows)
    ordered = sorted(rows, key=lambda r: (r["alive_frames"], r["seed"]))
    deaths = [r for r in rows if r["terminated"]]
    return {
        "complete": True, "episodes": 64, "mean_alive_frames": sum(r["alive_frames"] for r in rows) / 64,
        "bottom16_mean_Q1": sum(r["alive_frames"] for r in ordered[:16]) / 16,
        "top16_mean_Q4": sum(r["alive_frames"] for r in ordered[-16:]) / 16,
        "death_cause_counts": {c: sum(r["death_cause"] == c for r in deaths) for c in (*DEATH_CAUSES, UNAVAILABLE)},
        "truncations": sum(r["truncated"] for r in rows), "rows": rows,
    }

def paired_summary(constant_rows: Iterable[dict], linear_rows: Iterable[dict]) -> dict:
    c = validate_rows(constant_rows); l = validate_rows(linear_rows)
    require([r["seed"] for r in c] == [r["seed"] for r in l], "arms are not seed-aligned")
    differences = [{"seed": a["seed"], "linear_minus_constant_alive_frames": b["alive_frames"] - a["alive_frames"]}
                   for a, b in zip(c, l)]
    return {"schema": "paired_LR_upperD64_summary_v1", "comparison": "per-seed linear minus constant alive frames",
            "seed_label": LABEL, "constant_endpoint": CONSTANT, "linear_endpoint": {"phase_update": 384, "cumulative_update": 432},
            "constant": summarize_arm(c), "linear": summarize_arm(l),
            "mean_paired_alive_frame_difference": sum(x["linear_minus_constant_alive_frames"] for x in differences) / 64,
            "per_seed_differences": differences,
            "interpretation_limits": ["One matched training seed (4200000001); no training replicate uncertainty estimate.",
              "Linear average LR 2e-5 versus constant 3e-5; ordering is not isolated from average LR.",
              "No causal claim about schedule ordering; evaluation score is diagnostic only."]}

def validate_registration(registration: dict, arm: str, checkpoint_metadata: dict) -> None:
    require(arm in ("constant", "linear"), "arm must be constant or linear")
    require(registration.get("schema") == "paired_LR_upperD64_evaluation_registration_v1", "registration schema differs")
    require(registration.get("manifest_sha256") == EXPECTED_MANIFEST_SHA256, "registration manifest pin differs")
    require(registration.get("seed_label") == LABEL, "registration seed label differs")
    require(registration.get("episode_contract") == {"difficulty": 2, "action_repeat": 4, "raw_frame_cap": 18000,
            "episodes": 64, "batch_size": 1, "action_mode": "deterministic_argmax", "gradients": False,
            "reset_policy": "construct_once_no_reset"}, "registration episode contract differs")
    endpoint = CONSTANT if arm == "constant" else registration.get("linear_endpoint")
    require(isinstance(endpoint, dict), "linear endpoint registration missing")
    require(checkpoint_metadata.get("checkpoint_sha256") == endpoint.get("checkpoint_sha256"), "checkpoint metadata SHA pin differs")
    require(endpoint.get("endpoint_phase_update") == 384 and endpoint.get("cumulative_update") == 432
            and checkpoint_metadata.get("phase_update") == endpoint.get("endpoint_phase_update")
            and checkpoint_metadata.get("cumulative_updates") == endpoint.get("cumulative_update")
            and checkpoint_metadata.get("run_id") == endpoint.get("run_id"),
            "checkpoint endpoint metadata differs")
    if arm == "constant":
        require(endpoint.get("checkpoint_sha256") == CONSTANT["checkpoint_sha256"], "constant checkpoint pin differs")

def evaluate_registered(*, registration_path: str, registration_sha256: str, arm: str,
                         checkpoint_metadata: dict, check_guard: Callable[[], None], collector: Callable,
                         output_path: str) -> dict:
    """Explicit parent-only entry. Collector must implement the frozen D2 loop."""
    p = Path(registration_path); raw = p.read_bytes()
    require(sha256(raw) == registration_sha256, "registration byte SHA-256 differs")
    registration = json.loads(raw)
    validate_registration(registration, arm, checkpoint_metadata)
    manifest = load_manifest()
    require(callable(check_guard) and callable(collector), "guard and collector are required")
    check_guard()
    rows = collector(seeds=tuple(manifest["seeds"]), difficulty=2, action_repeat=4,
                     raw_frame_cap=18000, batch_size=1, gradients=False, action_mode="deterministic_argmax",
                     reset_policy="construct_once_no_reset")
    check_guard()
    result = summarize_arm(rows)
    result.update({"arm": arm, "seed_label": LABEL, "manifest_sha256": EXPECTED_MANIFEST_SHA256,
                   "checkpoint_sha256": checkpoint_metadata["checkpoint_sha256"],
                   "endpoint_phase_update": 384, "cumulative_update": 432,
                   "action_repeat": 4, "difficulty": 2, "raw_frame_cap": 18000,
                   "action_mode": "deterministic_argmax", "gradients": False})
    Path(output_path).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result

def collect_d2_rows(*, model, env_factory, observation_keys, death_fields,
                    check_guard: Callable[[], None], device="cpu") -> list[dict]:
    """D2 deterministic argmax loop; all runtime objects must be explicitly injected."""
    import numpy as np
    import torch
    require(device == "cpu", "this prepared evaluator permits CPU only")
    require(callable(env_factory) and callable(death_fields), "explicit runtime bindings required")
    require(tuple(observation_keys), "observation keys required")
    envs, obs, completed = {}, {}, {}
    was_training = model.training
    model.eval()
    try:
        for i, seed in enumerate(SEEDS):
            check_guard()
            env = env_factory(batch_size=1, action_repeat=4, difficulty=2, patterns_enabled=True,
                              powerups_enabled=True, raw_frame_cap=18000, num_threads=1,
                              chunk_size=1, render_pixels=False, auxiliary_targets=False,
                              seeds_by_slot=[[seed]])
            info = env.episode_info()[0]
            require(info["seed"]["evaluation"] is True and info["seed"]["actual_seed"] == seed
                    and info["startup_frames"] == 13, "D2 constructor seed/startup differs")
            envs[i] = env; obs[i] = env.observations()
        while envs:
            check_guard()
            active = sorted(envs)
            tensors = {name: torch.from_numpy(np.concatenate([obs[i][name] for i in active], axis=0)).to(device)
                       for name in observation_keys}
            with torch.no_grad():
                logits = model(*(tensors[name] for name in observation_keys)).logits
            require(tuple(logits.shape) == (len(active), 9) and bool(torch.isfinite(logits).all()),
                    "nonfinite or malformed D2 policy output")
            actions = logits.argmax(dim=-1).cpu().numpy()
            del tensors, logits
            for pos, i in enumerate(active):
                check_guard()
                result = envs[i].step(np.array([actions[pos]], dtype=np.int64)); info = result["info"][0]
                terminated, truncated = bool(result["terminated"][0]), bool(result["truncated"][0])
                require(info["seed"]["actual_seed"] == SEEDS[i], "D2 environment seed changed")
                require(not (terminated and truncated) and info["bootstrap"] == (not terminated),
                        "D2 boundary flags differ")
                require(info["score_raw_fixed"] == info["score_delta_sum_raw_fixed"], "D2 score identity failed")
                objective = info["score_raw_fixed"] / 65536 + info["alive_frames"] / 100 - 5 * terminated
                require(math.isclose(info["objective_return"], objective, rel_tol=0, abs_tol=1e-9),
                        "D2 objective identity failed")
                if terminated or truncated:
                    completed[i] = {"episode_index": i, "seed": info["seed"]["actual_seed"],
                        "score_raw_fixed": info["score_raw_fixed"], "score": info["score_raw_fixed"] / 65536,
                        "alive_frames": info["alive_frames"], "gameplay_frames": info["gameplay_frames"],
                        "terminated": terminated, "truncated": truncated,
                        **death_fields(info, terminated, truncated)}
                    del envs[i], obs[i]
                else:
                    obs[i] = result["observations"]
            check_guard()
    finally:
        model.train(was_training)
    require(len(completed) == 64, "D2 evaluation incomplete")
    check_guard()
    return validate_rows([completed[i] for i in range(64)])
