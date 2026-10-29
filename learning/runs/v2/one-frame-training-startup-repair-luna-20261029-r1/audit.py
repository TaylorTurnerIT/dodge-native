"""Parent-side durable terminal audit, then exact lease release."""
from __future__ import annotations
import argparse
import datetime
import os
from pathlib import Path
import binding as b
import terminal
from execute_once import group_exists


def replace_state(path,state):
    staged=Path(path).with_name(b.PENDING_STATE)
    b.save(staged,state); os.replace(staged,path)
    directory=os.open(Path(path).parent,os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)


def clear_lease(reg):
    b.check_lease(reg)
    path=Path(reg['state_path']); b.need(not os.path.lexists(path.with_name(b.PENDING_STATE)),
        'state pending file exists')
    state=b.read(path)
    b.need(state.get(reg['lease_key'])==reg['expected_lease'],'exact run lease changed before release')
    state[reg['lease_key']]=None
    state['last_update_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    replace_state(path,state)
    b.need(b.read(path).get(reg['lease_key']) is None,'lease release readback differs')


def validate_artifact_manifest(out, manifest):
    b.need(type(manifest) is dict and manifest,'supervisor artifact manifest missing')
    actual={}
    for path in Path(out).iterdir():
        b.need(path.is_file() and not path.is_symlink(),'worker output must contain only flat regular files')
        actual[path.name]=b.sha(path)
    b.need(all(Path(name).name==name for name in manifest)
        and set(manifest)==set(actual) and manifest==actual,
        'supervisor output artifact manifest differs from exact current output bytes')
    return actual


def finalize(registration, registration_sha256, observer_receipt, observer_sha256, exit_receipt, exit_sha256):
    b.verify_pins({registration:registration_sha256,observer_receipt:observer_sha256,
                   exit_receipt:exit_sha256})
    reg=b.read(registration); phase=reg.get('phase','formal')
    b.validate_static(reg,require_registered=True,check_streams=True,phase=phase)
    observation=b.read(observer_receipt); exit_doc=b.read(exit_receipt)
    b.need(observation.get('status')=='completed_pending_parent_audit'
        and observation.get('registration_sha256')==registration_sha256
        and observation.get('observed_worker_raw_exit')==0 and observation.get('directly_reaped') is True
        and observation.get('owned_group_absent') is True,'observer completion proof differs')
    b.need(exit_doc.get('raw_observer_exit_code')==0 and exit_doc.get('observer_directly_reaped') is True
        and exit_doc.get('registration_sha256')==registration_sha256,'parent execution receipt differs')
    phase_root=b.phase_path(reg,'')
    envelope_path=phase_root/'launch-envelope.json'; envelope=b.read(envelope_path)
    control=phase_root/'dispatch'/reg['run_id']
    b.need(b.sha(envelope_path)==observation.get('envelope_sha256')==exit_doc.get('envelope_sha256')
        and envelope.get('phase','formal')==phase and envelope.get('run_id')==reg['run_id']
        and envelope.get('registration')==str(Path(registration).resolve())
        and envelope.get('registration_sha256')==registration_sha256
        and envelope.get('control')==str(control.resolve()),'phase envelope/control binding differs')
    b.verify_bound(envelope,reg,preflight=True)
    limits=reg['limits']
    b.need(observation.get('first_event') is None and observation.get('deadline_consumed') is False
        and 0<=observation.get('elapsed_seconds',limits['total_seconds'])<limits['total_seconds']
        and observation.get('max_aggregate_rss_bytes',limits['rss_bytes']+1)<=limits['rss_bytes']
        and observation.get('final_observer_peak_rss_bytes',limits['rss_bytes']+1)<=limits['rss_bytes'],
        'observer work/total/resource boundary differs')
    b.need(exit_doc.get('elapsed_seconds',limits['total_seconds'])<limits['total_seconds'],
        'parent execution exceeded registered total deadline')
    cache=Path(reg['import_policy']['pycache_prefix'])
    b.need(cache.is_dir() and not cache.is_symlink() and not any(cache.iterdir()),
        'phase bytecode cache is not empty after worker')
    worker_pid=observation.get('worker_pid'); worker_pgid=observation.get('owned_pgid')
    observer_pid=exit_doc.get('observer_pid'); observer_pgid=exit_doc.get('observer_pgid')
    for pid,pgid,role in ((worker_pid,worker_pgid,'worker'),(observer_pid,observer_pgid,'observer')):
        b.need(type(pid) is int and 1<pid<=0x7fffffff and type(pgid) is int
            and 1<pgid<=0x7fffffff and pgid!=os.getpgrp(), 'unsafe '+role+' PID/PGID receipt')
        b.need(not group_exists(pgid),role+' process group remains after supervised exit')
    worker=b.read(Path(reg['output'])/'worker-result.json')
    evidence=(terminal.validate_qualification_outputs(reg,worker,registration_sha256)
        if phase=='qualification' else terminal.validate_outputs(reg,worker,registration_sha256))
    local_audit=b.read(phase_root/'local-terminal-audit.json')
    b.need(local_audit.get('schema')==b.AUDIT_SCHEMA and local_audit.get('phase')==phase
        and local_audit.get('run_id')==reg['run_id']
        and local_audit.get('registration_sha256')==registration_sha256
        and local_audit.get('worker_result_sha256')==b.sha(Path(reg['output'])/'worker-result.json')
        and local_audit.get('audit')==evidence,
        'local terminal audit differs from parent recomputation')
    resources=b.worker_resources(reg['output'],strict=True)
    b.need(resources['peak_rss_bytes']<=limits['rss_bytes']
        and resources['peak_mps_driver_bytes']<=limits['mps_bytes'],
        'strict worker resource journal exceeds registered limits')
    manifest=b.read(control/'artifact-manifest.json')
    validate_artifact_manifest(reg['output'],manifest)
    audit=dict(schema=b.AUDIT_SCHEMA,status='parent_terminal_audit_accepted',phase=phase,
        run_id=reg['run_id'],registration_sha256=registration_sha256,
        envelope_sha256=observation['envelope_sha256'],observer_receipt_sha256=observer_sha256,
        execution_exit_sha256=exit_sha256,evidence=evidence,worker_result_sha256=b.sha(Path(reg['output'])/'worker-result.json'),
        artifact_manifest=manifest,worker_resources={k:resources[k] for k in
            ('samples','peak_rss_bytes','peak_mps_driver_bytes')},launch_authority=False,automatic_selection=False,
        promoted=False,training_eligible=False,lease_cleared=False)
    path=phase_root/'parent-terminal-audit.json'; b.save(path,audit)
    audit_sha=b.sha(path)
    clear_lease(reg)
    b.save(phase_root/'lease-release.json',dict(schema='one_frame_training_comparison_lease_release_v1',
        run_id=reg['run_id'],registration_sha256=registration_sha256,
        parent_terminal_audit_sha256=audit_sha,lease_value_after_release=None))
    return audit


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('registration','registration-sha256','observer-receipt','observer-sha256','exit-receipt','exit-sha256'):
        parser.add_argument('--'+name,required=True)
    a=parser.parse_args();finalize(a.registration,a.registration_sha256,a.observer_receipt,a.observer_sha256,
                                   a.exit_receipt,a.exit_sha256)
