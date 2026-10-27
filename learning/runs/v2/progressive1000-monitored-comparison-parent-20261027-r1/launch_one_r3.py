"""Parent-approved one-use timing probe; retain observer and raw exit evidence."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[3]
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--run-id',required=True)
run_id=parser.parse_args().run_id
if '/' in run_id or run_id not in {row['run_id'] for row in json.loads((PACKAGE/'registration-index.json').read_text())['runs']}:
    raise ValueError('unregistered comparison run')
HERE=PACKAGE/run_id
SUPERVISOR = ROOT/'learning/runs/v2/progressive1000-throughput-supervisor-parent-20261027-r3'
sys.path.insert(0,str(SUPERVISOR))
import binding as b


def publish_state(state):
    path=ROOT/'learning/runs/v2-orchestration/state.json'
    staged=path.with_name('state.throughput-probe.pending.json')
    b.save(staged,state)
    os.replace(staged,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def main():
    reg_path=HERE/'registration-final.json';reg=b.read(reg_path);digest=b.sha(reg_path)
    gates=b.read(HERE/'gate-acceptance.json')
    b.need(gates['status']=='approved_for_exactly_one_registered_comparison' and gates['registration_sha256']==digest,'missing exact parent gates')
    for path,expected in gates['pins'].items():b.need(b.sha(path)==expected,'gate evidence drift: '+path)
    for key in ('output','attempt_claim_path','launch_marker_path'):
        b.need(not os.path.lexists(reg[key]),'one-use probe already spent: '+key)
    control=SUPERVISOR/'dispatch'/reg['run_id']
    b.need(not control.exists(),'supervisor dispatch already spent')
    state=b.read(reg['state_path'])
    b.need(state.get('active_long_campaign') is None and state.get('active_inference_diagnostic') is None,'conflicting campaign')
    b.save(HERE/'user-authorization.json',dict(user_message='Go',scope='slowdown diagnosis, progress monitoring, bounded timing check, then matched comparison with measured limits',
        purpose='matched_comparison',registration_sha256=digest,qualification=False,retries=0))
    state['active_long_campaign']=reg['expected_lease']
    state['progressive1000_curriculum_work'].update(status='authorized_monitored_comparison_preflight',
        active_registered_run=str(reg_path),active_registered_run_sha256=digest,current_launch_authorized=True,
        throughput_probe=str(PACKAGE/'wall-budget.json'),throughput_source=str(b.SOURCE),
        throughput_supervisor=str(SUPERVISOR))
    state['last_update_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    publish_state(state)
    c=b.contracts();c.validate_static(reg);c.cache_check(reg);dependencies=b.verify_dependencies(reg)
    approval=dict(schema='progressive1000_parent_launch_approval_v1',status='approved_exactly_one_registered_run',
        registration_sha256=digest,source_manifest_sha256=reg['source_manifest_sha256'],
        runtime_manifest_sha256=reg['runtime_manifest_sha256'],run_id=reg['run_id'],gates=dict.fromkeys(c.GATES,'passed'))
    approval_path=HERE/'launch-approval.json';b.save(approval_path,approval)
    b.save(HERE/'parent-preflight.json',dict(registration_sha256=digest,static_inputs='passed',cache='passed',dependencies=dependencies,
        evidence_scope='Inherited identical runtime/native bytes and prior actual restore; new worker source and bounded probe reviewed separately.'))
    started=time.monotonic()
    pins={str(SUPERVISOR/name):b.sha(SUPERVISOR/name) for name in ('binding.py','terminal.py','execute_once.py','observe.py','dependency-binding.json','source-manifest.json')}
    pins.update(gates['pins'])
    acceptance=HERE/'source-acceptance.json'
    envelope=dict(schema='progressive1000_existing_supervisor_envelope_v1',status='parent_bound_exactly_one_run',
        registration=str(reg_path),registration_sha256=digest,launch_approval=str(approval_path),launch_approval_sha256=b.sha(approval_path),
        source_acceptance=str(acceptance),source_acceptance_sha256=b.sha(acceptance),control=str(control),
        cancel_path=str(HERE/'cancel'),started=started,pins=pins,
        interpreter_resolved=str(Path(reg['interpreter']).resolve()),interpreter_sha256=b.sha(Path(reg['interpreter']).resolve()))
    envelope_path=HERE/'launch-envelope.json';b.save(envelope_path,envelope);envelope_sha=b.sha(envelope_path)
    b.load_envelope(envelope_path,envelope_sha)
    b.save(reg['launch_marker_path'],dict(schema='progressive1000_parent_spent_launch_marker_v1',registration_sha256=digest,run_id=reg['run_id'],started=started))
    command=[reg['interpreter'],'-B',str(SUPERVISOR/'observe.py'),'--envelope',str(envelope_path),'--envelope-sha256',envelope_sha]
    with (HERE/'observer.log').open('xb') as output:
        process=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        b.save(HERE/'parent-execution.json',dict(command=command,observer_pid=process.pid,observer_pgid=process.pid,
            registration_sha256=digest,envelope_sha256=envelope_sha,started=started))
        print(json.dumps(dict(status='comparison_launched_once',pid=process.pid,updates=60)),flush=True)
        position=0;last_update=-1;last_warning=False;last_print=started
        with (HERE/'progress-reports.jsonl').open('x') as reports:
            while process.poll() is None:
                log=control/'worker.log'
                if log.exists():
                    with log.open() as stream:
                        stream.seek(position)
                        while True:
                            offset=stream.tell();line=stream.readline()
                            if not line or not line.endswith('\n'):
                                position=offset;break
                            position=stream.tell()
                            try:row=json.loads(line)
                            except ValueError:continue
                            if row.get('schema')!='progressive1000_progress_v1':continue
                            reports.write(line);reports.flush()
                            completed=row['completed_updates'];warning=row['projected_work_deadline_miss'];now=time.monotonic()
                            if completed!=last_update or warning!=last_warning or now-last_print>=60:
                                print(json.dumps(row,sort_keys=True),flush=True)
                                last_update,last_warning,last_print=completed,warning,now
                time.sleep(.5)
            result=process.wait()
    b.save(HERE/'execution-exit.json',dict(raw_observer_exit_code=result,elapsed_seconds=time.monotonic()-started,
        observer_directly_reaped=True,registration_sha256=digest,envelope_sha256=envelope_sha,parent_terminal_audit_pending=True))
    print(json.dumps(dict(status='comparison_terminal_parent_audit_pending',raw_exit=result)),flush=True)
    return int(result!=0)


if __name__=='__main__':
    raise SystemExit(main())
