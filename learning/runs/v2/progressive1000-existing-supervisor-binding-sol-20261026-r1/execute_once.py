"""Adapted D2 one-use launcher. Parent owns marker, lease and acceptance.

Only control files are written here. The accepted worker creates its own output.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback
import binding as r
import terminal

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


def execute(envelope_path, envelope_sha, *, clock=time.monotonic, popen=subprocess.Popen,
            sleep=time.sleep):
    envelope, reg = r.load_envelope(envelope_path, envelope_sha)
    started = envelope['started']
    registration_sha = envelope['registration_sha256']
    out, control = Path(reg['output']), Path(envelope['control'])
    r.need(r.read(control/'dispatch.claimed')['envelope_sha256'] == envelope_sha,
           'external observer dispatch claim missing')
    r.save(control/'supervisor.claimed', {'envelope_sha256': envelope_sha, 'pid': os.getpid()})
    r.verify_bound(envelope, reg, preflight=True)
    result = {"status": "failed", "actual_worker_launch_count": 0, "normal_training_iteration": True,
              "training_eligible": False, "promoted": False, "registration_sha256": registration_sha}
    process = None
    signal_event = None
    publication_phase = False
    cleanup = None
    previous = {n: signal.getsignal(n) for n in (signal.SIGINT, signal.SIGTERM)}

    def handle(number, _frame):
        nonlocal signal_event
        if signal_event is None:
            signal_event = {"monotonic": clock(), "signal": number, "kind": "cancelled"}
            if publication_phase:
                # Once work/cleanup is over, a first late signal must interrupt
                # publication instead of becoming an unobserved success latch.
                raise r.Cancelled("Cancellation during terminal publication")

    for n in previous:
        signal.signal(n, handle)
    try:
        r.need(signal_event is None and clock() - started < r.LIMITS['work_seconds'], 'Cancelled or preflight expired')
        command = r.worker_command(envelope, reg)
        env = os.environ.copy()
        env["PYTHONPATH"] = reg["runtime_root"]
        env["PYTHONPYCACHEPREFIX"] = reg["import_policy"]["pycache_prefix"]
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        with (control / "worker.log").open("x") as log:
            process = popen(command, env=env, cwd=r.ROOT, start_new_session=True,
                            stdout=log, stderr=subprocess.STDOUT)
            result.update(actual_worker_launch_count=1, command=command, worker_pid=process.pid,
                          owned_pgid=process.pid, start_new_session=True)
            r.save(control / "worker-launch.json", {"worker_pid": process.pid,
                   "owned_pgid": process.pid, "launcher_pid": os.getpid(),
                   "command": command, "start_new_session": True,
                   "observed_monotonic": clock(), "registration_sha256": registration_sha})
            while True:
                r.need(signal_event is None, "Parent cancellation latched")
                r.need(0 <= clock() - started < r.LIMITS["work_seconds"], "Parent work deadline exhausted")
                r.need(not os.path.lexists(envelope["cancel_path"]), "Parent cancel marker present")
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
        result["evidence_checks"] = terminal.validate_outputs(reg, worker, registration_sha)
        r.need(signal_event is None and clock() - started < r.LIMITS["total_seconds"], "Cancelled or total budget exhausted")
        # Recheck the externally anchored registration, every source/runtime
        # byte, old native binary and exact lease after the worker has exited.
        r.verify_bound(envelope, reg, preflight=False)
        r.need(r.sha(envelope_path) == envelope_sha, 'envelope changed during execution')
        result["postflight_inputs_unchanged"] = True
        r.need(signal_event is None and clock() - started < r.LIMITS["total_seconds"], "Finalization budget exhausted")
        files = {str(p.relative_to(out)): r.sha(p) for p in out.iterdir() if p.is_file()}
        r.save(control / "artifact-manifest.json", files)
        r.need(signal_event is None and clock() - started < r.LIMITS["total_seconds"], "Publication budget exhausted")
        result["status"] = "completed_pending_parent_audit"
    except BaseException as error:
        result.update(error=repr(error), traceback=traceback.format_exc(), failure_observed_monotonic=clock())
        if process is not None and result.get("owned_group_absent") is not True:
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
        try:
            publication_phase = True
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
                failures.append({"monotonic": result.get("direct_wait_observed_monotonic", clock()),
                                 "kind": "worker_failure_observed", "raw_first_failure": worker_failure})
            if "failure_observed_monotonic" in result:
                failures.append({"monotonic": result["failure_observed_monotonic"], "kind": "parent_failure",
                                 "error": result["error"]})
            result["first_observed_failure"] = min(failures, key=lambda v: v["monotonic"]) if failures else None
            try:
                result["terminal_accounting"] = terminal.accounting(out, result.get("worker_result", {}))
            except BaseException as accounting_error:
                result["accounting_error"] = repr(accounting_error)
                result["status"] = "failed"
            r.save(control / "execution-result.json", result)
            return_code = 0 if (result["status"] == "completed_pending_parent_audit" and signal_event is None
                                 and clock() - started < r.LIMITS["total_seconds"]) else 1
            if return_code != 0 and result["status"] == "completed_pending_parent_audit":
                r.save(control / "publication-failure.json", {"status": "failed",
                       "reason": "Absolute budget exceeded during receipt publication",
                       "elapsed_seconds": clock() - started})
        except r.Cancelled as error:
            # An interrupted primary receipt may be partial. The nonzero exit
            # and separate failure receipt prohibit acceptance.
            result["status"] = "failed"
            failures = [signal_event]
            earlier = result.get("first_observed_failure")
            if earlier is not None:
                failures.append(earlier)
            worker_failure = result.get("worker_result", {}).get("first_failure")
            if worker_failure is not None:
                failures.append({"monotonic": clock(), "kind": "worker_failure_observed", "raw_first_failure": worker_failure})
            r.save(control / "publication-failure.json", {"status": "failed", "error": repr(error),
                   "parent_signal": signal_event,
                   "first_observed_failure": min(failures, key=lambda v: v["monotonic"]),
                   "elapsed_seconds": clock() - started})
            return_code = 1
        finally:
            # Keep the publication handler active through the last write and
            # acceptance decision; a signal during restoration still exits
            # nonzero rather than being silently converted to success.
            for n, handler in previous.items():
                signal.signal(n, handler)
    return return_code

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--envelope', required=True)
    parser.add_argument('--envelope-sha256', required=True)
    args = parser.parse_args()
    raise SystemExit(execute(args.envelope, args.envelope_sha256))
