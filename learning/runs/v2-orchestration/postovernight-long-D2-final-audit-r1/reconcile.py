"""Reconcile completed read-only audits; never import or launch the learner."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
STATE = ROOT / "learning/runs/v2-orchestration/state.json"
DIAG = ROOT / "learning/runs/v2/postovernight-long-D2-guard-diagnosis-opus-r1"
AUDIT = ROOT / "learning/runs/v2/postovernight-long-D2-failure-parent-audit-r1"
RESULT = ROOT / "learning/runs/v2-orchestration/postovernight-long-D2-guard-diagnosis-opus-r1-result.json"


def read(path):
    return json.loads(path.read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path):
    return str(path.relative_to(ROOT))


def save_new(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def atomic_json(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    now = datetime.now(timezone.utc).isoformat()
    assert ROOT == Path("/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79")
    before = OUT / "before"
    assert sha(STATE) == sha(before / "state.json"), "Concurrent ledger change"
    state = read(STATE)
    assert state["active_long_campaign"] is None
    assert state["scheduler_enabled"] is False
    assert state["post_overnight_long_D2"]["single_use_consumed"] is True
    assert state["post_overnight_long_D2"]["retry_authorized"] is False
    task = state["tasks"]["postovernight_long_D2_guard_diagnosis_opus_r1"]
    native = state["native_independent_work"]["long_D2_failure_result_audit_r1"]
    assert task["result_ingested"] is False and native["result_ingested"] is False
    raw = read(RESULT)["structuredContent"]
    assert raw["taskId"] == task["task_id"]
    assert raw["status"] == "completed" and not raw["hasPendingChildRuns"]

    # These parent documents were deliberately updated after the first live
    # verification. Preserve and verify their exact pre-closeout input bytes.
    originals = {
        str(ROOT / "learning/runs/v2-orchestration/state.json"): before / "state.json",
        str(ROOT / "docs/v2-foundation-progress.md"): before / "v2-foundation-progress.md",
        str(ROOT / "docs/v2-long-D2-results-2026-10-24.md"): before / "v2-long-D2-results-2026-10-24.md",
    }
    diagnosis_inputs = read(DIAG / "input-hashes.json")
    assert len(diagnosis_inputs) == 36
    for path, entry in diagnosis_inputs.items():
        current = ROOT / path
        checked = originals.get(str(current), current)
        assert checked.stat().st_size == entry["bytes"] and sha(checked) == entry["sha256"], path
    diagnosis_receipt = read(DIAG / "receipt.json")
    for path, digest in diagnosis_receipt["outputs_sha256"].items():
        assert sha(DIAG / path) == digest, path
    audit_manifest = read(AUDIT / "artifact-manifest.json")
    assert len(audit_manifest["files"]) == 11
    for path, digest in audit_manifest["files"].items():
        assert sha(AUDIT / path) == digest, path
    audit_inputs = read(AUDIT / "input-sha256-manifest.json")
    assert not audit_inputs["mismatches"]
    for label in ("files", "end_files"):
        assert len(audit_inputs[label]) == 9936
        for path, digest in audit_inputs[label].items():
            current = Path(path) if Path(path).is_absolute() else ROOT / path
            assert sha(originals.get(str(current), current)) == digest, path
    audit = read(AUDIT / "audit.json")
    assert len(audit["checks"]) == 49 and all(item["passed"] for item in audit["checks"].values())
    assert audit["failure_evidence_consistent"] and not audit["accepted_successful_training"]
    assert not audit["teacher_qualified"] and not audit["training_parent_eligible"]

    scheduler = read(OUT / "scheduler-observation.json")
    own = scheduler["tasks"]
    assert len(own) == 1 and own[0]["scheduledTaskId"] == state["scheduler_task_id"]
    assert own[0]["enabled"] is False and own[0]["nextRunAt"] is None
    scheduler.pop("observed_at_utc", None)
    scheduler["observation_after_utc"] = "2026-10-24T20:07:49Z"
    scheduler["recorded_at_utc"] = now
    atomic_json(OUT / "scheduler-observation.json", scheduler)
    census = subprocess.check_output(["ps", "-axo", "pid=,pgid="], text=True)
    absence = {}
    for role, group in (("outer", 30643), ("inner", 30650), ("worker", 30714)):
        members = [int(row.split()[0]) for row in census.splitlines()
                   if len(row.split()) == 2 and int(row.split()[1]) == group]
        probe = "present"
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            probe = "ESRCH"
        assert not members and probe == "ESRCH", (role, members, probe)
        absence[role] = {"pgid": group, "census_members": members, "killpg_zero": probe,
                         "positive_absence": True}

    hashes = {relative(path): sha(path) for path in (
        DIAG / "diagnosis.md", DIAG / "plan.json", DIAG / "input-hashes.json", DIAG / "receipt.json",
        AUDIT / "audit.json", AUDIT / "artifact-manifest.json", AUDIT / "input-sha256-manifest.json",
        RESULT, OUT / "scheduler-observation.json",
        ROOT / "docs/v2-long-D2-results-2026-10-24.md", ROOT / "docs/v2-foundation-progress.md")}
    verification = {
        "observed_at_utc": now,
        "diagnosis_inputs_verified": 36, "diagnosis_receipt_outputs_verified": 3,
        "audit_artifacts_verified": 11, "audit_input_entries_verified_per_snapshot": 9936,
        "audit_snapshot_count": 2, "audit_checks_passed": 49, "mismatches": [],
        "live_input_verification_before_parent_document_edits": True,
        "recheck_uses_preserved_pre_closeout_bytes_for_known_parent_documents": True,
        "before_snapshots": {relative(path): sha(path) for path in before.iterdir()},
        "artifact_hashes": hashes, "current_owned_group_absence": absence,
        "scheduler_enabled": False, "scheduler_next_run_at": None,
        "ML_imports_inference_training_checkpoint_deserialization": False,
    }
    save_new(OUT / "verification.json", verification)
    reconciliation = {
        "schema": "long_D2_final_audit_and_diagnosis_parent_reconciliation_v1",
        "observed_at_utc": now,
        "run_id": state["post_overnight_long_D2"]["run_id"],
        "status": "accepted_retained_failure_evidence_and_qualified_diagnosis_only",
        "experiment_status": "failed_full_input_verification_guard",
        "teacher_qualified": False, "training_parent_eligible": False,
        "actual_invocations": 1, "one_shot_consumed": True,
        "retry_authorized": False, "resume_authorized": False,
        "new_training_authorized": False, "implementation_performed": False,
        "audit_checks_passed": 49, "completed_training_episodes_audited": 4306,
        "phase_updates": 51, "new_adam_steps": 6528, "partial_adam_steps": 0,
        "new_raw_frames": 3388752, "partial_rollout_raw_frames": 53153,
        "actual_wall_seconds": audit["actual_wall_seconds"],
        "evaluation_table": audit["evaluation_table"],
        "primary_failure": audit["primary_failure"],
        "maximum_full_input_gap_seconds": audit["maximum_full_input_gap_seconds"],
        "primary_vs_cleanup": "Guard failure preceded automatic cleanup SIGTERM; no external/user cancellation. Cleanup relabeled outcome but did not change rejection.",
        "cleanup_reap_seconds_after_first_failure": 0.3479244580375962,
        "source_confirmed": {
            "controller": "learning/runs/v2/postovernight-long-D2-prepare-r4/long_d2.py",
            "controller_sha256": state["post_overnight_long_D2"]["controller_source_sha256"],
            "background_trigger_seconds": 4, "maximum_interval_seconds": 5,
            "structural_headroom_seconds": 1,
            "interval_semantics": "Current verification end minus previous successful verification start; monitor also enforces age while pass is in flight.",
            "full_pin_count": 9870, "full_pin_bytes": 228611008,
            "idle_pins_only_seconds": 0.3268215410062112,
            "additional_verification": ["readonly capsule inventory and parent walks", "legacy identity rebuild", "loaded module origins and mirrors"],
            "reporting_defect_lines": [937, 938, 939, 940],
        },
        "qualifications_to_Opus": [
            "Exact background start/duration was not logged; the 0.955-1.005s range assumes prompt scheduling and is not a measured duration.",
            "The 0.450s median from resource-sample spacing is a heuristic containing other work; concurrent force/background sampling complicates classification.",
            "A twofold background slowdown, measured CPU duty and actual disk throughput are not established. Arithmetic volume/cadence estimates are not loaded-system measurements.",
            "GIL/CPU contention and IO/page-cache delay remain hypotheses. The verified guard violation does not establish a learning defect or eliminate all latent numerical/code defects.",
            "The guard's conservative interval semantics are intentional and must stay unchanged.",
            "Adding schedule timestamps is optional and needs separate reconciliation of the protected run_schedule block.",
            "Opus hashed governing documents and inspected ledger keys only. Parent read the full corrected governing documents and retained v2 constraints.",
        ],
        "future_proposal_only": {
            "implemented": False, "tests_executed": False, "training_authorized": False,
            "initial_trigger_seconds": 2, "unchanged_strict_limit_seconds": 5,
            "required_instrumentation": ["per-pass start/end", "trigger delay", "lock wait", "component durations", "thread CPU time"],
            "reporting": "Keep primary outcome/error; record cleanup cancellation separately.",
            "preserved_invariants": ["all 9870 pins", "9675 old-pin union", "75 legacy sources", "capsule/origin checks", "forced update/evaluation checks", "conservative interval semantics", "no caches, dropped pins, tolerance or higher limit"],
            "conditional_larger_fallback": "Process-isolated verifier only if earlier admission and instrumented synthetic stress show a need; requires separate lifecycle review.",
            "gates": ["new implementation and stdlib regressions/stress", "frozen free adversarial review or supported recorded fallback", "parent reconciliation", "fresh explicit training authorization and registered identity", "eligible audited D1 parent; failed weights excluded"],
        },
        "limitations": audit["limitations"],
        "final_artifact_hashes": hashes,
        "verification": relative(OUT / "verification.json"),
        "verification_sha256": sha(OUT / "verification.json"),
        "preserved_original_receipts": True,
        "active_long_campaign": None, "active_readonly_tasks_for_this_experiment": [],
        "scheduler_enabled": False,
    }
    save_new(OUT / "parent-reconciliation.json", reconciliation)
    reconciliation_path = relative(OUT / "parent-reconciliation.json")
    reconciliation_hash = sha(OUT / "parent-reconciliation.json")
    task.update(status="completed", workState="result_available", result_ingested=True,
                ingested_at_utc=now, parent_reconciled=True,
                result_receipt=relative(RESULT), result_receipt_sha256=sha(RESULT),
                parent_reconciliation=reconciliation_path,
                parent_reconciliation_sha256=reconciliation_hash,
                verdict="qualified_diagnosis_accepted;future_proposal_only_no_implementation")
    native.update(status="completed_retained_failure_evidence_consistent", result_ingested=True,
                  ingested_at_utc=now, parent_reconciled=True,
                  receipt=relative(AUDIT / "audit.json"), receipt_sha256=sha(AUDIT / "audit.json"),
                  parent_reconciliation=reconciliation_path, checks_passed=49,
                  learning_passed=False, training_parent_eligible=False)
    long_run = state["post_overnight_long_D2"]
    long_run.update(status="failed_one_shot;final_audit_complete;no_active_work",
                    final_audit_parent_reconciliation=reconciliation_path,
                    final_audit_parent_reconciliation_sha256=reconciliation_hash,
                    failure_evidence_audit=relative(AUDIT / "audit.json"),
                    failure_evidence_audit_sha256=sha(AUDIT / "audit.json"),
                    guard_diagnosis=relative(DIAG / "diagnosis.md"),
                    guard_diagnosis_sha256=sha(DIAG / "diagnosis.md"),
                    report="docs/v2-long-D2-results-2026-10-24.md",
                    report_sha256=sha(ROOT / "docs/v2-long-D2-results-2026-10-24.md"),
                    audit_checks_passed=49, completed_training_episodes_audited=4306,
                    new_training_authorized=False, resume_authorized=False,
                    guard_fix_implemented=False, guard_fix_status="proposal_only",
                    authorization_consumed=True, audit_completed_at_utc=now)
    state.update(status="postovernight_long_D2_one_shot_failed;audits_complete;no_active_work",
                 last_update_at_utc=now,
                 scheduler_disabled_verified_at_utc=now,
                 suggested_next_work="Proposed guard admission/instrumentation/reporting repair only. No new implementation or training started; one-shot consumed, retry/resume not authorized.",
                 next_actions=["No active work remains for the consumed one-shot experiment.",
                               "Retain failed artifacts and qualified diagnosis; proposed future guard repair remains unimplemented.",
                               "Any new training requires fresh explicit authorization and a newly reviewed frozen registration; no failed-weight resume or D3/B/E/student work."])
    assert sha(STATE) == sha(before / "state.json"), "Concurrent ledger change before replacement"
    atomic_json(STATE, state)
    save_new(OUT / "state-update-receipt.json", {
        "updated_at_utc": now, "atomic_os_replace": True,
        "state_before_sha256": sha(before / "state.json"), "state_after_sha256": sha(STATE),
        "ingested_once": ["postovernight_long_D2_guard_diagnosis_opus_r1", "long_D2_failure_result_audit_r1"],
        "parent_reconciliation_sha256": reconciliation_hash,
    })
    print(json.dumps({"status": state["status"], "audit_checks_passed": 49,
                      "reconciliation": reconciliation_path, "retry_started": False}))


if __name__ == "__main__":
    main()
