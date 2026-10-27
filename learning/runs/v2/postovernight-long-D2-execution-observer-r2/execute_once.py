#!/usr/bin/env python3
"""Single-use stdlib observer. The frozen executor owns experiment safety and cleanup."""
import datetime, hashlib, json, math, os, shlex, signal, subprocess, sys, time, traceback
from pathlib import Path
ROOT=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
OUT=ROOT/'learning/runs/v2/postovernight-long-D2-execution-observer-r2'
PLAN=ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-execution-r2-plan.json'
STATE=ROOT/'learning/runs/v2-orchestration/state.json'
PLAN_SHA='42b069b10f0cb71b7a6b2ae5e18b0c4a3bc4af26391431aa1a300c1b52621517'
PREP=ROOT/'learning/runs/v2/postovernight-long-D2-boundary-prepare-r14'
CAPSULE=PREP/'capsule-final'
HELPERS=CAPSULE/'learning/runs/v2/postovernight-long-D2-boundary-prepare-r14'
TASK='postovernight_long_D2_execution_r2'
START=time.monotonic()
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()
def pairs(items):
    d={}
    for k,v in items:
        if k in d: raise RuntimeError('Duplicate JSON key: '+k)
        d[k]=v
    return d
def read(path): return json.loads(Path(path).read_bytes(),object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def need(ok,msg):
    if not ok: raise RuntimeError(msg)
def save(name,value,replace=False):
    p=OUT/name; q=p.with_name('.'+p.name+'.pending') if replace else p
    with q.open('x') as f:
        json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    if replace: os.replace(q,p)
def emit(name,value):
    with (OUT/name).open('a') as f: f.write(json.dumps(value,sort_keys=True,allow_nan=False)+'\n');f.flush()
def check(pins):
    for name,digest in pins.items(): need(sha(name)==digest,'Input hash mismatch: '+name)
def ledger(fields,task_fields,status):
    s=read(STATE); before=json.loads(json.dumps(s))
    need(s['active_long_campaign']==plan['required_lease'],'Lease changed before bookkeeping')
    s['post_overnight_long_D2_r2'].update(fields);s['tasks'][TASK].update(task_fields)
    s['status']=status;s['last_update_at_utc']=utc()
    need(s['active_long_campaign']==before['active_long_campaign'],'Observer changed lease')
    q=OUT/'state-update.pending.json'
    with q.open('x') as f: json.dump(s,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
    need(read(STATE)==before,'Concurrent ledger write; no overwrite')
    os.replace(q,STATE)
def table():
    p=subprocess.run(['ps','-axo','pid=,ppid=,pgid=,lstart=,rss=,args='],capture_output=True,text=True,timeout=.2)
    need(p.returncode==0,'Process census failed: '+p.stderr)
    rows=[]
    for line in p.stdout.splitlines():
        a=line.split(None,9);need(len(a)==10,'Malformed process census')
        rows.append(dict(pid=int(a[0]),ppid=int(a[1]),pgid=int(a[2]),start_time=' '.join(a[3:8]),rss_bytes=int(a[8])*1024,argv=shlex.split(a[9])))
    return rows
plan=None;registration=None;process=None;child=None;groups={};t0=None;before_popen=None
signals=[];observer_errors=[];pool_until=None;outer_wait=None
result=dict(schema='long_D2_r2_observed_execution_v1',actual_command_launch_count=0,observer_pid=os.getpid(),observer_started_utc=utc(),observer_sha256=sha(__file__),teacher_qualified=False,training_parent_eligible=False,followon_authorized=False,lease_clearing_owner='parent',limits=dict(outer_seconds=7200,worker_seconds=7140,inner_seconds=7170,cleanup_seconds=10,latest_failure_seconds=7210,RSS_bytes=6442450944,MPS_bytes=6442450944,resource_interval_seconds=.05,lease_interval_seconds=.15,maximum_sample_gap_seconds=.5))
def observe():
    global t0
    rows=table();by={r['pid']:r for r in rows}
    def register(role,row):
        if row is None:return
        need(row['pgid']==row['pid'] and os.getsid(row['pid'])==row['pid'],'Owned session differs: '+role)
        if role not in groups:groups[role]=dict(row,new_session_verified=True,registered_monotonic=time.monotonic())
    row=by.get(process.pid)
    if row is not None:
        need(row['argv']==plan['command'] and row['ppid']==os.getpid(),'Outer command/parent differs')
        register('outer',row)
    exe=plan['command'][0];controller=registration['controller']
    for row in rows:
        a=row['argv']
        if a[:4]==[exe,'-B',controller,'run']:
            args=dict(zip(a[4::2],a[5::2]))
            if set(args)=={'--output','--state-path','--executor-fd','--executor-pid'} and args['--output']==registration['output'] and args['--state-path']==registration['state_path'] and args['--executor-pid']==str(process.pid) and args['--executor-fd'].isdigit() and row['ppid']==process.pid:register('supervisor',row)
    sup=groups.get('supervisor')
    if sup:
        for row in rows:
            a=row['argv']
            if a[:4]==[exe,'-B',controller,'worker']:
                args=dict(zip(a[4::2],a[5::2]))
                if set(args)=={'--output','--state-path','--started','--supervisor-pid','--executor-fd','--executor-pid'} and args['--output']==registration['output'] and args['--state-path']==registration['state_path'] and args['--supervisor-pid']==str(sup['pid']) and args['--executor-pid']==str(process.pid) and args['--executor-fd'].isdigit() and row['ppid']==sup['pid']:
                    clock=float(args['--started']);need(math.isfinite(clock) and before_popen<=clock<=time.monotonic(),'Inherited T0 invalid')
                    need(t0 is None or t0==clock,'Inherited T0 changed');t0=clock;register('worker',row)
    for role,g in groups.items():
        row=by.get(g['pid'])
        if row is not None:need(all(row[k]==g[k] for k in ('argv','pgid','start_time')),'Owned identity changed: '+role)
    selected=[dict(r,role=role) for role,g in groups.items() for r in rows if r['pgid']==g['pgid']]
    emit('process-observations.jsonl',dict(utc=utc(),monotonic=time.monotonic(),elapsed_seconds=time.monotonic()-before_popen,owned=selected,t0_monotonic_hex=None if t0 is None else t0.hex()))
    return rows

def signal_owned(role,number,reason):
    g=groups.get(role)
    if g is None:return
    rows=table();row=next((r for r in rows if r['pid']==g['pid']),None)
    if row is None:
        emit('signals.jsonl',dict(role=role,signal=number,forwarded=False,reason='leader_absent_identity_not_current',monotonic=time.monotonic()));return
    need(all(row[k]==g[k] for k in ('argv','pgid','start_time')) and os.getsid(g['pid'])==g['pid'],'Signal ownership revalidation failed')
    event=dict(role=role,pid=g['pid'],pgid=g['pgid'],signal=number,reason=reason,monotonic=time.monotonic(),utc=utc(),record_precedes_forward=True)
    emit('signals.jsonl',event)
    with (OUT/'signals.jsonl').open('a') as f:f.flush();os.fsync(f.fileno())
    try:os.killpg(g['pgid'],number)
    except ProcessLookupError:pass

def delivered(number,frame):signals.append(dict(signal=number,monotonic=time.monotonic(),utc=utc()))
for number in (signal.SIGINT,signal.SIGTERM):signal.signal(number,delivered)

def tighten():
    global pool_until
    candidates=[]
    for path in (Path(registration['receipt']),Path(registration['output'])/'long-run-result.json',Path(registration['output'])/'long-worker-result.json',Path(registration['output'])/'finalization-result.json'):
        if not path.is_file():continue
        try:v=read(path)
        except (ValueError,OSError):continue
        if type(v.get('cleanup_until_monotonic')) in (int,float):candidates.append(v['cleanup_until_monotonic'])
        for key in ('first_global_failure','first_local_failure'):
            d=v.get(key)
            if isinstance(d,dict) and type(d.get('timestamp')) in (int,float):candidates.append(d['timestamp']+10)
        if type(v.get('first_failure_monotonic')) in (int,float):candidates.append(v['first_failure_monotonic']+10)
    if t0 is not None:candidates.append(t0+7210)
    if candidates:pool_until=min([x for x in candidates if math.isfinite(x)]+([] if pool_until is None else [pool_until]))

try:
    save('read-only-lookup-notes.json',dict(recovered=["Initial rg inventory honored ignore rules and returned no helpers; explicit frozen paths and --no-ignore recovered inventory.","Broad state/source output exceeded display budget; focused reads recovered current contracts."],source_changes=False))
    need(sha(PLAN)==PLAN_SHA,'Execution plan SHA mismatch');plan=read(PLAN)
    acceptance=read(ROOT/plan['acceptance']);inv=read(ROOT/plan['invocation'])
    for key in ('acceptance','invocation','registration'):need(sha(ROOT/plan[key])==plan[key+'_sha256'],key+' SHA mismatch')
    for key in ('review_reconciliation','validation_result'):need(sha(ROOT/acceptance[key])==acceptance[key+'_sha256'],key+' SHA mismatch')
    review=read(ROOT/acceptance['review_reconciliation']);validation=read(ROOT/acceptance['validation_result'])
    need(review['verdict']=='accepted_no_findings_source_and_synthetic_only' and review['registered_runtime_stages_passed'] is True and review['immutable_review_inputs_rehashed']==1477 and review['review_outputs_rehashed']==38,'Parent reconciliation differs')
    need(validation['current_unit_methods_passed']==143 and validation['OS_cases_passed']==15 and all(x['raw_exit']==0 for x in validation['stages'].values()),'Current validation differs')
    need(acceptance['status']=='parent_accepted_r14_for_exactly_one_authorized_7200s_D2_experiment' and acceptance['campaign_invocations_before_acceptance']==0,'Acceptance authority differs')
    need(plan['command']==inv['argv'] and plan['cwd']==inv['cwd']==str(CAPSULE) and plan['environment']==inv['environment'] and plan['unset_environment']==inv['unset_environment'],'Invocation differs')
    need(plan['one_invocation_only'] and plan['normal_max_seconds']==7200 and plan['latest_failure_deadline_seconds']==7210,'Plan limits differ')
    pins=read(PREP/'parent-frozen-pins.json');need(pins==acceptance['parent_frozen_pins']==validation['parent_frozen_pins'],'Parent pins differ');check(pins)
    registration=read(ROOT/plan['registration']);check(registration['pins'])
    need(registration['class_counts']==dict(B=253,R=37,A=9998),'Class counts differ')
    sys.path.insert(0,str(HELPERS))
    import long_d2 as c, processes as owned, long_d2_executor as executor
    need(executor.checked_registration(ROOT/plan['registration'],CAPSULE)==registration,'Frozen registration differs')
    context=c.capsule_context(CAPSULE);protocol,config,base,identity,bindings,lease=context
    need(lease==plan['required_lease']==acceptance['required_lease']==read(PREP/'required-lease.json'),'Required lease differs')
    state=read(STATE);c.assert_lease(STATE,lease)
    need(state['scheduler_enabled'] is False and state['scheduler_next_run_at'] is None,'Scheduler enabled')
    entry=state['post_overnight_long_D2_r2'];need(entry.get('actual_command_launch_count',0)==0 and entry['single_use_consumed'] is False and entry['campaign_launched'] is False and entry['current_source_owner']=='frozen;no_writer','Single-use reservation differs')
    all_pins=dict(bindings);all_pins.update({str(ROOT/k):v for k,v in pins.items()})
    for label,name in (('R','native-manifest.json'),('A','archive-manifest.json')):
        m=read(HELPERS/name);need(sha(HELPERS/name)==registration['class_manifest_hashes'][label],label+' manifest differs');check(m['files']);all_pins.update(m['files'])
    need(sha(ROOT/acceptance['no_writer_reservation'])==registration['reservation_sha256'],'No-writer reservation differs')
    d1=state['M3_implementation']['D1'];anchor=lease['parent_terminal_receipt']
    need(anchor==protocol['parent_terminal_receipt']==identity['parent_terminal_receipt']==d1['parent_terminal_receipt'],'Eligible D1 terminal anchor differs')
    need(d1['status']=='accepted_D1_progress_only' and d1['supervisor_exit_code']==anchor['supervisor_exit_code']==0,'D1 not accepted')
    need(sha(ROOT/plan['training_parent'])==plan['training_parent_sha256']==anchor['checkpoint_sha256']==d1['candidate_sha256'],'D1 checkpoint differs')
    for field in ('run_result','identity','config'):need(sha(ROOT/d1[field])==anchor[field+'_sha256'],'D1 '+field+' differs')
    candidate=ROOT/plan['training_parent'];need(sha(candidate.with_name(candidate.stem+'-D1-development.jsonl'))==anchor['evaluation_sha256'],'D1 evaluation differs')
    env=dict(os.environ);env.update(plan['environment'])
    for k in plan['unset_environment']:env.pop(k,None)
    for k,v in registration['cache_policy']['environment'].items():need(env.get(k)==v,'Registered runtime environment differs: '+k)
    cache=Path(registration['cache_policy']['pycache_prefix']);need(cache.is_dir() and not cache.is_symlink() and not any(cache.iterdir()),'Production cache not empty')
    need(not any(n in ('torch','numpy','dodge_rl') or n.startswith(('torch.','numpy.','dodge_rl.')) for n in sys.modules),'Observer imported ML/project')
    need(time.monotonic()-START<600,'Observer preparation cap exceeded')
    save('sourcehashes-before.json',all_pins);save('state-before.json',state)
    save('command.json',dict(argv=plan['command'],cwd=plan['cwd'],environment=plan['environment'],unset_environment=plan['unset_environment'],observer_sha256=sha(__file__),plan_sha256=sha(PLAN),registration_sha256=sha(ROOT/plan['registration']),effective_environment_sha256=c.semantic_hash(env)))
    # No validation campaign or pilot is invoked here.
    need(not any(Path(p).exists() for p in plan['immutable_command_outputs']),'Registered output already exists')
    c.assert_lease(STATE,lease);need(read(STATE)['scheduler_enabled'] is False,'Scheduler changed')
    save('prelaunch-verification.json',dict(status='passed',utc=utc(),verified_bindings=len(all_pins),class_counts=registration['class_counts'],D1_anchor=anchor,ML_imports=False,production_cache_empty=True))
    with (OUT/'outer.stdout.log').open('x') as stdout,(OUT/'outer.stderr.log').open('x') as stderr:
        c.assert_lease(STATE,lease);need(not any(Path(p).exists() for p in plan['immutable_command_outputs']),'Output appeared before Popen')
        marker=dict(actual_command_launch_count=1,single_use_consumed=True,campaign_launched=True,launch_attempt_at_utc=utc(),status='launch_attempt_1_registered_before_Popen')
        ledger(marker,dict(latest_progress=marker),'postovernight_long_D2_r2_launch_attempt_1')
        result['actual_command_launch_count']=1
        save('invocation-attempt-1.json',dict(marker,argv=plan['command'],cwd=plan['cwd']))
        before_popen=time.monotonic();save('Popen-before.json',dict(monotonic=before_popen,utc=utc(),parent_pid=os.getpid()))
        process=subprocess.Popen(plan['command'],cwd=plan['cwd'],env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        child=owned.Child(process);save('Popen-returned.json',dict(pid=process.pid,parent_pid=os.getpid(),returned_monotonic=time.monotonic(),session=os.getsid(process.pid)))
        last_observe=0;last_update=0;cancel_at=None;kill_attempted=False
        while True:
            outer_wait=child.poll()
            if outer_wait is not None:break
            now=time.monotonic()
            try:
                if now-last_observe>=.5:observe();last_observe=now
                tighten()
                if signals:
                    for event in signals:
                        emit('delivered-signals.jsonl',event)
                        if cancel_at is None:cancel_at=event['monotonic']
                        pool_until=min(pool_until or before_popen+7210,event['monotonic']+10,before_popen+7210)
                        signal_owned('outer',event['signal'],'delivered_observer_cancellation')
                    signals.clear()
                if now>=before_popen+7200 and cancel_at is None:
                    cancel_at=now;pool_until=min(pool_until or before_popen+7210,now+10,before_popen+7210)
                    signal_owned('outer',signal.SIGTERM,'observed_outer_wall_limit')
                if now-last_update>=30:
                    progress=dict(elapsed_seconds=now-before_popen,pid=process.pid,roles=list(groups),t0_monotonic_hex=None if t0 is None else t0.hex(),cleanup_until_monotonic=pool_until,status='attached_running')
                    save('progress.json',progress,replace=True);print(json.dumps(progress),flush=True);last_update=now
                if pool_until is not None and now>=pool_until-.5 and cancel_at is not None and not kill_attempted:
                    kill_attempted=True
                    for role in ('worker','supervisor','outer'):signal_owned(role,signal.SIGKILL,'existing_shared_deadline_final_bound')
                if pool_until is not None and now>=pool_until and cancel_at is not None:result['deadline_exceeded']=True
            except BaseException as error:
                observer_errors.append(dict(error=repr(error),at_monotonic=time.monotonic(),traceback=traceback.format_exc()));emit('observer-errors.jsonl',observer_errors[-1])
                if cancel_at is None:
                    cancel_at=observer_errors[-1]['at_monotonic'];pool_until=min(pool_until or before_popen+7210,cancel_at+10,before_popen+7210)
                    try:signal_owned('outer',signal.SIGTERM,'observer_error')
                    except BaseException as e:emit('observer-errors.jsonl',dict(error=repr(e),phase='exact_owned_cancel'))
            time.sleep(.02)
    wall=outer_wait['observed_monotonic']-before_popen
    owned.validate_report(outer_wait,process.pid,os.getpid(),before_popen,time.monotonic())
    save('raw-wait.json',dict(report=outer_wait,Popen_before_monotonic=before_popen,observed_reap_wall_seconds=wall,reaped_utc=utc()))
    result.update(raw_exit=outer_wait['returncode'],raw_wait_status=outer_wait['raw_wait_status'],observed_wall_seconds=wall,outer_wait=outer_wait,t0_monotonic_hex=None if t0 is None else t0.hex(),observer_errors=observer_errors)
except BaseException as error:
    result.update(error=repr(error),traceback=traceback.format_exc(),status='prelaunch_blocked' if process is None else 'observer_failed',Popen_returned=process is not None)
    save('failure-evidence.json',result)
    if process is not None and (child is None or child.report is None):
        # This branch is only for setup failure immediately after successful Popen.
        child=child or owned.Child(process)
        at=time.monotonic();pool_until=min(pool_until or before_popen+7210,at+10,before_popen+7210)
        try:observe();signal_owned('outer',signal.SIGTERM,'postlaunch_observer_setup_failure')
        except BaseException as e:emit('observer-errors.jsonl',dict(error=repr(e)))
        while child.poll() is None:
            if time.monotonic()>=pool_until-.5:
                for role in ('worker','supervisor','outer'):
                    try:signal_owned(role,signal.SIGKILL,'existing_shared_deadline')
                    except BaseException:pass
                break
            time.sleep(.02)
        while child.poll() is None:
            result['deadline_exceeded']=True;time.sleep(.1)
        outer_wait=child.report;result.update(outer_wait=outer_wait,raw_exit=outer_wait['returncode'],observed_wall_seconds=outer_wait['observed_monotonic']-before_popen)
# Postflight uses no ML imports. It does not signal or grant another cleanup window.
post_start=time.monotonic()
try:
    if process is not None and outer_wait is not None:
        receipt_path=Path(registration['receipt']);receipt=read(receipt_path) if receipt_path.is_file() else None
        absence={}
        for role,g in groups.items():absence[role]=dict(pid=g['pid'],pgid=g['pgid'],group_absent=owned.absent(g['pgid'],time.monotonic()+.2),identity=g)
        if receipt:
            for role,g in receipt.get('ownership',{}).items():
                absence.setdefault(role,dict(pid=g['pid'],pgid=g['pgid'],group_absent=owned.absent(g['pgid'],time.monotonic()+.2),identity_source='frozen_executor_receipt',identity=g))
        save('postflight-owned-absence.json',absence)
        stable=bool(absence) and all(x['group_absent'] for x in absence.values())
        result['owned_groups_positive_absence']=stable;result['receipt_present']=receipt is not None
        current={};mismatches={}
        for p,d in read(OUT/'sourcehashes-before.json').items():
            actual=sha(p);current[p]=actual
            if actual!=d:mismatches[p]=dict(expected=d,actual=actual)
        save('current-input-hashes.json',dict(current=current,mismatches=mismatches))
        summary_path=receipt_path.parent/'integrity-summary.json';summary_digest=sha(summary_path) if summary_path.is_file() else None
        accepted=executor.accept_observed(receipt or {},outer_wait['returncode'],result['observed_wall_seconds'],registration_sha256=plan['registration_sha256'],summary_sha256=summary_digest)
        result.update(frozen_accept_observed=accepted,mandatory_integrity_summary_sha256=summary_digest,current_input_mismatches=mismatches,status='complete' if accepted and stable and not mismatches and not observer_errors else 'failed',command_receipt=receipt,qualification_status='teacher_unqualified_no_automatic_followon')
        inventories={}
        for directory in map(Path,plan['immutable_command_outputs']):
            inventories[str(directory)]={str(p.relative_to(directory)):dict(sha256=sha(p),size_bytes=p.stat().st_size) for p in sorted(directory.rglob('*')) if p.is_file() and not p.is_symlink()}
        save('command-artifact-inventory.json',dict(stable_after_owned_absence=stable,partial=not stable,artifacts=inventories))
        campaign=Path(registration['output']);metrics={}
        for name in ('entry-restoration.json','entry-control.json','parent-lineage.json','checkpoint-index.json','long-worker-result.json','long-run-result.json','finalization-result.json'):
            path=campaign/name
            if path.is_file():metrics[name]=read(path)
        evaluations={}
        for path in campaign.glob('*.long-evaluation.json'):
            cert=read(path);evaluations[path.name]=cert
        save('actual-metrics.json',dict(receipts=metrics,evaluations=evaluations,checkpoint_decoding=False))
        result['metrics_evidence']=str(OUT/'actual-metrics.json');result['artifact_inventory']=str(OUT/'command-artifact-inventory.json')
        result['primary_failure']=None if not receipt else receipt.get('first_global_failure') or receipt.get('error')
        result['postflight_seconds']=time.monotonic()-post_start
        need(result['postflight_seconds']<=600,'Postflight cap exceeded')
    result['finished_at_utc']=utc();result['lease_retained']=read(STATE)['active_long_campaign']==plan['required_lease'] if plan else None
    if plan:
        ledger(dict(status=result['status'],execution_finished_at_utc=utc(),actual_command_launch_count=result['actual_command_launch_count']),dict(status='completed',latest_progress=dict(status=result['status'],result=str(OUT/'execution-result.json'),raw_exit=result.get('raw_exit'),observed_wall_seconds=result.get('observed_wall_seconds'))),'postovernight_long_D2_r2_observer_terminal_parent_audit_pending')
except BaseException as error:
    result['postflight_error']=repr(error);result['postflight_traceback']=traceback.format_exc();result['status']='failed'
save('execution-result.json',result)
save('observer-artifact-manifest.json',{p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='observer-artifact-manifest.json'})
print(json.dumps({k:result.get(k) for k in ('status','actual_command_launch_count','raw_exit','observed_wall_seconds','frozen_accept_observed','error','postflight_error')}),flush=True)
