import datetime, hashlib, json, os, signal, subprocess, sys, time
from pathlib import Path

ROOT=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
OWN=ROOT/'learning/runs/v2/D2-gradient-execution-observer-20261025-r2'
PREP=ROOT/'learning/runs/v2/D2-gradient-campaign-parent-authorization-20261025-r2'
REG=ROOT/'learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/registration-proposed.json'; PIN=PREP/'registration-pin.json'; ACCEPT=PREP/'parent-acceptance.json'
SHA='6f4adf808789655a663800a1e4a0613192d02b0c8287d121455ea748fe043916'
LIMIT=1800.0; RSS_LIMIT=6442450944
start_mono=time.monotonic(); start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
first_event=None; proc=None; record={'observer_started_utc':start_utc,'observer_started_monotonic':start_mono,'launch_count':0,'command':None,'registration_sha256':SHA,'outer_timeout_seconds':LIMIT,'aggregate_rss_limit_bytes':RSS_LIMIT,'samples_file':'resources.jsonl','cancel_path':None,'events':[]}
def save(n,v): (OWN/n).write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def sha(b): return hashlib.sha256(b).hexdigest()
def psall():
 r=subprocess.run(['/bin/ps','-axo','pid=,ppid=,pgid=,rss=,lstart=,command='],capture_output=True,text=True)
 if r.returncode: raise RuntimeError('ps failed: '+r.stderr)
 rows={}
 for line in r.stdout.splitlines():
  p=line.strip().split(None,9)
  if len(p)>=9:
   try: rows[int(p[0])]={'pid':int(p[0]),'ppid':int(p[1]),'pgid':int(p[2]),'rss_bytes':int(p[3])*1024,'start_identity':' '.join(p[4:9]),'command':p[9] if len(p)>9 else ''}
   except ValueError: pass
 return rows
def tree(rows,rootpid):
 found={rootpid}; changed=True
 while changed:
  changed=False
  for pid,row in rows.items():
   if row['ppid'] in found and pid not in found: found.add(pid); changed=True
 return [rows[p] for p in found if p in rows]
def write_event(kind,detail):
 global first_event
 if first_event is None:
  first_event={'kind':kind,'detail':detail,'monotonic':time.monotonic(),'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
  record['first_event']=first_event; save('observation.json',record)
def on_signal(signum,frame): write_event('observer_signal',signal.Signals(signum).name)
signal.signal(signal.SIGINT,on_signal); signal.signal(signal.SIGTERM,on_signal)
try:
 if OWN.exists() and any(p.name not in {'observe.py','observation.json'} for p in OWN.iterdir()): raise RuntimeError('observer output directory contains unexpected files')
 regb=REG.read_bytes(); reg=json.loads(regb); pin=json.loads(PIN.read_bytes()); acc=json.loads(ACCEPT.read_bytes())
 statep=Path(reg['state_path']); stateb=statep.read_bytes(); state=json.loads(stateb)
 out=Path(reg['output']); cache=Path(reg['import_policy']['pycache_prefix']); cancel=Path(reg['cancel_path'])
 command=pin['command']; expected=['/usr/bin/env','PYTHONPYCACHEPREFIX='+str(cache),reg['interpreter'],'-B',reg['launcher_path'],'--registration',str(REG),'--registration-sha256',SHA]
 checks={'registration_sha256':sha(regb),'pin_sha256':pin['sha256'],'accepted_registration_sha256':acc['registration_sha256'],'review_verdict':acc['review_verdict'],'pins_checked':pin['pins_checked'],'exact_command':command,'lease_exact':state.get('active_long_campaign')==reg['expected_lease'],'state_sha256_before':sha(stateb),'output_absent':not os.path.lexists(out),'cache_prefix':str(cache),'cache_empty_before':cache.is_dir() and not any(cache.iterdir()),'cancel_path_absent':not os.path.lexists(cancel),'run_seed':reg['run_seed'],'limits':reg['limits'],'observer_started_monotonic':start_mono,'observer_started_utc':start_utc}
 record.update(prelaunch=checks,cancel_path=str(cancel),command=command)
 save('prelaunch.json',checks)
 assert checks['registration_sha256']==SHA and pin['sha256']==SHA and acc['registration_sha256']==SHA
 assert acc['review_verdict']=='no_blocking_findings' and pin['pins_checked']==13724
 assert checks['lease_exact'] and checks['output_absent'] and checks['cache_empty_before'] and checks['cancel_path_absent']
 assert reg['run_seed']==810631976 and reg['limits']=={'MPS_bytes':RSS_LIMIT,'RSS_bytes':RSS_LIMIT,'eval_updates':[132,180],'max_updates':48,'retries':0,'total_seconds':1800,'work_seconds':1600}
 assert command==expected and not first_event
 with (OWN/'stdout.log').open('xb') as stdout,(OWN/'stderr.log').open('xb') as stderr,(OWN/'resources.jsonl').open('x') as samples:
  command_start=time.monotonic(); command_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
  proc=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,env=os.environ.copy())
  record.update(launch_count=1,outer_pid=proc.pid,command_started_monotonic=command_start,command_started_utc=command_utc)
  rows=psall(); own=tree(rows,proc.pid); rootrow=rows.get(proc.pid)
  record['outer_initial_identity']=rootrow
  save('launch.json',record)
  maxrss=0; maxsample=None; deadline=start_mono+LIMIT; code=None; killed=[]
  while True:
   now=time.monotonic()
   if first_event is None and os.path.lexists(cancel): write_event('cancel_marker',str(cancel))
   code=proc.poll()
   rows=psall(); own=tree(rows,proc.pid)
   rss=sum(x['rss_bytes'] for x in own)
   sample={'monotonic':now,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elapsed_since_observer_start':now-start_mono,'elapsed_since_command_start':now-command_start,'outer_pid':proc.pid,'owned_processes':own,'aggregate_rss_bytes':rss}
   wl=out/'worker-launch.json'
   if wl.is_file():
    try:
     worker=json.loads(wl.read_bytes()); sample['worker_launch']=worker
     wpid=worker.get('worker_pid'); wrow=rows.get(wpid)
     sample['worker_process']=wrow
     if wrow: sample['worker_start_identity']=wrow['start_identity']
    except Exception as e: sample['worker_observation_error']=repr(e)
   samples.write(json.dumps(sample,sort_keys=True)+'\n'); samples.flush()
   if rss>maxrss: maxrss=rss; maxsample=sample
   record.update(max_aggregate_rss_bytes=maxrss,max_rss_sample=maxsample)
   if rss>RSS_LIMIT: write_event('aggregate_rss_limit_exceeded',{'bytes':rss,'limit':RSS_LIMIT})
   if now>=deadline: write_event('inclusive_1800s_deadline',{'elapsed':now-start_mono})
   if first_event and proc.poll() is None:
    try: proc.terminate(); killed.append({'target':'owned_outer_pid','pid':proc.pid,'signal':'SIGTERM','time':time.monotonic()})
    except ProcessLookupError: pass
    try: code=proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
     # Direct worker cleanup only when launcher metadata and PID start identity still match.
     try:
      w=json.loads(wl.read_bytes()); wpid=w['worker_pid']; before=rows.get(wpid); after=psall().get(wpid)
      if before and after and before['start_identity']==after['start_identity'] and before['command']==after['command'] and after['pgid']==w['owned_pgid']==wpid:
       os.kill(wpid,signal.SIGTERM); killed.append({'target':'owned_worker_pid','pid':wpid,'signal':'SIGTERM','time':time.monotonic()})
       try: code=proc.wait(timeout=5)
       except subprocess.TimeoutExpired:
        after=psall().get(wpid)
        if after and after['start_identity']==before['start_identity']:
         os.kill(wpid,signal.SIGKILL); killed.append({'target':'owned_worker_pid','pid':wpid,'signal':'SIGKILL','time':time.monotonic()})
        try: code=proc.wait(timeout=5)
        except subprocess.TimeoutExpired: code=proc.poll()
      else: code=proc.poll()
     except (FileNotFoundError,KeyError,ProcessLookupError,ValueError): code=proc.poll()
    if code is not None: break
   if code is not None: break
   time.sleep(min(1.0,max(0.02,deadline-now)))
  if code is None:
   write_event('outer_not_reaped_after_bounded_cleanup',{})
   raise RuntimeError('owned outer process did not exit after bounded cleanup')
  code=proc.wait()
  command_end=time.monotonic(); command_end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
  record.update(outer_raw_exit=code,command_ended_monotonic=command_end,command_ended_utc=command_end_utc,inclusive_process_wall_seconds=command_end-command_start,observer_inclusive_wall_seconds=command_end-start_mono,directly_reaped=True,cleanup_signals=killed,max_aggregate_rss_bytes=maxrss,max_rss_sample=maxsample)
 # postflight evidence and absence observations
 rows=psall(); outer=rows.get(record['outer_pid']); record['outer_terminal_process']=outer
 record['outer_process_absent']=outer is None
 out=Path(reg['output']); cache=Path(reg['import_policy']['pycache_prefix']); statep=Path(reg['state_path'])
 for name in ('launch-marker.json','worker-launch.json','execution-result.json','worker-result.json','publication-failure.json','training-metrics.jsonl','checkpoint-000180-candidate.pt'):
  p=out/name
  if p.is_file():
   if p.suffix=='.json':
    try: record[name]=json.loads(p.read_bytes())
    except Exception as e: record[name]={'read_error':repr(e)}
   elif name.endswith('.jsonl'):
    try: record['metrics_summary']=[json.loads(x) for x in p.read_text().splitlines()]
    except Exception as e: record['metrics_read_error']=repr(e)
   else: record['candidate_sha256']=sha(p.read_bytes())
 workerlaunch=record.get('worker-launch.json',{})
 if workerlaunch.get('worker_pid'):
  pinfo=psall().get(workerlaunch['worker_pid']); record['worker_terminal_process']=pinfo
  record['worker_process_absent']=pinfo is None
  record['worker_group_absent_observed']=not any(x['pgid']==workerlaunch['owned_pgid'] for x in psall().values())
 record['publication_failure_present']=os.path.lexists(out/'publication-failure.json')
 record['cache_prefix_empty_after']=cache.is_dir() and not any(cache.iterdir())
 stateb=statep.read_bytes(); state=json.loads(stateb); record['state_sha256_after']=sha(stateb); record['lease_still_exact']=state.get('active_long_campaign')==reg['expected_lease']
 record['outer_exit_and_wall_accepted']=record.get('outer_raw_exit')==0 and record.get('inclusive_process_wall_seconds',LIMIT+1)<=LIMIT and first_event is None
 record['worker_exit_accepted']=record.get('execution-result.json',{}).get('observed_worker_raw_exit')==0
 record['success_authoritative']=record['outer_exit_and_wall_accepted'] and record['worker_exit_accepted'] and not record['publication_failure_present'] and record.get('outer_process_absent') and record.get('worker_process_absent') and record.get('worker_group_absent_observed') and record.get('cache_prefix_empty_after') and record.get('lease_still_exact')
 record['observer_ended_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat(); record['observer_ended_monotonic']=time.monotonic()
 save('observation.json',record)
 print(json.dumps({'outer_raw_exit':record.get('outer_raw_exit'),'worker_raw_exit':record.get('execution-result.json',{}).get('observed_worker_raw_exit'),'wall_seconds':record.get('inclusive_process_wall_seconds'),'max_aggregate_rss_bytes':record.get('max_aggregate_rss_bytes'),'success_authoritative':record.get('success_authoritative'),'first_event':first_event},sort_keys=True),flush=True)
except BaseException as error:
 record.update(observer_error=repr(error),observer_ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),observer_ended_monotonic=time.monotonic(),first_event=first_event)
 try: save('observation.json',record)
 except Exception: pass
 print(json.dumps({'observer_error':repr(error),'first_event':first_event},sort_keys=True),file=sys.stderr,flush=True)
 raise
