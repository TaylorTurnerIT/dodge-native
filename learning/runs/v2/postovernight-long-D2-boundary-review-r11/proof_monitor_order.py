"""Independent old/new scheduling discriminator; fake process table only."""
from extract import *
import copy,json

osfake=NS(getpid=lambda:150,waitstatus_to_exitcode=os.waitstatus_to_exitcode)
selectfake=NS()
namespace=dict(c=c,life=life,owned=owned,time=clock,math=math,os=osfake,json=json,
               signal=signal,threading=threading,select=selectfake,NORMAL_SECONDS=7200)
extract('long_d2_executor.py',{'Execution'},namespace)
New=namespace['Execution']
old_path=H.parent/'postovernight-long-D2-boundary-prepare-r11/r10-source/long_d2_executor.py'
old_source=old_path.read_text()
old_node=next(n for n in ast.parse(old_source).body if isinstance(n,ast.ClassDef) and n.name=='Execution')
old_namespace=dict(namespace)
exec(compile(ast.Module(body=[old_node],type_ignores=[]),str(old_path),'exec'),old_namespace)
Old=old_namespace['Execution']

def run(cls,deliver=True):
    clock.value=100.;x=cls.__new__(cls);x.t0=90.;x.pool=life.FailurePool(90.)
    x.events=[];x.forwarded=[];x.ipc_lock=threading.RLock();x.worker_wait=x.inner_ready=x.worker_ready=None
    x.guard=NS(failure=None,failure_at=None,last_sample=100.)
    x.latch=NS(first_cancel_at=None,first_alarm_at=None,deadline=7290.,cancellation_requests=0,
               requested_signal=None,phase='NORMAL');life.ACTIVE=ln['ACTIVE']=x.latch
    x.recovery_proven=True;x.cleanup_complete=False
    x.groups={role:dict(pid=pid,pgid=pid,new_session_verified=True,parent_at_registration=parent,
                       term_sent=False,kill_sent=False,group_absent=False)
              for role,pid,parent in [('supervisor',200,150),('worker',300,200)]}
    states={200:'alive',300:'alive'};queue=[];signals=[];reports=[];reads=[]
    def direct(pid,parent):
        return dict(pid=pid,reaped_by=parent,direct_child_reaped=True,raw_wait_status=9,
                    returncode=-9,observed_monotonic=clock.value)
    class Child:
        process=NS(pid=200);report=None
        def poll(self):
            if self.report is None and states[200]=='zombie':
                self.report=direct(200,150);states[200]='gone'
            return self.report
    x.child=Child()
    class Super:
        sock=NS(fileno=lambda:9)
        def receive(self,deadline):reads.append(('supervisor',clock.value));return queue.pop(0),[]
    class Worker:
        sock=NS(fileno=lambda:10)
        def receive(self,deadline):reads.append(('worker',clock.value));raise ConnectionResetError('modeled dead worker endpoint')
    x.super_channel=Super();x.worker_channel=Worker()
    def sig(record,number):
        key='term_sent' if number==signal.SIGTERM else 'kill_sent'
        if record[key]:return
        record[key]=True;pid=record['pid'];signals.append((pid,int(number),clock.value))
        if number==signal.SIGKILL:
            states[pid]='zombie'
            # Model init's eventual orphan reap as immediate. It supplies no
            # direct report to executor and cannot make worker_wait non-null.
            if states[200]!='alive' and states[300]=='zombie':states[300]='gone'
    owned.signal_once=sig;owned.absent=lambda pid,deadline:states[pid]=='gone'
    selectfake.select=lambda socks,*a:(([x.super_channel.sock] if queue else [])+
                                     ([x.worker_channel.sock] if states[300]!='alive' else []),[],[])
    class Ticks:
        def wait(self,*a):
            clock.value=round(clock.value+.02,6);x.guard.last_sample=clock.value
            # Explicit model assumption: responsive living supervisor polls its
            # worker once on the next tick and queues its validated report.
            if deliver and states[200]=='alive' and states[300]=='zombie':
                r=direct(300,200);reports.append(copy.deepcopy(r));states[300]='gone'
                queue.append(dict(kind='worker_wait',sender=200,report=r,t0_monotonic_hex=x.t0.hex()))
            if clock.value>110.02:raise AssertionError('cleanup deadline lost')
            return x.cleanup_complete
    x.stop=Ticks()
    osfake._exit=lambda code:(_ for _ in ()).throw(AssertionError('unexpected bounded-cleanup expiry'))
    x.fail(c.Stop('explicit cutoff','wall_guard'),100.)
    x.monitor()
    return dict(signals=signals,worker_wait=x.worker_wait,inner_wait=x.child.report,
                first=x.pool.first,until=x.pool.until,final_clock=clock.value,
                cleanup_complete=x.cleanup_complete,events=x.events,reads=reads,
                supplied_model_direct_reports=reports)

old=run(Old);new=run(New);lost=run(New,False)
def kills(value):return {p:t for p,s,t in value['signals'] if s==int(signal.SIGKILL)}
assert kills(old)=={200:105.,300:105.} and old['worker_wait'] is None
assert kills(new)[300]==105. and kills(new)[200]>new['worker_wait']['observed_monotonic']>105.
assert new['worker_wait']['reaped_by']==200 and new['worker_wait']['returncode']==-9
assert new['cleanup_complete'] and new['final_clock']<new['until']
assert kills(lost)[200]==109.5 and lost['worker_wait'] is None
assert all(v['until']==110. and v['final_clock']<110. for v in (old,new,lost))
result=dict(old=old,new=new,no_report=lost,extractions=extractions,
            old_class_source=dict(path=str(old_path),line=old_node.lineno,end_line=old_node.end_lineno),
            limits='Exact old/new Execution.monitor/pump/fail and new kill_due; real FailurePool/direct-report validator. Supervisor polling, process table, direct reports, signals, endpoint readiness/reset and absence are modeled. This is control-flow ordering, never actual direct-reap, datagram delivery, native execution or OS closure evidence.')
(H/'monitor-order-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(old_kills=kills(old),new_kills=kills(new),lost_kills=kills(lost),
                      new_worker_wait=new['worker_wait'],passed=True),indent=2))
