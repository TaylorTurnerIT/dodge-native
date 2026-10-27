"""Parent-owned one-use launcher. It never edits or clears the parent lease."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

import runner as r


def group_exists(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def stop_owned(process):
    """Existing five-second TERM, five-second KILL policy on exact owned group."""
    r.need(type(process.pid) is int and process.pid > 1 and process.pid != os.getpgrp(),
           "Refusing unsafe process group")
    result = {"owned_pid": process.pid, "owned_pgid": process.pid, "errors": []}
    for sig, wait_seconds in ((signal.SIGTERM, 5), (signal.SIGKILL, 5)):
        signal_started = time.monotonic()
        group_gone = False
        try:
            os.killpg(process.pid, sig)
            result[signal.Signals(sig).name] = True
        except ProcessLookupError:
            group_gone = True
        except BaseException as error:
            result["errors"].append(repr(error))
        try:
            process.wait(timeout=wait_seconds)
        except subprocess.TimeoutExpired:
            continue
        except BaseException as error:
            result["errors"].append(repr(error))
        if sig == signal.SIGTERM and process.poll() is not None:
            for _ in range(50):
                if group_gone or not group_exists(process.pid):
                    group_gone = True
                    break
                if time.monotonic() - signal_started >= wait_seconds:
                    break
                time.sleep(.1)
            if group_gone:
                break
    result.update(exit_code=process.poll(), reaped=process.poll() is not None)
    return result


def validate_outputs(reg, worker):
    """Inspect complete retained evidence, not just the worker status string."""
    r.need(r.valid_worker_result(worker), "Worker did not complete the registered diagnostic")
    r.need(0 <= worker["elapsed_seconds"] <= r.LIMITS["work_seconds"], "Worker work budget differs")
    r.need(worker["peak_rss_bytes"] <= r.LIMITS["RSS_bytes"]
           and worker["peak_mps_driver_bytes"] <= r.LIMITS["MPS_bytes"], "Worker exceeded resources")
    out = Path(reg["output"])
    metrics = [json.loads(line) for line in (out / "training-metrics.jsonl").read_text().splitlines()]
    r.need([row["phase_update"] for row in metrics] == list(range(1, 49)), "Update journal incomplete")
    steps = 0
    for row in metrics:
        value = row["metrics"]
        r.finite_tree(value)
        steps += value["optimizer_steps"]
        r.need(0 < value["optimizer_steps"] <= 128 and value["transitions"] == 16384,
               "Optimizer or rollout counts differ")
        diag = value["critic_diagnostics"]
        r.need(diag["version"] == "same_batch_critic_diagnostics_v1", "Wrong diagnostics schema")
        pre, post = diag["pre_update"], diag["post_update"]
        for moments in (pre, post):
            r.need(moments["count"] == 16384 and moments["target_variance"] >= 0
                   and moments["residual_variance"] >= 0 and moments["residual_mse"] >= 0,
                   "Invalid critic moments")
            r.need(math.isclose(moments["residual_mse"], moments["residual_variance"]
                               + moments["residual_mean"] ** 2, rel_tol=1e-9, abs_tol=1e-12),
                   "Residual moment identity differs")
            var = moments["target_variance"]
            expected = None if var <= 1e-12 else 1 - moments["residual_variance"] / var
            r.need((expected is None and moments["explained_variance"] is None)
                   or (expected is not None and math.isclose(expected, moments["explained_variance"],
                                                            rel_tol=1e-9, abs_tol=1e-12)),
                   "Explained variance identity differs")
        r.need(pre["target_mean"] == post["target_mean"]
               and pre["target_variance"] == post["target_variance"], "Diagnostic targets changed")
        old, direct = value["explained_variance"], pre["explained_variance"]
        r.need((old is None and direct is None) or (old is not None and direct is not None
               and math.isclose(old, direct, rel_tol=1e-6, abs_tol=1e-6)), "Legacy EV differs")
        r.need(row["update_progress"]["complete"] is True
               and row["update_progress"]["in_update"] is False, "Incomplete optimizer update")
    r.need(worker["counters"]["optimizer_steps"] == steps
           and worker["counters"]["environment_decisions"] == 48 * 16384,
           "Terminal counters differ from journal")
    for update in (0, 24, 48):
        certificate = r.read(out / f"development-{update:06d}.json")
        evaluation = certificate["evaluation"]
        rows = evaluation["rows"]
        r.need(evaluation["complete"] is True and len(rows) == 64
               and [row["seed"] for row in rows] == list(range(0xD0000000, 0xD0000040)),
               "Development cohort incomplete or changed")
        r.need(certificate["performance"] == r.performance(evaluation)
               and evaluation["mean_alive_frames"] == sum(row["alive_frames"] for row in rows) / 64
               and evaluation["mean_score"] == sum(row["score"] for row in rows) / 64,
               "Development summary differs")
        r.need(sum(evaluation["death_causes"].values()) == evaluation["deaths"]
               and evaluation["deaths"] + evaluation["caps"] == 64,
               "Death/cap summary incomplete")
        r.need(certificate["diagnostic_only"] is True and certificate["training_eligible"] is False
               and certificate["promoted"] is False and certificate["training_state_unchanged"] is True,
               "Evaluation eligibility/state flags differ")
        path = out / certificate["checkpoint"]
        r.need(path.parent == out and path.name == f"diagnostic-{update:06d}.pt"
               and r.sha(path) == certificate["checkpoint_sha256"], "Checkpoint identity differs")
        sidecar = r.read(Path(str(path) + ".json"))
        r.need(sidecar["diagnostic_only"] is True and sidecar["training_eligible"] is False
               and sidecar["promoted"] is False and sidecar["checkpoint_sha256"] == r.sha(path),
               "Checkpoint sidecar differs")
    return {"updates_checked": 48, "evaluations_checked": 3, "optimizer_steps_checked": steps}


def execute(registration, registration_sha, *, clock=time.monotonic, popen=subprocess.Popen,
            sleep=time.sleep):
    started = clock()
    # Shape validation precedes trusting the output path. No subprocess precedes
    # the exclusive marker and full byte checks.
    reg = r.validate_registration(r.read(registration))
    out = Path(reg["output"])
    out.mkdir(parents=True, exist_ok=True)
    r.save(out / "launch-marker.json", {"registration_sha256": registration_sha,
           "started_monotonic": started, "launcher_pid": os.getpid(), "single_use": True})
    result = {"status": "failed", "actual_worker_launch_count": 0, "diagnostic_only": True,
              "training_eligible": False, "promoted": False, "registration_sha256": registration_sha}
    process = None
    signal_event = None
    cleanup = None
    previous = {n: signal.getsignal(n) for n in (signal.SIGINT, signal.SIGTERM)}

    def handle(number, _frame):
        nonlocal signal_event
        if signal_event is None:
            signal_event = {"monotonic": clock(), "signal": number, "kind": "cancelled"}

    for n in previous:
        signal.signal(n, handle)
    try:
        reg, _ = r.load_registration(registration, registration_sha)
        r.need(Path(reg["launcher_path"]).resolve() == Path(__file__).resolve(), "Launcher origin differs")
        r.need(signal_event is None and clock() - started < r.LIMITS["work_seconds"], "Cancelled or preflight expired")
        command = [reg["interpreter"], "-B", reg["runner_path"], "--registration", str(registration),
                   "--registration-sha256", registration_sha, "--started", repr(started)]
        env = os.environ.copy()
        env["PYTHONPATH"] = reg["runtime_root"]
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        with (out / "worker.log").open("x") as log:
            process = popen(command, env=env, cwd=reg["root"], start_new_session=True,
                            stdout=log, stderr=subprocess.STDOUT)
            result.update(actual_worker_launch_count=1, command=command, worker_pid=process.pid,
                          owned_pgid=process.pid, start_new_session=True)
            while True:
                r.need(signal_event is None, "Parent cancellation latched")
                r.need(clock() - started < r.LIMITS["work_seconds"], "Parent work deadline exhausted")
                r.check_lease(reg)
                code = process.poll()
                if code is not None:
                    break
                sleep(.1)
            code = process.wait(timeout=0)
            result.update(observed_worker_raw_exit=code, directly_reaped=True,
                          direct_wait_observed_monotonic=clock())
        r.need(not group_exists(process.pid), "Owned group remains after leader reap")
        result["owned_group_absent"] = True
        r.need(code == 0, "Worker raw exit was not zero")
        worker = r.read(out / "worker-result.json")
        result["worker_result"] = worker
        result["evidence_checks"] = validate_outputs(reg, worker)
        r.need(signal_event is None and clock() - started < r.LIMITS["total_seconds"], "Cancelled or total budget exhausted")
        # Recheck the externally anchored registration, every source/runtime
        # byte, old native binary and exact lease after the worker has exited.
        r.load_registration(registration, registration_sha)
        result["postflight_inputs_unchanged"] = True
        r.need(signal_event is None and clock() - started < r.LIMITS["total_seconds"], "Finalization budget exhausted")
        files = {str(p.relative_to(out)): r.sha(p) for p in out.iterdir() if p.is_file()}
        r.save(out / "artifact-manifest.json", files)
        r.need(signal_event is None and clock() - started < r.LIMITS["total_seconds"], "Publication budget exhausted")
        result["status"] = "passed"
    except BaseException as error:
        result.update(error=repr(error), traceback=traceback.format_exc(), failure_observed_monotonic=clock())
        if process is not None:
            cleanup = stop_owned(process)
            result["owned_group_absent"] = not group_exists(process.pid)
            result["observed_worker_raw_exit"] = process.poll()
            result["directly_reaped"] = process.poll() is not None
        worker_path = out / "worker-result.json"
        if worker_path.exists():
            try:
                result["worker_result"] = r.read(worker_path)
            except BaseException as secondary:
                result["worker_receipt_error"] = repr(secondary)
    finally:
        if signal_event is not None:
            result["status"] = "failed"
            result["parent_signal"] = signal_event
        result.update(elapsed_seconds=clock() - started, cleanup=cleanup,
                      lease_clearing_owner="parent")
        failures = []
        if signal_event is not None:
            failures.append(signal_event)
        worker_failure = result.get("worker_result", {}).get("first_failure")
        if worker_failure is not None:
            failure = dict(worker_failure, role="worker")
            failure.setdefault("kind", "worker_failure")
            failures.append(failure)
        if "failure_observed_monotonic" in result:
            failures.append({"monotonic": result["failure_observed_monotonic"], "kind": "parent_failure",
                             "error": result["error"]})
        result["first_observed_failure"] = min(failures, key=lambda v: v["monotonic"]) if failures else None
        for n, handler in previous.items():
            signal.signal(n, handler)
        r.save(out / "execution-result.json", result)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--registration", required=True)
    parser.add_argument("--registration-sha256", required=True)
    args = parser.parse_args()
    raise SystemExit(execute(args.registration, args.registration_sha256))
