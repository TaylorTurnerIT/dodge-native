"""Self-contained fail-closed parent supervisor. No evaluator/native import here."""
from __future__ import annotations
import argparse, hashlib, json, os, signal, subprocess, sys, time, uuid
from pathlib import Path

CAP=6*1024**3; CLEANUP=10; POLL=.2; START_GRACE=12; VERIFY_FROZEN_RUNTIME=True; VERIFY_PROPOSAL_CANDIDATES=True
NATIVE_REL='dodge_rl/_native.cpython-312-darwin.so'
NATIVE_SHA='022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e'
PROPOSAL_PATH=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/expanded-evaluation-registration-proposal-parent-20261026-r5/proposal.json')
PROPOSAL_SHA='187e0464ba966b29124b29cf606c831d7097adeea99ccfc0e336598ad3fc9765'
TRAINING_REG=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-integrated-luna-20261026-r4/registration-final-r2.json')
TRAINING_REG_SHA='0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e'
BENCHMARK_MANIFEST=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/expanded-eval-parent-integration-20261026-r1/benchmark-dev64-seed-manifest.json')
BENCHMARK_MANIFEST_SHA='a57410e1848f8b35b874507afa21a4d90ced706efd3bd7a141e1dc3ad5df3695'
GOLDEN_PATH=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-lr-20261026-r1/development-000348.jsonl')
GOLDEN_SHA='d6e914345dcc955f678db41eb08d9f20af8e77490652f8d25f7ee09550a63a03'
RANKING_FRAMES=110592000
CONFIRMATION_FRAMES=73728000
class PreflightError(RuntimeError): pass
class SupervisorSignal(BaseException):
 def __init__(self,signum):self.signum=signum

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def read(path): return json.loads(Path(path).read_text())
def atomic_json(path,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+f'.{os.getpid()}.{uuid.uuid4().hex}.tmp')
 fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'w') as f:json.dump(obj,f,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
 os.link(tmp,p);tmp.unlink()
def require_hash(path,pin,label):
 if not isinstance(pin,str) or len(pin)!=64 or sha(path)!=pin: raise PreflightError(label+' hash mismatch')
def active_procs(pid):
 try:
  out=subprocess.run(['ps','-axo','pid=,pgid=,rss='],capture_output=True,text=True,timeout=0.2,check=True).stdout
  rows=[]
  for line in out.splitlines():
   a=line.split()
   if len(a)==3 and int(a[1])==pid:rows.append((int(a[0]),int(a[2])*1024))
  return rows
 except Exception as e: raise RuntimeError('cannot sample actual owned process group RSS') from e
def sample_procs(pid):
 try:return active_procs(pid),None
 except Exception as e:return None,'process_group_sampling_failed:'+str(e)
def sample_procs(pid):
 try:return active_procs(pid),None
 except Exception as e:return None,'process_group_sampling_failed:'+str(e)
def aggregate_rss(pid):
 rows=active_procs(pid)
 if not rows:return 0,[]
 return sum(x[1] for x in rows),rows
def mps_from_heartbeat(path,proc_pid,reg):
 if not path.exists(): return None
 h=read(path)
 if h.get('run_id')!=reg['run_id'] or h.get('registration_sha256')!=reg['_external_registration_sha256'] or h.get('pid')!=proc_pid: raise RuntimeError('worker heartbeat identity mismatch')
 age=(time.time_ns()-int(h['timestamp_ns']))/1e9
 if age>float(reg['limits']['heartbeat_stale_seconds']): raise RuntimeError('worker heartbeat stale')
 for key in ('rss_bytes','mps_driver_bytes','sequence'):
  if key not in h or not isinstance(h[key],int): raise RuntimeError('worker heartbeat missing '+key)
 return h['mps_driver_bytes'],h

def check_mode(reg,stage,update,cohort,output):
 if reg.get('schema')!='expanded_D2_evaluation_registration_v1' or reg.get('mode')!=stage: raise PreflightError('registration schema/mode mismatch')
 expected={'schema','run_id','mode','source','runtime','candidates','cohorts','selection_record','limits','output_dir','cancel_path','one_shot_marker','state_path','expected_lease','review_records','benchmark_reference'}
 optional={'provenance','benchmark_measurement','observer'}
 if set(reg)-expected-optional or not expected.issubset(reg): raise PreflightError('registration top-level field set differs from evaluator interface')
 if reg.get('run_id') in (None,'','PENDING_PARENT_UNIQUE_RUN_ID'):raise PreflightError('parent unique run_id required')
 expected={'benchmark':(348,'benchmark_dev64'),'ranking':(None,'ranking'),'confirmation':(None,'confirmation')}[stage]
 if expected[0] is not None and update!=expected[0] or cohort!=expected[1]: raise PreflightError('mode/update/cohort mismatch')
 if Path(output).resolve().parent!=Path(reg['output_dir']).resolve(): raise PreflightError('output outside registered output directory')
 planned=[Path(output)]
 receipt_path=Path(output).with_suffix(Path(output).suffix+'.outer-receipt.json')
 planned.append(receipt_path)
 if stage=='benchmark': planned += [Path(output).with_name(Path(output).stem+f'-repeat-{i}'+Path(output).suffix) for i in (1,2)]
 elif stage=='ranking': planned += [Path(output).with_name(Path(output).stem+f'-candidate-{k}'+Path(output).suffix) for k in sorted(reg.get('candidates',{}),key=int)]
 elif stage=='confirmation': planned += [Path(output).with_name(Path(output).stem+'-winner'+Path(output).suffix),Path(output).with_name(Path(output).stem+'-incumbent-348'+Path(output).suffix)]
 if len({str(x.resolve()) for x in planned})!=len(planned) or any(x.exists() for x in planned): raise PreflightError('planned evaluator output or outer receipt exists or collides')
 if Path(reg['one_shot_marker']).exists(): raise PreflightError('one-shot marker already exists')
 if Path(output).exists(): raise PreflightError('stage output already exists')


def certificate_rows(path):
 p=Path(path)
 if p.suffix=='.jsonl':return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
 d=read(p);return d.get('evaluation',d).get('rows',[])
def validate_throughput_receipt(reg):
 refs=[x for x in reg.get('review_records',[]) if x.get('kind')=='old_dev64_benchmark_receipt']
 if len(refs)!=1:raise PreflightError('one byte-pinned successful old-dev64 receipt required')
 d=read(refs[0]['path']);reps=d.get('repeats')
 if d.get('schema')!='expanded_eval_dev64_benchmark_receipt_v1' or d.get('candidate_update')!=348 or d.get('cohort_name')!='benchmark_dev64':raise PreflightError('benchmark receipt identity differs')
 if d.get('complete') is not True or not isinstance(reps,list) or len(reps)!=2:raise PreflightError('old-dev64 receipt must prove two successful repeats')
 raw=elapsed=0
 golden={x['seed']:x for x in certificate_rows(GOLDEN_PATH)}
 fields=('seed','episode_index','alive_frames','gameplay_frames','score_raw_fixed','score','objective_return','terminated','truncated','death_cause','fatal_gameplay_frame','death_observed_lethal_contacts')
 seen=[]
 for r in reps:
  if r.get('candidate_update')!=348 or r.get('cohort_name')!='benchmark_dev64':raise PreflightError('benchmark repeat identity differs')
  if r.get('complete') is not True or len(r.get('rows',[]))!=64 or not isinstance(r.get('raw_frames'),int) or r['raw_frames']<=0 or not isinstance(r.get('elapsed_seconds'),(int,float)) or r['elapsed_seconds']<=0:raise PreflightError('old-dev64 repeat lacks actual rows, raw frames, or timing')
  if sum(int(x.get('alive_frames',-1)) for x in r['rows'])!=r['raw_frames'] or {x.get('seed') for x in r['rows']}!=set(range(0xD0000000,0xD0000040)):raise PreflightError('old-dev64 raw frame count or seed set differs from raw rows')
  by={x['seed']:x for x in r['rows']}
  if any(any(by[k].get(f)!=golden[k].get(f) for f in fields) for k in golden):raise PreflightError('benchmark repeat differs from accepted golden rows')
  seen.append(by);raw+=r['raw_frames'];elapsed+=float(r['elapsed_seconds'])
 if any(seen[0][k]!=seen[1][k] for k in golden):raise PreflightError('benchmark receipt repeats differ')
 cap=RANKING_FRAMES if reg['mode']=='ranking' else CONFIRMATION_FRAMES
 projected=2*elapsed/raw*cap+CLEANUP
 measure=reg.get('benchmark_measurement')
 if measure and (measure.get('receipt_path')!=refs[0]['path'] or measure.get('receipt_sha256')!=refs[0]['sha256'] or measure.get('raw_frames')!=raw or measure.get('elapsed_seconds')!=elapsed):raise PreflightError('benchmark measurement summary differs from pinned receipt')
 if reg['limits']['projection_multiplier']!=2.0:raise PreflightError('projection multiplier differs')
 expected_rank=__import__('math').ceil(2*elapsed/raw*RANKING_FRAMES+CLEANUP);expected_confirm=__import__('math').ceil(2*elapsed/raw*CONFIRMATION_FRAMES+CLEANUP)
 if reg['limits'].get('ranking_projected_work_seconds')!=expected_rank or reg['limits'].get('confirmation_projected_work_seconds')!=expected_confirm:raise PreflightError('registered full-cap projections differ from pinned measurements')
 if reg['limits']['work_seconds']!=__import__('math').ceil(projected) or reg['limits']['outer_seconds']!=reg['limits']['work_seconds']+CLEANUP:raise PreflightError('registered work budget underprojects full raw-frame cap')

def preflight(registration,registration_sha256,worker,evaluator,stage,update,cohort,output):
 rp=Path(registration); require_hash(rp,registration_sha256,'external registration');reg=read(rp)
 check_mode(reg,stage,update,cohort,output)
 if set(reg.get('candidates',{}))!={'180','204','276','300','324','348'}:raise PreflightError('exact six candidate inventory required')
 # All paths and outputs are validated before marker creation.
 src=reg.get('source') or {}
 for name,path in [('worker',worker),('evaluator',evaluator),('launcher',Path(__file__))]:
  require_hash(path,src.get(name+'_sha256'),name+' source')
  if Path(src.get(name+'_path','')).resolve()!=Path(path).resolve(): raise PreflightError(name+' path differs from registration')
 if not reg.get('expected_lease') or not reg.get('state_path'): raise PreflightError('parent lease and ledger binding absent')
 for key in ('cancel_path','one_shot_marker','state_path','output_dir'):
  if not Path(reg[key]).is_absolute():raise PreflightError(key+' must be absolute')
 if Path(reg['one_shot_marker']).resolve()==Path(reg['cancel_path']).resolve():raise PreflightError('marker and cancellation paths collide')
 state=read(reg['state_path']); lease=reg['expected_lease']
 if state.get('active_inference_diagnostic')!=lease: raise PreflightError('exact active inference lease absent')
 if state.get('active_long_campaign') not in (None,False): raise PreflightError('active long campaign exists')
 if state.get('active_inference_diagnostic')!=lease: raise PreflightError('active inference diagnostic lease differs')
 if state.get('active_inference') not in (None,False): raise PreflightError('other inference lease exists')
 if state.get('active_long') not in (None,False): raise PreflightError('legacy active long lease exists')
 if Path(reg['cancel_path']).exists(): raise PreflightError('cancel file exists')
 base_limits={'outer_seconds','work_seconds','cleanup_seconds','RSS_bytes','MPS_driver_bytes','guard_poll_seconds','heartbeat_stale_seconds'}
 extras={'startup_grace_seconds','ranking_projected_work_seconds','confirmation_projected_work_seconds','projection_multiplier'}
 if set(reg['limits'])-base_limits-extras or not base_limits.issubset(reg['limits']):raise PreflightError('registration limits fields differ from evaluator interface')
 if reg['limits'].get('projection_multiplier',2.0)!=2.0:raise PreflightError('projection multiplier must be 2')
 if float(reg['limits'].get('startup_grace_seconds',START_GRACE))>START_GRACE:raise PreflightError('startup grace exceeds bounded allowance')
 if not float(reg['limits']['outer_seconds'])>CLEANUP or float(reg['limits']['cleanup_seconds'])!=CLEANUP or float(reg['limits']['outer_seconds'])!=float(reg['limits']['work_seconds'])+CLEANUP: raise PreflightError('invalid wall/cleanup budget')
 if stage=='benchmark' and (reg['limits']['work_seconds']!=170 or reg['limits']['outer_seconds']!=180):raise PreflightError('benchmark budget must be fixed 170/180 seconds')
 if not 0<float(reg['limits']['guard_poll_seconds'])<=.2: raise PreflightError('guard poll must be positive and no slower than 0.2 seconds')
 if not 0<float(reg['limits']['heartbeat_stale_seconds'])<=5:raise PreflightError('heartbeat stale limit must be positive and bounded')
 if int(reg['limits']['RSS_bytes'])!=CAP or int(reg['limits']['MPS_driver_bytes'])!=CAP: raise PreflightError('resource caps mismatch')
 if Path(reg['output_dir']).exists() and any(Path(reg['output_dir']).iterdir()): raise PreflightError('registered output directory is not empty')
 rt=reg.get('runtime') or {};root=Path(rt.get('root') or '')
 # Candidate receipts and checkpoint bytes are immutable evaluator inputs.
 for update,candidate in reg.get('candidates',{}).items():
  require_hash(candidate.get('checkpoint_path',''),candidate.get('checkpoint_sha256'),'candidate '+update+' checkpoint')
  require_hash(candidate.get('source_receipt_path',''),candidate.get('source_receipt_sha256'),'candidate '+update+' receipt')
  receipt=read(candidate['source_receipt_path'])
  if receipt.get('status') not in {'accepted_complete_candidate_from_completed_normal_training_iteration','accepted_completed_normal_training_iteration'} or receipt.get('checkpoint_sha256')!=candidate['checkpoint_sha256'] or Path(receipt.get('checkpoint_path','')).resolve()!=Path(candidate['checkpoint_path']).resolve():raise PreflightError('candidate accepted receipt identity differs: '+update)
 if Path(rt.get('pycache_prefix','')).exists() and any(Path(rt['pycache_prefix']).iterdir()): raise PreflightError('registered pycache prefix must be empty')
 if set(reg.get('cohorts',{}))!={'benchmark_dev64','ranking','confirmation'}:raise PreflightError('exact three registered cohorts required')
 proposal=read(PROPOSAL_PATH);require_hash(PROPOSAL_PATH,PROPOSAL_SHA,'proposal source')
 training=read(TRAINING_REG);require_hash(TRAINING_REG,TRAINING_REG_SHA,'frozen training registration')
 frozen_runtime=training['runtime_continuity']
 if VERIFY_FROZEN_RUNTIME and (Path(rt['root']).resolve()!=Path(training['runtime_root']).resolve() or rt['member_sha256']!=frozen_runtime['member_sha256'] or rt['torch_version']!=training['runtime_versions']['torch'] or rt['numpy_version']!=training['runtime_versions']['numpy']):raise PreflightError('frozen runtime root/member/version inventory differs from training registration')
 proposal_candidates={str(x['phase_update']):x for x in proposal['candidates']}
 for update,entry in reg['candidates'].items():
  pin=proposal_candidates[update]
  if VERIFY_PROPOSAL_CANDIDATES and any(entry.get(k)!=pin.get(k) for k in ('phase_update','checkpoint_path','checkpoint_sha256','source_receipt_path','source_receipt_sha256')):raise PreflightError('candidate registration differs from proposal: '+update)
 for name,c in reg.get('cohorts',{}).items():
  p=c.get('manifest_path'); require_hash(p,c.get('manifest_sha256'),name+' manifest');m=read(p);seeds=m.get('seeds',[])
  if len(seeds)!=c.get('count') or m.get('count')!=c.get('count') or len(set(seeds))!=len(seeds) or seeds!=list(range(seeds[0],seeds[0]+len(seeds))):raise PreflightError(name+' manifest count/order mismatch')
  if name=='benchmark_dev64' and (Path(p).resolve()!=BENCHMARK_MANIFEST.resolve() or c.get('manifest_sha256')!=BENCHMARK_MANIFEST_SHA or seeds!=list(range(0xD0000000,0xD0000040))):raise PreflightError('benchmark manifest differs from parent pin')
  if name in ('ranking','confirmation'):
   expected_manifest=proposal['cohorts'][name]
   if Path(p).resolve()!=Path(expected_manifest['path']).resolve() or c['manifest_sha256']!=expected_manifest['sha256']:raise PreflightError(name+' manifest differs from proposal pin')
 if not reg.get('review_records'):raise PreflightError('external review records missing')
 if stage=='confirmation':
  from worker import validate_selection
  validate_selection(reg)
 for rr in reg.get('review_records',[]): require_hash(rr['path'],rr['sha256'],'review record')
 exe=[x for x in reg.get('review_records',[]) if x.get('kind')=='runtime_executable']
 if len(exe)!=1 or Path(exe[0]['path']).resolve()!=Path(sys.executable).resolve():raise PreflightError('externally pinned runtime executable differs from launcher Python')
 require_hash(exe[0]['path'],exe[0]['sha256'],'runtime executable')
 if stage in ('ranking','confirmation'):
  if not reg.get('benchmark_measurement'):raise PreflightError('byte-pinned benchmark measurement summary required')
  validate_throughput_receipt(reg)
  key='ranking_projected_work_seconds' if stage=='ranking' else 'confirmation_projected_work_seconds'
  if key in reg['limits'] and reg['limits']['work_seconds']<reg['limits'][key]:raise PreflightError('registered work seconds below projected cap')
 if not root.is_dir() or len(rt.get('member_sha256') or {})!=13: raise PreflightError('exact 13-member runtime inventory absent')
 if rt.get('native_relative_path')!=NATIVE_REL or rt['member_sha256'].get(NATIVE_REL)!=NATIVE_SHA or not (root/rt['native_relative_path']).is_file(): raise PreflightError('frozen native member pin mismatch')
 for k,p in rt['member_sha256'].items():require_hash(root/k,p,'runtime '+k)
 for k in ('backend','torch_version','numpy_version','pycache_prefix'):
  if not rt.get(k):raise PreflightError('runtime '+k+' missing')
 if not Path(rt['pycache_prefix']).is_absolute():raise PreflightError('pycache prefix not absolute')

 if stage=='benchmark':
  ref=reg.get('benchmark_reference') or {}
  if Path(ref.get('certificate_path','')).resolve()!=GOLDEN_PATH.resolve() or ref.get('certificate_sha256')!=GOLDEN_SHA:raise PreflightError('accepted 348 JSONL path/SHA differs from frozen pin')
  require_hash(ref.get('certificate_path',''),ref.get('certificate_sha256'),'accepted 348 benchmark certificate')
  rows=certificate_rows(ref['certificate_path'])
  if len(rows)!=64 or {r.get('seed') for r in rows}!=set(range(0xD0000000,0xD0000040)):raise PreflightError('accepted certificate must contain exact 348 64-row evidence')
 return reg

def execute_once(*,registration,registration_sha256,worker,evaluator,stage,candidate_update,cohort,output):
 rp=Path(registration);w=Path(worker);e=Path(evaluator);out=Path(output)
 # Real built-in checks always run before one-shot claim.
 reg=preflight(rp,registration_sha256,w,e,stage,candidate_update,cohort,out)
 reg['_external_registration_sha256']=registration_sha256
 marker=Path(reg['one_shot_marker']);atomic_json(marker,{'run_id':reg['run_id'],'registration_sha256':registration_sha256,'pid':os.getpid(),'timestamp_ns':time.time_ns()})
 start=time.monotonic(); outer=float(reg['limits']['outer_seconds']); deadline=start+outer-CLEANUP
 heartbeat=Path(reg['output_dir'])/'worker-heartbeat.json';log=Path(reg['output_dir'])/'worker.log'
 proc=None;reason=None;exit_code=None;rows=None;last=0;cleanup_attempted=False;receipt_path=out.with_suffix(out.suffix+'.outer-receipt.json');handling_signal=False
 previous_handlers={}
 def on_signal(signum,frame):
  nonlocal reason
  if handling_signal:return
  reason='supervisor_signal:'+signal.Signals(signum).name
  raise SupervisorSignal(signum)
 for sig in (signal.SIGTERM,signal.SIGHUP):
  previous_handlers[sig]=signal.getsignal(sig);signal.signal(sig,on_signal)
 try:
  try:
   Path(reg['output_dir']).mkdir(parents=True,exist_ok=True)
   exe=next(x['path'] for x in reg['review_records'] if x.get('kind')=='runtime_executable')
   cmd=[exe,str(w),'--registration',str(rp),'--registration-sha256',registration_sha256,'--evaluator',str(e),'--output',str(out),'--stage',stage,'--candidate-update',str(candidate_update),'--cohort',cohort,'--heartbeat',str(heartbeat),'--deadline',str(deadline)]
   with log.open('xb') as lf:
    proc=subprocess.Popen(cmd,start_new_session=True,stdout=lf,stderr=subprocess.STDOUT,close_fds=True)
    grace_end=min(deadline,start+float(reg['limits'].get('startup_grace_seconds',START_GRACE)))
    while proc.poll() is None:
     now=time.monotonic()
     if now>=deadline:reason='wall_limit';break
     if now-last>=POLL:
      try:rss,rows=aggregate_rss(proc.pid)
      except Exception as ex:reason='process_group_sampling_failed:'+str(ex);break
      if rss>CAP:reason='rss_limit';break
      if heartbeat.exists():
       try:mps,h=mps_from_heartbeat(heartbeat,proc.pid,reg)
       except Exception as ex:reason='heartbeat_invalid:'+str(ex);break
       if h['rss_bytes']>CAP:reason='worker_rss_limit';break
       if mps>CAP:reason='mps_limit';break
      elif now>grace_end:reason='heartbeat_missing';break
      if Path(reg['cancel_path']).exists():reason='cancelled';break
      try:
       mark=read(reg['one_shot_marker'])
       if mark.get('run_id')!=reg['run_id'] or mark.get('registration_sha256')!=registration_sha256:raise RuntimeError('one-shot marker lost or changed')
       for source_name in ('evaluator','worker','launcher'):
        item=reg['source'];require_hash(item[source_name+'_path'],item[source_name+'_sha256'],source_name+' source changed during run')
      except Exception as ex:reason='source_or_marker_invalid:'+str(ex);break
      state=read(reg['state_path'])
      if state.get('active_inference_diagnostic')!=reg['expected_lease'] or state.get('active_long_campaign') not in (None,False) or state.get('active_long') not in (None,False) or state.get('active_inference') not in (None,False):reason='lease_invalid';break
      if sha(rp)!=registration_sha256:reason='registration_changed';break
      last=now
     time.sleep(.02)
    if reason:
     cleanup_attempted=True;handling_signal=True;terminate_bounded(proc,deadline+CLEANUP)
    else:exit_code=proc.wait(timeout=max(.01,deadline-time.monotonic()))
  except BaseException as ex:
   handling_signal=True
   if isinstance(ex,SupervisorSignal):reason=reason or 'supervisor_signal:'+signal.Signals(ex.signum).name
   else:reason=reason or 'supervisor_exception:'+str(ex)
   if proc is not None and not cleanup_attempted:
    cleanup_attempted=True;terminate_bounded(proc,deadline+CLEANUP)
   if proc is not None:exit_code=proc.poll()
   rows,sample_error=sample_procs(proc.pid) if proc is not None else ([],None)
   if sample_error:reason+=';'+sample_error
   try:atomic_json(receipt_path,receipt(reg,registration_sha256,stage,candidate_update,cohort,start,reason,exit_code,rows,log))
   except Exception as receipt_error:raise RuntimeError(reason+'; outer receipt write failed: '+str(receipt_error)) from ex
   if isinstance(ex,SupervisorSignal):raise RuntimeError(reason+'; partial receipt preserved') from ex
   raise
 finally:
  for sig,handler in previous_handlers.items():signal.signal(sig,handler)
 exit_code=proc.returncode if proc else None
 remaining,sample_error=sample_procs(proc.pid) if proc else ([],None);rows=remaining
 if sample_error:reason=reason or sample_error
 if remaining:
  if not cleanup_attempted:cleanup_attempted=True;terminate_bounded(proc,deadline+CLEANUP)
  remaining,sample_error=sample_procs(proc.pid);rows=remaining
  if sample_error:reason=reason or sample_error
  if reason is None:reason='process_group_survived'
 passed=not reason and exit_code==0 and remaining==[] and sample_error is None
 try:
  if sha(rp)!=registration_sha256:raise RuntimeError('registration changed')
  for name,path in [('worker',w),('evaluator',e),('launcher',Path(__file__))]:require_hash(path,reg['source'][name+'_sha256'],name+' postflight source')
  executable_pin=next(x for x in reg['review_records'] if x.get('kind')=='runtime_executable');require_hash(executable_pin['path'],executable_pin['sha256'],'postflight runtime executable')
  post=read(reg['state_path'])
  if post.get('active_inference_diagnostic')!=reg['expected_lease']:raise RuntimeError('postflight lease changed')
  mark=read(reg['one_shot_marker'])
  if mark.get('run_id')!=reg['run_id'] or mark.get('registration_sha256')!=registration_sha256:raise RuntimeError('postflight marker changed')
  if post.get('active_long_campaign') not in (None,False) or post.get('active_long') not in (None,False) or post.get('active_inference') not in (None,False):raise RuntimeError('postflight conflicting lease')
  for k,p in reg['runtime']['member_sha256'].items():require_hash(Path(reg['runtime']['root'])/k,p,'postflight runtime '+k)
  for update,candidate in reg.get('candidates',{}).items():
   require_hash(candidate['checkpoint_path'],candidate['checkpoint_sha256'],'postflight candidate '+update+' checkpoint')
   require_hash(candidate['source_receipt_path'],candidate['source_receipt_sha256'],'postflight candidate '+update+' receipt')
  for name,c in reg.get('cohorts',{}).items():require_hash(c['manifest_path'],c['manifest_sha256'],'postflight '+name+' manifest')
  for rr in reg.get('review_records',[]):require_hash(rr['path'],rr['sha256'],'postflight review record')
  if stage=='benchmark':require_hash(reg['benchmark_reference']['certificate_path'],reg['benchmark_reference']['certificate_sha256'],'postflight accepted certificate')
  if stage in ('ranking','confirmation'):validate_throughput_receipt(reg)
  if stage=='confirmation':
   from worker import validate_selection
   validate_selection(reg)
  if Path(reg['runtime']['pycache_prefix']).exists() and any(Path(reg['runtime']['pycache_prefix']).iterdir()):raise RuntimeError('postflight pycache is not empty')
  if reg.get('cancel_path') and Path(reg['cancel_path']).exists():raise RuntimeError('postflight cancellation')
 except Exception as ex:passed=False;reason=reason or 'postflight:'+str(ex)
 rec=receipt(reg,registration_sha256,stage,candidate_update,cohort,start,reason,exit_code,rows,log);atomic_json(receipt_path,rec)
 if not passed:raise RuntimeError('worker stopped: '+str(reason or exit_code)+'; partial receipt preserved')
 return rec

def terminate_bounded(proc,deadline):
 end=min(time.monotonic()+CLEANUP,deadline)
 try:os.killpg(proc.pid,signal.SIGTERM)
 except ProcessLookupError:pass
 term_end=min(end,time.monotonic()+5)
 while time.monotonic()<term_end:
  proc.poll()  # reap main child while checking its process group
  sampled,_=sample_procs(proc.pid)
  if sampled==[]:
   try:proc.wait(timeout=max(.01,term_end-time.monotonic()))
   except subprocess.TimeoutExpired:pass
   return proc.poll() is not None
  time.sleep(.05)
 try:os.killpg(proc.pid,signal.SIGKILL)
 except ProcessLookupError:pass
 while time.monotonic()<end:
  proc.poll()
  sampled,_=sample_procs(proc.pid)
  if sampled==[]:
   if proc.poll() is None:
    try:proc.wait(timeout=max(.01,end-time.monotonic()))
    except subprocess.TimeoutExpired:break
   return proc.poll() is not None
  time.sleep(.05)
 return False

def receipt(reg,regsha,stage,update,cohort,start,reason,exit_code,rows,log):
 artifacts=[]
 for path in sorted(Path(reg['output_dir']).glob('*')):
  if path.is_file() and not path.name.endswith('.outer-receipt.json'):
   try:artifacts.append({'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)})
   except OSError:artifacts.append({'path':str(path),'unreadable':True})
 return {'schema':'expanded_eval_outer_receipt_v1','run_id':reg['run_id'],'registration_sha256':regsha,'stage':stage,'candidate_update':update,'cohort':cohort,'raw_exit_code':exit_code,'stop_reason':reason,'elapsed_seconds':time.monotonic()-start,'process_group_remaining':rows,'process_group_absent':rows==[],'output_artifacts':artifacts,'worker_log_path':str(log),'worker_log_bytes':log.stat().st_size if log.exists() else 0,'worker_sha256':reg['source']['worker_sha256'],'evaluator_sha256':reg['source']['evaluator_sha256']}
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for n in ('registration','registration-sha256','worker','evaluator','stage','cohort','output'):p.add_argument('--'+n,required=True)
 p.add_argument('--candidate-update',type=int,required=True);a=p.parse_args()
 execute_once(registration=a.registration,registration_sha256=a.registration_sha256,worker=a.worker,evaluator=a.evaluator,stage=a.stage,candidate_update=a.candidate_update,cohort=a.cohort,output=a.output)
