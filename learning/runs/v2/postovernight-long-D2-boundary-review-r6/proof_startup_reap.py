"""Exact inner exception path after worker Popen; synthetic stdlib dependencies.

No process, signal, thread, or ML operation occurs. Fake Popen returns an owned
leader token; real supervise_owned and fixture predicate decide reporting.
"""
from pathlib import Path
from types import SimpleNamespace as NS
from contextlib import contextmanager
import ast,io,json,math,signal,threading,traceback
H=Path(__file__).resolve().parent;B=H.parent/'postovernight-long-D2-boundary-prepare-r6';D=H/'startup-reap-fixture';D.mkdir()
events=[];clock=NS(monotonic=lambda:100.)
def extract(path,names,ns):
    nodes=[n for n in ast.parse(path.read_text()).body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names]
    assert {n.name for n in nodes}==set(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),ns)
ln= dict(time=clock,math=math,threading=threading)
extract(B/'lifecycle.py',{'Stop','FailurePool','remaining'},ln)
life=NS(Stop=ln['Stop'],remaining=ln['remaining'],OWNED={signal.SIGINT,signal.SIGTERM,signal.SIGALRM},POOL=ln['FailurePool'](90.),ACTIVE=NS(phase='NORMAL',check=lambda:None))
class FakeChild:
    def __init__(self,process):self.process=process;self.report=None;events.append('Child_created')
    def poll(self):events.append('Child_poll');return None
owned=NS(Child=FakeChild)
class Guard:
    failure=None;failure_at=None;thread=verify_thread=None
    event=NS(set=lambda:events.append('guard_stop'))
    def __init__(self,*a):pass
    def start(self):events.append('guard_started')
    def check(self):pass
class Channel:
    sock=NS(close=lambda:events.append('IPC_close'))
    def send(self,value,deadline):
        events.append(value['kind'])
        raise life.Stop('Cancellation latched','cancelled')
life.CHANNEL=Channel()
def notify(error,at):
    events.append('failure_ACK')
    return life.POOL.fail(error,at,error.first_failure_descriptor)
life.notify_failure=notify
os=NS(getpid=lambda:200,environ={},pthread_sigmask=None)
sig=NS(SIG_BLOCK=0,SIG_SETMASK=1,pthread_sigmask=lambda *a:None)
def popen(*a,**kw):events.append('worker_Popen_returned');return NS(pid=300)
subprocess=NS(Popen=popen)
ns=dict(Path=Path,Stop=life.Stop,life=life,owned=owned,io=io,Guard=Guard,ROOT=D,ORIGINAL_ROOT=D,STATE_PATH=D/'state.json',INNER_SECONDS=7170,WORKER_SECONDS=7140,time=clock,traceback=traceback,signal=sig,os=os,sys=NS(executable='fixture-python'),subprocess=subprocess,__file__=str(B/'long_d2.py'),PROTOCOL_SHA256='fixture',integrity=NS(),capsule_context=lambda *a:None,assert_lease=lambda *a:None)
extract(B/'long_d2.py',{'require','failure_outcome','outcome_fields','result_code','provisional'},ns)
def observed(error,guard,role):
    descriptor=dict(timestamp=100.,kind='cancel',outcome='cancelled',role=role,timing_basis='synthetic_source',signal=15)
    error.first_failure_descriptor=descriptor
    return error,descriptor
ns['observed_failure']=observed
receipts=[]
def mandatory(path,result,until):events.append('mandatory');receipts.append(dict(result))
ns['mandatory_failure']=mandatory;ns['optional_timing']=lambda *a:events.append('optional')
extract(B/'long_d2.py',{'supervise_owned'},ns)
lease=dict(identity_sha256='id',capsule_manifest_sha256='cap');p=dict(output='campaign',run_id='fixture')
args=NS(output=D/'campaign',state_path=D/'state.json',executor_pid=150)
code,_=ns['supervise_owned'](args,90.,lease,NS(fileno=lambda:9,close=lambda:events.append('gate_close')),context_provider=lambda *a,**kw:(p,{},{},{},{},lease),guard_factory=Guard)
assert code==1 and len(receipts)==1
receipt=receipts[0]
assert 'worker_Popen_returned' in events and 'Child_created' in events
assert 'Child_poll' not in events and 'worker_wait' not in events
assert receipt['worker_wait'] is None and receipt['owned_worker_reaped'] is False
# The repaired fixture explicitly requires a direct wait when that worker was
# spawned. This is the source mismatch, not an OS execution or absence proof.
fn={};extract(B/'fixture_guards.py',{'validate_fixture'},fn)
fixture_receipt={'ownership':{'worker':{'pid':300}},'worker_wait':receipt['worker_wait']}
fixture_events=[dict(kind='owned_spawn',owned_role='worker',pid=300,monotonic=100.)]
try:fn['validate_fixture'](fixture_receipt,fixture_events,{'worker':True},{},receipt_available=True)
except AssertionError as e:rejection=str(e)
else:raise AssertionError('fixture unexpectedly accepted missing direct reap')
result=dict(raw_inner_result=code,events=events,worker_wait=receipt['worker_wait'],owned_worker_reaped=receipt['owned_worker_reaped'],cleanup_complete=receipt['cleanup_complete'],fixture_rejection=rejection,limits='Fake process/ACK/clock/IO only; no OS closure or survivors demonstrated. Actual failure branch and fixture predicate are exact extracted source.')
(H/'startup-reap-proof-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
