"""Parent-only terminal acceptance. Importing this module performs no finalization."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
OWN = Path(__file__).resolve().parent
BASE = ROOT / "learning/runs/v2"
PREP = BASE / "D2-retained324-continuation-prepare-luna-20261026-r2"
RUN = BASE / "D2-retained324-continuation-20261026-r1"
OBSERVER = BASE / "D2-retained324-execution-observer-parent-20261026-r1"
AUDITOR = BASE / "D2-retained324-all-candidate-auditor-luna-20261026-r2"
INCUMBENT = BASE / "D2-retained300-continuation-20261026-r1/checkpoint-000324-candidate.pt"
OLD_RECEIPT = BASE / "D2-retained300-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json"
REG_SHA = "44ac8185b24de2d98cc1c870191f18be47734b5cc11c7c6ff91b9feacb34cd5a"
INCUMBENT_SHA = "c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc"
OLD_RECEIPT_SHA = "76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08"


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_parent_guard(state, expected_lease, cancel_exists):
    need(state.get("active_long_campaign") == expected_lease, "Exact lease changed")
    need(not any(state.get(k) for k in ("active_inference_diagnostic", "active_inference_campaign", "active_inference_lease")), "Inference lease exists")
    need(not cancel_exists and state.get("cancel_requested") in (None, False), "Cancellation present")


def validate_snapshot_unchanged(current_bytes, original_bytes):
    need(current_bytes == original_bytes, "Concurrent ledger change before replace")


def read(path):
    return json.loads(Path(path).read_text())


def write(name, value):
    with (OWN / name).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _validate_and_prepare():
    reg = read(PREP / "registration.json")
    need(sha(PREP / "registration.json") == REG_SHA, "Registration changed")
    need(reg["pins"] and reg["expected_lease"]["parent_checkpoint_sha256"] == INCUMBENT_SHA,
         "Registration parent identity differs")
    statepath = Path(reg["state_path"])

    def guard():
        raw = statepath.read_bytes()
        state = json.loads(raw)
        validate_parent_guard(state, reg["expected_lease"], Path(reg["cancel_path"]).exists())
        for path, digest in reg["pins"].items():
            need(sha(path) == digest, "Pinned input changed: " + path)
        return state, raw

    state, _ = guard()
    full_path = AUDITOR / "full-audit.json"
    obs_path = OBSERVER / "observation.json"
    full, obs = read(full_path), read(obs_path)
    execution, worker = read(RUN / "execution-result.json"), read(RUN / "worker-result.json")
    audit = full["audit"]
    need(full["mode"] == "full_parent_only" and audit["status"] == "all_candidates_audited_pending_parent_terminal_acceptance", "Full audit not accepted")
    need(audit["updates_audited"] == [324, 336, 348, 360, 372, 384], "Candidate set differs")
    need(audit["registration_sha256"] == REG_SHA and audit["pins_checked_before_and_after"] == 13846, "Full audit identity differs")
    wrapper = AUDITOR / "wrapper.py"
    bootstrap = AUDITOR / "bootstrap.py"
    need(sha(wrapper) == "a915a4a07fbcae9a70948991a31ca5d334c9414ed7ca13ba8689af53ae5f5c06", "Auditor wrapper changed")
    need(sha(bootstrap) == "f07980868ad0e7f0da1077daebf109812de6150f32b34e707c2faa8d3399123f", "Auditor bootstrap changed")
    need(full["wrapper_sha256"] == sha(wrapper), "Full audit wrapper identity differs")
    reconciliation_path = BASE / "D2-retained324-parent-terminal-audit-20261026-r1/review-reconciliation.json"
    inventory_path = BASE / "D2-retained324-parent-terminal-audit-20261026-r1/artifact-inventory-check.json"
    reconciliation, inventory_check = read(reconciliation_path), read(inventory_path)
    parent_raw_exit_path = BASE / "D2-retained324-parent-terminal-audit-20261026-r1/full-audit-raw-exit.json"
    parent_command_path = BASE / "D2-retained324-parent-terminal-audit-20261026-r1/full-audit-command.json"
    parent_raw_exit = read(parent_raw_exit_path)
    need(reconciliation["status"] == "no_blockers_after_parent_replay_and_terminal_audit" and reconciliation["wrapper_and_bootstrap_hashes_verified"] and reconciliation["full_audit_records_exact_wrapper_hash"], "Parent review reconciliation failed")
    need(reconciliation["full_audit_sha256"] == sha(full_path), "Parent replay audit identity differs")
    need(parent_raw_exit == {"raw_exit": 0, "acceptance_published": False}, "Parent replay did not remain preacceptance")
    need(sha(reconciliation["review"]) == reconciliation["review_sha256"], "Haiku review changed")
    need(inventory_check["status"] == "passed" and inventory_check["registered_artifacts_hashed"] == 32, "Parent inventory receipt failed")
    artifact_manifest_path = RUN / "artifact-manifest.json"
    artifact_manifest = read(artifact_manifest_path)
    manifest = artifact_manifest.get("artifacts", artifact_manifest)
    need(set(manifest) == set(reg["expected_outputs"]), "Artifact manifest key set differs")
    for name in reg["expected_outputs"]:
        item = manifest[name]
        digest = item if isinstance(item, str) else item.get("sha256")
        need(digest == sha(RUN / name), "Registered artifact hash differs: " + name)
    actual_names = {p.name for p in RUN.iterdir() if p.is_file()}
    need(actual_names == set(reg["expected_outputs"]) | {"artifact-manifest.json", "execution-result.json"}, "Run inventory differs")
    need(len(actual_names) == 34 and inventory_check["unexpected_extra_files"] == [], "Exact34 run inventory failed")
    need(sha(artifact_manifest_path) == inventory_check["artifact_manifest_sha256"], "Artifact manifest receipt hash differs")
    need(sha(RUN / "execution-result.json") == inventory_check["execution_receipt_sha256"], "Execution receipt hash differs")
    need(obs["success_authoritative"] and obs["first_event"] is None, "Observer failed")
    need(obs["launch_count"] == execution["actual_worker_launch_count"] == 1, "Launch count differs")
    need(obs["outer_raw_exit"] == obs["worker_raw_exit"] == execution["observed_worker_raw_exit"] == 0, "Raw exits differ")
    need(execution["status"] == "passed" and worker["status"] == "completed" and worker["first_failure"] is None, "Terminal status differs")
    need(execution["directly_reaped"] and execution["owned_group_absent"] and all(obs[k] for k in ("outer_process_absent", "worker_process_absent", "worker_group_absent")), "Process cleanup failed")
    need(obs["outer_inclusive_wall_seconds"] <= 1800 and worker["elapsed_seconds"] <= 1790, "Wall cap failed")
    need(obs["max_aggregate_rss_bytes"] <= 6442450944 and worker["peak_mps_driver_bytes"] <= 6442450944, "Resource cap failed")
    need(worker["counters"]["updates"] == 60 and worker["counters"]["environment_decisions"] == 983040 and worker["counters"]["optimizer_steps"] == 7680, "Completed counters differ")

    # Recheck live process absence; frozen observer evidence alone is insufficient.
    absent = {}
    for pid in (obs["observer_pid"], obs["outer_pid"], execution["worker_pid"]):
        result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "pid="], capture_output=True, text=True)
        need(result.returncode == 1 and not result.stdout.strip(), "Owned process remains: " + str(pid))
        absent[str(pid)] = {"returncode": result.returncode, "stdout": result.stdout}
    for pgid in {obs["outer_process_group"], execution["owned_pgid"]}:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            pass
        else:
            raise ValueError("Owned process group remains: " + str(pgid))

    # All six means are below incumbent; no replacement. Metrics come from original certificate.
    candidates = audit["candidates"]
    means = [2939.40625, 2708.328125, 2351.671875, 2372.65625, 2561.3125, 2648.375]
    for key, mean in zip(("324", "336", "348", "360", "372", "384"), means):
        need(candidates[key]["mean_alive_frames"] == mean, "Candidate metric differs: " + key)
    incumbent_cert = read(BASE / "D2-retained300-continuation-20261026-r1/development-000324.json")
    need(sha(INCUMBENT) == INCUMBENT_SHA and sha(OLD_RECEIPT) == OLD_RECEIPT_SHA, "Original incumbent artifacts changed")
    rows = incumbent_cert["evaluation"]["rows"]
    alive = sorted(row["alive_frames"] for row in rows)
    need(len(alive) == 64 and sum(alive) / 64 == 2939.40625, "Original incumbent certificate differs")
    perf = {"update": 324, "q1_bottom16_mean": sum(alive[:16]) / 16, "q4_top16_mean": sum(alive[-16:]) / 16,
            "mean_alive_frames": sum(alive) / 64, "mean_score": incumbent_cert["evaluation"]["mean_score"],
            "episodes": 64, "deaths": incumbent_cert["evaluation"]["deaths"], "caps": incumbent_cert["evaluation"]["caps"],
            "death_causes": dict(Counter(row["death_cause"] for row in rows if row["terminated"])),
            "checkpoint_sha256": INCUMBENT_SHA, "certificate_sha256": sha(BASE / "D2-retained300-continuation-20261026-r1/development-000324.json")}
    need(perf["q1_bottom16_mean"] == 767.5 and perf["q4_top16_mean"] == 5468.6875, "Original quartiles differ")
    previous = read(OLD_RECEIPT)
    need(previous["checkpoint_sha256"] == INCUMBENT_SHA and previous["performance"]["mean_alive_frames"] == perf["mean_alive_frames"], "Original receipt ancestry differs")

    outer = obs["outer_inclusive_wall_seconds"]
    cost_before = 9758.365427209174
    cost = cost_before + outer
    trajectory = 5678.9823631240915
    now = datetime.now(timezone.utc).isoformat()
    evidence = [full_path, obs_path, RUN / "execution-result.json", RUN / "worker-result.json", PREP / "registration.json", OLD_RECEIPT, INCUMBENT,
                BASE / "D2-retained300-continuation-20261026-r1/development-000324.json", wrapper, bootstrap,
                reconciliation_path, inventory_path, artifact_manifest_path, parent_raw_exit_path, parent_command_path]
    frozen = {str(p): sha(p) for p in evidence}
    audit_out = {"schema": "d2_retained324_parent_terminal_audit_v1", "status": "accepted_completed_iteration_no_best_replacement",
        "at_utc": now, "registration_sha256": REG_SHA, "source_pins_unchanged": 13846,
        "full_audit_path": str(full_path), "full_audit_sha256": sha(full_path), "observer_sha256": sha(obs_path),
        "parent_review_reconciliation_sha256": sha(reconciliation_path), "parent_full_audit_raw_exit_sha256": sha(parent_raw_exit_path),
        "parent_full_audit_command_sha256": sha(parent_command_path), "haiku_review_sha256": reconciliation["review_sha256"],
        "artifact_inventory_check_sha256": sha(inventory_path), "artifact_manifest_sha256": sha(artifact_manifest_path),
        "auditor_wrapper_sha256": sha(wrapper), "auditor_bootstrap_sha256": sha(bootstrap),
        "all_six_candidates_audited": True, "candidate_means": dict(zip(("324", "336", "348", "360", "372", "384"), means)),
        "retained_best_performance": perf, "retained_best_checkpoint_sha256": INCUMBENT_SHA,
        "retained_best_receipt_sha256": OLD_RECEIPT_SHA, "raw_exits": {"outer": 0, "worker": 0},
        "observed_outer_seconds": outer, "process_absence": absent, "owned_groups_absent": True,
        "raw_counters": worker["counters"], "resource_limits_passed": True, "frozen_evidence_sha256": frozen,
        "authority": "Completed iteration/resource-cost accounting only. No best replacement, selection, continuation, qualification, D3, B, E, or student authority."}
    write("audit.json", audit_out)
    completed = {"schema": "d2_completed_iteration_parent_audit_receipt_v1", "status": "accepted_completed_training_iteration_no_best_replacement",
        "at_utc": now, "run_id": reg["run_id"], "phase": "D2", "normal_training_iteration": True,
        "completed_local_updates": 60, "completed_phase_updates": 384, "counters": worker["counters"],
        "cumulative_counters": worker["cumulative_counters"], "endpoint_checkpoint_sha256": candidates["384"]["checkpoint_sha256"],
        "endpoint_performance": candidates["384"]["performance"], "best_replacement": False, "selected_phase_update": None,
        "training_continuation_eligible": False, "stage_promotion_eligible": False, "checkpoint_metadata_unchanged": True,
        "raw_exits": {"outer": 0, "worker": 0}, "owned_processes_and_groups_absent": True,
        "registration_path": str(PREP / "registration.json"), "registration_sha256": REG_SHA,
        "audit_path": str(OWN / "audit.json"), "audit_sha256": sha(OWN / "audit.json"), "full_audit_sha256": sha(full_path),
        "wall_accounting": {"completed_campaign_resource_cost_before_seconds": cost_before,
            "completed_campaign_resource_cost_after_seconds": cost, "observed_outer_seconds": outer,
            "selected_checkpoint_future_baseline_seconds": trajectory,
            "discarded_branch_end_highwater_seconds": trajectory + outer,
            "semantics": "All60 discarded updates add resource cost; no discarded checkpoint adds model/Adam/RNG/counter ancestry."}}
    write("completed-iteration-receipt.json", completed)
    decision = {"selection": "retain_original_incumbent_no_replacement", "phase_update": 324,
        "checkpoint_path": str(INCUMBENT), "checkpoint_sha256": INCUMBENT_SHA,
        "receipt_path": str(OLD_RECEIPT), "receipt_sha256": OLD_RECEIPT_SHA,
        "original_certificate_path": str(BASE / "D2-retained300-continuation-20261026-r1/development-000324.json"),
        "original_certificate_sha256": perf["certificate_sha256"], "new_candidate_means_all_below_incumbent": True,
        "endpoint384_not_selected": True, "future_branch_baseline_seconds": trajectory, "completed_campaign_cost_seconds": cost}
    write("retained-best-decision.json", decision)
    report = ["# Retained324 terminal audit", "", "All60 updates and six candidate audits passed. Every new candidate scored below incumbent; no replacement.", "",
        "| Update | Mean frames |", "| ---: | ---: |"]
    report.extend(f"| {u} | {m} |" for u, m in zip((324,336,348,360,372,384), means))
    report += ["", "Retained original checkpoint c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc; original receipt 76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08.",
        "Original certificate: Q1 767.5, Q4 5468.6875, mean 2939.40625. Deaths: 35 normal, 14 static, 9 kamikaze, 3 moving, 3 explosion.",
        f"Observed outer duration {outer}s; completed resource cost {cost}s. Selected trajectory baseline remains {trajectory}s. Endpoint384 is not selected.",
        "No qualification, D3, B, E, or student claim. Score gate unchanged and absent."]
    with (OWN / "report.md").open("x") as stream:
        stream.write("\n".join(report) + "\n")

    # Require unchanged lease/state at both checks and preserve concurrent ledger edits.
    state, state_before = guard()
    write("state-before-lease-clear.json", state)
    state["active_long_campaign"] = None
    state["last_update_at_utc"] = now
    relative_cost = str((OWN / "completed-iteration-receipt.json").relative_to(ROOT))
    cost_sha = sha(OWN / "completed-iteration-receipt.json")
    post = state["postcritic_training_work"]
    post.update(active_campaign=None, status="accepted_iteration_no_best_replacement_endpoint384_discarded",
        latest_parent_terminal_audit=str((OWN / "audit.json").relative_to(ROOT)),
        latest_completed_iteration_receipt=relative_cost, latest_completed_iteration_receipt_sha256=cost_sha,
        completed_campaign_resource_cost_seconds=cost, latest_completed_cumulative_updates=432,
        latest_completed_phase_updates=384, latest_completed_endpoint_performance=candidates["384"]["performance"],
        lease_cleared_at_utc=now)
    # Keep latest_parent_terminal_receipt, best reference, and selection policy byte-for-byte semantically unchanged.
    need(state["training_parent_selection_policy"] == read(statepath)["training_parent_selection_policy"], "Selection policy changed")
    current = read(statepath)["postcritic_training_work"]
    need(post["latest_parent_terminal_receipt"] == current["latest_parent_terminal_receipt"] and post["latest_parent_terminal_receipt_sha256"] == current["latest_parent_terminal_receipt_sha256"], "Retained receipt pointer changed")
    task = state["tasks"].get("retained324_terminal_finalizer_prepare_luna_20261026_r1")
    need(task is not None, "Finalizer task key missing")
    task.update(status="completed", workState="result_available", result_ingested=True,
        ingested_at_utc=now, actual_outcome="terminal_iteration_accepted_no_best_replacement", parent_terminal_audit=str((OWN / "audit.json").relative_to(ROOT)), lease_cleared_at_utc=now)
    validate_snapshot_unchanged(statepath.read_bytes(), state_before)
    with tempfile.NamedTemporaryFile("w", dir=statepath.parent, prefix=".retained324-finalize-", delete=False) as stream:
        json.dump(state, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno()); temporary = stream.name
    validate_snapshot_unchanged(statepath.read_bytes(), state_before)
    # Final immediate guard includes exact lease and cancellation checks before os.replace.
    guard()
    validate_snapshot_unchanged(statepath.read_bytes(), state_before)
    os.replace(temporary, statepath)
    write("state-after-lease-clear.json", state)


def finalize_parent():
    """Explicit parent invocation entry point."""
    _validate_and_prepare()


if __name__ == "__main__":
    finalize_parent()
