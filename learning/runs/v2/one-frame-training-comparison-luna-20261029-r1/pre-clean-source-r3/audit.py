"""Parent-side durable terminal audit, then exact lease release."""
from __future__ import annotations
import argparse
import datetime
import os
from pathlib import Path
import binding as b
import terminal


def replace_state(path,state):
    staged=Path(path).with_name(b.PENDING_STATE)
    b.save(staged,state); os.replace(staged,path)
    directory=os.open(Path(path).parent,os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)


def clear_lease(reg):
    path=Path(reg['state_path']); b.need(not os.path.lexists(path.with_name(b.PENDING_STATE)),
        'state pending file exists')
    state=b.read(path)
    b.need(state.get(reg['lease_key'])==reg['expected_lease'],'exact run lease changed before release')
    state[reg['lease_key']]=None
    state['last_update_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    replace_state(path,state)
    b.need(b.read(path).get(reg['lease_key']) is None,'lease release readback differs')


def finalize(registration, registration_sha256, observer_receipt, observer_sha256, exit_receipt, exit_sha256):
    b.verify_pins({registration:registration_sha256,observer_receipt:observer_sha256,
                   exit_receipt:exit_sha256})
    reg=b.read(registration); b.validate_static(reg,require_registered=True,check_streams=True)
    observation=b.read(observer_receipt); exit_doc=b.read(exit_receipt)
    b.need(observation.get('status')=='completed_pending_parent_audit'
        and observation.get('registration_sha256')==registration_sha256
        and observation.get('observed_worker_raw_exit')==0 and observation.get('directly_reaped') is True
        and observation.get('owned_group_absent') is True,'observer completion proof differs')
    b.need(exit_doc.get('raw_observer_exit_code')==0 and exit_doc.get('observer_directly_reaped') is True
        and exit_doc.get('registration_sha256')==registration_sha256,'parent execution receipt differs')
    worker=b.read(Path(reg['output'])/'worker-result.json')
    evidence=terminal.validate_outputs(reg,worker,registration_sha256)
    manifest=b.read(Path(reg['launch_marker_path']).parent/'dispatch'/reg['run_id']/'artifact-manifest.json')
    b.need(type(manifest) is dict and manifest,'supervisor artifact manifest missing')
    audit=dict(schema=b.AUDIT_SCHEMA,run_id=reg['run_id'],registration_sha256=registration_sha256,
        envelope_sha256=observation['envelope_sha256'],observer_receipt_sha256=observer_sha256,
        execution_exit_sha256=exit_sha256,evidence=evidence,worker_result_sha256=b.sha(Path(reg['output'])/'worker-result.json'),
        artifact_manifest=manifest,launch_authority=False,automatic_selection=False,
        promoted=False,training_eligible=False,lease_cleared=False)
    path=b.HERE/'parent-terminal-audit.json'; b.save(path,audit)
    audit_sha=b.sha(path)
    clear_lease(reg)
    b.save(b.HERE/'lease-release.json',dict(schema='one_frame_training_comparison_lease_release_v1',
        run_id=reg['run_id'],registration_sha256=registration_sha256,
        parent_terminal_audit_sha256=audit_sha,lease_value_after_release=None))
    return audit


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('registration','registration-sha256','observer-receipt','observer-sha256','exit-receipt','exit-sha256'):
        parser.add_argument('--'+name,required=True)
    a=parser.parse_args();finalize(a.registration,a.registration_sha256,a.observer_receipt,a.observer_sha256,
                                   a.exit_receipt,a.exit_sha256)
