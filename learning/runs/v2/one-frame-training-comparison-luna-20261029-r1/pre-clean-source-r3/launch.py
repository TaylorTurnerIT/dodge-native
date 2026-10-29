"""Exactly-once parent dispatcher. Launch authority comes only from accepted parent gates."""
from __future__ import annotations
import argparse
import datetime
import os
from pathlib import Path
import subprocess
import time

import binding as b
import power_guard


def replace_state(path, state):
    staged=Path(path).with_name(b.PENDING_STATE)
    b.save(staged,state); os.replace(staged,path)
    directory=os.open(Path(path).parent,os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)


def state_free(reg):
    path=Path(reg['state_path'])
    b.need(not os.path.lexists(path.with_name(b.PENDING_STATE)), 'shared state pending path exists')
    state=b.read(path)
    for key in ('active_long_campaign','active_inference_diagnostic','active_inference_campaign','active_inference_lease'):
        b.need(state.get(key) is None, 'conflicting lease blocks DODGE-013: '+key)
    b.need(state.get('training_hold',{}).get('active') is not True, 'training hold is active')
    work=state.get('one_frame_training_comparison_work')
    b.need(type(work) is dict and all(work.get(k)==v for k,v in reg['expected_parent_work_identity'].items()),
           'parent work identity changed before lease')
    return state


def install_lease(reg):
    state=state_free(reg); state[reg['lease_key']]=reg['expected_lease']
    state['last_update_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    replace_state(reg['state_path'],state)


def require_empty_cache(reg):
    cache=Path(reg['import_policy']['pycache_prefix'])
    b.need(cache.is_dir() and not cache.is_symlink() and not any(cache.iterdir()),
           'registered bytecode cache must be empty before lease')
    return cache


def acceptances(reg_path, reg_sha, gate_path, gate_sha, source_path, source_sha):
    b.verify_pins({reg_path:reg_sha,gate_path:gate_sha,source_path:source_sha})
    reg=b.read(reg_path); b.validate_static(reg,require_registered=True,check_streams=True)
    source=b.read(source_path)
    b.need(source==b.source_acceptance_document(reg['source_manifest_sha256']),
           'independent source acceptance differs')
    gate=b.read(gate_path)
    b.need(gate==b.approval_document(reg_sha,reg['source_manifest_sha256'],gate.get('pins')),
           'parent exact gates are missing or stale')
    b.verify_pins(gate['pins'])
    return reg,gate


def main(registration, registration_sha256, gate_path, gate_sha256, source_path, source_sha256):
    reg,gate=acceptances(registration,registration_sha256,gate_path,gate_sha256,source_path,source_sha256)
    cache=require_empty_cache(reg)
    outputs=(reg['output'],reg['attempt_claim_path'],reg['launch_marker_path'],b.HERE/'launch-envelope.json',
        b.HERE/'parent-execution.json',b.HERE/'execution-exit.json',b.HERE/'observer.log',
        b.HERE/'worker-output',b.HERE/'local-terminal-audit.json',b.HERE/'parent-terminal-audit.json')
    for path in outputs: b.need(not os.path.lexists(path), 'exactly-once output already exists: '+str(path))
    control=b.HERE/'dispatch'/reg['run_id']; b.need(not os.path.lexists(control),'exactly-once dispatch already exists')
    power=power_guard.check(override=None); b.need(power['on_ac'] is True,'DODGE-013 requires AC power')
    b.need(b.sha(reg['runtime_manifest_path'])==reg['runtime_manifest_sha256'],'runtime manifest changed')
    started=time.monotonic(); install_lease(reg)
    b.save(reg['attempt_claim_path'],dict(schema=b.ATTEMPT_SCHEMA,run_id=reg['run_id'],
        registration_sha256=registration_sha256,started=started,exactly_once=True))
    pins={str(Path(registration).resolve()):registration_sha256,str(Path(gate_path).resolve()):gate_sha256,
        str(Path(source_path).resolve()):source_sha256,str(Path(reg['interpreter']).resolve()):reg['interpreter_sha256'],
        str(b.SOURCE_MANIFEST):reg['source_manifest_sha256'],str(Path(reg['runtime_manifest_path'])):reg['runtime_manifest_sha256'],
        **gate['pins'],**reg['input_pins']}
    envelope=dict(schema=b.ENVELOPE_SCHEMA,run_id=reg['run_id'],registration=str(Path(registration).resolve()),
        registration_sha256=registration_sha256,source_acceptance=str(Path(source_path).resolve()),
        source_acceptance_sha256=source_sha256,gate_acceptance=str(Path(gate_path).resolve()),
        gate_acceptance_sha256=gate_sha256,control=str(control),cancel_path=str(b.CANCEL),
        started=started,pins=pins,power_guard=power)
    path=b.HERE/'launch-envelope.json'; b.save(path,envelope); digest=b.sha(path)
    b.save(reg['launch_marker_path'],dict(schema='one_frame_training_comparison_spent_marker_v1',
        run_id=reg['run_id'],registration_sha256=registration_sha256,envelope_sha256=digest,started=started))
    env,loaded=b.load_envelope(path,digest); b.verify_bound(env,loaded,preflight=True)
    childenv=os.environ.copy();childenv.update(PYTHONDONTWRITEBYTECODE='1',
        PYTHONPYCACHEPREFIX=str(cache),PYTHONPATH=reg['runtime_root'])
    command=[reg['interpreter'],'-B',str(b.HERE/'observe.py'),'--envelope',str(path),'--envelope-sha256',digest]
    with (b.HERE/'observer.log').open('x') as log:
        proc=subprocess.Popen(command,cwd=b.ROOT,env=childenv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        b.save(b.HERE/'parent-execution.json',dict(observer_pid=proc.pid,observer_pgid=proc.pid,
            command=command,started=started,registration_sha256=registration_sha256,
            envelope_sha256=digest,power_guard=power,lease_clear_owner='parent audit after durable terminal audit'))
        code=proc.wait()
    b.save(b.HERE/'execution-exit.json',dict(raw_observer_exit_code=code,observer_directly_reaped=True,
        elapsed_seconds=time.monotonic()-started,registration_sha256=registration_sha256,
        parent_terminal_audit_pending=True,lease_cleared=False))
    b.need(not any(cache.iterdir()), 'bytecode cache is not empty after supervised worker')
    return int(code!=0)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('registration','registration-sha256','gate','gate-sha256','source-acceptance','source-acceptance-sha256'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    raise SystemExit(main(args.registration,args.registration_sha256,args.gate,args.gate_sha256,
                          args.source_acceptance,args.source_acceptance_sha256))
