"""One-use launch boundary for a parent-registered adapter worker.

Parent owns state and lease publication. This module only validates, creates
the one-use marker, launches one worker, and reports raw exit evidence.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import math
import os
from pathlib import Path
import signal
import sys
import subprocess
import time

import adapter


def group_exists(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def check_finalization_budget(reg, started, clock):
    adapter.need(reg.get("_signal_event") is None, "Launcher cancellation signal latched")
    adapter.need(not Path(reg["cancel_path"]).exists(), "Parent cancellation latched")
    adapter.need(clock() - started < adapter.LIMITS["total_seconds"], "Total launcher deadline exhausted")
    adapter.need(clock() - reg["started_monotonic"] < adapter.LIMITS["total_seconds"],
                 "Parent total deadline exhausted")
    adapter.need(clock() < reg["absolute_deadline_monotonic"], "Absolute parent deadline exhausted")


def stop_owned(proc, sleep=time.sleep, clock=time.monotonic):
    if group_exists(proc.pid):
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = clock() + 5
    while group_exists(proc.pid) and clock() < deadline:
        sleep(.05)
    if group_exists(proc.pid):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.wait()
    return not group_exists(proc.pid)


def validate_final_checkpoint(reg, checkpoint_path, expected_sha, worker, episode_evidence):
    adapter.check_import_cache(reg)
    sys.path.insert(0, reg["runtime_root"])
    from dodge_rl import checkpoints
    state = checkpoints.load_checkpoint(checkpoint_path, expected_sha256=expected_sha)
    checkpoints.require_complete_update(state)
    adapter.need(state.get("schema") == "d2_training_v3_checkpoint_v1"
        and state.get("tag") == "candidate" and state.get("phase") == "D2"
        and state.get("eligibility_status") == "provisional_pending_parent_terminal_receipt"
        and state.get("training_eligible") is None and state.get("diagnostic_only") is None,
        "Final candidate checkpoint schema or eligibility differs")
    adapter.need(state.get("registration_sha256") == expected_sha,
        "Final candidate registration identity differs")
    adapter.need(state.get("parent_sha256") == adapter.PARENT_SHA
        and state.get("policy_sha256") == reg["policy"]["sha256"]
        and state.get("runtime_sha256") == reg["runtime_sha256"]
        and state.get("native_sha256") == reg["native"]["sha256"]
        and state.get("config_sha256") == reg["pins"][reg["config_path"]],
        "Final candidate frozen identities differ")
    adapter.need(state.get("run_seed") == reg["run_seed"] and state.get("counters") == worker["counters"]
        and state.get("counters", {}).get("updates") == 80
        and state.get("update_progress", {}).get("complete") is True
        and state.get("update_progress", {}).get("in_update") is False
        and state.get("complete_update_boundary") is True,
        "Final candidate counters or update boundary differ")
    adapter.need(state.get("next_episode_indices") ==
        [episode_evidence["final_episode_indices"][slot] for slot in range(64)],
        "Final candidate next episode indices differ from telemetry")
    adapter.need(state.get("cumulative_wall_seconds", math.inf) <= adapter.LIMITS["work_seconds"],
        "Final candidate cumulative wall exceeds work budget")
    adapter.need({"python", "numpy_global", "numpy_generator", "torch_cpu", "torch_mps",
                  "sampling_backend"} <= state.get("rng", {}).keys(), "Final checkpoint RNG state is incomplete")
    adapter.need(bool(state.get("model")) and bool(state.get("optimizer")), "Final candidate learner state is empty")
    adapter.check_import_cache(reg)
    return {"checkpoint_sha256": expected_sha, "identity_sha256": state["identity_sha256"],
            "counters": state["counters"], "next_episode_indices": state["next_episode_indices"],
            "schema": state["schema"], "eligibility_status": state["eligibility_status"]}


def _launch(registration_path, expected_sha256, *, worker_path, clock=time.monotonic,
            popen=subprocess.Popen, sleep=time.sleep):
    registration_path = Path(registration_path).resolve()
    data = registration_path.read_bytes()
    adapter.need(hashlib.sha256(data).hexdigest() == expected_sha256, "Registration hash changed")
    reg = json.loads(data)
    adapter.validate_registration(reg, reg["root"])
    adapter.need(Path(__file__).resolve() == Path(reg["launcher_path"]).resolve(),
                 "Launcher source path differs from registration")
    adapter.check_lease(reg)
    adapter.need(clock() < reg["absolute_deadline_monotonic"] and
                 clock() - reg["started_monotonic"] < adapter.LIMITS["total_seconds"],
                 "Parent registration expired before launch")
    adapter.need(Path(worker_path).resolve() == Path(reg["runner_path"]).resolve(),
                 "Worker path differs from registered runner")
    out = Path(reg["output"])
    out.mkdir(parents=True, exist_ok=True)
    adapter.need(not any(out.iterdir()), "Registered output directory is not fresh")
    marker = out / "launch-marker.json"
    adapter.need(Path(reg["one_use_marker_path"]).resolve() == marker.resolve(), "One-use marker path differs")
    with marker.open("x") as stream:
        json.dump({"registration_sha256": expected_sha256, "started_monotonic": clock(), "single_use": True}, stream)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    started = clock()
    reg["_signal_event"] = None
    def latch_signal(number, _frame):
        if reg["_signal_event"] is None:
            reg["_signal_event"] = {"signal": number, "monotonic": clock()}
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, latch_signal)
    cmd = [reg["interpreter"], "-B", str(Path(worker_path).resolve()), "--registration",
           str(registration_path), "--registration-sha256", expected_sha256, "--started", repr(started)]
    env = os.environ.copy()
    env["PYTHONPYCACHEPREFIX"] = ""
    env["PYTHONPATH"] = reg["runtime_root"]
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with (out / "worker.log").open("x") as log:
        proc = popen(cmd, cwd=reg["root"], env=env, start_new_session=True,
                     stdout=log, stderr=subprocess.STDOUT)
        failure = None
        try:
            while proc.poll() is None:
                elapsed = clock() - started
                parent_elapsed = clock() - reg["started_monotonic"]
                cancel = Path(reg["cancel_path"]).exists()
                lease_ok = json.loads(Path(reg["state_path"]).read_text()).get("active_long_campaign") == reg["expected_lease"]
                if reg["_signal_event"] is not None or cancel or not lease_ok or elapsed >= adapter.LIMITS["work_seconds"] \
                        or elapsed >= adapter.LIMITS["total_seconds"] \
                        or parent_elapsed >= adapter.LIMITS["total_seconds"] \
                        or clock() >= reg["absolute_deadline_monotonic"]:
                    failure = "cancelled" if cancel or reg["_signal_event"] else "lease_changed" if not lease_ok else "deadline_exhausted"
                    if group_exists(proc.pid):
                        stop_owned(proc, sleep=sleep, clock=clock)
                    break
                sleep(.1)
        except BaseException as error:
            failure = "monitor_error:" + repr(error)
            if group_exists(proc.pid):
                stop_owned(proc, sleep=sleep, clock=clock)
        raw_exit = proc.wait()
    if group_exists(proc.pid):
        failure = failure or "owned_group_survived_worker_leader"
        stop_owned(proc, sleep=sleep, clock=clock)
    group_absent = not group_exists(proc.pid)
    observation = {"worker_pid": proc.pid, "raw_exit": raw_exit,
        "directly_reaped": proc.poll() is not None, "owned_group_absent": group_absent,
        "failure": failure, "first_signal": reg["_signal_event"], "observed_monotonic": clock()}
    with (out / "worker-supervisor-observation.json").open("x") as stream:
        json.dump(observation, stream, sort_keys=True, allow_nan=False)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    check_finalization_budget(reg, started, clock)
    adapter.need(group_absent, "Owned process group remains after leader reap")
    adapter.need(failure is None, failure or "Launcher failed")
    adapter.need(raw_exit == 0, "Worker raw exit was not zero")
    adapter.validate_registration(json.loads(registration_path.read_text()), reg["root"])
    adapter.check_lease(reg)
    check_finalization_budget(reg, started, clock)
    worker = json.loads((out / "worker-result.json").read_text())
    episodes = [json.loads(line) for line in (out / "training-episodes.jsonl").read_text().splitlines()]
    episode_evidence = adapter.validate_episode_journal(episodes)
    metric_rows = [json.loads(line) for line in (out / "training-metrics.jsonl").read_text().splitlines()]
    eval_rows = [json.loads((out / f"evaluation-{u:06d}.json").read_text()) for u in adapter.EVAL_UPDATES]
    worker_for_validation = dict(worker)
    worker_for_validation.update(raw_exit=raw_exit, cancelled=worker.get("first_signal") is not None)
    evidence = adapter.validate_synthetic_iteration(metric_rows, eval_rows, worker_for_validation)
    final_checkpoint = out / "checkpoint-000080-candidate.pt"
    adapter.need(final_checkpoint.is_file() and eval_rows[-1]["checkpoint"] == final_checkpoint.name
                 and adapter.sha(final_checkpoint) == eval_rows[-1]["checkpoint_sha256"],
                 "Exact final checkpoint differs")
    for evaluation in eval_rows:
        checkpoint = out / evaluation["checkpoint"]
        adapter.need(checkpoint.is_file() and adapter.sha(checkpoint) == evaluation["checkpoint_sha256"],
                     "Evaluation checkpoint hash differs")
    adapter.need(worker["evaluated_updates"] == list(adapter.EVAL_UPDATES), "Evaluation schedule differs")
    final_checkpoint_evidence = validate_final_checkpoint(reg, final_checkpoint,
        eval_rows[-1]["checkpoint_sha256"], worker, episode_evidence)
    adapter.validate_registration(json.loads(registration_path.read_text()), reg["root"])
    adapter.check_lease(reg)
    check_finalization_budget(reg, started, clock)
    result = {"status": "completed_worker_pending_parent_terminal_acceptance",
            "worker_pid": proc.pid, "raw_exit": raw_exit, "failure": failure,
            "elapsed_seconds": clock() - started, "command": cmd,
            "owned_group_absent": group_absent, "directly_reaped": proc.poll() is not None,
            "first_signal": reg["_signal_event"],
            "worker_result": worker, "evidence": evidence,
            "episode_evidence": episode_evidence,
            "final_checkpoint_evidence": final_checkpoint_evidence,
            "final_checkpoint": final_checkpoint.name, "final_checkpoint_sha256": adapter.sha(final_checkpoint)}
    with (out / "launcher-result.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    try:
        check_finalization_budget(reg, started, clock)
    except BaseException as error:
        publication_failure = {"status": "failed", "publication_failure": repr(error),
            "launcher_result_sha256": adapter.sha(out / "launcher-result.json"),
            "observed_monotonic": clock()}
        with (out / "publication-failure.json").open("x") as stream:
            json.dump(publication_failure, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        raise
    return result


def launch(registration_path, expected_sha256, *, worker_path=None, clock=time.monotonic,
           popen=subprocess.Popen, sleep=time.sleep):
    registration_path = Path(registration_path).resolve()
    out = None
    reg = None
    try:
        if registration_path.is_file():
            reg = json.loads(registration_path.read_text())
            if isinstance(reg.get("root"), str) and isinstance(reg.get("output"), str):
                expected_out = (Path(reg["root"]) / "learning/runs/v2" / adapter.RUN_ID).resolve()
                if Path(reg["output"]).resolve() == expected_out:
                    out = expected_out
        if reg is None:
            raise ValueError("Cannot read parent registration")
        return _launch(registration_path, expected_sha256,
            worker_path=worker_path or reg["runner_path"], clock=clock, popen=popen, sleep=sleep)
    except BaseException as error:
        if out is not None and out.is_dir() and (out / "launcher-result.json").is_file():
            try:
                published = json.loads((out / "launcher-result.json").read_text())
            except BaseException:
                published = {}
            if published.get("status") == "completed_worker_pending_parent_terminal_acceptance" \
                    and not (out / "publication-failure.json").exists():
                failure = {"status": "failed", "publication_failure": repr(error),
                    "launcher_result_sha256": adapter.sha(out / "launcher-result.json"),
                    "observed_monotonic": time.monotonic()}
                with (out / "publication-failure.json").open("x") as stream:
                    json.dump(failure, stream, indent=2, sort_keys=True, allow_nan=False)
                    stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        elif out is not None and out.is_dir():
            failure = {"status": "failed", "error": repr(error),
                "worker_supervisor_observation": json.loads((out / "worker-supervisor-observation.json").read_text())
                    if (out / "worker-supervisor-observation.json").is_file() else None,
                "worker_result": json.loads((out / "worker-result.json").read_text())
                    if (out / "worker-result.json").is_file() else None,
                "registration_sha256": expected_sha256}
            with (out / "launcher-result.json").open("x") as stream:
                json.dump(failure, stream, indent=2, sort_keys=True, allow_nan=False)
                stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--registration", required=True)
    parser.add_argument("--registration-sha256", required=True)
    args = parser.parse_args()
    registration = json.loads(Path(args.registration).read_text())
    result = launch(args.registration, args.registration_sha256, worker_path=registration["runner_path"])
    print(json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    raise SystemExit(0 if result["status"] == "completed_worker_pending_parent_terminal_acceptance" else 1)
