"""Exact kill_due/monitor source with fake clocks, reports and signal attempts."""
from extract import *
import copy,json,signal
osfake=NS(getpid=lambda:150,waitstatus_to_exitcode=os.waitstatus_to_exitcode)
namespace=dict(c=c,life=life,owned=owned,time=clock,math=math,os=osfake,json=json,
               signal=signal,threading=threading,select=NS(),NORMAL_SECONDS=7200)
extract('long_d2_executor.py',{'Execution'},namespace)
Execution=namespace['Execution']
# Reuse only fixture constructors; never import or rerun the IPC discriminator.
fixture_source=(H/'proof_mixed_endpoints.py').read_text()
fixture_nodes=[n for n in ast.parse(fixture_source).body
               if isinstance(n,ast.FunctionDef) and n.name in {'execution','descriptor'}]
exec(compile(ast.Module(body=fixture_nodes,type_ignores=[]),'fixture_constructors','exec'),globals())

def report(pid,parent,at,raw=9):
    return dict(pid=pid,reaped_by=parent,direct_child_reaped=True,raw_wait_status=raw,
                returncode=osfake.waitstatus_to_exitcode(raw),observed_monotonic=at)

rows=[]
x=execution();x.pool.fail('source',100.,descriptor(100.,'outer'))
for at in (100.,104.999,105.,109.499,109.5):
    clock.value=at
    worker=x.kill_due('worker');supervisor=x.kill_due('supervisor')
    assert worker==('original_cutpoint' if at>=105. else None)
    assert supervisor==('latest_bound' if at>=109.5 else None)
    rows.append(dict(case='unknown_worker_report',at=at,worker=worker,supervisor=supervisor))
x.child=None;clock.value=105.
assert x.kill_due('supervisor') is None
x.groups.pop('worker')
assert x.kill_due('supervisor') is None
rows.append(dict(case='child_None_and_missing_worker_registration',at=105.,supervisor=None))
x=execution();x.pool.fail('source',100.,descriptor(100.,'outer'));clock.value=105.
x.worker_wait=report(300,200,104.9)
assert x.kill_due('supervisor')=='validated_worker_wait'
rows.append(dict(case='actual_validated_worker_wait',at=105.,reason=x.kill_due('supervisor')))
for key,value in [('pid',301),('reaped_by',201),('direct_child_reaped',False),
                  ('raw_wait_status',256),('observed_monotonic',106.),('observed_monotonic',True)]:
    x.worker_wait=report(300,200,104.9);x.worker_wait[key]=value
    try:x.kill_due('supervisor')
    except life.Stop as error:rows.append(dict(case='invalid_worker_wait',field=key,error=str(error)))
    else:raise AssertionError(('invalid worker direct proof accepted',key))
x.worker_wait=None;x.child.report=report(200,150,104.9)
assert x.kill_due('supervisor')=='supervisor_reaped'
x.child.process.pid=201
try:x.kill_due('supervisor')
except life.Stop as error:rows.append(dict(case='retained_leader_PID_mismatch',error=str(error)))
else:raise AssertionError('wrong supervisor process released')
x=execution();x.pool.fail('source',100.,descriptor(100.,'outer'));clock.value=104.7
x.pool.fail('late earlier peer',99.5,descriptor(99.5,'worker'),peer=True)
assert x.kill_due('worker')=='original_cutpoint' and x.kill_due('supervisor') is None
clock.value=109.;assert x.kill_due('supervisor')=='latest_bound'
rows.append(dict(case='late_earlier_peer',first=x.pool.first,until=x.pool.until,latest=109.))
x=execution();x.pool=life.FailurePool(90.,outer_seconds=10.);clock.value=109.6
x.pool.fail('cap truncated',109.5,descriptor(109.5,'worker'))
assert x.pool.until==110. and x.kill_due('worker')=='original_cutpoint' and x.kill_due('supervisor')=='latest_bound'
assert x.worker_wait is None
rows.append(dict(case='cap_truncated',first=x.pool.first,until=x.pool.until,truthful_worker_wait=x.worker_wait))

# A permanently throwing gate is exercised before AND after original eligibility.
# Both owned roles remain independent; actual deadline leaf stays outside duties.
class DeadlineExit(BaseException):pass
x=execution();x.pool.fail('source',100.,descriptor(100.,'outer'));signals=[]
x.super_channel=x.worker_channel=None
def broken(role):raise RuntimeError('synthetic gate failure')
x.kill_due=broken
class Ticks:
    def wait(self,*args):
        clock.value=round(clock.value+.02,6);x.guard.last_sample=clock.value
        if clock.value>110.02:raise AssertionError('deadline duty starved')
        return False
x.stop=Ticks();clock.value=100.
def signal_once(rec,number):
    key='term_sent' if number==signal.SIGTERM else 'kill_sent'
    if rec[key]:return
    rec[key]=True;signals.append(dict(pid=rec['pid'],signal=int(number),at=clock.value))
owned.signal_once=signal_once;owned.absent=lambda *args:False
osfake._exit=lambda code:(_ for _ in ()).throw(DeadlineExit(code))
try:x.monitor()
except DeadlineExit as error:assert error.args==(1,)
else:raise AssertionError('deadline exit missing')
kills=[v for v in signals if v['signal']==int(signal.SIGKILL)]
assert {v['pid'] for v in kills}=={200,300}
assert all(v['at']==105. for v in kills)
assert clock.value==110. and not x.cleanup_complete and x.worker_wait is None
assert len([v for v in x.events if v['kind']=='escalation'])==2
assert len([v for v in x.events if v['kind']=='monitor_error'])<=8
monitor=dict(signals=signals,events=x.events,first=x.pool.first,until=x.pool.until,
             exit_at=clock.value,cleanup_complete=x.cleanup_complete,worker_wait=x.worker_wait)
result=dict(gate_cases=rows,persistent_gate_error_monitor=monitor,
            limits='Extracted production gates, monitor, FailurePool and direct-report validation. Fake time/process reports/signals/absence; no real child, socket, signal, OS closure, runtime or acceptance proof.')
(H/'escalation-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(gate_cases=len(rows),persistent_gate_error_monitor=monitor,passed=True),indent=2))
