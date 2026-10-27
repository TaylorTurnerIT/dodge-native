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
import registration_schema


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



def expected_checkpoint_counters(update, metrics):
    """Return exact counters at entry or a registered 12-update boundary."""
    r.need(update in r.EVALUATION_UPDATES, "Checkpoint update is not a registered boundary")
    if update == r.PHASE_START:
        return {"updates": 0, "optimizer_steps": 0, "environment_decisions": 0, "raw_frames": 0}
    matches = [item["counters"] for item in metrics if item.get("phase_update") == update]
    r.need(len(matches) == 1, "Checkpoint metric boundary missing or duplicated")
    return matches[0]


def validate_terminal_candidate_binding(state, phase_update, expected_counters):
    """Production boundary validator for entry and each registered evaluation checkpoint."""
    local = phase_update - r.PHASE_START
    r.need(phase_update in r.EVALUATION_UPDATES and state.get("phase_update") == phase_update
           and state.get("local_update") == local
           and state.get("update_progress", {}).get("complete") is True
           and state.get("update_progress", {}).get("in_update") is False
           and state.get("update_progress", {}).get("completed_updates") == local
           and state.get("counters") == expected_counters,
           "Candidate update/counter boundary differs")
    r.assert_saved_optimizer_lr(state, 0.00003)


def validate_outputs(reg, worker, registration_sha):
    """Validate completed normal training separately from stage competence."""
    r.need(r.valid_worker_result(worker), "Worker did not complete registered training")
    r.need(0 <= worker["work_elapsed_seconds"] < r.LIMITS["work_seconds"]
           and worker["work_elapsed_seconds"] <= worker["elapsed_seconds"] < r.LIMITS["total_seconds"],
           "Worker work/finalization budgets differ")
    r.need(worker["parent_selected_checkpoint_reported_trajectory_wall_seconds"] == r.PARENT_SELECTED_TRAJECTORY_REPORTED_SECONDS
           and worker["parent_selected_checkpoint_reported_iteration_wall_seconds"] == r.PARENT_SELECTED_ITERATION_REPORTED_SECONDS
           and worker["parent_worker_reported_trajectory_end_seconds"] == r.PARENT_WORKER_TRAJECTORY_REPORTED_SECONDS
           and worker["parent_worker_reported_complete_campaign_cost_seconds"] == r.PARENT_WORKER_CAMPAIGN_REPORTED_SECONDS,
           "Parent narrow reported clocks were not preserved separately")
    r.need(worker["selected_parent_checkpoint_trajectory_baseline_seconds"] == r.SELECTED_TRAJECTORY_BASELINE_SECONDS
           and worker["parent_completed_campaign_cost_baseline_seconds"] == r.COMPLETED_CAMPAIGN_COST_BASELINE_SECONDS
           and worker["current_iteration_observed_outer_seconds"] <= worker["elapsed_seconds"]
           and math.isclose(worker["cumulative_selected_checkpoint_trajectory_wall_seconds"],
                            r.SELECTED_TRAJECTORY_BASELINE_SECONDS + worker["current_iteration_observed_outer_seconds"], rel_tol=0, abs_tol=0.01)
           and math.isclose(worker["cumulative_successful_ancestor_and_completed_campaign_cost_seconds"],
                            r.COMPLETED_CAMPAIGN_COST_BASELINE_SECONDS + worker["current_iteration_observed_outer_seconds"], rel_tol=0, abs_tol=0.01),
           "Worker trajectory and complete-campaign wall accounting differ")
    r.need(worker["peak_rss_bytes"] <= r.LIMITS["RSS_bytes"]
           and worker["peak_mps_driver_bytes"] <= r.LIMITS["MPS_bytes"], "Worker exceeded resources")
    out = Path(reg["output"])
    transition = r.read(out / "lr-transition.json")
    entry_restore = r.read(out / "entry-restoration.json")
    r.need(transition.get("parent_checkpoint_sha256") == r.PARENT_SHA
           and transition.get("parent_receipt_sha256") == r.PARENT_RECEIPT_SHA
           and transition.get("parent_config_sha256") == r.PARENT_CONFIG_SHA
           and transition.get("arm_config_sha256") == r.CONFIG_SHA
           and transition.get("helper_sha256") == reg["lr_transition_helper_sha256"]
           and transition.get("parent_optimizer_fingerprint") == entry_restore["components"]["Adam"]["restored_sha256"]
           and transition.get("effective_lr") == 0.00003
           and transition.get("changed_fields") == ["optimizer.param_groups[*].lr"]
           and transition.get("non_lr_fields_changed") == []
           and transition.get("actual_group_lr_delta")
           and all(change == {"index":index,"before":0.0001,"after":0.00003}
                   for index,change in enumerate(transition["actual_group_lr_delta"])),
           "Registered parent-to-arm learning-rate transition receipt differs")
    r.check_import_cache(reg)
    sys.path.insert(0, reg["runtime_root"])
    from dodge_rl import checkpoints as ckpt
    metrics = [json.loads(line) for line in (out / "training-metrics.jsonl").read_text().splitlines()]
    r.need([row["phase_update"] for row in metrics] == list(range(r.PHASE_START + 1, r.PHASE_END + 1)), "Update journal incomplete")
    steps = 0
    for local_update, row in enumerate(metrics, 1):
        update = r.PHASE_START + local_update
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
        r.validate_gradient_alignment(value.get("gradient_alignment_diagnostics"))
        old, direct = value["explained_variance"], pre["explained_variance"]
        r.need((old is None and direct is None) or (old is not None and direct is not None
               and math.isclose(old, direct, rel_tol=1e-6, abs_tol=1e-6)), "Legacy EV differs")
    r.need(worker["counters"] == metrics[-1]["counters"], "Terminal counters differ")
    journal = [json.loads(line) for line in (out / "training-episodes.jsonl").read_text().splitlines()]
    parent_state = ckpt.load_checkpoint(Path(reg["parent"]["path"]), expected_sha256=r.PARENT_SHA)
    parent_abandoned = [row for row in journal if row["kind"] == "abandoned_parent_episode"]
    r.need(len(parent_abandoned) == 64
           and sorted(row["info"]["slot"] for row in parent_abandoned) == list(range(64))
           and sorted((row["info"] for row in parent_abandoned), key=lambda item: item["slot"])
               == sorted(parent_state["abandoned_current_episodes"], key=lambda item: item["slot"])
           and all(row["reason"] == "fresh_environment_at_saved_next_episode_index"
                   and row["parent_checkpoint_sha256"] == r.PARENT_SHA for row in parent_abandoned),
           "Accepted parent abandoned-episode records were not preserved exactly")
    episodes = r.validate_episode_journal(journal, parent_state["next_episode_indices"])
    r.need(worker["phase_updates"] == list(r.EVALUATION_UPDATES)
           and episodes["next_episode_indices"] == worker["final_resume_next_episode_indices"],
           "Final resume seed indices differ from journal")
    for update in r.EVALUATION_UPDATES:
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
        embedded = ckpt.load_checkpoint(path, expected_sha256=certificate["checkpoint_sha256"])
        ckpt.require_complete_update(embedded)
        expected_local = update - r.PHASE_START
        expected_counters = expected_checkpoint_counters(update, metrics)
        validate_terminal_candidate_binding(embedded, update, expected_counters)
        r.need(len(embedded["next_episode_indices"]) == 64
               and all(type(index) is int and index >= 0 for index in embedded["next_episode_indices"])
               and embedded["registration_sha256"] == registration_sha
               and embedded["parent_checkpoint_sha256"] == r.PARENT_SHA
               and embedded["config_sha256"] == reg["config_sha256"],
               "Embedded checkpoint resume state or identity differs")
        r.need(certificate["evaluation"]["complete"] is True
               and certificate["phase_update"] == update
               and certificate["evaluation"]["mean_alive_frames"] == sum(item["alive_frames"] for item in rows) / 64
               and certificate["performance"] == r.performance(certificate["evaluation"]),
               "Checkpoint evaluation certificate binding differs")
    entry = r.read(out / f"development-{r.PHASE_START:06d}.json")["evaluation"]
    predecessor = r.read(reg["parent"]["source_evaluation_path"])["evaluation"]
    entry_rows = sorted(entry["rows"], key=lambda item: item["seed"])
    predecessor_rows = sorted(predecessor["rows"], key=lambda item: item["seed"])
    r.need(entry_rows == predecessor_rows, "Entry evaluation differs from selected phase-276 candidate receipt")
    final = out / f"checkpoint-{r.PHASE_END:06d}-candidate.pt"
    # File digest and registration digest are distinct authorities.
    final_certificate = r.read(out / f"development-{r.PHASE_END:06d}.json")
    state = ckpt.load_checkpoint(final, expected_sha256=final_certificate["checkpoint_sha256"])
    ckpt.require_complete_update(state)
    parent = ckpt.load_checkpoint(Path(reg["parent"]["path"]), expected_sha256=r.PARENT_SHA)
    r.validate_parent_checkpoint_for_restore(parent, r.PARENT_SHA, r.read(reg["parent"]["terminal_receipt_path"]))
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
           and state["update_progress"]["completed_updates"] == r.NEW_UPDATES and state["phase_update"] == r.PHASE_END
           and state["local_update"] == r.NEW_UPDATES and state["selected_parent_checkpoint_trajectory_baseline_seconds"] == r.SELECTED_TRAJECTORY_BASELINE_SECONDS
           and state["parent_completed_campaign_cost_baseline_seconds"] == r.COMPLETED_CAMPAIGN_COST_BASELINE_SECONDS
           and state["current_iteration_observed_outer_seconds"] <= worker["elapsed_seconds"]
           and state["parent_checkpoint_sha256"] == r.PARENT_SHA
           and state["cumulative_selected_checkpoint_trajectory_wall_seconds"] == r.SELECTED_TRAJECTORY_BASELINE_SECONDS + state["current_iteration_observed_outer_seconds"]
           and state["cumulative_successful_ancestor_and_completed_campaign_cost_seconds"] == r.COMPLETED_CAMPAIGN_COST_BASELINE_SECONDS + state["current_iteration_observed_outer_seconds"],
           "Candidate counters, inheritance or next indices differ")
    cumulative = r.continuation_cumulative_counters(parent["cumulative_counters"], worker["counters"])
    r.need(state["cumulative_counters"] == cumulative == worker["cumulative_counters"]
           and cumulative["updates"] == r.EXPECTED_TOTAL, "Cumulative counters differ")
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
    return {"updates_checked": r.NEW_UPDATES, "evaluations_checked": len(r.EVALUATION_UPDATES), "optimizer_steps_checked": steps,
            "competence_passed": certificate["competence_passed"],
            "final_checkpoint_sha256": r.sha(final), "cumulative_counters": cumulative,
            "episode_journal": episodes}


def execute(registration, registration_sha, *, clock=time.monotonic, popen=subprocess.Popen,
            sleep=time.sleep):
    started = clock()
    # Shape validation precedes trusting the output path. The exclusive marker
    # precedes verified registration loading; no subprocess starts before checks.
    reg = r.read(registration)
    registration_schema.validate_identity(reg)
    out = Path(reg["output"])
    out.mkdir(parents=True, exist_ok=True)
    r.save(out / "launch-marker.json", {"registration_sha256": registration_sha,
           "started_monotonic": started, "launcher_pid": os.getpid(), "single_use": True})
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
            # An interrupted primary receipt may be partial. The nonzero exit
            # and separate failure receipt prohibit acceptance.
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
