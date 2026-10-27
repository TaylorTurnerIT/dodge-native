"""Independent stdlib-only audit of retained runtime-repair receipts."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import tarfile
import time

STARTED = time.monotonic()
ROOT = Path.cwd()
SOURCE = ROOT / "learning/runs/v2/milestone3-runtime-repair-r1"
CAPSULE = ROOT / "learning/.cache/v2-m3-runtime-review-r1"
OUT = Path(__file__).resolve().parent
observed = {}
checks = []


def read(path):
    path = Path(path)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    key = str(path.relative_to(ROOT))
    if key in observed:
        assert observed[key] == digest, ("input changed during audit", key)
    observed[key] = digest
    return data


def digest(path):
    return hashlib.sha256(read(path)).hexdigest()


def load(path):
    return json.loads(read(path))


def verify_map(base, values):
    for name, expected in values.items():
        assert digest(base / name) == expected, name
    return len(values)


def record(name, count, detail):
    checks.append({"check": name, "count": count, "detail": detail, "status": "passed"})


result = load(SOURCE / "result.json")
manifest = load(SOURCE / "artifact-sha256.json")
assert len(manifest) == 668
verify_map(SOURCE, manifest)
actual_files = {str(p.relative_to(SOURCE)) for p in SOURCE.rglob("*") if p.is_file()}
assert actual_files == set(manifest) | {"artifact-sha256.json"}
record("retained_artifact_manifest", len(manifest), "Every digest matches; exact file coverage excluding the manifest itself.")

preflight = load(SOURCE / "preflight.json")
before = load(SOURCE / "protected-before.json")
after = load(SOURCE / "protected-after.json")
assert before == after and len(before) == 813
verify_map(ROOT, before)
record("protected_before_after_and_current", len(before), "Both protected maps match exactly and every current protected input matches.")

assert digest(CAPSULE / "manifest.json") == preflight["frozen_manifest_sha256"]
capsule = load(CAPSULE / "manifest.json")
assert len(capsule["files"]) == 818
verify_map(CAPSULE, capsule["files"])
assert digest(ROOT / "learning/runs/v2/milestone3-integration-r1/probe-frozen-identity.json") == preflight["identity_sha256"]
record("frozen_predecessor_capsule", len(capsule["files"]), "All 818 frozen files, manifest and original probe identity match retained pins.")

owned = load(SOURCE / "owned-after-sha256.json")
assert owned == result["owned_after_sha256"] and len(owned) == 7
verify_map(ROOT, owned)
verify_map(SOURCE / "after", owned)
verify_map(SOURCE / "before", preflight["owned_before"])
for name, expected in preflight["owned_before"].items():
    assert digest(CAPSULE / name) == expected, ("before differs from frozen r1", name)
record("owned_source_before_after_current", len(owned), "Seven current/after files match; five before files match frozen r1 bytes.")

expected_archive = {}
patch = []
changed = []
for name in sorted(owned):
    original_path = SOURCE / "before" / name
    revised_path = SOURCE / "after" / name
    original = read(original_path) if original_path.exists() else b""
    revised = read(revised_path)
    for side in ("before", "after"):
        path = SOURCE / side / name
        if path.exists():
            expected_archive[str(path.relative_to(SOURCE))] = read(path)
    if original != revised:
        changed.append(name)
        patch.extend(difflib.unified_diff(original.decode().splitlines(keepends=True),
                                        revised.decode().splitlines(keepends=True),
                                        fromfile="a/" + name if original_path.exists() else "/dev/null",
                                        tofile="b/" + name))
assert changed == result["changed_files"]
assert "".join(patch).encode() == read(SOURCE / "repair.patch")
with tarfile.open(SOURCE / "source-before-after.tar.gz", "r:gz") as archive:
    members = archive.getmembers()
    assert len(members) == len(expected_archive) == 12
    assert set(m.name for m in members) == set(expected_archive)
    for member in members:
        assert member.isfile() and archive.extractfile(member).read() == expected_archive[member.name]
assert digest(SOURCE / result["source_archive"]["path"]) == result["source_archive"]["sha256"]
assert digest(SOURCE / result["patch"]["path"]) == result["patch"]["sha256"]
record("archive_and_exact_patch", len(expected_archive), "12 archive members exactly match before/after files; independent unified diff equals retained patch byte-for-byte.")

test_records = []
for label, expected_status, expected_failures, expected_passes in (
        ("frozen-r1-negative", 1, 19, 1),
        ("repaired-cpu-r1", 0, 0, 90),
        ("frozen-r1-parent-resume-negative", 1, 5, 0),
        ("repaired-cpu-final", 0, 0, 94)):
    directory = SOURCE / label
    command = load(directory / "command-result.json")
    sources = load(directory / "executed-source.json")
    log = read(directory / "stdout-stderr.log").decode()
    assert command["exit_status"] == expected_status
    assert command["source_unchanged_during_test"] is True
    assert command["duration_seconds"] < 120
    assert command["environment"] == {"PYTHONPATH": "python", "PYTHONDONTWRITEBYTECODE": "1"}
    assert command["cwd"] == str(ROOT)
    assert command["argv"][1:3] == ["-B", "-c"]
    loader = command["argv"][3]
    assert "spec_from_file_location('dodge_rl.'+name,path)" in loader
    assert "sys.modules[spec.name]=module" in loader
    assert "setattr(dodge_rl,name,module)" in loader
    assert "spec.loader.exec_module(module)" in loader
    selected_root = CAPSULE if label.startswith("frozen-") else ROOT
    assert command["argv"][4] == str(selected_root)
    assert len(sources) == len(command["source_sha256_after"]) == 12
    for name, row in sources.items():
        assert row["sha256"] == command["source_sha256_after"][name]
        if name.endswith(".py"):
            assert digest(directory / "source" / name) == row["sha256"]
        if name in ("python/dodge_rl/supervision.py", "python/dodge_rl/checkpoints.py", "python/dodge_rl/train_teacher.py"):
            assert row["executed_path"] == str(selected_root / name)
            if label.startswith("frozen-"):
                assert row["sha256"] == preflight["owned_before"][name]
            if label == "repaired-cpu-final":
                assert row["sha256"] == owned[name]
            module_name = Path(name).stem
            line = f"EXECUTED_SOURCE {module_name} {row['executed_path']} {row['sha256']}"
            assert line in log
        if label == "repaired-cpu-final":
            assert digest(ROOT / name) == row["sha256"]
    summary = re.findall(r"(?:\d+ failed, )?\d+ passed in [0-9.]+s|\d+ failed in [0-9.]+s", log)
    assert len(summary) == 1
    failed_ids = re.findall(r"^FAILED (.+)$", log, re.MULTILINE)
    assert len(failed_ids) == expected_failures
    if expected_failures:
        assert f"{expected_failures} failed" in summary[0]
        assert "AttributeError:" not in log and "ImportError:" not in log and "ModuleNotFoundError:" not in log
        assert "ERROR collecting" not in log and "ERROR at setup" not in log and "HARNESS_TIMEOUT" not in log
        failure_blocks = re.split(r"(?m)^_{2,} .+ _{2,}\n", log)[1:]
        assert len(failure_blocks) == expected_failures
        assert all(re.search(r"^E\s+(?:AssertionError:|Failed: DID NOT RAISE|assert )", block, re.MULTILINE)
                   for block in failure_blocks)
    if expected_passes:
        assert f"{expected_passes} passed" in summary[0]
    source_snapshot_hashes = {name: row["sha256"] for name, row in sources.items()}
    test_records.append({"label": label, "status": command["exit_status"], "summary": summary[0],
                         "duration_seconds": command["duration_seconds"], "argv": command["argv"],
                         "executed_source_sha256": source_snapshot_hashes,
                         "failed_test_ids": failed_ids,
                         "negative_failure_kind": "behavioral_assertions_only" if expected_failures else None})
record("test_command_and_executed_source_provenance", len(test_records), "All four exact commands, loader paths, printed source pins, snapshots, summaries and statuses verified; old failures are behavioral assertions.")

# The initially retained source snapshots identify the test additions and one
# strengthened worker-entry guard between the first and final successful runs.
early_sources = load(SOURCE / "repaired-cpu-r1/executed-source.json")
final_sources = load(SOURCE / "repaired-cpu-final/executed-source.json")
between_successes = [name for name in final_sources if early_sources[name]["sha256"] != final_sources[name]["sha256"]]
assert between_successes == ["python/dodge_rl/train_teacher.py", "python/tests/test_runtime_repair.py"]
early_train = read(SOURCE / "repaired-cpu-r1/source/python/dodge_rl/train_teacher.py").decode()
final_train = read(SOURCE / "repaired-cpu-final/source/python/dodge_rl/train_teacher.py").decode()
success_diff = "".join(difflib.unified_diff(early_train.splitlines(keepends=True), final_train.splitlines(keepends=True)))
assert "checkpoint-local phase consumption" in success_diff
record("successive_successes_distinct_source", len(between_successes), "90-pass intermediate and 94-pass final runs are separately source-pinned; added parent/worker resume controls followed the intermediate pass.")

failure = load(SOURCE / "preflight-attempt1-failure.json")
assert failure["status"] == 1 and failure["error"].startswith("FileExistsError:")
assert failure["operation"] == "mkdir(exist_ok=False) before archive verification"
assert "No source changed" in failure["reason"]
assert "preflight-attempt1-failure.json" in result["retained_failed_attempts"]
record("preflight_error_retention", 1, "Directory-exists preflight error is separately retained and labeled; it is not counted as a behavioral test or retry.")

process = load(SOURCE / "owned-process-audit.json")
assert process["all_test_owned_worker_pids_absent"] is True
ready_files = {str(path.relative_to(SOURCE)): int(read(path).decode())
               for path in SOURCE.rglob("worker-ready") if path.is_file()}
assert len(ready_files) == len(process["workers"]) == 3
for row in process["workers"]:
    assert ready_files[row["ready_file"]] == row["pid"]
    assert row["ps_exit_status"] == 1 and row["ps_output"] == ""
record("retained_owned_process_absence_receipt", len(ready_files), "All three test-owned PID-ready files match retained ps exit-1/empty-output checks; no live process claim or process mutation made by this audit.")

for name, expected in observed.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, ("changed after read", name)

audit = {
    "status": "passed_retained_receipts_and_source_identity",
    "started_at_utc": "2026-10-24T10:31:31Z",
    "finished_at_utc": datetime.now(timezone.utc).isoformat(),
    "elapsed_seconds": time.monotonic() - STARTED,
    "scope": "stdlib-only retained receipt/source audit; no project/Torch/native/test execution",
    "findings": [],
    "checks": checks,
    "test_runs": test_records,
    "inputs_rehashed_unchanged": len(observed),
    "repair_result_sha256": digest(SOURCE / "result.json"),
    "repair_artifact_manifest_sha256": digest(SOURCE / "artifact-sha256.json"),
    "successive_success_source_changes": between_successes,
    "limitations": [
        "This audit verifies retained evidence and current pinned bytes; it does not independently rerun tests, training or device measurements.",
        "Same-phase resume is intentionally rejected. Parent-owned cumulative terminal-receipt anchoring remains unavailable; registered curriculum transitions are a separate path.",
        "Process absence is supported by retained ps receipts for three test-owned PIDs, not an exhaustive live process census.",
        "Signal tests use plain Python subprocesses and mocked controller paths. Actual native training cancellation and actual MPS behavior remain unqualified.",
        "The 90-pass intermediate run and 94-pass final run execute distinct, accurately recorded trainer/test bytes; only the final run identifies current repaired source."
    ]
}
with (OUT / "audit.json").open("x") as stream:
    json.dump(audit, stream, indent=2, sort_keys=True); stream.write("\n")
with (OUT / "input-sha256.json").open("x") as stream:
    json.dump(observed, stream, indent=2, sort_keys=True); stream.write("\n")
artifacts = {str(path.relative_to(OUT)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "artifact-sha256.json"}
with (OUT / "artifact-sha256.json").open("x") as stream:
    json.dump(artifacts, stream, indent=2, sort_keys=True); stream.write("\n")
print(json.dumps({"status": audit["status"], "checks": len(checks), "inputs_rehashed_unchanged": len(observed),
                  "audit_sha256": artifacts["audit.json"], "artifact_count": len(artifacts)}))
