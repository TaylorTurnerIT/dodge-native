"""Freeze the bounded supervisor repair and its retained pure-test evidence once."""
import ast
import datetime
import difflib
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
RUNNER = ROOT / "learning/scripts/v2_validate_environment.py"
ORIGINAL = OUT / "snapshots/learning/scripts/v2_validate_environment.py"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(name, value):
    with (OUT / name).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")

before = json.loads((OUT / "before-manifest.json").read_text())
assert sha(ORIGINAL) == before["runner_original_sha256"]
assert all(sha(Path(name)) == expected for name, expected in before["protected_sha256"].items())
source = OUT / "source/learning/scripts/v2_validate_environment.py"
source.parent.mkdir(parents=True)
with source.open("xb") as stream:
    stream.write(RUNNER.read_bytes())
with (OUT / "source.patch").open("x") as stream:
    stream.writelines(difflib.unified_diff(ORIGINAL.read_text().splitlines(keepends=True), RUNNER.read_text().splitlines(keepends=True),
                                         fromfile="a/learning/scripts/v2_validate_environment.py", tofile="b/learning/scripts/v2_validate_environment.py"))
source_files = [source, ORIGINAL, OUT / "test_supervisor.py", OUT / "run_pure_tests.py", OUT / "run_check.py", Path(__file__).resolve()]
for path in source_files:
    ast.parse(path.read_text())
save("source-manifest.json", {"changed_live_source": {str(RUNNER.relative_to(ROOT)): sha(RUNNER)},
    "original_runner_sha256": sha(ORIGINAL), "original_snapshot_manifest_sha256": sha(OUT / "before-manifest.json"),
    "frozen_sources_sha256": {str(path.relative_to(OUT)): sha(path) for path in source_files},
    "patch_sha256": sha(OUT / "source.patch"), "compiled_sources_changed": False})
archive_members = source_files + [OUT / "source.patch", OUT / "source-manifest.json", OUT / "before-manifest.json", OUT / "static-preservation-check.json"]
with (OUT / "source.tar.gz").open("xb") as raw:
    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for path in archive_members:
                contents = path.read_bytes()
                info = tarfile.TarInfo(str(path.relative_to(OUT)))
                info.size = len(contents)
                info.mode = 0o644
                info.mtime = 0
                archive.addfile(info, io.BytesIO(contents))
checks = {name: json.loads((OUT / "checks" / (name + ".json")).read_text()) for name in ("repaired-pure-r1", "existing-nine-r1", "original-discrimination-r1")}
assert checks["repaired-pure-r1"]["exit_code"] == checks["existing-nine-r1"]["exit_code"] == 0
assert checks["original-discrimination-r1"]["exit_code"] == 1
assert checks["repaired-pure-r1"]["source_sha256"] == checks["existing-nine-r1"]["source_sha256"] == sha(RUNNER)
save("failure-ledger.json", {"unexpected_repaired_check_failures": [], "expected_original_source_regression_failures": {
    "tests": 12, "assertion_failures": 10, "cleanup_race_errors": 2, "exit_code": 1,
    "source_sha256": sha(ORIGINAL), "log": "checks/original-discrimination-r1.log",
    "meaning": "The original supervisor accepts replaced identities and late/revoked completions; its KILL race escapes cleanup.",
    "automatic_retry": False}, "native_campaign_failures": [], "actual_native_campaign_executed": False})
identity = json.loads((OUT / "snapshots/learning/runs/v2/milestone2-integration-r2/frozen-identity.json").read_text())
assert identity["runtime"]["extension_sha256"] == "967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583"
result = {"status": "implemented_pure_tests_passed_pending_parent_identity_and_independent_review",
    "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "owned_live_source": "learning/scripts/v2_validate_environment.py", "runner_sha256": sha(RUNNER),
    "original_runner_sha256": sha(ORIGINAL), "before_manifest_sha256": sha(OUT / "before-manifest.json"),
    "patch": "source.patch", "patch_sha256": sha(OUT / "source.patch"),
    "source_archive": "source.tar.gz", "source_archive_sha256": sha(OUT / "source.tar.gz"),
    "source_manifest": "source-manifest.json", "source_manifest_sha256": sha(OUT / "source-manifest.json"),
    "findings": [
        {"id": "identity_document_recheck_pin", "severity": "P1", "response": "Every check hashes the exact parsed document bytes against the original lease anchor, then rechecks the document after verification. Workers receive the same anchor explicitly and verify it before and after their workload; the parent never reanchors."},
        {"id": "launch_exit_finalization_time_lease_guards", "severity": "P1", "response": "A shared guard checks the exact lease, monotonic deadline, UTC cutoff and phase wall at launch, exit, identity, parse, phase-save and final-success boundaries. Late observed exits fail even if the polling body never runs. Large final artifact hashes precede the final guarded identity check."},
        {"id": "kill_exit_race_receipts", "severity": "P2", "response": "Owned-group TERM/KILL races and bounded wait/poll failures return diagnostics. Campaign failure handling preserves the original error, cleanup diagnostics, failed-stage receipt and overall receipt separately."}],
    "pure_tests": {"new_regressions_passed": 37, "existing_readonly_tests_passed": 9, "total_passed": 46,
        "interpreter": "python/.venv/bin/python", "warnings": "-W error", "bytecode_writes_disabled": True,
        "existing_test_source_edited": False, "existing_test_temporaries_redirected_to_owned_directory": True,
        "original_discriminating_tests": {"run": 12, "expected_failures": 10, "expected_errors": 2},
        "receipts": {name: "checks/" + name + ".json" for name in checks},
        "logs": {name: "checks/" + name + ".log" for name in checks}},
    "preservation": {"protected_files_unchanged": len(before["protected_sha256"]),
        "old_review_capsule_manifest_sha256": before["capsule_manifest_sha256"], "original_harness_artifacts_unchanged": True,
        "compiled_inputs_and_binaries_unchanged": True, "extension_sha256": identity["runtime"]["extension_sha256"],
        "native_test_binary": identity["native_test_binary"], "module_constants_unchanged": True,
        "workload_functions_unchanged": ["worker_trajectory", "worker_memory", "worker_throughput"],
        "campaign_wall_seconds": 1800, "receipt_reserve_seconds": 600,
        "phase_wall_seconds": {"native_parity": 900, "trajectory": 120, "memory": 600, "throughput": 120},
        "worker_rss_limit_bytes": 6442450944, "memory_workload_and_plateau_thresholds_unchanged": True,
        "baseline_assertions_and_seed_reservations_unchanged": True, "automatic_campaign_retries": 0,
        "state_or_docs_edited": False},
    "actual_campaign_executed": False, "native_or_extension_operation_executed": False,
    "active_long_campaign_at_start": before["active_long_campaign_at_start"],
    "active_long_campaign_at_finish": json.loads((ROOT / "learning/runs/v2-orchestration/state.json").read_text())["active_long_campaign"],
    "limitations": ["Pure mocked supervisor tests establish supervisor behavior, not native/game/extension or campaign qualification.",
        "Guards remain cooperative; late observed completion is rejected without claiming an exact OS exit time or a hard synchronous kill guarantee.",
        "The 600-second receipt reserve remains separate from the unchanged 1800-second experiment deadline.",
        "No new combined identity, build receipt or review was created. Parent must reconcile unchanged compiled inputs, freeze a new identity and obtain independent r2 review before campaign launch.",
        "No commits, PRs, deployments, provider operations, external messages or nested agents."]}
save("result.json", result)
# Validate every retained JSON receipt, including deliberately failed synthetic cases.
json_files = sorted(OUT.rglob("*.json"))
for path in json_files:
    json.loads(path.read_text())
save("json-validation.json", {"validated_json_files_before_manifests": len(json_files), "status": "passed"})
artifacts = {str(path.relative_to(OUT)): sha(path) for path in sorted(OUT.rglob("*")) if path.is_file()}
save("artifact-sha256.json", artifacts)
save("frozen-result-manifest.json", {"version": "m2_supervisor_repair_r1_frozen_result_v1", "status": result["status"],
    "runner_sha256": sha(RUNNER), "original_runner_sha256": sha(ORIGINAL),
    "before_manifest_sha256": sha(OUT / "before-manifest.json"),
    "result_sha256": sha(OUT / "result.json"), "source_manifest_sha256": sha(OUT / "source-manifest.json"),
    "source_patch_sha256": sha(OUT / "source.patch"), "source_archive_sha256": sha(OUT / "source.tar.gz"),
    "artifact_manifest_sha256": sha(OUT / "artifact-sha256.json"), "artifact_count": len(artifacts),
    "actual_campaign_executed": False, "new_pure_tests_passed": 37, "existing_pure_tests_passed": 9,
    "expected_original_regression_failures": 12, "protected_files_unchanged": len(before["protected_sha256"]),
    "manifest_rule": "artifact-sha256.json covers every retained file except itself and this frozen manifest; this manifest pins it."})
print(json.dumps({"frozen_manifest_sha256": sha(OUT / "frozen-result-manifest.json"), "result_sha256": sha(OUT / "result.json"),
                  "runner_sha256": sha(RUNNER), "patch_sha256": sha(OUT / "source.patch"), "archive_sha256": sha(OUT / "source.tar.gz"),
                  "artifact_count": len(artifacts), "protected_files": len(before["protected_sha256"])}))
