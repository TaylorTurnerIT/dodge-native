"""Independent standard-library receipt audit; audited code is never imported."""
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile
import traceback

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
TARGET = ROOT / "learning/runs/v2/milestone3-trainer-runtime-r1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    report = {
        "schema": "independent_M3_trainer_component_receipt_audit_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Byte/hash, archive, AST and retained-log audit only; no audited project import or execution.",
        "checks": [], "findings": [], "failures": [],
        "limitations": [
            "Retained commands, source snapshots and logs are audited; tests and CLI commands were not rerun.",
            "No end-to-end trainer execution, game learning, MPS compatibility or whole-pipeline readiness follows from this audit.",
            "Synthetic fixtures intentionally include non-JSON files with .json suffixes; only declared receipts are parsed.",
            "Version strings are retained runtime observations; interpreter, installed extension, native executable and receipt bytes are independently hashed.",
            "Current preservation is checked against recorded pins; it does not reconstruct a complete pre-edit checkout or prove historical execution independently.",
        ],
        "checker_sha256": sha(Path(__file__)),
    }
    try:
        frozen = read(TARGET / "frozen-result-manifest.json")
        require(sha(TARGET / "frozen-result-manifest.json") == "cde0136716cbf9a2c64b0385ef7b339d92f1f249c0c958b056d84279ecfa3c2c", "Frozen manifest pin differs")
        manifest = read(TARGET / "artifact-sha256.json")
        require(len(manifest) == frozen["artifact_count"] == 720, "Artifact count differs")
        require(sha(TARGET / "artifact-sha256.json") == frozen["artifact_manifest_sha256"], "Artifact manifest hash differs")
        actual = {str(p.relative_to(TARGET)) for p in TARGET.rglob("*") if p.is_file()
                  and p not in (TARGET / "artifact-sha256.json", TARGET / "frozen-result-manifest.json")}
        require(actual == set(manifest), "Exact artifact coverage differs")
        for name, expected in manifest.items():
            require(sha(TARGET / name) == expected, f"Artifact changed: {name}")
        protected = read(TARGET / "protected-inputs-verified.json")
        source = read(TARGET / "source-manifest.json")
        result = read(TARGET / "result.json")
        final_identity = read(TARGET / "cli-final-preparation-identity.json")
        input_paths = {p for p in TARGET.rglob("*") if p.is_file()}
        input_paths.update(ROOT / name for name in protected["files"])
        input_paths.update(ROOT / name for name in final_identity["sources"])
        input_paths.update(Path(name) for name in final_identity["foundation"]["binary_and_receipt_sha256"])
        input_paths.add(Path(final_identity["foundation"]["extension_path"]))
        before = {str(p): sha(p) for p in sorted(input_paths)}
        report["checks"].append({"check": "exact_artifact_manifest", "passed": True,
                                 "artifact_hashes": len(manifest),
                                 "nested_fixture_manifests_included": True})

        for name, key in (("result.json", "result_sha256"), ("source.tar.gz", "source_archive_sha256"),
                          ("source-manifest.json", "source_manifest_sha256"), ("source.patch", "source_patch_sha256")):
            require(sha(TARGET / name) == frozen[key], f"Frozen component reference differs: {name}")
        require(sha(TARGET / "result.json") == "e858fcb3cd316c634f53c491db529aa64b5eba8d8ebc239fb1a2280e4e1f1fa0", "Result pin differs")
        require(source == result["owned_source_sha256"] and len(source) == 7, "Owned source manifests differ")
        for name, expected in source.items():
            require(sha(ROOT / name) == sha(TARGET / "source" / name) == expected, f"Owned source differs: {name}")
            ast.parse((TARGET / "source" / name).read_text())
        with tarfile.open(TARGET / "source.tar.gz") as archive:
            members = archive.getmembers()
            require(len(members) == 7 and {m.name for m in members} == set(source), "Archive coverage differs")
            require(all(m.isfile() for m in members), "Archive has non-file payload")
            order = [m.name for m in members]
            for member in members:
                data = archive.extractfile(member).read()
                require(hashlib.sha256(data).hexdigest() == source[member.name], f"Archive member differs: {member.name}")
        generated_patch = "".join("".join(difflib.unified_diff([], (TARGET / "source" / name).read_text().splitlines(True),
                                                              fromfile="/dev/null", tofile=name)) for name in order)
        require(generated_patch == (TARGET / "source.patch").read_text(), "Added-file patch reconstruction differs")
        require(protected["changed"] == [] and len(protected["files"]) == 67, "Protected-input declaration differs")
        for name, expected in protected["files"].items():
            require(sha(ROOT / name) == expected, f"Protected input changed: {name}")
        report["checks"].append({"check": "live_sources_archive_patch_and_protected_inputs", "passed": True,
                                 "owned_sources": 7, "archive_members": 7,
                                 "exact_patch_reconstruction": True, "protected_inputs": 67})

        retained = []
        for attempt in result["test_attempts"]:
            number = attempt["attempt"]
            command = read(TARGET / attempt["command_receipt"])
            require(command["command"][:6] == ["python/.venv/bin/python", "-B", "-W", "error", "-m", "pytest"], "Unexpected test command")
            require(command["command"][-2:] == ["python/tests/test_checkpoints.py", "python/tests/test_teacher_runner.py"], "Unexpected test scope")
            require(command["command"][command["command"].index("--basetemp") + 1].endswith(f"pytest-attempt{number}"), "Fixture ownership differs")
            require(set(command["source_sha256"]) == set(source), "Test snapshot scope differs")
            for name, expected in command["source_sha256"].items():
                require(sha(TARGET / f"test-attempt{number}-source" / name) == expected, f"Test snapshot differs: {number}/{name}")
            log = TARGET / attempt["log"]
            require(sha(log) == attempt["log_sha256"], "Test log hash differs")
            text = log.read_text()
            require(re.search(rf"\b{attempt['passed']} passed\b", text) is not None, "Passing count differs")
            if attempt["failed"]:
                require(attempt["exit_code"] == 1 and re.search(rf"\b{attempt['failed']} failed\b", text), "Failure count differs")
            else:
                require(attempt["exit_code"] == 0 and " failed" not in text, "Unexpected failure in passing receipt")
            retained.append({"attempt": number, "passed": attempt["passed"], "failed": attempt["failed"],
                             "exit_code": attempt["exit_code"], "source_pins": len(command["source_sha256"])})
        last = read(TARGET / "test-attempt5-command.json")
        require(last["source_sha256"] == source and result["unique_final_tests_passed"] == 64, "Final passing source differs")
        failed = read(TARGET / "test-attempt4-command.json")
        production = [name for name in source if name.startswith("python/dodge_rl/")]
        require(all(failed["source_sha256"][name] == source[name] for name in production), "Production changed for fixture correction")
        name = "python/tests/test_teacher_runner.py"
        old = (TARGET / "test-attempt4-source" / name).read_text()
        new = (TARGET / "test-attempt5-source" / name).read_text()
        addition = "    model.context['D1_competence_demonstrated']=False\n    model.model=FakePolicy();model.device=torch.device('cpu')\n"
        require(new.replace(addition, "", 1) == old, "Fixture correction differs from two initialization lines")
        assertions = lambda text: [ast.dump(node, include_attributes=False) for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Assert)]
        require(assertions(old) == assertions(new), "Fixture correction changed assertions")
        require("KeyError: 'D1_competence_demonstrated'" in (TARGET / "test-attempt4.log").read_text(), "Original fixture error not retained")
        report["checks"].append({"check": "retained_test_commands_snapshots_and_discriminated_fixture_correction", "passed": True,
                                 "attempts": retained, "final_tests_passed": 64,
                                 "production_files_unchanged_between_attempts_4_5": 5,
                                 "test_assertions_unchanged": True})

        raw_config = (TARGET / "cli-probe-config.json").read_bytes()
        config = json.loads(raw_config)
        raw_hash = hashlib.sha256(raw_config).hexdigest()
        semantic_hash = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        protocol = read(ROOT / "docs/v2-m3-run-protocol.json")
        require(config["phase_settings"] == protocol["seed_namespace_table"]["probe"], "Registered u64 namespace differs")
        require(isinstance(config["phase_settings"]["run_seed"], int) and config["phase_settings"]["run_seed"] > 2**53, "u64 seed representation differs")
        require(final_identity["config"] == config and final_identity["config_sha256"] == semantic_hash, "Semantic identity/config differs")
        require(raw_hash != semantic_hash, "Raw and canonical config unexpectedly conflated")
        for command in read(TARGET / "cli-preparation-commands.json")["commands"]:
            require(command["exit_code"] == 0 and command["argv"][6] in {"config", "freeze"}, "Unexpected CLI execution scope")
            log = TARGET / command["stdout"]
            require(sha(log) == command["stdout_sha256"], "CLI log pin differs")
            record = json.loads(log.read_text())
            require(record["config_sha256"] == raw_hash, "CLI raw config hash differs")
            if "identity" in record:
                require(sha(ROOT / record["identity"]) == record["identity_sha256"], "CLI identity document hash differs")
                require(record["semantic_config_sha256"] == semantic_hash, "CLI semantic config hash differs")
        require(sha(TARGET / "cli-final-preparation-identity.json") == result["CLI_preparation"]["candidate_identity_sha256"]
                == "464c8a99f65d2223885de5715a0c7b23c8f8dc98510c923409778cffcc21116d", "Final preparation identity differs")
        for name, expected in final_identity["sources"].items():
            require(sha(ROOT / name) == expected, f"Final CLI source pin differs: {name}")
        foundation = final_identity["foundation"]
        for name, expected in foundation["native_inputs"].items():
            require(sha(ROOT / name) == expected, f"Native lineage source differs: {name}")
        for name, expected in foundation["binary_and_receipt_sha256"].items():
            require(sha(Path(name)) == expected, f"Native lineage binary/receipt differs: {name}")
        require(sha(Path(foundation["extension_path"])) == foundation["extension_sha256"]
                == "967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583", "Extension differs")
        require(sha(Path(final_identity["runtime"]["interpreter"])) == final_identity["runtime"]["interpreter_sha256"], "Interpreter differs")
        require(sha(ROOT / "learning/runs/v2-orchestration/milestone2-acceptance-r2.json") == foundation["acceptance_sha256"], "Foundation acceptance differs")
        require(sha(ROOT / "learning/runs/v2/milestone2-campaign-freeze-r4/frozen-identity.json") == foundation["identity_sha256"], "Foundation identity differs")
        first_identity = read(TARGET / "cli-probe-identity.json")
        changed_intermediate = [name for name, expected in final_identity["sources"].items()
                                if first_identity["sources"].get(name) != expected]
        report["checks"].append({"check": "CLI_preparation_raw_semantic_hashes_final_inventory_and_native_lineage", "passed": True,
                                 "raw_config_sha256": raw_hash, "semantic_config_sha256": semantic_hash,
                                 "final_identity_sha256": sha(TARGET / "cli-final-preparation-identity.json"),
                                 "final_source_pins": len(final_identity["sources"]),
                                 "native_input_pins": len(foundation["native_inputs"]),
                                 "native_binary_receipt_pins": len(foundation["binary_and_receipt_sha256"]),
                                 "registered_u64_run_seed_exact": config["phase_settings"]["run_seed"],
                                 "earlier_preparation_identity_changed_sources": changed_intermediate,
                                 "earlier_identity_is_obsolete_preparation_only": True})

        error = read(TARGET / "freeze-attempt1-failure.json")
        require(error["source_or_test_rerun"] is False and len(error["invalid_synthetic_fixture_paths"]) == 40, "Evidence-only error declaration differs")
        for name in error["invalid_synthetic_fixture_paths"]:
            try:
                json.loads((TARGET / name).read_text())
            except json.JSONDecodeError:
                continue
            raise AssertionError(f"Expected invalid inventory fixture became JSON: {name}")
        root_json = [p for p in TARGET.iterdir() if p.is_file() and p.suffix == ".json"]
        for path in root_json:
            read(path)
        report["checks"].append({"check": "intentional_nonJSON_fixture_and_receipt_validation_scope", "passed": True,
                                 "declared_intentional_nonJSON_fixtures": 40,
                                 "root_receipt_JSON_files_parsed": len(root_json),
                                 "original_scope_error_preserved": True})
        changed = [name for name, expected in before.items() if sha(Path(name)) != expected]
        require(not changed, "Audited input bytes changed")
        report["checks"].append({"check": "input_preservation", "passed": True, "files": len(before), "changed": changed})
        report["status"] = "passed_trainer_component_receipt_audit;parent_integration_and_code_review_required"
    except BaseException as error:
        report["failures"].append({"error": repr(error), "traceback": traceback.format_exc()})
        report["status"] = "failed_audit_attempt"
    with (HERE / "audit.json").open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]),
                      "failures": report["failures"], "audit_sha256": sha(HERE / "audit.json")}))
    return bool(report["failures"])


if __name__ == "__main__":
    sys.exit(main())
