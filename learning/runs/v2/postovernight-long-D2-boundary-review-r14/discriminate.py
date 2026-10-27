"""Bounded source-extracted chronology discriminator. No project imports or OS signal delivery."""
import ast,contextlib,hashlib,json,math,pathlib,signal,sys,threading,time,types
O=pathlib.Path(__file__).resolve().parent; C=O.parent/'postovernight-long-D2-boundary-prepare-r14'; records=[];extractions=[]
clock=[95.]
tm=types.SimpleNamespace(monotonic=lambda:clock[0],thread_time=time.thread_time)
def extract(path,names,namespace):
 source=path.read_text(); tree=ast.parse(source);nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
 assert {n.name for n in nodes}==set(names)
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
 extractions.append(dict(path=str(path),sha256=hashlib.sha256(source.encode()).hexdigest(),nodes=[dict(name=n.name,line=n.lineno,end=n.end_lineno) for n in nodes]))
life=types.ModuleType('extracted_lifecycle');life.__dict__.update(time=tm,math=math,threading=threading,signal=signal,ACTIVE=None,POOL=None,CHANNEL=None)
extract(C/'lifecycle.py',['Stop','FailurePool','ProcessLatch','remaining','notify_failure'],life.__dict__)
real_set=sys.setswitchinterval;real_get=sys.getswitchinterval
class SysView:
 def __init__(self):self.hook=None;self.calls=[]
 def getswitchinterval(self):return real_get()
 def setswitchinterval(self,value):
  self.calls.append(value)
  if self.hook:self.hook(value)
  else:real_set(value)
view=SysView()
def controller(path):
 d=dict(time=tm,sys=view,threading=threading,math=math,signal=signal,life=life,Stop=life.Stop,contextmanager=contextlib.contextmanager,BOUNDARY_SWITCH_INTERVAL=.0001,VERIFY_LOCAL=threading.local(),self_peak=lambda:1,LIMIT=6442450944,WORKER_SECONDS=7140)
 extract(path,['require','failure_outcome','outcome_fields','result_code','observed_failure','primary_error','record_primary_failure','worker_failure','worker_write_permission','restore_boundary_switch_interval','boundary_switch_interval','Guard'],d)
 return types.SimpleNamespace(**d)
r14=controller(C/'long_d2.py');r12=controller(C/'r12-source/long_d2.py')
class ForeignFailure(BaseException):pass
original=real_get()
try:
 # CPython quantization and same-thread nested contexts use real interval operations.
 quant=[]
 for value in [.000001,.000017,.000099,.0001,.000731,.002731,.005,.02]:
  real_set(value);saved=real_get();real_set(.000002);r14.restore_boundary_switch_interval(saved);assert real_get()==saved
  with r14.boundary_switch_interval():
   outer=real_get();assert outer<=.0001
   with r14.boundary_switch_interval():assert real_get()==outer
   assert real_get()==outer
  assert real_get()==saved;quant.append(dict(requested=value,saved=saved,restored=real_get()))
 records.append(dict(case='actual_CPython_quantization_and_nested_LIFO',rows=quant))
 # Main-thread ownership fails before interval mutation.
 view.calls=[];errors=[]
 def foreign():
  try:
   with r14.boundary_switch_interval():raise AssertionError('Non-main callback entered')
  except BaseException as e:errors.append(repr(e))
 thread=threading.Thread(target=foreign);thread.start();thread.join(2)
 assert not thread.is_alive() and len(errors)==1 and 'main-thread ownership' in errors[0] and not view.calls
 records.append(dict(case='nonmain',errors=errors,setters=view.calls,thread_absent=True))
 def case(label,module=r14,kind='stop',cleanup='cancel',after_set=False,prior=None,descriptor=None,peer=None,ack=True,cap=None):
  clock[0]=95.;real_set(.002731);saved=real_get();life.ACTIVE=life.ProcessLatch();life.ACTIVE.deadline=200.;life.POOL=life.FailurePool(90.,outer_seconds=7200 if cap is None else cap)
  callback_error=life.Stop('callback','resource_stop') if kind=='stop' else ForeignFailure('callback') if kind=='foreign' else None
  if descriptor is not None:callback_error.first_failure_descriptor=dict(descriptor)
  count=[0];injected=[False];calls=[]
  guard=None
  def callback():
   count[0]+=1;calls.append(real_get());assert calls[-1]<=.0001
   if prior=='guard':guard.failure_at=98.;guard.failure=life.Stop('earlier guard','resource_stop')
   clock[0]=100.
   if callback_error is not None:raise callback_error
   return 'verified'
  guard=module.Guard(200.,lambda:None,callback,None,clock=lambda:clock[0],rss=lambda:1,peak=lambda:1)
  if prior in ('cancel','alarm'):
   clock[0]=97.;life.ACTIVE.record(signal.SIGTERM if prior=='cancel' else signal.SIGALRM);clock[0]=95.
  if peer:
   clock[0]=peer['timestamp'];life.POOL.fail(life.Stop('peer','resource_stop'),descriptor=peer,peer=True);clock[0]=95.
  def setter(value):
   if cleanup and value==saved and not injected[0]:
    injected[0]=True;clock[0]=101.
    if after_set:real_set(value)
    if cleanup=='foreign':raise ForeignFailure('cleanup')
    life.ACTIVE.handle(signal.SIGTERM if cleanup=='cancel' else signal.SIGALRM,None)
   real_set(value)
  view.hook=setter;raised=None
  try:
   guard.full_check(True)
  except BaseException as error:raised=error
  finally:view.hook=None
  assert real_get()==saved and count[0]==1
  if callback_error is None and cleanup is None:
   assert raised is None and guard.failure is None and guard.boundaries[0]['verdict']=='passed'
   row=dict(case=label,verdict='passed',callback_count=1,restored=True);records.append(row);return
  assert raised is not None and guard.boundaries[0]['verdict']=='failed' and 'observation' not in guard.boundaries[0]
  primary,desc=module.observed_failure(raised,guard,'worker');result={};permission={'failed':False,'acknowledged_until':None,'ack_failed':False}
  class Channel:
   def send(self,value,deadline):self.sent=value
   def receive(self,deadline):return dict(kind='failure_ack',t0_monotonic_hex=life.POOL.t0.hex(),first_monotonic_hex=life.POOL.first.hex(),cleanup_until_monotonic_hex=life.POOL.until.hex(),descriptor=life.POOL.first_global),[]
  life.CHANNEL=Channel() if ack else None
  acknowledged=module.worker_failure(raised,types.SimpleNamespace(),guard,None,result,permission)
  expected=101. if module is r12 or kind=='success' else descriptor['timestamp'] if descriptor is not None else 100.
  if prior in ('cancel','alarm'):expected=min(expected,97.)
  if prior=='guard':expected=min(expected,98.)
  expected_global=min(expected,peer['timestamp']) if peer else expected
  assert desc['timestamp']==expected,(label,desc,expected)
  assert life.POOL.first==expected_global and life.POOL.until==min(expected_global+10.,life.POOL.cap),(label,life.POOL.__dict__)
  assert acknowledged==ack and permission['ack_failed']==(not ack)
  assert result['experiment_status']=='failed' and result['expected_exit_code']==1
  if module is r14 and callback_error is not None and cleanup is not None:
   assert raised is callback_error and raised.__cause__ is not None
   assert 'cleanup_error' in guard.boundaries[0]
  if cleanup in ('cancel','alarm'):
   assert (life.ACTIVE.first_cancel_at if cleanup=='cancel' else life.ACTIVE.first_alarm_at)==101. or prior==cleanup
  if not ack:
   try:module.worker_write_permission(types.SimpleNamespace(started=90.),result,permission)
   except life.Stop:pass
   else:raise AssertionError('Unacknowledged write allowed')
  records.append(dict(case=label,raised=repr(raised),cause=repr(raised.__cause__),descriptor=desc,global_descriptor=life.POOL.first_global,until=life.POOL.until,guard_failure_at=guard.failure_at,worker_outcome=result['outcome'],acknowledged=acknowledged,permission=permission,boundary=guard.boundaries[0],callback_count=count[0],restored=True))
 case('success_callback',kind='success',cleanup=None)
 case('r12_negative_control',module=r12)
 for kind in ['stop','foreign']:
  for cleanup in ['cancel','alarm','foreign']:
   for after in [False,True]:case(kind+'_'+cleanup+('_after_set' if after else '_before_set'),kind=kind,cleanup=cleanup,after_set=after)
 for prior in ['guard','cancel','alarm']:case('earlier_'+prior,prior=prior)
 d=dict(timestamp=96.,kind='peer_failure_observed',outcome='resource_stop',role='peer',timing_basis='peer_catch_observation',signal=None)
 case('original_descriptor',descriptor=d)
 case('earlier_peer_pool',peer=d)
 case('callback_without_cleanup',cleanup=None)
 case('cleanup_only_cancel',kind='success')
 case('cleanup_only_alarm',kind='success',cleanup='alarm')
 case('missing_ack_forbids_writes',ack=False)
 case('original_pool_cap_stays_tighter',cap=8.)
 assert not any(n.split('.')[0] in {'torch','numpy','dodge_rl','long_d2','lifecycle'} for n in sys.modules)
finally:
 view.hook=None;r14.restore_boundary_switch_interval(original)
assert real_get()==original
value=dict(status='passed',records=records,extractions=extractions,original_interval=original,final_interval=real_get(),limitations=['Extracted exact source nodes, modeled clock and direct ProcessLatch.handle only; no project imports, OS signals, IPC transport, real cleanup or suite rerun.','Successful ACK channel is modeled; missing ACK exercises actual write rejection.'])
(O/'discriminator-results.json').write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');print(json.dumps({'status':'passed','records':len(records),'source_extractions':len(extractions)}))
