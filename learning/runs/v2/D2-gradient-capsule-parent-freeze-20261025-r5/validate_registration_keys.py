"""Pre-command exact inventory, path, and digest audit; no runtime execution."""
import hashlib,json
from pathlib import Path
base=Path(__file__).resolve().parent
r=json.loads((base/"registration-proposed.json").read_text())
invp=Path(r["root"])/"learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/dependency-inventory.json"
inventory=json.loads(invp.read_text())["pins"]
assert all(Path(k).is_absolute() for k in r["pins"])
missing={k:v["sha256"] for k,v in inventory.items() if r["pins"].get(k)!=v["sha256"]}
assert not missing, ("original inventory lexical keys/digests missing",len(missing),list(missing.items())[:3])
for name,digest in r["pins"].items():
 p=Path(name); assert p.is_file(),name
 assert hashlib.sha256(p.read_bytes()).hexdigest()==digest,name
assert Path(r["import_policy"]["pycache_prefix"]).is_dir() and not any(Path(r["import_policy"]["pycache_prefix"]).iterdir())
print(json.dumps({"status":"passed","pin_count":len(r["pins"]),"inventory_key_count":len(inventory),"all_inventory_keys_exact":True,"all_pin_hashes_valid":True,"runtime_sha256":r["runtime_sha256"]},sort_keys=True))
