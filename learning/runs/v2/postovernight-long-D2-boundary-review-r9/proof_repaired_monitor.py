"""Focused current monitor discriminator; fake clock/child/latch, no OS calls."""
from pathlib import Path
from types import SimpleNamespace as NS
import ast,json,math,os,signal,threading
H=Path(__file__).resolve().parent;B=H/'snapshot';clock=NS(monotonic=lambda:100.)
def extract(file,names,namespace):
 nodes=[n for n in ast.parse((B/file).read_text()).body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names]
 assert {n.name for n in nodes}==names
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(B/file),'exec'),namespace)
ln=dict(time=clock,math=math,threading=threading);extract('lifecycle.py',{'Stop','FailurePool'},ln);life=NS(**ln,ACTIVE=None)
cn=dict(Stop=life.Stop,life=life,time=clock,signal=signal);extract('long_d2.py',{'require','failure_outcome','observed_failure'},cn)
c=NS(**{k:cn[k] for k in ('require','failure_outcome','observed_failure')},Stop=life.Stop,WORKER_SECONDS=7140,INNER_SECONDS=7170,Guard=object)
pn=dict(os=os,life=life);extract('processes.py',{'validate_report'},pn)
owned=NS(validate_report=pn['validate_report'],signal_once=lambda *a:None,absent=lambda *a:True)
ns=dict(c=c,life=life,owned=owned,time=clock,os=os,signal=signal,NORMAL_SECONDS=7200)
extract('long_d2_executor.py',{'Execution'},ns);Execution=ns['Execution']
class Once:
 def __init__(self):self.count=0
 def wait(self,*a):self.count+=1;return self.count>1
def run(alarm=None,cancel=None,peer=None):
 x=Execution.__new__(Execution);x.t0=90.;x.pool=life.FailurePool(90.);x.forwarded=[];x.stop=Once();x.super_channel=None
 x.latch=NS(first_at=alarm,first_cancel_at=cancel,first_alarm_at=alarm,deadline=7290.,cancellation_requests=int(cancel is not None),requested_signal=signal.SIGTERM,phase='NORMAL')
 life.ACTIVE=x.latch
 x.guard=NS(failure=None,failure_at=None,last_sample=100.)
 report=dict(pid=200,reaped_by=os.getpid(),raw_wait_status=256,returncode=1,direct_child_reaped=True,observed_monotonic=99.75)
 x.child=NS(process=NS(pid=200),report=report,poll=lambda:report)
 x.groups={'supervisor':dict(pid=200,pgid=200)};x.recovery_proven=True
 if peer is not None:x.pool.fail('peer',peer,dict(timestamp=peer,kind='peer',outcome='safety_stop'),peer=True)
 x.monitor();return dict(first=x.pool.first,until=x.pool.until,descriptor=x.pool.first_global)
results=dict(raw=run(),alarm_then_cancel=run(99.5,99.75),cancel_then_alarm=run(99.75,99.5),earlier_peer=run(peer=99.25))
assert results['raw']['first']==99.75 and results['raw']['until']==109.75
assert results['raw']['descriptor']['kind']=='direct_wait_observation'
assert results['alarm_then_cancel']['descriptor']['kind']=='alarm' and results['alarm_then_cancel']['first']==99.5
assert results['cancel_then_alarm']['descriptor']['outcome']=='cancelled' and results['cancel_then_alarm']['first']==99.5
assert results['earlier_peer']['first']==99.25 and results['earlier_peer']['until']==109.25
(H/'repaired-monitor-results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
