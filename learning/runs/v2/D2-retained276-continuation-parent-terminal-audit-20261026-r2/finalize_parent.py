"""Accept the completed iteration while retaining the exact earlier best276."""
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

OWN = Path(__file__).resolve().parent
ROOT = OWN.parents[3]
STATE = ROOT / "learning/runs/v2-orchestration/state.json"
RUN = ROOT / "learning/runs/v2/D2-retained276-continuation-20261026-r2"
OBS = ROOT / "learning/runs/v2/D2-retained276-continuation-execution-observer-luna-20261026-r2"
REG = ROOT / "learning/runs/v2/D2-retained276-continuation-prepare-luna-20261026-r2/registration.json"
REG_SHA = "477217f3c7617ccbe01c651db8932eab01f54ea3924f213e67b413e640cf866c"
PARENT_SHA = "0b5cf72b4eb9629fa4f10ce2cecb3625b56f8787c0eca6395b9fe17161e6b292"
PARENT_RECEIPT_SHA = "d64d0f803d02a8d2c33da9fa0ba862f06ba7d9c56dcf4f0494e559a49e48fcc4"
UPDATES = [276, 288, 300, 312, 324, 336, 348]

def read(path):
    return json.loads(Path(path).read_text())

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()

def save(name, value):
    with (OWN / name).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")

def main():
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    reg, full = read(REG), read(OWN / "full-audit.json")
    audit = full["audit"]
    observation, execution, worker = read(OBS / "observation.json"), read(RUN / "execution-result.json"), read(RUN / "worker-result.json")
    state = read(STATE)
    assert sha(REG) == REG_SHA and full["registration"]["sha256"] == REG_SHA
    assert full["mode"] == "full_parent_only" and audit["status"] == "all_candidates_audited_pending_parent_terminal_acceptance"
    assert audit["updates_audited"] == UPDATES and audit["proposed_best_update"] is None
    assert audit["baseline_mean_alive_frames"] == 2483.65625 and audit["effective_lr"] == 0.0001
    assert full["registration"]["pins_checked_before_and_after"] == audit["pins_checked_before_and_after"] == 13787
    assert observation["outer_raw_exit"] == observation["worker_raw_exit"] == 0
    assert observation["success_authoritative"] and observation["first_event"] is None
    assert execution["status"] == "passed" and execution["actual_worker_launch_count"] == 1
    assert execution["observed_worker_raw_exit"] == 0 and execution["directly_reaped"] and execution["owned_group_absent"]
    assert execution["postflight_inputs_unchanged"] and execution["first_observed_failure"] is None
    assert worker["status"] == "completed" and worker["updates"] == 72
    assert worker["counters"] == {"updates": 72, "optimizer_steps": 9216,
                                   "environment_decisions": 1179648, "raw_frames": 4714511}
    assert worker["cumulative_counters"] == {"updates": 396, "optimizer_steps": 49568,
                                              "environment_decisions": 6488064, "raw_frames": 25917040}
    assert full["terminal_gates"]["owned_processes_absent"]
    assert 0 < observation["outer_inclusive_wall_seconds"] < 1800
    assert 0 < worker["work_elapsed_seconds"] < 1790
    assert all(0 < value < 6442450944 for value in
               (observation["max_aggregate_rss_bytes"], worker["peak_rss_bytes"], worker["peak_mps_driver_bytes"]))
    assert state["active_long_campaign"] == reg["expected_lease"] and state["active_inference_diagnostic"] is None
    assert state.get("cancel_requested") in (None, False)
    policy_before = dict(state["training_parent_selection_policy"])
    assert policy_before["current_parent_sha256"] == PARENT_SHA
    assert policy_before["current_parent_receipt_sha256"] == PARENT_RECEIPT_SHA
    assert sha(reg["parent"]["path"]) == PARENT_SHA
    assert sha(reg["parent"]["terminal_receipt_path"]) == PARENT_RECEIPT_SHA
    for path, expected in reg["pins"].items():
        assert sha(path) == expected, path
    for path, expected in audit["tracked_file_sha256"].items():
        assert sha(path) == expected, path
    assert not any(Path(reg["import_policy"]["pycache_prefix"]).iterdir())
    assert not (RUN / "publication-failure.json").exists()
    assert not (OBS / "observer-error.json").exists()
    launch, worker_launch = read(OBS / "launch.json"), read(RUN / "worker-launch.json")
    process_rows = subprocess.run(["/bin/ps", "-axo", "pid=,pgid=,comm="], check=True,
                                  capture_output=True, text=True).stdout
    (OWN / "process-postflight.txt").write_text(process_rows)
    owned = {launch["observer_pid"], launch["outer_pid"], worker_launch["worker_pid"]}
    groups = {worker_launch["owned_pgid"]}
    for line in process_rows.splitlines():
        fields = line.split(None, 2)
        if len(fields) >= 2:
            assert int(fields[0]) not in owned and int(fields[1]) not in groups, line
    performance = {}
    for update in UPDATES:
        certificate = read(RUN / f"development-{update:06d}.json")
        evaluation = certificate["evaluation"]
        rows = sorted(evaluation["rows"], key=lambda row: (row["alive_frames"], row["seed"]))
        assert len(rows) == 64 and evaluation["deaths"] == 64 and evaluation["caps"] == 0
        values = [row["alive_frames"] for row in rows]
        calculated = {"Q1": math.fsum(values[:16]) / 16, "Q4": math.fsum(values[-16:]) / 16,
                      "mean": math.fsum(values) / 64}
        assert calculated == certificate["performance"]["alive_frames"]
        assert calculated["mean"] == audit["candidates"][str(update)]["mean_alive_frames"]
        performance[str(update)] = dict(calculated, death_causes=evaluation["death_causes"],
                                        checkpoint_sha256=certificate["checkpoint_sha256"])
    assert all(performance[str(update)]["mean"] < 2483.65625 for update in UPDATES[1:])
    wall = {"observed_outer_seconds": observation["outer_inclusive_wall_seconds"],
            "retained_parent_checkpoint_reported_point_seconds": 4740.377017625088,
            "retained_parent_future_branch_high_water_seconds": 4760.062404125177,
            "completed_campaign_resource_cost_before_seconds": 5537.773026792208,
            "completed_campaign_resource_cost_after_seconds": 5537.773026792208 + observation["outer_inclusive_wall_seconds"],
            "completed_branch_not_selected_high_water_seconds": 4760.062404125177 + observation["outer_inclusive_wall_seconds"],
            "semantics": "Retained learner stays276. Discarded branch adds full outer cost only to resource accounting. Parent audit CPU time is separate."}
    save("state-before-closeout.json", state)
    result = {"schema": "d2_completed_iteration_no_best_replacement_parent_audit_v1", "status": "passed",
              "at_utc": now, "run_id": reg["run_id"], "registration_sha256": REG_SHA,
              "full_audit_sha256": sha(OWN / "full-audit.json"), "actual_launch_count": 1,
              "updates_completed": 72, "all_seven_candidates_independently_audited": True,
              "source_pins_verified_after_audit": 13787, "owned_processes_and_groups_absent": True,
              "raw_exits": {"outer": 0, "worker": 0}, "worker_counters": worker["counters"],
              "cumulative_counters": worker["cumulative_counters"], "performance": performance,
              "retained_phase_update": 276, "retained_checkpoint_sha256": PARENT_SHA,
              "retained_receipt_sha256": PARENT_RECEIPT_SHA, "retained_policy_unchanged": True,
              "best_replaced": False, "competence_passed": False, "wall_accounting": wall,
              "resources": full["terminal_gates"], "provider_turn_failed_independently_of_OS_run": True}
    save("audit.json", result)
    receipt = {"schema": "d2_completed_iteration_parent_audit_receipt_v1",
               "status": "accepted_completed_training_iteration_no_best_replacement", "at_utc": now,
               "run_id": reg["run_id"], "phase": "D2", "completed_phase_updates": 348,
               "completed_local_updates": 72, "registration_path": str(REG), "registration_sha256": REG_SHA,
               "audit_path": str(OWN / "audit.json"), "audit_sha256": sha(OWN / "audit.json"),
               "full_audit_sha256": sha(OWN / "full-audit.json"),
               "endpoint_checkpoint_sha256": performance["348"]["checkpoint_sha256"],
               "counters": worker["counters"], "cumulative_counters": worker["cumulative_counters"],
               "raw_exits": {"outer": 0, "worker": 0}, "owned_processes_and_groups_absent": True,
               "retained_parent_policy": policy_before, "wall_accounting": wall,
               "checkpoint_metadata_unchanged": True, "best_replacement": False,
               "training_continuation_eligible": False, "stage_promotion_eligible": False,
               "competence_passed": False,
               "authority": "Completed iteration and resource-cost accounting only. Existing retained276 receipt remains the sole model-continuation authority."}
    save("completed-iteration-receipt.json", receipt)
    receipt_path = str((OWN / "completed-iteration-receipt.json").relative_to(ROOT))
    receipt_sha = sha(OWN / "completed-iteration-receipt.json")
    save("retained-best-decision.json", {"selection": "retain_exact_parent276", "prior_and_current_policy": policy_before,
                                         "reason": "None of six new audited candidates improves the retained mean2483.65625.",
                                         "retained_branch_seconds": 4760.062404125177,
                                         "completed_resource_cost_seconds": wall["completed_campaign_resource_cost_after_seconds"]})
    ingested = read(OWN / "task-result-ingestion.json")
    for key, name in (("retained276_continuation_execution_luna_20261026_r2", "execution"),
                      ("retained276_terminal_planner_luna_20261026_r1", "planner"),
                      ("calibration_r5_lifecycle_repair_luna_20261026_r1", "calibration_r5")):
        record = state["tasks"][key]
        assert not record["result_ingested"]
        terminal = ingested[name]
        record.update(status=terminal["status"], workState=terminal["workState"], result_ingested=True,
                      ingested_at_utc=now, provider_error=terminal["summary"])
    state["tasks"]["retained276_continuation_execution_luna_20261026_r2"].update(
        actual_campaign_outcome=receipt["status"], parent_audit=str((OWN / "audit.json").relative_to(ROOT)),
        lease_cleared_at_utc=now, actual_campaign_launch_count=1)
    state["tasks"]["retained276_terminal_planner_luna_20261026_r1"]["preserved_artifact_scope"] = "Prepared proposal-only files exist; provider failure does not grant parent acceptance; unused in this closeout."
    state["tasks"]["calibration_r5_lifecycle_repair_luna_20261026_r1"]["preserved_artifact_scope"] = "Frozen R5 files and13-test log exist; late missing-CLI finding persists; R6 successor repairs."
    late = ingested["late_calibration_review"]
    late_key = "calibration_r4_frozen_review_haiku_limit_resume_20261026_r1"
    assert late_key not in state["tasks"]
    state["tasks"][late_key] = {"task_id": late["taskId"], "status": late["status"],
        "workState": late["workState"], "result_ingested": True, "ingested_at_utc": now,
        "summary": late["summary"], "scope": "Late automatic resume of original rate-limited source review; additional missing-CLI finding sent to R6 successor."}
    for key, name, directory, budget in (
            ("retained276_348_plateau_diagnosis_haiku_20261026_r1", "diagnosis_task", "D2-retained276-348-plateau-diagnosis-haiku-20261026-r1", 420),
            ("calibration_r6_cli_completion_luna_20261026_r1", "calibration_r6_task", "current-pair-resource-calibration-prepare-luna-20261026-r6", 900)):
        task = ingested[name]
        assert key not in state["tasks"]
        state["tasks"][key] = {"task_id": task["taskId"], "model": task["model"],
            "provider_instance_id": task["providerInstanceId"], "status": task["status"], "workState": task["workState"],
            "result_ingested": False, "registered_at_utc": now, "planned_budget_seconds": budget,
            "owned": "learning/runs/v2/" + directory, "scope": "Bounded read-only diagnosis or CPU-only preparation; no actual campaign/state/lease writes."}
    endpoint = performance["348"]
    latest = {"phase_update": 348, "run_id": reg["run_id"], "checkpoint_sha256": endpoint["checkpoint_sha256"],
              "Q1_bottom16_mean": endpoint["Q1"], "Q4_top16_mean": endpoint["Q4"], "mean_alive_frames": endpoint["mean"],
              "completed_iteration_receipt": receipt_path, "completed_iteration_receipt_sha256": receipt_sha,
              "training_parent_selected": False}
    work = state["postcritic_training_work"]
    work.update(status="completed_276to348_iteration_parent_accepted_no_best_replacement", active_campaign=None,
        latest_completed_phase_updates=348, latest_completed_cumulative_updates=396,
        latest_completed_endpoint_performance=endpoint,
        latest_completed_iteration_receipt=receipt_path, latest_completed_iteration_receipt_sha256=receipt_sha,
        latest_parent_terminal_audit=str((OWN / "audit.json").relative_to(ROOT)),
        latest_run_id=reg["run_id"], latest_registration=str(REG.relative_to(ROOT)), latest_registration_sha256=REG_SHA,
        latest_source_directory=str(REG.parent.relative_to(ROOT)),
        cumulative_D2_inclusive_wall_seconds=4760.062404125177,
        completed_campaign_resource_cost_seconds=wall["completed_campaign_resource_cost_after_seconds"],
        resource_cost_anchor=receipt_path, resource_cost_anchor_sha256=receipt_sha, lease_cleared_at_utc=now)
    state["performance_reporting_policy"].update(latest=latest,
        current_cohort=str((OWN / "audit.json").relative_to(ROOT)),
        current_death_causes=str((RUN / "development-000348.jsonl").relative_to(ROOT)),
        death_attribution="Audited endpoint348; retainedbest276 shown separately;64fixedD2developmentgames.")
    assert state["training_parent_selection_policy"] == policy_before
    state["completed_long_campaigns"].append({"run_id": reg["run_id"], "status": receipt["status"],
        "audit": str((OWN / "audit.json").relative_to(ROOT)), "retained_phase_update": 276,
        "wall_seconds": observation["outer_inclusive_wall_seconds"]})
    state["parallel_acceleration_work"].update(status="276to348_completed_audited_retained276;Haiku_plateau_diagnosis_and_Luna_calibrationR6_active",
        canonical_report=str((OWN / "report.md").relative_to(ROOT)),
        current_training_task_key=None, current_eval_implementation_task_key="calibration_r6_cli_completion_luna_20261026_r1",
        current_design_task_key="retained276_348_plateau_diagnosis_haiku_20261026_r1")
    state["next_actions"] = ["Reconcile completed-run PPO diagnosis and prepare one supported bounded experiment from unchanged retained276 model/Adam/RNG.",
        "Continue calibrationR6 CPU repair; fresh frozen review before any actual resource probe.",
        "Future preparation must bind retained276 authority and separately account cumulative completed resource cost7118.78208862512; no automatic endpoint348 continuation."]
    state["active_long_campaign"] = None
    state["last_update_at_utc"] = now
    # Re-read authority immediately before the sole atomic ledger mutation.
    current = read(STATE)
    assert current["active_long_campaign"] == reg["expected_lease"]
    assert current["training_parent_selection_policy"] == policy_before
    assert current.get("cancel_requested") in (None, False)
    temporary = STATE.with_name("state.retained276-completed-closeout.tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temporary, STATE)
    save("state-after-closeout.json", state)
    print(json.dumps({"status": receipt["status"], "retained_phase": 276,
                      "endpoint": endpoint, "completed_resource_cost_seconds": wall["completed_campaign_resource_cost_after_seconds"],
                      "receipt_sha256": receipt_sha}))

if __name__ == "__main__":
    main()
