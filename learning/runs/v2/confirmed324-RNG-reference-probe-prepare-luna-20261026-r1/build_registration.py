"""Build descriptive parent-owned registration template; cannot claim or launch."""
import hashlib, json
from pathlib import Path

RUN=Path(__file__).resolve().parent
SOURCE=RUN.parent/"confirmation-proof-binding-parent-repair-20261026-r4"/"execute_once.py"
PIN="4a5d084359ee48fe5351c96e0ec4455fdcd95a428a17bbcf59d0653f6922de98"

def build(*, vectors_path, output_path, state_path, marker_path, cancel_path, expected_lease,
          python_path, runtime_root, torch_version="2.14.1", numpy_version="2.5.4"):
    data=Path(vectors_path).read_bytes(); vectors=json.loads(data)
    if vectors.get("study_id")!="paired-lr-confirmed324-20261026-r1" or len(vectors.get("vectors",[]))!=3:
        raise ValueError("exact three parent vectors required")
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=PIN: raise ValueError("pinned supervisor source changed")
    reg={"schema":"d2_layerb_rng_reference_probe_registration_v1","status":"draft_parent_review_required",
      "authority":"none_until_parent_registration_review_and_lease_installation",
      "run_id":"paired-lr-confirmed324-rng-reference-probe-once","study_id":vectors["study_id"],
      "source":{"worker_path":str(RUN/"probe.py"),"worker_sha256":hashlib.sha256((RUN/"probe.py").read_bytes()).hexdigest(),
        "supervisor_path":str(SOURCE),"supervisor_sha256":PIN},
      "runtime":{"python_path":str(Path(python_path).resolve()),"runtime_root":str(Path(runtime_root).resolve()),
        "torch_version":torch_version,"numpy_version":numpy_version,"pycache_policy":"PYTHONDONTWRITEBYTECODE=1 -B; ownedemptycache"},
      "inputs":{"vectors_path":str(Path(vectors_path).resolve()),"vectors_sha256":hashlib.sha256(data).hexdigest(),
        "checkpoint_sha256":"c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc",
        "parent_receipt_sha256":"76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08"},
      "limits":{"work_seconds":45,"outer_seconds":55,"cleanup_seconds":10,"startup_grace_seconds":12,
        "RSS_bytes":6*1024**3,"MPS_driver_bytes":6*1024**3,"guard_poll_seconds":0.2,"heartbeat_stale_seconds":2.0},
      "state_path":str(Path(state_path).resolve()),"expected_lease":expected_lease,
      "one_shot_marker":str(Path(marker_path).resolve()),"cancel_path":str(Path(cancel_path).resolve()),
      "output_dir":str(Path(output_path).resolve()),"references":{"required_replicas":[1,2,3],"receipt_fields":sorted([
        "schema","status","backend","torch_version","accepted_checkpoint_sha256","parent_receipt_sha256","study_id",
        "replica","complete_seed_vector","vector_sha256","cpu_rng_state_sha256","mps_rng_state_sha256"]),
        "same_reference_for_both_arms":True}}
    return reg

if __name__=="__main__":
    raise SystemExit("draft builder is a library only; parent must supply reviewed registration and exact-once launcher")
