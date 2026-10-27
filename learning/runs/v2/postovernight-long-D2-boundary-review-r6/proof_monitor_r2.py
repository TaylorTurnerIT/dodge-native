"""Exact AST-extracted monitor/failure code, deterministic stdlib dependencies.

No processes, signals, threads, project imports, ML, or production writes.
"""
from pathlib import Path
from types import SimpleNamespace as NS
import ast
import json
import math
import signal
import threading

H=Path(__file__).resolve().parent
SOURCE=H.parent/'postovernight-long-D2-boundary-prepare-r6'
clock=NS(value=100.,monotonic=lambda:clock.value)

def extract(path,names,namespace):
    tree=ast.parse(path.read_text())
    nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    assert {n.name for n in nodes}==set(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    return namespace

life=NS(ACTIVE=None)
ln=extract(SOURCE/'lifecycle.py',{'Stop','FailurePool'},dict(time=clock,math=math,threading=threading))
life.Stop=ln['Stop'];life.FailurePool=ln['FailurePool']
cn=extract(SOURCE/'long_d2.py',{'require','failure_outcome','observed_failure'},dict(Stop=life.Stop,time=clock,life=life,signal=signal))
c=NS(**{k:cn[k] for k in ('require','failure_outcome','observed_failure')},Stop=life.Stop,WORKER_SECONDS=7140,INNER_SECONDS=7170,Guard=object)
class UnexpectedExit(Exception):pass
class Once:
    def __init__(self):self.n=0
    def wait(self,seconds):self.n+=1;return self.n>1
signals=[]
owned=NS(signal_once=lambda r,n:signals.append(int(n)),absent=lambda *a:True)
en=extract(SOURCE/'long_d2_executor.py',{'Execution'},dict(c=c,life=life,time=clock,owned=owned,signal=signal,NORMAL_SECONDS=7200,os=NS(_exit=lambda code:(_ for _ in ()).throw(UnexpectedExit(code))),threading=threading))
Execution=en['Execution']
def fresh():
    x=Execution.__new__(Execution);x.t0=90.;x.pool=life.FailurePool(x.t0)
    x.latch=NS(first_at=None,first_cancel_at=None,first_alarm_at=None,deadline=7290.,cancellation_requests=0,requested_signal=None,phase='NORMAL')
    x.guard=NS(failure=None,failure_at=None,last_sample=100.)
    x.super_channel=None;x.groups={'supervisor':dict(pid=200,pgid=200)}
    x.recovery_proven=True;x.child=None;x.worker_wait=None;x.forwarded=[];x.stop=Once()
    life.ACTIVE=x.latch
    return x

results={}
# A direct parent's Child.poll has already retained a nonzero report. The
# watchdog sees the same immutable report on its next tick.
x=fresh();report=dict(pid=200,reaped_by=150,direct_child_reaped=True,raw_wait_status=256,returncode=1,observed_monotonic=99.75)
x.child=NS(report=report,poll=lambda:report)
x.monitor()
results['retained_raw_failure']=dict(source_observation=99.75,monitor_clock=clock.value,expected_pool_until=109.75,actual_pool_until=x.pool.until,actual_first=x.pool.first,descriptor=x.pool.first_global)
assert x.pool.first==100. and x.pool.until==110.
assert x.pool.first>report['observed_monotonic']
# A source-stamped failure through the very same fail entry proves the pool
# can retain the original time. Only the actual monitor call drops it.
y=fresh();y.fail(c.Stop('Inner raw failure','publication_failure'),99.75)
results['explicit_source_control']=dict(first=y.pool.first,until=y.pool.until)
assert y.pool.first==99.75 and y.pool.until==109.75
# An early SIGALRM is recorded during deferred finalization, then a SIGTERM
# arrives before the watchdog's next iteration. first_at belongs to SIGALRM.
x=fresh();x.latch.first_at=x.latch.first_alarm_at=99.5
x.latch.first_cancel_at=99.75;x.latch.cancellation_requests=1;x.latch.requested_signal=signal.SIGTERM
report=dict(returncode=0);x.child=NS(report=report,poll=lambda:report)
x.monitor()
results['alarm_then_cancel_actual_monitor']=dict(alarm_at=99.5,cancel_at=99.75,actual_first=x.pool.first,descriptor=x.pool.first_global)
assert x.pool.first_global['timestamp']==99.5
assert x.pool.first_global['outcome']=='cancelled'
y=fresh();y.latch.first_at=y.latch.first_alarm_at=99.5;y.latch.first_cancel_at=99.75;y.latch.cancellation_requests=1;y.latch.requested_signal=signal.SIGTERM
y.fail(c.Stop('Executor recorded cancellation','cancelled'),y.latch.first_cancel_at)
results['correct_cancel_source_control']=dict(first=y.pool.first,descriptor=y.pool.first_global)
assert y.pool.first_global['outcome']=='wall_guard'
(H/'monitor-proof-r2-results.json').write_text(json.dumps(results,indent=2,allow_nan=False)+'\n')
print(json.dumps(results,indent=2,allow_nan=False))
