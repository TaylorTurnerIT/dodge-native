"""One-shot RNG state reference worker contract. Import is inert."""
import hashlib
import json
import os
import threading
import time
from pathlib import Path

SCHEMA = "d2_layerb_rng_real_state_preflight_v1"
RECEIPT_FIELDS = frozenset({"schema", "status", "backend", "torch_version",
    "accepted_checkpoint_sha256", "parent_receipt_sha256", "study_id", "replica",
    "complete_seed_vector", "vector_sha256", "cpu_rng_state_sha256", "mps_rng_state_sha256"})
SEED_FIELDS = frozenset({"constructor_init_seed", "python_random_seed", "numpy_global_seed",
    "torch_cpu_global_seed", "action_sampler_torch_mps_seed", "env_master_seed"})
PARENT = "c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc"
PARENT_RECEIPT = "76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08"
FINGERPRINT_SOURCE_SHA256 = "6ef9cf3f08fe800f54230801a921a2f5c82e47e5013ef3087ead6499d2533d61"

def canonical_vector_sha256(study, replica, seeds):
    raw=json.dumps({"study_id":study,"replica":replica,"seeds":seeds},sort_keys=True,
                   separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()

def strict_int(value): return type(value) is int

def validate_vectors(obj, study="paired-lr-confirmed324-20261026-r1"):
    if not isinstance(obj,dict) or obj.get("schema")!="d2_layerb_proposed_rng_seed_vectors_v3" or obj.get("study_id")!=study:
        raise ValueError("vector study/schema mismatch")
    if obj.get("status")!="proposed_only_not_reserved_not_applied": raise ValueError("vectors not pending")
    rows=obj.get("vectors")
    if not isinstance(rows,list) or len(rows)!=3: raise ValueError("exactly three vectors required")
    seen=set(); out=[]
    for i,row in enumerate(rows,1):
        if not isinstance(row,dict) or type(row.get("replica")) is not int or row.get("replica")!=i or set(row.get("seeds",{}))!=SEED_FIELDS:
            raise ValueError("replica/vector fields mismatch")
        seeds=row["seeds"]
        bounds={"constructor_init_seed":(1,4294967295),"python_random_seed":(1,9223372036854775807),
          "numpy_global_seed":(0,4294967295),"torch_cpu_global_seed":(1,9223372036854775807),
          "action_sampler_torch_mps_seed":(1,9223372036854775807),"env_master_seed":(1,18446744073709551615)}
        if any(not strict_int(v) or not bounds[k][0]<=v<=bounds[k][1] for k,v in seeds.items()): raise ValueError("seed values outside strict stream bounds")
        digest=canonical_vector_sha256(study,i,seeds)
        if row.get("vector_sha256")!=digest or digest in seen: raise ValueError("vector hash mismatch or duplicate")
        seen.add(digest); out.append({"replica":i,"complete_seed_vector":seeds,"vector_sha256":digest})
    return out

def capture_references(*, vectors, study_id, torch_api, numpy_version, python_version,
                       torch_version, backend_available, fingerprint, checkpoint_sha256=PARENT,
                       parent_receipt_sha256=PARENT_RECEIPT, heartbeat=None):
    """Capture actual state using injected APIs; production caller supplies pinned modules."""
    if checkpoint_sha256!=PARENT or parent_receipt_sha256!=PARENT_RECEIPT:
        raise ValueError("parent pins mismatch")
    if not backend_available: raise RuntimeError("MPS unavailable")
    rows=validate_vectors(vectors,study_id)
    if numpy_version!="2.5.4" or torch_version!="2.14.1": raise RuntimeError("pinned library version mismatch")
    captured=[]
    for row in rows:
        s=row["complete_seed_vector"]
        # Reference contract: CPU seed first, explicit MPS seed last, then read states.
        torch_api.manual_seed(s["torch_cpu_global_seed"])
        torch_api.mps.manual_seed(s["action_sampler_torch_mps_seed"])
        cpu=fingerprint(torch_api.get_rng_state())
        mps=fingerprint(torch_api.mps.get_rng_state())
        vals={"schema":SCHEMA,"status":"measured","backend":"mps","torch_version":torch_version,
              "accepted_checkpoint_sha256":checkpoint_sha256,"parent_receipt_sha256":parent_receipt_sha256,
              "study_id":study_id,"replica":row["replica"],"complete_seed_vector":s,
              "vector_sha256":row["vector_sha256"],"cpu_rng_state_sha256":cpu,"mps_rng_state_sha256":mps}
        if set(vals)!=RECEIPT_FIELDS: raise RuntimeError("reference receipt schema drift")
        captured.append(vals)
        if heartbeat: heartbeat()
    return {"schema":"d2_layerb_rng_reference_probe_receipt_v1","status":"captured_pending_parent_postflight",
            "study_id":study_id,"references":captured,"runtime":{"python":python_version,
            "numpy":numpy_version,"torch":torch_version,"backend":"mps"},
            "scope":{"checkpoint_bytes_hashed_only":True,"model_constructed":False,"environment_constructed":False,
            "checkpoint_deserialized":False,"training":False,"evaluation":False,"launch_authority":False}}

def atomic_publish(directory, receipt):
    """Publish exclusive files, then exclusive commit manifest; parent requires manifest."""
    dest=Path(directory)
    rows=receipt.get("references",[])
    if len(rows)!=3 or [r.get("replica") for r in rows]!=[1,2,3]: raise ValueError("partial references cannot publish")
    if dest.exists() and not dest.is_dir(): raise FileExistsError("reference output collision")
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.mkdir(exist_ok=True)
    def exclusive(path,obj):
        raw=(json.dumps(obj,sort_keys=True,indent=2)+"\n").encode()
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,"wb") as f: f.write(raw); f.flush(); os.fsync(f.fileno())
        return hashlib.sha256(raw).hexdigest()
    files=[]
    for row in rows:
        if set(row)!=RECEIPT_FIELDS or row.get("schema")!=SCHEMA or row.get("status")!="measured": raise ValueError("reference fields/status invalid")
        p=dest/f"replica-{row['replica']}.json"; files.append({"path":p.name,"sha256":exclusive(p,row)})
    rpath=dest/"receipt.json"; files.append({"path":rpath.name,"sha256":exclusive(rpath,receipt)})
    # This exclusive commit record is the sole completeness signal.
    exclusive(dest/"COMMITTED.json",{"schema":"d2_layerb_rng_reference_probe_commit_v1","files":files,"references":3})

def heartbeat_loop(path, identity, stop, memory_sample):
    seq=0
    while not stop.is_set():
        rss,mps=memory_sample()
        if type(rss)is not int or rss<0 or type(mps)is not int or not 0<=mps<=identity["mps_cap_bytes"]:
            raise RuntimeError("invalid memory sample")
        rec={"run_id":identity["run_id"],"registration_sha256":identity["registration_sha256"],
             "pid":os.getpid(),"timestamp_ns":time.time_ns(),"sequence":seq,"rss_bytes":rss,"mps_driver_bytes":mps}
        tmp=Path(path).with_suffix(".tmp")
        tmp.write_text(json.dumps(rec,sort_keys=True));os.replace(tmp,path);seq+=1
        stop.wait(.2)
