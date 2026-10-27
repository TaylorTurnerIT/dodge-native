"""Dedicated fail-closed supervisor for the RNG reference probe schema."""
import argparse,hashlib,json,os,signal,subprocess,sys,time,uuid
from pathlib import Path
PIN='4a5d084359ee48fe5351c96e0ec4455fdcd95a428a17bbcf59d0653f6922de98'
PRIMITIVES=Path(__file__).parents[1]/'confirmation-proof-binding-parent-repair-20261026-r4'/'execute_once.py'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def exclusive_json(path,obj):
 p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); raw=(json.dumps(obj,sort_keys=True)+'\n').encode(); fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'wb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
def verified_primitives():
 raw=PRIMITIVES.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=PIN: raise RuntimeError('cleanup primitive source pin mismatch')
 ns={'__file__':str(PRIMITIVES),'__name__':'_verified_cleanup'}
 exec(compile(raw,str(PRIMITIVES),'exec'),ns)
 return ns
def preflight(rp,rsha,reg,worker):
 if sha(rp)!=rsha: raise RuntimeError('external registration SHA mismatch')
 required={'schema','status','authority','run_id','study_id','source','runtime','vectors_path','vectors_sha256','vectors','checkpoint_path','checkpoint_sha256','parent_receipt_path','parent_receipt_sha256','state_path','expected_lease','one_shot_marker','cancel_path','output_dir','limits','references'}
 synthetic_extra={'synthetic_test_dependencies'} if reg.get('status')=='synthetic_test_only' else set()
 if set(reg)!=required|synthetic_extra: raise RuntimeError('registration top-level fields mismatch')
 synthetic=(reg.get('status')=='synthetic_test_only' and reg.get('authority')=='synthetic_test_only' and os.environ.get('RNG_PROBE_SYNTHETIC_TEST')=='1' and bool(reg.get('synthetic_test_dependencies')))
 if reg.get('schema')!='d2_layerb_rng_reference_probe_registration_v1' or (reg.get('status')!='parent_registered' and not synthetic): raise RuntimeError('registration schema/status mismatch')
 if reg.get('authority')!='parent_approved_one_shot' and not synthetic: raise RuntimeError('parent approval absent')
 src=reg['source']
 pins={'worker':Path(worker),'supervisor':Path(__file__),'probe':Path(__file__).with_name('probe.py'),'fingerprint':Path(src['fingerprint_path'])}
 for n,p in pins.items():
  if Path(src[n+'_path']).resolve()!=p.resolve() or sha(p)!=src[n+'_sha256']: raise RuntimeError(n+' source pin mismatch')
 if synthetic and sha(reg['synthetic_test_dependencies']['runtime_path'])!=reg['synthetic_test_dependencies']['runtime_sha256']: raise RuntimeError('synthetic runtime source pin mismatch')
 if sha(PRIMITIVES)!=PIN or src.get('cleanup_primitives_sha256')!=PIN: raise RuntimeError('verified cleanup source pin mismatch')
 vectors=read(reg['vectors_path'])
 if sha(reg['vectors_path'])!=reg['vectors_sha256'] or vectors!=reg['vectors']: raise RuntimeError('vectors pin/content mismatch')
 # Strict validation before marker; importing probe is stdlib-only.
 import probe
 probe.validate_vectors(vectors,reg['study_id'])
 if sha(reg['checkpoint_path'])!=reg['checkpoint_sha256'] or reg['checkpoint_sha256']!=probe.PARENT: raise RuntimeError('checkpoint byte pin mismatch')
 if sha(reg['parent_receipt_path'])!=reg['parent_receipt_sha256'] or reg['parent_receipt_sha256']!=probe.PARENT_RECEIPT: raise RuntimeError('accepted receipt pin mismatch')
 rt=reg['runtime']; exe=Path(rt['python_path'])
 if not exe.is_file() or sha(exe)!=rt['interpreter_sha256']: raise RuntimeError('interpreter byte pin mismatch')
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
def execute(rp,rsha,worker):
 reg=read(rp); ns=verified_primitives(); preflight(rp,rsha,reg,worker)
 start=time.monotonic(); work_deadline=start+45; outer_deadline=start+55; proc=None; reason=None; raw_exit=None; claimed=False; rows=None; log=Path(reg['output_dir'])/'worker.log'; hb=Path(reg['output_dir'])/'worker-heartbeat.json'; receipt_path=Path(reg['output_dir'])/'outer-receipt.json'
 old={}; pending=[]; spawning=False
 def handler(sig,frame):
  nonlocal reason,spawning
  reason='supervisor_signal:'+signal.Signals(sig).name
  if spawning: pending.append(sig); return
  raise KeyboardInterrupt
 for s in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT): old[s]=signal.signal(s,handler)
 try:
  # Claim after all preflight and signal installation; marker never cleared.
  exclusive_json(reg['one_shot_marker'],{'run_id':reg['run_id'],'registration_sha256':rsha,'pid':os.getpid(),'timestamp_ns':time.time_ns()}); claimed=True
  Path(reg['output_dir']).mkdir(parents=True,exist_ok=True)
  cmd=[reg['runtime']['python_path'],'-B',str(worker),'--registration',str(rp),'--registration-sha256',rsha,'--heartbeat',str(hb),'--deadline',str(work_deadline)]
  env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=reg['runtime']['empty_cache_path'])
  with log.open('xb') as f:
   spawning=True
   try: proc=subprocess.Popen(cmd,start_new_session=True,stdout=f,stderr=subprocess.STDOUT,env=env,close_fds=True)
   finally: spawning=False
  if pending: raise KeyboardInterrupt
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
  if reason: ns['terminate_bounded'](proc,min(outer_deadline,start+45+10))
  raw_exit=proc.poll()
  rows,sample_error=ns['sample_procs'](proc.pid)
  if rows:
   reason=reason or 'process_group_survived'
   ns['terminate_bounded'](proc,min(outer_deadline,time.monotonic()+10))
   rows,sample_error=ns['sample_procs'](proc.pid)
  if sample_error: reason=reason or sample_error
  if rows: reason=reason or 'process_group_survived'
  if raw_exit!=0: reason=reason or 'worker_nonzero_exit'
  if Path(reg['cancel_path']).exists(): reason=reason or 'cancelled_postflight'
  if sha(rp)!=rsha: reason=reason or 'registration_postflight_changed'
  for n in ('worker','supervisor','probe','fingerprint'):
   if sha(reg['source'][n+'_path'])!=reg['source'][n+'_sha256']: reason=reason or 'source_postflight_changed:'+n
  if sha(reg['checkpoint_path'])!=reg['checkpoint_sha256'] or sha(reg['parent_receipt_path'])!=reg['parent_receipt_sha256'] or sha(reg['vectors_path'])!=reg['vectors_sha256']: reason=reason or 'input_pin_postflight_changed'
  if sha(reg['runtime']['python_path'])!=reg['runtime']['interpreter_sha256']: reason=reason or 'interpreter_postflight_changed'
  state=read(reg['state_path'])
  if state.get('active_inference_diagnostic')!=reg['expected_lease'] or any(state.get(k) not in (None,False) for k in ('active_long_campaign','active_long','active_inference')): reason=reason or 'lease_postflight_changed'
  if Path(reg['cancel_path']).exists(): reason=reason or 'cancelled_postflight'
  marker=read(reg['one_shot_marker'])
  if marker.get('run_id')!=reg['run_id'] or marker.get('registration_sha256')!=rsha: reason=reason or 'marker_postflight_changed'
  commit_path=Path(reg['output_dir'],'COMMITTED.json')
  if not commit_path.is_file(): reason=reason or 'reference_commit_missing'
  else:
   try:
    commit=read(commit_path)
    if commit.get('schema')!='d2_layerb_rng_reference_probe_commit_v1' or commit.get('references')!=3 or len(commit.get('files',[]))!=4: raise ValueError('commit manifest schema/count mismatch')
    names={'replica-1.json','replica-2.json','replica-3.json','receipt.json'}
    if {x.get('path') for x in commit['files']}!=names: raise ValueError('commit file inventory mismatch')
    for item in commit['files']:
     if sha(Path(reg['output_dir'])/item['path'])!=item['sha256']: raise ValueError('committed artifact hash mismatch')
    import probe
    for i in (1,2,3):
     row=read(Path(reg['output_dir'])/f'replica-{i}.json'); vector=reg['vectors']['vectors'][i-1]
     if set(row)!=probe.RECEIPT_FIELDS or row.get('schema')!='d2_layerb_rng_real_state_preflight_v1' or row.get('status')!='measured' or type(row.get('replica')) is not int or row['replica']!=i: raise ValueError('reference schema/status/replica invalid')
     if row.get('study_id')!=reg['study_id'] or row.get('complete_seed_vector')!=vector['seeds'] or row.get('vector_sha256')!=vector['vector_sha256']: raise ValueError('reference vector binding mismatch')
     for field in ('cpu_rng_state_sha256','mps_rng_state_sha256'):
      value=row.get(field)
      if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value): raise ValueError('reference digest invalid')
    agg=read(Path(reg['output_dir'])/'receipt.json')
    if agg.get('status')!='captured_pending_parent_postflight' or len(agg.get('references',[]))!=3: raise ValueError('aggregate receipt incomplete')
   except Exception as e: reason=reason or 'reference_postflight:'+str(e)
 except BaseException as e:
  reason=reason or ('supervisor_interrupted' if isinstance(e,KeyboardInterrupt) else 'supervisor_exception:'+str(e))
  if proc is not None and proc.poll() is None:
   try: ns['terminate_bounded'](proc,min(outer_deadline,time.monotonic()+10))
   except Exception as cleanup_error: reason+=';cleanup_error:'+str(cleanup_error)
  if proc is not None: raw_exit=proc.poll()
 finally:
  if claimed and not receipt_path.exists():
   rows=rows if rows is not None else (ns['sample_procs'](proc.pid)[0] if proc else None)
   artifacts=[]
   for p in sorted(Path(reg['output_dir']).glob('*')):
    if p.is_file(): artifacts.append({'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)})
   exclusive_json(receipt_path,{'schema':'d2_layerb_rng_reference_probe_outer_receipt_v1','run_id':reg['run_id'],'registration_sha256':rsha,'raw_worker_exit_code':raw_exit,'stop_reason':reason,'process_group_remaining':rows,'process_group_absent':rows==[],'artifacts':artifacts,'elapsed_seconds':time.monotonic()-start,'status':'accepted_pending_parent_postflight' if reason is None else 'partial_failure_preserved'})
  for s,h in old.items(): signal.signal(s,h)
 if reason: raise RuntimeError('probe failed: '+reason+'; partial receipt preserved')
 return read(receipt_path)
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--registration',required=True); ap.add_argument('--registration-sha256',required=True); ap.add_argument('--worker',default=str(Path(__file__).with_name('worker_cli.py'))); a=ap.parse_args(); execute(Path(a.registration),a.registration_sha256,Path(a.worker))
if __name__=='__main__': main()
