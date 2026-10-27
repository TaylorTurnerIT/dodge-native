"""Development-only deterministic evaluation; B and E are not entry points."""
from __future__ import annotations

import math
import time

import numpy as np
import torch

from .identity import OBSERVATION_KEYS, read_protocol, require


def development_seeds() -> list[int]:
    protocol = read_protocol()
    return list(range(protocol["development"]["seed_start"],
                      protocol["development"]["seed_start"] + 64))


def require_development_seed(seed: int) -> None:
    require(type(seed) is int and seed in development_seeds(), "Only registered development D seeds are permitted")


def development_environment_config(seed: int, stage: str) -> dict:
    require_development_seed(seed)
    require(stage in {"D1", "D2", "D3"}, "Unknown development difficulty")
    difficulty = int(stage[-1])
    return {"batch_size": 1, "action_repeat": 4, "difficulty": difficulty,
            "patterns_enabled": difficulty != 1, "powerups_enabled": True,
            "raw_frame_cap": 2000 if difficulty == 1 else 18000,
            "num_threads": 1, "chunk_size": 1, "render_pixels": False,
            "auxiliary_targets": False, "seeds_by_slot": [[seed]],
            "excluded_seed_ranges": [tuple(pair) for pair in read_protocol()["training_excluded_ranges"]]}


def _guard(callback):
    if callback is not None:
        callback()


def summarize(rows: list[dict], stage: str, elapsed: float) -> dict:
    require(len(rows) == 64 and [row["seed"] for row in rows] == development_seeds(),
            "Development evaluation incomplete or seed order changed")
    cap = 2000 if stage == "D1" else 18000
    for row in rows:
        require(type(row["alive_frames"]) is int and type(row["gameplay_frames"]) is int
                and 0 <= row["alive_frames"] <= row["gameplay_frames"] <= cap,
                "Development row frame bounds differ")
        require(bool(row["terminated"]) != bool(row["truncated"]), "Development row is not a completed episode")
        require(row["score"] == row["score_raw_fixed"] / 65536
                and math.isfinite(row["score"]) and row["score_raw_fixed"] >= 0,
                "Development row score differs")
    return {"complete": True, "stage": stage, "episodes": 64,
            "mean_score": sum(row["score"] for row in rows) / 64,
            "mean_alive_frames": sum(row["alive_frames"] for row in rows) / 64,
            "raw_frames": sum(row["gameplay_frames"] for row in rows),
            "deaths": sum(row["terminated"] for row in rows),
            "caps": sum(row["truncated"] for row in rows),
            "elapsed_seconds": elapsed, "rows": rows,
            "action_mode": "deterministic_argmax", "gradients": False,
            "environment_layout": "64_independent_B1_envs;batched_policy_over_alive;no_reset"}


@torch.no_grad()
def evaluate(model, stage: str, device="cpu", *, check_guard=None, env_factory=None,
             episode_stream=None) -> dict:
    if env_factory is None:
        from . import VecDodgeEnv
        env_factory = VecDodgeEnv
    started = time.monotonic()
    device = torch.device(device)
    environments, observations = {}, {}
    rows = {}
    was_training = model.training
    model.eval()
    try:
        for index, seed in enumerate(development_seeds()):
            _guard(check_guard)
            env = env_factory(**development_environment_config(seed, stage))
            info = env.episode_info()[0]
            require(info["seed"]["evaluation"] and info["seed"]["actual_seed"] == seed
                    and info["startup_frames"] == 13, "Development constructor changed seed/startup")
            environments[index], observations[index] = env, env.observations()
        while environments:
            _guard(check_guard)
            active = sorted(environments)
            tensors = {name: torch.from_numpy(np.concatenate([observations[index][name]
                       for index in active], axis=0)).to(device) for name in OBSERVATION_KEYS}
            output = model(*(tensors[name] for name in OBSERVATION_KEYS))
            require(output.logits.shape == (len(active), 9)
                    and bool(torch.isfinite(output.logits).all()), "Nonfinite development policy")
            actions = output.logits.argmax(dim=-1).cpu().numpy()
            del output, tensors
            for position, index in enumerate(active):
                _guard(check_guard)
                result = environments[index].step(np.array([actions[position]], dtype=np.int64))
                info = result["info"][0]
                require(info["seed"]["actual_seed"] == development_seeds()[index], "Development seed changed")
                terminated, truncated = bool(result["terminated"][0]), bool(result["truncated"][0])
                require(not (terminated and truncated) and info["bootstrap"] == (not terminated),
                        "Development boundary flags differ")
                require(info["score_raw_fixed"] == info["score_delta_sum_raw_fixed"], "Development score identity failed")
                objective = info["score_raw_fixed"] / 65536 + info["alive_frames"] / 100 - 5 * terminated
                require(math.isclose(info["objective_return"], objective, rel_tol=0, abs_tol=1e-9),
                        "Development objective identity failed")
                if terminated or truncated:
                    row = {"episode_index": index, "seed": info["seed"]["actual_seed"],
                           "score_raw_fixed": info["score_raw_fixed"], "score": info["score_raw_fixed"] / 65536,
                           "alive_frames": info["alive_frames"], "gameplay_frames": info["gameplay_frames"],
                           "terminated": terminated, "truncated": truncated,
                           "objective_return": info["objective_return"]}
                    rows[index] = row
                    if episode_stream is not None:
                        from .supervision import emit
                        emit(episode_stream, row)
                    del environments[index], observations[index]
                else:
                    observations[index] = result["observations"]
            _guard(check_guard)
    finally:
        model.train(was_training)
    _guard(check_guard)
    return summarize([rows[i] for i in range(64)], stage, time.monotonic() - started)


def pilot_improved(before: dict, after: dict) -> bool:
    require(before.get("complete") is True and after.get("complete") is True
            and before["stage"] == after["stage"] == "D1", "Pilot development evaluations incomplete")
    require([r["seed"] for r in before["rows"]] == [r["seed"] for r in after["rows"]] == development_seeds(),
            "Pilot evaluations are not paired on registered D seeds")
    validate_summary(before)
    validate_summary(after)
    return after["mean_score"] > before["mean_score"] and after["mean_alive_frames"] > before["mean_alive_frames"]


def progress_passed(phase: str, evaluations: dict[str, dict]) -> bool:
    for result in evaluations.values():
        validate_summary(result)
    if phase == "D1":
        result = evaluations["D1"]
        return result["complete"] and result["mean_score"] >= 10 and result["mean_alive_frames"] >= 1500
    if phase == "D2":
        result = evaluations["D2"]
        return result["complete"] and result["mean_score"] >= 50 and result["mean_alive_frames"] >= 3060
    require(phase == "D3", "Unknown curriculum phase")
    d2, d3 = evaluations["D2"], evaluations["D3"]
    return (d2["complete"] and d3["complete"]
            and d2["mean_score"] >= 200.215 and d2["mean_alive_frames"] >= 6726.0523
            and d3["mean_score"] >= 177.266 and d3["mean_alive_frames"] >= 4433.0418)


def validate_summary(result: dict) -> None:
    expected = summarize(result["rows"], result["stage"], result["elapsed_seconds"])
    for key in ("complete", "stage", "episodes", "mean_score", "mean_alive_frames",
                "raw_frames", "deaths", "caps"):
        require(result[key] == expected[key], f"Development summary {key} differs from rows")
