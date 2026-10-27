"""Archive this bounded repair and verify immutable evidence before handoff."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import time

started = time.monotonic()
root = Path.cwd()
out = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


preflight = json.loads((out / "preflight.json").read_text())
protected = json.loads((out / "protected-before.json").read_text())
assert all(digest(root / name) == expected for name, expected in protected.items())
assert all(digest(out / "before" / name) == expected
           for name, expected in preflight["owned_before"].items())
capsule = root / "learning/.cache/v2-m3-runtime-review-r1"
assert digest(capsule / "manifest.json") == preflight["frozen_manifest_sha256"]
frozen = json.loads((capsule / "manifest.json").read_text())
assert all(digest(capsule / name) == expected for name, expected in frozen["files"].items())
owned = list(preflight["owned_before"]) + ["python/tests/test_runtime_repair.py",
                                         "python/tests/test_runtime_repair_signals.py"]
patch = []
changed = []
for name in sorted(owned):
    old = out / "before" / name
    current = root / name
    target = out / "after" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(current, target)
    old_text = old.read_text().splitlines(keepends=True) if old.exists() else []
    new_text = current.read_text().splitlines(keepends=True)
    if old_text != new_text:
        changed.append(name)
        patch.extend(difflib.unified_diff(old_text, new_text,
                                         fromfile="a/" + name if old.exists() else "/dev/null",
                                         tofile="b/" + name))
with (out / "repair.patch").open("x") as stream:
    stream.writelines(patch)
archive = out / "source-before-after.tar.gz"
assert not archive.exists()
with tarfile.open(archive, "x:gz") as bundle:
    for name in sorted(owned):
        for side in ("before", "after"):
            path = out / side / name
            if path.exists():
                bundle.add(path, arcname=str(path.relative_to(out)))
test_runs = []
for label, expected_status, summary in (
        ("frozen-r1-negative", 1, "19 failed, 1 passed"),
        ("repaired-cpu-r1", 0, "90 passed"),
        ("frozen-r1-parent-resume-negative", 1, "5 failed"),
        ("repaired-cpu-final", 0, "94 passed")):
    command = json.loads((out / label / "command-result.json").read_text())
    log = out / label / "stdout-stderr.log"
    assert command["exit_status"] == expected_status
    assert command["source_unchanged_during_test"] is True
    assert summary in log.read_text()
    source = json.loads((out / label / "executed-source.json").read_text())
    if label == "repaired-cpu-final":
        assert all(digest(Path(row["executed_path"])) == row["sha256"] for row in source.values())
    test_runs.append({"label": label, "summary": summary, "exit_status": command["exit_status"],
                      "duration_seconds": command["duration_seconds"],
                      "command_receipt": label + "/command-result.json",
                      "source_receipt": label + "/executed-source.json",
                      "log": str(log.relative_to(out)), "log_sha256": digest(log)})
source_hashes = {name: digest(root / name) for name in sorted(owned)}
write_json(out / "owned-after-sha256.json", source_hashes)
now = datetime.now(timezone.utc)
result = {
    "status": "bounded_implementation_repair_passed_synthetic_CPU_tests_pending_parent_integration_review",
    "started_at_utc": preflight["started_utc"], "finished_at_utc": now.isoformat(),
    "task_elapsed_seconds": (now - datetime.fromisoformat(preflight["started_utc"].replace("Z", "+00:00"))).total_seconds(),
    "task_budget_seconds": 1800, "task_deadline_utc": preflight["task_deadline_utc"],
    "cutoff_utc": preflight["cutoff_utc"],
    "changed_files": changed, "owned_after_sha256": source_hashes,
    "frozen_review_manifest_sha256": preflight["frozen_manifest_sha256"],
    "frozen_identity_sha256": preflight["identity_sha256"],
    "protected_live_inputs_unchanged": len(protected), "frozen_capsule_files_unchanged": len(frozen["files"]),
    "before_archive_unchanged": True,
    "key_unchanged_pins": {name: protected[name] for name in (
        "python/dodge_rl/models/teacher.py", "python/dodge_rl/ppo.py", "python/dodge_rl/identity.py",
        "python/dodge_rl/dev_eval.py", "python/dodge_rl/_native.cpython-312-darwin.so",
        "docs/SPEC_PRIVILEGED_VIT_RL.md", "docs/v2-m3-component-contract.md",
        "docs/v2-m3-run-protocol.json", "learning/runs/v2/milestone3-integration-r1/probe-config.json",
        "learning/runs/v2/milestone3-integration-r1/probe-frozen-identity.json")},
    "repairs": [
        {"finding": "P1 cancellation orphan", "change": "Catch BaseException in supervisor/worker; temporary SIGTERM/SIGINT handlers restore on every exit. Defer cancellation across Popen PID assignment and cleanup. TERM exact new-session group with five-second checkpoint opportunity, then KILL and bounded reap, including already-exited leaders.",
         "evidence": "Mocked KeyboardInterrupt/SystemExit/BaseException supervisor paths; real synthetic supervisor SIGTERM; worker SIGTERM and KeyboardInterrupt diagnostic checkpoints; helper signal restoration/defer/group/reap tests."},
        {"finding": "P1 interrupted update becomes candidate on resume", "change": "Reject interrupted/incomplete updates before construction restores learner; restore_learner also rejects before mutation. Raw diagnostic loading remains possible and immutable.",
         "evidence": "Frozen r1 restores phase_updates=0 partial learners and reaches candidate; repaired constructor rejects both interrupted tag and incomplete untagged progress before any candidate."},
        {"finding": "P1 checkpoint-local phase allowance", "change": "Fail closed by rejecting all same-phase resume. Public supervisor, Experiment construction and internal worker paths cannot obtain allowance from a checkpoint or free consumed-time CLI claim. Initial registered full budgets remain unchanged.",
         "evidence": "1600-second checkpoint after 1800-second terminal receipt; absent/stale/mismatching CLI anchor claims rejected before launch; direct _worker path rejected before identity/candidate."},
        {"finding": "P1 probe correctness failure masked by completed CPU", "change": "Retain failed-device JSON and propagate every unexpected measured-device exception. Selector rejects failed rows. Explicit unavailable MPS remains allowed.",
         "evidence": "Mocked inference NaN, nonfinite PPO loss, reward audit and unexpected measured-device failures all invalidate probe; unavailable MPS still permits CPU comparison."}
    ],
    "test_runs": test_runs,
    "negative_control_semantics": "Expected assertion failures on explicitly loaded frozen r1 bytes, not missing new APIs. One unavailable-device positive control passed. Supplemental negatives cover parent launch and internal worker bypass. No fixture correction was needed.",
    "retained_failed_attempts": ["frozen-r1-negative", "frozen-r1-parent-resume-negative",
                                  "preflight-attempt1-failure.json"],
    "preflight_fixture_correction": "Directory creation initially refused the parent's existing evidence directory. Verified and reused its untouched before/ archive; no source had changed. Failure retained separately from behavioral controls.",
    "test_owned_process_audit": "owned-process-audit.json",
    "source_archive": {"path": archive.name, "sha256": digest(archive)},
    "patch": {"path": "repair.patch", "sha256": digest(out / "repair.patch")},
    "limitations": [
        "Same-phase fresh_env resume is deliberately unavailable. Parent-owned cumulative terminal receipt/hash anchoring is not implemented; this is the explicitly authorized fail-closed fallback.",
        "Registered eligible curriculum transitions remain supported; this repair does not authorize a new attempt or relax any lease, deadline, budget, gate or retry policy.",
        "All execution was synthetic/mocked CPU testing, including plain Python signal subprocesses. No real rollout, device probe, pilot, training, native build, install or model/PPO mutation occurred.",
        "MPS paths use CPU test doubles; actual MPS inference/update behavior is unqualified.",
        "Frozen r1 identity is preserved historical evidence. Parent must integrate, freeze repaired inputs and obtain fresh independent review before any campaign.",
        "No public deployment, PR, commit, external message, provider retry or nested external review occurred. An internal implementation helper owned supervision.py and its new tests."
    ],
    "parent_owned_files_edited": False,
    "identity_or_dev_eval_edits": False,
    "active_long_campaign_at_handoff": json.loads((root / "learning/runs/v2-orchestration/state.json").read_text())["active_long_campaign"],
}
assert result["task_elapsed_seconds"] < 1800
assert result["active_long_campaign_at_handoff"] is None
write_json(out / "result.json", result)
write_json(out / "finalize-command-result.json", {"argv": [sys.executable, "-B", str(Path(__file__).resolve())],
    "cwd": str(root), "environment": {"PYTHONPATH": os.environ.get("PYTHONPATH"),
    "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE")},
    "exit_status": 0, "duration_seconds": time.monotonic() - started})
hashes = {str(path.relative_to(out)): digest(path) for path in sorted(out.rglob("*"))
          if path.is_file() and path != out / "artifact-sha256.json"}
write_json(out / "artifact-sha256.json", hashes)
print(json.dumps({"status": result["status"], "task_elapsed_seconds": result["task_elapsed_seconds"],
    "artifact_files": len(hashes), "result_sha256": digest(out / "result.json"),
    "artifact_manifest_sha256": digest(out / "artifact-sha256.json"),
    "source_archive_sha256": digest(archive), "patch_sha256": digest(out / "repair.patch")}))
