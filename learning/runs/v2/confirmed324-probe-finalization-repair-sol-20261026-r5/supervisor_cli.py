"""Dedicated fail-closed supervisor for the RNG reference probe schema."""
import argparse,hashlib,json,os,signal,subprocess,sys,time,uuid
from pathlib import Path
PIN='4a5d084359ee48fe5351c96e0ec4455fdcd95a428a17bbcf59d0653f6922de98'
PRIMITIVES=Path(__file__).parents[1]/'confirmation-proof-binding-parent-repair-20261026-r4'/'execute_once.py'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def exclusive_json(path,obj,on_created=None):
 p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); raw=(json.dumps(obj,sort_keys=True)+'\n').encode(); fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 try:
  if on_created is not None: on_created(fd)
  with os.fdopen(fd,'wb') as f:
   fd=None; f.write(raw); f.flush(); os.fsync(f.fileno())
 finally:
  if fd is not None: os.close(fd)
def verified_primitives():
 raw=PRIMITIVES.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=PIN: raise RuntimeError('cleanup primitive source pin mismatch')
 ns={'__file__':str(PRIMITIVES),'__name__':'_verified_cleanup'}
 exec(compile(raw,str(PRIMITIVES),'exec'),ns)
 return ns
def preflight(rp,rsha,reg,worker):
 if sha(rp)!=rsha: raise RuntimeError('external registration SHA mismatch')
 required={'schema','status','authority','run_id','study_id','source','runtime','vectors_path','vectors_sha256','vectors','checkpoint_path','checkpoint_sha256','parent_receipt_path','parent_receipt_sha256','acceptance_path','acceptance_sha256','state_path','expected_lease','one_shot_marker','cancel_path','output_dir','limits','references'}
 synthetic_extra={'synthetic_test_dependencies'} if reg.get('status')=='synthetic_test_only' else set()
 if set(reg)!=required|synthetic_extra: raise RuntimeError('registration top-level fields mismatch')
 synthetic=(reg.get('status')=='synthetic_test_only' and reg.get('authority')=='synthetic_test_only' and os.environ.get('RNG_PROBE_SYNTHETIC_TEST')=='1' and bool(reg.get('synthetic_test_dependencies')))
 if reg.get('schema')!='d2_layerb_rng_reference_probe_registration_v1' or (reg.get('status')!='parent_registered' and not synthetic): raise RuntimeError('registration schema/status mismatch')
 if reg.get('authority')!='parent_approved_one_shot' and not synthetic: raise RuntimeError('parent approval absent')
 src=reg['source']
 pins={'worker':Path(worker),'supervisor':Path(__file__),'probe':Path(__file__).with_name('probe.py'),'fingerprint':Path(src['fingerprint_path'])}
 for n,p in pins.items():
  if Path(src[n+'_path']).absolute()!=p.absolute() or sha(p)!=src[n+'_sha256']: raise RuntimeError(n+' source pin mismatch')
 if synthetic and sha(reg['synthetic_test_dependencies']['runtime_path'])!=reg['synthetic_test_dependencies']['runtime_sha256']: raise RuntimeError('synthetic runtime source pin mismatch')
 if sha(PRIMITIVES)!=PIN or src.get('cleanup_primitives_sha256')!=PIN: raise RuntimeError('verified cleanup source pin mismatch')
 vectors=read(reg['vectors_path'])
 if sha(reg['vectors_path'])!=reg['vectors_sha256'] or vectors!=reg['vectors']: raise RuntimeError('vectors pin/content mismatch')
 # Load exact pinned probe buffer into a private module before marker.
 import importlib.util
 probe_path=Path(src['probe_path']); probe_raw=probe_path.read_bytes()
 if hashlib.sha256(probe_raw).hexdigest()!=src['probe_sha256']: raise RuntimeError('probe source buffer pin mismatch')
 spec=importlib.util.spec_from_file_location('_verified_probe_preflight',probe_path); probe=importlib.util.module_from_spec(spec); exec(compile(probe_raw,str(probe_path),'exec'),probe.__dict__)
 probe.validate_vectors(vectors,reg['study_id'])
 if reg['references']!={'required_replicas':[1,2,3],'receipt_fields':sorted(probe.RECEIPT_FIELDS),'same_reference_for_both_arms':True}: raise RuntimeError('reference contract mismatch')
 if sha(reg['checkpoint_path'])!=reg['checkpoint_sha256'] or reg['checkpoint_sha256']!=probe.PARENT: raise RuntimeError('checkpoint byte pin mismatch')
 if sha(reg['parent_receipt_path'])!=reg['parent_receipt_sha256'] or reg['parent_receipt_sha256']!=probe.PARENT_RECEIPT: raise RuntimeError('accepted receipt pin mismatch')
 acceptance=read(reg['acceptance_path'])
 if reg['acceptance_sha256']!='3e84979c4c8da76d0f98666a23f90eb15c1e813ca5edf1001e19daebaf4d5bbd' or sha(reg['acceptance_path'])!=reg['acceptance_sha256'] or acceptance.get('status')!='accepted_checkpoint324_replaces348_by_registered_fresh_confirmation' or acceptance.get('retained_update')!=324 or acceptance.get('checkpoint_sha256')!=reg['checkpoint_sha256'] or acceptance.get('source_integrity_receipt_sha256')!=reg['parent_receipt_sha256']: raise RuntimeError('accepted parent binding mismatch')
 rt=reg['runtime']; exe=Path(rt['python_path'])
 if not exe.is_file() or sha(exe)!=rt['interpreter_sha256']: raise RuntimeError('interpreter byte pin mismatch')
 if Path(sys.executable).absolute()!=exe.absolute() or sys.prefix!=rt['expected_venv_prefix'] or sys.version.split()[0]!=rt['python_version']: raise RuntimeError('interpreter invocation/prefix/version mismatch')
 if rt['python_version']!='3.12.15' or rt['torch_version']!='2.14.1' or rt['numpy_version']!='2.5.4': raise RuntimeError('runtime version registration mismatch')
 cache=Path(rt['empty_cache_path'])
 if not cache.is_dir() or any(cache.iterdir()): raise RuntimeError('owned empty cache missing/not empty')
 for k in ('state_path','one_shot_marker','cancel_path','output_dir'):
  if not Path(reg[k]).is_absolute(): raise RuntimeError(k+' must be absolute')
 state=read(reg['state_path'])
 if state.get('active_inference_diagnostic')!=reg['expected_lease']: raise RuntimeError('exact active inference diagnostic lease absent')
 if any(state.get(k) not in (None,False) for k in ('active_long_campaign','active_long','active_inference')): raise RuntimeError('conflicting active lease')
 if Path(reg['cancel_path']).exists() or Path(reg['one_shot_marker']).exists(): raise RuntimeError('cancel or marker already exists')
 out=Path(reg['output_dir'])
 if out.exists() and any(out.iterdir()): raise RuntimeError('output collision/nonempty output')
 lim=reg['limits']; expected={'work_seconds':45,'outer_seconds':55,'cleanup_seconds':10,'startup_grace_seconds':12,'RSS_bytes':6*1024**3,'MPS_driver_bytes':6*1024**3,'guard_poll_seconds':.2,'heartbeat_stale_seconds':2.0}
 if lim!=expected: raise RuntimeError('resource/time limits mismatch')
 return state
def require(ok,message):
 if not ok: raise ValueError(message)
def cache_check(reg):
 cache=Path(reg['runtime']['empty_cache_path'])
 require(cache.exists() and cache.is_dir() and not any(cache.iterdir()),'registered empty cache missing/not directory/not empty')
def lease_check(reg):
 state=read(reg['state_path'])
 require(state.get('active_inference_diagnostic')==reg['expected_lease'] and all(state.get(k) in (None,False) for k in ('active_long_campaign','active_long','active_inference')),'exact lease changed/conflicting lease')
def marker_check(reg,rsha):
 marker=read(reg['one_shot_marker'])
 require(marker.get('run_id')==reg['run_id'] and marker.get('registration_sha256')==rsha,'marker binding mismatch')
def committed_check(reg):
 """Independent consumer: hashes alone do not establish semantic bindings."""
 out=Path(reg['output_dir']); commit=read(out/'COMMITTED.json')
 require(set(commit)=={'schema','references','files'} and commit['schema']=='d2_layerb_rng_reference_probe_commit_v1' and type(commit['references']) is int and commit['references']==3,'commit schema/count mismatch')
 names={'replica-1.json','replica-2.json','replica-3.json','receipt.json'}
 items=commit['files']
 require(isinstance(items,list) and len(items)==4 and all(set(x)=={'path','sha256'} for x in items) and {x['path'] for x in items}==names,'commit inventory mismatch')
 require({p.name for p in out.glob('replica-*.json')}==names-{'receipt.json'},'replica inventory mismatch')
 # Parse the same bytes that were hashed, including the aggregate.
 parsed={}
 for item in items:
  raw=(out/item['path']).read_bytes()
  require(hashlib.sha256(raw).hexdigest()==item['sha256'],'committed artifact hash mismatch')
  parsed[item['path']]=json.loads(raw)
 probe_path=Path(reg['source']['probe_path']); raw=probe_path.read_bytes()
 require(hashlib.sha256(raw).hexdigest()==reg['source']['probe_sha256'],'probe postflight buffer pin mismatch')
 ns={'__file__':str(probe_path),'__name__':'_verified_probe_postflight'}; exec(compile(raw,str(probe_path),'exec'),ns)
 require(reg['references']=={'required_replicas':[1,2,3],'receipt_fields':sorted(ns['RECEIPT_FIELDS']),'same_reference_for_both_arms':True},'registered reference contract mismatch')
 canonical=lambda obj:json.dumps(obj,sort_keys=True,allow_nan=False,separators=(',',':'))
 rows=[]
 for i in (1,2,3):
  row=parsed[f'replica-{i}.json']; vector=reg['vectors']['vectors'][i-1]
  require(set(row)==ns['RECEIPT_FIELDS'] and row['schema']==ns['SCHEMA'] and row['status']=='measured' and type(row['replica']) is int and row['replica']==i,'reference schema/status/replica invalid')
  require(row['study_id']==reg['study_id'] and canonical(row['complete_seed_vector'])==canonical(vector['seeds']) and row['vector_sha256']==vector['vector_sha256'],'reference vector binding mismatch')
  require(row['accepted_checkpoint_sha256']==reg['checkpoint_sha256'] and row['parent_receipt_sha256']==reg['parent_receipt_sha256'],'reference parent binding mismatch')
  require(row['backend']=='mps' and row['torch_version']==reg['runtime']['torch_version'],'reference backend/torch binding mismatch')
  for field in ('cpu_rng_state_sha256','mps_rng_state_sha256'):
   value=row[field]
   require(isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value),'reference digest invalid')
  rows.append(row)
 agg=parsed['receipt.json']
 expected_runtime={'python':reg['runtime']['python_version'],'numpy':reg['runtime']['numpy_version'],'torch':reg['runtime']['torch_version'],'backend':'mps'}
 scope={'checkpoint_bytes_hashed_only':True,'model_constructed':False,'environment_constructed':False,'checkpoint_deserialized':False,'training':False,'evaluation':False,'launch_authority':False}
 require(set(agg)=={'schema','status','study_id','references','runtime','scope'} and agg['schema']=='d2_layerb_rng_reference_probe_receipt_v1' and agg['status']=='captured_pending_parent_postflight' and agg['study_id']==reg['study_id'],'aggregate schema/status/study mismatch')
 require(canonical(agg['runtime'])==canonical(expected_runtime),'aggregate runtime mismatch')
 require(canonical(agg['references'])==canonical(rows),'aggregate references differ from replicas')
 require(canonical(agg['scope'])==canonical(scope),'aggregate scope mismatch')
 return {'replicas':3,'runtime':expected_runtime}
def integrity_postflight(reg,rp,rsha,ns,proc):
 """Each required observation survives failure or unavailability of every other check."""
 checks={}
 def check(name,fn):
  try:
   value=fn(); checks[name]={'status':'pass'}
   if value is not None: checks[name]['observed']=value
  except (ValueError,AssertionError) as e: checks[name]={'status':'fail','error':type(e).__name__+':'+str(e)}
  except Exception as e: checks[name]={'status':'unavailable','error':type(e).__name__+':'+str(e)}
 def pinned(path,digest):
  actual=sha(path); require(actual==digest,'SHA-256 mismatch'); return {'sha256':actual}
 check('registration',lambda:pinned(rp,rsha))
 for n in ('worker','supervisor','probe','fingerprint'):
  check('source:'+n,lambda n=n:pinned(reg['source'][n+'_path'],reg['source'][n+'_sha256']))
 check('cleanup_source',lambda:pinned(PRIMITIVES,PIN))
 check('cleanup_registration_pin',lambda:require(reg['source']['cleanup_primitives_sha256']==PIN,'cleanup registration pin mismatch'))
 for n in ('checkpoint','parent_receipt','vectors','acceptance'):
  check('input:'+n,lambda n=n:pinned(reg[n+'_path'],reg[n+'_sha256']))
 check('interpreter',lambda:pinned(reg['runtime']['python_path'],reg['runtime']['interpreter_sha256']))
 check('interpreter_identity',lambda:require(Path(sys.executable).absolute()==Path(reg['runtime']['python_path']).absolute() and sys.prefix==reg['runtime']['expected_venv_prefix'] and sys.version.split()[0]==reg['runtime']['python_version'],'interpreter invocation/prefix/version changed'))
 check('lease',lambda:lease_check(reg))
 check('marker',lambda:marker_check(reg,rsha))
 check('cache',lambda:cache_check(reg))
 check('cancel',lambda:require(not Path(reg['cancel_path']).exists(),'cancel present'))
 def absent():
  if proc is None: return {'rows':[],'worker_spawned':False}
  rows,error=ns['sample_procs'](proc.pid)
  if error: raise OSError(error)
  require(rows==[],'process group remains'); return {'rows':rows,'worker_spawned':True}
 check('process_absence',absent)
 check('committed_output',lambda:committed_check(reg))
 return checks
def inventory(directory):
 artifacts=[]; errors=[]
 try: paths=sorted(Path(directory).iterdir())
 except Exception as e: return [],[{'path':str(directory),'error':type(e).__name__+':'+str(e)}]
 for p in paths:
  try:
   if p.is_file(): artifacts.append({'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)})
  except Exception as e: errors.append({'path':str(p),'error':type(e).__name__+':'+str(e)})
 return artifacts,errors
def execute(rp,rsha,worker):
 reg=read(rp); ns=verified_primitives(); preflight(rp,rsha,reg,worker)
 start=time.monotonic(); work_deadline=start+45; outer_deadline=start+55; proc=None; reason=None; raw_exit=None; claimed=False; claim_complete=False; claim_identity=None; rows=None
 log=Path(reg['output_dir'])/'worker.log'; hb=Path(reg['output_dir'])/'worker-heartbeat.json'; receipt_path=Path(reg['output_dir'])/'outer-receipt.json'
 old={}; received=[]; deferred=True; outcome_frozen=False; errors=[]; result=None
 def handler(sig,frame):
  nonlocal reason,deferred
  # After the outcome boundary, ignore handled signals without changing verdict
  # or history. Keep this policy until each original handler is restored.
  if outcome_frozen: return
  received.append(signal.Signals(sig).name)
  reason=reason or 'supervisor_signal:'+signal.Signals(sig).name
  if deferred: return
  # First interrupt switches permanently to deferral before unwinding.
  deferred=True
  raise KeyboardInterrupt
 def own_claim(fd):
  nonlocal claimed,claim_identity
  claimed=True  # O_EXCL succeeded; write/fsync completion is a separate fact.
  st=os.fstat(fd); claim_identity={'device':st.st_dev,'inode':st.st_ino}
 try:
  for s in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT): old[s]=signal.signal(s,handler)
  try:
   # Do not mask OS signals: a future child must inherit an unblocked signal mask.
   # Defer Python handler exceptions until claim ownership / child handle is known.
   exclusive_json(reg['one_shot_marker'],{'run_id':reg['run_id'],'registration_sha256':rsha,'pid':os.getpid(),'timestamp_ns':time.time_ns()},on_created=own_claim)
   claim_complete=True; deferred=False
   if received: deferred=True; raise KeyboardInterrupt
   Path(reg['output_dir']).mkdir(parents=True,exist_ok=True)
   cmd=[reg['runtime']['python_path'],'-B',str(worker),'--registration',str(rp),'--registration-sha256',rsha,'--heartbeat',str(hb),'--deadline',str(work_deadline)]
   env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=reg['runtime']['empty_cache_path'])
   deferred=True
   with log.open('xb') as f:
    proc=subprocess.Popen(cmd,start_new_session=True,stdout=f,stderr=subprocess.STDOUT,env=env,close_fds=True)
   deferred=False
   if received: deferred=True; raise KeyboardInterrupt
   startup_end=min(work_deadline,start+12); last=0
   while proc.poll() is None:
    now=time.monotonic()
    if now>=work_deadline: reason='work_limit'; break
    if now-last>=.2:
     rss,rows=ns['aggregate_rss'](proc.pid)
     if rss>reg['limits']['RSS_bytes']: reason='rss_limit'; break
     if hb.exists():
      h=read(hb)
      if h.get('run_id')!=reg['run_id'] or h.get('registration_sha256')!=rsha or h.get('pid')!=proc.pid: reason='heartbeat_identity'; break
      if (time.time_ns()-h.get('timestamp_ns',0))/1e9>2: reason='heartbeat_stale'; break
      if type(h.get('mps_driver_bytes')) is not int or not 0<=h['mps_driver_bytes']<=reg['limits']['MPS_driver_bytes']: reason='mps_limit_or_invalid'; break
      if type(h.get('rss_bytes')) is not int or h['rss_bytes']>reg['limits']['RSS_bytes']: reason='worker_rss_limit'; break
     elif now>startup_end: reason='heartbeat_missing'; break
     if Path(reg['cancel_path']).exists(): reason='cancelled'; break
     if sha(rp)!=rsha: reason='registration_changed'; break
     for n in ('worker','supervisor','probe','fingerprint'):
      if sha(reg['source'][n+'_path'])!=reg['source'][n+'_sha256']: reason='source_changed:'+n; break
     if reason: break
     mark=read(reg['one_shot_marker'])
     if mark.get('run_id')!=reg['run_id'] or mark.get('registration_sha256')!=rsha: reason='marker_changed'; break
     st=read(reg['state_path'])
     if st.get('active_inference_diagnostic')!=reg['expected_lease'] or any(st.get(k) not in (None,False) for k in ('active_long_campaign','active_long','active_inference')): reason='lease_changed'; break
     last=now
    time.sleep(.02)
  except BaseException as e:
   deferred=True
   reason=reason or ('supervisor_interrupted' if isinstance(e,KeyboardInterrupt) else 'supervisor_exception:'+str(e))
  finally:
   # Keep these handlers installed through cleanup, every integrity check, inventory,
   # and receipt fsync. Repeated signals are observations, never new exceptions.
   deferred=True
   if proc is not None:
    try:
     current=proc.poll()
     remaining,sample_error=ns['sample_procs'](proc.pid)
     if current is None or remaining or sample_error:
      ns['terminate_bounded'](proc,min(outer_deadline,time.monotonic()+10))
     raw_exit=proc.poll()  # Preserve the real child status, including signal death.
     if raw_exit!=0: reason=reason or 'worker_nonzero_exit'
    except Exception as e:
     errors.append('cleanup:'+type(e).__name__+':'+str(e)); reason=reason or 'cleanup_failed'
     raw_exit=proc.poll()
   if claimed:
    checks=integrity_postflight(reg,rp,rsha,ns,proc)
    failed=[name for name,value in checks.items() if value['status']!='pass']
    if failed: reason=reason or 'postflight_failed:'+','.join(failed)
    artifacts,inventory_errors=inventory(reg['output_dir'])
    if inventory_errors: reason=reason or 'inventory_failed'
    rows=checks['process_absence'].get('observed',{}).get('rows')
    # Finalization commit boundary: cleanup, required checks and inventory are done.
    # Signals before this assignment still cancel; signals after it are ignored
    # through receipt publication/restoration. No OS signal mask reaches children.
    outcome_frozen=True
    result={'schema':'d2_layerb_rng_reference_probe_outer_receipt_v1','run_id':reg['run_id'],'registration_sha256':rsha,'raw_worker_exit_code':raw_exit,'stop_reason':reason,'process_group_remaining':rows,'process_group_absent':checks['process_absence']['status']=='pass','artifacts':artifacts,'inventory_errors':inventory_errors,'errors':errors,'postflight':checks,'failed_checks':failed,'claim_created':True,'claim_write_completed':claim_complete,'claim_identity':claim_identity,'handled_signals':received,'elapsed_seconds':time.monotonic()-start,'status':'accepted_pending_parent_postflight' if reason is None else 'partial_failure_preserved','bounds_limit':'55-second decisions; filesystem/hash/fsync/receipt finalization lack a hard watchdog'}
    exclusive_json(receipt_path,result)
 finally:
  # No handlers are restored until receipt finalization completes or raises.
  for s,h in old.items(): signal.signal(s,h)
 if reason: raise RuntimeError('probe failed: '+reason+'; '+('partial receipt preserved' if claimed else 'marker not claimed'))
 return result
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--registration',required=True); ap.add_argument('--registration-sha256',required=True); ap.add_argument('--worker',default=str(Path(__file__).with_name('worker_cli.py'))); a=ap.parse_args(); execute(Path(a.registration),a.registration_sha256,Path(a.worker))
if __name__=='__main__': main()
