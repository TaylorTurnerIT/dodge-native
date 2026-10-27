"""Pre-test authority path and pin digest audit; performs no runtime checks."""
import hashlib,json
from pathlib import Path
reg_path=Path(__file__).with_name("registration-proposed.json")
r=json.loads(reg_path.read_text())
required=["root","output","runtime_root","interpreter","runner_path","launcher_path","state_path","config_path","cancel_path","import_policy.pycache_prefix","parent.path","parent.terminal_receipt_path","native.path","native.old_path","runtime_transition.source_runtime_root"]
def get(path):
    value=r
    for part in path.split("."): value=value[part]
    return value
for key in required:
    value=get(key)
    assert isinstance(value,str) and Path(value).is_absolute(), (key,value)
assert all(Path(key).is_absolute() for key in r["pins"])
critical=[r["runner_path"],r["launcher_path"],r["interpreter"],r["config_path"],r["parent"]["path"],r["parent"]["terminal_receipt_path"],r["native"]["path"],r["native"]["old_path"]]
assert set(critical)<=r["pins"].keys()
for name,digest in r["pins"].items():
    path=Path(name); assert path.is_file(), name
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest, name
assert Path(r["import_policy"]["pycache_prefix"]).is_dir() and not any(Path(r["import_policy"]["pycache_prefix"]).iterdir())
print(json.dumps({"status":"passed","pin_count":len(r["pins"]),"all_pin_keys_absolute":True,"all_pin_hashes_valid":True,"runtime_sha256":r["runtime_sha256"]},sort_keys=True))
