"""Exclusive, single-launch wrapper for the bounded calibration probe."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
STATE = ROOT / "learning/runs/v2-orchestration/state.json"
PYTHON = ROOT / "python/.venv/bin/python"
RUN_ID = "paired-current-checkpoints-resource-calibration-20261026-r1"
REQUEST_ID = "dodge-v2-current-pair-calibration-and-prepare-luna-20261026-r5"


def require_reservation() -> dict:
    state = json.loads(STATE.read_text())
    reservation = state.get("active_inference_diagnostic")
    expected = {"kind": "paired_resource_calibration", "run_id": RUN_ID,
                "client_request_id": REQUEST_ID,
                "owned": "learning/runs/v2/current-pair-resource-calibration-luna-20261026-r1",
                "authorization": "bounded_inference_resource_validation_no_game_episodes",
                "outer_limit_seconds": 120, "work_limit_seconds": 90,
                "aggregate_RSS_limit_bytes": 6442450944,
                "MPS_driver_limit_bytes": 6442450944, "cancel_requested": False}
    for key, value in expected.items():
        if reservation is None or reservation.get(key) != value:
            raise RuntimeError(f"Active diagnostic reservation mismatch: {key}")
    if state.get("active_long_campaign") is not None:
        raise RuntimeError("active_long_campaign is not null")
    return reservation


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pinned_hashes() -> dict:
    return {"probe_sha256": sha(HERE / "probe.py"),
            "launcher_sha256": sha(HERE / "launch_once.py"),
            "r4_worker_sha256": sha(ROOT / "learning/runs/v2/latest-best-paired-eval-prepare-haiku-20261026-r4/worker.py"),
            "r4_supervisor_sha256": sha(ROOT / "learning/runs/v2/latest-best-paired-eval-prepare-haiku-20261026-r4/supervisor.py"),
            "checkpoint_sha256": sha(ROOT / "learning/runs/v2/D2-best180-branch-luna-20261026-r1/checkpoint-000204-candidate.pt"),
            "interpreter_sha256": sha(PYTHON.resolve())}


def main() -> int:
    reservation = require_reservation()
    hashes_before = pinned_hashes()
    cache = HERE / "python-cache"
    cache.mkdir()
    if any(cache.iterdir()):
        raise RuntimeError("Caller-owned Python cache is not empty")
    marker = HERE / "launch-marker.json"
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"run_id": RUN_ID, "client_request_id": REQUEST_ID,
                   "created_monotonic": time.monotonic(), "pid": os.getpid()}, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    stdout_path = HERE / "probe.stdout.log"
    stderr_path = HERE / "probe.stderr.log"
    env = dict(os.environ)
    env["PYTHONPYCACHEPREFIX"] = str(cache)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [str(PYTHON), "-B", str(HERE / "probe.py")]
    started = time.monotonic()
    with stdout_path.open("x") as stdout, stderr_path.open("x") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                                   start_new_session=True)
        deadline = started + 105.0
        timed_out = False
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        if process.poll() is None:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        exit_code = process.wait()
    elapsed = time.monotonic() - started
    post = require_reservation()
    hashes_after = pinned_hashes()
    result = {"schema": "resource_calibration_single_launch_v1", "run_id": RUN_ID,
              "client_request_id": REQUEST_ID, "command": command, "cwd": str(ROOT),
              "pid": process.pid, "raw_exit_code": exit_code, "timed_out": timed_out,
              "observed_outer_seconds": elapsed, "within_120_seconds": elapsed <= 120.0,
              "work_seconds": json.loads((HERE / "probe-result.json").read_text()).get("time", {}).get("work_seconds")
              if (HERE / "probe-result.json").is_file() else None,
              "work_limit_seconds": 90.0, "reservation_verified_before_and_after": True,
              "reservation": reservation, "reservation_after": post,
              "hashes_before": hashes_before, "hashes_after": hashes_after,
              "hashes_unchanged": hashes_before == hashes_after,
              "probe_status": json.loads((HERE / "probe-result.json").read_text()).get("status")
              if (HERE / "probe-result.json").is_file() else "missing"}
    (HERE / "launch-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if exit_code == 0 and not timed_out and elapsed <= 120.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
