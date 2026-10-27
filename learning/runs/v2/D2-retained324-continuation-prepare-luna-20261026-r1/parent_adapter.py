"""Validate exact externally accepted selected324 state and separate cost anchor."""
from __future__ import annotations
from collections.abc import Mapping
RECEIPT_SHA = "76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08"
CHECKPOINT_SHA = "c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc"
CHECKPOINT_METADATA_SHA = "cedb20704c9a7c0ec9126c6e7da2f75e230d6acdaa1b7b47f25256ed4f1fd939"
COST_RECEIPT_SHA = "7c6f250b5c5aa9e4098603cc8772c532a713e65f478cbda6ebfdd3941692fc9b"
CONFIG_SHA = "1c24df3eea150160451ada08e9f6844cd67645abf5fb8b712afd14abca930ce8"
SCHEMA = "d2_retained_best_candidate_parent_receipt_v1"
STATUS = "accepted_complete_candidate_from_completed_normal_training_iteration"
COST_SCHEMA = "d2_completed_iteration_parent_audit_receipt_v1"
COST_STATUS = "accepted_completed_training_iteration_with_best_replacement"
PARENT_OF_RUN_SHA = "e2c8fbe44e23da910686954e90cb7841b38b6d7f60f69ca657a4a69b14214710"
def need(ok, message):
    if not ok: raise ValueError(message)
def validate_parent(state: Mapping, checkpoint_sha: str, receipt: Mapping, receipt_sha: str, fingerprint,
                    checkpoint_metadata: Mapping, checkpoint_metadata_sha: str, cost_anchor: Mapping, cost_anchor_sha: str):
    need(checkpoint_sha == CHECKPOINT_SHA and receipt_sha == RECEIPT_SHA, "Parent byte pins differ")
    need(receipt.get("schema") == SCHEMA and receipt.get("status") == STATUS, "Selected candidate receipt authority differs")
    need(receipt.get("training_continuation_eligible") is True and receipt.get("stage_promotion_eligible") is False
         and receipt.get("competence_passed") is False and receipt.get("checkpoint_metadata_unchanged") is True,
         "External receipt does not grant exact D2 continuation authority")
    need(receipt.get("checkpoint_sha256") == CHECKPOINT_SHA and receipt.get("config_sha256") == CONFIG_SHA,
         "Selected checkpoint/config pin differs")
    need(checkpoint_metadata_sha == CHECKPOINT_METADATA_SHA and checkpoint_metadata == {
        "checkpoint_sha256": CHECKPOINT_SHA, "eligibility_status": "provisional_pending_parent_terminal_receipt",
        "promoted": False, "training_eligible": False}, "Checkpoint metadata changed or became eligible")
    need((receipt.get("candidate_phase_update"), receipt.get("candidate_local_update")) == (324, 24), "Selected point is not local24/update324")
    pairs = {"counters":"candidate_counters", "cumulative_counters":"candidate_cumulative_counters", "inherited_counters":"inherited_counters",
             "next_episode_indices":"next_episode_indices", "identity_sha256":"identity_sha256", "config_sha256":"config_sha256",
             "runtime_sha256":"runtime_sha256", "native_sha256":"native_sha256", "policy_sha256":"policy_sha256", "registration_sha256":"registration_sha256"}
    for a,b in pairs.items(): need(state.get(a) == receipt.get(b), "Checkpoint differs from selected receipt: " + a)
    need((state.get("phase"),state.get("phase_update"),state.get("local_update")) == ("D2",324,24), "Checkpoint counters identify another point")
    need(state.get("tag")=="candidate" and state.get("training_eligible") is False and state.get("promoted") is False
         and state.get("eligibility_status")=="provisional_pending_parent_terminal_receipt", "Saved state is not provisional and ineligible")
    progress=state.get("update_progress",{})
    need(progress.get("complete") is True and progress.get("in_update") is False and progress.get("completed_updates")==24, "Selected update is incomplete")
    need(state.get("parent_checkpoint_sha256")==PARENT_OF_RUN_SHA and receipt.get("candidate_parent_checkpoint_sha256")==PARENT_OF_RUN_SHA,
         "Parent-of-run lineage differs")
    wall=receipt["wall_accounting"]
    need(state.get("cumulative_selected_checkpoint_trajectory_wall_seconds")==wall["future_checkpoint_trajectory_baseline_seconds"], "Selected trajectory clock differs")
    need(state.get("current_iteration_observed_outer_seconds")==wall["selected_checkpoint_reported_current_iteration_wall_seconds"], "Selected iteration clock differs")
    validate_cost_anchor(cost_anchor,cost_anchor_sha)
    before=cost_anchor["wall_accounting"]["completed_campaign_resource_cost_before_seconds"]
    need(state.get("parent_completed_campaign_cost_baseline_seconds")==before
         and state.get("cumulative_successful_ancestor_and_completed_campaign_cost_seconds")==before+state["current_iteration_observed_outer_seconds"],
         "Selected campaign cost baseline differs")
    need(fingerprint(state["model"])==receipt["learner_fingerprints"]["model"] and fingerprint(state["optimizer"])==receipt["learner_fingerprints"]["optimizer"]
         and fingerprint(state["rng"])==receipt["learner_fingerprints"]["rng"], "Model, Adam, or RNG fingerprint differs")
    groups=state["optimizer"]["param_groups"]
    need(groups and all(g.get("lr")==3e-5 for g in groups) and all(g.get("eps")==1e-5 for g in groups), "Restored optimizer parameters differ")
    return state
def validate_cost_anchor(anchor: Mapping, anchor_sha: str, fingerprint=None):
    need(anchor_sha==COST_RECEIPT_SHA and anchor.get("schema")==COST_SCHEMA, "Completed-iteration receipt pin/schema differs")
    need(anchor.get("status")==COST_STATUS, "Completed cost receipt status differs")
    wall=anchor["wall_accounting"]
    need(wall.get("completed_campaign_resource_cost_after_seconds")==9758.365427209174
         and wall.get("completed_campaign_resource_cost_before_seconds")==8621.338345875141
         and wall.get("selected_checkpoint_future_baseline_seconds")==5678.9823631240915, "Completed cost or selected trajectory baseline differs")
    need((anchor.get("completed_phase_updates"),anchor.get("completed_local_updates"),anchor.get("cumulative_counters",{}).get("updates"))==(360,60,408), "Completed cost interval differs")
    need(anchor.get("training_continuation_eligible") is False and anchor.get("stage_promotion_eligible") is False
         and anchor.get("competence_passed") is False and anchor.get("checkpoint_metadata_unchanged") is True, "Completed cost receipt eligibility differs")
    return anchor
