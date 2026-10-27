"""Validate the externally accepted selected300 parent and separate cost anchor."""
from __future__ import annotations

from collections.abc import Mapping

RECEIPT_SHA = "ccc73fbc72c83e9dc061ad11be536b2e0d7cb076319e6d7cff27b9f2a0f8838d"
CHECKPOINT_SHA = "e2c8fbe44e23da910686954e90cb7841b38b6d7f60f69ca657a4a69b14214710"
CHECKPOINT_METADATA_SHA = "7d6f5eb8bca5758bbf7bf71a6615eabca823f48703b6d22798587cafced9f8ac"
COST_RECEIPT_SHA = "b170f68ce68c98e1a0d7511fed71f978732731895446214966da1402caea863a"
CONFIG_SHA = "1c24df3eea150160451ada08e9f6844cd67645abf5fb8b712afd14abca930ce8"
SCHEMA = "d2_retained_best_candidate_parent_receipt_v1"
STATUS = "accepted_complete_candidate_from_completed_normal_training_iteration"
COST_SCHEMA = "d2_completed_iteration_parent_audit_receipt_v1"
COST_STATUS = "accepted_completed_training_iteration_with_best_replacement"
PARENT_OF_RUN_SHA = "0b5cf72b4eb9629fa4f10ce2cecb3625b56f8787c0eca6395b9fe17161e6b292"


def need(ok, message):
    if not ok:
        raise ValueError(message)


def validate_parent(state: Mapping, checkpoint_sha: str, receipt: Mapping,
                    receipt_sha: str, fingerprint, checkpoint_metadata: Mapping,
                    checkpoint_metadata_sha: str, cost_anchor: Mapping, cost_anchor_sha: str):
    need(checkpoint_sha == CHECKPOINT_SHA and receipt_sha == RECEIPT_SHA,
         "Parent byte pins differ")
    need(receipt.get("schema") == SCHEMA and receipt.get("status") == STATUS,
         "Selected candidate receipt authority differs")
    need(receipt.get("training_continuation_eligible") is True
         and receipt.get("stage_promotion_eligible") is False
         and receipt.get("competence_passed") is False
         and receipt.get("checkpoint_metadata_unchanged") is True,
         "External receipt does not grant exact D2 continuation authority")
    need(receipt.get("checkpoint_sha256") == CHECKPOINT_SHA
         and receipt.get("config_sha256") == CONFIG_SHA,
         "Selected checkpoint/config pin differs")
    need(checkpoint_metadata_sha == CHECKPOINT_METADATA_SHA
         and checkpoint_metadata == {"checkpoint_sha256": CHECKPOINT_SHA,
                                     "eligibility_status": "provisional_pending_parent_terminal_receipt",
                                     "promoted": False, "training_eligible": False},
         "Checkpoint metadata changed or became eligible")
    need((receipt.get("candidate_phase_update"), receipt.get("candidate_local_update")) == (300, 24),
         "Selected point is not local24/update300")
    pairs = {
        "counters": "candidate_counters",
        "cumulative_counters": "candidate_cumulative_counters",
        "inherited_counters": "inherited_counters",
        "next_episode_indices": "next_episode_indices",
        "identity_sha256": "identity_sha256", "config_sha256": "config_sha256",
        "runtime_sha256": "runtime_sha256", "native_sha256": "native_sha256",
        "policy_sha256": "policy_sha256", "registration_sha256": "registration_sha256",
    }
    for state_key, receipt_key in pairs.items():
        need(state.get(state_key) == receipt.get(receipt_key),
             "Checkpoint differs from selected receipt: " + state_key)
    need(state.get("phase") == "D2" and state.get("phase_update") == 300
         and state.get("local_update") == 24, "Checkpoint counters identify another point")
    need(state.get("tag") == "candidate" and state.get("training_eligible") is False
         and state.get("promoted") is False
         and state.get("eligibility_status") == "provisional_pending_parent_terminal_receipt",
         "Saved state is not provisional and ineligible")
    progress = state.get("update_progress", {})
    need(progress.get("complete") is True and progress.get("in_update") is False
         and progress.get("completed_updates") == 24, "Selected update is incomplete")
    need(state.get("parent_checkpoint_sha256") == PARENT_OF_RUN_SHA
         and receipt.get("candidate_parent_checkpoint_sha256") == PARENT_OF_RUN_SHA,
         "Parent-of-run lineage differs")
    need(state.get("parent_checkpoint_sha256") != CHECKPOINT_SHA,
         "Parent-of-run was confused with selected continuation checkpoint")
    wall = receipt.get("wall_accounting", {})
    need(state.get("cumulative_selected_checkpoint_trajectory_wall_seconds")
         == wall.get("future_checkpoint_trajectory_baseline_seconds") == 5190.209660791156,
         "Selected trajectory clock differs")
    need(state.get("current_iteration_observed_outer_seconds")
         == wall.get("selected_checkpoint_reported_current_iteration_wall_seconds"),
         "Selected iteration clock differs")
    validate_cost_anchor(cost_anchor, cost_anchor_sha)
    campaign_before = cost_anchor["wall_accounting"]["completed_campaign_resource_cost_before_seconds"]
    need(state.get("parent_completed_campaign_cost_baseline_seconds") == campaign_before
         and state.get("cumulative_successful_ancestor_and_completed_campaign_cost_seconds")
         == campaign_before + state["current_iteration_observed_outer_seconds"],
         "Saved selected-point campaign clock differs from completed-cost receipt")
    need(fingerprint(state["model"]) == receipt["learner_fingerprints"]["model"],
         "Model fingerprint differs")
    need(fingerprint(state["optimizer"]) == receipt["learner_fingerprints"]["optimizer"],
         "Adam fingerprint differs")
    need(fingerprint(state["rng"]) == receipt["learner_fingerprints"]["rng"],
         "RNG fingerprint differs")
    groups = state["optimizer"]["param_groups"]
    need(bool(groups) and all(g.get("lr") == 3e-5 for g in groups), "Restored LR differs")
    need(all(g.get("eps") == 1e-5 for g in groups), "Restored Adam epsilon differs")
    return state


def validate_cost_anchor(anchor: Mapping, anchor_sha: str, fingerprint=None):
    need(anchor_sha == COST_RECEIPT_SHA and anchor.get("schema") == COST_SCHEMA,
         "Completed-iteration receipt pin/schema differs")
    need(anchor.get("status") == COST_STATUS, "Completed cost receipt status differs")
    wall = anchor["wall_accounting"]
    need(wall.get("completed_campaign_resource_cost_before_seconds") == 7118.78208862512
         and wall.get("completed_campaign_resource_cost_after_seconds") == 8621.338345875141,
         "Full campaign cost baseline differs")
    need(wall.get("selected_checkpoint_future_baseline_seconds") == 5190.209660791156,
         "Selected trajectory baseline differs")
    need(anchor.get("completed_phase_updates") == 336
         and anchor.get("completed_local_updates") == 60
         and anchor.get("cumulative_counters", {}).get("updates") == 384,
         "Completed cost interval differs")
    need(anchor.get("training_continuation_eligible") is False
         and anchor.get("stage_promotion_eligible") is False
         and anchor.get("competence_passed") is False
         and anchor.get("checkpoint_metadata_unchanged") is True,
         "Completed cost receipt eligibility or metadata differs")
    return anchor
