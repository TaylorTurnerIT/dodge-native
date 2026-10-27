#!/usr/bin/env python3
"""Frozen, parent-leased M2 validation. No training, implicit retries, or reset policy."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import signal
import statistics
import struct
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "learning/runs/v2/milestone2-validation-harness-r1"
STATE = ROOT / "learning/runs/v2-orchestration/state.json"
PLAN_PATH = ARTIFACT / "campaign-plan.json"
POLICY = "nearest_lethal_aabb_safe_powerup"
POLICY_SHA256 = "eeae605299b1018437a54df66f4eabf6e6d4defc20334c1baf93692900601b85"
NATIVE_TEST = "qualification_replay_tests::frozen_m0_full_heuristic_d2_d3"
BASELINES = {
    2: ("learning/runs/v2/milestone0-campaign-r2/native-results/baselines/episodes.jsonl", "40b5a8a1614a304bfd041dcd6eedfd7e68262f60fbca5cf6acfc1ece9a2694b3"),
    3: ("learning/runs/v2/gate-baselines-r1/native-results/d3/episodes.jsonl", "cd0222856a3e56d3eb2b7ae89228314af5d35feefb1e28784aadfab3ad4f9801"),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stamp() -> str:
    return utc_now().isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_new(path: Path, value) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def event(stream, value) -> None:
    stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
    stream.flush()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_plan() -> dict:
    plan = json.loads(PLAN_PATH.read_text())
    require(plan["version"] == "m2_validation_campaign_v1", "Unknown campaign plan")
    require(plan["campaign_wall_seconds"] == 1800 and plan["receipt_reserve_seconds"] == 600, "Campaign budget changed")
    require(plan["observed_worker_peak_rss_limit_bytes"] == 6 * 1024**3, "RSS limit changed")
    memory = next(stage for stage in plan["stages"] if stage["name"] == "memory")
    require(memory["warmup_step_calls"] == 5000 and memory["measured_step_calls"] == 100000, "Memory workload changed")
    require(memory["plateau_median_growth_max_bytes"] == 64 * 1024**2, "Memory criterion changed")
    return plan


def assert_cutoff_budget(now: datetime, plan: dict) -> None:
    cutoff = datetime.fromisoformat(plan["cutoff_utc"].replace("Z", "+00:00"))
    require(now + timedelta(seconds=plan["campaign_wall_seconds"] + plan["receipt_reserve_seconds"]) <= cutoff, "Full campaign budget plus receipt reserve does not fit cutoff")


def assert_lease(run_id: str, identity_hash: str) -> dict:
    state = json.loads(STATE.read_text())
    lease = state.get("active_long_campaign")
    require(isinstance(lease, dict), "No parent-owned long-campaign lease")
    require(lease.get("run_id") == run_id and lease.get("identity_sha256") == identity_hash, "Campaign lease identity mismatch")
    require(lease.get("kind") == "M2_validation" and lease.get("authorization") == "frozen_reviewed_M2_campaign", "Campaign was not registered after frozen review")
    return lease


def source_inventory() -> dict[str, str]:
    paths = {ROOT / name for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", ".cargo/config.toml", "assets/dodge.p8")}
    skip = {"target", ".venv", "__pycache__", ".pytest_cache", "build", "dist"}
    for base in (ROOT / "crates", ROOT / "python"):
        for path in base.rglob("*"):
            if path.is_file() and not skip.intersection(path.relative_to(base).parts) and (path.suffix in {".rs", ".py", ".toml", ".lock"} or path.name == "requirements-local-mac.txt"):
                paths.add(path)
    for name in ("docs/SPEC_PRIVILEGED_VIT_RL.md", "docs/implementation-plan-v2.md", "docs/v2-environment-contract.md", "docs/teacher-qualification-v2.json"):
        paths.add(ROOT / name)
    paths.add(Path(__file__).resolve())
    paths.update(path for path in ARTIFACT.iterdir() if path.is_file() and path.suffix in {".py", ".rs"})
    paths.update({PLAN_PATH, ARTIFACT / "expected-generation.json"})
    return {str(path.relative_to(ROOT)): sha256(path) for path in sorted(paths)}


def runtime_identity() -> dict:
    np = importlib.import_module("numpy")
    extension = importlib.import_module("dodge_rl._native")
    package = importlib.import_module("dodge_rl")
    require("torch" not in sys.modules, "M2 validation unexpectedly imports Torch")
    extension_path = Path(extension.__file__).resolve()
    hardware = {}
    if sys.platform == "darwin":
        for key in ("hw.memsize", "hw.physicalcpu", "machdep.cpu.brand_string"):
            hardware[key] = subprocess.check_output(["sysctl", "-n", key], text=True).strip()
    return {"python_executable": str(Path(sys.executable).resolve()), "python_version": sys.version, "numpy_version": np.__version__, "package_path": str(Path(package.__file__).resolve()), "extension_path": str(extension_path), "extension_sha256": sha256(extension_path), "platform": platform.platform(), "machine": platform.machine(), "hardware": hardware}


def freeze_identity(args) -> None:
    require(Path(sys.prefix).resolve() == (ROOT / "python/.venv").resolve(), "Use python/.venv for real extension identity")
    require(sha256(ROOT / "crates/dodge-rl-env/tests/support/m0_policy.rs") == POLICY_SHA256, "Frozen M0 policy changed")
    plan = read_plan()
    binary = args.native_test_binary.resolve(strict=True)
    build_receipt = args.build_receipt.resolve(strict=True)
    identity = {"version": "m2_validation_identity_v1", "created_at_utc": stamp(), "plan_sha256": sha256(PLAN_PATH), "source_sha256": source_inventory(), "runtime": runtime_identity(), "native_test_binary": str(binary), "native_test_name": NATIVE_TEST, "build_receipt": str(build_receipt), "binary_and_receipt_sha256": {str(binary): sha256(binary), str(build_receipt): sha256(build_receipt), str(Path(sys.executable).resolve()): sha256(Path(sys.executable).resolve())}, "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "git_status": subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True), "campaign_seconds": plan["campaign_wall_seconds"], "provenance_limit": "Parent must reconcile retained build receipts against source and binary identities before review. Freezing alone does not establish build provenance."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_new(args.output, identity)
    print(json.dumps({"identity": str(args.output), "sha256": sha256(args.output)}))


def check_identity(path: Path, check_runtime: bool = False) -> dict:
    identity = json.loads(path.read_text())
    require(identity["version"] == "m2_validation_identity_v1", "Unknown frozen identity")
    require(identity["plan_sha256"] == sha256(PLAN_PATH), "Plan changed after freeze")
    require(identity["source_sha256"] == source_inventory(), "Rust/Python/harness source inventory changed after freeze")
    for name, expected in identity["binary_and_receipt_sha256"].items():
        require(sha256(Path(name)) == expected, f"Binary or build receipt changed: {name}")
    require(sha256(Path(identity["runtime"]["extension_path"])) == identity["runtime"]["extension_sha256"], "Installed extension changed")
    if check_runtime:
        require(runtime_identity() == identity["runtime"], "Worker imports a different runtime or extension")
    return identity


def current_rss_bytes(pid: int) -> int:
    result = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
    require(result.returncode == 0 and result.stdout.strip().isdigit(), f"Cannot sample RSS for PID {pid}: {result.stderr.strip()}")
    return int(result.stdout.strip()) * 1024


def peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def load_baselines() -> dict[int, list[dict]]:
    output = {}
    for difficulty, (name, expected_hash) in BASELINES.items():
        require(sha256(ROOT / name) == expected_hash, f"Original baseline hash mismatch: {name}")
        with (ROOT / name).open() as stream:
            rows = sorted((json.loads(line) for line in stream if line.strip()), key=lambda row: (row["policy"], row["episode_index"]))
        rows = [row for row in rows if row["policy"] == POLICY]
        require(len(rows) == 1000, "Baseline must contain exactly 1000 heuristic rows")
        for index, row in enumerate(rows):
            config = row["native_config"]
            require(row["episode_index"] == index and row["seed"] == 0xB0000000 + index, "Baseline seed order changed")
            require(config["difficulty"] == difficulty and config["patterns_enabled"] and config["powerups_enabled"] and config["theme_background_shadow"] == [12, 1] and config["initial_highscores_raw_fixed"] == [0] * 12, "Baseline configuration changed")
            require(row["episode_status"] == "complete" and not row["failure"] and not row["run_deadline_truncation"] and row["startup_native_frames_excluded"] == 13, "Incomplete baseline row")
        output[difficulty] = rows
    return output


def parse_native_output(log: Path) -> dict:
    expected = load_baselines()
    rows, patterns, summaries, total = {}, {}, {}, []
    prefixes = {"V2_FULL_PARITY_EPISODE ": "episode", "V2_FULL_PARITY_PATTERN ": "pattern", "V2_FULL_PARITY_DIFFICULTY ": "difficulty", "V2_FULL_PARITY_TOTAL ": "total"}
    for line in log.read_text().splitlines():
        for prefix, kind in prefixes.items():
            if prefix not in line:
                continue
            # libtest may prefix a single line with its test name before nocapture.
            record = json.loads(line.split(prefix, 1)[1])
            if kind == "episode":
                key = (record["difficulty"], record["episode_index"])
                require(key not in rows, "Duplicate native episode receipt")
                rows[key] = record
            elif kind == "pattern":
                key = (record["difficulty"], record["id"])
                require(key not in patterns, "Duplicate native pattern receipt")
                patterns[key] = record["frames"]
            elif kind == "difficulty":
                require(record["difficulty"] not in summaries, "Duplicate difficulty summary")
                summaries[record["difficulty"]] = record
            else:
                total.append(record)
    require(len(rows) == 2000 and set(summaries) == {2, 3} and len(total) == 1, "Incomplete full native parity output")
    output = {}
    frame_total = 0
    for difficulty, baseline in expected.items():
        expected_patterns = {}
        raw_frames = alive = score = caps = 0
        for index, reference in enumerate(baseline):
            actual = rows[(difficulty, index)]
            required = {"seed": reference["seed"], "score_raw_fixed": reference["scores"]["final_score_raw_fixed"], "raw_frames": reference["gameplay_native_frames"], "alive_frames": reference["raw_survival_frames"], "terminated": reference["death"], "truncated": reference["cap_truncation"], "death_events": reference["frame_event_counts_enemy_spawn_collision_death_pattern_active_terminal"][2], "full_state_hash": reference["final_state_hash"]}
            require(all(actual.get(key) == value for key, value in required.items()), f"D{difficulty} episode {index} differs from original M0: {actual}")
            objective = required["score_raw_fixed"] / 65536 + required["alive_frames"] / 100 - 5 * required["terminated"]
            require(actual["objective_return"] == objective, "Native objective accounting mismatch")
            raw_frames += required["raw_frames"]
            alive += required["alive_frames"]
            score += required["score_raw_fixed"]
            caps += required["truncated"]
            for pattern in reference["counts"]["pattern_frames"]:
                expected_patterns[pattern["id"]] = expected_patterns.get(pattern["id"], 0) + pattern["frames"]
        require({key[1]: count for key, count in patterns.items() if key[0] == difficulty} == expected_patterns, f"D{difficulty} pattern coverage differs")
        wanted = {"difficulty": difficulty, "episodes": 1000, "raw_frames_per_path": raw_frames, "alive_frames": alive, "score_sum_raw_fixed": score, "caps": caps, "pattern_ids": len(expected_patterns)}
        require(summaries[difficulty] == wanted, "Native summary differs from parsed rows")
        output[f"D{difficulty}"] = dict(wanted, score_mean=score / 65536 / 1000, alive_frames_mean=alive / 1000, pattern_frames=expected_patterns)
        frame_total += raw_frames
    require(total[0]["episodes"] == 2000 and total[0]["raw_frames_per_path"] == frame_total, "Native total mismatch")
    return {"status": "passed", "episodes": 2000, "raw_frames_per_path": frame_total, "difficulties": output, "native_total": total[0], "original_datasets_sha256": {name: sha for name, sha in BASELINES.values()}}


def memory_plateau(samples: list[dict], expected_last_step: int = 100000) -> dict:
    require(len(samples) == 101, "Expected warm boundary plus 100 post-warmup RSS samples")
    require([sample["measured_step_calls"] for sample in samples] == list(range(0, expected_last_step + 1, 1000)), "Missing or reordered RSS samples")
    values = [sample["rss_bytes"] for sample in samples]
    count = math.ceil(len(values) / 10)
    first, last = statistics.median(values[:count]), statistics.median(values[-count:])
    x = [sample["measured_step_calls"] for sample in samples]
    mean_x, mean_y = statistics.mean(x), statistics.mean(values)
    slope = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, values)) / sum((a - mean_x) ** 2 for a in x)
    growth = last - first
    return {"passed": growth <= 64 * 1024**2, "sample_count": len(samples), "endpoint_sample_count_each": count, "first_median_rss_bytes": first, "last_median_rss_bytes": last, "median_growth_bytes": growth, "median_growth_limit_bytes": 64 * 1024**2, "ols_rss_bytes_per_step_call": slope, "interpretation": "Empirical post-warmup plateau under this workload; no mathematical zero-leak claim."}


def array_digest(np, observation: dict, only_neural: bool = False) -> str:
    keys = ["global_feats", "entity_feats", "entity_types", "entity_mask"] if only_neural else ["global_feats", "entity_feats", "entity_types", "entity_mask", "indices", "pixels", "auxiliary", "pixel_valid", "pixel_aux_pair_valid"]
    digest = hashlib.sha256()
    for key in keys:
        value = observation[key]
        digest.update(key.encode())
        if value is None:
            digest.update(b"None")
        else:
            array = np.asarray(value)
            digest.update(str(array.dtype).encode())
            digest.update(str(array.shape).encode())
            digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def validate_observation(np, observation: dict, batch: int, pixels: bool, auxiliary: bool) -> None:
    indices = observation["indices"]
    require(isinstance(indices, np.ndarray) and indices.shape == (batch,) and indices.dtype.kind in "iu" and indices.flags.c_contiguous, "Wrong subset index array")
    required = {"global_feats": ((batch, 1, 14), np.float32), "entity_feats": ((batch, 80, 16), np.float32), "entity_types": ((batch, 80), np.int64), "entity_mask": ((batch, 80), np.bool_), "pixel_valid": ((batch,), np.bool_), "pixel_aux_pair_valid": ((batch,), np.bool_)}
    if pixels:
        required["pixels"] = ((batch, 4, 128, 128), np.uint8)
    else:
        require(observation["pixels"] is None, "Unexpected pixels")
    if auxiliary:
        required["auxiliary"] = ((batch, 5, 16, 16), np.float32)
    else:
        require(observation["auxiliary"] is None, "Unexpected targets")
    for key, (shape, dtype) in required.items():
        value = observation[key]
        require(isinstance(value, np.ndarray) and value.shape == shape and value.dtype == dtype and value.flags.c_contiguous, f"Wrong {key} shape/dtype/contiguity")
        require(bool(np.isfinite(value).all()), f"Nonfinite {key}")
    mask, types = observation["entity_mask"], observation["entity_types"]
    require(bool((types[~mask] == 0).all()) and bool(((types[mask] >= 1) & (types[mask] <= 8)).all()), "Types/padding disagree")
    require(bool((observation["entity_feats"][~mask] == 0).all()), "Nonzero padded entity scalars")
    if pixels:
        require(bool((observation["pixels"] <= 15).all()), "Palette overflow")
    if auxiliary:
        require(bool(((observation["auxiliary"] == 0) | (observation["auxiliary"] == 1)).all()), "Targets are not independent binary channels")


def base_config(plan: dict, **changes) -> dict:
    config = {"batch_size": 8, "action_repeat": 4, "difficulty": 2, "patterns_enabled": True, "powerups_enabled": True, "raw_frame_cap": 18000, "num_threads": 4, "chunk_size": 2, "render_pixels": True, "auxiliary_targets": True, "run_seed": plan["training_run_seed"], "excluded_seed_ranges": plan["effective_reserved_ranges"]}
    config.update(changes)
    return config


def audit_info(info: dict, plan: dict, cap: int) -> None:
    seed = info["seed"]
    require(not seed["evaluation"], "Python stress/profile unexpectedly uses evaluation seeds")
    require(all(not low <= seed["actual_seed"] <= high for low, high in plan["effective_reserved_ranges"]), "Reserved seed constructed")
    require(info["startup_frames"] == 13 and 0 <= info["alive_frames"] <= info["gameplay_frames"] <= cap, "Startup/cap accounting mismatch")
    require(not (info["terminated"] and info["truncated"]), "Death and cap both set")
    require(info["bootstrap"] == (not info["terminated"]), "Wrong bootstrap marker")
    require(info["score_delta_sum_raw_fixed"] == info["score_raw_fixed"], "Cumulative fixed score identity mismatch")
    objective = info["score_delta_sum_raw_fixed"] / 65536 + info["alive_frames"] / 100 - 5 * info["terminated"]
    require(info["objective_return"] == objective, "Exact episode objective mismatch")


def audit_step(np, result: dict, plan: dict, cap: int) -> None:
    expected = result["score_delta_raw_fixed"].astype(np.float64) / 65536 + result["alive_raw_frames"].astype(np.float64) / 100 - 5 * result["terminated"].astype(np.float64)
    require(bool(np.allclose(result["rewards"], expected, rtol=0, atol=1e-5)), "Unscaled step reward identity mismatch")
    require(bool((result["elapsed_raw_frames"] >= 1).all()) and bool((result["elapsed_raw_frames"] <= 4).all()), "Bad executed K")
    for info in result["info"]:
        audit_info(info, plan, cap)


def compare_tree(np, left, right, name="payload") -> None:
    if isinstance(left, np.ndarray):
        require(isinstance(right, np.ndarray) and left.dtype == right.dtype and left.shape == right.shape and bool(np.array_equal(left, right)), f"Thread/chunk mismatch: {name}")
    elif isinstance(left, dict):
        require(isinstance(right, dict) and left.keys() == right.keys(), f"Dictionary keys differ: {name}")
        for key in left:
            compare_tree(np, left[key], right[key], name + "." + key)
    elif isinstance(left, (list, tuple)):
        require(isinstance(right, type(left)) and len(left) == len(right), f"Sequence differs: {name}")
        for index, (a, b) in enumerate(zip(left, right)):
            compare_tree(np, a, b, f"{name}[{index}]")
    else:
        require(left == right, f"Metadata differs: {name}")


def worker_trajectory(np, Env, plan: dict, directory: Path) -> dict:
    stage = next(stage for stage in plan["stages"] if stage["name"] == "trajectory")
    summaries = []
    for case in (stage["default_cap_case"], stage["ragged_cap_case"]):
        batch, cap = case["batch_size"], case["raw_frame_cap"]
        left = Env(**base_config(plan, batch_size=batch, raw_frame_cap=cap, num_threads=1, chunk_size=1))
        right = Env(**base_config(plan, batch_size=batch, raw_frame_cap=cap, num_threads=4, chunk_size=3))
        observation = left.observations()
        compare_tree(np, observation, right.observations())
        validate_observation(np, observation, batch, True, True)
        old = {key: value for key, value in observation.items() if isinstance(value, np.ndarray)}
        # Mutate owned old outputs and verify engine state remains equal to control.
        for value in old.values():
            value.fill(0)
        sentinels = {key: value.copy() for key, value in old.items()}
        compare_tree(np, left.observations(), right.observations())
        rng = np.random.Generator(np.random.PCG64(plan["action_rng_seed"]))
        raw_frames = resets = caps = deaths = ragged = 0
        for _ in range(case["decisions"]):
            actions = rng.integers(0, 9, size=batch, dtype=np.int64)
            a, b = left.step(actions), right.step(actions.copy())
            compare_tree(np, a, b)
            audit_step(np, a, plan, cap)
            validate_observation(np, a["observations"], batch, True, True)
            raw_frames += int(a["elapsed_raw_frames"].sum())
            ragged += int((a["elapsed_raw_frames"] < 4).sum())
            caps += int(a["truncated"].sum())
            deaths += int(a["terminated"].sum())
            for key, value in old.items():
                require(not np.shares_memory(value, a["observations"][key]), "Returned arrays alias across calls")
                require(bool(np.array_equal(value, sentinels[key])), "Retained array was overwritten")
            ended = np.flatnonzero(a["terminated"] | a["truncated"]).tolist()
            if ended:
                a_reset, b_reset = left.reset_done(ended[::-1]), right.reset_done(ended[::-1])
                compare_tree(np, a_reset, b_reset)
                require(list(a_reset["observations"]["indices"]) == ended[::-1], "Subset reset row order differs")
                resets += len(ended)
        if cap == 17:
            require(caps > 0 and ragged > 0, "Ragged-cap trajectory fixture did not exercise truncation")
        else:
            require(deaths > 0, "Default-cap trajectory fixture did not exercise terminal resets")
        summaries.append({"config": dict(case, thread_chunk_pairs=stage["thread_chunk_pairs"]), "raw_frames_per_path": raw_frames, "explicit_slot_resets": resets, "deaths": deaths, "caps": caps, "ragged_K_endings": ragged, "final_observation_sha256": array_digest(np, left.observations())})
    return {"status": "passed", "cases": summaries}


def worker_memory(np, Env, plan: dict, directory: Path) -> dict:
    stage = next(stage for stage in plan["stages"] if stage["name"] == "memory")
    env = Env(**base_config(plan))
    rng = np.random.Generator(np.random.PCG64(plan["action_rng_seed"]))
    raw_frames = resets = deaths = caps = 0
    warmup_raw_frames = None
    observed_enemy_max = observed_rect_max = 0
    samples = []
    old = env.observations()
    retained = {key: value for key, value in old.items() if isinstance(value, np.ndarray)}
    frozen = {key: value.copy() for key, value in retained.items()}
    with (directory / "memory-episodes.jsonl").open("x") as episodes, (directory / "memory-rss.jsonl").open("x") as rss_stream:
        event(episodes, {"kind": "initial", "info": env.episode_info()})
        for call in range(stage["warmup_step_calls"] + stage["measured_step_calls"]):
            if call == stage["warmup_step_calls"]:
                warmup_raw_frames = raw_frames
                sample = {"at_utc": stamp(), "measured_step_calls": 0, "rss_bytes": current_rss_bytes(os.getpid()), "raw_frames_including_warmup": raw_frames}
                samples.append(sample)
                event(rss_stream, sample)
            result = env.step(rng.integers(0, 9, size=stage["batch_size"], dtype=np.int64))
            audit_step(np, result, plan, stage["raw_frame_cap"])
            raw_frames += int(result["elapsed_raw_frames"].sum())
            deaths += int(result["terminated"].sum())
            caps += int(result["truncated"].sum())
            for row in result["observations"]["diagnostics"]:
                observed_enemy_max = max(observed_enemy_max, row["admitted_enemies"])
                observed_rect_max = max(observed_rect_max, row["admitted_rectangles"])
            ended = np.flatnonzero(result["terminated"] | result["truncated"]).tolist()
            if ended:
                event(episodes, {"kind": "ended", "step_call": call + 1, "info": [result["info"][index] for index in ended]})
                reset = env.reset_done(ended)
                for info in reset["info"]:
                    audit_info(info, plan, stage["raw_frame_cap"])
                event(episodes, {"kind": "reset", "step_call": call + 1, "info": reset["info"]})
                resets += len(ended)
            measured = call + 1 - stage["warmup_step_calls"]
            if measured > 0 and measured % stage["sample_every_step_calls"] == 0:
                sample = {"at_utc": stamp(), "measured_step_calls": measured, "rss_bytes": current_rss_bytes(os.getpid()), "raw_frames_including_warmup": raw_frames}
                require(sample["rss_bytes"] <= plan["observed_worker_peak_rss_limit_bytes"], "Worker RSS guard exceeded")
                samples.append(sample)
                event(rss_stream, sample)
                for key, value in retained.items():
                    require(not np.shares_memory(value, result["observations"][key]), "Memory stress outputs alias")
                    require(bool(np.array_equal(value, frozen[key])), "Retained old output was overwritten")
        plateau = memory_plateau(samples)
        require(plateau["passed"], f"Post-warmup plateau failed: {plateau}")
    require(peak_rss_bytes() <= plan["observed_worker_peak_rss_limit_bytes"], "Worker observed peak RSS guard exceeded")
    require(warmup_raw_frames is not None, "Warmup boundary was not recorded")
    return {"status": "passed", "config": base_config(plan), "batch_info": env.batch_info(), "warmup_step_calls": stage["warmup_step_calls"], "measured_step_calls": stage["measured_step_calls"], "warmup_raw_frames": warmup_raw_frames, "measured_raw_frames": raw_frames - warmup_raw_frames, "raw_frames_including_warmup": raw_frames, "explicit_slot_resets": resets, "deaths_including_warmup": deaths, "caps_including_warmup": caps, "max_admitted_enemies": observed_enemy_max, "max_admitted_rectangles": observed_rect_max, "post_warmup_samples": plateau, "retained_output_ownership_checks": True, "coverage_limit": plan["memory_coverage_limit"]}


def worker_throughput(np, Env, plan: dict, directory: Path) -> dict:
    stage = next(stage for stage in plan["stages"] if stage["name"] == "throughput")
    batch = stage["batch_size"]
    rng = np.random.Generator(np.random.PCG64(plan["action_rng_seed"]))
    warm = rng.integers(0, 9, size=(stage["warmup_step_calls"], batch), dtype=np.int64)
    actions = rng.integers(0, 9, size=(stage["measured_step_calls"], batch), dtype=np.int64)
    action_hash = hashlib.sha256(actions.astype("<i8", copy=False).tobytes()).hexdigest()
    results = []
    for pixels in stage["render_modes"]:
        for threads, chunk in stage["thread_chunk_pairs"]:
            config = base_config(plan, batch_size=batch, num_threads=threads, chunk_size=chunk, render_pixels=pixels, auxiliary_targets=False)
            env = Env(**config)
            seed_hash = hashlib.sha256()
            # At most B*(warmup+measured+1) small tuples are retained. Write
            # their exact values after timing; the timed loop does no file I/O.
            seed_assignments = []
            def note_seeds(infos, phase, call):
                for info in infos:
                    seed = info["seed"]
                    values = (seed["slot"], seed["episode"], seed["counter"], seed["actual_seed"])
                    seed_hash.update(struct.pack("<QQQI", *values))
                    seed_assignments.append((phase, call, *values))
            note_seeds(env.episode_info(), "initial", 0)
            for warm_index, vector in enumerate(warm):
                result = env.step(vector)
                ended = np.flatnonzero(result["terminated"] | result["truncated"]).tolist()
                if ended:
                    note_seeds(env.reset_done(ended)["info"], "warmup_reset", warm_index + 1)
            work_hash = hashlib.sha256()
            raw_frames = resets = 0
            start = time.monotonic()
            for call_index, vector in enumerate(actions):
                require(time.monotonic() - start <= stage["per_config_wall_seconds"], "Throughput config wall guard exceeded")
                result = env.step(vector)
                raw_frames += int(result["elapsed_raw_frames"].sum())
                for key in ("elapsed_raw_frames", "score_delta_raw_fixed", "terminated", "truncated"):
                    work_hash.update(result[key].tobytes())
                ended = np.flatnonzero(result["terminated"] | result["truncated"]).tolist()
                if ended:
                    reset = env.reset_done(ended)
                    note_seeds(reset["info"], "timed_reset", call_index + 1)
                    resets += len(ended)
            elapsed = time.monotonic() - start
            observations = env.observations()
            validate_observation(np, observations, batch, pixels, False)
            seed_log = directory / f"throughput-seeds-pixels{int(pixels)}-threads{threads}-chunk{chunk}.jsonl"
            with seed_log.open("x") as stream:
                for phase, call, slot, episode, counter, actual in seed_assignments:
                    require(all(not low <= actual <= high for low, high in plan["effective_reserved_ranges"]), "Throughput constructed a reserved seed")
                    event(stream, {"phase": phase, "step_call": call, "slot": slot, "episode": episode, "counter": counter, "actual_seed": actual})
            results.append({"config": config, "batch_info": env.batch_info(), "warmup_step_calls": stage["warmup_step_calls"], "measured_step_calls": stage["measured_step_calls"], "environment_decisions": stage["measured_step_calls"] * batch, "raw_gameplay_frames": raw_frames, "wall_seconds": elapsed, "public_step_calls_per_second": stage["measured_step_calls"] / elapsed, "environment_decisions_per_second": stage["measured_step_calls"] * batch / elapsed, "raw_gameplay_frames_per_second": raw_frames / elapsed, "explicit_slot_resets": resets, "action_schedule_sha256": action_hash, "actual_reset_seed_schedule_sha256": seed_hash.hexdigest(), "actual_seed_assignments": len(seed_assignments), "actual_seed_log": seed_log.name, "actual_seed_log_sha256": sha256(seed_log), "work_schedule_sha256": work_hash.hexdigest(), "final_neural_arrays_sha256": array_digest(np, observations, only_neural=True), "costs": stage["throughput_costs"]})
    for key in ("actual_reset_seed_schedule_sha256", "work_schedule_sha256", "final_neural_arrays_sha256", "raw_gameplay_frames", "explicit_slot_resets"):
        require(len({result[key] for result in results}) == 1, f"Throughput paired workload differs: {key}")
    return {"status": "passed", "measurements": results, "comparison_limit": "Actual public API measurements under a fixed random workload; no causal speedup claim against differently configured historical engine profiles."}


def worker(args) -> None:
    plan = read_plan()
    identity_hash = sha256(args.identity)
    assert_lease(args.run_id, identity_hash)
    check_identity(args.identity, check_runtime=True)
    np = importlib.import_module("numpy")
    Env = importlib.import_module("dodge_rl").VecDodgeEnv
    funcs = {"trajectory": worker_trajectory, "memory": worker_memory, "throughput": worker_throughput}
    started = time.monotonic()
    try:
        result = funcs[args.phase](np, Env, plan, args.directory)
        result.update({"phase": args.phase, "at_utc": stamp(), "elapsed_seconds": time.monotonic() - started, "observed_peak_self_rss_bytes": peak_rss_bytes(), "identity_sha256": identity_hash})
        require(result["observed_peak_self_rss_bytes"] <= plan["observed_worker_peak_rss_limit_bytes"], "Final observed peak RSS exceeded")
        save_new(args.directory / (args.phase + "-result.json"), result)
    except BaseException as error:
        save_new(args.directory / (args.phase + "-failure.json"), {"status": "failed", "phase": args.phase, "at_utc": stamp(), "elapsed_seconds": time.monotonic() - started, "error": repr(error), "traceback": traceback.format_exc(), "observed_peak_self_rss_bytes": peak_rss_bytes()})
        raise


def stop_owned(process: subprocess.Popen) -> dict:
    result = {"owned_pid": process.pid, "owned_pgid": process.pid, "term_sent": False, "kill_sent": False}
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            result["term_sent"] = True
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            result["kill_sent"] = True
            process.wait(timeout=5)
        except ProcessLookupError:
            pass
    return result


def campaign(args) -> None:
    plan = read_plan()
    assert_cutoff_budget(utc_now(), plan)
    identity = check_identity(args.identity)
    identity_hash = sha256(args.identity)
    assert_lease(args.run_id, identity_hash)
    args.output.mkdir(parents=True, exist_ok=False)
    save_new(args.output / "registered-plan.json", plan)
    save_new(args.output / "identity.json", identity)
    started = time.monotonic()
    deadline = started + plan["campaign_wall_seconds"]
    phases = []
    overall = {"run_id": args.run_id, "started_at_utc": stamp(), "status": "running", "identity_sha256": identity_hash, "registered_plan_sha256": sha256(PLAN_PATH), "rss_sample_seconds": plan["supervisor_rss_sample_seconds"], "rss_limit_bytes": plan["observed_worker_peak_rss_limit_bytes"], "guards": "Cooperative sampled worker RSS and wall/cutoff guards; not a hard OS ceiling.", "phases": phases}
    save_new(args.output / "campaign-start.json", overall)
    active = None
    try:
        for stage in plan["stages"]:
            assert_lease(args.run_id, identity_hash)
            check_identity(args.identity)
            name = stage["name"]
            phase = {"name": name, "at_utc": stamp(), "wall_limit_seconds": stage["wall_seconds"], "status": "running"}
            if name == "native_parity":
                command = [identity["native_test_binary"], NATIVE_TEST, "--ignored", "--exact", "--nocapture", "--test-threads=1"]
            else:
                command = [sys.executable, str(Path(__file__).resolve()), "_worker", "--phase", name, "--identity", str(args.identity.resolve()), "--run-id", args.run_id, "--directory", str(args.output.resolve())]
            phase["command"] = command
            save_new(args.output / (name + "-command.json"), phase)
            log = args.output / (name + ".stdout.log")
            with log.open("xb") as stdout, (args.output / (name + ".rss.jsonl")).open("x") as rss_stream:
                phase_started = time.monotonic()
                active = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=subprocess.STDOUT, start_new_session=True)
                phase.update({"owned_pid": active.pid, "owned_pgid": active.pid, "observed_peak_worker_rss_bytes": None, "rss_samples": 0})
                save_new(args.output / (name + "-launch.json"), phase)
                while active.poll() is None:
                    assert_lease(args.run_id, identity_hash)
                    require(time.monotonic() < deadline, "Campaign wall guard expired")
                    require(time.monotonic() - phase_started <= stage["wall_seconds"], f"{name} wall guard expired")
                    require(utc_now() < datetime.fromisoformat(plan["cutoff_utc"].replace("Z", "+00:00")), "Overnight cutoff reached")
                    try:
                        rss = current_rss_bytes(active.pid)
                    except ValueError:
                        if active.poll() is not None:
                            break
                        raise
                    phase["observed_peak_worker_rss_bytes"] = max(phase["observed_peak_worker_rss_bytes"] or 0, rss)
                    phase["rss_samples"] += 1
                    event(rss_stream, {"at_utc": stamp(), "wall_seconds": time.monotonic() - phase_started, "pid": active.pid, "rss_bytes": rss})
                    require(rss <= plan["observed_worker_peak_rss_limit_bytes"], f"{name} sampled RSS guard exceeded")
                    time.sleep(plan["supervisor_rss_sample_seconds"])
                phase.update({"exit_code": active.wait(), "elapsed_seconds": time.monotonic() - phase_started, "stdout_sha256": sha256(log)})
                require(phase["exit_code"] == 0, f"{name} failed with exit {phase['exit_code']}")
            if name == "native_parity":
                require(phase["rss_samples"] > 0, "Native run completed without any retained RSS sample")
                result = parse_native_output(log)
                save_new(args.output / "native-parity-audit.json", result)
            else:
                result_path = args.output / (name + "-result.json")
                result = json.loads(result_path.read_text())
                require(result["status"] == "passed" and result["identity_sha256"] == identity_hash, "Worker result/identity failed")
                require(result["observed_peak_self_rss_bytes"] <= plan["observed_worker_peak_rss_limit_bytes"], "Worker final peak RSS failed")
                phase["worker_result_sha256"] = sha256(result_path)
            phase["status"] = "passed"
            phases.append(phase)
            save_new(args.output / (name + "-receipt.json"), phase)
            active = None
        check_identity(args.identity)
        overall["status"] = "passed"
    except BaseException as error:
        overall.update({"status": "failed", "error": repr(error), "traceback": traceback.format_exc()})
        if active is not None:
            overall["owned_process_stop"] = stop_owned(active)
            phase.update({"status": "failed", "exit_code": active.returncode, "elapsed_seconds": time.monotonic() - phase_started, "stdout_sha256": sha256(log)})
            phases.append(phase)
            save_new(args.output / (phase["name"] + "-receipt.json"), phase)
        raise
    finally:
        overall.update({"finished_at_utc": stamp(), "elapsed_seconds": time.monotonic() - started, "automatic_retries": 0, "resource_limits_relaxed": False})
        save_new(args.output / "campaign-result.json", overall)
        hashes = {str(path.relative_to(args.output)): sha256(path) for path in sorted(args.output.rglob("*")) if path.is_file()}
        save_new(args.output / "artifact-sha256.json", hashes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze", help="Read runtime and build identities; does not construct environments")
    freeze.add_argument("--native-test-binary", type=Path, required=True)
    freeze.add_argument("--build-receipt", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("campaign", help="Execute once under a parent-owned reviewed campaign lease")
    run.add_argument("--identity", type=Path, required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--output", type=Path, required=True)
    parse = sub.add_parser("audit-native", help="Read an existing native log; never rerun native work")
    parse.add_argument("--log", type=Path, required=True)
    parse.add_argument("--output", type=Path, required=True)
    internal = sub.add_parser("_worker", help=argparse.SUPPRESS)
    internal.add_argument("--phase", choices=("trajectory", "memory", "throughput"), required=True)
    internal.add_argument("--identity", type=Path, required=True)
    internal.add_argument("--run-id", required=True)
    internal.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "freeze":
        freeze_identity(args)
    elif args.command == "campaign":
        campaign(args)
    elif args.command == "audit-native":
        save_new(args.output, parse_native_output(args.log))
    else:
        worker(args)


if __name__ == "__main__":
    main()
