"""Small stdlib source-extracted failure publication discriminators. No project imports."""
import ast,hashlib,json,math,os,threading,time,traceback,types
from pathlib import Path
O=Path(__file__).resolve().parent;H=O.parent/'postovernight-long-D2-guard-prepare-r1'
s=(H/'long_d2.py').read_text();t=ast.parse(s)
class Stop(RuntimeError):
 def __init__(self,message,outcome='identity_or_lease_failure'):self.outcome=outcome;super().__init__(message)
def require(b,m,outcome='identity_or_lease_failure'):
 if not b:raise Stop(m,outcome)
def remaining(d,maximum=None):
 if d<=time.monotonic():raise Stop('Absolute deadline expired','wall_guard')
 return d-time.monotonic() if maximum is None else min(maximum,d-time.monotonic())
ns=dict(Path=Path,json=json,hashlib=hashlib,os=os,require=require,Stop=Stop,HASH_OBSERVER=None,VERIFY_LOCAL=threading.local(),life=types.SimpleNamespace(remaining=remaining))
nodes=[n for n in t.body if isinstance(n,ast.FunctionDef) and n.name in {'sha','save','replace_json','emit'}]
g=next(n for n in t.body if isinstance(n,ast.ClassDef) and n.name=='Guard')
persist=next(n for n in g.body if isinstance(n,ast.FunctionDef) and n.name=='persist_timing')
check=next(n for n in g.body if isinstance(n,ast.FunctionDef) and n.name=='check')
mod=ast.Module(body=nodes+[persist,check],type_ignores=[]);exec(compile(mod,'frozen-controller-extract','exec'),ns)
(O/'controller-executed-v3.ast.txt').write_text(ast.dump(mod,indent=2)+'\n')
es=(H/'long_d2_executor.py').read_text();et=ast.parse(es);execution=next(n for n in et.body if isinstance(n,ast.ClassDef) and n.name=='Execution');run=next(n for n in execution.body if isinstance(n,ast.FunctionDef) and n.name=='run')
outer=next(n for n in run.body if isinstance(n,ast.Try));handler=outer.handlers[0]
# Exact failure cleanup/publication try, including its original exception swallow.
failure_try=next(n for n in handler.body if isinstance(n,ast.Try))
fm=ast.Module(body=[failure_try],type_ignores=[])
(O/'executor-failure-executed-v3.ast.txt').write_text(ast.dump(fm,indent=2)+'\n')
class Guard:
 failure=None
 clock=staticmethod(time.monotonic)
 check=ns['check']
 event=threading.Event()
 thread=verify_thread=None
 timings=[dict(sequence=0,status='passed',end_monotonic=1.0)]
 persist_timing=ns['persist_timing']
class Watchdog:
 def join(self,**kwargs):pass
results=[]
for case in ('partial-normal-timing','failed-hash-observer','no-telemetry-control'):
 d=O/('v3-'+case);d.mkdir();receipt=d/'terminal-receipt.json';ns['save'](receipt,{'accepted':True,'experiment_status':'complete'})
 guard=Guard();timing=d/'outer-verification.jsonl'
 primary=None
 if case=='partial-normal-timing':
  def inject(stream,row):
   ns['emit_original'](stream,row)
   raise OSError('injected telemetry IO failure after file creation')
  ns['emit_original']=ns['emit'];ns['emit']=inject
  try:guard.persist_timing(timing,time.monotonic()+20)
  except OSError as e:primary=repr(e)
  ns['emit']=ns['emit_original']
 elif case=='failed-hash-observer':
  guard.deadline=time.monotonic()-1
  def fail_observer():guard.check()
  ns['HASH_OBSERVER']=fail_observer;primary='normal Guard deadline expired with cleanup time remaining'
 elif case=='no-telemetry-control':guard=None
 calls=[]
 def replace(path,value):calls.append(str(path));return ns['replace_json'](path,value)
 self=types.SimpleNamespace(child=None,cleanup_complete=True,guard=guard,
   pool=types.SimpleNamespace(until=time.monotonic()+20,first=time.monotonic()),
   groups={},worker_wait=None,forwarded=[],events=[],stop=threading.Event(),watchdog=Watchdog(),super_channel=None,worker_channel=None)
 scope=dict(self=self,life=ns['life'],time=time,Path=Path,receipt_path=receipt,error=OSError(primary or 'control failure'),traceback=traceback,LIMITATIONS=[],c=types.SimpleNamespace(replace_json=replace))
 # Capture exact swallowed exception without changing extracted handler.
 swallowed=[]
 def trace(frame,event,arg):
  if frame.f_code.co_filename=='frozen-executor-failure-extract' and event=='exception':swallowed.append(repr(arg[1]))
  return trace
 import sys
 sys.settrace(trace)
 try:exec(compile(fm,'frozen-executor-failure-extract','exec'),scope)
 finally:sys.settrace(None)
 result=dict(case=case,primary_injection=primary,failed_receipt_write_calls=calls,retained_receipt=json.loads(receipt.read_text()),timing_exists=timing.exists(),timing_manifest_exists=timing.with_suffix('.manifest.json').exists(),swallowed=swallowed)
 results.append(result)
 ns['HASH_OBSERVER']=None
assert results[0]['retained_receipt']['accepted'] is True and not results[0]['failed_receipt_write_calls']
assert 'FileExistsError' in ' '.join(results[0]['swallowed'])
assert results[1]['retained_receipt']['accepted'] is True and not results[1]['failed_receipt_write_calls']
assert results[2]['retained_receipt']['accepted'] is False and len(results[2]['failed_receipt_write_calls'])==1
value={'schema':'source_extracted_failure_publication_discriminator_v1','controller_sha256':hashlib.sha256(s.encode()).hexdigest(),'executor_sha256':hashlib.sha256(es.encode()).hexdigest(),'scope':'2 injected stdlib reporting paths and 1 no-telemetry control; no signals, processes, monitors, ML, inference or campaign','results':results,'candidate_accepted_for_training':False,'acceptance_bypass_claimed':False}
(O/'discriminator-result-v3.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value,indent=2))
