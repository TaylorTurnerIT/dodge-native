"""Exact one-shot ACK path and preregistered pure fixture predicates."""
from extract import *
import copy,json
osfake=NS(getpid=lambda:150,waitstatus_to_exitcode=os.waitstatus_to_exitcode)
selectfake=NS(select=lambda *a:([],[],[]))
ns=dict(c=c,life=life,owned=owned,time=clock,math=math,os=osfake,json=json,signal=signal,threading=threading,select=selectfake,NORMAL_SECONDS=7200)
extract('long_d2_executor.py',{'Execution','accept_observed'},ns)
Execution=ns['Execution']
clock.value=100.
x=Execution.__new__(Execution);x.t0=90.;x.pool=life.FailurePool(90.);x.events=[];x.forwarded=[]
x.latch=NS(first_cancel_at=None,first_alarm_at=None,deadline=7290.,cancellation_requests=0,requested_signal=None,phase='NORMAL')
life.ACTIVE=x.latch;x.guard=NS(failure=None,failure_at=None,last_sample=100.)
x.child=NS(process=NS(pid=200));x.registration=dict(identity_sha256='id',capsule_manifest_sha256='cap')
x.groups={'worker':dict(pid=300,gate_ack_attempted=False,gate_acked=False,gate_ack_failed=False)}
x.worker_ready=dict(sender=300,supervisor_pid=200,executor_pid=150,protocol_sha256='pin')
c.PROTOCOL_SHA256='pin';x.super_channel=None;x.inner_ready=None;x.worker_wait=None;x.recovery_proven=False
sends=[]
class FailedSend:
 sock=object()
 def send(self,value,*a):sends.append(value);raise TimeoutError('failed start_ack')
x.worker_channel=FailedSend()
try:x.pump()
except TimeoutError:pass
else:raise AssertionError('failed send not raised')
for _ in range(10):x.pump()
assert len(sends)==1 and x.groups['worker']['gate_acked'] is False and x.groups['worker']['gate_ack_failed'] is True
assert (x.pool.first,x.pool.until)==(100.,110.) and not x.recovery_proven
assert ns['accept_observed'](dict(accepted=True),1,1.) is False
fns={};exec(compile((B/'fixture_preconditions.py').read_text(),str(B/'fixture_preconditions.py'),'exec'),fns)
options=fns['preregister'](dict(phase='outer:receipt-before',expectation_class='failed_supervisor_alive'))
positive=dict(kind='injection',role='outer',phase='receipt-before',monotonic=100.,precondition_passed=True,latch_phase='NORMAL',pool_first=None,pool_until=None,first_global_failure=None,guard_failure=None,first_cancel_at=None,first_alarm_at=None,milestones={k:True for k in options['injection_contract']['positive_prerequisites']})
receipt=dict(first_global_failure=dict(timestamp=100.1))
assert fns['validate_injection'](options,[positive],receipt)
rejected=[]
for label,change in [('wrong_phase',{'latch_phase':'FAILURE'}),('earlier_error',{'pool_first':99.5}),('missing_prerequisite',{'milestones':{}})]:
 event=copy.deepcopy(positive);event.update(change)
 try:fns['validate_injection'](options,[event],receipt)
 except AssertionError as error:rejected.append(dict(case=label,error=str(error)))
 else:raise AssertionError(label+' accepted')
case_node=next(n for n in ast.parse((B/'os_checks.py').read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CASES' for t in n.targets))
case_ns={};exec(compile(ast.Module(body=[case_node],type_ignores=[]),'exact_case_registration','exec'),case_ns)
assert len(case_ns['CASES'])==15
for name,opts,expected in case_ns['CASES']:
 fns['preregister'](opts)
result=dict(ACK_sends=len(sends),gate=x.groups['worker'],first=x.pool.first,until=x.pool.until,stale_accepted_receipt_raw1_rejected=True,positive_fixture_predicate=True,rejected=rejected,original_registered_scenarios=len(case_ns['CASES']),limits='Exact extracted pure functions/classes with synthetic clock/channel/latch and event data. No OS injection, process, teacher or acceptance proof.')
(H/'ack-preconditions-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
