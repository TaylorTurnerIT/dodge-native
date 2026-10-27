#!/usr/bin/env python3
"""Exclusive single-launch, stdlib-only observer. No learner imports or timer installation."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
import traceback

ROOT=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
OUT=ROOT/'learning/runs/v2/postovernight-long-D2-execution-observer-r1'
PREP=ROOT/'learning/runs/v2/postovernight-long-D2-prepare-r4'
CAPSULE=PREP/'capsule-final'
HELPERS=CAPSULE/'learning/runs/v2/postovernight-long-D2-prepare-r4'
PLAN=ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-execution-r1-plan.json'
STATE=ROOT/'learning/runs/v2-orchestration/state.json'
PLAN_SHA='fb0e7226ce4c66f748e5d09959014988c01bb63471b74212bae9f34c6b421cde'
EXPECTED_ARGV=[str(ROOT/'learning/.venv/bin/python'),'-B',str(HELPERS/'long_d2_executor.py'),'run','--registration',str(PREP/'registration.json')]

def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def pairs(items):
    value={}
    for k,v in items:
        if k in value:raise RuntimeError('Duplicate JSON key: '+k)
        value[k]=v
    return value
def read(path):return json.loads(Path(path).read_bytes(),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(RuntimeError('Nonfinite JSON '+x)))
def require(value,message):
    if not value:raise RuntimeError(message)
def save(name,value):
    with (OUT/name).open('x') as f:
        json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
def emit(f,value):
    f.write(json.dumps(value,sort_keys=True,allow_nan=False)+'\n');f.flush()
def check(pins):
    mismatch={}
    for path,digest in pins.items():
        actual=sha(path)
        if actual!=digest:mismatch[path]={'expected':digest,'actual':actual}
    require(not mismatch,'Pinned input mismatch: '+repr(mismatch))
    return len(pins)
def table():
    p=subprocess.run(['ps','-axo','pid=,ppid=,pgid=,lstart=,rss=,args='],capture_output=True,text=True,timeout=.2)
    require(p.returncode==0,'Process census failed: '+p.stderr)
    rows=[]
    for line in p.stdout.splitlines():
        f=line.split(None,9)
        require(len(f)==10,'Malformed process census')
        rows.append(dict(pid=int(f[0]),ppid=int(f[1]),pgid=int(f[2]),start_time=' '.join(f[3:8]),rss_bytes=int(f[8])*1024,argv=shlex.split(f[9])))
    return rows

def preflight():
    require(sha(PLAN)==PLAN_SHA,'Execution plan SHA mismatch')
    plan=read(PLAN);inv=read(ROOT/plan['invocation']);acceptance=read(ROOT/plan['acceptance'])
    require(sha(ROOT/plan['acceptance'])==plan['acceptance_sha256'],'Parent acceptance SHA mismatch')
    require(sha(ROOT/plan['invocation'])==plan['invocation_sha256'],'Invocation SHA mismatch')
    require(sha(ROOT/plan['registration'])==plan['registration_sha256']==inv['registration_sha256'],'Registration SHA mismatch')
    require(plan['command']==inv['argv']==EXPECTED_ARGV and plan['cwd']==inv['cwd']==str(CAPSULE),'Exact argv/cwd mismatch')
    require(plan['environment']==inv['environment']=={'PYTHONDONTWRITEBYTECODE':'1'} and plan['unset_environment']==inv['unset_environment']==['PYTORCH_ENABLE_MPS_FALLBACK'],'Environment delta mismatch')
    require(plan['normal_max_seconds']==7200 and plan['latest_failure_deadline_seconds']==7210 and plan['one_invocation_only'] is True,'Plan bounds mismatch')
    require(acceptance['status']=='parent_accepted_R4_for_exactly_one_previously_authorized_long_D2_experiment' and acceptance['campaign_invocations_before_acceptance']==0,'Parent acceptance authority mismatch')
    state=read(STATE);lease=read(PREP/'required-lease.json')
    require(len(lease)==15 and state['active_long_campaign']==lease==plan['required_lease']==acceptance['required_lease'] and lease['cancel_requested'] is False,'Strict 15-field lease mismatch')
    require(state['scheduler_enabled'] is False and state['scheduler_next_run_at'] is None,'Scheduler must remain disabled')
    for key in ('review','evidence_API_audit'):
        path=ROOT/acceptance[key]
        require(sha(path)==acceptance[key+'_sha256'],'Accepted review SHA mismatch: '+key)
        report=read(path);require(report['findings']==[],'Accepted review contains findings')
    registration=read(PREP/'registration.json');require(registration==inv['registration'],'Invocation registration mismatch')
    check(registration['pins'])
    for k in ('controller','executor'):
        require(sha(registration[k])==sha(PREP/(k=='controller' and 'long_d2.py' or 'long_d2_executor.py'))==acceptance[k+'_sha256'],'Preparation/capsule source mismatch')
    sys.path.insert(0,str(HELPERS))
    import long_d2 as c
    import processes as owned
    import long_d2_executor as executor
    require(not any(n in ('torch','numpy','dodge_rl') or n.startswith(('torch.','numpy.','dodge_rl.')) for n in sys.modules),'Observer imported ML/project')
    context=c.capsule_context(CAPSULE)
    protocol,config,base,identity,pins,expected=context
    c.assert_lease(STATE,expected);require(expected==lease,'Frozen helper required lease mismatch')
    require(len(pins)==9870 and len(identity['base_registered_identity']['sources'])==75,'Frozen input count mismatch')
    d1=state['M3_implementation']['D1'];anchor=lease['parent_terminal_receipt']
    require(anchor==protocol['parent_terminal_receipt']==identity['parent_terminal_receipt']==d1['parent_terminal_receipt'],'Eligible D1 terminal anchor mismatch')
    require(anchor['checkpoint_sha256']==acceptance['parent_checkpoint']==d1['candidate_sha256']==sha(ROOT/protocol['parent_checkpoint']),'Eligible D1 checkpoint mismatch')
    require(d1['supervisor_exit_code']==anchor['supervisor_exit_code']==0 and d1['status']=='accepted_D1_progress_only' and sha(ROOT/d1['run_result'])==anchor['run_result_sha256'],'D1 successful terminal binding mismatch')
    require(d1['identity_sha256']==anchor['identity_sha256']==sha(ROOT/d1['identity']) and d1['config_sha256']==anchor['config_sha256']==sha(ROOT/d1['config']),'D1 identity/config binding mismatch')
    campaign=Path(registration['output']);receipt=Path(registration['receipt'])
    require(not campaign.exists() and not receipt.parent.exists(),'Single-use output/receipt path already exists')
    immutable=read(PREP/'protected-before.json')
    require(str(STATE) not in immutable,'Unexpected mutable state in historical immutable inventory')
    check(immutable)
    artifacts=read(PREP/'artifact-inventory.json');check({str(PREP/k):v for k,v in artifacts.items()})
    protected=dict(immutable);protected.update(pins);protected.update({str(PREP/k):v for k,v in artifacts.items()})
    for tree in (PREP,ROOT/'learning/runs/v2/milestone3-D1-curriculum-r1',ROOT/'learning/runs/v2/milestone3-D2-curriculum-r1'):
        for path in tree.rglob('*'):
            if path.is_file():protected[str(path)]=sha(path)
    for path in (PLAN,ROOT/plan['acceptance'],ROOT/plan['invocation'],ROOT/plan['registration'],PREP/'required-lease.json',STATE):protected[str(path)]=sha(path)
    save('sourcehashes-before.json',dict(pins=pins,protected=protected,legacy_sources=75,identity_raw_sha256=sha(HELPERS/'long-identity.json'),identity_semantic_sha256=c.semantic_hash(identity)))
    save('state-before.json',state)
    env=dict(os.environ);env['PYTHONDONTWRITEBYTECODE']='1';env.pop('PYTORCH_ENABLE_MPS_FALLBACK',None)
    save('command.json',dict(argv=EXPECTED_ARGV,cwd=str(CAPSULE),environment_set=plan['environment'],environment_unset=plan['unset_environment'],inherited_environment_sha256=c.semantic_hash(dict(os.environ)),effective_environment_sha256=c.semantic_hash(env),observer_sha256=sha(__file__),registration_sha256=sha(PREP/'registration.json'),plan_sha256=sha(PLAN)))
    command=EXPECTED_ARGV.copy();command[3]='preflight'
    save('frozen-preflight-command.json',dict(argv=command,cwd=str(CAPSULE),ML_execution=False))
    with (OUT/'frozen-preflight.stdout.log').open('x') as stdout,(OUT/'frozen-preflight.stderr.log').open('x') as stderr:
        result=subprocess.run(command,cwd=CAPSULE,env=env,stdout=stdout,stderr=stderr,timeout=60)
    require(result.returncode==0,'Frozen executor preflight failed with exit '+str(result.returncode))
    pre=read(OUT/'frozen-preflight.stdout.log')
    require(pre['status']=='pure_identity_preflight_passed' and pre['verified_pin_count']==9870 and pre['launch_performed'] is False,'Frozen preflight evidence mismatch')
    c.assert_lease(STATE,lease);require(not campaign.exists() and not receipt.parent.exists(),'Single-use output appeared during preflight')
    save('preflight.json',dict(status='passed',utc=utc(),strict_lease=lease,verified_full_pins=len(pins),protected_files=len(protected),preparation_artifacts=len(artifacts),frozen_preflight_returncode=result.returncode,ML_project_imports=False,campaign_output_absent=True,observer_sha256=sha(__file__)))
    return plan,registration,lease,env,owned

def main():
    process=child=None;start=None;groups={};signals=[];errors=[];deadline_missed=False
    result=dict(actual_command_launch_count=0,observer_pid=os.getpid(),observer_started_utc=utc(),observer_sha256=sha(__file__),normal_cap_seconds=7200,latest_failure_cap_seconds=7210,no_new_cleanup_allowance=True,retry=False)
    save('invocation-count-initial.json',dict(actual_command_launch_count=0,utc=utc()))
    signal_log=(OUT/'signals.jsonl').open('x');observations=(OUT/'process-observations.jsonl').open('x')
    def observe():
        rows=table();by={r['pid']:r for r in rows};selected=[]
        if process is None:return rows
        outer=by.get(process.pid)
        if outer is not None and outer['argv']==EXPECTED_ARGV and outer['ppid']==os.getpid() and outer['pgid']==outer['pid'] and os.getsid(outer['pid'])==outer['pid']:
            groups.setdefault('outer',dict(outer,new_session_verified=True))
        controller=registration['controller'];inner=None
        for row in rows:
            a=row['argv']
            if (len(a)==12 and a[:4]==[EXPECTED_ARGV[0],'-B',controller,'run'] and a[4:8]==['--output',registration['output'],'--state-path',registration['state_path']] and a[8]=='--executor-fd' and a[9].isdigit() and a[10:]==['--executor-pid',str(process.pid)] and row['ppid']==process.pid and row['pgid']==row['pid'] and os.getsid(row['pid'])==row['pid']):
                inner=row;groups.setdefault('inner',dict(row,new_session_verified=True))
        inner=inner or groups.get('inner')
        if inner:
            for row in rows:
                a=row['argv']
                if (len(a)==16 and a[:4]==[EXPECTED_ARGV[0],'-B',controller,'worker'] and a[4:8]==['--output',registration['output'],'--state-path',registration['state_path']] and a[8]=='--started' and a[10:13]==['--supervisor-pid',str(inner['pid']),'--executor-fd'] and a[13].isdigit() and a[14:]==['--executor-pid',str(process.pid)] and row['ppid']==inner['pid'] and row['pgid']==row['pid'] and os.getsid(row['pid'])==row['pid']):
                    t0=float(a[9]);require(start<=t0<=time.monotonic(),'Worker shared T0 outside observed run')
                    groups.setdefault('worker',dict(row,new_session_verified=True,shared_t0=t0))
        for role,identity in groups.items():
            row=by.get(identity['pid'])
            if row is not None:
                require(row['start_time']==identity['start_time'] and row['argv']==identity['argv'] and row['pgid']==identity['pgid'],'Observed owned identity changed: '+role)
            selected.extend(dict(r,role=role) for r in rows if r['pgid']==identity['pgid'])
        emit(observations,dict(utc=utc(),monotonic=time.monotonic(),elapsed_seconds=time.monotonic()-start,owned=selected))
        return rows
    def cancel(number,frame):
        record=dict(signal=number,utc=utc(),monotonic=time.monotonic(),record_precedes_forward=True)
        signals.append(record);emit(signal_log,record);os.fsync(signal_log.fileno())
        if process is not None and child.report is None:
            try:
                observe();identity=groups.get('outer');require(identity is not None,'Outer signal ownership unproven')
                os.killpg(identity['pgid'],number)
            except ProcessLookupError:pass
            except BaseException as e:errors.append('Signal forwarding: '+repr(e))
    try:
        plan,registration,lease,env,owned=preflight()
        signal.signal(signal.SIGINT,cancel);signal.signal(signal.SIGTERM,cancel)
        with (OUT/'outer.stdout.log').open('x') as stdout,(OUT/'outer.stderr.log').open('x') as stderr:
            require(read(STATE)['active_long_campaign']==lease,'Lease changed immediately before Popen')
            require(not Path(registration['output']).exists() and not Path(registration['receipt']).parent.exists(),'Single-use output appeared before Popen')
            save('invocation-attempt-1.json',dict(actual_command_launch_count=1,argv=EXPECTED_ARGV,cwd=str(CAPSULE),utc=utc(),one_attempt_only=True))
            result['actual_command_launch_count']=1
            start_utc=utc();start=time.monotonic()
            process=subprocess.Popen(EXPECTED_ARGV,cwd=CAPSULE,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
            child=owned.Child(process)
            result.update(popen_before_monotonic=start,popen_before_utc=start_utc,popen_return_monotonic=time.monotonic(),popen_return_utc=utc(),outer_pid=process.pid,outer_pgid=process.pid)
            save('start.json',result)
            print('Single frozen command launched: outer PID '+str(process.pid),flush=True)
            next_census=start;next_status=start+45
            while child.poll() is None:
                now=time.monotonic()
                if now>=start+7210:
                    deadline_missed=True;errors.append('Conservative external failure deadline missed: 7210 seconds')
                    rows=observe();by={r['pid']:r for r in rows}
                    for role in ('worker','inner','outer'):
                        identity=groups.get(role)
                        if identity is None:
                            errors.append('Emergency group ownership unproven: '+role);continue
                        row=by.get(identity['pid'])
                        if row is None:
                            if any(r['pgid']==identity['pgid'] for r in rows):errors.append('Emergency leader absent; group ownership unproven: '+role)
                            continue
                        if row['start_time']==identity['start_time'] and row['argv']==identity['argv'] and row['pgid']==identity['pid'] and os.getsid(identity['pid'])==identity['pid']:
                            emit(signal_log,dict(emergency=True,signal=int(signal.SIGKILL),role=role,pid=identity['pid'],monotonic=time.monotonic(),no_added_grace=True))
                            try:os.killpg(identity['pgid'],signal.SIGKILL)
                            except ProcessLookupError:pass
                        else:errors.append('Emergency current ownership unproven: '+role)
                    break
                if now>=next_census:
                    try:observe()
                    except BaseException as e:emit(observations,dict(observation_error=repr(e),monotonic=time.monotonic()))
                    next_census=time.monotonic()+(0.25 if now<start+5 else 1)
                if now>=next_status:
                    print(json.dumps(dict(outer_pid=process.pid,elapsed_seconds=now-start,proven_roles=list(groups))),flush=True);next_status=now+45
                time.sleep(min(.05,max(.001,start+7210-time.monotonic())))
            if child.report is None:child.poll()
            result.update(raw_wait_report=child.report,reap_observed_utc=utc(),actual_wall_seconds=None if child.report is None else child.report['observed_monotonic']-start,deadline_missed=deadline_missed)
            save('raw-wait.json',dict(report=child.report,actual_wall_seconds=result['actual_wall_seconds'],reap_observed_utc=result['reap_observed_utc'],scope='Only observer direct child; no nonchild reaping claim'))
    except BaseException as e:
        errors.append(repr(e));result['traceback']=traceback.format_exc()
        # No second launch, new timer, or new cleanup allowance on observer failure.
        if process is not None and child is not None and child.report is None:
            try:cancel(signal.SIGTERM,None)
            except BaseException as e2:errors.append(repr(e2))
            while child.poll() is None and time.monotonic()<start+7210:time.sleep(.05)
            result.update(raw_wait_report=child.report,actual_wall_seconds=None if child.report is None else child.report['observed_monotonic']-start,reap_observed_utc=utc())
    finally:
        result.update(errors=errors,owned_identities=groups,cancellation_requests=signals,observer_finished_utc=utc(),stdout_stderr_closed=True,ledger_written=False,scheduler_changed=False)
        try:
            rows=table();pgids={g['pgid'] for g in groups.values()}
            result['owned_remaining_rows']=[r for r in rows if r['pgid'] in pgids]
            result['positive_group_absence']={role:owned.absent(g['pgid'],time.monotonic()+1) for role,g in groups.items()} if process is not None else {}
        except BaseException as e:result['absence_error']=repr(e)
        signal_log.close();observations.close()
        save('process-exit.json',result)
        print(json.dumps(dict(actual_command_launch_count=result['actual_command_launch_count'],raw_wait_report=result.get('raw_wait_report'),actual_wall_seconds=result.get('actual_wall_seconds'),errors=errors)),flush=True)
    return 0 if result.get('raw_wait_report',{}).get('returncode') in (0,2) and not errors else 1

if __name__=='__main__':sys.exit(main())
