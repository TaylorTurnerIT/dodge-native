"""Accept one completed continuation and its strongest complete candidate."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path.cwd()
OWN = Path(__file__).resolve().parent
BASE = ROOT / "learning/runs/v2"
PREP = BASE / "D2-retained300-continuation-freeze-20261026-r5"
RUN = BASE / "D2-retained300-continuation-20261026-r1"
OBSERVER = BASE / "D2-retained300-execution-observer-parent-20261026-r1"
AUDITOR = BASE / "D2-retained300-all-candidate-auditor-luna-20261026-r5"
REG_SHA = "8a60dc80f1ebe03c43bf18eebf75199e14f207b677570ac2d6d4368ddfcb0f79"


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(name, value):
    with (OWN / name).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


reg = read(PREP / "registration.json")
need(sha(PREP / "registration.json") == REG_SHA, "Registration changed")
statepath = Path(reg["state_path"])


def guard():
    raw = statepath.read_bytes()
    state = json.loads(raw)
    need(state["active_long_campaign"] == reg["expected_lease"], "Exact lease changed")
    need(all(state.get(k) is None for k in ("active_inference_diagnostic", "active_inference_campaign", "active_inference_lease")), "Another hardware lease exists")
    need(not Path(reg["cancel_path"]).exists() and state.get("cancel_requested") in (None, False), "Cancellation present")
    for path, digest in reg["pins"].items():
        need(sha(path) == digest, "Pinned input changed: " + path)
    return state, raw


state, _ = guard()
full = read(AUDITOR / "full-audit.json")
obs = read(OBSERVER / "observation.json")
worker = read(RUN / "worker-result.json")
execution = read(RUN / "execution-result.json")
need(full["mode"] == "full_parent_only" and full["audit"]["updates_audited"] == [300, 312, 324, 336, 348, 360], "Full audit candidate set differs")
need(full["registration"]["sha256"] == REG_SHA and full["registration"]["pins_checked_before_and_after"] == 13827, "Full audit identity differs")
need(obs["success_authoritative"] is True and obs["first_event"] is None, "Observer failed")
need(obs["launch_count"] == execution["actual_worker_launch_count"] == 1 and obs["outer_raw_exit"] == obs["worker_raw_exit"] == 0, "Launch count or raw exits differ")
need(execution["status"] == "passed" and worker["status"] == "completed" and worker["first_failure"] is None, "Terminal status differs")
need(execution["directly_reaped"] and execution["owned_group_absent"] and all(obs[k] for k in ("outer_process_absent", "worker_process_absent", "worker_group_absent")), "Reaping or process absence failed")
need(obs["outer_inclusive_wall_seconds"] <= 1800 and worker["elapsed_seconds"] <= 1790, "Wall cap failed")
need(obs["max_aggregate_rss_bytes"] <= 6442450944 and worker["peak_mps_driver_bytes"] <= 6442450944, "Memory cap failed")
need(worker["counters"]["updates"] == 60 and worker["counters"]["environment_decisions"] == 983040 and worker["counters"]["optimizer_steps"] <= 7680, "Completed counters differ")
absence = {}
for pid in (obs["observer_pid"], obs["outer_pid"], execution["worker_pid"]):
    result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "pid=,pgid=,lstart=,command="], capture_output=True, text=True)
    need(result.returncode == 1 and not result.stdout.strip(), "Owned process remains: " + str(pid))
    absence[str(pid)] = {"returncode": result.returncode, "stdout": result.stdout}
for pgid in {obs["outer_process_group"], execution["owned_pgid"]}:
    need(type(pgid) is int and pgid > 1, "Unproven owned process group")
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        pass
    else:
        raise ValueError("Owned group remains: " + str(pgid))

candidates = full["audit"]["candidates"]
best = max(candidates, key=lambda k: (candidates[k]["mean_alive_frames"], -int(k)))
selected_update = int(best)
need(selected_update == full["audit"]["proposed_best_update"] == 324, "Selected candidate differs")
previous_receipt = read(reg["parent"]["terminal_receipt_path"])
previous_mean = previous_receipt["performance"]["mean_alive_frames"]
need(candidates[best]["mean_alive_frames"] > previous_mean, "No best replacement")
checkpoint = RUN / f"checkpoint-{selected_update:06d}-candidate.pt"
need(sha(checkpoint) == candidates[best]["checkpoint_sha256"], "Selected checkpoint digest differs")
sys.path.insert(0, str(PREP))
import runner
sys.path.insert(0, reg["runtime_root"])
import torch
torch.set_num_threads(2)
from dodge_rl.checkpoints import load_checkpoint
selected = load_checkpoint(checkpoint, expected_sha256=sha(checkpoint))
local = selected_update - runner.PHASE_START
need(selected["phase_update"] == selected_update and selected["local_update"] == local == 24 and selected["update_progress"]["complete"], "Selected update incomplete")
need(selected["cumulative_counters"]["updates"] == 372 and selected["counters"]["optimizer_steps"] == 3072, "Selected ancestry differs")
runner.assert_saved_optimizer_lr(selected, 3e-5)
certificate = RUN / f"development-{selected_update:06d}.json"
cert = read(certificate)
rows = cert["evaluation"]["rows"]
alive = sorted(row["alive_frames"] for row in rows)
need(len(alive) == 64 and sum(alive) / 64 == 2939.40625, "Selected performance differs")
performance = {"update": selected_update, "q1_bottom16_mean": sum(alive[:16]) / 16,
               "q4_top16_mean": sum(alive[-16:]) / 16, "mean_alive_frames": sum(alive) / 64,
               "mean_score": cert["evaluation"]["mean_score"], "episodes": 64,
               "deaths": cert["evaluation"]["deaths"], "caps": cert["evaluation"]["caps"],
               "death_causes": dict(Counter(row["death_cause"] for row in rows if row["terminated"])),
               "checkpoint_sha256": sha(checkpoint), "certificate_sha256": sha(certificate)}
outer = obs["outer_inclusive_wall_seconds"]
cost_before = runner.COMPLETED_CAMPAIGN_COST_BASELINE_SECONDS
cost = cost_before + outer
future = selected["cumulative_selected_checkpoint_trajectory_wall_seconds"]
now = datetime.now(timezone.utc).isoformat()
competence = performance["mean_alive_frames"] >= 3060
audit = {"schema": "d2_same_lr_parent_terminal_audit_v1", "status": "accepted_completed_iteration_and_selected_intermediate324",
         "at_utc": now, "registration_sha256": REG_SHA, "source_pins_unchanged": 13827,
         "full_audit_path": str(AUDITOR / "full-audit.json"), "full_audit_sha256": sha(AUDITOR / "full-audit.json"),
         "observer_sha256": sha(OBSERVER / "observation.json"), "all_six_candidates_audited": True,
         "selected_update": selected_update, "selected_performance": performance,
         "raw_exits": {"outer": 0, "worker": 0}, "observed_outer_seconds": outer,
         "process_absence": absence, "owned_groups_absent": True, "raw_counters": worker["counters"],
         "selected_counters": selected["counters"], "selected_cumulative_counters": selected["cumulative_counters"],
         "resource_limits_passed": True, "UTC_annotation": "Recorded monotonic elapsed governs budgets; UTC/ps wall jumps are not elapsed runtime.",
         "provider_failure_annotation": "Initial executor agent failed with provider high demand. Original observer/launcher/worker continued once; attach-only monitor observed completion. No campaign retry."}
write("audit.json", audit)
completed = {"schema": "d2_completed_iteration_parent_audit_receipt_v1", "status": "accepted_completed_training_iteration_with_best_replacement",
             "at_utc": now, "run_id": reg["run_id"], "phase": "D2", "normal_training_iteration": True,
             "completed_local_updates": 60, "completed_phase_updates": 360, "counters": worker["counters"],
             "cumulative_counters": worker["cumulative_counters"], "endpoint_checkpoint_sha256": candidates["360"]["checkpoint_sha256"],
             "best_replacement": True, "selected_phase_update": selected_update, "training_continuation_eligible": False,
             "stage_promotion_eligible": False, "competence_passed": competence, "checkpoint_metadata_unchanged": True,
             "raw_exits": {"outer": 0, "worker": 0}, "owned_processes_and_groups_absent": True,
             "registration_path": str(PREP / "registration.json"), "registration_sha256": REG_SHA,
             "audit_path": str(OWN / "audit.json"), "audit_sha256": sha(OWN / "audit.json"),
             "full_audit_sha256": sha(AUDITOR / "full-audit.json"),
             "authority": "Completed iteration/resource-cost accounting only. Separate selected324 receipt grants continuation; endpoint360 is not retained.",
             "wall_accounting": {"completed_campaign_resource_cost_before_seconds": cost_before,
                                 "completed_campaign_resource_cost_after_seconds": cost, "observed_outer_seconds": outer,
                                 "selected_checkpoint_future_baseline_seconds": future,
                                 "completed_discarded_branch_end_highwater_seconds": runner.SELECTED_TRAJECTORY_BASELINE_SECONDS + outer,
                                 "semantics": "Later36 discarded updates add resource cost, not selected model/Adam/RNG/counter ancestry."}}
write("completed-iteration-receipt.json", completed)
fingerprints = {key: runner.fingerprint(selected[field]) for key, field in (("model", "model"), ("optimizer", "optimizer"), ("rng", "rng"))}
receipt = {"schema": "d2_retained_best_candidate_parent_receipt_v1", "status": "accepted_complete_candidate_from_completed_normal_training_iteration",
           "at_utc": now, "run_id": reg["run_id"], "phase": "D2", "checkpoint_path": str(checkpoint),
           "checkpoint_sha256": sha(checkpoint), "continuation_parent_checkpoint_sha256": sha(checkpoint),
           "checkpoint_sidecar_sha256": sha(Path(str(checkpoint) + ".json")), "checkpoint_metadata_unchanged": True,
           "candidate_phase_update": selected_update, "candidate_local_update": local,
           "candidate_counters": selected["counters"], "candidate_cumulative_counters": selected["cumulative_counters"],
           "counters": selected["counters"], "cumulative_counters": selected["cumulative_counters"],
           "inherited_counters": selected["inherited_counters"], "next_episode_indices": selected["next_episode_indices"],
           "learner_fingerprints": fingerprints, "identity_sha256": selected["identity_sha256"],
           "config_sha256": selected["config_sha256"], "runtime_sha256": selected["runtime_sha256"],
           "native_sha256": selected["native_sha256"], "policy_sha256": selected["policy_sha256"],
           "parent_registration_sha256": reg["parent"]["registration_sha256"],
           "candidate_parent_checkpoint_sha256": reg["parent"]["sha256"], "parent_checkpoint_sha256": reg["parent"]["sha256"],
           "previous_retained_checkpoint_sha256": reg["parent"]["sha256"],
           "parent_terminal_receipt_path": reg["parent"]["terminal_receipt_path"],
           "parent_terminal_receipt_sha256": reg["parent"]["terminal_receipt_sha256"],
           "completed_iteration_local_updates": 60, "completed_iteration_phase_update_end": 360,
           "completed_iteration_receipt_path": str(OWN / "completed-iteration-receipt.json"),
           "completed_iteration_receipt_sha256": sha(OWN / "completed-iteration-receipt.json"),
           "registration_path": str(PREP / "registration.json"), "registration_sha256": REG_SHA,
           "evaluation_path": str(certificate), "evaluation_sha256": sha(certificate),
           "evaluation_jsonl_path": str(RUN / f"development-{selected_update:06d}.jsonl"),
           "evaluation_jsonl_sha256": sha(RUN / f"development-{selected_update:06d}.jsonl"),
           "audit_path": str(OWN / "audit.json"), "audit_sha256": sha(OWN / "audit.json"),
           "performance": performance, "selection_rule": "Highest independently audited mean survival on same64 D2 development seeds; ties keep earlier incumbent.",
           "effective_learning_rate": 3e-5, "competence_passed": competence, "stage_promotion_eligible": False,
           "training_continuation_eligible": True,
           "authority_scope": "Exact selected324 complete-update candidate may parent a NEW registered D2 continuation. Model/Adam/RNG and counters stop atlocal24. Later36 discarded updates add resource cost only. No D3/student/B/E/qualification authority.",
           "wall_accounting": {"definition": "Selected point clock and total completed campaign resource cost remain distinct.",
                               "future_checkpoint_trajectory_baseline_seconds": future,
                               "selected_checkpoint_reported_cumulative_D2_wall_seconds": future,
                               "selected_checkpoint_reported_current_iteration_wall_seconds": selected["current_iteration_observed_outer_seconds"],
                               "selected_checkpoint_reported_trajectory_wall_seconds": future,
                               "selected_checkpoint_reported_iteration_wall_seconds": selected["current_iteration_observed_outer_seconds"],
                               "successful_ancestor_and_completed_campaign_cost_seconds": cost,
                               "whole_completed_iteration_observed_outer_seconds": outer,
                               "continuation_deadline_origin": "Fresh next launcher monotonic T0; accounting baselines are not deadline origins."}}
write("retained-best-candidate-receipt.json", receipt)
write("retained-best-decision.json", {"selection": "retained_best_integrity_accepted_checkpoint", "phase_update": selected_update,
      "checkpoint_path": str(checkpoint), "checkpoint_sha256": sha(checkpoint),
      "receipt_path": str(OWN / "retained-best-candidate-receipt.json"), "receipt_sha256": sha(OWN / "retained-best-candidate-receipt.json"),
      "previous_mean": previous_mean, "new_mean": performance["mean_alive_frames"], "endpoint360_not_selected": True,
      "future_branch_baseline_seconds": future, "completed_campaign_cost_seconds": cost})
report = ["# Retained324 accepted", "", "All60 updates and six candidates passed independent terminal audit. Selected324 improves the same64-game development mean8.69%; endpoint360 is discarded. No qualification claim.", "",
          "| Candidate | Q1 frames | Q4 frames | Mean frames |", "| --- | ---: | ---: | ---: |"]
for key, candidate in candidates.items():
    p = candidate["performance"]["alive_frames"]
    report.append(f"| {key} | {p['Q1']} | {p['Q4']} | {p['mean']} |")
report += ["", "Selected deaths:35 normal enemies,14 static rectangles,9 kamikazes,3 moving rectangles,3 explosions. All64 died; no caps.", "",
           f"Observed monotonic outer duration: {outer}s. Total completed resource cost: {cost}s. Selected324 future trajectory baseline: {future}s. Later36 discarded updates are not learner ancestry."]
with (OWN / "report.md").open("x") as stream:
    stream.write("\n".join(report) + "\n")

state, state_before = guard()
write("state-before-lease-clear.json", state)
state["active_long_campaign"] = None
state["last_update_at_utc"] = now
relative_receipt = str((OWN / "retained-best-candidate-receipt.json").relative_to(ROOT))
receipt_sha = sha(OWN / "retained-best-candidate-receipt.json")
state["postcritic_training_work"].update(active_campaign=None, status="accepted_sameLR_iteration;retained324_selected;endpoint360_discarded",
      latest_parent_terminal_receipt=relative_receipt, latest_parent_terminal_receipt_sha256=receipt_sha,
      latest_completed_iteration_receipt=str((OWN / "completed-iteration-receipt.json").relative_to(ROOT)),
      latest_completed_iteration_receipt_sha256=sha(OWN / "completed-iteration-receipt.json"),
      completed_campaign_resource_cost_seconds=cost, cumulative_D2_inclusive_wall_seconds=future,
      latest_performance=performance,
      best_observed_current_lineage_reference={"phase_update": selected_update, "run_id": reg["run_id"], "checkpoint_sha256": sha(checkpoint),
          "parent_terminal_receipt": relative_receipt, "parent_terminal_receipt_sha256": receipt_sha,
          "Q1_bottom16_mean": performance["q1_bottom16_mean"], "Q4_top16_mean": performance["q4_top16_mean"], "mean_alive_frames": performance["mean_alive_frames"]})
state["training_parent_selection_policy"].update(current_parent_phase_update=selected_update, current_parent_sha256=sha(checkpoint),
      current_parent_receipt=relative_receipt, current_parent_receipt_sha256=receipt_sha, parent_receipt_schema=receipt["schema"])
state["tasks"]["retained300_existing_run_monitor_luna_20261026_r1"].update(status="completed", workState="result_available", result_ingested=True,
      ingested_at_utc=now, actual_outcome="accepted_completed_iteration_selected324", parent_terminal_audit=str((OWN / "audit.json").relative_to(ROOT)), lease_cleared_at_utc=now)
state["tasks"]["retained300_continuation_execution_luna_20261026_r1"].update(actual_outcome="campaign_completed_and_accepted_despite_executor_provider_failure;selected324", parent_terminal_audit=str((OWN / "audit.json").relative_to(ROOT)))
state["parallel_acceleration_work"].update(status="SameLRcontinuation accepted;retained324mean2939.40625;endpoint360discarded",
      current_training_monitor_task_key=None, retained300_campaign_status="accepted_completed", canonical_report=str((OWN / "report.md").relative_to(ROOT)),
      retained300_terminal_audit=str((OWN / "audit.json").relative_to(ROOT)), retained300_matching_lease_cleared=True)
state["next_actions"] = ["Prepare next sameLR3e-5 continuation from exact accepted324 model/Adam/RNG and cumulative372;never endpoint360.",
                         "Review new parent receipt and freeze next run registration before one new bounded launch.",
                         "Preserve all frozen evidence and failed executor provider result;no retries of completed campaign."]
need(statepath.read_bytes() == state_before, "Concurrent ledger change before publication")
with tempfile.NamedTemporaryFile("w", dir=statepath.parent, prefix=".accepted324-", delete=False) as stream:
    json.dump(state, stream, indent=2, sort_keys=True, allow_nan=False)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
    temporary = stream.name
need(statepath.read_bytes() == state_before, "Concurrent ledger change before replace")
os.replace(temporary, statepath)
write("state-after-lease-clear.json", state)
print(json.dumps({"status": audit["status"], "selected_update": selected_update,
      "checkpoint_sha256": sha(checkpoint), "receipt_sha256": receipt_sha, "performance": performance,
      "future_trajectory_baseline_seconds": future, "completed_resource_cost_seconds": cost,
      "matching_lease_cleared": True}))
