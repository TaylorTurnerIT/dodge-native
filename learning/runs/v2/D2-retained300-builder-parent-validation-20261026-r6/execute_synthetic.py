#!/usr/bin/env python3
"""Execute registration builder against synthetic source files and immutable receipts."""
import importlib.util
import json
import re
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location("builder", HERE / "prepare_registration.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
contract = builder.CONTRACT
c = builder.read_json(contract)
evidence = builder.EVIDENCE_MAP
base = builder.BASE_DEFAULT
parent_dir = ROOT / "learning/runs/v2/D2-retained276-lr3em5-parent-terminal-audit-20261026-r2"
auditor_dir = ROOT / "learning/runs/v2/D2-retained276-lr3em5-auditor-luna-20261026-r2"
kwargs = dict(
    evidence_map_path=evidence,
    selected_receipt_path=parent_dir / "retained-best-candidate-receipt.json",
    completed_cost_receipt_path=parent_dir / "completed-iteration-receipt.json",
    audit_path=parent_dir / "audit.json",
    selection_path=parent_dir / "retained-best-decision.json",
    full_audit_path=auditor_dir / "full-audit.json",
    producing_registration_path=base,
)
fixture = HERE / "synthetic-fixture"
if fixture.exists():
    shutil.rmtree(fixture)
fixture.mkdir()
final = fixture / "final-source"
final.mkdir()
for name in builder.REQUIRED_SOURCES:
    (final / name).write_text(f"# synthetic assembled fixture: {name}\n")
output = fixture / "out" / "registration.json"
result = builder.build_registration(contract, base, final, output, **kwargs)
reg = json.loads(output.read_text())
assert result["sha256"] == builder.sha(output)
assert reg["parent"]["phase_update"] == 300 and reg["parent"]["local_update"] == 24
assert reg["parent"]["total_update"] == 348
assert reg["expected_total_updates"] == 408 and reg["new_updates"] == 60
assert reg["expected_lease"] == {"authorization":"user_continue_D2_training_v3","kind":"D2_gradient_alignment","parent_checkpoint_sha256":"e2c8fbe44e23da910686954e90cb7841b38b6d7f60f69ca657a4a69b14214710","run_id":"D2-retained300-continuation-20261026-r1"}
assert reg["parent"]["path"] == json.loads(kwargs["selected_receipt_path"].read_text())["checkpoint_path"]
assert reg["resource_cost_anchor"]["path"] == json.loads(kwargs["selected_receipt_path"].read_text())["completed_iteration_receipt_path"]
assert reg["parent"]["registration_sha256"] == "8e17e1188253f091b62a8b60397663a530c4a865166f9568978dd009148308e7"
assert reg["parent"]["wall_accounting"] == json.loads(kwargs["selected_receipt_path"].read_text())["wall_accounting"]
assert reg["limits"]["retries"] == 0
assert reg["import_policy"]["pycache_prefix"] == str(final / "empty-pycache")
assert "lr-transition.json" not in reg["expected_outputs"]
assert len(reg["expected_outputs"]) == len(set(reg["expected_outputs"]))
assert "arm_transition" not in reg
assert re.fullmatch(r"[0-9a-f]{64}", reg["parent"]["sha256"])
assert all(re.fullmatch(r"[0-9a-f]{64}", v) for v in reg["pins"].values())
assert reg["resource_estimate"]["observed_control_optimizer_steps"] == 7680
assert not (fixture / "actual-run").exists()

# Missing source and mutated immutable input must fail before output mutation.
missing_final = fixture / "missing-final"
missing_final.mkdir()
for name in builder.REQUIRED_SOURCES[:-1]:
    (missing_final / name).write_text("synthetic\n")
missing_out = fixture / "missing-out" / "registration.json"
try:
    builder.build_registration(contract, base, missing_final, missing_out, **kwargs)
except ValueError as exc:
    assert "required input missing" in str(exc)
else:
    raise AssertionError("missing source accepted")
assert not missing_out.parent.exists()

with tempfile.TemporaryDirectory(dir=fixture) as td:
    temp = Path(td)
    bad_map = temp / "evidence-map.json"
    bad = json.loads(evidence.read_text())
    bad["verified_input_sha256"]["learning/runs/v2/D2-retained276-lr3em5-parent-terminal-audit-20261026-r2/audit.json"] = "0" * 64
    bad_map.write_text(json.dumps(bad))
    drift_out = temp / "drift" / "registration.json"
    drift_kwargs = dict(kwargs, evidence_map_path=bad_map)
    try:
        builder.build_registration(contract, base, final, drift_out, **drift_kwargs)
    except ValueError as exc:
        assert "input hash differs" in str(exc)
    else:
        raise AssertionError("input drift accepted")
    assert not drift_out.parent.exists()

try:
    builder.build_registration(contract, base, final, output, **kwargs)
except FileExistsError:
    pass
else:
    raise AssertionError("existing output accepted")
assert output.is_file()
print(json.dumps({"status":"passed","output":str(output),"sha256":builder.sha(output),"negative_cases":["missing source","input drift","existing output"],"run_directory_created":False},indent=2))
