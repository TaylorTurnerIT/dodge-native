"""One-shot parent-reserved calibration launcher. Never creates a reservation."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PROBE = HERE / "probe.py"
MARKER = HERE / "launch-once.marker"

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def verify(pins_path: Path, expected: str) -> dict:
    if sha(pins_path) != expected:
        raise RuntimeError("Source pinset hash differs")
    pins = json.loads(pins_path.read_text())
    for name, digest in pins["files"].items():
        path = Path(name)
        if not path.is_file() or sha(path) != digest:
            raise RuntimeError(f"Pinned file changed: {name}")
    for name, digest in pins["directories"].items():
        path = Path(name)
        entries = {str(item): sha(item) for item in path.rglob("*")
                   if item.is_file() and "__pycache__" not in item.parts
                   and item.suffix not in {".pyc", ".pyo"}}
        actual = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if actual != digest:
            raise RuntimeError(f"Pinned source directory changed: {name}")
    return pins

def check_live_state(plan: dict, plan_sha: str) -> str:
    path = Path(plan["authoritative_state_path"])
    raw = path.read_bytes()
    state = json.loads(raw)
    if state.get("active_long_campaign") is not None:
        raise RuntimeError("Live authority has active_long_campaign")
    active = state.get("active_inference_diagnostic")
    expected = {"run_id": plan["run_id"], "client_request_id": plan["client_request_id"],
                "plan_sha256": plan_sha, "authorization": "one_shot_resource_probe",
                "cancel_requested": False}
    if not isinstance(active, dict) or any(active.get(k) != v for k, v in expected.items()):
        raise RuntimeError("Live authority lacks exact active calibration reservation")
    if state.get("cancel_requested") not in (None, False):
        raise RuntimeError("Live authority cancellation requested")
    return hashlib.sha256(raw).hexdigest()

def claim_once(plan: dict, plan_sha: str, state_sha256: str) -> Path:
    with MARKER.open("x") as stream:
        stream.write(json.dumps({"run_id": plan["run_id"], "plan_sha256": plan_sha,
                                "started_monotonic": time.monotonic(),
                                "state_sha256": state_sha256}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return MARKER

def group_is_absent(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    return False

def ensure_group_absent(pgid: int) -> bool:
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        if group_is_absent(pgid):
            return True
        time.sleep(0.05)
    if not group_is_absent(pgid):
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return True
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if group_is_absent(pgid):
            return True
        time.sleep(0.05)
    if not group_is_absent(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return True
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if group_is_absent(pgid):
            return True
        time.sleep(0.05)
    return group_is_absent(pgid)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=HERE / "calibration-plan.json")
    parser.add_argument("--pins", type=Path, default=HERE / "source-pins.json")
    parser.add_argument("--reservation", type=Path, default=HERE / "parent-reservation.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    outer_started = time.monotonic()
    plan_sha = sha(args.plan)
    plan = json.loads(args.plan.read_text())
    pins_sha = sha(args.pins)
    if pins_sha != plan["source_pins_sha256"]:
        raise RuntimeError("Plan source pinset anchor differs")
    verify(args.pins, pins_sha)
    pins_before_launch = True
    if not args.reservation.is_file():
        raise RuntimeError("Parent-owned one-shot reservation is missing")
    reservation = json.loads(args.reservation.read_text())
    expected = {"schema": "current_pair_resource_calibration_parent_reservation_v1",
                "run_id": plan["run_id"], "client_request_id": plan["client_request_id"],
                "plan_sha256": plan_sha, "authorization": "one_shot_resource_probe",
                "authorized_once": True, "cancel_requested": False,
                "no_concurrent_long_mps_training": True,
                "state_path": plan["authoritative_state_path"]}
    if any(reservation.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Exact parent calibration reservation missing or changed")
    args.output.mkdir(parents=True, exist_ok=False)
    preflight_spec = importlib.util.spec_from_file_location("_r6_calibration_cpu_preflight",
                                                            HERE / "cpu_preflight.py")
    if preflight_spec is None or preflight_spec.loader is None:
        raise RuntimeError("Cannot load pinned CPU preflight helper")
    preflight = importlib.util.module_from_spec(preflight_spec)
    sys.modules[preflight_spec.name] = preflight
    preflight_spec.loader.exec_module(preflight)
    cpu_result = preflight.run(args.output)
    if cpu_result.get("status") != "passed" or cpu_result.get("mps_operations") != 0:
        raise RuntimeError("CPU preflight failed before calibration hardware launch")
    verify(args.pins, pins_sha)
    reservation = json.loads(args.reservation.read_text())
    if any(reservation.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Parent calibration reservation changed after CPU preflight")
    target = Path(plan["interpreter"]["resolved_target"])
    lexical = Path(plan["interpreter"]["lexical_path"])
    if not lexical.is_file() or lexical.resolve() != target.resolve():
        raise RuntimeError("Pinned lexical interpreter target differs")
    if sha(target) != plan["interpreter"]["sha256"]:
        raise RuntimeError("Pinned interpreter changed")
    observed_state_sha256 = check_live_state(plan, plan_sha)
    marker = MARKER
    marker = claim_once(plan, plan_sha, observed_state_sha256)
    started = time.monotonic()
    probe_hash_before = sha(PROBE)
    command = [str(target), "-I", "-B", str(PROBE), "--plan", str(args.plan),
               "--plan-sha256", plan_sha, "--pins", str(args.pins),
               "--pins-sha256", pins_sha, "--reservation", str(args.reservation),
               "--output", str(args.output)]
    process = subprocess.Popen(command, cwd=ROOT, start_new_session=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    rss_peaks = {"launcher_current_bytes": 0, "worker_current_bytes": 0,
                 "aggregate_current_bytes": 0}
    monitor_error = []
    def monitor_rss():
        try:
            while process.poll() is None:
                values = {}
                for key, pid in (("launcher_current_bytes", os.getpid()),
                                 ("worker_current_bytes", process.pid)):
                    if process.poll() is not None:
                        return
                    measured = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)],
                                              check=False, capture_output=True, text=True,
                                              timeout=0.5)
                    if measured.returncode and key == "worker_current_bytes" and process.poll() is not None:
                        return
                    if measured.returncode:
                        raise RuntimeError(f"RSS read failed for owned PID {pid}")
                    value = int(measured.stdout.strip()) * 1024
                    if value <= 0:
                        raise RuntimeError(f"Current RSS measurement unavailable: {key}")
                    values[key] = value
                values["aggregate_current_bytes"] = (values["launcher_current_bytes"] +
                                                       values["worker_current_bytes"])
                for key, value in values.items():
                    rss_peaks[key] = max(rss_peaks[key], value)
                if values["aggregate_current_bytes"] > 6 * 1024**3:
                    raise RuntimeError("Aggregate owned current RSS exceeded separate 6 GiB cap")
                time.sleep(0.25)
        except BaseException as error:
            monitor_error.append(f"{type(error).__name__}: {error}")
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    monitor = threading.Thread(target=monitor_rss, name="calibration-rss-monitor", daemon=True)
    monitor.start()
    child_timeout = max(1.0, 120.0 - (time.monotonic() - outer_started) - 10.0)
    try:
        stdout, stderr = process.communicate(timeout=child_timeout)
    except subprocess.TimeoutExpired:
        identity = subprocess.run(["ps", "-o", "lstart=", "-p", str(process.pid)],
                                  check=False, capture_output=True, text=True, timeout=1.0).stdout.strip()
        if not group_is_absent(process.pid):
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            stdout, stderr = process.communicate(timeout=5.0)
        except subprocess.TimeoutExpired:
            if not group_is_absent(process.pid):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            stdout, stderr = process.communicate()
        absent = ensure_group_absent(process.pid)
        (args.output / "probe.stdout.log").write_text(stdout or "")
        (args.output / "probe.stderr.log").write_text(stderr or "")
        (args.output / "launcher-timeout-evidence.json").write_text(json.dumps({
            "status": "failed_timeout", "term_sent": True,
            "owned_pid": process.pid, "owned_pgid": process.pid,
            "owned_process_start_identity": identity,
            "process_group_absent": absent,
            "cleanup_seconds_max": 10}, sort_keys=True, indent=2) + "\n")
        raise RuntimeError("Calibration probe exceeded 120-second outer bound")
    monitor.join(timeout=1.0)
    if monitor.is_alive():
        raise RuntimeError("RSS monitor did not stop")
    if monitor_error:
        raise RuntimeError(f"RSS monitor failed closed: {monitor_error[0]}")
    group_absent = ensure_group_absent(process.pid)
    if not group_absent:
        raise RuntimeError("Owned calibration process group remains after child reap")
    verify(args.pins, pins_sha)
    outer_seconds = time.monotonic() - outer_started
    if outer_seconds > 120.0:
        raise RuntimeError("Calibration launcher exceeded 120-second outer bound")
    result = {"schema": "current_pair_resource_calibration_launcher_result_v2",
              "run_id": plan["run_id"], "client_request_id": plan["client_request_id"],
              "plan_sha256": plan_sha, "raw_exit": process.returncode,
              "outer_seconds": outer_seconds,
              "probe_sha256_before": probe_hash_before, "probe_sha256_after": sha(PROBE),
              "rss_current_peaks_bytes": rss_peaks,
              "raw_exits": {"outer": process.returncode, "worker": process.returncode},
              "owned_processes_and_groups_absent": group_absent,
              "pins_checked_before_and_after": 2,
              "pre_spawn_state_sha256": observed_state_sha256,
              "observer_wrapper_error_disposition": "not_applicable_no_observer_wrapper",
              "launch_once_marker": str(marker)}
    (args.output / "launcher-result.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    (args.output / "probe.stdout.log").write_text(stdout)
    (args.output / "probe.stderr.log").write_text(stderr)
    return process.returncode

if __name__ == "__main__":
    raise SystemExit(main())
