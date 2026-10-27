"""Single bounded MPS resource-sampler calibration; synthetic inputs only."""
from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
R4 = ROOT / "learning/runs/v2/latest-best-paired-eval-prepare-haiku-20261026-r4"
R5 = ROOT / "learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r5"
sys.path.insert(0, str(R4))
from worker import ResourceSampler  # Frozen R4 implementation.
from supervisor import latest_resource_sample, read_resource_log  # Frozen R4 reader.

sys.path.insert(0, str(R5))
from paired_eval import UniformStream, sample_logits_cpu
spec = importlib.util.spec_from_file_location("worker_r5_calibration", R5 / "worker.py")
worker_r5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker_r5)

BEST = ROOT / "learning/runs/v2/D2-best180-branch-luna-20261026-r1/checkpoint-000204-candidate.pt"
BEST_SHA = "f1300e4e86ec89ed9cfba446c8e7f66cf29caad6a1130864edd4d6ee7859d442"
RUNTIME = ROOT / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
RSS_LIMIT = MPS_LIMIT = 6 * 1024**3
STATE_PATH = ROOT / "learning/runs/v2-orchestration/state.json"
RUN_ID = "paired-current-checkpoints-resource-calibration-20261026-r1"
REQUEST_ID = "dodge-v2-current-pair-calibration-and-prepare-luna-20261026-r5"


def verify_reservation() -> None:
    state = json.loads(STATE_PATH.read_text())
    lease = state.get("active_inference_diagnostic")
    if lease is None or lease.get("kind") != "paired_resource_calibration" \
            or lease.get("run_id") != RUN_ID or lease.get("client_request_id") != REQUEST_ID \
            or lease.get("cancel_requested") is not False:
        raise RuntimeError("Exact live calibration reservation missing or cancelled")
    if state.get("active_long_campaign") is not None:
        raise RuntimeError("active_long_campaign is not null before MPS use")


def sha(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cpu_row_contention(stop: threading.Event, errors: list[str], path: Path) -> None:
    import torch
    logits = torch.zeros(9, dtype=torch.float32)
    rows = 0
    try:
        with path.open("x", buffering=1) as stream:
            while not stop.is_set():
                for seed in range(3489660928, 3489660992):
                    uniform = UniformStream(64001, seed).next()
                    action = sample_logits_cpu(logits, uniform)
                    stream.write(json.dumps({"seed": seed, "action": action, "row": rows},
                                            separators=(",", ":")) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                    rows += 1
                    if stop.is_set():
                        break
    except Exception as error:
        errors.append(f"{type(error).__name__}: {error}")


def main() -> int:
    import torch
    from dodge_rl import checkpoints
    from dodge_rl.models.teacher import OmniscientEntityTeacher

    started = time.monotonic()
    resources = HERE / "resources.jsonl"
    observations_path = HERE / "read-observations.jsonl"
    sampler = ResourceSampler(resources, period=0.25)
    sampler.start()
    sampler.wait_first_sample(timeout=10.0)
    initial = latest_resource_sample(resources)
    if initial is None:
        raise RuntimeError("No complete resource sample; MPS remains prohibited")

    if sha(BEST) != BEST_SHA:
        raise RuntimeError("Best204 checkpoint pin changed before CPU load")
    state = checkpoints.load_checkpoint(BEST, expected_sha256=BEST_SHA)
    checkpoints.require_complete_update(state)
    receipt, _audit = worker_r5._receipt_anchor("best204", ROOT)
    worker_r5.validate_checkpoint_receipt_binding(state, receipt, "best204", checkpoints.identity_hash)
    with torch.random.fork_rng(devices=[]):
        model = OmniscientEntityTeacher()
    model.load_state_dict(state["model"], strict=True)
    del state
    if sampler.error is not None or not sampler.thread.is_alive():
        raise RuntimeError(f"Sampler failed before MPS: {sampler.error}")
    verify_reservation()
    model.requires_grad_(False)
    model.eval()
    model.to(torch.device("mps"))

    stop = threading.Event()
    contention_errors: list[str] = []
    contention = threading.Thread(target=cpu_row_contention,
                                  args=(stop, contention_errors, HERE / "cpu-json-fsync.jsonl"),
                                  name="owned-cpu-json-fsync-contention", daemon=True)
    contention.start()
    batch_results = []
    observations = []
    work_deadline = time.monotonic() + 34.0
    with observations_path.open("x", buffering=1) as observation_log:
        with torch.inference_mode():
            for batch_size in (1, 8, 32, 64):
                sampler.require_live()
                current = latest_resource_sample(resources)
                if current is None:
                    raise RuntimeError("Resource sample unknown before MPS inference")
                if current["rss_bytes"] > RSS_LIMIT or current["mps_driver_bytes"] > MPS_LIMIT:
                    raise RuntimeError("Resource cap exceeded before MPS inference")
                xg = torch.zeros((batch_size, 1, 14), device="mps")
                xe = torch.zeros((batch_size, 80, 16), device="mps")
                xt = torch.zeros((batch_size, 80), dtype=torch.int64, device="mps")
                xm = torch.zeros((batch_size, 80), dtype=torch.bool, device="mps")
                calls = 0
                batch_deadline = min(work_deadline, time.monotonic() + 7.0)
                while time.monotonic() < batch_deadline:
                    sampler.require_live()
                    sample = latest_resource_sample(resources)
                    if sample is None:
                        raise RuntimeError("Resource sample unknown during MPS inference")
                    if sample["rss_bytes"] > RSS_LIMIT or sample["mps_driver_bytes"] > MPS_LIMIT:
                        raise RuntimeError("Resource cap exceeded during MPS inference")
                    output = model(xg, xe, xt, xm)
                    output.logits[0].to(device="cpu")
                    calls += 1
                    samples, _partial = read_resource_log(resources)
                    read_clock = time.monotonic()
                    age = read_clock - samples[-1]["monotonic"] if samples else None
                    observation = {"batch_size": batch_size, "read_monotonic": read_clock,
                                   "sample_monotonic": None if not samples else samples[-1]["monotonic"],
                                   "freshness_age_seconds": age,
                                   "rss_bytes": None if not samples else samples[-1]["rss_bytes"],
                                   "mps_driver_bytes": None if not samples else samples[-1]["mps_driver_bytes"]}
                    observations.append(observation)
                    observation_log.write(json.dumps(observation, sort_keys=True) + "\n")
                    observation_log.flush()
                batch_results.append({"batch_size": batch_size, "inference_calls": calls})
                del xg, xe, xt, xm
                if time.monotonic() >= work_deadline:
                    break

    stop.set()
    contention.join(timeout=5.0)
    if contention.is_alive():
        raise RuntimeError("CPU contention thread did not stop")
    sampler.close()
    samples, partial_tail_bytes = read_resource_log(resources)
    gaps = [float(b["monotonic"] - a["monotonic"]) for a, b in zip(samples, samples[1:])]
    ages = [float(item["freshness_age_seconds"]) for item in observations
            if item["freshness_age_seconds"] is not None]
    peak_rss = max((s["rss_bytes"] for s in samples), default=None)
    peak_mps = max((s["mps_driver_bytes"] for s in samples), default=None)
    result = {
        "schema": "current_pair_resource_calibration_v1", "status": "measured",
        "scope": "synthetic teacher tensor batches and CPU row/log contention; no game environment or episodes",
        "source": {"r4_worker_sha256": sha(R4 / "worker.py"),
                   "r4_supervisor_sha256": sha(R4 / "supervisor.py"),
                   "probe_sha256": sha(Path(__file__)), "checkpoint_sha256_pre": BEST_SHA,
                   "checkpoint_sha256_post": sha(BEST),
                   "python_executable": sys.executable,
                   "python_version": sys.version,
                   "runtime_teacher_sha256": sha(RUNTIME / "dodge_rl/models/teacher.py"),
                   "checkpoint_loader_sha256": sha(RUNTIME / "dodge_rl/checkpoints.py")},
        "time": {"work_seconds": time.monotonic() - started, "first_complete_sample_delay_seconds":
                 samples[0]["monotonic"] - started if samples else None},
        "sampler": {"period_seconds": 0.25, "freshness_gate_seconds": 1.0,
                    "sample_count": len(samples), "partial_tail_bytes": partial_tail_bytes,
                    "max_interarrival_gap_seconds": max(gaps, default=None),
                    "interarrival_gaps_seconds": gaps,
                    "max_after_read_freshness_age_seconds": max(ages, default=None),
                    "after_read_freshness_ages_seconds": ages,
                    "liveness_error": sampler.error, "thread_alive_after_close": sampler.thread.is_alive()},
        "caps": {"aggregate_rss_limit_bytes": RSS_LIMIT, "MPS_driver_limit_bytes": MPS_LIMIT,
                 "peak_rss_bytes": peak_rss, "peak_mps_driver_bytes": peak_mps,
                 "within_separate_caps": peak_rss is not None and peak_mps is not None
                 and peak_rss <= RSS_LIMIT and peak_mps <= MPS_LIMIT},
        "inference": {"device": "mps", "batch_sizes": batch_results, "inference_mode": True,
                      "model_eval": not model.training,
                      "requires_grad_false": not any(p.requires_grad for p in model.parameters())},
        "contention": {"cpu_sampler_rows_written": sum(1 for _ in (HERE / "cpu-json-fsync.jsonl").open()),
                       "json_flush_fsync_each_row": True, "errors": contention_errors},
        "cleanup": {"sampler_thread_reaped": not sampler.thread.is_alive(),
                    "contention_thread_reaped": not contention.is_alive(),
                    "owned_threads": [thread.name for thread in threading.enumerate()
                                      if thread.name.startswith("owned-")]},
    }
    result["status"] = "passed" if (result["caps"]["within_separate_caps"]
        and result["sampler"]["sample_count"] >= 2
        and result["sampler"]["max_interarrival_gap_seconds"] <= 1.0
        and result["sampler"]["max_after_read_freshness_age_seconds"] <= 1.0
        and result["sampler"]["first_complete_sample_delay_seconds"] <= 10.0
        and not result["sampler"]["liveness_error"]
        and not result["cleanup"]["owned_threads"] and not contention_errors
        and result["source"]["checkpoint_sha256_post"] == BEST_SHA
        and result["time"]["work_seconds"] <= 90.0) else "failed"
    (HERE / "probe-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "work_seconds": result["time"]["work_seconds"],
                      "max_gap": result["sampler"]["max_interarrival_gap_seconds"],
                      "max_age": result["sampler"]["max_after_read_freshness_age_seconds"],
                      "peak_rss": peak_rss, "peak_mps": peak_mps}, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BaseException as error:
        failure = {"schema": "current_pair_resource_calibration_v1", "status": "failed",
                   "scope": "single no-retry hardware probe; no game environment or episodes",
                   "error": f"{type(error).__name__}: {error}",
                   "owned_threads_at_failure": [thread.name for thread in threading.enumerate()
                                                 if thread.name.startswith("owned-")],
                   "checkpoint_sha256_post": sha(BEST) if BEST.is_file() else None,
                   "probe_sha256": sha(Path(__file__))}
        (HERE / "probe-result.json").write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        raise
