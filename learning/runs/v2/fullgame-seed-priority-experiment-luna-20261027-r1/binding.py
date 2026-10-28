"""Parent-gated dynamic binding for copied direct-owner watchdog; stdlib only."""
from __future__ import annotations
import hashlib, importlib, json, os, tempfile
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
STUDY="fullgame-seed-priority-luna-20261027-r1"
LIMITS={}
GATES=("source_review","accepted_parent_lineage","explicit_seeded_training_validation",
       "rng_reference","pool_history_scope","D4_D5_reservation","resource_calibration",
       "terminal_evaluator","one_shot_registration")
class Cancelled(RuntimeError): pass

def need(ok,message):
    if not ok: raise ValueError(message)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()
def read(path):
    def unique(items):
        d={}
        for k,v in items:
            need(k not in d,"duplicate JSON field: "+k);d[k]=v
        return d
    return json.loads(Path(path).read_bytes(),object_pairs_hook=unique,
        parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def save(path,value):
    path=Path(path); fd,tmp=tempfile.mkstemp(prefix="."+path.name+".pending-",dir=path.parent)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write("\n");f.flush();os.fsync(f.fileno())
        os.link(tmp,path); dfd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(dfd)
        finally:os.close(dfd)
    finally:os.unlink(tmp)
def check_pins(pins):
    need(type(pins)is dict and pins,"external parent pins required")
    for path,digest in pins.items():need(sha(path)==digest,"pin drift: "+path)
def check_lease(reg):
    state=read(reg["state_path"])
    need(state.get("active_long_campaign")==reg["expected_lease"],"parent lease changed")
def _contracts():
    if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
    module=importlib.import_module("contracts")
    need(Path(module.__file__).resolve()==HERE/"contracts.py","contracts origin mismatch")
    return module
def load_envelope(path,digest):
    need(sha(path)==digest,"external envelope digest differs")
    env=read(path)
    fields={"schema","status","registration","registration_sha256","launch_approval","launch_approval_sha256",
        "source_acceptance","source_acceptance_sha256","control","cancel_path","started","pins",
        "interpreter_resolved","interpreter_sha256"}
    need(set(env)==fields and env["schema"]=="dodge_seed_priority_worker_envelope_v1"
         and env["status"]=="parent_bound_exactly_one_run","parent envelope schema/status differs")
    reg=read(env["registration"])
    LIMITS.clear();LIMITS.update(reg["limits"])
    env["self_path"]=str(Path(path).resolve());env["self_sha256"]=digest
    return env,reg
def verify_bound(env,reg,*,preflight):
    check_pins(env["pins"])
    check_pins({env["registration"]:env["registration_sha256"],
                env["launch_approval"]:env["launch_approval_sha256"],
                env["source_acceptance"]:env["source_acceptance_sha256"]})
    c=_contracts();c.validate_static(reg,startup=preflight)
    need(env["registration_sha256"]==sha(env["registration"]),"registration identity differs")
    approval=read(env["launch_approval"])
    need(approval==dict(schema="dodge_seed_priority_parent_launch_approval_v1",
        status="approved_exactly_one_registered_run",registration_sha256=env["registration_sha256"],
        source_manifest_sha256=reg["source_manifest_sha256"],runtime_manifest_sha256=reg["runtime_manifest_sha256"],
        run_id=reg["run_id"],gates=dict.fromkeys(GATES,"passed")),"external parent approval gates missing")
    source=read(env["source_acceptance"])
    need(source==dict(schema="dodge_seed_priority_independent_source_acceptance_v1",
        status="accepted_exact_source",study_id=STUDY,source_manifest_sha256=reg["source_manifest_sha256"]),
        "independent source acceptance differs")
    marker=read(reg["launch_marker_path"])
    need(marker==dict(schema="dodge_seed_priority_parent_spent_launch_marker_v1",
        registration_sha256=env["registration_sha256"],run_id=reg["run_id"],started=env["started"]),
        "parent spent marker differs")
    check_lease(reg);need(not os.path.lexists(env["cancel_path"]),"parent cancellation present")
    need(str(Path(reg["interpreter"]).resolve())==env["interpreter_resolved"]
         and sha(env["interpreter_resolved"])==env["interpreter_sha256"],"registered interpreter bytes differ")
    if preflight:need(not os.path.lexists(reg["output"]) and not os.path.lexists(reg["attempt_claim_path"]),
                      "fixed output/attempt claim already spent")
def worker_command(env,reg):
    return [reg["interpreter"],"-B",str(HERE/"worker_cli.py"),"--registration",env["registration"],
        "--registration-sha256",env["registration_sha256"],"--source-acceptance",env["source_acceptance"],
        "--source-acceptance-sha256",env["source_acceptance_sha256"],"--started",str(env["started"])]
def worker_resources(out,*,strict=False):
    result={"samples":0,"peak_rss_bytes":None,"peak_mps_driver_bytes":None}
    path=Path(out)/"resources.jsonl"
    if not path.is_file():return result
    with path.open() as f:
        for line in f:
            if not line.endswith("\n"):
                need(not strict,"torn worker resource journal");break
            row=json.loads(line)
            need(all(type(row.get(k))is int and row[k]>=0 for k in ("rss_bytes","mps_driver_bytes")),
                 "invalid worker resource sample")
            result["samples"]+=1
            result["peak_rss_bytes"]=max(result["peak_rss_bytes"] or 0,row["rss_bytes"])
            result["peak_mps_driver_bytes"]=max(result["peak_mps_driver_bytes"] or 0,row["mps_driver_bytes"])
    return result
