"""Validate selected324 ancestry separately from latest campaign resource cost."""
from __future__ import annotations

from collections.abc import Mapping
import math

SELECTED_RECEIPT_SHA256 = "76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08"
CHECKPOINT_SHA256 = "c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc"
CHECKPOINT_METADATA_SHA256 = "cedb20704c9a7c0ec9126c6e7da2f75e230d6acdaa1b7b47f25256ed4f1fd939"
PRODUCING_COST_RECEIPT_SHA256 = "7c6f250b5c5aa9e4098603cc8772c532a713e65f478cbda6ebfdd3941692fc9b"
LATEST_COST_RECEIPT_SHA256 = "d3ddc427f18c8a88c45439452c9efcd966daefe423222e0fa03e97ff4f4fc7d3"
CONFIG_SHA256 = "1c24df3eea150160451ada08e9f6844cd67645abf5fb8b712afd14abca930ce8"
SELECTED_SCHEMA = "d2_retained_best_candidate_parent_receipt_v1"
SELECTED_STATUS = "accepted_complete_candidate_from_completed_normal_training_iteration"
COST_SCHEMA = "d2_completed_iteration_parent_audit_receipt_v1"
PRODUCING_COST_STATUS = "accepted_completed_training_iteration_with_best_replacement"
LATEST_COST_STATUS = "accepted_completed_training_iteration_no_best_replacement"
PARENT_OF_RUN_SHA256 = "e2c8fbe44e23da910686954e90cb7841b38b6d7f60f69ca657a4a69b14214710"
SELECTED_TRAJECTORY_BASELINE_SECONDS = 5678.9823631240915
PRODUCING_COST_BEFORE_SECONDS = 8621.338345875141
PRODUCING_COST_AFTER_SECONDS = 9758.365427209174
LATEST_COST_BEFORE_SECONDS = 9758.365427209174
LATEST_COST_AFTER_SECONDS = 10824.835578584221
LATEST_OUTER_SECONDS = 1066.4701513750479


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _wall(receipt: Mapping) -> Mapping:
    wall = receipt.get("wall_accounting")
    need(isinstance(wall, Mapping), "Receipt wall accounting is missing")
    return wall


def validate_producing_cost_receipt(receipt: Mapping, digest: str) -> Mapping:
    need(digest == PRODUCING_COST_RECEIPT_SHA256, "Original producing cost receipt digest differs")
    need(receipt.get("schema") == COST_SCHEMA and receipt.get("status") == PRODUCING_COST_STATUS,
         "Original producing cost receipt authority differs")
    wall = _wall(receipt)
    need(wall.get("completed_campaign_resource_cost_before_seconds") == PRODUCING_COST_BEFORE_SECONDS
         and wall.get("completed_campaign_resource_cost_after_seconds") == PRODUCING_COST_AFTER_SECONDS
         and wall.get("selected_checkpoint_future_baseline_seconds") == SELECTED_TRAJECTORY_BASELINE_SECONDS,
         "Original producing cost receipt accounting differs")
    need((receipt.get("completed_phase_updates"), receipt.get("completed_local_updates"),
          receipt.get("cumulative_counters", {}).get("updates")) == (360, 60, 408),
         "Original producing iteration interval differs")
    need(receipt.get("training_continuation_eligible") is False
         and receipt.get("stage_promotion_eligible") is False
         and receipt.get("competence_passed") is False
         and receipt.get("checkpoint_metadata_unchanged") is True,
         "Original producing cost receipt eligibility differs")
    return receipt


def validate_latest_cost_receipt(receipt: Mapping, digest: str) -> Mapping:
    need(digest == LATEST_COST_RECEIPT_SHA256, "Latest campaign cost receipt digest differs")
    need(receipt.get("schema") == COST_SCHEMA and receipt.get("status") == LATEST_COST_STATUS,
         "Latest campaign cost receipt authority differs")
    wall = _wall(receipt)
    need(wall.get("completed_campaign_resource_cost_before_seconds") == LATEST_COST_BEFORE_SECONDS
         and wall.get("completed_campaign_resource_cost_after_seconds") == LATEST_COST_AFTER_SECONDS
         and wall.get("observed_outer_seconds") == LATEST_OUTER_SECONDS
         and wall.get("selected_checkpoint_future_baseline_seconds") == SELECTED_TRAJECTORY_BASELINE_SECONDS,
         "Latest campaign resource accounting differs")
    need(receipt.get("completed_phase_updates") == 384 and receipt.get("completed_local_updates") == 60
         and receipt.get("cumulative_counters", {}).get("updates") == 432,
         "Latest completed iteration interval differs")
    need(receipt.get("training_continuation_eligible") is False
         and receipt.get("stage_promotion_eligible") is False
         and receipt.get("checkpoint_metadata_unchanged") is True,
         "Latest accounting receipt grants unrecognized authority")
    need("competence_passed" not in receipt,
         "Latest accounting receipt contains a fabricated competence authority field")
    before = wall.get("completed_campaign_resource_cost_before_seconds")
    after = wall.get("completed_campaign_resource_cost_after_seconds")
    need(math.isclose(after - before, LATEST_OUTER_SECONDS, rel_tol=0, abs_tol=1e-12),
         "Latest outer cost delta differs")
    return receipt


def validate_parent(state: Mapping, checkpoint_sha256: str, selected_receipt: Mapping,
                    selected_receipt_sha256: str, fingerprint,
                    checkpoint_metadata: Mapping, checkpoint_metadata_sha256: str,
                    producing_cost_receipt: Mapping, producing_cost_receipt_sha256: str,
                    latest_cost_receipt: Mapping, latest_cost_receipt_sha256: str) -> Mapping:
    need(checkpoint_sha256 == CHECKPOINT_SHA256
         and selected_receipt_sha256 == SELECTED_RECEIPT_SHA256,
         "Selected checkpoint or receipt byte pin differs")
    need(selected_receipt.get("schema") == SELECTED_SCHEMA
         and selected_receipt.get("status") == SELECTED_STATUS,
         "Selected candidate receipt authority differs")
    need(selected_receipt.get("training_continuation_eligible") is True
         and selected_receipt.get("stage_promotion_eligible") is False
         and selected_receipt.get("competence_passed") is False
         and selected_receipt.get("checkpoint_metadata_unchanged") is True,
         "Original selected receipt does not authorize this continuation")
    need(selected_receipt.get("checkpoint_sha256") == CHECKPOINT_SHA256
         and selected_receipt.get("config_sha256") == CONFIG_SHA256,
         "Selected checkpoint or config identity differs")
    need(checkpoint_metadata_sha256 == CHECKPOINT_METADATA_SHA256
         and checkpoint_metadata == {
             "checkpoint_sha256": CHECKPOINT_SHA256,
             "eligibility_status": "provisional_pending_parent_terminal_receipt",
             "promoted": False,
             "training_eligible": False,
         }, "Selected checkpoint metadata changed or became eligible")
    need((selected_receipt.get("candidate_phase_update"),
          selected_receipt.get("candidate_local_update")) == (324, 24),
         "Selected point is not original local24/update324")
    pairs = {
        "counters": "candidate_counters",
        "cumulative_counters": "candidate_cumulative_counters",
        "inherited_counters": "inherited_counters",
        "next_episode_indices": "next_episode_indices",
        "identity_sha256": "identity_sha256",
        "config_sha256": "config_sha256",
        "runtime_sha256": "runtime_sha256",
        "native_sha256": "native_sha256",
        "policy_sha256": "policy_sha256",
        "registration_sha256": "registration_sha256",
    }
    for state_key, receipt_key in pairs.items():
        need(state.get(state_key) == selected_receipt.get(receipt_key),
             "Checkpoint differs from selected receipt: " + state_key)
    need((state.get("phase"), state.get("phase_update"), state.get("local_update")) == ("D2", 324, 24),
         "Checkpoint counters identify another point")
    need(state.get("tag") == "candidate" and state.get("training_eligible") is False
         and state.get("promoted") is False
         and state.get("eligibility_status") == "provisional_pending_parent_terminal_receipt",
         "Saved state is not provisional and ineligible")
    progress = state.get("update_progress", {})
    need(progress.get("complete") is True and progress.get("in_update") is False
         and progress.get("completed_updates") == 24, "Selected update is incomplete")
    need(state.get("parent_checkpoint_sha256") == PARENT_OF_RUN_SHA256
         and selected_receipt.get("candidate_parent_checkpoint_sha256") == PARENT_OF_RUN_SHA256,
         "Parent-of-run lineage differs")

    selected_wall = _wall(selected_receipt)
    need(state.get("cumulative_selected_checkpoint_trajectory_wall_seconds")
         == selected_wall.get("future_checkpoint_trajectory_baseline_seconds")
         == SELECTED_TRAJECTORY_BASELINE_SECONDS,
         "Selected trajectory clock differs")
    need(state.get("current_iteration_observed_outer_seconds")
         == selected_wall.get("selected_checkpoint_reported_current_iteration_wall_seconds"),
         "Selected iteration clock differs")

    validate_producing_cost_receipt(producing_cost_receipt, producing_cost_receipt_sha256)
    producing_after = _wall(producing_cost_receipt)["completed_campaign_resource_cost_after_seconds"]
    need(state.get("parent_completed_campaign_cost_baseline_seconds") == PRODUCING_COST_BEFORE_SECONDS
         and state.get("cumulative_successful_ancestor_and_completed_campaign_cost_seconds")
         == PRODUCING_COST_BEFORE_SECONDS + state["current_iteration_observed_outer_seconds"],
         "Selected checkpoint producing-run cost lineage differs")
    validate_latest_cost_receipt(latest_cost_receipt, latest_cost_receipt_sha256)
    need(_wall(latest_cost_receipt)["completed_campaign_resource_cost_before_seconds"] == producing_after,
         "Latest cost receipt does not continue original producing cost")

    need(fingerprint(state["model"]) == selected_receipt["learner_fingerprints"]["model"]
         and fingerprint(state["optimizer"]) == selected_receipt["learner_fingerprints"]["optimizer"]
         and fingerprint(state["rng"]) == selected_receipt["learner_fingerprints"]["rng"],
         "Model, Adam, or RNG fingerprint differs")
    groups = state["optimizer"]["param_groups"]
    need(groups and all(group.get("lr") == 3e-5 for group in groups)
         and all(group.get("eps") == 1e-5 for group in groups),
         "Restored optimizer parameters differ")
    return state
