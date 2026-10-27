"""Read-only byte/receipt checks. Does not execute project or native code."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import tarfile
import traceback
import zipfile

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
EV = ROOT / "learning/runs/v2/milestone2-integration-r2"
H = ROOT / "learning/runs/v2/milestone2-validation-harness-r1"
CAP = ROOT / "learning/.cache/v2-m2-campaign-review-r1"
CHECKS = []
HASHES = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(group, path, expected):
    path = Path(path)
    actual = sha(path)
    assert actual == expected, (group, str(path), actual, expected)
    HASHES.setdefault(group, {})[str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)] = actual


def load(path):
    return json.loads(Path(path).read_text())


def note(name, result):
    CHECKS.append({"name": name, "result": result})


def audit():
    checked("frozen_identity", EV / "frozen-identity.json", "8a0065bfdf292c3112bb9026d28aae2ebbc174ab4c25c0100151eb091a5dca64")
    checked("capsule_manifest", CAP / "manifest.json", "701d153e7281ec1a97c1b648a9abe031757659e8c1d9e78a38a915c8c1b16539")
    manifest = load(CAP / "manifest.json")
    for name, expected in manifest["files"].items():
        checked("capsule", CAP / name, expected)
    assert len(manifest["files"]) == 82
    build = load(EV / "build-receipt.json")
    parent = load(EV / "parent-verification.json")
    identity = load(EV / "frozen-identity.json")
    sources = load(EV / "prebuild-source-manifest.json")
    assert sources == identity["source_sha256"] and len(sources) == 62
    for name, expected in sources.items():
        checked("current_source", ROOT / name, expected)
    for name, expected in identity["binary_and_receipt_sha256"].items():
        checked("identity_binary_and_receipt", name, expected)
    for name, field in (("prebuild-source-manifest.json", "source_manifest_sha256"), ("prebuild-source.tar.gz", "source_archive_sha256"), ("build-receipt.json", "build_receipt_sha256"), ("frozen-identity.json", "identity_sha256")):
        checked("parent_receipt_references", EV / name, parent[field])
    assert build["source_manifest_sha256"] == parent["source_manifest_sha256"]
    assert build["source_archive_sha256"] == parent["source_archive_sha256"]
    assert build["status"] == "passed" and build["source_unchanged_through_checks"]
    assert not build["full_campaign_executed"] and not parent["full_campaign_executed"]
    with tarfile.open(EV / "prebuild-source.tar.gz", "r:gz") as archive:
        assert {member.name for member in archive.getmembers()} == set(sources)
        for name, expected in sources.items():
            assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == expected, name
    note("prebuild_archive_and_current_frozen_identity_match", len(sources))

    required_inputs = {".cargo/config.toml", "Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "assets/dodge.p8", "crates/dodge-core/build.rs"}
    required_inputs.update(str(path.relative_to(ROOT)) for path in (ROOT / "crates").rglob("Cargo.toml"))
    required_inputs.update(str(path.relative_to(ROOT)) for path in (ROOT / "crates").rglob("*.rs"))
    required_inputs.update(str(path.relative_to(ROOT)) for path in (ROOT / "python/dodge_rl").rglob("*.py"))
    required_inputs.update(str(path.relative_to(ROOT)) for path in (ROOT / "python/tests").rglob("*.py"))
    assert required_inputs <= set(sources), sorted(required_inputs-set(sources))
    runner = (EV / "run_checks.py").read_text()
    assert runner.index('write_new(OUT / "prebuild-source-manifest.json", SOURCES)') < runner.index('run("default-crate-tests"')
    assert 'assert harness.source_inventory() == SOURCES' in runner
    assert 'archive.add(ROOT / name, arcname=name)' in runner
    assert 'read_to_string(&source_path)' in (ROOT / "crates/dodge-core/build.rs").read_text()
    assert '../../assets/dodge.p8' in (ROOT / "crates/dodge-core/build.rs").read_text()
    note("prior_missing_build_inputs_in_new_prebuild_freeze", {name: sources[name] for name in (".cargo/config.toml", "crates/dodge-core/Cargo.toml", "assets/dodge.p8")})

    commands = [json.loads(line) for line in (EV / "commands.jsonl").read_text().splitlines()]
    assert commands == build["commands"] and len(commands) == 9
    for command in commands:
        assert command["exit_code"] == 0 and not command.get("timeout"), command["name"]
        checked("command_logs", ROOT / command["log"], command["log_sha256"])
        assert command["environment_overrides"]["CARGO_TARGET_DIR"].endswith("v2-m2-integration-build-r2")
        assert command["elapsed_seconds"] < command["timeout_seconds"]
    tests = (EV / "default-crate-tests.log").read_text()
    counts = re.findall(r"test result: ok\. (\d+) passed; 0 failed; (\d+) ignored", tests)
    assert counts == [("41", "2"), ("35", "0"), ("0", "0")], counts
    assert "test qualification_replay_tests::frozen_m0_full_heuristic_d2_d3 ... ignored" in tests
    assert len(re.findall(r"^test tests::m0_policy::.* \.\.\. ok$", tests, re.M)) == 8
    assert "68 passed" in (EV / "real-extension-pytest.log").read_text()
    compile_command = next(c for c in commands if c["name"] == "release-test-compile")
    assert "--no-run" in compile_command["command"] and "--release" in compile_command["command"]
    artifacts = []
    for line in (EV / "release-test-compile.log").read_text().splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("reason") == "compiler-artifact" and item.get("executable") and item.get("profile", {}).get("test") and item.get("target", {}).get("name") == "dodge_rl_env":
            artifacts.append(item)
    binary = load(EV / "native-test-binary.json")
    assert len(artifacts) == 1 and artifacts[0] == binary["compiler_artifact"]
    assert artifacts[0]["executable"] == binary["path"] == build["native_test_binary"] == identity["native_test_binary"]
    checked("native_test_binary", binary["path"], binary["sha256"])
    assert binary["sha256"] == build["native_test_binary_sha256"]
    native_command = next(c for c in commands if c["name"] == "small-d2-replay")["command"]
    assert native_command[0] == binary["path"] and native_command[1] == "tests::frozen_m0_ten_paired_episodes_per_policy"
    assert "--exact" in native_command and "--ignored" in native_command
    note("fresh_build_checks_counts_and_actual_test_artifact", {"rust_unit":41, "rust_primitive":35, "rust_total":76, "rust_ignored_compiled":2, "shared_policy_helper_tests":8, "python_cases":68, "commands":9})

    extension_sha = build["installed_extension_sha256"]
    assert extension_sha == "967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583"
    for path in (Path(build["installed_extension"]), EV / "native.cpython-312-darwin.so"):
        checked("extension", path, extension_sha)
    assert identity["runtime"]["extension_sha256"] == extension_sha
    wheels = list((EV / "wheels").glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        native_files = [name for name in wheel.namelist() if name.endswith(".so")]
        assert len(native_files) == 1
        assert hashlib.sha256(wheel.read(native_files[0])).hexdigest() == extension_sha
        assert wheel.read("dodge_rl/__init__.py") == (ROOT / "python/dodge_rl/__init__.py").read_bytes()
    HASHES.setdefault("wheel", {})[str(wheels[0].relative_to(ROOT))] = sha(wheels[0])
    note("fresh_installed_archived_and_wheel_extension_match", True)

    core = load(ROOT / "learning/runs/v2/milestone2-core-r1/source-manifest.json")["source_sha256"]
    for name, expected in core.items():
        checked("accepted_core", ROOT / name, expected)
    for name, expected in {"crates/dodge-rl-env/src/geometry.rs":"5b04907b9d87b336b685922ac0c7f235174e347e5a5308b1ebb1645c6014c171", "crates/dodge-rl-env/src/raster.rs":"a48c80a0a549e76e7e77bdd79ef2aa0b6171669d761770c6b33b3ea0921a6927", "crates/dodge-rl-env/src/features.rs":"78d72ee29fdcf2c0828e26d0a4265b50809f4c9899183332a4c48fb326dc006c", "crates/dodge-rl-env/tests/support/m0_policy.rs":"eeae605299b1018437a54df66f4eabf6e6d4defc20334c1baf93692900601b85"}.items():
        checked("accepted_math_features_policy", ROOT/name, expected)
    prior_tests = (ROOT / "learning/.cache/v2-m2-binding-review-r1/crates/dodge-rl-env/src/tests.rs").read_text()
    assert prior_tests.replace("mod m0_policy;", "pub(crate) mod m0_policy;", 1) == (ROOT / "crates/dodge-rl-env/src/tests.rs").read_text()
    template = (H / "qualification_replay_tests.rs").read_text()
    integrated = (ROOT / "crates/dodge-rl-env/src/qualification_replay_tests.rs").read_text()
    assert template.replace('#[path = "../tests/support/m0_policy.rs"]\nmod m0_policy;', "use crate::tests::m0_policy;") == integrated
    original_table = (H / "qualification_expected.rs").read_text()
    table = (ROOT / "crates/dodge-rl-env/tests/support/qualification_expected.rs").read_text()
    assert original_table.replace("const EXPECTED_D2:", "static EXPECTED_D2:").replace("const EXPECTED_D3:", "static EXPECTED_D3:") == table
    note("test_only_wiring_and_static_storage_changes_preserve_assertions_rows_policy", True)

    generation = load(H / "expected-generation.json")
    checked("generated_expected", H / "qualification_expected.rs", generation["generated_sha256"])
    row_pattern = re.compile(r"Expected \{ seed: (\d+), score: (-?\d+), frames: (\d+), alive: (\d+), dead: (true|false), cap: (true|false), full_state_hash: (\d+), death_events: (\d+) \}")
    rows = [tuple(int(value) if value not in ("true","false") else value=="true" for value in match) for match in row_pattern.findall(table)]
    assert len(rows) == 2000
    originals = {}
    for name, expected in generation["source_files"].items():
        checked("original_baselines", ROOT/name, expected)
        with (ROOT/name).open() as stream:
            dataset = [json.loads(line) for line in stream]
        difficulty = 3 if "/d3/" in name else 2
        originals[difficulty] = dataset
        baseline = sorted((row for row in dataset if row["policy"] == "nearest_lethal_aabb_safe_powerup"),key=lambda row:row["episode_index"])
        assert len(baseline) == 1000
        expected_rows = []
        for index, reference in enumerate(baseline):
            assert reference["episode_index"] == index and reference["seed"] == 0xB0000000+index
            assert reference["native_config"]["difficulty"] == difficulty and reference["startup_native_frames_excluded"] == 13
            assert reference["native_config"]["patterns_enabled"] and reference["native_config"]["powerups_enabled"]
            assert reference["native_config"]["theme_background_shadow"] == [12,1]
            assert reference["episode_status"] == "complete" and not reference["failure"]
            expected_rows.append((reference["seed"],reference["scores"]["final_score_raw_fixed"],reference["gameplay_native_frames"],reference["raw_survival_frames"],reference["death"],reference["cap_truncation"],reference["final_state_hash"],reference["frame_event_counts_enemy_spawn_collision_death_pattern_active_terminal"][2]))
        assert rows[(difficulty-2)*1000:(difficulty-1)*1000] == expected_rows
    note("all_2000_heuristic_expected_rows_match_8_original_fields", True)

    original_map = {(row["policy"],row["seed"]):row for row in originals[2]}
    replay = (EV/"small-d2-replay.log").read_text()
    episodes = [json.loads(line.split("REPLAY_EPISODE ",1)[1]) for line in replay.splitlines() if "REPLAY_EPISODE " in line]
    assert len(episodes) == 30 and len({(row["policy"],row["seed"]) for row in episodes}) == 30
    for row in episodes:
        reference = original_map[(row["policy"],row["seed"])]
        assert 0 <= reference["episode_index"] < 10
        wanted = {"score_raw_fixed":reference["scores"]["final_score_raw_fixed"],"raw_frames":reference["gameplay_native_frames"],"alive_frames":reference["raw_survival_frames"],"terminated":reference["death"],"truncated":reference["cap_truncation"],"death_events":reference["frame_event_counts_enemy_spawn_collision_death_pattern_active_terminal"][2],"full_state_hash":reference["final_state_hash"]}
        assert all(row[key] == value for key,value in wanted.items())
        assert row["objective_return"] == wanted["score_raw_fixed"]/65536 + wanted["alive_frames"]/100 - 5*wanted["terminated"]
    total = [json.loads(line.split("REPLAY_TOTAL ",1)[1]) for line in replay.splitlines() if "REPLAY_TOTAL " in line]
    assert len(total)==1 and total[0]["episodes"]==30 and total[0]["raw_frames_per_path"]==sum(row["raw_frames"] for row in episodes)==69326
    note("fresh_30_D2_replay_rows_match_originals", {"episodes":30,"raw_frames_per_path":69326,"patterns":total[0]["catalog_ids_seen"]})

    old_failure = ROOT/"learning/runs/v2/milestone2-integration-r1/clippy-repair-reconciliation.json"
    failure = load(old_failure)
    checked("prior_failure", ROOT/failure["source_run"]/"workspace-clippy.log", failure["log_sha256"])
    assert failure["first_normal_tests"]["included_eight_duplicate_helper_executions"]
    assert failure["limit_relaxation"] is False and failure["full_campaign_executed"] is False
    pure_log = (H/"target-pure-tests.log").read_text()
    assert "Ran 9 tests" in pure_log and "OK" in pure_log
    source_manifest = load(H/"source-manifest.json")
    for name,expected in source_manifest["source_sha256"].items():
        checked("unchanged_harness_sources", ROOT/name, expected)
    note("retained_failures_and_pure_9_tests_distinguished_from_campaign", True)
    return {
        "status":"passed_declared_build_and_pre_campaign_receipts",
        "findings":[], "checks":CHECKS,
        "counts":{group:len(files) for group,files in HASHES.items()},
        "verified_hashes":HASHES,
        "limitations":[
            "No compiler, test, native simulation, extension import, or benchmark executed by this audit.",
            "Build provenance is based on retained source pre/post checks, isolated-target commands and compiler artifacts, not an independently repeated build.",
            "Complete input pins resolve the prior manifest-scope gap for this new build only; original receipts remain historical.",
            "Early overwritten intermediate binding binaries remain unavailable.",
            "76 normal Rust tests and 68 Python cases are retained execution evidence. Full native 2000-episode replay is compiled and ignored, not run.",
            "Full D2/D3 parity, post-warmup memory, throughput and teacher qualification remain unproven."
        ]
    }


started = datetime.now(timezone.utc).isoformat()
try:
    result = audit()
except BaseException as error:
    result={"status":"checker_failed", "error":repr(error), "traceback":traceback.format_exc(), "checks_completed":CHECKS}
    failure_path=OUT/f"checker-failure-{len(list(OUT.glob('checker-failure*.json')))+1}.json"
    with failure_path.open("x") as stream:
        json.dump(result,stream,indent=2);stream.write("\n")
    raise
result.update(started_at_utc=started,completed_at_utc=datetime.now(timezone.utc).isoformat(),checker_sha256=sha(Path(__file__)))
with (OUT/"audit.json").open("x") as stream:
    json.dump(result,stream,indent=2,sort_keys=True);stream.write("\n")
print(json.dumps({"status":result["status"],"counts":result["counts"],"audit_sha256":sha(OUT/"audit.json")}))
