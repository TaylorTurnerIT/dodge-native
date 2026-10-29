#!/usr/bin/env python3
"""Check or explicitly apply one user-authorized DODGE-013 metadata exception.

Default and --check-only modes write only new, immutable files in this helper's
parent directory. --apply requires an independent review acceptance bound to this
source and the exact check-only input manifest. No strict observer failure is
rewritten or represented as a successful strict observer pass.
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import tempfile

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CONTRACT = HERE / "exception-protocol.json"
REVIEW_SCHEMA = HERE / "review-acceptance-schema.json"
AUTH = HERE / "user-authorization.json"  # Root-owned; read only.
INCIDENT = ROOT / "learning/runs/v2/qualification-r2-integrity-incident-parent-20261029-r1"
PROPOSAL = INCIDENT / "metadata-exception-proposal.json"
FIRST_FAILURE = INCIDENT / "first-integrity-failure.json"
FORENSIC = ROOT / "learning/runs/v2/one-frame-training-comparison-execution-review-luna-20261029-r2/forensic-review-r4.json"
INCIDENT_OPERATOR_SNAPSHOT = INCIDENT / "operator-snapshot-before-launch.json"
PARENT = ROOT / "learning/runs/v2/one-frame-training-comparison-parent-20261029-r2"
CAPSULE = ROOT / "learning/runs/v2/one-frame-training-comparison-luna-20261029-r2"
QROOT = CAPSULE / "qualification-control"
RUN_ID = "one-frame-training-resource-qualification-20261029-r2"
DISPATCH = QROOT / "dispatch" / RUN_ID
REGISTRATION = QROOT / "registration-final-r4.json"
ENVELOPE = QROOT / "launch-envelope.json"
OBSERVATION = DISPATCH / "observation.json"
EXECUTION_RESULT = DISPATCH / "execution-result.json"
OBSERVER_FINALIZATION = DISPATCH / "observer-finalization.json"
OBSERVER_RESOURCES = DISPATCH / "observer-resources.jsonl"
PARENT_EXECUTION = QROOT / "parent-execution.json"
EXECUTION_EXIT = QROOT / "execution-exit.json"
LOCAL_AUDIT = QROOT / "local-terminal-audit.json"
WORKER_LAUNCH = DISPATCH / "worker-launch.json"
WORKER_RESULT = QROOT / "worker-output" / "worker-result.json"
OUTPUT = QROOT / "worker-output"
INPUT_MANIFEST = HERE / "check-only-input-manifest-r2.json"
CHECK_REPORT = HERE / "check-only-report-r2.json"
CANDIDATE_CERT = HERE / "exception-acceptance-candidate-r2.json"
FINAL_CERT = HERE / "exception-acceptance-r2.json"
OWN_ARTIFACT_MANIFEST = HERE / "parent-exception-artifact-manifest-r2.json"
HELPER_MANIFEST = HERE / "helper-manifest-r2.json"
AUDIT = QROOT / "parent-terminal-audit.json"
RELEASE = QROOT / "lease-release.json"
SUPERVISOR_ARTIFACT_MANIFEST = DISPATCH / "artifact-manifest.json"


def sha(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path: Path | str):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field: " + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def need(ok, message):
    if not ok:
        raise ValueError(message)


def write_new(path: Path, value):
    """Create one JSON file without replacement and fsync its directory."""
    path = Path(path)
    need(not os.path.lexists(path), "refuse to replace existing file: " + str(path))
    fd, staged = tempfile.mkstemp(prefix="." + path.name + ".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staged, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(staged)


def pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def snapshot_file(path: Path | str, files: dict[str, str]):
    p = Path(path)
    need(p.is_file(), "required input file missing: " + str(p))
    files[str(p)] = sha(p)


def snapshot_pins(pins: dict, files: dict[str, str], *, exception_path=None,
                  exception_expected=None, exception_actual=None):
    need(type(pins) is dict, "pin mapping must be an object")
    mismatches = []
    for raw_path, expected in pins.items():
        p = Path(raw_path)
        need(p.is_file(), "pinned input is missing: " + raw_path)
        actual = sha(p)
        files[raw_path] = actual
        if actual != expected:
            mismatches.append({"path": raw_path, "expected_sha256": expected,
                               "actual_sha256": actual})
    if exception_path is not None:
        need(mismatches == [{"path": exception_path,
                             "expected_sha256": exception_expected,
                             "actual_sha256": exception_actual}],
             "envelope does not have exactly the one user-approved metadata mismatch")
    else:
        need(not mismatches, "registered input pin drift: " + repr(mismatches))
    return mismatches


def load_candidate():
    contract = read(CONTRACT)
    auth = read(AUTH)
    proposal = read(PROPOSAL)
    forensic = read(FORENSIC)
    first = read(FIRST_FAILURE)
    need(contract["schema"] == "dodge013_r2_metadata_exception_helper_contract_v1"
         and contract["status"] == "source_only_pending_independent_review",
         "helper contract identity differs")
    need(sha(PROPOSAL) == auth["approved_proposal_sha256"]
         and str(PROPOSAL.resolve()) == auth["approved_proposal_path"],
         "user authorization does not pin the exact proposal")
    need(auth["schema"] == "dodge013_user_authorized_single_metadata_exception_v1"
         and auth["authorized"] is True
         and auth["approved_question"] == "May I accept the documented status-file exception and continue through remaining launch checks?"
         and auth["user_message"] == "Yep, go."
         and auth["qualification_rerun_authorized"] is False
         and auth["restore_or_rewrite_pinned_metadata_authorized"] is False
         and auth["code_runtime_recipe_seed_limit_change_authorized"] is False,
         "user authorization scope differs")
    scope = contract["scope"]
    need(auth["exception_scope"] == proposal["exception_scope"]
         and auth["exception_scope"]["file"] == scope["file"]
         and auth["exception_scope"]["expected_sha256"] == scope["expected_sha256"]
         and auth["exception_scope"]["actual_sha256"] == scope["actual_sha256"]
         and auth["exception_scope"]["reason"] == scope["reason"],
         "authorization and proposal do not define the same exact exception")
    need(proposal["schema"] == "dodge013_specific_metadata_exception_proposal_v1"
         and proposal["status"] == "proposed_not_authorized_not_applied"
         and proposal["would_not_claim_original_strict_check_passed"] is True
         and proposal["would_not_restore_or_erase_failed_evidence"] is True
         and proposal["would_not_retry_training_or_reuse_disposable_weights"] is True,
         "proposal scope or preservation boundary differs")
    need(proposal["independent_forensic_review_path"] == str(FORENSIC.relative_to(ROOT))
         and sha(FORENSIC) == proposal["independent_forensic_review_sha256"]
         == contract["expected_forensic_review_sha256"],
         "independent forensic review pin differs")
    need(proposal["incident_sha256"] == sha(FIRST_FAILURE),
         "original integrity incident pin differs")
    need(scope["file"] == contract["scope"]["file"]
         and scope["expected_sha256"] == contract["scope"]["expected_sha256"]
         and scope["actual_sha256"] == sha(scope["file"])
         and scope["actual_sha256"] == contract["scope"]["actual_sha256"],
         "current operator metadata does not match the one approved drift")
    need(sha(INCIDENT_OPERATOR_SNAPSHOT) == contract["expected_before_launch_operator_sha256"],
         "original incident operator snapshot changed")
    archived_operator = PARENT / "before-parent-approval-r3" / "operator-handoff.json"
    need(sha(archived_operator) == contract["expected_before_launch_operator_sha256"],
         "original parent operator archive changed")
    need(first["schema"] == "dodge013_r2_first_integrity_failure_v1"
         and first["run_id"] == RUN_ID
         and first["status"] == "failed_qualification_preserved_no_formal_launch"
         and first["strict_parent_audit_accepted"] is False
         and first["actual_worker_launch_count"] == 1
         and first["formal_training_launched"] is False,
         "original failure disposition differs")
    need(forensic["schema"] == "dodge013_failed_qualification_forensic_review_v1"
         and forensic["disposition"]["qualification_acceptance"].startswith("not accepted")
         and forensic["disposition"]["retry_or_replay_authorized"] is False
         and forensic["launch_identity"]["envelope_pin_mismatches"] == [{
             "actual_sha256": scope["actual_sha256"],
             "expected_sha256": scope["expected_sha256"],
             "path": scope["file"]}],
         "forensic review no longer pins the same sole mismatch")
    return contract, auth, proposal, forensic, first


def evaluate():
    """Read-only recomputation. Returns report and every input hash read."""
    contract, auth, proposal, forensic, first = load_candidate()
    files: dict[str, str] = {}
    for p in (CONTRACT, REVIEW_SCHEMA, Path(__file__), AUTH, PROPOSAL, FIRST_FAILURE, FORENSIC,
              INCIDENT_OPERATOR_SNAPSHOT, PARENT / "before-parent-approval-r3" / "operator-handoff.json",
              PARENT / "operator-handoff.json", REGISTRATION, ENVELOPE, OBSERVATION,
              EXECUTION_RESULT, OBSERVER_FINALIZATION, OBSERVER_RESOURCES,
              PARENT_EXECUTION, EXECUTION_EXIT, LOCAL_AUDIT, WORKER_LAUNCH, WORKER_RESULT,
              QROOT / "attempt.claimed", QROOT / "launch.claimed",
              DISPATCH / "dispatch.claimed", DISPATCH / "supervisor.claimed",
              CAPSULE / "source-manifest-r3.json", CAPSULE / "runtime-clean-r2-manifest.json",
              PARENT / "qualification-protocol.json", PARENT / "runtime-acceptance.json",
              PARENT / "qualification-gate-acceptance-r4.json",
              PARENT / "qualification-parent-approval-r4.json",
              ROOT / "learning/runs/v2-orchestration/state.json"):
        snapshot_file(p, files)
    reg = read(REGISTRATION)
    envelope = read(ENVELOPE)
    q = read(PARENT / "qualification-protocol.json")
    source_manifest = read(CAPSULE / "source-manifest-r3.json")
    runtime_manifest_path = Path(reg["runtime_manifest_path"])
    runtime_manifest = read(runtime_manifest_path)
    source_acceptance = read(PARENT / "source-acceptance-r3.json")
    runtime_acceptance = read(PARENT / "runtime-acceptance.json")
    gate_acceptance = read(PARENT / "qualification-gate-acceptance-r4.json")
    parent_approval = read(PARENT / "qualification-parent-approval-r4.json")
    reg_sha = sha(REGISTRATION)
    env_sha = sha(ENVELOPE)
    exception_path = contract["scope"]["file"]
    mismatch = snapshot_pins(envelope["pins"], files, exception_path=exception_path,
                             exception_expected=contract["scope"]["expected_sha256"],
                             exception_actual=contract["scope"]["actual_sha256"])
    need(len(envelope["pins"]) == contract["envelope_pin_count"],
         "envelope pin count differs")
    reg_mismatch = snapshot_pins(reg["input_pins"], files)
    need(not reg_mismatch and len(reg["input_pins"]) == contract["registration_input_pin_count"],
         "registration inputs changed")
    source_root = CAPSULE
    for name, digest in source_manifest["files"].items():
        snapshot_file(source_root / name, files)
        need(files[str(source_root / name)] == digest, "source member hash differs: " + name)
    runtime_root = Path(runtime_manifest["runtime_root"])
    for name, digest in runtime_manifest["files"].items():
        snapshot_file(runtime_root / name, files)
        need(files[str(runtime_root / name)] == digest, "runtime member hash differs: " + name)
    snapshot_pins(first["evidence_pins"], files)
    need(len(source_manifest["files"]) == contract["source_member_count"]
         and len(runtime_manifest["files"]) == contract["runtime_member_count"]
         and len(reg["source_files"]) == contract["source_member_count"]
         and len(reg["runtime_files"]) == contract["runtime_member_count"]
         and reg["source_files"] == source_manifest["files"]
         and reg["runtime_files"] == runtime_manifest["files"],
         "source/runtime registration member maps differ")
    need(sha(REGISTRATION) == contract["expected_registration_sha256"] == reg_sha
         and sha(ENVELOPE) == contract["expected_envelope_sha256"] == env_sha,
         "qualification registration or launch envelope changed")
    need(reg["schema"] == "one_frame_training_comparison_registration_v1"
         and reg["status"] == "parent_registered" and reg["launch_authority"] is False
         and reg["phase"] == "qualification" and reg["run_id"] == RUN_ID
         and reg["formal_run_id"] == contract["formal_run_id"],
         "qualification registration identity/status differs")
    need(reg["source_manifest_sha256"] == sha(CAPSULE / "source-manifest-r3.json")
         and reg["runtime_manifest_sha256"] == sha(runtime_manifest_path)
         and reg["runtime_root"] == runtime_manifest["runtime_root"]
         and runtime_manifest["runtime_root"] == str(runtime_root.resolve()),
         "registered source/runtime origin differs")
    need(q["run_id"] == RUN_ID and q["launch_authority"] is False
         and q["limits"] == reg["limits"]
         and q["gameplay_frame_target_per_arm"] == reg["gameplay_frame_target_per_arm"] == 458816
         and q["gameplay_frame_cap_per_arm"] == 524544
         and q["max_PPO_updates_per_arm"] == 8
         and q["wall_cap_seconds"] == 1800
         and q["RSS_bytes"] == contract["rss_limit_bytes"]
         and q["MPS_driver_bytes"] == contract["mps_limit_bytes"],
         "qualification contract or limits differ")
    need(envelope["schema"] == "one_frame_training_comparison_envelope_v1"
         and envelope["run_id"] == RUN_ID and envelope["phase"] == "qualification"
         and envelope["registration_sha256"] == reg_sha
         and envelope["registration"] == str(REGISTRATION.resolve())
         and env_sha == forensic["launch_identity"]["envelope_sha256"],
         "frozen envelope identity differs")
    need(source_acceptance.get("status") == "accepted"
         and source_acceptance.get("source_manifest_sha256") == reg["source_manifest_sha256"]
         and runtime_acceptance.get("status") == "accepted"
         and runtime_acceptance.get("runtime_manifest_sha256") == reg["runtime_manifest_sha256"],
         "fresh source/runtime acceptance receipts differ")
    need(gate_acceptance.get("status") == "accepted"
         and gate_acceptance.get("registration_sha256") == reg_sha
         and parent_approval.get("registration_sha256") == reg_sha
         and parent_approval.get("status") == "parent_authorized_exactly_once_bounded_training_resource_qualification",
         "qualification gate or parent authorization differs")
    # Current registration pins all 33 current files. The frozen envelope permits
    # one and only one mismatch, named by authorization and independent review.
    need(len(mismatch) == 1, "exception mismatch count differs")
    need(sha(FIRST_FAILURE) == first["incident_sha256"] if "incident_sha256" in first else True,
         "first-failure incident binding differs")
    need(all(Path(k).is_file() and sha(k) == v for k, v in first["evidence_pins"].items()),
         "one or more original failure evidence pins changed")
    # Registration and phase lineage. Do not invoke binding.validate_static: it
    # must reject the strict envelope pin drift. Its normal receipt validator is
    # safe to call and does not decide observer acceptance.
    need(reg["qualification_protocol_path"] == str((PARENT / "qualification-protocol.json").resolve())
         and reg["qualification_protocol_sha256"] == sha(PARENT / "qualification-protocol.json")
         and reg["source_manifest_path"] == str((CAPSULE / "source-manifest-r3.json").resolve())
         and reg["runtime_manifest_path"] == str(runtime_manifest_path.resolve()),
         "registration phase/source/runtime paths differ")
    formal_path = Path(reg["formal_registration_path"])
    snapshot_file(formal_path, files)
    need(sha(formal_path) == reg["formal_registration_sha256"], "formal draft registration pin differs")
    need(envelope["control"] == str(DISPATCH.resolve()), "phase control directory differs")
    phase_files = [OBSERVATION, EXECUTION_RESULT, OBSERVER_FINALIZATION, PARENT_EXECUTION,
                   EXECUTION_EXIT, WORKER_LAUNCH]
    docs = {p.name: read(p) for p in phase_files}
    obs = read(OBSERVATION); execution_result = read(EXECUTION_RESULT)
    finalization = read(OBSERVER_FINALIZATION); parent_exec = read(PARENT_EXECUTION)
    exit_doc = read(EXECUTION_EXIT); launch = read(WORKER_LAUNCH)
    exception_error = "ValueError('pin drift: " + exception_path + "')"
    need(obs["status"] == execution_result["status"] == finalization["status"] == "failed"
         and obs["first_event"] == execution_result["first_event"]
         and obs["first_event"] == {"kind": "observer_failure", "error": exception_error,
                                     "monotonic": obs["first_event"]["monotonic"]}
         and finalization.get("status") == "failed",
         "original strict observer failure is not the single authorized pin drift")
    need(obs["registration_sha256"] == execution_result["registration_sha256"] == reg_sha
         and obs["envelope_sha256"] == execution_result["envelope_sha256"] == env_sha
         and obs["observed_worker_raw_exit"] == execution_result["observed_worker_raw_exit"] == 0
         and obs["directly_reaped"] is True and execution_result["directly_reaped"] is True
         and obs["owned_group_absent"] is True and execution_result["owned_group_absent"] is True,
         "worker raw exit/direct-reap/group evidence differs")
    need(exit_doc["raw_observer_exit_code"] == 1 and exit_doc["observer_directly_reaped"] is True
         and exit_doc["registration_sha256"] == reg_sha and exit_doc["envelope_sha256"] == env_sha
         and parent_exec["observer_pid"] == exit_doc["observer_pid"]
         and parent_exec["observer_pgid"] == exit_doc["observer_pgid"]
         and launch["worker_pid"] == obs["worker_pid"]
         and launch["owned_pgid"] == obs["owned_pgid"]
         and launch["registration_sha256"] == reg_sha,
         "observer exit or supervisor/worker identity differs")
    need(forensic["observer_parent_evidence"]["observer_raw_exit_code"] == 1
         and forensic["observer_parent_evidence"]["observed_worker_raw_exit"] == 0,
         "forensic review does not match direct observer/worker exits")
    pids = [(obs["worker_pid"], obs["owned_pgid"]),
            (exit_doc["observer_pid"], exit_doc["observer_pgid"])]
    for pid, pgid in pids:
        need(type(pid) is int and type(pgid) is int and not pid_exists(pid)
             and not group_exists(pgid), "recorded worker/observer PID or process group remains live")
    limits = q["limits"]
    need(0 <= read(WORKER_RESULT)["elapsed_seconds"] < limits["work_seconds"]
         and 0 <= obs["elapsed_seconds"] < limits["total_seconds"]
         and 0 <= execution_result["elapsed_seconds"] < limits["total_seconds"]
         and 0 <= exit_doc["elapsed_seconds"] < limits["total_seconds"]
         and 0 <= finalization["elapsed_seconds"] < limits["total_seconds"]
         and 0 <= finalization["elapsed_seconds"] - execution_result["elapsed_seconds"] <= limits["cleanup_seconds"],
         "work, total or cleanup deadline exceeded")
    need(obs["deadline_consumed"] is False
         and obs["max_aggregate_rss_bytes"] <= limits["rss_bytes"]
         and obs["final_observer_peak_rss_bytes"] <= limits["rss_bytes"],
         "observer deadline or RSS boundary differs")
    observer_rows = []
    with OBSERVER_RESOURCES.open("r") as stream:
        for line_number, line in enumerate(stream, 1):
            row = json.loads(line)
            need(type(row.get("aggregate_rss_bytes")) is int
                 and type(row.get("elapsed_seconds")) in (int, float)
                 and row["aggregate_rss_bytes"] <= limits["rss_bytes"],
                 "observer resource journal exceeds RSS limit at line " + str(line_number))
            observer_rows.append(row)
    need(observer_rows and max(row["aggregate_rss_bytes"] for row in observer_rows)
         == obs["max_aggregate_rss_bytes"], "observer resource maximum differs")
    cache = Path(reg["import_policy"]["pycache_prefix"])
    need(cache.is_dir() and not cache.is_symlink() and not any(cache.iterdir()),
         "qualification bytecode cache is not empty")
    # The exact output contract and all journal/stream/update/resource math are
    # recomputed through the frozen source terminal validator.
    need(not WORKER_RESULT.is_symlink(), "worker result is not a regular file")
    actual_output = {}
    for entry in OUTPUT.iterdir():
        need(entry.is_file() and not entry.is_symlink(), "worker output contains non-flat/non-regular entry")
        actual_output[entry.name] = sha(entry)
    need(set(actual_output) == set(contract["output_files"]),
         "worker output is not exactly three flat regular files")
    worker = read(WORKER_RESULT)
    need(worker["status"] == "completed" and worker["checkpoint_writes"] == 0
         and worker["evaluation_calls"] == 0 and worker["training_eligible"] is False
         and worker["no_checkpoint_writes"] is True and worker["no_evaluation_seed_use"] is True
         and worker["no_formal_weight_reuse"] is True and worker["no_retry"] is True,
         "worker completion or disposable-output boundary differs")
    if str(CAPSULE) not in sys.path:
        sys.path.insert(0, str(CAPSULE))
    import binding as b
    import terminal
    source = b.check_source()
    runtime, runtime_root = b.runtime_files()
    need(len(source["files"]) == contract["source_member_count"]
         and len(runtime["files"]) == contract["runtime_member_count"],
         "source or runtime member count differs")
    evidence = terminal.validate_qualification_outputs(reg, worker, reg_sha)
    local = read(LOCAL_AUDIT)
    need(local["schema"] == "one_frame_training_comparison_terminal_audit_v1"
         and local["run_id"] == RUN_ID and local["registration_sha256"] == reg_sha
         and local["worker_result_sha256"] == sha(WORKER_RESULT)
         and local["audit"] == evidence and local["launch_authority"] is False
         and local["training_eligible"] is False,
         "recorded local terminal recomputation differs")
    # Check no parent disposition already exists; this helper never overwrites it.
    pending = Path(reg["state_path"]).with_name("state.one-frame-training-comparison.pending.json")
    state_path = Path(reg["state_path"])
    state = read(state_path)
    need(state.get(reg["lease_key"]) == reg["expected_lease"] == q["expected_lease"]
         and all(state.get(key) is None for key in
                 ("active_inference_diagnostic", "active_inference_campaign", "active_inference_lease"))
         and state.get("training_hold", {}).get("active") is not True
         and not os.path.lexists(pending),
         "exact qualification lease/other leases/hold/pending state differs")
    need(not AUDIT.exists() and not RELEASE.exists() and not SUPERVISOR_ARTIFACT_MANIFEST.exists(),
         "a terminal disposition or supervisor manifest already exists")
    need(not os.path.lexists(FINAL_CERT) and not os.path.lexists(OWN_ARTIFACT_MANIFEST),
         "exception apply output already exists")
    # Preserve every existing control input and original failure receipt in the snapshot.
    files[str(OUTPUT / "training.jsonl")] = sha(OUTPUT / "training.jsonl")
    files[str(OUTPUT / "resources.jsonl")] = sha(OUTPUT / "resources.jsonl")
    evidence_summary = {
        "status": evidence["status"], "arms": evidence["arms"],
        "peak_rss_bytes": evidence["resources"]["peak_rss_bytes"],
        "peak_mps_driver_bytes": evidence["resources"]["peak_mps_driver_bytes"],
        "resource_samples": evidence["resources"]["samples"],
        "checkpoint_writes": evidence["checkpoint_writes"],
        "evaluation_calls": evidence["evaluation_calls"],
        "no_checkpoint_writes": evidence["no_checkpoint_writes"],
        "no_evaluation_seed_use": evidence["no_evaluation_seed_use"],
        "automatic_selection": evidence["automatic_selection"],
        "promoted": evidence["promoted"], "training_eligible": evidence["training_eligible"]}
    report = {
        "schema": "dodge013_metadata_exception_check_only_report_v1",
        "status": "check_only_passed_pending_independent_review",
        "acceptance_mode": "user_authorized_specific_metadata_exception",
        "original_strict_observer_passed": False,
        "sole_exception": mismatch[0],
        "observer_raw_exit_code": 1,
        "worker_raw_exit_code": 0,
        "worker_directly_reaped": True,
        "observer_directly_reaped": True,
        "worker_and_observer_groups_absent": True,
        "resource_evidence": evidence_summary,
        "qualification_limits": limits,
        "registration_sha256": reg_sha,
        "envelope_sha256": env_sha,
        "source_manifest_sha256": reg["source_manifest_sha256"],
        "runtime_manifest_sha256": reg["runtime_manifest_sha256"],
        "source_member_count": len(source["files"]),
        "runtime_member_count": len(runtime["files"]),
        "registration_pin_count": len(reg["input_pins"]),
        "envelope_pin_count": len(envelope["pins"]),
        "input_file_count": len(files),
        "worker_output_files": actual_output,
        "supervisor_artifact_manifest_present": False,
        "lease_cleared": False,
        "launch_authority": False,
        "formal_training_authorized": False,
    }
    return report, files, evidence, actual_output, reg, obs, exit_doc, state


def check_only():
    report, files, evidence, output_manifest, reg, obs, exit_doc, state = evaluate()
    file_manifest = {"schema": "dodge013_metadata_exception_input_manifest_v1",
                     "files": dict(sorted(files.items()))}
    write_new(INPUT_MANIFEST, file_manifest)
    manifest_sha = sha(INPUT_MANIFEST)
    report["input_manifest_sha256"] = manifest_sha
    candidate = {
        "schema": "dodge013_parent_exception_acceptance_candidate_v1",
        "status": "candidate_pending_independent_review_and_explicit_apply",
        "acceptance_mode": "user_authorized_specific_metadata_exception",
        "original_strict_observer_passed": False,
        "scope": read(CONTRACT)["scope"],
        "authorization_sha256": sha(AUTH),
        "proposal_sha256": sha(PROPOSAL),
        "forensic_review_sha256": sha(FORENSIC),
        "input_manifest_sha256": manifest_sha,
        "review_acceptance_schema_path": str(REVIEW_SCHEMA.resolve()),
        "review_acceptance_schema_sha256": sha(REVIEW_SCHEMA),
        "registration_sha256": sha(REGISTRATION),
        "worker_result_sha256": sha(WORKER_RESULT),
        "observer_raw_exit_code": 1,
        "worker_raw_exit_code": 0,
        "lease_cleared": False,
        "launch_authority": False,
        "formal_training_authorized": False,
    }
    write_new(CHECK_REPORT, report)
    write_new(CANDIDATE_CERT, candidate)
    return {"status": report["status"], "input_manifest_sha256": sha(INPUT_MANIFEST),
            "report_sha256": sha(CHECK_REPORT), "candidate_certificate_sha256": sha(CANDIDATE_CERT),
            "original_strict_observer_passed": False, "lease_cleared": False}


def validate_review(path: Path, digest: str, helper_sha: str, manifest_sha: str):
    need(sha(path) == digest, "independent review acceptance pin differs")
    review = read(path)
    schema = read(REVIEW_SCHEMA)
    need(schema.get("schema") == "dodge013_metadata_exception_independent_review_acceptance_schema_v1"
         and schema.get("review_document_schema") == "dodge013_metadata_exception_independent_review_acceptance_v1",
         "independent review schema contract differs")
    required = schema["required"]
    expected = {
        "schema": schema["review_document_schema"],
        "status": required["status"],
        "acceptance_mode": required["acceptance_mode"],
        "helper_path": str(Path(__file__).resolve()),
        "helper_sha256": helper_sha,
        "input_manifest_path": str(INPUT_MANIFEST.resolve()),
        "input_manifest_sha256": manifest_sha,
        "check_only_report_sha256": sha(CHECK_REPORT),
        "authorization_sha256": sha(AUTH),
        "proposal_sha256": sha(PROPOSAL),
        "original_strict_observer_passed": False,
    }
    need(all(review.get(key) == value for key, value in expected.items()),
         "independent review does not accept this exact helper/check-only input")
    return review


def replace_state(path: Path, state: dict):
    pending = path.with_name("state.one-frame-training-comparison.pending.json")
    need(not os.path.lexists(pending), "parent state pending file appeared before CAS")
    write_new(pending, state)
    os.replace(pending, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    need(read(path).get("active_long_campaign") is None,
         "lease release readback differs")


def apply(review_path: Path, review_sha: str):
    need(INPUT_MANIFEST.is_file() and CHECK_REPORT.is_file() and CANDIDATE_CERT.is_file(),
         "check-only report/manifest/candidate certificate missing")
    current_report, current_files, evidence, output_manifest, reg, obs, exit_doc, state = evaluate()
    saved_manifest = read(INPUT_MANIFEST)
    need(saved_manifest.get("schema") == "dodge013_metadata_exception_input_manifest_v1"
         and saved_manifest.get("files") == dict(sorted(current_files.items())),
         "check-only input manifest drifted; refuse apply")
    manifest_sha = sha(INPUT_MANIFEST)
    saved_report = read(CHECK_REPORT)
    need(saved_report.get("status") == "check_only_passed_pending_independent_review"
         and saved_report.get("input_manifest_sha256") == manifest_sha
         and saved_report.get("registration_sha256") == sha(REGISTRATION)
         and saved_report.get("envelope_sha256") == sha(ENVELOPE),
         "check-only report does not bind current evidence")
    helper_sha = sha(Path(__file__))
    review = validate_review(review_path, review_sha, helper_sha, manifest_sha)
    # Recheck destination absence and exact lease immediately before writes.
    need(not AUDIT.exists() and not RELEASE.exists() and not SUPERVISOR_ARTIFACT_MANIFEST.exists(),
         "terminal output appeared before apply")
    state_path = Path(reg["state_path"])
    pending = state_path.with_name("state.one-frame-training-comparison.pending.json")
    need(not os.path.lexists(pending) and state.get("active_long_campaign") == reg["expected_lease"]
         and not any(state.get(k) is not None for k in
                     ("active_inference_diagnostic", "active_inference_campaign", "active_inference_lease"))
         and state.get("training_hold", {}).get("active") is not True,
         "exact lease CAS precondition changed")
    contract = read(CONTRACT)
    certificate = {
        "schema": "dodge013_parent_metadata_exception_acceptance_v1",
        "status": "accepted_parent_exception_for_qualification_evidence",
        "acceptance_mode": "user_authorized_specific_metadata_exception",
        "original_strict_observer_passed": False,
        "scope": contract["scope"],
        "approved_question": read(AUTH)["approved_question"],
        "authorization_sha256": sha(AUTH), "proposal_sha256": sha(PROPOSAL),
        "forensic_review_sha256": sha(FORENSIC), "independent_review_acceptance_sha256": sha(review_path),
        "helper_sha256": helper_sha, "input_manifest_sha256": manifest_sha,
        "review_acceptance_schema_path": str(REVIEW_SCHEMA.resolve()),
        "review_acceptance_schema_sha256": sha(REVIEW_SCHEMA),
        "registration_sha256": sha(REGISTRATION), "envelope_sha256": sha(ENVELOPE),
        "observer_receipt_sha256": sha(OBSERVATION), "execution_exit_sha256": sha(EXECUTION_EXIT),
        "worker_result_sha256": sha(WORKER_RESULT),
        "observer_raw_exit_code": 1, "worker_raw_exit_code": 0,
        "actual_worker_launch_count": 1, "direct_reap_confirmed": True,
        "worker_and_observer_groups_absent": True,
        "lease_cleared": False, "formal_training_authorized": False,
        "launch_authority": False,
    }
    write_new(FINAL_CERT, certificate)
    exception_artifact_manifest = {
        "schema": "dodge013_parent_exception_artifact_manifest_v1",
        "artifact_manifest_kind": "parent_exception_recomputed_worker_output",
        "supervisor_artifact_manifest_was_missing": True,
        "files": output_manifest,
        "exception_certificate_sha256": sha(FINAL_CERT),
        "worker_output_sha256": sha(WORKER_RESULT),
    }
    write_new(OWN_ARTIFACT_MANIFEST, exception_artifact_manifest)
    audit = {
        "schema": "one_frame_training_comparison_terminal_audit_v1",
        "status": "parent_terminal_audit_accepted",
        "phase": "qualification", "run_id": reg["run_id"],
        "registration_sha256": sha(REGISTRATION), "envelope_sha256": sha(ENVELOPE),
        "observer_receipt_sha256": sha(OBSERVATION),
        "execution_exit_sha256": sha(EXECUTION_EXIT),
        "evidence": evidence, "worker_result_sha256": sha(WORKER_RESULT),
        "artifact_manifest": output_manifest,
        "artifact_manifest_kind": "parent_exception_recomputed_worker_output",
        "parent_exception_artifact_manifest_path": str(OWN_ARTIFACT_MANIFEST.resolve()),
        "parent_exception_artifact_manifest_sha256": sha(OWN_ARTIFACT_MANIFEST),
        "parent_exception_certificate_path": str(FINAL_CERT.resolve()),
        "parent_exception_certificate_sha256": sha(FINAL_CERT),
        "acceptance_mode": "user_authorized_specific_metadata_exception",
        "original_strict_observer_passed": False,
        "observer_status": "failed", "observer_raw_exit_code": 1,
        "observer_first_event": obs["first_event"], "worker_raw_exit_code": 0,
        "metadata_exception": contract["scope"],
        "authorization_sha256": sha(AUTH), "proposal_sha256": sha(PROPOSAL),
        "forensic_review_sha256": sha(FORENSIC),
        "worker_resources": {k: evidence["resources"][k] for k in
                              ("samples", "peak_rss_bytes", "peak_mps_driver_bytes")},
        "launch_authority": False, "automatic_selection": False,
        "promoted": False, "training_eligible": False, "lease_cleared": False,
    }
    write_new(AUDIT, audit)
    audit_sha = sha(AUDIT)
    # Exact CAS release happens only after exception certificate, artifact manifest,
    # and accepted parent audit have been fsynced. No unrelated lease may change.
    latest = read(state_path)
    need(latest.get(reg["lease_key"]) == reg["expected_lease"]
         and all(latest.get(k) is None for k in
                 ("active_inference_diagnostic", "active_inference_campaign", "active_inference_lease"))
         and latest.get("training_hold", {}).get("active") is not True
         and not os.path.lexists(pending),
         "parent state changed before exact lease release CAS")
    latest[reg["lease_key"]] = None
    latest["last_update_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    replace_state(state_path, latest)
    write_new(RELEASE, {
        "schema": "one_frame_training_comparison_lease_release_v1",
        "run_id": reg["run_id"], "registration_sha256": sha(REGISTRATION),
        "parent_terminal_audit_sha256": audit_sha, "lease_value_after_release": None,
        "release_mode": "exact_qualification_lease_cas_after_durable_parent_exception_audit",
        "acceptance_mode": "user_authorized_specific_metadata_exception",
        "exception_certificate_sha256": sha(FINAL_CERT),
        "original_strict_observer_passed": False,
    })
    return {"status": "parent_exception_applied_and_exact_lease_released",
            "audit_sha256": audit_sha, "lease_cleared": True,
            "original_strict_observer_passed": False,
            "formal_training_authorized": False}


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check-only", action="store_true", help="read inputs; write own report only (default)")
    group.add_argument("--apply", action="store_true", help="apply only with independent review pins")
    parser.add_argument("--review-acceptance", type=Path)
    parser.add_argument("--review-sha256")
    args = parser.parse_args()
    if args.apply:
        need(args.review_acceptance is not None and args.review_sha256 is not None,
             "--apply requires independently pinned --review-acceptance and --review-sha256")
        result = apply(args.review_acceptance.resolve(), args.review_sha256)
    else:
        need(args.review_acceptance is None and args.review_sha256 is None,
             "review pins are valid only with --apply")
        result = check_only()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
