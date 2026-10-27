"""Read/hash/AST/JSON review checks only. Never import or execute target code."""
from pathlib import Path
import ast
import copy
import hashlib
import json
import re

OWN = Path(__file__).resolve().parent
ROOT = OWN.parents[3]
BASE = OWN.parent
TARGET = BASE / "progressive1000-collector-prepare-sol-20261026-r1"
DESIGN = BASE / "progressive1000-curriculum-replica-parent-20261026-r3"
PARENT = BASE / "progressive1000-collector-r1-parent-validation-20261026-r1"
FROZEN = BASE / "D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime/dodge_rl"
inputs = {}


def read(path):
    data = path.read_bytes()
    key = str(path.relative_to(ROOT))
    digest = hashlib.sha256(data).hexdigest()
    if key in inputs:
        assert inputs[key] == digest, key
    inputs[key] = digest
    return data


def load(path):
    return json.loads(read(path))


checks = {}
seal = read(TARGET / "SHA256SUMS").decode().splitlines()
for row in seal:
    expected, name = row.split("  ", 1)
    assert hashlib.sha256(read(TARGET / name)).hexdigest() == expected, name
checks["target_seal_entries_verified"] = len(seal)
manifest = load(TARGET / "source-manifest.json")
assert inputs[str((TARGET / "source-manifest.json").relative_to(ROOT))] == "1839e0f89a08f1c79e0e2a26e26019b2ad951ac1f461a3a2de7a83ff7d214f24"
for row in manifest["owned_files"]:
    data = read(TARGET / row["path"])
    assert len(data) == row["bytes"]
    assert hashlib.sha256(data).hexdigest() == row["sha256"]
checks["manifest_payload_entries_verified"] = len(manifest["owned_files"])

# Reconstruct the entire published unified diff in memory, without patching files.
lines = read(TARGET / "accepted-to-successor.diff").decode().splitlines(True)
i = sections = 0
while i < len(lines):
    assert lines[i].startswith("--- ")
    old_name = lines[i][4:].rstrip("\n")
    new_name = lines[i + 1][4:].rstrip("\n")
    assert lines[i + 1].startswith("+++ ")
    old = [] if old_name == "/dev/null" else read(ROOT / old_name).decode().splitlines(True)
    i += 2
    cursor = 0
    output = []
    while i < len(lines) and not lines[i].startswith("--- "):
        match = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\n", lines[i])
        assert match, lines[i]
        start, count, new_start, new_count = match.groups()
        start, count = int(start), int(count or 1)
        new_start, new_count = int(new_start), int(new_count or 1)
        offset = start - 1 if count else start
        output.extend(old[cursor:offset])
        cursor = offset
        assert len(output) == (new_start - 1 if new_count else new_start)
        consumed = added = 0
        i += 1
        while i < len(lines) and not lines[i].startswith(("--- ", "@@ ")):
            tag, value = lines[i][0], lines[i][1:]
            assert tag in " +-", lines[i]
            if tag in " -":
                assert old[cursor] == value
                cursor += 1
                consumed += 1
            if tag in " +":
                output.append(value)
                added += 1
            i += 1
        assert consumed == count and added == new_count
    output.extend(old[cursor:])
    assert "".join(output).encode() == read(ROOT / new_name), new_name
    sections += 1
checks["exact_diff_sections_reconstructed_in_memory"] = sections

trees = {}
for path in sorted(TARGET.rglob("*.py")):
    trees[str(path.relative_to(TARGET))] = ast.parse(read(path), filename=str(path))
checks["target_python_files_ast_parsed"] = len(trees)
checks["test_methods_read_not_run"] = {
    name: sum(isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
              for node in ast.walk(tree))
    for name, tree in trees.items() if name.startswith("tests/test_")
}

accepted = ast.parse(read(FROZEN / "ppo.py"))
successor = copy.deepcopy(trees["successor/ppo.py"])
collector = next(node for node in successor.body
                 if isinstance(node, ast.FunctionDef) and node.name == "collect_rollout")
index = next(i for i, arg in enumerate(collector.args.kwonlyargs) if arg.arg == "boundary_adapter")
del collector.args.kwonlyargs[index]
del collector.args.kw_defaults[index]


class StripHooks(ast.NodeTransformer):
    def visit_If(self, node):
        if ast.unparse(node.test) == "boundary_adapter is not None":
            assert not node.orelse
            return None
        return self.generic_visit(node)


StripHooks().visit(collector)
assert ast.dump(accepted) == ast.dump(successor)
checks["entire_ppo_ast_identical_after_removing_only_collector_argument_and_hooks"] = True
for name in ("critic_diagnostics.py", "gradient_alignment.py"):
    assert read(TARGET / "successor" / name) == read(FROZEN / name)
checks["optional_diagnostics_byte_identical"] = True
assert read(TARGET / "successor/scheduler_reference.py") == read(DESIGN / "scheduler_reference.py")
assert hashlib.sha256(read(DESIGN / "scheduler_reference.py")).hexdigest() == "a467b7219a9cd801fa3b403a6af112fc693ec3d14c9d311e8845632ef61d844b"
assert hashlib.sha256(read(DESIGN / "experiment.json")).hexdigest() == "c20bd35188c4b4dd36687bc10c7998e6410c70d37300be92db9a42b3d01c43c0"
checks["design_and_scheduler_pins_match"] = True
contract = BASE / "progressive1000-design-parent-acceptance-20261026-r1/implementation-contract.json"
load(contract)
shared = load(TARGET / "shared-config-contract.json")
design = load(DESIGN / "experiment.json")
assert shared["shared_contract"]["ppo"] == design["architecture_and_ppo"]["ppo"]
checks["shared_ppo_json_matches_design"] = True

copies = 0
for path in sorted(TARGET.rglob("*.py")):
    assert read(path) == read(PARENT / path.relative_to(TARGET))
    copies += 1
parent_receipt = load(PARENT / "receipt.json")
parent_log = read(PARENT / "tests.log").decode()
assert parent_receipt["exit_code"] == 0 and "Ran 39 tests" in parent_log and "\nOK\n" in parent_log
checks["parent_python_copies_byte_identical"] = copies
checks["parent_reported_tests"] = 39
checks["review_tests_executed"] = 0
checks["target_code_executed_or_imported"] = False
checks["scope"] = "stdlib read/hash/AST/JSON only; source evidence, not runtime qualification"
for name, before in inputs.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == before, name
checks["listed_inputs_unchanged_at_end"] = True
checks["input_sha256"] = dict(sorted(inputs.items()))
(OWN / "source-checks.json").write_text(json.dumps(checks, indent=2, sort_keys=True) + "\n")
print(json.dumps({key: value for key, value in checks.items() if key != "input_sha256"}, indent=2))
