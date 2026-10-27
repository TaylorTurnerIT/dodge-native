"""Selected-intermediate parent and separate completed-cost authority."""
from __future__ import annotations

from collections.abc import Mapping

RECEIPT_SHA = "ccc73fbc72c83e9dc061ad11be536b2e0d7cb076319e6d7cff27b9f2a0f8838d"
CHECKPOINT_SHA = "e2c8fbe44e23da910686954e90cb7841b38b6d7f60f69ca657a4a69b14214710"
COST_RECEIPT_SHA = "b170f68ce68c98e1a0d7511fed71f978732731895446214966da1402caea863a"
CONFIG_SHA = "1c24df3eea150160451ada08e9f6844cd67645abf5fb8b712afd14abca930ce8"
SCHEMA = "d2_retained_best_candidate_parent_receipt_v1"
STATUS = "accepted_complete_candidate_from_completed_normal_training_iteration"

def need(ok, message):
    if not ok:
        raise ValueError(message)

def validate_parent(state: Mapping, checkpoint_sha: str, receipt: Mapping, receipt_sha: str, fingerprint):
    need(checkpoint_sha == CHECKPOINT_SHA and receipt_sha == RECEIPT_SHA, "Parent byte pins differ")
    need(receipt.get("schema") == SCHEMA and receipt.get("status") == STATUS, "Selected candidate receipt authority differs")
    need(receipt.get("checkpoint_sha256") == CHECKPOINT_SHA and receipt.get("config_sha256") == CONFIG_SHA, "Selected checkpoint/config pin differs")
    need((receipt.get("candidate_phase_update"), receipt.get("candidate_local_update")) == (300, 24), "Selected point is not local24/update300")
    for key in ("counters", "cumulative_counters", "inherited_counters", "next_episode_indices", "identity_sha256", "config_sha256", "runtime_sha256", "native_sha256", "policy_sha256", "registration_sha256"):
        expected_key = {"counters":"candidate_counters", "cumulative_counters":"candidate_cumulative_counters"}.get(key, key)
        need(state.get(key) == receipt.get(expected_key), "Checkpoint differs from selected receipt: " + key)
    need(state.get("phase") == "D2" and state.get("phase_update") == 300 and state.get("local_update") == 24, "Checkpoint counters identify another point")
    need(state.get("update_progress", {}).get("complete") is True and state.get("update_progress", {}).get("completed_updates") == 24, "Selected update is incomplete")
    need(fingerprint(state["model"]) == receipt["learner_fingerprints"]["model"], "Model fingerprint differs")
    need(fingerprint(state["optimizer"]) == receipt["learner_fingerprints"]["optimizer"], "Adam fingerprint differs")
    need(fingerprint(state["rng"]) == receipt["learner_fingerprints"]["rng"], "RNG fingerprint differs")
    groups = state["optimizer"]["param_groups"]
    need(all(g.get("lr") == 3e-5 for g in groups), "Restored LR differs")
    need(all(g.get("eps") == 1e-5 for g in groups), "Restored Adam epsilon differs")
    return state

def validate_cost_anchor(anchor: Mapping, anchor_sha: str, fingerprint):
    need(anchor_sha == COST_RECEIPT_SHA and anchor.get("schema") == "d2_completed_training_iteration_receipt_v1", "Completed-iteration receipt pin/schema differs")
    need(anchor.get("status") == "accepted_completed_training_iteration_with_best_replacement", "Completed cost receipt status differs")
    wall = anchor["wall_accounting"]
    need(wall.get("completed_campaign_resource_cost_after_seconds") == 8621.338345875141, "Full campaign cost baseline differs")
    need(wall.get("selected_checkpoint_future_trajectory_baseline_seconds") == 5190.209660791156, "Selected trajectory baseline differs")
    return anchor
