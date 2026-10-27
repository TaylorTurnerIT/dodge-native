"""Parent-reserved one-shot R6 resource probe. Never writes leases or state."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREPARE = ROOT / "learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r6"

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())

def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)

def verify_pins(pins_path: Path, pins_sha256: str) -> dict:
    require(sha(pins_path) == pins_sha256, "Source pinset hash differs")
    pins = load_json(pins_path)
    for name, digest in pins["files"].items():
        path = Path(name)
        require(path.is_file() and sha(path) == digest, f"Pinned file changed: {name}")
    for name, digest in pins["directories"].items():
        path = Path(name)
        entries = {str(item): sha(item) for item in path.rglob("*")
                   if item.is_file() and "__pycache__" not in item.parts
                   and item.suffix not in {".pyc", ".pyo"}}
        require(hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == digest,
                f"Pinned source directory changed: {name}")
    return pins

def load_exact(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"Cannot load exact module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    require(Path(module.__file__).resolve() == path.resolve(), f"Module origin differs: {name}")
    return module

def check_reservation(path: Path, plan: dict, plan_sha256: str) -> dict:
    reservation = load_json(path)
    required = {
        "schema": "current_pair_resource_calibration_parent_reservation_v1",
        "run_id": plan["run_id"], "client_request_id": plan["client_request_id"],
        "plan_sha256": plan_sha256, "authorization": "one_shot_resource_probe",
        "authorized_once": True, "cancel_requested": False,
        "no_concurrent_long_mps_training": True,
        "state_path": plan["authoritative_state_path"],
    }
    require(all(reservation.get(key) == value for key, value in required.items()),
            "Exact parent calibration reservation missing or changed")
    return reservation

def check_live_state(plan: dict, plan_sha256: str) -> str:
    path = Path(plan["authoritative_state_path"])
    raw = path.read_bytes()
    state = json.loads(raw)
    require(state.get("active_long_campaign") is None,
            "Live authority has active_long_campaign")
    active = state.get("active_inference_diagnostic")
    expected = {"run_id": plan["run_id"], "client_request_id": plan["client_request_id"],
                "plan_sha256": plan_sha256, "authorization": "one_shot_resource_probe",
                "cancel_requested": False}
    require(isinstance(active, dict) and all(active.get(k) == v for k, v in expected.items()),
            "Live authority lacks exact active calibration reservation")
    require(state.get("cancel_requested") in (None, False), "Live authority cancellation requested")
    return hashlib.sha256(raw).hexdigest()

def validate_representative_measurements(*, gaps: list[float], after_read_ages: list[float],
                                         sample_count: int, forward_count: int,
                                         guard_count: int, evaluate_passes: int,
                                         active_seconds: float) -> None:
    require(bool(gaps), "Resource sample interarrival gaps are empty")
    require(sample_count >= 20, "Fewer than 20 complete resource samples")
    require(max(gaps) <= 1.0, "Resource sample interarrival gap exceeded 1.0 seconds")
    require(bool(after_read_ages), "After-read age measurements are empty")
    require(max(after_read_ages) <= 1.0, "After-read resource sample freshness exceeded 1.0 seconds")
    require(guard_count == 64 + evaluate_passes * 72,
            "Guard count differs from 64 construction + 9 per decision across 8 decisions")
    require(forward_count >= 240, "Representative MPS forward count is below 240")
    require(30.0 <= active_seconds <= 90.0,
            "Representative active work is outside 30 to 90 seconds")

class SyntheticEnv:
    """Production evaluator adapter; no native game, reset, or actual game episode."""
    def __init__(self, *, seed=None, stage=None, seeds_by_slot=None, difficulty=2, **config):
        self.seed = seed if seed is not None else int(seeds_by_slot[0][0])
        self.stage = stage or f"D{difficulty}"
        self.steps = 0
    def episode_info(self):
        return [{"seed": {"evaluation": True, "actual_seed": self.seed}, "startup_frames": 13}]
    def observations(self):
        import numpy as np
        return {"global_feats": np.zeros((1, 1, 14), dtype=np.float32),
                "entity_feats": np.zeros((1, 80, 16), dtype=np.float32),
                "entity_types": np.zeros((1, 80), dtype=np.int64),
                "entity_mask": np.zeros((1, 80), dtype=np.bool_)}
    def step(self, actions):
        import numpy as np
        self.steps += 1
        done = self.steps >= 8
        info = {"seed": {"actual_seed": self.seed}, "bootstrap": True,
                "score_raw_fixed": 0, "score_delta_sum_raw_fixed": 0,
                "alive_frames": self.steps * 4, "gameplay_frames": self.steps * 4,
                "objective_return": self.steps * 0.04,
                "death_cause": None, "fatal_gameplay_frame": None,
                "death_observed_lethal_contacts": None}
        return {"info": [info], "terminated": np.array([False]),
                "truncated": np.array([done]),
                "observations": None if done else self.observations()}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--pins", type=Path, required=True)
    parser.add_argument("--pins-sha256", required=True)
    parser.add_argument("--reservation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    plan_sha = sha(args.plan)
    require(plan_sha == args.plan_sha256, "Calibration plan hash differs")
    plan = load_json(args.plan)
    require(plan["run_id"] == "current-pair-resource-calibration-luna-20261026-r3"
            and plan["execution_authorized_by_preparation"] is False,
            "Unexpected or preparation-authorized calibration plan")
    verify_pins(args.pins, args.pins_sha256)
    pins_before_import = True
    check_reservation(args.reservation, plan, plan_sha)
    # All pinned sources, runtime files, interpreter, native extension, checkpoints,
    # receipts, and audits pass before importing Torch or any R6 module.
    sys.path.insert(0, str(PREPARE))
    worker = load_exact("worker", PREPARE / "worker.py")
    supervisor = load_exact("_r6_supervisor", PREPARE / "supervisor.py")
    import numpy
    import torch
    origins = worker.verify_module_origins()
    require(Path(worker._PAIRED_EVAL.__file__).resolve() == (PREPARE / "paired_eval.py").resolve(),
            "R6 paired evaluator origin differs")
    require(Path(supervisor.__file__).resolve() == (PREPARE / "supervisor.py").resolve(),
            "R6 supervisor origin differs")
    manifest = worker.verify_inputs()
    for label in worker.CHECKPOINTS:
        model, _ = worker.load_inference_model(label, device="cpu", manifest=manifest)
        require(not model.training and not any(parameter.requires_grad for parameter in model.parameters()),
                f"Strict CPU checkpoint validation failed: {label}")
        del model
    # Rehash immediately before model-to-MPS and forward. No MPS call precedes this gate.
    verify_pins(args.pins, args.pins_sha256)
    pins_before_mps = True
    check_reservation(args.reservation, plan, plan_sha)
    output = args.output
    sampler = worker.ResourceSampler(output / "resources.jsonl")
    sampler_started = time.monotonic()
    sampler.start()
    metrics = {"schema": "current_pair_resource_calibration_probe_result_v2",
               "run_id": plan["run_id"], "plan_sha256": plan_sha,
               "status": "failed", "mps_forward_calls": 0,
               "real_game_episodes": 0, "worker_evaluator": "R6 worker.evaluate",
               "module_origins": origins,
               "pins_checked_before_import": pins_before_import,
               "pins_checked_before_mps": pins_before_mps,
               "live_state_observed_sha256": []}
    def term_to_evidence(signum, frame):
        raise InterruptedError(f"Received signal {signum}; retain partial probe evidence")
    signal.signal(signal.SIGTERM, term_to_evidence)
    cleanup_started = None
    try:
        sampler.wait_first_sample(10.0)
        first_sample_delay = time.monotonic() - sampler_started
        require(first_sample_delay <= 10.0, "First complete resource sample exceeded 10 seconds")
        worker.read_latest_resource_sample(sampler.path, max_age=1.0)
        verify_pins(args.pins, args.pins_sha256)
        check_reservation(args.reservation, plan, plan_sha)
        state_hashes = [check_live_state(plan, plan_sha)]
        metrics["live_state_observed_sha256"] = state_hashes
        model, _ = worker.load_inference_model("best204", device="mps", manifest=manifest)
        rows_path = output / "synthetic-episodes.jsonl"
        guard_costs = []
        after_read_ages = []
        forward_calls = []
        fsync_costs = []
        state_hashes.extend([check_live_state(plan, plan_sha)])
        model.register_forward_hook(lambda *_: forward_calls.append(time.monotonic()))
        deadline = started + 90.0
        def guard():
            state_hashes.append(check_live_state(plan, plan_sha))
            sampler.require_live()
            fresh = worker.read_latest_resource_sample(sampler.path, max_age=1.0)
            after_read_ages.append(fresh["age_seconds"])
            reservation_start = time.perf_counter()
            check_reservation(args.reservation, plan, plan_sha)
            guard_costs.append(time.perf_counter() - reservation_start)
            require(time.monotonic() <= deadline, "90-second probe work limit exceeded")
            return fresh
        with rows_path.open("x", buffering=1) as stream:
            def sink(row):
                stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                stream.flush()
                sync_started = time.perf_counter()
                os.fsync(stream.fileno())
                fsync_costs.append(time.perf_counter() - sync_started)
            from dodge_rl.dev_eval import development_environment_config
            rows = []
            active_started = time.monotonic()
            passes = 0
            while True:
                rows.extend(worker.evaluate(model, checkpoint="best204", mode="argmax", replicate_seed=None,
                                            env_factory=SyntheticEnv,
                                            config_factory=development_environment_config,
                                            expected_control_path=None, check_guard=guard,
                                            episode_sink=sink, fixture=False))
                passes += 1
                elapsed = time.monotonic() - active_started
                require(time.monotonic() <= deadline, "90-second probe work limit exceeded")
                if len(forward_calls) >= 240 and elapsed >= 30.0:
                    break
        sample_lines = [json.loads(line) for line in (output / "resources.jsonl").read_text().splitlines()]
        sample_times = [entry["monotonic"] for entry in sample_lines]
        gaps = [b - a for a, b in zip(sample_times, sample_times[1:])]
        rss_peak = max((entry["rss_bytes"] for entry in sample_lines), default=0)
        mps_peak = max((entry["mps_driver_bytes"] for entry in sample_lines), default=0)
        require(rss_peak <= 6 * 1024**3, "Worker RSS high-water exceeded separate 6 GiB cap")
        require(mps_peak <= 6 * 1024**3, "MPS driver allocation exceeded separate 6 GiB cap")
        validate_representative_measurements(
            gaps=gaps, after_read_ages=after_read_ages, sample_count=len(sample_lines),
            forward_count=len(forward_calls), guard_count=len(guard_costs),
            evaluate_passes=passes, active_seconds=elapsed)
        del model
        cleanup_started = time.monotonic()
        metrics.update({"status": "passed", "synthetic_rows": len(rows),
                        "mps_forward_calls": len(forward_calls),
                        "first_complete_sample_delay_seconds": first_sample_delay,
                        "guard_checks": len(guard_costs),
                        "reservation_read_total_seconds": sum(guard_costs),
                        "reservation_read_max_seconds": max(guard_costs, default=0.0),
                        "jsonl_fsync_count": len(fsync_costs),
                        "jsonl_fsync_total_seconds": sum(fsync_costs),
                        "jsonl_fsync_max_seconds": max(fsync_costs, default=0.0),
                        "jsonl_fsync_seconds_per_row": fsync_costs,
                        "max_after_read_age_seconds": max(after_read_ages, default=0.0),
                        "after_read_age_seconds": after_read_ages,
                        "max_interarrival_gap_seconds": max(gaps, default=0.0),
                        "representative_active_seconds": elapsed,
                        "evaluate_passes": passes,
                        "live_state_observed_sha256": state_hashes,
                        "sample_interarrival_gap_seconds": gaps,
                        "resource_sample_count": len(sample_lines),
                        "mps_sampler_query_success_count": sum(
                            type(entry.get("mps_driver_bytes")) is int for entry in sample_lines),
                        "worker_rss_highwater_bytes": rss_peak,
                        "mps_driver_highwater_bytes": mps_peak,
                        "supervisor_rss_definition": "launcher current RSS sampled separately; not combined with worker high-water RSS",
                        "work_seconds": time.monotonic() - started})
        require(metrics["work_seconds"] <= 90.0, "90-second probe work limit exceeded")
    except BaseException as error:
        metrics["status"] = "failed"
        metrics["error"] = f"{type(error).__name__}: {error}"
        metrics["traceback"] = traceback.format_exc()
        return 1
    finally:
        cleanup_started = cleanup_started or time.monotonic()
        try:
            sampler.close()
        except BaseException as error:
            metrics["sampler_cleanup_error"] = f"{type(error).__name__}: {error}"
            metrics["status"] = "failed"
        metrics["elapsed_outer_seconds"] = time.monotonic() - started
        metrics["cleanup_seconds"] = time.monotonic() - cleanup_started
        if metrics["cleanup_seconds"] > 10.0:
            metrics["status"] = "failed"
            metrics["error"] = "10-second cleanup limit exceeded"
        metrics["raw_exits"] = {"probe": 0 if metrics["status"] == "passed" else 1}
        metrics["pins_checked_before_import_and_mps"] = 3
        metrics["observer_wrapper_error_disposition"] = "not_applicable_no_observer_wrapper"
        metrics["resource_log_sha256"] = sha(output / "resources.jsonl") if (output / "resources.jsonl").exists() else None
        (output / "probe-result.json").write_text(json.dumps(metrics, sort_keys=True, indent=2) + "\n")
        if metrics["elapsed_outer_seconds"] > 120.0:
            metrics["status"] = "failed"
            metrics["error"] = "120-second outer limit exceeded"
            (output / "probe-result.json").write_text(json.dumps(metrics, sort_keys=True, indent=2) + "\n")
    return 0 if metrics["status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
