"""Pure planner for parent review after the retained276 continuation ends."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any


OWN = Path(__file__).resolve().parent
BASELINE_MEAN = 2483.65625
BASELINE_UPDATE = 276
BASELINE_SHA256 = "0b5cf72b4eb9629fa4f10ce2cecb3625b56f8787c0eca6395b9fe17161e6b292"
BASELINE_RECEIPT_SHA256 = "d64d0f803d02a8d2c33da9fa0ba862f06ba7d9c56dcf4f0494e559a49e48fcc4"
BASELINE_FUTURE_SECONDS = 4760.062404125177
BASELINE_FULL_COST_SECONDS = 5537.773026792208
EXPECTED_UPDATES = [276, 288, 300, 312, 324, 336, 348]
AUDITOR_SHA256 = "98a58d8300eebd4630eb5d8ba66cf4880b49fc0526253d3bb8fe4b9d485ab707"
WRAPPER_SHA256 = "fbc3e71532b4db918042c962efa61172848a40626ec065c78838d4d858d8f854"
OBSERVER_SHA256 = "e3782f1c28c05548e995f3cb8c1a41b2a66f77b69d9455cada0be465f950ad95"
REGISTRATION_SHA256 = "477217f3c7617ccbe01c651db8932eab01f54ea3924f213e67b413e640cf866c"
MAX_BYTES = 6442450944
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class InvalidEvidence(ValueError):
    pass


def _need(ok: bool, message: str) -> None:
    if not ok:
        raise InvalidEvidence(message)


def _finite(value: Any, label: str, *, positive: bool = False) -> float:
    _need(isinstance(value, (int, float)) and not isinstance(value, bool), f"{label} missing or nonnumeric")
    number = float(value)
    _need(math.isfinite(number) and (number > 0 if positive else number >= 0), f"{label} invalid")
    return number


def _sha(value: Any, label: str) -> str:
    _need(isinstance(value, str) and HEX64.fullmatch(value) is not None, f"{label} is not SHA-256")
    return value


def _finite_tree(value: Any, path: str = "evidence") -> None:
    if isinstance(value, float):
        _need(math.isfinite(value), f"{path} contains nonfinite number")
    elif isinstance(value, dict):
        for key, child in value.items():
            _finite_tree(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _finite_tree(child, f"{path}[{index}]")


def _counter_record(value: Any, label: str) -> None:
    _need(isinstance(value, dict), f"{label} missing")
    required = {"updates", "optimizer_steps", "environment_decisions", "raw_frames"}
    _need(required <= set(value), f"{label} fields incomplete")
    for key in required:
        item = value[key]
        _need(type(item) is int and item >= 0, f"{label}.{key} invalid")


def _validate(e: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _need(isinstance(e, dict), "evidence must be an object")
    _finite_tree(e)
    _need(e.get("schema") == "retained276_terminal_planner_evidence_v1", "evidence schema differs")
    pins = e.get("pins", {})
    expected_pins = {
        "registration_sha256": REGISTRATION_SHA256,
        "auditor_sha256": AUDITOR_SHA256,
        "wrapper_sha256": WRAPPER_SHA256,
    }
    for key, expected in expected_pins.items():
        _need(pins.get(key) == expected, f"{key} pin mismatch")

    parent = e.get("parent", {})
    _need(parent.get("phase_update") == BASELINE_UPDATE, "stale parent update")
    _need(_sha(parent.get("checkpoint_sha256"), "parent checkpoint") == BASELINE_SHA256,
          "stale parent checkpoint")
    _need(_finite(parent.get("mean_alive_frames"), "parent baseline") == BASELINE_MEAN,
          "parent baseline mean mismatch")
    _need(parent.get("stale") is False, "parent marked stale")
    receipt = parent.get("receipt", {})
    _need(receipt.get("schema") == "d2_normal_training_parent_terminal_receipt_v1"
          and receipt.get("status") == "accepted_completed_normal_training_iteration",
          "retained parent receipt schema or status mismatch")
    _need(receipt.get("receipt_sha256") == BASELINE_RECEIPT_SHA256
          and receipt.get("checkpoint_sha256") == BASELINE_SHA256
          and receipt.get("completed_phase_updates") == 276
          and receipt.get("performance", {}).get("mean_alive_frames") == BASELINE_MEAN,
          "retained parent receipt binding mismatch")
    _need(receipt.get("wall_accounting", {}).get("future_checkpoint_trajectory_baseline_seconds")
          == BASELINE_FUTURE_SECONDS
          and receipt.get("wall_accounting", {}).get("successful_ancestor_and_completed_campaign_cost_seconds")
          == BASELINE_FULL_COST_SECONDS, "retained parent clocks mismatch")

    reg = e.get("registration", {})
    _need(reg.get("sha256") == REGISTRATION_SHA256 and reg.get("run_id") == "D2-retained276-continuation-20261026-r2",
          "registration binding mismatch")
    _need(reg.get("parent_checkpoint_sha256") == BASELINE_SHA256, "registration parent mismatch")
    _need(reg.get("phase_start") == 276 and reg.get("phase_end") == 348 and reg.get("local_updates") == 72,
          "registration interval mismatch")
    _need(reg.get("run_seed") == 3791628419 and reg.get("config_sha256") ==
          "f858a63c324fc312f794c0423aa56db2daf60793b62990cd51fa400afe3af628",
          "registration seed or config mismatch")

    audit = e.get("audit", {})
    _need(audit.get("schema") == "d2_retained276_continuation_terminal_wrapper_audit_v1",
          "wrapper audit schema mismatch")
    _need(audit.get("mode") == "full_parent_only", "audit is not full parent-only mode")
    _need(audit.get("auditor_sha256") == AUDITOR_SHA256 and audit.get("wrapper_sha256") == WRAPPER_SHA256,
          "audit source hash mismatch")
    _need(audit.get("observer_sha256") == OBSERVER_SHA256, "observer source hash mismatch")
    _need(audit.get("registration_sha256") == REGISTRATION_SHA256, "audit registration hash mismatch")
    _need(audit.get("status") == "all_candidates_audited_pending_parent_terminal_acceptance",
          "candidate audit not complete")
    _need(audit.get("updates_audited") == EXPECTED_UPDATES, "candidate list incomplete or reordered")
    _need(audit.get("pins_checked_before") == audit.get("pins_checked_after") == 13787,
          "registration pins not verified before and after")
    _need(audit.get("parent_sha256") == BASELINE_SHA256 and audit.get("stale_parent") is False,
          "audit parent is stale")

    terminal = e.get("terminal", {})
    _need(terminal.get("execution_status") == "passed" and terminal.get("worker_status") == "completed",
          "terminal execution not successful")
    _need(terminal.get("raw_exits") == {"outer": 0, "worker": 0}, "terminal raw exit mismatch")
    _need(terminal.get("owned_processes_and_groups_absent") is True, "owned processes remain")
    _need(terminal.get("source_postflight_passed") is True and terminal.get("final_publication_absent") is True,
          "terminal postflight incomplete")
    outer = _finite(terminal.get("outer_inclusive_wall_seconds"), "outer wall", positive=True)
    _need(outer <= 1800, "outer wall exceeds registered cap")
    for key in ("aggregate_rss_peak_bytes", "worker_rss_peak_bytes", "mps_driver_peak_bytes"):
        _need(_finite(terminal.get(key), key, positive=True) <= MAX_BYTES, f"{key} exceeds registered cap")
    _need(terminal.get("resources_complete") is True, "terminal resource evidence incomplete")
    for key in ("execution_result_sha256", "worker_result_sha256", "observation_sha256", "resource_log_sha256"):
        _sha(terminal.get(key), f"terminal {key}")
    _counter_record(terminal.get("cumulative_counters"), "terminal cumulative counters")
    terminal_indices = terminal.get("next_episode_indices")
    _need(isinstance(terminal_indices, list) and len(terminal_indices) == 64
          and all(type(index) is int and index >= 0 for index in terminal_indices),
          "terminal resume indices invalid")

    candidates = audit.get("candidates")
    performance = e.get("performance")
    _need(isinstance(candidates, dict) and set(candidates) == {str(x) for x in EXPECTED_UPDATES},
          "candidate records missing or extra")
    _need(isinstance(performance, dict) and set(performance) == {str(x) for x in EXPECTED_UPDATES},
          "performance records missing or extra")
    for update in EXPECTED_UPDATES:
        row = candidates[str(update)]
        _sha(row.get("checkpoint_sha256"), f"candidate {update} checkpoint")
        _sha(row.get("certificate_sha256"), f"candidate {update} certificate")
        _sha(row.get("sidecar_sha256"), f"candidate {update} sidecar")
        perf = performance[str(update)]
        _need(perf.get("update") == update, f"performance {update} update mismatch")
        _need(perf.get("checkpoint_sha256") == row["checkpoint_sha256"]
              and perf.get("certificate_sha256") == row["certificate_sha256"],
              f"performance {update} audit hashes mismatch")
        mean = _finite(perf.get("mean_alive_frames"), f"candidate {update} mean")
        _finite(perf.get("q1_bottom16_mean"), f"candidate {update} Q1")
        _finite(perf.get("q4_top16_mean"), f"candidate {update} Q4")
        _need(perf.get("episodes") == 64 and perf.get("deaths", 0) + perf.get("caps", 0) == 64,
              f"candidate {update} episode accounting mismatch")
        _need(isinstance(perf.get("death_causes"), dict), f"candidate {update} death causes missing")
        _need(update != BASELINE_UPDATE or (
            row["checkpoint_sha256"] == BASELINE_SHA256 and mean == BASELINE_MEAN
        ), "entry candidate does not match retained276 baseline")

    metadata = e.get("candidate_metadata")
    _need(isinstance(metadata, dict) and set(metadata) == {str(x) for x in EXPECTED_UPDATES},
          "candidate metadata missing or extra")
    for update in EXPECTED_UPDATES:
        m = metadata[str(update)]
        row = candidates[str(update)]
        _need(m.get("phase_update") == update and m.get("checkpoint_sha256") == row["checkpoint_sha256"],
              f"candidate {update} metadata binding mismatch")
        _need(m.get("sidecar_sha256") == row["sidecar_sha256"],
              f"candidate {update} sidecar metadata hash mismatch")
        _need(m.get("metadata_sha256") and HEX64.fullmatch(m["metadata_sha256"]) is not None,
              f"candidate {update} metadata hash missing")
        for key in ("counters", "cumulative_counters", "next_episode_indices", "learner_fingerprints"):
            _need(key in m and m[key] not in (None, {}, []), f"candidate {update} {key} missing")
        _counter_record(m["counters"], f"candidate {update} counters")
        _counter_record(m["cumulative_counters"], f"candidate {update} cumulative counters")
        indices = m["next_episode_indices"]
        _need(isinstance(indices, list) and len(indices) == 64
              and all(type(index) is int and index >= 0 for index in indices),
              f"candidate {update} resume indices invalid")
        _need(set(m["learner_fingerprints"]) >= {"model", "optimizer", "rng"},
              f"candidate {update} learner fingerprints incomplete")
        _need(all(HEX64.fullmatch(str(m["learner_fingerprints"][k])) for k in ("model", "optimizer", "rng")),
              f"candidate {update} learner fingerprint invalid")
    return audit, terminal, metadata


def build_plan(evidence: dict[str, Any]) -> dict[str, Any]:
    """Return pending parent proposal, or fail-closed plan with all authority false."""
    flags = {
        "actual_acceptance": False,
        "training_continuation_eligible": False,
        "selection_applied": False,
        "lease_cleared": False,
        "qualification_claim": False,
        "automatic_follow_on": False,
    }
    try:
        audit, terminal, metadata = _validate(evidence)
        candidates = audit["candidates"]
        performance = evidence["performance"]
        best = max(_finite(performance[str(u)]["mean_alive_frames"], f"candidate {u} mean") for u in EXPECTED_UPDATES)
        if best <= BASELINE_MEAN:
            selected_update = BASELINE_UPDATE
            branch = "retain_exact_current_parent"
            selected = evidence["parent"]["receipt"]
            trajectory = BASELINE_FUTURE_SECONDS
        else:
            selected_update = min(u for u in EXPECTED_UPDATES
                                  if _finite(performance[str(u)]["mean_alive_frames"], f"candidate {u} mean") == best)
            selected = metadata[str(selected_update)]
            if selected_update == 348:
                branch = "select_better_endpoint"
                trajectory = BASELINE_FUTURE_SECONDS + terminal["outer_inclusive_wall_seconds"]
            else:
                branch = "select_better_intermediate"
                trajectory = _finite(selected.get("cumulative_selected_checkpoint_trajectory_wall_seconds"),
                                     "selected candidate reported trajectory", positive=True)
        full_cost = BASELINE_FULL_COST_SECONDS + terminal["outer_inclusive_wall_seconds"]
        return {
            "schema": "retained276_parent_reconciliation_proposal_v1",
            "proposal_status": "proposed_pending_parent_decision",
            "authority_flags": flags,
            "selection_rule": "Strictly higher audited mean alive frames than retained276; equal means retain earlier parent/candidate.",
            "branch": branch,
            "proposed_update": selected_update,
            "proposed_checkpoint_sha256": selected.get("checkpoint_sha256"),
            "proposed_candidate_metadata": selected if selected_update != BASELINE_UPDATE else None,
            "retained_parent_receipt": selected if selected_update == BASELINE_UPDATE else None,
            "selected_performance": performance[str(selected_update)],
            "terminal_candidate_means": {str(u): performance[str(u)]["mean_alive_frames"] for u in EXPECTED_UPDATES},
            "counter_binding": {
                "selected_checkpoint_metadata_is_verbatim": selected_update != BASELINE_UPDATE,
                "selected_checkpoint_counters": selected.get("counters"),
                "selected_checkpoint_cumulative_counters": selected.get("cumulative_counters"),
                "selected_checkpoint_next_episode_indices": selected.get("next_episode_indices"),
                "selected_checkpoint_learner_fingerprints": selected.get("learner_fingerprints"),
                "completed_terminal_cumulative_counters": evidence["terminal"]["cumulative_counters"],
                "completed_terminal_next_episode_indices": evidence["terminal"]["next_episode_indices"],
                "intermediate_discarded_tail_is_not_checkpoint_ancestry": branch == "select_better_intermediate",
            },
            "wall_accounting": {
                "retained_parent_future_branch_baseline_seconds": BASELINE_FUTURE_SECONDS,
                "selected_future_branch_baseline_seconds": trajectory,
                "previous_full_resource_cost_seconds": BASELINE_FULL_COST_SECONDS,
                "completed_campaign_full_outer_seconds": terminal["outer_inclusive_wall_seconds"],
                "completed_campaign_full_resource_cost_seconds": full_cost,
                "clock_semantics": "Saved candidate trajectory, accepted future branch high-water, and complete campaign resource cost remain separate.",
            },
            "decision_note": "Proposal only. Parent must bind terminal/audit evidence and decide acceptance; this plan performs no acceptance, selection, lease, or follow-on write.",
        }
    except (InvalidEvidence, KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        return {
            "schema": "retained276_parent_reconciliation_proposal_v1",
            "proposal_status": "blocked_fail_closed",
            "authority_flags": flags,
            "reasons": [str(exc)],
            "proposed_update": None,
            "decision_note": "Insufficient or inconsistent evidence. No parent proposal can grant authority.",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a pending retained276 parent proposal from externally pinned evidence.")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", default=OWN / "proposed-plan.json", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    _need(output.is_relative_to(OWN.resolve()), "output must stay under this planner directory")
    evidence = json.loads(args.evidence.read_text())
    plan = build_plan(evidence)
    output.write_text(json.dumps(plan, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"proposal_status": plan["proposal_status"], "output": str(output)}, sort_keys=True))
    return 0 if plan["proposal_status"] != "blocked_fail_closed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
