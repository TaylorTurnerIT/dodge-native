"""Small owned-child supervisor for the future one-shot inference campaign."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

from paired_eval import require, sha256
from worker import (INPUT_MANIFEST_PATH, PROTOCOL_PATH, ROOT, STATE_PATH,
                    RUNTIME_DIR, _lease_check, load_json, verify_inputs)


RSS_LIMIT = 6 * 1024**3
MPS_LIMIT = 6 * 1024**3
WORK_SECONDS = 590.0
TOTAL_SECONDS = 600.0
SAMPLE_SECONDS = 0.25


def observed_rss(pid: int) -> int:
    result = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True,
                            text=True, timeout=0.5, check=False)
    require(result.returncode == 0 and result.stdout.strip().isdigit(), "Owned child RSS sample failed")
    return int(result.stdout.strip()) * 1024


def supervisor_peak_rss() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def latest_resource_sample(path: Path, *, now: float | None = None) -> dict | None:
    if not path.exists():
        return None
    data = path.read_bytes()
    if not data:
        return None
    complete = data.split(b"\n")
    has_partial_tail = not data.endswith(b"\n")
    if has_partial_tail:
        complete.pop()
    complete = [line for line in complete if line]
    require(bool(complete), "Resource log has no complete sample")
    sample = json.loads(complete[-1])
    require(isinstance(sample, dict) and type(sample.get("monotonic")) in (int, float)
            and type(sample.get("mps_driver_bytes")) is int and type(sample.get("rss_bytes")) is int,
            "Latest complete resource sample is malformed")
    current = time.monotonic() if now is None else now
    age = current - sample["monotonic"]
    require(0.0 <= age <= 4 * SAMPLE_SECONDS, "Latest complete resource sample is stale")
    return sample


def resources_within_limits(rss_bytes: int, mps_bytes: int) -> bool:
    return type(rss_bytes) is int and type(mps_bytes) is int \
        and 0 <= rss_bytes <= RSS_LIMIT and 0 <= mps_bytes <= MPS_LIMIT


def group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def stop_owned_child(process: subprocess.Popen, *, timeout: float = 5.0) -> dict:
    """Signal only the still-existing group created by start_new_session."""
    pgid = process.pid
    result = {"owned_pid": process.pid, "owned_pgid": pgid, "signals": [], "errors": []}
    # Reap direct child first. Never signal after the exact group is proven absent.
    if process.poll() is None:
        try:
            if group_exists(pgid):
                os.killpg(pgid, signal.SIGTERM)
                result["signals"].append("SIGTERM")
        except ProcessLookupError:
            result["group_absent_proven"] = True
        except BaseException as error:
            result["errors"].append(f"SIGTERM: {type(error).__name__}: {error}")
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if process.poll() is None and group_exists(pgid):
            try:
                os.killpg(pgid, signal.SIGKILL)
                result["signals"].append("SIGKILL")
            except ProcessLookupError:
                result["group_absent_proven"] = True
            except BaseException as error:
                result["errors"].append(f"SIGKILL: {type(error).__name__}: {error}")
        try:
            process.wait(timeout=timeout)
        except BaseException as error:
            result["errors"].append(f"wait: {type(error).__name__}: {error}")
    except BaseException as error:
        result["errors"].append(f"wait: {type(error).__name__}: {error}")
    result["raw_exit"] = process.poll()
    result["direct_child_reaped"] = process.poll() is not None
    result["group_absent_after_reap"] = not group_exists(pgid)
    return result


def terminal_status(*, worker_status: str | None, raw_exit: int | None,
                    child_reaped: bool, group_absent: bool, guard_ok: bool,
                    publication_ok: bool) -> str:
    if not guard_ok or not publication_ok or not child_reaped or not group_absent:
        return "failed_postflight_or_publication"
    if raw_exit != 0 or worker_status != "complete":
        return "failed_worker"
    return "complete_pending_parent_acceptance"


def _publish_json(path: Path, value: dict, *, replace: bool = False) -> None:
    path = Path(path)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    if path.exists() and not replace:
        raise FileExistsError(path)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _child_environment(output_dir: Path) -> dict[str, str]:
    selected = ("PATH", "HOME", "TMPDIR", "LANG", "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH")
    env = {key: os.environ[key] for key in selected if key in os.environ}
    env.update({"PYTHONPYCACHEPREFIX": str(output_dir / "pycache"),
                "PYTHONPATH": str(RUNTIME_DIR), "PYTHONUNBUFFERED": "1",
                "PYTHONHASHSEED": "0", "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4",
                "T3_PAIRED_EVAL_SUPERVISED": "1"})
    return env


def run_once(output_dir: Path, *, python: Path, protocol_path: Path = PROTOCOL_PATH,
             state_path: Path = STATE_PATH, clock=time.monotonic,
             popen=subprocess.Popen, sleep=time.sleep) -> dict:
    started = clock()
    deadline = started + TOTAL_SECONDS
    work_deadline = started + WORK_SECONDS
    output_dir = Path(output_dir)
    require(not output_dir.exists(), "Campaign output path already exists; no retries")
    protocol = load_json(protocol_path)
    manifest = verify_inputs()
    expected_python = ROOT / manifest["interpreter"]["lexical_venv_path"]
    require(Path(sys.executable).resolve() == Path(manifest["interpreter"]["resolved_target"])
            and Path(python).absolute() == expected_python.absolute(),
            "Supervisor and worker must use the registered lexical venv interpreter")
    protocol_hash = sha256(protocol_path)
    manifest_hash = sha256(INPUT_MANIFEST_PATH)
    harness_hash = protocol["harness_sha256"]
    _lease_check(protocol, protocol_hash, harness_hash, manifest_hash, state_path)
    require(clock() < work_deadline, "Preflight exhausted registered work budget")
    output_dir.mkdir(parents=True, exist_ok=False)
    pycache_dir = output_dir / "pycache"
    pycache_dir.mkdir()
    require(not any(pycache_dir.iterdir()), "Owned Python cache prefix must start empty")
    stdout_path, stderr_path = output_dir / "worker.stdout.log", output_dir / "worker.stderr.log"
    resources_path = output_dir / "resources.jsonl"
    command = [str(python), "-B", str(PROTOCOL_PATH.parent / "worker.py"),
               "--worker", "--output", str(output_dir / "worker-output"),
               "--resource-log", str(resources_path)]
    process = None
    raw_exit = None
    stop_info = None
    cancel = []
    resource_ok = True
    worker_status = None
    stdout = stdout_path.open("xb")
    stderr = stderr_path.open("xb")
    try:
        process = popen(command, cwd=str(ROOT), env=_child_environment(output_dir),
                       stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                       start_new_session=True, close_fds=True)
        while process.poll() is None:
            now = clock()
            try:
                _lease_check(protocol, protocol_hash, harness_hash, manifest_hash, state_path)
            except BaseException as error:
                cancel.append({"kind": "lease_or_parent_cancel", "monotonic": now,
                               "error": f"{type(error).__name__}: {error}"})
                break
            try:
                rss = observed_rss(process.pid) + supervisor_peak_rss()
                sample = latest_resource_sample(resources_path, now=now)
                mps = 0 if sample is None else int(sample["mps_driver_bytes"])
                if not resources_within_limits(rss, mps):
                    cancel.append({"kind": "resource_limit", "monotonic": now,
                                   "rss_bytes": rss, "mps_driver_bytes": mps})
                    resource_ok = False
                    break
            except BaseException as error:
                cancel.append({"kind": "resource_monitor_failure", "monotonic": now,
                               "error": f"{type(error).__name__}: {error}"})
                resource_ok = False
                break
            if now >= work_deadline:
                cancel.append({"kind": "590_second_work_deadline", "monotonic": now})
                break
            sleep(SAMPLE_SECONDS)
        if cancel and process.poll() is None:
            stop_info = stop_owned_child(process)
        else:
            raw_exit = process.wait(timeout=max(0.0, min(10.0, deadline - clock())))
            stop_info = {"owned_pid": process.pid, "owned_pgid": process.pid,
                         "raw_exit": raw_exit, "direct_child_reaped": True,
                         "group_absent_after_reap": not group_exists(process.pid), "signals": [], "errors": []}
        raw_exit = process.poll()
    except BaseException as error:
        cancel.append({"kind": "supervisor_exception", "monotonic": clock(),
                       "error": f"{type(error).__name__}: {error}"})
        if process is not None and process.poll() is None:
            stop_info = stop_owned_child(process)
        raw_exit = None if process is None else process.poll()
    finally:
        stdout.flush()
        stderr.flush()
        stdout.close()
        stderr.close()
    worker_output = output_dir / "worker-output"
    worker_result_path = worker_output / "worker-result.json"
    if worker_result_path.is_file():
        try:
            worker_status = load_json(worker_result_path).get("status")
        except BaseException:
            worker_status = "invalid_result"
    guard_ok = False
    postflight_error = None
    try:
        require(clock() <= deadline, "600-second total deadline exceeded")
        verify_inputs()
        _lease_check(protocol, protocol_hash, harness_hash, manifest_hash, state_path)
        require(stop_info is not None and stop_info.get("direct_child_reaped") is True
                and stop_info.get("group_absent_after_reap") is True,
                "Owned child/group not directly reaped")
        samples = [json.loads(line) for line in resources_path.read_text().splitlines()]
        require(bool(samples), "No resource samples retained")
        worker_rss_peak = max(int(row["rss_bytes"]) for row in samples)
        rss_peak = worker_rss_peak + supervisor_peak_rss()
        mps_peak = max(int(row["mps_driver_bytes"]) for row in samples)
        require(resource_ok and resources_within_limits(rss_peak, mps_peak),
                "Owned resource cap exceeded")
        guard_ok = not cancel
    except BaseException as error:
        postflight_error = f"{type(error).__name__}: {error}"
    publication_ok = True
    result = {"schema": "latest_best_paired_eval_run_result_v1",
              "status": terminal_status(worker_status=worker_status, raw_exit=raw_exit,
                                        child_reaped=bool(stop_info and stop_info.get("direct_child_reaped")),
                                        group_absent=bool(stop_info and stop_info.get("group_absent_after_reap")),
                                        guard_ok=guard_ok, publication_ok=publication_ok),
              "accepted": False, "worker_status": worker_status, "raw_worker_exit": raw_exit,
              "worker_launch_count": 0 if process is None else 1,
              "command": command, "cwd": str(ROOT), "python_symlink": str(python),
              "python_target": str(python.resolve()), "outer_elapsed_seconds": clock() - started,
              "child_environment": _child_environment(output_dir),
              "work_budget_seconds": WORK_SECONDS, "total_budget_seconds": TOTAL_SECONDS,
              "cleanup_reserve_seconds": 10, "cancellation_lineage": cancel,
              "owned_process_cleanup": stop_info, "resource_caps_bytes": {"aggregate_rss": RSS_LIMIT,
                                                                           "mps_driver": MPS_LIMIT},
              "resource_monitor_passed": resource_ok and guard_ok,
              "postflight_error": postflight_error,
              "scope": "inference-only exploratory D2 paired diagnostic; parent acceptance required"}
    # All child pipes and episode/resource streams are closed before final hashes.
    artifact_hashes = {}
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name not in {"run-result.json", "preparation-receipt.json"}:
            artifact_hashes[str(path.relative_to(output_dir))] = sha256(path)
    result["artifact_sha256"] = artifact_hashes
    publication_error = None
    try:
        _publish_json(output_dir / "run-result.json", result)
        verify_inputs()
        _lease_check(protocol, protocol_hash, harness_hash, manifest_hash, state_path)
        require(clock() <= deadline, "600-second total deadline exceeded during publication")
    except BaseException as error:
        publication_error = f"{type(error).__name__}: {error}"
        result["status"] = "failed_postflight_or_publication"
        result["accepted"] = False
        result["publication_failure"] = publication_error
        try:
            if not (output_dir / "run-result.json").exists():
                _publish_json(output_dir / "run-result.json", result)
            else:
                _publish_json(output_dir / "run-result.json", result, replace=True)
        except BaseException as publication_exception:
            result["publication_failure_receipt_error"] = \
                f"{type(publication_exception).__name__}: {publication_exception}"
    if (output_dir / "run-result.json").is_file():
        result["run_result_sha256"] = sha256(output_dir / "run-result.json")
        try:
            _publish_json(output_dir / "preparation-receipt.json", result)
        except BaseException as error:
            result["publication_failure"] = f"{type(error).__name__}: {error}"
            result["status"] = "failed_postflight_or_publication"
            try:
                _publish_json(output_dir / "run-result.json", result, replace=True)
                result["run_result_sha256"] = sha256(output_dir / "run-result.json")
                _publish_json(output_dir / "publication-failure.json", result)
            except BaseException:
                pass
    if (output_dir / "preparation-receipt.json").is_file() and publication_error is None:
        try:
            verify_inputs()
            _lease_check(protocol, protocol_hash, harness_hash, manifest_hash, state_path)
            require(clock() <= deadline, "600-second total deadline exceeded after final receipt")
        except BaseException as error:
            result["status"] = "failed_postflight_or_publication"
            result["accepted"] = False
            result["postpublication_failure"] = f"{type(error).__name__}: {error}"
            try:
                _publish_json(output_dir / "run-result.json", result, replace=True)
                result["run_result_sha256"] = sha256(output_dir / "run-result.json")
                _publish_json(output_dir / "preparation-receipt.json", result, replace=True)
                _publish_json(output_dir / "postpublication-failure.json", result)
            except BaseException as publication_exception:
                result["publication_failure_receipt_error"] = \
                    f"{type(publication_exception).__name__}: {publication_exception}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=ROOT / "python/.venv/bin/python")
    args = parser.parse_args()
    result = run_once(args.output, python=args.python)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "complete_pending_parent_acceptance" else 1


if __name__ == "__main__":
    raise SystemExit(main())
