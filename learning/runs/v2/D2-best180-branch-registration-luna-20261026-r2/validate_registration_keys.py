"""Strict key and full dependency-closure validation for this registration."""
import hashlib
import json
from pathlib import Path

base = Path(__file__).resolve().parent
reg = json.loads((base / "registration-proposed.json").read_text())
allowed = {
    "cancel_path", "capsule_support", "config_path", "config_sha256", "expected_lease",
    "import_policy", "interpreter", "launcher_path", "limits", "native",
    "normal_training_iteration", "output", "parent", "pins", "policy_sha256", "root",
    "run_id", "run_seed", "runner_path", "runtime_continuity", "runtime_root",
    "runtime_sha256", "runtime_versions", "schema", "state_path", "timing_policy",
    "training_eligible",
}
assert set(reg) == allowed, (sorted(set(reg) - allowed), sorted(allowed - set(reg)))
root = Path(reg["root"])
inventory_path = root / "learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/dependency-inventory.json"
inventory = json.loads(inventory_path.read_text())["pins"]
assert all(Path(k).is_absolute() for k in reg["pins"])
missing = {k: v["sha256"] for k, v in inventory.items() if reg["pins"].get(k) != v["sha256"]}
assert not missing, ("baseline dependency inventory missing or changed", len(missing), list(missing.items())[:3])
for name, digest in reg["pins"].items():
    path = Path(name)
    assert path.is_file(), name
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == digest, (name, digest, actual)
assert reg["pins"].get(str(base / "input-manifest.json")) == hashlib.sha256((base / "input-manifest.json").read_bytes()).hexdigest()
print(json.dumps({"status": "passed", "strict_registration_keys": len(allowed), "pin_count": len(reg["pins"]), "baseline_inventory_keys": len(inventory), "all_inventory_keys_exact": True, "all_pin_hashes_valid": True}, sort_keys=True))
