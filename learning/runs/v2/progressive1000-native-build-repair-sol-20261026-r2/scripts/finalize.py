"""Write the preparation receipt, then freeze only this owned successor."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import signal
import sys

OUT = Path(__file__).absolute().parents[1]
ROOT = OUT.parents[3]
PREVIOUS = OUT.parent / "progressive1000-native-cutoff-prepare-sol-20261026-r1"

def deadline(signum, frame):
    raise TimeoutError("300-second finalization deadline")

signal.signal(signal.SIGALRM, deadline)
signal.alarm(300)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def save(name, value):
    p = OUT / name
    assert not p.exists(), p
    p.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")

assert sys.version_info[:3] == (3, 12, 15)
assert sys.executable == str(ROOT / "python/.venv/bin/python3.12")
assert not (ROOT / "python/.venv/bin/python3.12.15").exists()
source = json.loads((OUT / "source-manifest.json").read_text())
binary = json.loads((OUT / "extension/final/manifest.json").read_text())
baseline = json.loads((OUT / "input-baseline.json").read_text())
assert source["files"] == binary["source"]
for name, expected in source["files"].items():
    assert sha(OUT / "source" / name) == expected
for name, expected in baseline["protected"].items():
    assert sha(Path(name)) == expected
assert sha(OUT / binary["path"]) == binary["sha256"]
assert "12 passed; 0 failed" in (OUT / "logs/native-practice-final.log").read_text()
assert "Ran 6 tests" in (OUT / "logs/binding-first.log").read_text()
assert "\nOK\n" in (OUT / "logs/binding-first.log").read_text()
commands = [json.loads(p.read_text()) for p in sorted((OUT / "logs").glob("*.json"))]
assert all(c["exit_code"] == 0 and not c["timed_out"] and c["wall_limit_seconds"] == 300
           for c in commands)
save("check-results.json", {"status": "all_captured_build_test_check_commands_passed",
                           "commands": commands, "initial_setup_failure": "logs/setup-first-failure.log",
                           "setup_failure_transcribed_from_tool_result": True,
                           "finalization_deadline_seconds": 300})
save("invocation.json", {"final_build": next(c for c in commands if c["name"] == "extension-build-final"),
                          "native_tests": next(c for c in commands if c["name"] == "native-practice-final"),
                          "binding_tests": next(c for c in commands if c["name"] == "binding-first"),
                          "stage_extension": next(c for c in commands if c["name"] == "stage-final"),
                          "host_manifest": "host-manifest.json",
                          "freeze_note": "Do not rerun into this frozen output; copy source into a new parent-owned successor."})
remaining = [
    "Prove correspondence to the accepted binary and disabled-cutoff parity on pinned synthetic seeds/actions; current Rust hashes do not prove accepted-binary correspondence.",
    "Integrate collector mask/info synchronization before audit/storage/bootstrap, preserve original final observation/rewards/counts, compute final value before one normal ascending subset reset; validate unchanged GAE and decision256/cross-rollout boundaries with no abandoned transitions.",
    "Pin one shared successor native binary/runtime/config/evaluator for curriculum and constant3e-5 control; only curriculum enablement differs. Complete identity/member/evaluator validation without weakening frozen validators.",
    "Complete authenticated accepted324 phase324/cumulative372 restore/reseed references without automatic replacement; no actual checkpoint was read here.",
    "Complete seed ancestry, exclusions, reservations and resource/cleanup/one-shot calibration and ceilings; parent owns seed/resource decisions.",
    "Obtain independent implementation review, parent registration, launch authorization and acceptance. B/E qualification remains closed."
]
save("receipt.json", {
    "schema": "progressive1000-native-build-repair-receipt-v1",
    "status": "preparation_complete_cpu_synthetic_tests_passed_parent_gates_open",
    "prepared_at_utc": datetime.now(timezone.utc).isoformat(), "owned_directory": str(OUT),
    "predecessor": str(PREVIOUS),
    "design_experiment_sha256": "c20bd35188c4b4dd36687bc10c7998e6410c70d37300be92db9a42b3d01c43c0",
    "design_scheduler_sha256": "a467b7219a9cd801fa3b403a6af112fc693ec3d14c9d311e8845632ef61d844b",
    "implementation_contract_sha256": sha(OUT.parent / "progressive1000-design-parent-acceptance-20261026-r1/implementation-contract.json"),
    "accepted_parent": {"phase_updates": 324, "cumulative_updates": 372,
         "checkpoint_sha256_supplied_not_read": "c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc",
         "automatic_replacement": False},
    "native_tests": {"initial_r1_source_passed": 10, "final_source_passed": 12,
                     "failed": 0, "python_features": False,
                     "synthetic_fixed_seed_values": "31..35, 131..135, 231..235; never study/B/E cohorts",
                     "coverage": ["H1000/H2000", "ordinary18000", "deathH-1/H/H+1 at both horizons",
                         "mixed ended/cutoff/continuing", "atomic invalid requests", "owned finalobs/pixels/history",
                         "reward/counter preservation", "one subset reset", "poison/overflow/seed exhaustion",
                         "thread/chunk invariance", "fixed18000/configured ceiling", "real996/1004 frame rejection"]},
    "binding_tests": {"passed": 6, "failed": 0, "imported_only_owned_native_extension": True,
                      "synthetic_fixed_seeds": [31, 32, 131, 132],
                      "live_h1000_with_normal_spawns": True,
                      "production_forced_death_or_restore_api_added": False,
                      "torch_or_mps": False},
    "build": {"interpreter_invocation": sys.executable, "python_version": sys.version,
              "venv_prefix": sys.prefix, "profile": binary["profile"],
              "macos_link_fix": "cargo rustc final-crate -C link-arg=-undefined -C link-arg=dynamic_lookup",
              "extension": {"path": binary["path"], "sha256": binary["sha256"]},
              "invocation_manifest": "invocation.json", "installed": False,
              "initial_pre_ceiling_extension_retained_not_imported": "extension/initial/",
              "initial_manifest_source_inventory_corrected_to_actual_pre_edit_baseline": True},
    "source": {"changed_from_r1": source["changed_from_r1"],
               "only_production_behavior_change_from_r1": "Reject H>=18000 even if configured cap is higher.",
               "core_unchanged": source["core_unchanged_from_r1_and_original"],
               "diffs": source["diffs"], "cargo_lock_sha256": source["files"]["Cargo.lock"],
               "source_manifest_sha256": sha(OUT / "source-manifest.json"),
               "dependency_manifest_sha256": sha(OUT / "dependency-manifest.json")},
    "failures_preserved": {"predecessor_binding_link": "R1 unchanged; _PyBaseObject_Type CPython symbols with Python3.11",
                           "successor_setup": "logs/setup-first-failure.log; existing scripts directory; copied hashes verified before finish-existing recovery",
                           "captured_build_test_failures": 0},
    "scope": {"writes": "owned successor only", "copied_source_not_prior_target": True,
              "own_cargo_home_target_tmp": True, "immutable_offline_registry_inputs_copied": True,
              "network_dependency_downloads": False, "predecessor_freeze_files_verified": source["predecessor_frozen_files_verified"],
              "listed_protected_inputs_unchanged": True, "whole_workspace_concurrent_write_attribution": False,
              "global_install_or_runtime_overwrite": False, "checkpoint_reads_or_deserialization": False,
              "study_cohort_or_B_E_use": False, "mps": False, "training_or_evaluation_campaign": False,
              "subdelegation": False, "commits_or_pushes": False,
              "parent_registration_seed_resource_launch_acceptance_owned_here": False},
    "limits": {"source_and_synthetic_evidence_only": True, "accepted_binary_correspondence_proven": False,
               "runtime_qualification": False, "independent_review": False,
               "all_captured_build_test_check_commands_have_300_second_deadline": True,
               "initial_setup_direct_invocation": "1.439 seconds to preserved FileExistsError; no subprocess deadline wrapper",
               "no_blanket_retry": "One setup repair; native test and extension rebuild followed source changes."},
    "remaining_parent_gates": remaining,
    "artifacts": {name: sha(OUT / name) for name in ["README.md", "review.md", "check-results.json",
                  "invocation.json", "input-baseline.json", "dependency-manifest.json", "host-manifest.json",
                  "source-manifest.json", "r1-to-r2.diff", "original-to-r2.diff", "binding_tests.py",
                  "extension/final/manifest.json"]},
    "finalization_invocation": [sys.executable, "-I", "-B", str(Path(__file__).absolute())],
    "freeze": "All owned files and directories become read-only after freeze-manifest generation. No parent gate is granted."
})
files = {}
for p in sorted(OUT.rglob("*")):
    assert not p.is_symlink(), p
    if p.is_file():
        files[str(p.relative_to(OUT))] = {"sha256": sha(p), "bytes": p.stat().st_size}
save("freeze-manifest.json", {"schema": "progressive1000-owned-successor-freeze-v1",
                              "files": files, "self_excluded": True})
summary = {"receipt_sha256": sha(OUT / "receipt.json"),
           "freeze_manifest_sha256": sha(OUT / "freeze-manifest.json"),
           "binary_sha256": binary["sha256"], "r1_diff_sha256": source["diffs"]["r1-to-r2.diff"]["sha256"],
           "files_frozen": len(files), "native_passed": 12, "binding_passed": 6}
for p in sorted(OUT.rglob("*"), key=lambda p: len(p.parts), reverse=True):
    p.chmod(p.stat().st_mode & ~0o222)
OUT.chmod(OUT.stat().st_mode & ~0o222)
signal.alarm(0)
print(json.dumps(summary), flush=True)
