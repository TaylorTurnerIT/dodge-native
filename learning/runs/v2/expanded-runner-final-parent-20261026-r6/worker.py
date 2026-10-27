"""Inert expanded-evaluation worker. Imports evaluator only after all static checks."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, sys, time, uuid, threading
from pathlib import Path

LIMIT_RSS=6*1024**3
LIMIT_MPS=6*1024**3
NATIVE_REL='dodge_rl/_native.cpython-312-darwin.so'
NATIVE_SHA='022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e'
GOLDEN_PATH='/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-lr-20261026-r1/development-000348.jsonl'
GOLDEN_SHA='d6e914345dcc955f678db41eb08d9f20af8e77490652f8d25f7ee09550a63a03'

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def atomic_json(path,obj):
 path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_name(path.name+f'.{os.getpid()}.{uuid.uuid4().hex}.tmp')
 fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'w') as f: json.dump(obj,f,sort_keys=True,separators=(',',':')); f.write('\n'); f.flush(); os.fsync(f.fileno())
 os.link(tmp,path); tmp.unlink()
def exclusive_json(path,obj): atomic_json(path,obj)
def update_json(path,obj):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+f'.{os.getpid()}.{uuid.uuid4().hex}.tmp')
 with tmp.open('x') as f:json.dump(obj,f,sort_keys=True,separators=(',',':'));f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def read_json(path): return json.loads(Path(path).read_text())
def require_hash(path,expected,label):
 if not isinstance(expected,str) or len(expected)!=64 or sha(path)!=expected: raise RuntimeError(label+' pin absent or mismatch')
def runtime_check(reg):
 rt=reg.get('runtime') or {}; root=Path(rt.get('root') or '')
 if not root.is_dir(): raise RuntimeError('runtime root absent')
 native=rt.get('native_relative_path')
 if not native or not (root/native).is_file(): raise RuntimeError('frozen native member absent')
 members=rt.get('member_sha256')
 if not isinstance(members,dict) or len(members)!=13: raise RuntimeError('runtime must pin exact 13-member map')
 if native!=NATIVE_REL or members.get(NATIVE_REL)!=NATIVE_SHA: raise RuntimeError('frozen native pin mismatch')
 for rel,pin in members.items(): require_hash(root/rel,pin,'runtime member '+rel)
 for key in ('backend','torch_version','numpy_version','pycache_prefix'):
  if not rt.get(key): raise RuntimeError('runtime '+key+' pin absent')
 if not Path(rt['pycache_prefix']).is_absolute(): raise RuntimeError('pycache prefix must be absolute')

def call_plan(reg,stage,update,output):
 if stage=='benchmark': return [(update,'benchmark_dev64',Path(output).with_name(Path(output).stem+f'-repeat-{i}'+Path(output).suffix)) for i in (1,2)]
 if stage=='ranking': return [(int(k),'ranking',Path(output).with_name(Path(output).stem+f'-candidate-{k}'+Path(output).suffix)) for k in sorted(reg['candidates'],key=int)]
 if stage=='confirmation':
  s=reg['selection_record']; return [(int(s['winner_update']),'confirmation',Path(output).with_name(Path(output).stem+'-winner'+Path(output).suffix)),(348,'confirmation',Path(output).with_name(Path(output).stem+'-incumbent-348'+Path(output).suffix))]
 raise RuntimeError('unsupported stage')
def executable_pin(reg):
 matches=[x for x in reg.get('review_records',[]) if x.get('kind')=='runtime_executable']
 if len(matches)!=1: raise RuntimeError('one external runtime executable pin required')
 p=Path(matches[0]['path']);require_hash(p,matches[0].get('sha256'),'runtime executable')
 if Path(sys.executable).resolve()!=p.resolve(): raise RuntimeError('worker executable differs from external pin')
def worker_guard(reg,registration_path,registration_sha,deadline,heartbeat,sequence):
 if time.monotonic()>=deadline: raise RuntimeError('worker wall deadline reached')
 if Path(reg['cancel_path']).exists(): raise RuntimeError('parent cancellation requested')
 if sha(registration_path)!=registration_sha: raise RuntimeError('registration changed during run')
 marker=read_json(reg['one_shot_marker'])
 if marker.get('run_id')!=reg['run_id'] or marker.get('registration_sha256')!=registration_sha:raise RuntimeError('one-shot marker lost or changed')
 for key in ('evaluator','worker','launcher'):
  require_hash(reg['source'][key+'_path'],reg['source'][key+'_sha256'],key+' source changed during run')
 lease=reg['expected_lease']; ledger=read_json(reg['state_path'])
 if ledger.get('active_inference_diagnostic')!=lease: raise RuntimeError('inference lease lost')
 if ledger.get('active_long_campaign') not in (None,False): raise RuntimeError('active long campaign appeared')
 if ledger.get('active_long') not in (None,False): raise RuntimeError('legacy active long lease appeared')
 if ledger.get('active_inference') not in (None,False): raise RuntimeError('other inference lease appeared')
 # Peak RSS is conservative; supervisor independently measures current group RSS.
 import resource
 rss=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform=='darwin' else 1024)
 mps,phase,initialized=driver_memory_status(reg.get('runtime',{}).get('backend'))
 if rss is None: raise RuntimeError('worker RSS unavailable')
 if mps is None: raise RuntimeError('worker MPS driver memory unavailable')
 if rss>LIMIT_RSS: raise RuntimeError('worker RSS limit exceeded')
 if mps>LIMIT_MPS: raise RuntimeError('worker MPS driver limit exceeded')
 sequence+=1
 update_json(heartbeat,{'schema':'expanded_eval_worker_heartbeat_v1','run_id':reg['run_id'],'registration_sha256':registration_sha,'pid':os.getpid(),'sequence':sequence,'timestamp_ns':time.time_ns(),'rss_bytes':rss,'rss_measurement':'process_peak_rss','mps_driver_bytes':mps,'phase':phase,'driver_initialized':initialized})
 return sequence
def process_rss(pid):
 try:
  import resource
  # macOS ru_maxrss is bytes; Linux is KiB. Use ps where available for current RSS.
  import subprocess
  x=subprocess.run(['ps','-o','rss=','-p',str(pid)],capture_output=True,text=True,timeout=0.2,check=True)
  return int(x.stdout.strip())*1024
 except Exception: return None
def driver_memory_status(backend=None):
 # Inspect sys.modules only. Sampler must never import torch during evaluator imports.
 if backend!='mps': return 0,'runtime',False
 torch=sys.modules.get('torch')
 if torch is None or getattr(getattr(torch,'__spec__',None),'_initializing',False): return 0,'startup',False
 try:
  available=torch.backends.mps.is_available()
  if not available: return None,'runtime',False
  return int(torch.mps.driver_allocated_memory()),'runtime',True
 except Exception:
  return None,'runtime',True

def driver_memory(pid,backend=None): return driver_memory_status(backend)[0]

class HeartbeatSampler:
 def __init__(self,reg,rp,registration_sha,deadline,heartbeat,initial_sequence=0):
  self.reg=reg; self.rp=rp; self.registration_sha=registration_sha; self.deadline=deadline; self.heartbeat=heartbeat
  self.stop_event=threading.Event(); self.error=None; self.sequence=initial_sequence; self.started=time.monotonic()
  self.lock=threading.Lock(); self.thread=threading.Thread(target=self._run,name='worker-heartbeat-sampler',daemon=True)
 def start(self): self.thread.start()
 def _run(self):
  try:
   while not self.stop_event.is_set():
    now=time.monotonic()
    if now>=self.deadline: raise RuntimeError('worker wall deadline reached')
    mps,phase,initialized=driver_memory_status(self.reg.get('runtime',{}).get('backend'))
    if phase=='startup' and now-self.started>float(self.reg.get('limits',{}).get('startup_grace_seconds',12)): raise RuntimeError('MPS startup readiness deadline reached')
    if phase=='runtime' and self.reg.get('runtime',{}).get('backend')=='mps' and mps is None: raise RuntimeError('worker MPS driver memory unavailable')
    with self.lock:
     self.sequence=worker_guard(self.reg,self.rp,self.registration_sha,self.deadline,self.heartbeat,self.sequence)
    self.stop_event.wait(min(0.2,float(self.reg.get('limits',{}).get('guard_poll_seconds',0.2))))
  except BaseException as e:
   self.error=e; self.stop_event.set()
 def check(self):
  if self.error: raise RuntimeError('heartbeat sampler failed: '+str(self.error)) from self.error
  if not self.thread.is_alive() and not self.stop_event.is_set(): raise RuntimeError('heartbeat sampler stopped unexpectedly')
 def stop(self):
  self.stop_event.set(); self.thread.join(timeout=2)
  if self.thread.is_alive(): raise RuntimeError('heartbeat sampler did not stop within 2 seconds')
  self.check()

def validate_mode(reg,stage,update,cohort,output):
 if reg.get('schema')!='expanded_D2_evaluation_registration_v1' or reg.get('mode')!=stage: raise RuntimeError('registration schema/mode mismatch')
 expected={'benchmark':(348,'benchmark_dev64'),'ranking':(None,'ranking'),'confirmation':(None,'confirmation')}[stage]
 if expected[0] is not None and update!=expected[0] or cohort!=expected[1]: raise RuntimeError('stage/update/cohort differs from registration')
 if stage=='ranking' and update!=348:raise RuntimeError('ranking launcher update anchor must be 348')
 if stage=='confirmation' and update!=int((reg.get('selection_record') or {}).get('winner_update',-1)):raise RuntimeError('confirmation launcher update differs from locked winner')
 if Path(output).resolve().parent!=Path(reg['output_dir']).resolve(): raise RuntimeError('output path outside registered run directory')
 for p in [Path(output),* [x[2] for x in call_plan(reg,stage,update,output)]]:
  if p.exists(): raise RuntimeError('output already exists: '+str(p))
 if stage=='confirmation': validate_selection(reg)

def validate_selection(reg):
 s=reg.get('selection_record') or {}; p=s.get('path'); pin=s.get('sha256')
 if not p or not pin: raise RuntimeError('confirmation selection record path/hash required')
 require_hash(p,pin,'selection record')
 record=read_json(p)
 for k in ('winner_update','winner_checkpoint_sha256','incumbent_checkpoint_sha256'):
  if record.get(k)!=s.get(k): raise RuntimeError('selection record registration mismatch: '+k)
 winner=int(record['winner_update'])
 if winner==348: raise RuntimeError('348 cannot be confirmation winner')
 if reg['candidates'][str(winner)]['checkpoint_sha256']!=record['winner_checkpoint_sha256'] or reg['candidates']['348']['checkpoint_sha256']!=record['incumbent_checkpoint_sha256']: raise RuntimeError('selection checkpoint pin mismatch')
 refs=record.get('ranking_results')
 if len(refs)!=6: raise RuntimeError('selection must reference six ranking results')
 seen=set()
 for ref in refs:
  require_hash(ref['path'],ref['sha256'],'ranking result')
  result=read_json(ref['path']); update=int(result.get('candidate_update',-1))
  if result.get('complete') is not True or result.get('cohort_name')!='ranking': raise RuntimeError('referenced ranking result incomplete or wrong cohort')
  if update in seen or update not in {180,204,276,300,324,348}: raise RuntimeError('ranking result update set invalid')
  if result.get('checkpoint_sha256')!=reg['candidates'][str(update)]['checkpoint_sha256']: raise RuntimeError('ranking result checkpoint pin mismatch')
  seen.add(update)
 if seen!={180,204,276,300,324,348}: raise RuntimeError('selection references do not cover all six ranking candidates')

def read_certificate_rows(path):
 p=Path(path)
 if p.suffix=='.jsonl': return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
 d=read_json(p);return d.get('evaluation',d).get('rows',[])
def benchmark_certificate(reg):
 ref=reg.get('benchmark_reference') or {}; p=ref.get('certificate_path'); pin=ref.get('certificate_sha256')
 if p!=GOLDEN_PATH or pin!=GOLDEN_SHA: raise RuntimeError('accepted 348 JSONL pin differs')
 if not p or not pin: raise RuntimeError('accepted 348 benchmark certificate pin required')
 require_hash(p,pin,'accepted 348 certificate')
 rows=read_certificate_rows(p)
 if len(rows)!=64 or {r.get('seed') for r in rows}!=set(range(0xD0000000,0xD0000040)): raise RuntimeError('accepted certificate must contain exact 348 raw rows')
 return rows

def run(registration_path,evaluator_path,output_path,stage,candidate_update,cohort_name,registration_sha256,deadline,heartbeat):
 rp=Path(registration_path); ep=Path(evaluator_path); out=Path(output_path); reg=read_json(rp)
 require_hash(rp,registration_sha256,'external registration')
 runtime_check(reg); executable_pin(reg); validate_mode(reg,stage,candidate_update,cohort_name,out)
 source=reg['source']; require_hash(ep,source['evaluator_sha256'],'evaluator source')
 require_hash(source['worker_path'],source['worker_sha256'],'worker source')
 require_hash(source['launcher_path'],source['launcher_sha256'],'launcher source')
 if Path(source['worker_path']).resolve()!=Path(__file__).resolve():raise RuntimeError('worker path differs from registration')
 sys.pycache_prefix=reg['runtime']['pycache_prefix'];sys.dont_write_bytecode=True
 if Path(source['evaluator_path']).resolve()!=ep.resolve(): raise RuntimeError('evaluator path differs from registration')
 # First sample precedes evaluator import; sampler then runs independently.
 sequence=worker_guard(reg,rp,registration_sha256,deadline,heartbeat,0)
 sampler=HeartbeatSampler(reg,rp,registration_sha256,deadline,heartbeat,initial_sequence=sequence); sampler.start()
 def check_guard(force=False):
  sampler.check()
  if time.monotonic()>=deadline: raise RuntimeError('worker wall deadline reached')
  return True
 try:
  spec=importlib.util.spec_from_file_location('_pinned_expanded_evaluator',ep)
  if not spec or not spec.loader: raise RuntimeError('cannot load pinned evaluator')
  module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)
  require_hash(ep,source['evaluator_sha256'],'evaluator after import')
  require_hash(source['worker_path'],source['worker_sha256'],'worker after evaluator import')
  require_hash(source['launcher_path'],source['launcher_sha256'],'launcher after evaluator import')
  fn=getattr(module,'evaluate_registered',None)
  if not callable(fn): raise RuntimeError('canonical evaluator API missing')
  cert=benchmark_certificate(reg) if stage=='benchmark' else None
  results=[]; measured=[]
  for update,cohort,dest in call_plan(reg,stage,candidate_update,out):
   check_guard(force=True)
   began=time.monotonic()
   result=fn(registration_path=str(rp),registration_sha256=registration_sha256,candidate_update=update,cohort_name=cohort,output_path=str(dest),check_guard=check_guard)
   measured.append(time.monotonic()-began)
   if not isinstance(result,dict) or result.get('complete') is not True: raise RuntimeError('incomplete evaluator result; partial evidence preserved')
   if not dest.is_file(): raise RuntimeError('evaluator did not exclusively create its output')
   saved=read_json(dest)
   if saved!=result: raise RuntimeError('evaluator output differs from returned result')
   if stage=='benchmark':
    rows=result.get('rows')
    if len(rows or [])!=64 or result.get('candidate_update')!=348: raise RuntimeError('benchmark repeat must contain full 64 raw rows at update 348')
    gold={r['seed']:r for r in cert}; actual={r.get('seed'):r for r in result.get('rows',[])}
    fields=('seed','episode_index','alive_frames','gameplay_frames','score_raw_fixed','score','objective_return','terminated','truncated','death_cause','fatal_gameplay_frame','death_observed_lethal_contacts')
    if set(actual)!=set(gold) or any(any(actual[k].get(f)!=gold[k].get(f) for f in fields) for k in gold): raise RuntimeError('benchmark rows differ from accepted 348 certificate')
   results.append(result)
  if stage=='benchmark':
   a,b=results
   keys=('candidate_update','cohort_name','cohort_sha256','checkpoint_sha256','episodes','rows','performance','death_causes','caps')
   if any(a.get(k)!=b.get(k) for k in keys): raise RuntimeError('benchmark repeat mismatch')
  if stage=='benchmark':
   repeats=[]
   for result,elapsed in zip((a,b),measured):
    repeats.append({'complete':True,'candidate_update':348,'cohort_name':'benchmark_dev64','rows':result['rows'],'raw_frames':sum(int(row['gameplay_frames']) for row in result['rows']),'elapsed_seconds':elapsed})
   results={'schema':'expanded_eval_dev64_benchmark_receipt_v1','candidate_update':348,'cohort_name':'benchmark_dev64','complete':True,'run_id':reg['run_id'],'registration_sha256':registration_sha256,'accounting':'raw_frames=sum(gameplay_frames); gameplay_frames=alive_frames+1 terminal frame','repeats':repeats}
  elif stage=='ranking':
   if len(results)!=6 or {r.get('candidate_update') for r in results}!={180,204,276,300,324,348}: raise RuntimeError('ranking incomplete candidate set')
   results={'schema':'expanded_D2_ranking_selection_v1','selection_only':True,'winner_update':sorted(results,key=lambda r:(-r['performance']['mean'],r['candidate_update']))[0]['candidate_update'],'candidate_results':results}
  else: results={'schema':'expanded_D2_stage_bundle_v1','stage':stage,'results':results}
  sampler.check()
  if reg.get('runtime',{}).get('backend')=='mps':
   final_memory,final_phase,final_initialized=driver_memory_status('mps')
   if final_memory is None or final_phase!='runtime' or not final_initialized: raise RuntimeError('MPS runtime unavailable before result publication')
   if final_memory>LIMIT_MPS: raise RuntimeError('MPS driver limit exceeded before publication')
  sampler.stop()
  exclusive_json(out,results)
  return results
 finally:
  sampler.stop()
if __name__=='__main__':
 p=argparse.ArgumentParser();
 for n in ('registration','evaluator','output','heartbeat'): p.add_argument('--'+n,required=True)
 p.add_argument('--registration-sha256',required=True); p.add_argument('--stage',choices=('benchmark','ranking','confirmation'),required=True); p.add_argument('--candidate-update',type=int,required=True); p.add_argument('--cohort',required=True); p.add_argument('--deadline',type=float,required=True)
 a=p.parse_args(); run(a.registration,a.evaluator,a.output,a.stage,a.candidate_update,a.cohort,a.registration_sha256,a.deadline,a.heartbeat)
