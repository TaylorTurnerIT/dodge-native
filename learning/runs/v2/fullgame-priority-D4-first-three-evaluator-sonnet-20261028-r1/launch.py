"""Root-owned parent gate binding; one attempt, one direct-owner watchdog. Not run during preparation.

Installs the lease only in the OWN evaluation ledger. The main training state is read-only here.
Launch as `/usr/bin/caffeinate -ims <env/python> -B launch.py ...` from the native root session.
"""
from __future__ import annotations
import argparse
import datetime
import os
from pathlib import Path
import subprocess
import time
import binding as b
import power_guard


def replace_state(path,state):
    staged=Path(path).with_name('evaluation-resource-ledger.pending.json')
    b.save(staged,state);os.replace(staged,path)
    directory=os.open(Path(path).parent,os.O_RDONLY)
    try:os.fsync(directory)
    finally:os.close(directory)


def install_own_lease(reg):
    """Install the exact evaluation lease in the OWN ledger. Main training state is only read (allowlist)."""
    b.need(not os.path.lexists(reg['ledger_path']) and not os.path.lexists(Path(reg['ledger_path']).with_name('evaluation-resource-ledger.pending.json')),
        'own evaluation ledger already spent')
    b.need(Path(reg['ledger_path'])!=Path(reg['concurrency']['main_state_path']),'own ledger aliases main state')
    b.check_main_state(reg)
    b.save(reg['ledger_path'],dict(schema=b.LEDGER_SCHEMA,run_id=reg['run_id'],active_evaluation_lease=reg['expected_lease'],
        installed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),main_state_written=False))


def main(registration,registration_sha,gate_path,gate_sha,source_acceptance,source_acceptance_sha):
    b.check_pins({registration:registration_sha,gate_path:gate_sha,source_acceptance:source_acceptance_sha})
    reg=b.read(registration);b.validate_static(reg)
    gates=b.read(gate_path)
    b.need(gates['schema']=='fullgame_priority_d4_first3_evaluation_gate_acceptance_v1'
        and gates['status']=='approved_exactly_once_fixed_terminal60_d4_evaluation'
        and gates['registration_sha256']==registration_sha
        and gates['gates']==dict.fromkeys(b.GATES,'passed'),'exact parent gates missing')
    b.check_pins(gates['pins'])
    acceptance=b.read(source_acceptance)
    b.need(acceptance['source_manifest_sha256']==reg['source_manifest_sha256']
        and acceptance['status']=='accepted_source_review_only','independent source acceptance differs')
    for key in ('output','attempt_claim_path','launch_marker_path'):
        b.need(not os.path.lexists(reg[key]),'registered attempt already spent: '+key)
    for name in ('launch-envelope.json','parent-execution.json','execution-exit.json','observer.log'):
        b.need(not os.path.lexists(b.HERE/name),'parent output already spent: '+name)
    control=b.HERE/'dispatch'/reg['run_id'];b.need(not control.exists(),'dispatch already spent')
    power=power_guard.check()
    started=time.monotonic()
    install_own_lease(reg)
    envelope=dict(schema='fullgame_priority_d4_first3_evaluation_envelope_v1',status='parent_bound_exactly_one_run',
        registration=str(Path(registration).resolve()),registration_sha256=registration_sha,
        launch_approval=str(Path(gate_path).resolve()),launch_approval_sha256=gate_sha,
        source_acceptance=str(Path(source_acceptance).resolve()),source_acceptance_sha256=source_acceptance_sha,
        control=str(control),cancel_path=str(b.HERE/'cancel'),started=started,
        pins={**{str(b.HERE/name):digest for name,digest in b.read(b.HERE/'source-manifest.json')['files'].items()},
              str(b.HERE/'source-manifest.json'):reg['source_manifest_sha256'],**gates['pins']},
        interpreter_resolved=str(Path(reg['interpreter']).resolve()),interpreter_sha256=b.sha(Path(reg['interpreter']).resolve()))
    path=b.HERE/'launch-envelope.json';b.save(path,envelope);digest=b.sha(path)
    b.save(reg['launch_marker_path'],dict(schema='fullgame_priority_d4_first3_evaluation_spent_marker_v1',
        registration_sha256=registration_sha,run_id=reg['run_id'],started=started))
    e,_=b.load_envelope(path,digest);b.verify_bound(e,reg,preflight=True)
    env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=reg['import_policy']['pycache_prefix'])
    command=[reg['interpreter'],'-B',str(b.HERE/'observe.py'),'--envelope',str(path),'--envelope-sha256',digest]
    with (b.HERE/'observer.log').open('x') as log:
        process=subprocess.Popen(command,cwd=b.ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        b.save(b.HERE/'parent-execution.json',dict(observer_pid=process.pid,observer_pgid=process.pid,
            command=command,started=started,registration_sha256=registration_sha,envelope_sha256=digest,
            power_guard=power))
        print('evaluation_launched_exactly_once',process.pid,flush=True)
        code=process.wait()
    b.save(b.HERE/'execution-exit.json',dict(raw_observer_exit_code=code,observer_directly_reaped=True,
        elapsed_seconds=time.monotonic()-started,registration_sha256=registration_sha,parent_terminal_audit_pending=True))
    print('evaluation_terminal_parent_audit_pending',code,flush=True)
    return int(code!=0)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('registration','registration-sha256','gate','gate-sha256','source-acceptance','source-acceptance-sha256'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    raise SystemExit(main(args.registration,args.registration_sha256,args.gate,args.gate_sha256,
        args.source_acceptance,args.source_acceptance_sha256))
