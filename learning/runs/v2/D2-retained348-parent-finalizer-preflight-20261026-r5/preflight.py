"""Parent read-only validation of every receipt input flagged by the r4 source review."""
import ast
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
BASE = OWN.parent
SOURCE = BASE / "D2-retained348-linear-finalizer-prepare-parent-20261026-r5/finalize_parent.py"
SPEC = importlib.util.spec_from_file_location("parent_read_only_finalizer", SOURCE)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
module.need(module.sha(SOURCE) == "d82ee2bbc62ac98e185c795774b046d4cfc470d0d9bce777bb102652eb0aef04", "Finalizer changed")
reg = module.read(module.REG_PATH)
full = module.read(module.FULL_PATH)
obs = module.read(module.OBS_PATH)
execution = module.read(module.RUN / "execution-result.json")
worker = module.read(module.RUN / "worker-result.json")
module._verify_registered_evidence(reg, full, obs, execution, worker)
statepath = Path(reg["state_path"])
state_before = statepath.read_bytes()
module.validate_parent_guard(json.loads(state_before), reg["expected_lease"], Path(reg["cancel_path"]).exists())
selected, runner, fingerprints, lr, group_lrs, schedule_fields = module._load_selected_state(
    module.RUN / "checkpoint-000348-candidate.pt", full["audit"]["candidates"]["348"])
from dodge_rl.identity import identity_hash
module.need(identity_hash(selected["identity"]) == selected["identity_sha256"], "Selected identity hash differs")
module.need(selected["run_seed"] == reg["run_seed"], "Selected master seed differs")

# Check all literal fields of selected state accessed anywhere in the pinned finalizer.
tree = ast.parse(SOURCE.read_text())
keys = {node.slice.value for node in ast.walk(tree)
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
        and node.value.id == "selected" and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)}
for key in sorted(keys):
    module.need(key in selected, "Selected field missing before publication: " + key)

certificate_hashes = {}
for update in (324, 336, 348, 360, 372, 384):
    path = module.RUN / f"development-{update:06d}.json"
    expected = full["audit"]["candidates"][str(update)]
    module.need(module.sha(path) == expected["certificate_sha256"], "Certificate bytes differ")
    certificate = module.read(path)
    performance = module.selected_performance(certificate, expected["checkpoint_sha256"])
    module.need(performance["mean_alive_frames"] == expected["mean_alive_frames"]
                and performance["deaths"] == expected["deaths"] and performance["caps"] == expected["caps"],
                "Certificate row aggregate differs from full audit")
    certificate_hashes[str(path)] = module.sha(path)
old = module.read(module.OLD_RECEIPT)
module.need(module.sha(module.OLD_RECEIPT) == module.OLD_RECEIPT_SHA, "Incumbent receipt differs")
module.need(module.sha(Path(old["evaluation_path"])) == old["evaluation_sha256"], "Incumbent certificate differs")
for key in ("q1_bottom16_mean", "q4_top16_mean", "mean_alive_frames", "death_causes"):
    module.need(key in old["performance"], "Incumbent report field missing")
module.need(statepath.read_bytes() == state_before, "Ledger changed during read-only preflight")
module.need(not any((OWN / "empty-pycache").iterdir()), "Preflight cache is not empty")
receipt = {"schema": "selected348_parent_read_only_receipt_input_preflight_v1", "status": "passed",
           "finalizer_source_sha256": module.sha(SOURCE), "actual_selected_checkpoint_CPU_loaded": True,
           "selected_fields_checked": sorted(keys), "selected_identity_hash_verified": True,
           "selected_run_seed": selected["run_seed"], "selected_fingerprints": fingerprints,
           "schedule_metadata": schedule_fields, "effective_learning_rate": lr, "optimizer_group_lrs": group_lrs,
           "all_six_certificate_row_fields_and_aggregates_verified": certificate_hashes,
           "all_registered_pins_and_terminal_evidence_verified": True,
           "production_receipt_or_lease_mutation": False,
           "review_resolution": "Reported missing-key/parse trigger is absent on exact frozen bytes. Parent prevalidated every selected-state field and all six complete certificate row aggregates before any production receipt write. Earlier synthetic publication control exercises remaining construction and commit path."}
with (OWN / "receipt.json").open("x") as stream:
    json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
    stream.write("\n")
print(json.dumps({"status": "passed", "selected_fields": len(keys), "certificates": 6,
                  "effective_learning_rate": lr, "no_production_mutation": True}))
