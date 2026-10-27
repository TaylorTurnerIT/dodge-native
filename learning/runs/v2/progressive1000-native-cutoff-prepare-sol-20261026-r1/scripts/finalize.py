"""Read-only source checks and owned receipts; never builds or imports targets."""
from pathlib import Path
import ast
import datetime
import difflib
import hashlib
import json
import re
import tomllib

OUT = Path(__file__).resolve().parents[1]
ROOT = OUT.parents[3]
assert ROOT == Path("/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


manifest = json.loads((OUT / "source-manifest.json").read_text())
manifest["source_root_after"] = {p: sha(ROOT / p) for p in manifest["source_before"]}
manifest["external_after"] = {p: sha(ROOT / p) for p in manifest["external_before"]}
manifest["root_readme_after"] = sha(ROOT / "README.md")
assert manifest["source_before"] == manifest["source_root_after"]
assert manifest["external_before"] == manifest["external_after"]
assert manifest["root_readme_before"] == manifest["root_readme_after"]
for rel, expected in manifest["source_before"].items():
    assert sha(OUT / "originals" / rel) == expected
manifest["owned_source_after"] = {
    str(p.relative_to(OUT / "source")): sha(p)
    for p in sorted((OUT / "source").rglob("*")) if p.is_file()
}
manifest["scope_limit"] = "Listed input hashes only; no whole-workspace/concurrent-write attribution claim."
save("source-manifest.json", manifest)

patches = []
changed = []
all_files = sorted(set(manifest["source_before"]) | set(manifest["owned_source_after"]))
for rel in all_files:
    original = OUT / "originals" / rel
    source = OUT / "source" / rel
    old = original.read_text().splitlines(keepends=True) if original.exists() else []
    new = source.read_text().splitlines(keepends=True) if source.exists() else []
    if old == new:
        continue
    delta = list(difflib.unified_diff(old, new, fromfile="a/" + rel if original.exists() else "/dev/null",
                                      tofile="b/" + rel if source.exists() else "/dev/null"))
    # Independently apply each unified hunk to retained input lines.
    rebuilt = []
    cursor = 0
    in_hunk = False
    for line in delta[2:]:
        if line.startswith("@@"):
            match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            assert match
            old_count = int(match[2]) if match[2] is not None else 1
            start = int(match[1]) - (1 if old_count else 0)
            assert start >= cursor
            rebuilt.extend(old[cursor:start])
            cursor = start
            in_hunk = True
        else:
            assert in_hunk
            if line[0] in " -":
                assert old[cursor] == line[1:]
                if line[0] == " ":
                    rebuilt.append(old[cursor])
                cursor += 1
            elif line[0] == "+":
                rebuilt.append(line[1:])
            else:
                raise AssertionError(line)
    rebuilt.extend(old[cursor:])
    assert rebuilt == new, rel
    patches.extend(delta)
    changed.append(rel)
(OUT / "exact.diff").write_text("".join(patches))

env_rel = Path("crates/dodge-rl-env/src/env.rs")
old_env = (OUT / "originals" / env_rel).read_text()
new_env = (OUT / "source" / env_rel).read_text()
def between(text, begin, end):
    return text.split(begin, 1)[1].split(end, 1)[0]
assert between(old_env, "pub struct EpisodeInfo {", "pub struct StepBatch {") == between(new_env, "pub struct EpisodeInfo {", "pub struct StepBatch {")
assert between(old_env, "    fn advance(", "    /// Captured at the first dead frame") == between(new_env, "    fn advance(", "    /// Captured at the first dead frame")
assert between(old_env, "    pub fn step(", "    fn poison(") == between(new_env, "    pub fn step(", "    fn poison(")
test_module = '#[cfg(test)]\n#[path = "practice_tests.rs"]\nmod practice_tests;\n\n'
assert new_env.count(test_module) == 1
assert old_env.split("    /// Only `reset_all`", 1)[1] == new_env.replace(test_module, "").split("    /// Only `reset_all`", 1)[1]
core_files = [p for p in manifest["source_before"] if p.startswith("crates/dodge-core/")]
assert all(manifest["source_before"][p] == manifest["owned_source_after"][p] for p in core_files)
for rel in ["src/features.rs", "src/config.rs", "src/seed.rs"]:
    key = "crates/dodge-rl-env/" + rel
    assert manifest["source_before"][key] == manifest["owned_source_after"][key]
old_lock = tomllib.loads((OUT / "originals/Cargo.lock").read_text())["package"]
new_lock = tomllib.loads((OUT / "source/Cargo.lock").read_text())["package"]
old_packages = {(p["name"], p["version"], p.get("source")): p for p in old_lock}
for package in new_lock:
    old = old_packages[(package["name"], package["version"], package.get("source"))]
    assert package.get("checksum") == old.get("checksum")
python_paths = [OUT / "binding_tests_pending.py", *sorted((OUT / "scripts").glob("*.py"))]
for path in python_paths:
    ast.parse(path.read_text(), filename=str(path))
test_source = (OUT / "source/crates/dodge-rl-env/src/practice_tests.rs").read_text()
tests = re.findall(r"#\[test\]\s*fn (\w+)", test_source)
assert len(tests) == 10
checks = json.loads((OUT / "check-results.json").read_text())
assert checks["status"] == "failed"
assert [(c["name"], c["exit_code"]) for c in checks["commands"]] == [("format", 0), ("binding-build", 101)]
(OUT / "logs/native-unit.log").write_text("NOT RUN. Stop-on-failure after binding-build exit101.\nIntended: cargo test --offline -p dodge-rl-env --lib practice_tests:: -- --test-threads=1 --nocapture\nTen authored tests have neither compile nor execution evidence. No native simulation executed.\n")
(OUT / "logs/python-binding-tests.log").write_text("NOT RUN. Authored tests AST-parsed only. No target import, Python environment construction or extension installation.\n")
static = {
    "status": "passed_source_checks_only",
    "design_pins_match": True,
    "original_source_files": len(manifest["source_before"]),
    "external_files": len(manifest["external_before"]),
    "listed_originals_and_external_inputs_unchanged": True,
    "root_readme_unchanged": True,
    "exact_diff_reconstruction": True,
    "changed_owned_source_files": changed,
    "core_unchanged_files": len(core_files),
    "episode_info_schema_step_advance_reset_features_config_seed_unchanged": True,
    "retained_lock_versions_sources_checksums_unchanged": True,
    "python_ast_only": [str(p.relative_to(OUT)) for p in python_paths],
    "rust_tests_authored_not_compiled_not_run": tests,
}
save("static-checks.json", static)
(OUT / "logs/static-checks.log").write_text(json.dumps(static, indent=2) + "\n")
artifacts = {str(p.relative_to(OUT)): {"sha256": sha(p), "bytes": p.stat().st_size}
             for p in sorted((OUT / "target").rglob("*")) if p.is_file()}
save("build-artifacts.json", {"status": "partial_failed_build_not_runtime", "files": artifacts})
receipt = {
    "schema": "progressive1000-native-cutoff-preparation-receipt-v1",
    "status": "frozen_source_preparation_binding_link_failed_native_unit_tests_unrun",
    "prepared_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "owned_directory": str(OUT),
    "accepted_parent": {"phase_updates": 324, "cumulative_updates": 372,
        "checkpoint_sha256_supplied_not_read": manifest["accepted_parent_checkpoint_sha256_supplied_not_read"]},
    "design_experiment_sha256": "c20bd35188c4b4dd36687bc10c7998e6410c70d37300be92db9a42b3d01c43c0",
    "design_scheduler_sha256": "a467b7219a9cd801fa3b403a6af112fc693ec3d14c9d311e8845632ef61d844b",
    "native_api": "VecDodgeEnv::truncate_practice(&mut self, indices: &[usize], horizons: &[u32]) -> Result<Vec<EpisodeInfo>, EnvError>",
    "python_api": "VecDodgeEnv.truncate_practice(indices, horizons) -> list of owned EpisodeInfo dictionaries",
    "mutation": "Only selected truncated flags become true after whole-request validation; terminated is already false. No other slot field changes.",
    "overflow": "Selected episode u64::MAX rejects entire cutoff; next-seed availability remains normal reset prevalidation. No counter increments during cutoff.",
    "schema": "progressive1000-native-cutoff-preparation-receipt-v1",
    "checks": checks,
    "initial_setup_failure": "Python3.9 lacks tomllib; failed before writes. Existing Python3.11 used for scripts; no installation.",
    "binding_build_failure": {"phase": "macOS cdylib link", "exit_code": 101,
        "raw_error": "error: linking with `cc` failed: exit status: 1",
        "raw_summary": "ld: symbol(s) not found for architecture arm64",
        "example_symbol": "_PyBaseObject_Type",
        "diagnosis": "Direct Cargo extension-module link has neither CPython linkage nor dynamic-lookup arguments; normal project packaging uses maturin.",
        "retry": False, "fix_attempted": False, "extension_installed_or_imported": False},
    "build_python": {"executable": "/Users/taylor/.local/bin/python3.11", "package_requires": ">=3.12", "accepted_runtime_identity_proven": False},
    "native_tests": {"authored": len(tests), "compiled": False, "run": 0, "passed": 0, "simulation_executed": False,
        "reason": "Ordered driver stopped immediately after binding build failure; no further cargo commands."},
    "python_binding_tests": {"authored": True, "ast_parsed": True, "imported": False, "run": 0},
    "static_checks": "static-checks.json",
    "source_manifest": "source-manifest.json",
    "exact_diff": {"path": "exact.diff", "sha256": sha(OUT / "exact.diff"), "reconstruction_checked": True},
    "isolation": {"writes": "owned successor only", "offline": True, "own_cargo_home_target_tmp": True,
        "per_command_wall_limit_seconds": 300, "blanket_retries": False, "subdelegation": False,
        "checkpoint_reads_or_deserialization": False, "mps": False, "study_seeds_or_B_E_opened": False,
        "training_or_evaluation_campaign": False, "launch": False,
        "listed_input_hashes_unchanged": True, "root_readme_unchanged": True},
    "remaining_gates": [
        "Working pinned successor build/link with intended Python/dependencies; execute native CPU tests and binding input/ownership tests.",
        "Collector synchronization before audit/storage/bootstrap, owned final observation before one subset reset, decision256/cross-rollout and unchanged GAE validation.",
        "Disabled-cutoff accepted-binary parity and full history/reward/death/diagnostic parity; current Rust hashes do not prove accepted-binary correspondence.",
        "One new binary/runtime/config/evaluator for both arms; only curriculum enablement differs; pin successor identity/member/evaluator validation without weakening frozen validators.",
        "Accepted324 authenticated restore/reseed measured references, complete seed ancestry/exclusions/reservations, resource/cleanup/one-shot ceilings, independent review and registration before launch."
    ],
    "freeze": "Files/directories made read-only after freeze-manifest creation; any repair requires a new successor. No passing qualification claim."
}
save("receipt.json", receipt)
inventory = {str(p.relative_to(OUT)): {"sha256": sha(p), "bytes": p.stat().st_size}
             for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != "freeze-manifest.json"}
save("freeze-manifest.json", {"schema": "owned-readonly-freeze-v1", "files": inventory,
     "self_excluded": "freeze-manifest.json", "source_evidence": "preparation_only_not_qualification"})
for path in sorted(OUT.rglob("*"), key=lambda p: len(p.parts), reverse=True):
    path.chmod(path.stat().st_mode & ~0o222)
OUT.chmod(OUT.stat().st_mode & ~0o222)
print(json.dumps({"status": receipt["status"], "source_files": len(manifest["owned_source_after"]),
    "changed_source_files": changed, "rust_tests_authored_unrun": len(tests),
    "freeze_inventory_files": len(inventory), "freeze_manifest_sha256": sha(OUT / "freeze-manifest.json")}))
