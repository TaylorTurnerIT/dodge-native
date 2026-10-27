"""Independent stdlib ACK edge and actual-worker cancellation-tail probes."""
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import ast,copy,json,signal,sys,types
OUT=Path(__file__).resolve().parent;PREP=OUT.parent/'postovernight-long-D2-prepare-r4';sys.path.insert(0,str(PREP))
import long_d2 as c
import lifecycle as life
results=[]
def run(mode, cancellation=False):
 events=[];clock=[1.0]
 learner=types.SimpleNamespace(api=types.SimpleNamespace(absolute_deadline=7140),model=object(),progress={},checkpoints=[],report=lambda:{},close=lambda:events.append(dict(operation='stream_close')),checkpoint=lambda *a,**k:events.append(dict(operation='checkpoint')))
 class IPC:
  def send(self,value,deadline):events.append(dict(operation='failure_send',learner_deadline=learner.api.absolute_deadline,deadline=deadline))
  def receive(self,deadline):
   value=dict(kind='failure_ack',t0_monotonic_hex=0.0.hex(),first_monotonic_hex=0.0.hex(),cleanup_until_monotonic_hex=10.0.hex());fds=[]
   if mode=='wrong-kind':value['kind']='start_ack'
   if mode=='wrong-T0':value['t0_monotonic_hex']=1.0.hex()
   if mode=='future-first':value['first_monotonic_hex']=2.0.hex()
   if mode=='nonfinite-first':value['first_monotonic_hex']='inf'
   if mode=='before-T0':value['first_monotonic_hex']=(-1.0).hex()
   if mode=='missing-deadline':del value['cleanup_until_monotonic_hex']
   if mode=='FD':fds=[99]
   if mode=='expired':clock[0]=10.0
   if mode=='missing':raise TimeoutError('controlled missing ACK')
   return value,fds
 latch=life.ProcessLatch();latch.deadline=7140
 guard=types.SimpleNamespace(failure_at=0.0,close=lambda:None,receipt=lambda:{})
 with patch.object(life,'POOL',life.FailurePool(0.0)),patch.object(life,'ACTIVE',latch),patch.object(life,'CHANNEL',IPC()),patch.object(life.time,'monotonic',lambda:clock[0]):
  if cancellation:
   latch.record(signal.SIGINT)
   source=(PREP/'long_d2.py').read_text();worker=copy.deepcopy(next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='worker'))
   body=next(n for n in worker.body if isinstance(n,ast.With)).body[0]
   body.body=ast.parse("learner=probe_learner\nguard=probe_guard\nresult=outcome_fields('budget_closed_below_gate',True)").body
   verify=next(n for n in worker.body if isinstance(n,ast.FunctionDef) and n.name=='verify');verify.body=ast.parse('pass').body
   module=ast.fix_missing_locations(ast.Module(body=[worker],type_ignores=[]))
   namespace=dict(vars(c));namespace.update(probe_learner=learner,probe_guard=guard,save=lambda path,value:events.append(dict(operation='write',path=path.name,status=value.get('experiment_status') if isinstance(value,dict) else None)),check_module_origins=lambda *a:{})
   exec(compile(module,'actual_R4_worker_cancellation_tail','exec'),namespace)
   code=namespace['worker'](types.SimpleNamespace(started=0.0,output=OUT/'never-created'),({'run_id':'probe'}, {}, {}, {}, {}, {'identity_sha256':'c'*64}))
   assert code==1
   writes=[x for x in events if x['operation']=='write'];assert bool(writes)==(mode=='valid')
   assert all(x['status']=='failed' for x in writes if x['path']=='long-worker-result.json')
   row=dict(mode=mode,cancellation=True,code=code,events=events,deadline=learner.api.absolute_deadline)
  else:
   result=c.outcome_fields('budget_closed_below_gate',True);permission=dict(failed=False,ack_failed=False,acknowledged_until=None)
   ok=c.worker_failure(c.Stop('injected'),types.SimpleNamespace(),guard,learner,result,permission)
   assert ok is False and permission['ack_failed'] and result['experiment_status']=='failed'
   try:c.worker_write_permission(types.SimpleNamespace(started=0),result,permission,learner)
   except c.Stop:pass
   else:raise AssertionError('Invalid ACK permitted persistence')
   sends=len(events);assert not c.worker_failure(c.Stop('second'),types.SimpleNamespace(),guard,learner,result,permission)
   assert len(events)==sends,'ACK retried after permanent failure'
   row=dict(mode=mode,cancellation=False,events=events,permission=permission,deadline=learner.api.absolute_deadline)
  results.append(row)
 for e in events:
  if e['operation']=='failure_send':assert e['learner_deadline']<=10
for mode in ('wrong-kind','wrong-T0','future-first','nonfinite-first','before-T0','missing-deadline','FD','expired'):run(mode)
for mode in ('valid','missing'):run(mode,cancellation=True)
with (OUT/'worker-edges.json').open('x') as f:json.dump(dict(successful=True,scenarios=results,ML_imports=[n for n in sys.modules if n.split('.')[0] in ('torch','numpy','dodge_rl')]),f,indent=2);f.write('\n')
print(json.dumps(dict(successful=True,ACK_edge_cases=8,actual_worker_cancellation_tail_cases=2,real_ML=False)))
