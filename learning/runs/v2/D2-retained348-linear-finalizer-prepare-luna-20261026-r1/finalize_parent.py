"""Parent-only terminal acceptance for the completed retained324 linear-LR trial.

Importing this module is inert. The copied source must live in the exact parent
output directory and requires the parent's frozen review reconciliation.
"""
from collections import Counter
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "learning/runs/v2"
OWN = Path(__file__).resolve().parent
EXPECTED_OWN = BASE / "D2-retained324-linear-parent-terminal-audit-20261026-r1"
PREP = BASE / "D2-retained324-linear-integrated-luna-20261026-r4"
RUN = BASE / "D2-retained324-linear-lr-20261026-r1"
OBSERVER = BASE / "D2-retained324-linear-execution-observer-parent-20261026-r1"
AUDITOR = BASE / "D2-retained324-linear-auditor-prepare-luna-20261026-r3"
ASSEMBLY = BASE / "D2-retained324-linear-auditor-parent-assembly-20261026-r3"
REVIEW = BASE / "D2-retained324-linear-auditor-r3-review-haiku-20261026-r1/report.md"
RECONCILIATION = EXPECTED_OWN / "review-reconciliation.json"
REG_PATH = PREP / "registration-final-r2.json"
FULL_PATH = AUDITOR / "full-audit.json"
OBS_PATH = OBSERVER / "observation.json"
REG_SHA = "0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e"
FULL_SHA = "e1c32e9960e1b5dd832b88494771f01b02ef1e4f48fdb074f5f91fe4c9c9ee44"
BINDING_SHA = "a8ad01cb9012450b0a6b4d3b99c5f34772ad13fb4c15b09e924c10acd5b46186"
RECONCILIATION_SHA = "4b4e51ede5def51b44635926cbd4c0ae4345e8c68b165f2e8e9a8925c8f75b06"
REVIEW_SHA = "7bd06e8fdeae689166f230eee60beecc84b2ee1294e068e6098d312289fb7e42"
INCUMBENT = BASE / "D2-retained300-continuation-20261026-r1/checkpoint-000324-candidate.pt"
OLD_RECEIPT = BASE / "D2-retained300-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json"
INCUMBENT_SHA = "c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc"
OLD_RECEIPT_SHA = "76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08"
SELECTED_SHA = "b95228e5e2934c915597595f7eb3c8618ee5f7c2182dde1481a060d01c270369"
SCHEDULE_SPEC_SHA = "7ceed85c5dc277602f2f51937b4ac003e2013e2689341a963ce5d82d5b64c9e4"
PARENT_FULL_RECEIPT_SHA = "ffe709fe7fc142e191d7d908f8613e05b5a79a49e93b92882f235152f648cf10"
FROZEN_MANIFEST_SHA = "ec01c46db956d61fd346b8a4a01866ff7e1038ccdbd322759f4df101d2692c76"
OUTPUT_MANIFEST_SHA = "a3eab6a9edbd76957ca28e984dd554355b0c6d151ab7c6a6a4987be5933f759b"
REVIEWED_ASSEMBLY_SHA = "bd70d947f4569c146c7ae2ec8765d977eb0ea05abc0742fea95e0ea25b1a1270"
AUDITOR_SOURCE_SHA = {
    "audit_candidates.py": "4cc856c91d933c6d4723676bf53ed0df605a0049a1bb0a5b30fc6d761faeeac6",
    "binding_builder.py": "30dab9bd2369b7109c700296f5610206504bf60d28af4e412d0d1a3739fe69af",
    "lr_schedule.py": "1ac2a62de4989c30415cd4167262456299deae7cc7a7fbffc2d532ba4a8f09eb",
    "schedule_contract.py": "efaa421a3babbfd995074ae86c26731350d614dff7fdd34cefd4463e4cdf7809",
    "wrapper.py": "871bed65a8cc207c93bc6b5d77fd87ec0e78f6619273c52ce7c57446e96a3e2e",
}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def canonical_sha(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def validate_parent_guard(state, expected_lease, cancel_exists):
    need(state.get("active_long_campaign") == expected_lease, "Exact registered lease changed")
    need(not any(state.get(k) for k in ("active_inference_diagnostic", "active_inference_campaign", "active_inference_lease")),
         "Another inference lease exists")
    need(not cancel_exists and state.get("cancel_requested") in (None, False), "Cancellation present")


def validate_snapshot_unchanged(current_bytes, original_bytes):
    need(current_bytes == original_bytes, "Concurrent ledger change before replace")


def candidate_selection(candidates, incumbent_mean):
    need(set(candidates) == {"324", "336", "348", "360", "372", "384"}, "Candidate set differs")
    selected = max(candidates, key=lambda key: (candidates[key]["mean_alive_frames"], -int(key)))
    need(float(candidates[selected]["mean_alive_frames"]) > float(incumbent_mean), "No improvement over incumbent")
    return selected


def campaign_cost(previous_cost, observed_outer):
    previous = float(previous_cost)
    outer = float(observed_outer)
    need(math.isfinite(previous) and math.isfinite(outer) and previous >= 0 and outer >= 0,
         "Invalid observed resource accounting")
    return previous + outer


def schedule_field_mapping(saved, registered):
    fields = ("schedule_origin_cumulative_update", "horizon_updates", "completed_schedule_updates",
              "schedule_spec_sha256")
    mapped = {key: saved[key] for key in fields}
    need(mapped["schedule_origin_cumulative_update"] == registered["origin_cumulative_update"] == 372
         and mapped["horizon_updates"] == registered["horizon_updates"] == 60
         and mapped["schedule_spec_sha256"] == registered["spec_sha256"] == SCHEDULE_SPEC_SHA,
         "Saved schedule fields differ from registered schedule")
    need(type(mapped["completed_schedule_updates"]) is int and mapped["completed_schedule_updates"] == 24,
         "Saved schedule progress differs from selected local progress")
    return dict(saved)


def selected_performance(certificate, checkpoint_sha):
    evaluation = certificate["evaluation"]
    rows = evaluation["rows"]
    alive = sorted(row["alive_frames"] for row in rows)
    need(len(alive) == 64 and evaluation["complete"] is True
         and sum(alive) / 64 == evaluation["mean_alive_frames"]
         and sum(bool(row["terminated"]) for row in rows) == evaluation["deaths"],
         "Selected certificate is incomplete or row aggregates differ")
    causes = Counter(row["death_cause"] for row in rows if row["terminated"])
    for cause in ("normal_enemy", "static_pattern_rect", "kamikaze_enemy", "moving_pattern_rect", "kamikaze_explosion"):
        causes.setdefault(cause, 0)
    return {
        "update": 348,
        "q1_bottom16_mean": sum(alive[:16]) / 16,
        "q4_top16_mean": sum(alive[-16:]) / 16,
        "mean_alive_frames": sum(alive) / 64,
        "mean_score": evaluation["mean_score"],
        "episodes": 64,
        "deaths": evaluation["deaths"],
        "caps": evaluation["caps"],
        "death_causes": dict(causes),
        "checkpoint_sha256": checkpoint_sha,
    }


def validate_review_reconciliation():
    need(OWN == EXPECTED_OWN, "Copy exact finalizer to parent output directory before invocation")
    need({path.name for path in OWN.iterdir()} == {"finalize_parent.py", "review-reconciliation.json"},
         "Parent output directory has unexpected pre-existing files")
    need(RECONCILIATION.is_file() and sha(RECONCILIATION) == RECONCILIATION_SHA,
         "Parent review reconciliation missing or changed")
    rec = read(RECONCILIATION)
    need(rec.get("schema") == "linear_D2_parent_terminal_review_reconciliation_v1"
         and rec.get("status") == "no_blockers_full_candidate_audit_passed"
         and rec.get("parent_review_frozen") is True
         and rec.get("haiku_review_sha256") == REVIEW_SHA
         and rec.get("full_audit_sha256") == FULL_SHA
         and rec.get("binding_sha256") == BINDING_SHA
         and rec.get("all_six_candidates_audited") is True
         and rec.get("registered_artifact_hashes_verified") == 32
         and rec.get("exact_run_file_inventory") == 34
         and rec.get("unexpected_run_files") == []
         and rec.get("selected_candidate") == 348
         and rec.get("selected_checkpoint_sha256") == SELECTED_SHA
         and rec.get("selected_mean") == 3098.125
         and rec.get("previous_retained_mean") == 2939.40625
         and rec.get("actual_acceptance_published") is False
         and rec.get("lease_cleared") is False,
         "Parent review reconciliation fields differ")
    need(sha(REVIEW) == REVIEW_SHA, "Frozen Haiku review changed")
    return rec


def _assert_empty_cache(path):
    directory = Path(path)
    need(directory.is_dir(), "Required no-bytecode cache directory missing: " + str(directory))
    need(not any(directory.iterdir()), "Required no-bytecode cache is not empty: " + str(directory))


def _verify_registered_evidence(reg, full, obs, execution, worker):
    need(sha(REG_PATH) == REG_SHA and reg["run_id"] == "D2-retained324-linear-lr-20261026-r1", "Registration identity differs")
    need(sha(FULL_PATH) == FULL_SHA and full["mode"] == "full_parent_only", "Full audit identity or mode differs")
    audit = full["audit"]
    need(audit["status"] == "all_candidates_audited_pending_parent_terminal_acceptance"
         and audit["updates_audited"] == [324, 336, 348, 360, 372, 384]
         and audit["registration_sha256"] == REG_SHA
         and audit["pins_checked_before_and_after"] == 13857
         and audit["proposed_best_update"] == 348,
         "Full audit candidate or registration binding differs")
    binding = read(AUDITOR / "audit-binding.json")
    need(sha(AUDITOR / "audit-binding.json") == BINDING_SHA, "Auditor binding changed")
    frozen_path = AUDITOR / "frozen-manifest.json"
    output_manifest_path = AUDITOR / "output-manifest.json"
    reviewed_path = ASSEMBLY / "reviewed-assembly.json"
    need(sha(frozen_path) == FROZEN_MANIFEST_SHA and sha(output_manifest_path) == OUTPUT_MANIFEST_SHA
         and sha(reviewed_path) == REVIEWED_ASSEMBLY_SHA
         and full["reviewed_manifest"]["sha256"] == REVIEWED_ASSEMBLY_SHA
         and binding["reviewed_manifest"]["sha256"] == REVIEWED_ASSEMBLY_SHA,
         "Auditor frozen/output/reviewed manifests changed")
    frozen_manifest = read(frozen_path)
    output_manifest = read(output_manifest_path)
    need(frozen_manifest.get("files", {}).get("audit_candidates.py") == AUDITOR_SOURCE_SHA["audit_candidates.py"]
         and output_manifest.get("files", {}).get("frozen-manifest.json") == FROZEN_MANIFEST_SHA,
         "Auditor source manifests disagree")
    for name, digest in frozen_manifest["files"].items():
        need(sha(AUDITOR / name) == digest, "Frozen auditor file changed: " + name)
    for name, digest in output_manifest["files"].items():
        need(sha(AUDITOR / name) == digest, "Auditor output manifest file changed: " + name)
    for name, digest in AUDITOR_SOURCE_SHA.items():
        source = AUDITOR / name
        need(sha(source) == digest and binding["auditor_sources"].get(str(source)) == digest,
             "Auditor source pin differs: " + name)
    need(sha(ASSEMBLY / "full-audit-parent-receipt.json") == PARENT_FULL_RECEIPT_SHA,
         "Parent full-audit receipt changed")
    parent_audit = read(ASSEMBLY / "full-audit-parent-receipt.json")
    need(parent_audit.get("status") == "passed_parent_full_candidate_audit"
         and parent_audit.get("full_audit_sha256") == FULL_SHA
         and parent_audit.get("binding_sha256") == BINDING_SHA
         and parent_audit.get("accepted_checkpoint_or_lease_clear") is False,
         "Parent full-audit receipt differs")

    need(sha(OBS_PATH) == audit["terminal_record_sha256"][str(OBS_PATH)], "Observer receipt changed")
    need(obs["success_authoritative"] is True and obs["first_event"] is None
         and obs["cleanup_signals"] == [] and obs["launch_count"] == 1
         and obs["outer_raw_exit"] == obs["worker_raw_exit"] == 0
         and obs["outer_inclusive_wall_seconds"] <= 1800
         and obs["max_aggregate_rss_bytes"] <= 6442450944
         and all(obs[k] is True for k in ("outer_process_absent", "worker_process_absent", "worker_group_absent")),
         "Observer terminal proof failed")
    need(execution["status"] == "passed" and execution["actual_worker_launch_count"] == 1
         and execution["observed_worker_raw_exit"] == 0 and execution["directly_reaped"] is True
         and execution["owned_group_absent"] is True and execution["postflight_inputs_unchanged"] is True,
         "Execution terminal record failed")
    need(worker["status"] == "completed" and worker["first_failure"] is None
         and worker["elapsed_seconds"] <= 1790 and worker["peak_rss_bytes"] <= 6442450944
         and worker["peak_mps_driver_bytes"] <= 6442450944
         and worker["updates"] == 60 and worker["counters"]["updates"] == 60
         and worker["counters"]["environment_decisions"] == 983040
         and worker["counters"]["optimizer_steps"] == 7680
         and worker["cumulative_counters"]["updates"] == 432,
         "Completed worker accounting differs")
    need(execution["worker_pid"] == obs["execution_result"]["worker_pid"]
         and execution["owned_pgid"] == obs["execution_result"]["owned_pgid"],
         "Observer and execution process identities differ")

    # Exact run inventory and all 32 registered output hashes.
    manifest_path = RUN / "artifact-manifest.json"
    manifest_data = read(manifest_path)
    manifest = manifest_data.get("artifacts", manifest_data)
    need(set(manifest) == set(reg["expected_outputs"]), "Artifact manifest output set differs")
    for name in reg["expected_outputs"]:
        item = manifest[name]
        digest = item if isinstance(item, str) else item.get("sha256")
        need(digest == sha(RUN / name), "Registered artifact hash differs: " + name)
    names = {p.name for p in RUN.iterdir() if p.is_file()}
    need(len(reg["expected_outputs"]) == 32 and len(names) == 34
         and names == set(reg["expected_outputs"]) | {"artifact-manifest.json", "execution-result.json"},
         "Exact 34-file run inventory differs")
    need(audit["tracked_file_sha256"].get(str(manifest_path)) == sha(manifest_path), "Artifact manifest audit hash differs")
    need(audit["tracked_file_sha256"].get(str(RUN / "execution-result.json")) == sha(RUN / "execution-result.json"),
         "Execution result audit hash differs")
    for path, digest in reg["pins"].items():
        need(sha(path) == digest, "Registered source pin changed: " + path)
    for path, digest in audit["tracked_file_sha256"].items():
        need(sha(path) == digest, "Audited critical file changed: " + path)

    observer_source = OBSERVER / "observe.py"
    need(sha(observer_source) == binding["observer_source"]["sha256"]
         and reg["pins"].get(str(observer_source)) == sha(observer_source), "Observer source binding changed")
    instantiation = read(OBSERVER / "instantiation.json")
    need(sha(OBSERVER / "instantiation.json") == binding["observer_instantiation"]["sha256"]
         and instantiation["registration_sha256"] == REG_SHA
         and instantiation["observer_sha256"] == binding["observer_source"]["sha256"]
         and instantiation["actual_launches"] == 0
         and instantiation["one_shot_marker_absent"] is True,
         "Observer instantiation binding differs")

    _assert_empty_cache(reg["import_policy"]["pycache_prefix"])
    _assert_empty_cache(AUDITOR / "empty-pycache")


def _check_live_process_absence(obs, execution):
    absence = {}
    pids = (obs["observer_pid"], obs["outer_pid"], execution["worker_pid"])
    for pid in pids:
        result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "pid=,pgid=,lstart=,command="],
                                capture_output=True, text=True)
        need(result.returncode == 1 and not result.stdout.strip(), "Owned process remains: " + str(pid))
        absence[str(pid)] = {"returncode": result.returncode, "stdout": result.stdout}
    groups = {obs["outer_process_group"], execution["owned_pgid"]}
    for pgid in groups:
        need(type(pgid) is int and pgid > 1, "Invalid owned process group")
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            pass
        else:
            raise ValueError("Owned process group remains: " + str(pgid))
    return absence


def _load_selected_state(checkpoint, candidate):
    # Explicit parent commit only. CPU load reads the selected checkpoint and makes no edits.
    sys.path.insert(0, str(PREP))
    sys.path.insert(0, str(REG_PATH.parent))
    reg = read(REG_PATH)
    sys.path.insert(0, reg["runtime_root"])
    import torch
    torch.set_num_threads(2)
    import runner
    from dodge_rl.checkpoints import load_checkpoint
    from dodge_rl.identity import identity_hash

    selected = load_checkpoint(checkpoint, expected_sha256=SELECTED_SHA)
    cumulative = selected["cumulative_counters"]
    need(selected["phase_update"] == 348 and selected["local_update"] == 24
         and selected["update_progress"]["complete"] is True
         and selected["training_eligible"] is False and selected["promoted"] is False
         and cumulative["updates"] == 396,
         "Selected checkpoint update ancestry differs")
    need(selected["counters"]["updates"] == 24
         and selected["inherited_counters"]["updates"] == 372,
         "Selected checkpoint progress was reset or inferred")
    need(len(selected["next_episode_indices"]) == 64
         and all(type(value) is int and value >= 0 for value in selected["next_episode_indices"]),
         "Selected checkpoint episode indices are malformed")
    fingerprints = {
        "model": runner.fingerprint(selected["model"]),
        "Adam": runner.fingerprint(selected["optimizer"]),
        "RNG": runner.fingerprint(selected["rng"]),
    }
    need(fingerprints == candidate["component_fingerprints"], "Selected model/Adam/RNG fingerprints differ")
    lr = runner.validate_saved_schedule_lr(selected, cumulative["updates"])
    group_lrs = [group["lr"] for group in selected["optimizer"]["param_groups"]]
    need(lr == 2.2203389830508478e-05 and all(value == lr for value in group_lrs),
         "Selected saved LR or optimizer group LR differs")
    schedule_fields = schedule_field_mapping(selected["lr_schedule"], read(REG_PATH)["lr_schedule"])
    return selected, runner, fingerprints, lr, group_lrs


def _write(name, value):
    path = OWN / name
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return path


def _validate_and_finalize():
    rec = validate_review_reconciliation()
    reg = read(REG_PATH)
    full = read(FULL_PATH)
    obs = read(OBS_PATH)
    execution = read(RUN / "execution-result.json")
    worker = read(RUN / "worker-result.json")
    _verify_registered_evidence(reg, full, obs, execution, worker)
    statepath = Path(reg["state_path"])
    audit = full["audit"]

    def guard():
        raw = statepath.read_bytes()
        state = json.loads(raw)
        validate_parent_guard(state, reg["expected_lease"], Path(reg["cancel_path"]).exists())
        for path, digest in reg["pins"].items():
            need(sha(path) == digest, "Pinned input changed: " + path)
        need(sha(FULL_PATH) == FULL_SHA and sha(OBS_PATH) == audit["terminal_record_sha256"][str(OBS_PATH)]
             and sha(AUDITOR / "audit-binding.json") == BINDING_SHA
             and sha(RECONCILIATION) == RECONCILIATION_SHA and sha(REVIEW) == REVIEW_SHA,
             "Full audit/review evidence changed")
        for path, digest in audit["tracked_file_sha256"].items():
            need(sha(path) == digest, "Audited critical file changed before commit: " + path)
        _assert_empty_cache(reg["import_policy"]["pycache_prefix"])
        _assert_empty_cache(AUDITOR / "empty-pycache")
        return state, raw

    state, _ = guard()
    absence = _check_live_process_absence(obs, execution)
    candidates = audit["candidates"]
    selected_key = candidate_selection(candidates, read(OLD_RECEIPT)["performance"]["mean_alive_frames"])
    need(selected_key == "348" and rec["selected_candidate"] == 348, "Selected candidate differs from frozen reconciliation")
    checkpoint = RUN / "checkpoint-000348-candidate.pt"
    certificate_path = RUN / "development-000348.json"
    sidecar = Path(str(checkpoint) + ".json")
    need(sha(checkpoint) == SELECTED_SHA and sha(checkpoint) == candidates[selected_key]["checkpoint_sha256"],
         "Selected checkpoint changed")
    need(sha(sidecar) == candidates[selected_key]["sidecar_sha256"], "Selected sidecar changed")
    certificate = read(certificate_path)
    need(sha(certificate_path) == candidates[selected_key]["certificate_sha256"]
         and certificate["checkpoint_sha256"] == SELECTED_SHA
         and certificate["competence_passed"] is True,
         "Selected certificate identity or competence gate differs")
    performance = selected_performance(certificate, SELECTED_SHA)
    need(performance["q1_bottom16_mean"] == 867.0625 and performance["q4_top16_mean"] == 6003.875
         and performance["mean_alive_frames"] == 3098.125
         and performance["mean_alive_frames"] >= 3060
         and performance["death_causes"] == {"normal_enemy": 25, "static_pattern_rect": 15,
                                                 "kamikaze_enemy": 15, "moving_pattern_rect": 9,
                                                 "kamikaze_explosion": 0},
         "Selected performance differs from real certificate rows")
    previous_receipt = read(OLD_RECEIPT)
    need(sha(INCUMBENT) == INCUMBENT_SHA and sha(OLD_RECEIPT) == OLD_RECEIPT_SHA,
         "Original incumbent artifacts changed")
    previous_mean = previous_receipt["performance"]["mean_alive_frames"]
    selected, runner, fingerprints, effective_lr, group_lrs = _load_selected_state(checkpoint, candidates[selected_key])
    need(selected["config_sha256"] == reg["config_sha256"], "Selected checkpoint config binding differs")
    need(selected["runtime_sha256"] == reg["runtime_sha256"] and selected["native_sha256"] == reg["native"]["sha256"],
         "Selected runtime/native binding differs")
    need(selected["policy_sha256"] == reg["policy_sha256"], "Selected policy binding differs")

    outer = float(obs["outer_inclusive_wall_seconds"])
    cost_before = float(read(reg["parent"]["latest_resource_cost_anchor"]["path"])["wall_accounting"][
        "completed_campaign_resource_cost_after_seconds"])
    cost = campaign_cost(cost_before, outer)
    trajectory = float(selected["cumulative_selected_checkpoint_trajectory_wall_seconds"])
    endpoint_trajectory = float(worker["cumulative_selected_checkpoint_trajectory_wall_seconds"])
    need(trajectory == 5678.9823631240915 + selected["current_iteration_observed_outer_seconds"]
         and cost_before == 10824.835578584221 and outer == 1131.1351048339857
         and cost == 11955.970683418207 and endpoint_trajectory == 6806.37175508199,
         "Observed wall accounting differs")
    now = datetime.now(timezone.utc).isoformat()
    source_sha = sha(Path(__file__).resolve())
    evidence_files = [REG_PATH, FULL_PATH, OBS_PATH, REVIEW, RECONCILIATION,
                      ASSEMBLY / "full-audit-parent-receipt.json", AUDITOR / "audit-binding.json",
                      PREP / "runner.py", PREP / "lr_schedule.py", checkpoint, sidecar, certificate_path,
                      RUN / "execution-result.json", RUN / "worker-result.json"]
    frozen = {str(path): sha(path) for path in evidence_files}

    assembly = {
        "schema": "d2_retained348_parent_finalizer_assembly_v1",
        "status": "parent_checks_passed_before_atomic_acceptance",
        "finalizer_source_path": str(Path(__file__).resolve()),
        "finalizer_source_sha256": source_sha,
        "registration_sha256": REG_SHA, "full_audit_sha256": FULL_SHA,
        "binding_sha256": BINDING_SHA, "review_reconciliation_sha256": RECONCILIATION_SHA,
        "haiku_review_sha256": REVIEW_SHA, "selected_update": 348,
        "selected_checkpoint_sha256": SELECTED_SHA, "actual_acceptance_published": False,
    }
    _write("finalizer-assembly.json", assembly)
    audit_out = {
        "schema": "d2_retained348_linear_parent_terminal_audit_v1",
        "status": "accepted_completed_iteration_and_selected_intermediate348",
        "at_utc": now, "registration_sha256": REG_SHA, "source_pins_unchanged": 13857,
        "full_audit_path": str(FULL_PATH), "full_audit_sha256": FULL_SHA,
        "parent_review_reconciliation_path": str(RECONCILIATION),
        "parent_review_reconciliation_sha256": RECONCILIATION_SHA,
        "haiku_review_path": str(REVIEW), "haiku_review_sha256": REVIEW_SHA,
        "binding_sha256": BINDING_SHA, "all_six_candidates_audited": True,
        "candidate_means": {key: value["mean_alive_frames"] for key, value in candidates.items()},
        "selected_update": 348, "selected_checkpoint_sha256": SELECTED_SHA,
        "selected_performance": performance, "competence_passed": True,
        "qualification_passed": False, "stage_promotion_eligible": False,
        "raw_exits": {"outer": 0, "worker": 0}, "observed_outer_seconds": outer,
        "process_absence": absence, "owned_groups_absent": True,
        "raw_counters": worker["counters"], "selected_counters": selected["counters"],
        "selected_cumulative_counters": selected["cumulative_counters"],
        "selected_learner_fingerprints": fingerprints, "selected_effective_learning_rate": effective_lr,
        "selected_optimizer_group_lrs": group_lrs, "resource_limits_passed": True,
        "finalizer_source_path": str(Path(__file__).resolve()),
        "finalizer_source_sha256": source_sha,
        "frozen_evidence_sha256": frozen,
        "execution_history": "Initial executor provider failure recovered by attach-only observation. The registered campaign ran once with no campaign retry.",
        "qualification_limits": "No qualification, stage promotion, D3, B, E, or student authority.",
    }
    _write("audit.json", audit_out)
    completed = {
        "schema": "d2_completed_iteration_parent_audit_receipt_v1",
        "status": "accepted_completed_training_iteration_with_best_replacement",
        "at_utc": now, "run_id": reg["run_id"], "phase": "D2", "normal_training_iteration": True,
        "completed_local_updates": 60, "completed_phase_updates": 384,
        "counters": worker["counters"], "cumulative_counters": worker["cumulative_counters"],
        "endpoint_checkpoint_sha256": candidates["384"]["checkpoint_sha256"],
        "endpoint_update": 384, "endpoint_is_not_selected": True,
        "best_replacement": True, "selected_phase_update": 348,
        "training_continuation_eligible": False, "stage_promotion_eligible": False,
        "competence_passed": True, "qualification_passed": False,
        "checkpoint_metadata_unchanged": True, "raw_exits": {"outer": 0, "worker": 0},
        "owned_processes_and_groups_absent": True,
        "registration_path": str(REG_PATH), "registration_sha256": REG_SHA,
        "audit_path": str(OWN / "audit.json"), "audit_sha256": sha(OWN / "audit.json"),
        "full_audit_sha256": FULL_SHA,
        "authority": "Whole 60-update resource accounting only; endpoint384 is not continuation authority. Separate selected348 receipt grants only a new registered D2 continuation.",
        "wall_accounting": {
            "completed_campaign_resource_cost_before_seconds": cost_before,
            "completed_campaign_resource_cost_after_seconds": cost,
            "observed_outer_seconds": outer,
            "worker_current_iteration_observed_outer_seconds": worker["current_iteration_observed_outer_seconds"],
            "worker_elapsed_seconds": worker["elapsed_seconds"],
            "selected_checkpoint_future_baseline_seconds": trajectory,
            "completed_iteration_endpoint_trajectory_seconds": endpoint_trajectory,
            "discarded_branch_end_highwater_seconds": endpoint_trajectory,
            "semantics": "Whole 60-update campaign cost is separate from selected348 reported trajectory; updates after348 add resource cost only.",
        },
    }
    _write("completed-iteration-receipt.json", completed)

    sidecar_data = read(sidecar)
    schedule_spec_path = AUDITOR / "lr_schedule.py"
    schedule_bytes = schedule_spec_path.read_bytes()
    worker_schedule_path = Path(reg["lr_schedule_path"])
    worker_schedule_bytes = worker_schedule_path.read_bytes()
    need(sha(worker_schedule_path) == reg["lr_schedule_sha256"], "Registered schedule helper changed")
    schedule_spec = read_json_from_bytes(worker_schedule_bytes)
    need(canonical_sha(schedule_spec) == SCHEDULE_SPEC_SHA
         and schedule_spec == read_json_from_bytes(schedule_bytes), "Registered and audited schedule specs differ")
    receipt = {
        "schema": "d2_retained_best_candidate_parent_receipt_v1",
        "status": "accepted_complete_candidate_from_completed_normal_training_iteration",
        "at_utc": now, "run_id": reg["run_id"], "phase": "D2",
        "checkpoint_path": str(checkpoint), "checkpoint_sha256": SELECTED_SHA,
        "continuation_parent_checkpoint_sha256": SELECTED_SHA,
        "checkpoint_sidecar_sha256": sha(sidecar), "checkpoint_metadata_unchanged": True,
        "candidate_phase_update": 348, "candidate_local_update": 24,
        "candidate_counters": selected["counters"], "candidate_cumulative_counters": selected["cumulative_counters"],
        "counters": selected["counters"], "cumulative_counters": selected["cumulative_counters"],
        "inherited_counters": selected["inherited_counters"],
        "next_episode_indices": selected["next_episode_indices"],
        "learner_fingerprints": fingerprints,
        "identity": selected["identity"], "identity_sha256": selected["identity_sha256"],
        "run_seed": selected["run_seed"], "config_sha256": selected["config_sha256"],
        "runtime_sha256": selected["runtime_sha256"], "native_sha256": selected["native_sha256"],
        "policy_sha256": selected["policy_sha256"],
        "parent_registration_sha256": reg["parent"]["registration_sha256"],
        "candidate_parent_checkpoint_sha256": INCUMBENT_SHA,
        "parent_checkpoint_sha256": INCUMBENT_SHA,
        "previous_retained_checkpoint_sha256": INCUMBENT_SHA,
        "parent_terminal_receipt_path": str(OLD_RECEIPT),
        "parent_terminal_receipt_sha256": OLD_RECEIPT_SHA,
        "completed_iteration_local_updates": 60, "completed_iteration_phase_update_end": 384,
        "completed_iteration_receipt_path": str(OWN / "completed-iteration-receipt.json"),
        "completed_iteration_receipt_sha256": sha(OWN / "completed-iteration-receipt.json"),
        "registration_path": str(REG_PATH), "registration_sha256": REG_SHA,
        "evaluation_path": str(certificate_path), "evaluation_sha256": sha(certificate_path),
        "evaluation_jsonl_path": str(RUN / "development-000348.jsonl"),
        "evaluation_jsonl_sha256": sha(RUN / "development-000348.jsonl"),
        "audit_path": str(OWN / "audit.json"), "audit_sha256": sha(OWN / "audit.json"),
        "performance": performance,
        "selection_rule": "Highest independently audited mean survival among all six candidates; ties keep earlier update.",
        "effective_learning_rate": effective_lr, "optimizer_group_lrs": group_lrs,
        "schedule": {
            "metadata": schedule_fields, "specification": read_json_from_bytes(schedule_bytes),
            "specification_sha256": SCHEDULE_SPEC_SHA, "helper_path": str(worker_schedule_path),
            "helper_sha256": reg["lr_schedule_sha256"],
            "helper_bytes_encoding": "base64",
            "helper_bytes_base64": base64.b64encode(worker_schedule_bytes).decode("ascii"),
            "auditor_helper_path": str(schedule_spec_path),
            "auditor_helper_sha256": sha(schedule_spec_path),
            "auditor_helper_bytes_base64": base64.b64encode(schedule_bytes).decode("ascii"),
            "registration_schedule": reg["lr_schedule"], "sidecar_metadata": sidecar_data,
        },
        "competence_passed": True, "qualification_passed": False,
        "stage_promotion_eligible": False, "training_continuation_eligible": True,
        "authority_scope": "Selected complete348 candidate may parent only a NEW registered D2 continuation. No qualification, D3, B, E, student, or stage-promotion authority.",
        "wall_accounting": {
            "definition": "Selected checkpoint trajectory and completed campaign resource cost remain distinct.",
            "future_checkpoint_trajectory_baseline_seconds": trajectory,
            "selected_checkpoint_reported_cumulative_D2_wall_seconds": trajectory,
            "selected_checkpoint_reported_current_iteration_wall_seconds": selected["current_iteration_observed_outer_seconds"],
            "selected_checkpoint_reported_trajectory_wall_seconds": trajectory,
            "selected_checkpoint_reported_iteration_wall_seconds": selected["current_iteration_observed_outer_seconds"],
            "successful_ancestor_and_completed_campaign_cost_seconds": cost,
            "whole_completed_iteration_observed_outer_seconds": outer,
            "worker_current_iteration_observed_outer_seconds": worker["current_iteration_observed_outer_seconds"],
            "worker_elapsed_seconds": worker["elapsed_seconds"],
            "completed_iteration_endpoint_trajectory_seconds": endpoint_trajectory,
            "discarded_postselection_trajectory_seconds": endpoint_trajectory - trajectory,
            "continuation_deadline_origin": "Fresh next launcher monotonic T0; accounting baselines are not deadline origins.",
        },
    }
    _write("retained-best-candidate-receipt.json", receipt)
    incumbent_certificate_path = Path(previous_receipt["evaluation_path"])
    need(sha(incumbent_certificate_path) == previous_receipt["evaluation_sha256"],
         "Incumbent evaluation certificate changed")
    candidate_comparison = {"incumbent": previous_receipt["performance"]}
    report = [
        "# Retained348 terminal acceptance", "",
        "All 60 updates and six candidate audits passed. Selected348 improves the same 64-game development mean; endpoint384 is discarded.",
        "The 5.399687436876066% provisional mean gain is not a scientific schedule-causality claim.", "",
        "| Candidate | Q1 frames | Q4 frames | Mean frames | Deaths: normal/static/kamikaze/moving/explosion |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    incumbent_performance = previous_receipt["performance"]
    incumbent_causes = incumbent_performance["death_causes"]
    report.append("| Incumbent324 | {q1:g} | {q4:g} | {mean:g} | {deaths} |".format(
        q1=incumbent_performance["q1_bottom16_mean"],
        q4=incumbent_performance["q4_top16_mean"],
        mean=incumbent_performance["mean_alive_frames"],
        deaths="/".join(str(incumbent_causes.get(name, 0)) for name in
                         ("normal_enemy", "static_pattern_rect", "kamikaze_enemy", "moving_pattern_rect", "kamikaze_explosion"))))
    for key in ("324", "336", "348", "360", "372", "384"):
        cert = read(RUN / f"development-{int(key):06d}.json")
        rows = sorted(row["alive_frames"] for row in cert["evaluation"]["rows"])
        causes = Counter(row["death_cause"] for row in cert["evaluation"]["rows"] if row["terminated"])
        for cause in ("normal_enemy", "static_pattern_rect", "kamikaze_enemy", "moving_pattern_rect", "kamikaze_explosion"):
            causes.setdefault(cause, 0)
        candidate_comparison[key] = {
            "q1_bottom16_mean": sum(rows[:16]) / 16,
            "q4_top16_mean": sum(rows[-16:]) / 16,
            "mean_alive_frames": sum(rows) / 64,
            "deaths": cert["evaluation"]["deaths"], "caps": cert["evaluation"]["caps"],
            "death_causes": dict(causes), "certificate_sha256": sha(RUN / f"development-{int(key):06d}.json"),
        }
        deaths = "/".join(str(causes[name]) for name in
                           ("normal_enemy", "static_pattern_rect", "kamikaze_enemy", "moving_pattern_rect", "kamikaze_explosion"))
        report.append(f"| {key} | {sum(rows[:16]) / 16:g} | {sum(rows[-16:]) / 16:g} | {sum(rows) / 64:g} | {deaths} |")
    decision = {
        "selection": "retained_best_integrity_accepted_checkpoint", "phase_update": 348,
        "checkpoint_path": str(checkpoint), "checkpoint_sha256": SELECTED_SHA,
        "receipt_path": str(OWN / "retained-best-candidate-receipt.json"),
        "receipt_sha256": sha(OWN / "retained-best-candidate-receipt.json"),
        "previous_checkpoint_path": str(INCUMBENT), "previous_checkpoint_sha256": INCUMBENT_SHA,
        "previous_receipt_path": str(OLD_RECEIPT), "previous_receipt_sha256": OLD_RECEIPT_SHA,
        "previous_mean": previous_mean, "new_mean": performance["mean_alive_frames"],
        "candidate_comparison": candidate_comparison,
        "provisional_mean_gain_percent": (performance["mean_alive_frames"] / previous_mean - 1) * 100,
        "endpoint384_not_selected": True,
        "selected_future_branch_baseline_seconds": trajectory,
        "completed_campaign_resource_cost_seconds": cost,
    }
    _write("retained-best-decision.json", decision)
    report += [
        "", "Selected deaths from certificate rows: 25 normal, 15 static, 15 kamikaze enemy, 9 moving rectangle. No caps or explosions.",
        f"Selected saved effective LR: {effective_lr:.16g}; optimizer groups: {group_lrs}.",
        f"Observed outer duration: {outer}s. Completed resource cost: {cost}s. Selected348 future trajectory baseline: {trajectory}s.",
        "Qualification and stage promotion remain false. No D3, B, E, or student authority.",
    ]
    with (OWN / "report.md").open("x") as stream:
        stream.write("\n".join(report) + "\n")
        stream.flush()
        os.fsync(stream.fileno())

    # Re-read the exact state snapshot, preserve unrelated tasks, then replace atomically.
    state, state_before = guard()
    precommit_absence = _check_live_process_absence(obs, execution)
    _write("process-absence-precommit.json", {"schema": "d2_parent_process_absence_precommit_v1",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(), "processes": precommit_absence,
        "owned_groups_absent": True})
    _write("state-before-lease-clear.json", state)
    receipt_path = OWN / "retained-best-candidate-receipt.json"
    completed_path = OWN / "completed-iteration-receipt.json"
    relative_receipt = str(receipt_path.relative_to(ROOT))
    relative_completed = str(completed_path.relative_to(ROOT))
    receipt_sha = sha(receipt_path)
    completed_sha = sha(completed_path)
    state["active_long_campaign"] = None
    state["last_update_at_utc"] = now
    post = state["postcritic_training_work"]
    post.update(
        active_campaign=None,
        status="linear_trial_accepted;retained348_selected;endpoint384_discarded",
        latest_parent_terminal_audit=str((OWN / "audit.json").relative_to(ROOT)),
        latest_parent_terminal_receipt=relative_receipt,
        latest_parent_terminal_receipt_sha256=receipt_sha,
        latest_completed_iteration_receipt=relative_completed,
        latest_completed_iteration_receipt_sha256=completed_sha,
        completed_campaign_resource_cost_seconds=cost,
        latest_completed_cumulative_updates=432,
        latest_completed_phase_updates=384,
        latest_completed_endpoint_performance=candidates["384"]["performance"],
        latest_completed_endpoint_trajectory_wall_seconds=endpoint_trajectory,
        latest_completed_observed_outer_seconds=outer,
        latest_completed_worker_elapsed_seconds=worker["elapsed_seconds"],
        cumulative_D2_inclusive_wall_seconds=trajectory,
        cumulative_D2_wall_semantics="Selected348 trajectory through accepted checkpoint; completed campaign resource cost is separate.",
        latest_performance=performance,
        best_observed_current_lineage_reference={
            "phase_update": 348, "run_id": reg["run_id"], "checkpoint_sha256": SELECTED_SHA,
            "parent_terminal_receipt": relative_receipt, "parent_terminal_receipt_sha256": receipt_sha,
            "Q1_bottom16_mean": performance["q1_bottom16_mean"],
            "Q4_top16_mean": performance["q4_top16_mean"],
            "mean_alive_frames": performance["mean_alive_frames"],
        },
        lease_cleared_at_utc=now,
    )
    policy = state["training_parent_selection_policy"]
    decision_path = OWN / "retained-best-decision.json"
    relative_decision = str(decision_path.relative_to(ROOT))
    policy.update(selection="retained_best_integrity_accepted_checkpoint",
                  path=relative_decision, sha256=sha(decision_path),
                  current_parent_phase_update=348, current_parent_sha256=SELECTED_SHA,
                  current_parent_receipt=relative_receipt, current_parent_receipt_sha256=receipt_sha,
                  current_parent_effective_learning_rate=effective_lr,
                  current_parent_lr_schedule={"metadata": selected["lr_schedule"], "spec_sha256": SCHEDULE_SPEC_SHA},
                  parent_receipt_schema=receipt["schema"])
    need(state["postcritic_training_work"]["completed_campaign_resource_cost_seconds"] == cost
         and state["training_parent_selection_policy"]["current_parent_sha256"] == SELECTED_SHA,
         "Ledger parent selection/cost mapping failed")
    validate_snapshot_unchanged(statepath.read_bytes(), state_before)
    _write("state-after-lease-clear.json", state)
    manifest = {path.name: sha(path) for path in sorted(OWN.iterdir()) if path.is_file() and path.name != "output-manifest.json"}
    _write("output-manifest.json", {"schema": "d2_retained348_parent_output_manifest_v1", "files": manifest})
    with tempfile.NamedTemporaryFile("w", dir=statepath.parent, prefix=".retained348-linear-finalize-", delete=False) as stream:
        json.dump(state, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
        temporary = stream.name
    validate_snapshot_unchanged(statepath.read_bytes(), state_before)
    guard()  # Exact lease, cancellation, source pins, caches, and review receipt immediately precommit.
    validate_snapshot_unchanged(statepath.read_bytes(), state_before)
    final_absence = _check_live_process_absence(obs, execution)
    need(final_absence == precommit_absence, "Owned process/group absence changed before commit")
    validate_snapshot_unchanged(statepath.read_bytes(), state_before)
    os.replace(temporary, statepath)
    directory_fd = os.open(statepath.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    expected_ledger = (json.dumps(state, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    need(statepath.read_bytes() == expected_ledger, "Committed ledger bytes differ from prepared snapshot")
    print(json.dumps({"status": audit_out["status"], "selected_update": 348,
                      "checkpoint_sha256": SELECTED_SHA, "receipt_sha256": receipt_sha,
                      "performance": performance, "completed_resource_cost_seconds": cost,
                      "selected_trajectory_seconds": trajectory, "matching_lease_cleared": True}))


def read_json_from_bytes(data):
    # Schedule helper contains the full JSON-serializable specification as SCHEDULE_SPEC.
    # Parse the already pinned source's literal with AST; never import a second schedule module.
    import ast
    tree = ast.parse(data.decode())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "SCHEDULE_SPEC"
                                                for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("Pinned schedule helper has no SCHEDULE_SPEC")


def finalize_parent():
    """Explicit parent invocation entry point. Never call from preparation or review."""
    _validate_and_finalize()


if __name__ == "__main__":
    finalize_parent()
