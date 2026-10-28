"""Parent terminal audit; durable accepted evidence precedes exact lease release."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import binding as b
import terminal


def require_group_absent(pgid,role):
    b.need(type(pgid)is int and pgid>1 and pgid!=os.getpgrp(),"unsafe "+role+" process group")
    result=subprocess.run(['/bin/ps','-axo','pid=,ppid=,pgid=,command='],
        capture_output=True,text=True,check=True)
    members=[]
    for line in result.stdout.splitlines():
        fields=line.split(None,3)
        if len(fields)>=3 and int(fields[2])==pgid:members.append(line.strip())
    b.need(not members,role+" process group remains in process table")
    try:os.killpg(pgid,0)
    except ProcessLookupError:return dict(role=role,pgid=pgid,absent=True)
    raise ValueError(role+" process group absence not proven")


def output_manifest(control,out):
    path=Path(control)/"artifact-manifest.json"
    b.need(path.is_file() and not path.is_symlink(),"observer output manifest missing")
    manifest=b.read(path)
    b.need(type(manifest)is dict and manifest,"empty observer output manifest")
    actual={str(p.relative_to(out)) for p in out.iterdir() if p.is_file() and not p.is_symlink()}
    b.need(actual==set(manifest),"worker output member set differs from observer manifest")
    pins={}
    for relative,digest in manifest.items():
        member=Path(relative)
        b.need(not member.is_absolute() and ".." not in member.parts,"unsafe worker output manifest path")
        target=out/member
        b.need(target.is_file() and not target.is_symlink(),"worker output member missing or symlinked")
        pins[str(target)]=digest
    b.check_pins(pins)
    return dict(path=str(path),sha256=b.sha(path),files=len(manifest))


def verify_cache(reg):
    policy=reg["import_policy"]
    b.need(policy.get("dont_write_bytecode") is True,"bytecode write policy differs")
    path=Path(policy["pycache_prefix"])
    b.need(path.is_absolute() and path.is_dir() and not path.is_symlink()
        and not any(path.iterdir()),"registered worker bytecode cache is not empty")
    return dict(path=str(path),empty=True)


def validate_observer_receipts(envelope_sha256,registration_sha256,parent_execution,
                               exit_record,observer,execution_result):
    b.need(parent_execution.get("registration_sha256")==exit_record.get("registration_sha256")
        ==registration_sha256 and parent_execution.get("envelope_sha256")==envelope_sha256,
        "parent observer execution identity differs")
    b.need(exit_record.get("raw_observer_exit_code")==0
        and exit_record.get("observer_directly_reaped") is True,
        "parent raw observer exit/reap differs")
    fields=("status","observed_worker_raw_exit","directly_reaped","first_event",
        "owned_group_absent","worker_group_absent","postflight_inputs_unchanged",
        "registration_sha256","envelope_sha256","owned_pgid")
    b.need(all(execution_result.get(key)==observer.get(key) for key in fields),
        "observer execution/observation receipts differ")
    b.need(observer.get("status")=="completed_pending_parent_audit"
        and observer.get("observed_worker_raw_exit")==0
        and observer.get("directly_reaped") is True
        and observer.get("first_event") is None
        and observer.get("owned_group_absent") is True
        and observer.get("worker_group_absent") is True
        and observer.get("postflight_inputs_unchanged") is True
        and observer.get("registration_sha256")==registration_sha256
        and observer.get("envelope_sha256")==envelope_sha256
        and type(observer.get("owned_pgid")) is int,
        "observer actual child/postflight receipt differs")
    return True


def replace_state(path,state):
    path=Path(path)
    fd,tmp=tempfile.mkstemp(prefix=".seed-priority-state-pending-",dir=path.parent)
    try:
        with os.fdopen(fd,"w") as stream:
            json.dump(state,stream,sort_keys=True,indent=2,allow_nan=False)
            stream.write("\n");stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def audit(envelope_path,envelope_sha256,parent_execution_path,execution_exit_path,
          audit_path,lease_release_path=None):
    e,reg=b.load_envelope(envelope_path,envelope_sha256)
    audit_path=Path(audit_path);release_path=Path(lease_release_path or audit_path.with_name("lease-release.json"))
    b.need(not os.path.lexists(audit_path) and not os.path.lexists(release_path),
        "parent audit/release receipt already exists; inspect and do not duplicate")
    b.check_lease(reg)
    b.verify_bound(e,reg,preflight=False)
    parent_execution=b.read(parent_execution_path);exit_record=b.read(execution_exit_path)
    control=Path(e["control"]);out=Path(reg["output"])
    observer=b.read(control/"observation.json")
    execution_result=b.read(control/"execution-result.json")
    validate_observer_receipts(envelope_sha256,e["registration_sha256"],parent_execution,
        exit_record,observer,execution_result)
    groups=[require_group_absent(parent_execution.get("observer_pgid"),"observer"),
            require_group_absent(observer.get("owned_pgid"),"worker")]

    cache=verify_cache(reg)
    manifest=output_manifest(control,out)
    worker=b.read(out/"worker-result.json")
    result=terminal.validate_outputs(reg,worker,e["registration_sha256"])
    accounting=terminal.accounting(out,worker,strict=True)
    result["accounting"]={k:v for k,v in accounting.items() if k!="completed_episode_rows"}
    b.verify_bound(e,reg,preflight=False)
    b.check_lease(reg)

    audit_doc=dict(schema="dodge_seed_priority_parent_terminal_audit_v1",
        status="accepted_complete_global_update60_training_receipt",
        registration_sha256=e["registration_sha256"],envelope_sha256=envelope_sha256,
        source_manifest_sha256=reg["source_manifest_sha256"],runtime_manifest_sha256=reg["runtime_manifest_sha256"],
        parent_raw_observer_exit_code=exit_record["raw_observer_exit_code"],
        parent_observer_directly_reaped=exit_record["observer_directly_reaped"],
        observer_observed_worker_raw_exit=observer["observed_worker_raw_exit"],
        observer_directly_reaped=observer["directly_reaped"],process_groups=groups,
        postflight_inputs_unchanged=observer["postflight_inputs_unchanged"],
        output_manifest=manifest,bytecode_cache=cache,terminal=result,
        automatic_selection=False,promoted=False,training_eligible=False)
    b.save(audit_path,audit_doc)

    state=b.read(reg["state_path"])
    b.need(state.get("active_long_campaign")==reg["expected_lease"],
        "refusing to clear a different parent lease")
    state["active_long_campaign"]=None
    state.setdefault("fullgame_seed_priority_work",{}).update(
        parent_terminal_audit=str(audit_path.resolve()),parent_terminal_audit_sha256=b.sha(audit_path),
        completed=True,training_eligible=False,promoted=False)
    replace_state(reg["state_path"],state)
    b.save(release_path,dict(status="exact_lease_cleared_after_durable_parent_audit",
        audit_path=str(audit_path.resolve()),audit_sha256=b.sha(audit_path),
        released_lease=reg["expected_lease"]))
    return audit_doc


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--envelope",required=True);p.add_argument("--envelope-sha256",required=True)
    p.add_argument("--parent-execution",required=True);p.add_argument("--execution-exit",required=True)
    p.add_argument("--output",required=True);p.add_argument("--lease-release")
    a=p.parse_args()
    result=audit(a.envelope,a.envelope_sha256,a.parent_execution,a.execution_exit,a.output,a.lease_release)
    print(json.dumps(result,sort_keys=True,indent=2));return 0


if __name__=="__main__":raise SystemExit(main())
