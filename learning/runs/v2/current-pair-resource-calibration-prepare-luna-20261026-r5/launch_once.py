"""One-shot parent-reserved calibration launcher. Never creates a reservation."""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
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

def check_live_state(plan: dict, plan_sha: str, reservation: dict | None = None) -> str:
    path = Path(plan["authoritative_state_path"])
    raw = path.read_bytes()
    state = json.loads(raw)
    if state.get("active_long_campaign") is not None:
        raise RuntimeError("Live authority has active_long_campaign")
    active = state.get("active_inference_diagnostic")
    expected = plan["authoritative_state_fields"]["active_inference_diagnostic"] | {"plan_sha256": plan_sha}
    if reservation is not None:
        expected |= {"review_status": "passed", "campaign_launch_authorized": True,
                     "review_receipt_sha256": reservation["review_receipt_sha256"],
                     "review_source_manifest_sha256": reservation["review_source_manifest_sha256"]}
    if not isinstance(active, dict) or any(active.get(k) != v for k, v in expected.items()):
        raise RuntimeError("Live authority lacks exact active calibration reservation")
    if state.get("cancel_requested") not in (None, False):
        raise RuntimeError("Live authority cancellation requested")
    return hashlib.sha256(raw).hexdigest()

def verify_lexical_interpreter(plan: dict, cache_prefix: Path) -> dict:
    lexical = Path(plan["interpreter"]["lexical_path"])
    target = Path(plan["interpreter"]["resolved_target"])
    if not lexical.is_file() or lexical.resolve() != target.resolve():
        raise RuntimeError("Pinned lexical interpreter target differs")
    if sha(target) != plan["interpreter"]["sha256"]:
        raise RuntimeError("Pinned interpreter changed")
    script = "import importlib.util,json,pathlib,sys; print(json.dumps({'prefix':sys.prefix,'torch':importlib.util.find_spec('torch').origin,'numpy':importlib.util.find_spec('numpy').origin}))"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPYCACHEPREFIX"] = str(cache_prefix)
    result = subprocess.run([str(lexical), "-B", "-c", script], cwd=ROOT, env=env,
                            check=True, capture_output=True, text=True, timeout=10.0)
    found = json.loads(result.stdout)
    expected_prefix = str(lexical.parent.parent.resolve())
    if Path(found["prefix"]).resolve() != Path(expected_prefix):
        raise RuntimeError("Lexical interpreter prefix differs from pinned virtual environment")
    site = Path(found["prefix"]) / "lib/python3.12/site-packages"
    for module in ("torch", "numpy"):
        origin = Path(found[module]).resolve()
        if not origin.is_relative_to(site.resolve()):
            raise RuntimeError(f"{module} import origin is outside pinned virtual environment")
    return {"lexical_path": str(lexical), "resolved_target": str(target.resolve()),
            "resolved_sha256": sha(target), "prefix": found["prefix"],
            "torch_origin": found["torch"], "numpy_origin": found["numpy"]}

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
    # Never signal a surviving numeric group after its leader identity is gone.
    return group_is_absent(pgid)

def capture_process_identity(process: subprocess.Popen, deadline: float) -> tuple[str, int] | None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    try:
        result = subprocess.run(["ps", "-o", "lstart=,pgid=", "-p", str(process.pid)],
                                check=False, capture_output=True, text=True,
                                timeout=min(1.0, remaining))
        fields = result.stdout.strip().rsplit(None, 1)
        if result.returncode != 0 or len(fields) != 2:
            return None
        pgid = int(fields[-1])
        if not fields[0] or pgid <= 0:
            return None
        return fields[0], pgid
    except (OSError, ValueError, subprocess.SubprocessError):
        return None

def cleanup_spawned_child(process: subprocess.Popen, output: Path, *, reason: str,
                          outer_deadline: float, identity: tuple[str, int] | None = None,
                          identity_reader=capture_process_identity) -> dict:
    """Bound all cleanup. Group signals require fresh birth and exact PGID proof."""
    cleanup_started = time.monotonic()
    cleanup_deadline = min(outer_deadline, cleanup_started + 10.0)
    group_candidate = identity is not None and bool(identity[0]) and identity[1] == process.pid
    group_revalidated = False
    group_signal_used = False
    term_sent = False
    kill_sent = False
    stdout = stderr = ""
    def remaining() -> float:
        return max(0.0, cleanup_deadline - time.monotonic())
    def group_still_proven() -> bool:
        nonlocal group_revalidated
        if not group_candidate or remaining() <= 0:
            return False
        try:
            current = identity_reader(process, cleanup_deadline)
        except BaseException:
            return False
        group_revalidated = current == identity and current[1] == process.pid
        return group_revalidated
    def signal_owned(sig: int) -> bool:
        nonlocal term_sent, kill_sent, group_signal_used
        if process.poll() is not None:
            return False
        try:
            if group_still_proven():
                os.killpg(process.pid, sig)
                group_signal_used = True
            elif sig == signal.SIGTERM:
                process.terminate()
            else:
                process.kill()
            if sig == signal.SIGTERM: term_sent = True
            else: kill_sent = True
            return True
        except (ProcessLookupError, PermissionError, OSError):
            return False
    signal_owned(signal.SIGTERM)
    try:
        if remaining() > 0:
            stdout, stderr = process.communicate(timeout=min(1.0, remaining()))
    except subprocess.TimeoutExpired as error:
        stdout, stderr = error.output or "", error.stderr or ""
    if process.poll() is None:
        signal_owned(signal.SIGKILL)
        try:
            if remaining() > 0:
                out, err = process.communicate(timeout=remaining())
                stdout, stderr = out or stdout, err or stderr
        except subprocess.TimeoutExpired as error:
            stdout, stderr = error.output or stdout, error.stderr or stderr
        except (OSError, ValueError):
            pass
    child_reaped = process.poll() is not None
    group_absent = None
    if group_candidate and remaining() > 0 and group_still_proven():
        group_absent = ensure_group_absent(process.pid)
    complete = child_reaped and group_absent is True
    cleanup = {"schema": "current_pair_resource_calibration_cleanup_v1",
               "reason": reason, "direct_child_reaped": child_reaped,
               "group_identity_candidate": group_candidate,
               "group_identity_revalidated": group_revalidated,
               "group_signal_used": group_signal_used,
               "process_group_absent": group_absent,
               "absence_status": "absent" if complete else "unknown",
               "term_sent": term_sent, "kill_sent": kill_sent,
               "cleanup_seconds": time.monotonic() - cleanup_started,
               "cleanup_seconds_max": 10.0, "outer_deadline_monotonic": outer_deadline}
    (output / "probe.stdout.log").write_text(stdout or "")
    (output / "probe.stderr.log").write_text(stderr or "")
    result = {"schema": "current_pair_resource_calibration_launcher_result_v4",
              "status": "failed_postspawn", "error": reason,
              "raw_exit": process.returncode, "cleanup": cleanup}
    (output / "launcher-cleanup-evidence.json").write_text(json.dumps(cleanup, sort_keys=True, indent=2) + "\n")
    (output / "launcher-result.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result

def verify_spawn_identity_or_cleanup(process: subprocess.Popen, output: Path, *,
                                    outer_deadline: float, identity_reader=capture_process_identity) -> tuple[str, int]:
    identity = identity_reader(process, outer_deadline)
    if identity is None:
        cleanup_spawned_child(process, output, reason="spawn_identity_capture_failed",
                              outer_deadline=outer_deadline, identity_reader=identity_reader)
        raise RuntimeError("Cannot capture spawned process birth identity")
    if identity[1] != process.pid:
        cleanup_spawned_child(process, output, reason="spawn_pgid_mismatch",
                              outer_deadline=outer_deadline, identity=identity,
                              identity_reader=identity_reader)
        raise RuntimeError("Spawned process is not leader of its owned process group")
    return identity

def spawn_child_and_capture_identity(command: list[str], *, cwd: Path, env: dict,
                                     output: Path, outer_deadline: float,
                                     identity_reader=capture_process_identity, spawn_observer=None):
    process = subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if spawn_observer is not None:
        spawn_observer(process)
    identity = verify_spawn_identity_or_cleanup(
        process, output, outer_deadline=outer_deadline, identity_reader=identity_reader)
    return process, identity

def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=HERE / "calibration-plan.json")
    parser.add_argument("--pins", type=Path, default=HERE / "source-pins.json")
    parser.add_argument("--reservation", type=Path, default=HERE / "parent-reservation.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() != (HERE / "probe-output").resolve():
        raise RuntimeError("Calibration output path differs from fixed R5-owned location")
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
    expected = {"schema": "current_pair_resource_calibration_parent_reservation_v2",
                "kind": "resource_calibration", "run_id": plan["run_id"],
                "client_request_id": plan["client_request_id"], "plan_sha256": plan_sha,
                "source_pins_sha256": pins_sha, "owner": "parent_registered_calibration_r5",
                "identity": "calibration-r5-ef296efd-45e4-48b1-b2a1-8ec78bb35c31",
                "authorization": "one_shot_resource_probe", "authorized_once": True,
                "cancel_requested": False, "no_concurrent_long_mps_training": True,
                "review_status": "passed", "state_path": plan["authoritative_state_path"]}
    if any(reservation.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Exact parent calibration reservation missing or changed")
    for field in ("review_receipt_sha256", "review_source_manifest_sha256"):
        value = reservation.get(field)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise RuntimeError(f"Parent calibration reservation lacks exact {field}")
    args.output.mkdir(parents=True, exist_ok=False)
    bytecode_prefix = args.output / "bytecode-cache-empty"
    bytecode_prefix.mkdir()
    if any(bytecode_prefix.iterdir()):
        raise RuntimeError("Owned bytecode prefix is not empty before startup")
    interpreter_evidence = verify_lexical_interpreter(plan, bytecode_prefix)
    lexical = Path(plan["interpreter"]["lexical_path"])
    child_env = os.environ.copy()
    child_env.pop("PYTHONPATH", None)
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    child_env["PYTHONPYCACHEPREFIX"] = str(bytecode_prefix)
    preflight_result = subprocess.run([str(lexical), "-B", str(HERE / "cpu_preflight.py"),
                                       "--output", str(args.output)], cwd=ROOT,
                                      env=child_env, check=False, capture_output=True,
                                      text=True, timeout=30.0)
    (args.output / "cpu-preflight.stdout.log").write_text(preflight_result.stdout)
    (args.output / "cpu-preflight.stderr.log").write_text(preflight_result.stderr)
    cpu_result = json.loads((args.output / "cpu-preflight-validation/cpu-preflight.json").read_text())
    if preflight_result.returncode != 0 or cpu_result.get("status") != "passed" or cpu_result.get("mps_operations") != 0:
        raise RuntimeError("Lexical CPU preflight failed before calibration hardware launch")
    verify(args.pins, pins_sha)
    reservation = json.loads(args.reservation.read_text())
    if any(reservation.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Parent calibration reservation changed after CPU preflight")
    for field in ("review_receipt_sha256", "review_source_manifest_sha256"):
        value = reservation.get(field)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise RuntimeError(f"Parent calibration reservation lacks exact {field}")
    interpreter_evidence = verify_lexical_interpreter(plan, bytecode_prefix)
    observed_state_sha256 = check_live_state(plan, plan_sha, reservation)
    marker = MARKER
    marker = claim_once(plan, plan_sha, observed_state_sha256)
    started = time.monotonic()
    probe_hash_before = sha(PROBE)
    command = [str(lexical), "-B", str(PROBE), "--plan", str(args.plan),
               "--plan-sha256", plan_sha, "--pins", str(args.pins),
               "--pins-sha256", pins_sha, "--reservation", str(args.reservation),
               "--output", str(args.output)]
    child_env = os.environ.copy()
    child_env.pop("PYTHONPATH", None)
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    child_env["PYTHONPYCACHEPREFIX"] = str(bytecode_prefix)
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
                    if key == "worker_current_bytes" and process.poll() is not None:
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
                if owned_identity_matches():
                    os.killpg(process_pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    outer_deadline = outer_started + 120.0
    process, (process_start_identity, process_pgid) = spawn_child_and_capture_identity(
        command, cwd=ROOT, env=child_env, output=args.output, outer_deadline=outer_deadline)
    def owned_identity_matches():
        if process.poll() is not None:
            return False
        current = subprocess.run(["ps", "-o", "lstart=,pgid=", "-p", str(process.pid)],
                                 check=False, capture_output=True, text=True, timeout=1.0)
        fields = current.stdout.strip().rsplit(None, 1)
        return current.returncode == 0 and len(fields) == 2 and fields[0] == process_start_identity and int(fields[-1]) == process_pgid
    monitor = threading.Thread(target=monitor_rss, name="calibration-rss-monitor", daemon=True)
    try:
        monitor.start()
    except BaseException as error:
        cleanup_spawned_child(process, args.output,
                              reason=f"rss_monitor_start_failed:{type(error).__name__}",
                              outer_deadline=outer_deadline,
                              identity=(process_start_identity, process_pgid))
        raise
    child_timeout = max(0.001, min(outer_deadline - 10.0, outer_deadline) - time.monotonic())
    try:
        stdout, stderr = process.communicate(timeout=child_timeout)
    except subprocess.TimeoutExpired:
        cleanup_spawned_child(process, args.output, reason="probe_work_deadline_exceeded",
                              outer_deadline=outer_deadline,
                              identity=(process_start_identity, process_pgid))
        raise RuntimeError("Calibration probe exceeded 110-second work bound")
    except BaseException as error:
        cleanup_spawned_child(process, args.output,
                              reason=f"child_communication_failed:{type(error).__name__}",
                              outer_deadline=outer_deadline,
                              identity=(process_start_identity, process_pgid))
        raise
    (args.output / "probe.stdout.log").write_text(stdout or "")
    (args.output / "probe.stderr.log").write_text(stderr or "")
    (args.output / "probe.stderr.log").write_text(stderr or "")
    pending_result = {"schema": "current_pair_resource_calibration_launcher_result_v3",
                      "status": "child_reaped_postflight_pending",
                      "run_id": plan["run_id"], "client_request_id": plan["client_request_id"],
                      "plan_sha256": plan_sha, "raw_exit": process.returncode,
                      "raw_exits": {"launcher_child": process.returncode, "probe": process.returncode},
                      "rss_current_peaks_bytes": rss_peaks,
                      "process_birth_identity": process_start_identity,
                      "owned_pgid": process_pgid,
                      "owned_processes_and_groups_absent": None,
                      "pins_verified_before_spawn": len(verify(args.pins, pins_sha)["files"]),
                      "pins_verified_after_child": None}
    (args.output / "launcher-result.json").write_text(json.dumps(pending_result, sort_keys=True, indent=2) + "\n")
    monitor.join(timeout=1.0)
    if monitor.is_alive():
        raise RuntimeError("RSS monitor did not stop")
    if monitor_error:
        raise RuntimeError(f"RSS monitor failed closed: {monitor_error[0]}")
    group_absent = ensure_group_absent(process_pgid)
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
              "pins_verified_before_spawn": len(pins["files"]),
              "pins_verified_after_child": len(verify(args.pins, pins_sha)["files"]),
              "lexical_interpreter": interpreter_evidence,
              "process_birth_identity": process_start_identity,
              "owned_pgid": process_pgid,
              "bytecode_prefix_empty_after_child": not any(bytecode_prefix.rglob("*.pyc")),
              "pre_spawn_state_sha256": observed_state_sha256,
              "observer_wrapper_error_disposition": "not_applicable_no_observer_wrapper",
              "launch_once_marker": str(marker)}
    (args.output / "launcher-result.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    (args.output / "probe.stdout.log").write_text(stdout or "")
    (args.output / "probe.stderr.log").write_text(stderr or "")
    return process.returncode

def main() -> int:
    try:
        return _main()
    except BaseException as error:
        output = HERE / "probe-output"
        output.mkdir(exist_ok=True)
        result_path = output / "launcher-result.json"
        prior = None
        if result_path.exists():
            try: prior = json.loads(result_path.read_text())
            except (OSError, json.JSONDecodeError): prior = {"prior_result_unreadable": True}
        cleanup_path = output / "launcher-cleanup-evidence.json"
        cleanup = prior.get("cleanup") if isinstance(prior, dict) else None
        if cleanup is None and MARKER.exists():
            cleanup = {"schema": "current_pair_resource_calibration_cleanup_v1",
                       "reason": "postspawn_failure_cleanup_state_unavailable",
                       "direct_child_reaped": bool(isinstance(prior, dict) and prior.get("raw_exit") is not None),
                       "group_identity_candidate": False, "group_identity_revalidated": False,
                       "group_signal_used": False,
                       "process_group_absent": None, "absence_status": "unknown",
                       "cleanup_seconds": 0.0, "cleanup_seconds_max": 10.0}
            cleanup_path.write_text(json.dumps(cleanup, sort_keys=True, indent=2) + "\n")
        result_path.write_text(json.dumps({
            "schema": "current_pair_resource_calibration_launcher_result_v4",
            "status": "failed", "error": f"{type(error).__name__}: {error}",
            "launch_once_marker_exists": MARKER.exists(),
            "cleanup": cleanup,
            "prior_result": prior,
        }, sort_keys=True, indent=2) + "\n")
        raise

if __name__ == "__main__":
    raise SystemExit(main())
