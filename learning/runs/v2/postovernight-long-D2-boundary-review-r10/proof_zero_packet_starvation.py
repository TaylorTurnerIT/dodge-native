"""Exact pump/monitor; synthetic channels, clock, process reports only."""
from extract import *
import socket,array,stat
channel_ns=dict(time=clock,math=math,threading=threading,os=os,socket=socket,array=array,stat=stat,json=__import__('json'),Stop=life.Stop,remaining=life.remaining)
extract('lifecycle.py',{'Channel'},channel_ns)
Channel=channel_ns['Channel']
import errno,json,copy
osfake=NS(getpid=lambda:150,waitstatus_to_exitcode=os.waitstatus_to_exitcode,_exit=lambda code:(_ for _ in ()).throw(AssertionError('unexpected exit')))
selectfake=NS(select=None)
namespace=dict(c=c,life=life,owned=owned,time=clock,math=math,os=osfake,json=json,signal=signal,threading=threading,select=selectfake,NORMAL_SECONDS=7200)
extract('long_d2_executor.py',{'Execution'},namespace)
Execution=namespace['Execution']
def run(bad_first):
 clock.value=100.;reads=[];sends=[]
 x=Execution.__new__(Execution);x.t0=90.;x.pool=life.FailurePool(90.);x.events=[];x.forwarded=[];x.ipc_lock=threading.RLock()
 x.latch=NS(first_cancel_at=None,first_alarm_at=None,deadline=7290.,cancellation_requests=0,requested_signal=None,phase='NORMAL')
 life.ACTIVE=ln['ACTIVE']=x.latch
 x.guard=NS(failure=None,failure_at=None,last_sample=100.)
 report=dict(pid=200,reaped_by=150,direct_child_reaped=True,raw_wait_status=256,returncode=1,observed_monotonic=99.75)
 x.child=NS(process=NS(pid=200),report=report,poll=lambda:report)
 def group(pid):return dict(pid=pid,pgid=pid,new_session_verified=True,group_absent=False,gate_ack_attempted=True,gate_acked=True,done=False)
 x.groups={'supervisor':group(200),'worker':group(300)}
 x.recovery_proven=True;x.worker_wait=x.inner_ready=x.worker_ready=None
 desc=dict(timestamp=99.5,kind='worker_source',outcome='resource_stop',role='worker',timing_basis='synthetic_actual_observation',signal=None)
 packet=dict(kind='failure',sender=300,t0_monotonic_hex=(90.).hex(),first_monotonic_hex=(99.5).hex(),reason='earlier worker failure',descriptor=desc)
 class EmptySocket:
  def fileno(self):return 9
  def settimeout(self,*a):pass
  def recvmsg(self,*a):reads.append('supervisor');return b'',[],0,None
 broken=Channel.__new__(Channel);broken.sock=EmptySocket();broken.received=0;broken.sent=0;broken.lock=threading.RLock()
 class Valid:
  sock=NS(fileno=lambda:10)
  pending=True
  def receive(self,*a):reads.append('worker');self.pending=False;return copy.deepcopy(packet),[]
  def send(self,value,*a):sends.append(copy.deepcopy(value))
 x.super_channel=broken;x.worker_channel=Valid()
 def ready(sockets,*a):return ([x.super_channel.sock] if bad_first else [])+([x.worker_channel.sock] if x.worker_channel.pending else []),[],[]
 selectfake.select=ready
 class Ticks:
  ticks=0
  def wait(self,*a):self.ticks+=1;clock.value=100.+self.ticks*.02;x.guard.last_sample=clock.value;return self.ticks>10
 x.stop=Ticks()
 x.monitor()
 return dict(first=x.pool.first,until=x.pool.until,descriptor=x.pool.first_global,reads=reads,sends=sends,pending_worker_failure=x.worker_channel.pending,diagnostics=x.events,cleanup_complete=x.cleanup_complete)
starved=run(True);control=run(False)
assert starved['reads']==['supervisor']*10 and starved['pending_worker_failure']
assert (starved['first'],starved['until'])==(99.75,109.75)
assert control['reads']==['worker'] and not control['pending_worker_failure']
assert (control['first'],control['until'])==(99.5,109.5)
assert len(control['sends'])==1 and control['sends'][0]['kind']=='failure_ack'
result=dict(starved=starved,control=control,extractions=extractions,limits='Exact extracted Channel.receive, Execution.monitor/pump/fail and FailurePool/observed_failure. Empty raw datagram provided by fake socket; no kernel transport claim. Fake channels, readiness, clocks, groups, signal sink and direct reports. No real OS lifecycle, transport or acceptance proof.')
(H/'zero-packet-starvation-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
