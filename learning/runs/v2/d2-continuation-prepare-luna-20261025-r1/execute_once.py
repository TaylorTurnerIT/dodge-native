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
import threading
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



def process_tree(rows, root_pid):
    owned = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, row in rows.items():
            if row["ppid"] in owned and pid not in owned:
                owned.add(pid); changed = True
    return [rows[pid] for pid in owned if pid in rows]


def parse_ps_rows(output):
    rows = {}
    for line in output.splitlines():
        fields = line.strip().split()
        if len(fields) >= 3:
            try:
                pid, ppid, rss_kib = map(int, fields[:3])
                rows[pid] = {"pid": pid, "ppid": ppid, "rss_bytes": rss_kib * 1024}
            except ValueError:
                continue
    return rows


class AggregateRssWatch:
    """Sample launcher process tree through terminal CPU-side validation and decoding."""
    def __init__(self, root_pid, path, limit):
        self.root_pid, self.path, self.limit = root_pid, Path(path), limit
        self.stop_event = threading.Event()
        self.thread = None
        self.peak_bytes = 0
        self.samples = 0
        self.first_error = None
        self.exceeded = False

    def _run(self):
        with self.path.open("x") as stream:
            while not self.stop_event.is_set():
                now = time.monotonic()
                try:
                    output = subprocess.run(["/bin/ps", "-axo", "pid=,ppid=,rss="],
                                            capture_output=True, text=True, check=True).stdout
                    rows = parse_ps_rows(output)
                    owned = process_tree(rows, self.root_pid)
                    total = sum(row["rss_bytes"] for row in owned)
                    self.peak_bytes = max(self.peak_bytes, total)
                    self.samples += 1
                    self.exceeded |= total > self.limit
                    stream.write(json.dumps({"monotonic": now, "aggregate_rss_bytes": total,
                                            "owned_processes": owned}, sort_keys=True) + "\n")
                    stream.flush()
                except BaseException as error:
                    if self.first_error is None:
                        self.first_error = repr(error)
                self.stop_event.wait(.05)

    def start(self):
        self.thread = threading.Thread(target=self._run, name="owned-aggregate-rss", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
        return {"samples": self.samples, "peak_aggregate_rss_bytes": self.peak_bytes,
                "limit_bytes": self.limit, "limit_exceeded": self.exceeded,
                "observer_error": self.first_error, "thread_stopped": self.thread is None or not self.thread.is_alive()}

def validate_outputs(reg, worker, registration_sha):
    """Validate completed normal training separately from stage competence."""
    r.need(r.valid_worker_result(worker), "Worker did not complete registered training")
    r.need(0 <= worker["work_elapsed_seconds"] < r.LIMITS["work_seconds"]
           and worker["work_elapsed_seconds"] <= worker["elapsed_seconds"] < r.LIMITS["total_seconds"],
           "Worker work/finalization budgets differ")
    r.need(worker["peak_rss_bytes"] <= r.LIMITS["RSS_bytes"]
           and worker["peak_mps_driver_bytes"] <= r.LIMITS["MPS_bytes"], "Worker exceeded resources")
    out = Path(reg["output"])
    r.check_import_cache(reg)
    sys.path.insert(0, reg["runtime_root"])
    from dodge_rl import checkpoints as ckpt
    metrics = [json.loads(line) for line in (out / "training-metrics.jsonl").read_text().splitlines()]
    r.need([row["phase_update"] for row in metrics] == list(range(73, 145)), "Update journal incomplete")
    steps = 0
    for local_update, row in enumerate(metrics, 1):
        update = 72 + local_update
        value = row["metrics"]; r.finite_tree(value)
        r.need(0 < value["optimizer_steps"] <= 128 and value["transitions"] == 16384,
               "Optimizer or rollout counts differ")
        steps += value["optimizer_steps"]
        r.need(row.get("local_update") == local_update and row["counters"]["updates"] == local_update
               and row["counters"]["optimizer_steps"] == steps
               and row["counters"]["environment_decisions"] == local_update * 16384
               and row["update_progress"]["completed_updates"] == local_update
               and row["update_progress"]["complete"] is True
               and row["update_progress"]["in_update"] is False, "Counter/update boundary differs")
        diag = value["critic_diagnostics"]
        r.need(diag["version"] == "same_batch_critic_diagnostics_v1", "Wrong diagnostic schema")
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
    r.need(worker["counters"] == metrics[-1]["counters"], "Terminal counters differ")
    journal = [json.loads(line) for line in (out / "training-episodes.jsonl").read_text().splitlines()]
    parent_state = ckpt.load_checkpoint(Path(reg["parent"]["path"]), expected_sha256=r.PARENT_SHA)
    episodes = r.validate_episode_journal(journal, parent_state["next_episode_indices"])
    r.need(worker["phase_updates"] == [72, 144]
           and episodes["next_episode_indices"] == worker["final_resume_next_episode_indices"],
           "Final resume seed indices differ from journal")
    for update in (72, 144):
        certificate = r.read(out / f"development-{update:06d}.json")
        evaluation = certificate["evaluation"]; rows = evaluation["rows"]
        r.need(evaluation["complete"] is True and len(rows) == 64
               and sorted(row["seed"] for row in rows) == list(range(0xD0000000, 0xD0000040)),
               "Development cohort incomplete or changed")
        r.need(certificate["performance"] == r.performance(evaluation)
               and evaluation["mean_alive_frames"] == sum(row["alive_frames"] for row in rows) / 64
               and evaluation["mean_score"] == sum(row["score"] for row in rows) / 64,
               "Development summary differs")
        causes = {}
        for row in rows:
            r.need(row["terminated"] != row["truncated"], "Invalid episode termination")
            if row["terminated"]:
                causes[row["death_cause"]] = causes.get(row["death_cause"], 0) + 1
            r.need(math.isclose(row["objective_return"], row["score"] + .01 * row["alive_frames"]
                               - (5 if row["terminated"] else 0), abs_tol=1e-9), "Episode reward differs")
        r.need(causes == {key: count for key, count in evaluation["death_causes"].items() if count}
               and evaluation["deaths"] + evaluation["caps"] == 64, "Death/cap attribution differs")
        r.need(certificate["normal_training_iteration"] is True and certificate["training_eligible"] is False
               and certificate["promoted"] is False and certificate["training_state_unchanged"] is True,
               "Evaluation eligibility/state flags differ")
        path = out / certificate["checkpoint"]
        r.need(path.parent == out and path.name == f"checkpoint-{update:06d}-candidate.pt"
               and r.sha(path) == certificate["checkpoint_sha256"], "Checkpoint identity differs")
        sidecar = r.read(Path(str(path) + ".json"))
        r.need(sidecar["eligibility_status"] == "provisional_pending_parent_terminal_receipt"
               and sidecar["training_eligible"] is False and sidecar["promoted"] is False
               and sidecar["checkpoint_sha256"] == r.sha(path), "Checkpoint sidecar differs")
    final = out / "checkpoint-000144-candidate.pt"
    # File digest and registration digest are distinct authorities.
    state = ckpt.load_checkpoint(final, expected_sha256=certificate["checkpoint_sha256"])
    ckpt.require_complete_update(state)
    parent = ckpt.load_checkpoint(Path(reg["parent"]["path"]), expected_sha256=r.PARENT_SHA)
    r.need(state["schema"] == "d2_training_v3_checkpoint_v1"
           and state["eligibility_status"] == "provisional_pending_parent_terminal_receipt"
           and state["registration_sha256"] == registration_sha
           and state["config_sha256"] == reg["config_sha256"]
           and state["policy_sha256"] == r.POLICY_SHA
           and state["runtime_sha256"] == reg["runtime_sha256"]
           and state["native_sha256"] == reg["native"]["sha256"]
           and state["parent_sha256"] == r.PARENT_SHA and state["run_seed"] == reg["run_seed"]
           and state["identity"]["registration_sha256"] == registration_sha
           and state["identity"]["run_seed"] == reg["run_seed"]
           and state["training_eligible"] is False and state["promoted"] is False,
           "Normal candidate frozen identity differs")
    r.need(state["counters"] == worker["counters"]
           and state["inherited_counters"] == parent["cumulative_counters"] == worker["inherited_counters"]
           and state["next_episode_indices"] == episodes["next_episode_indices"]
           and state["update_progress"]["completed_updates"] == 72 and state["phase_update"] == 144
           and state["local_update"] == 72 and state["parent_inclusive_wall_seconds"] == r.PARENT_WALL_SECONDS
           and state["parent_checkpoint_sha256"] == r.PARENT_SHA,
           "Candidate counters, inheritance or next indices differ")
    cumulative = r.continuation_cumulative_counters(parent["cumulative_counters"], worker["counters"])
    r.need(state["cumulative_counters"] == cumulative == worker["cumulative_counters"]
           and cumulative["updates"] == 192, "Cumulative counters differ")
    abandoned = state["abandoned_current_episodes"]
    r.need(len(abandoned) == 64
           and sorted(item["slot"] for item in abandoned) == list(range(64)),
           "Final live episode abandonment records missing or duplicated")
    for item in abandoned:
        r.need(item["seed"]["episode"] == episodes["current_episode_indices"][item["slot"]]
               and 0 <= item["gameplay_frames"] < 18000,
               "Final live episode seed/frame state differs")
    completed_frames = sum(row["info"]["gameplay_frames"] for row in journal if row["kind"] == "completed")
    r.need(completed_frames + sum(item["gameplay_frames"] for item in abandoned)
           == worker["counters"]["raw_frames"], "Training episode raw-frame conservation differs")
    r.need(certificate["competence_passed"] == (evaluation["mean_alive_frames"] >= 3060),
           "V3 competence predicate differs")
    return {"updates_checked": 72, "evaluations_checked": 2, "optimizer_steps_checked": steps,
            "competence_passed": certificate["competence_passed"],
            "final_checkpoint_sha256": r.sha(final), "cumulative_counters": cumulative,
            "episode_journal": episodes}


def execute(registration, registration_sha, *, clock=time.monotonic, popen=subprocess.Popen,
            sleep=time.sleep):
    started = clock()
    # Shape validation precedes trusting the output path. No subprocess precedes
    # the exclusive marker and full byte checks.
    reg = r.read(registration)
    r.need(reg.get("schema") == "d2_training_v3_continuation_registration_v1"
           and Path(reg["output"]).resolve() == Path(reg["root"]) / "learning/runs/v2" / r.RUN_ID,
           "Unsafe registration output shape")
    out = Path(reg["output"])
    out.mkdir(parents=True, exist_ok=True)
    r.save(out / "launch-marker.json", {"registration_sha256": registration_sha,
           "started_monotonic": started, "launcher_pid": os.getpid(), "single_use": True})
    result = {"status": "failed", "actual_worker_launch_count": 0, "normal_training_iteration": True,
              "training_eligible": False, "promoted": False, "registration_sha256": registration_sha}
    process = None
    rss_watch = AggregateRssWatch(os.getpid(), out / "supervisor-resources.jsonl", r.LIMITS["RSS_bytes"])
    rss_watch.start()
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
        reg, _ = r.load_registration(registration, registration_sha)
        r.need(Path(reg["launcher_path"]).resolve() == Path(__file__).resolve(), "Launcher origin differs")
        r.need(signal_event is None and clock() - started < r.LIMITS["work_seconds"], "Cancelled or preflight expired")
        command = [reg["interpreter"], "-B", reg["runner_path"], "--registration", str(registration),
                   "--registration-sha256", registration_sha, "--started", repr(started)]
        env = os.environ.copy()
        env["PYTHONPATH"] = reg["runtime_root"]
        env["PYTHONPYCACHEPREFIX"] = reg["import_policy"]["pycache_prefix"]
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        with (out / "worker.log").open("x") as log:
            process = popen(command, env=env, cwd=reg["root"], start_new_session=True,
                            stdout=log, stderr=subprocess.STDOUT)
            result.update(actual_worker_launch_count=1, command=command, worker_pid=process.pid,
                          owned_pgid=process.pid, start_new_session=True)
            r.save(out / "worker-launch.json", {"worker_pid": process.pid,
                   "owned_pgid": process.pid, "launcher_pid": os.getpid(),
                   "command": command, "start_new_session": True,
                   "observed_monotonic": clock(), "registration_sha256": registration_sha})
            while True:
                r.need(signal_event is None, "Parent cancellation latched")
                r.need(0 <= clock() - started < r.LIMITS["total_seconds"], "Parent total deadline exhausted")
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
        result["evidence_checks"] = validate_outputs(reg, worker, registration_sha)
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
            rss_summary = rss_watch.stop()
            result["aggregate_rss_observation"] = rss_summary
            if (rss_summary["observer_error"] is not None or not rss_summary["thread_stopped"]
                    or rss_summary["limit_exceeded"]):
                result["status"] = "failed"
                result.setdefault("error", "Aggregate owned RSS observer failed or cap exceeded")
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
                failure = dict(worker_failure, role="worker")
                failure.setdefault("kind", "worker_failure")
                failures.append(failure)
            if "failure_observed_monotonic" in result:
                failures.append({"monotonic": result["failure_observed_monotonic"], "kind": "parent_failure",
                                 "error": result["error"]})
            result["first_observed_failure"] = min(failures, key=lambda v: v["monotonic"]) if failures else None
            r.save(out / "execution-result.json", result)
            return_code = 0 if (result["status"] == "passed" and signal_event is None
                                 and clock() - started < r.LIMITS["total_seconds"]) else 1
            if return_code != 0 and result["status"] == "passed":
                r.save(out / "publication-failure.json", {"status": "failed",
                       "reason": "Absolute budget exceeded during receipt publication",
                       "elapsed_seconds": clock() - started})
        except r.Cancelled as error:
            # An interrupted primary receipt remains untouched. The nonzero
            # exit and this separate failure receipt prohibit acceptance.
            result["status"] = "failed"
            failures = [signal_event]
            earlier = result.get("first_observed_failure")
            if earlier is not None:
                failures.append(earlier)
            worker_failure = result.get("worker_result", {}).get("first_failure")
            if worker_failure is not None:
                failures.append(worker_failure)
            r.save(out / "publication-failure.json", {"status": "failed", "error": repr(error),
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--registration", required=True)
    parser.add_argument("--registration-sha256", required=True)
    args = parser.parse_args()
    raise SystemExit(execute(args.registration, args.registration_sha256))
