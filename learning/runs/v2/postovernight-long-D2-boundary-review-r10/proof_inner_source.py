"""Exact source-extracted worker-report path. Synthetic processes/clock/IPC only."""
from pathlib import Path
from types import SimpleNamespace as NS
import ast,copy,io,json,math,os,signal,threading
H=Path(__file__).resolve().parent
B=H/'snapshot'
clock=NS(value=99.75)
clock.monotonic=lambda:clock.value
clock.sleep=lambda seconds:setattr(clock,'value',clock.value+seconds)
extracted={}
def extract(file,names,namespace):
    source=(B/file).read_text();nodes=[n for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    assert {n.name for n in nodes}==set(names)
    extracted[file]=extracted.get(file,[])+[dict(name=n.name,line=n.lineno,end_line=n.end_lineno) for n in nodes]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(B/file),'exec'),namespace)
ln=dict(time=clock,math=math,threading=threading,ACTIVE=None,CHANNEL=None,POOL=None)
extract('lifecycle.py',{'Stop','FailurePool','remaining','notify_failure'},ln)
life=NS(**ln)
life.OWNED={signal.SIGINT,signal.SIGTERM,signal.SIGALRM}
life.POOL=ln['POOL']=life.FailurePool(90.)
latch=NS(first_cancel_at=None,first_alarm_at=None,deadline=7260.,phase='NORMAL',requested_signal=None,check=lambda:None)
life.ACTIVE=ln['ACTIVE']=latch
actual_parent=os.getpid()
report=dict(pid=300,reaped_by=actual_parent,direct_child_reaped=True,raw_wait_status=256,returncode=1,observed_monotonic=99.75)
events=[];packets=[];receipts=[]
class FakeChild:
    def __init__(self,p):self.process=p;self.report=None
    def poll(self):
        events.append(dict(kind='direct_wait_observed',time=clock.value));self.report=report;clock.value=100.;return report
class Guard:
    failure=failure_at=thread=verify_thread=None
    def __init__(self,*a):self.event=NS(set=lambda:None)
    def start(self):pass
    def check(self):pass
class Channel:
    sock=NS(close=lambda:None)
    def send(self,value,deadline):
        packets.append(copy.deepcopy(value));events.append(dict(kind=value['kind'],time=clock.value))
        if value['kind']=='worker_wait':clock.value=99.9
    def receive(self,deadline,*a):
        if life.POOL.until is None:return dict(kind='registered',worker_pid=300),[]
        return dict(kind='failure_ack',t0_monotonic_hex=(90.).hex(),first_monotonic_hex=life.POOL.first.hex(),cleanup_until_monotonic_hex=life.POOL.until.hex(),descriptor=life.POOL.first_global),[]
life.CHANNEL=ln['CHANNEL']=Channel()
def absent(*a):
    clock.value=100.;events.append(dict(kind='positive_absence_synthetic',time=clock.value));return True
def missing_worker_result(path):raise FileNotFoundError(str(path))
def mandatory(path,result,until):receipts.append((path.name,copy.deepcopy(result)))
ns=dict(Path=Path,Stop=life.Stop,life=life,owned=NS(Child=FakeChild,absent=absent),io=io,Guard=Guard,
        ROOT=H,ORIGINAL_ROOT=H,STATE_PATH=H/'state.json',INNER_SECONDS=7170,WORKER_SECONDS=7140,
        time=clock,signal=NS(SIG_BLOCK=0,SIG_SETMASK=1,pthread_sigmask=lambda *a:None),
        os=NS(getpid=lambda:actual_parent,environ={}),sys=NS(executable='synthetic-python'),
        subprocess=NS(Popen=lambda *a,**kw:NS(pid=300)),__file__=str(B/'long_d2.py'),PROTOCOL_SHA256='synthetic',
        integrity=NS(),capsule_context=lambda *a:None,assert_lease=lambda *a:None,
        read_json=missing_worker_result,mandatory_failure=mandatory,optional_timing=lambda *a:None)
extract('long_d2.py',{'require','failure_outcome','outcome_fields','result_code','provisional','observed_failure','worker_raw_failure','supervise_owned'},ns)
# Real wait validation is extracted too; never call real waitpid or killpg.
pn=dict(os=os)
source=Path('learning/runs/v2/postovernight-long-D2-boundary-prepare-r9/processes.py').read_text()
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='validate_report')
pn['life']=life;exec(compile(ast.Module(body=[node],type_ignores=[]),'processes.py','exec'),pn)
ns['owned'].validate_report=pn['validate_report']
lease=dict(identity_sha256='id',capsule_manifest_sha256='cap')
args=NS(output=H/'worker-raw-fixture-r10',state_path=H/'state.json',executor_pid=200)
code,_=ns['supervise_owned'](args,90.,lease,NS(fileno=lambda:9,close=lambda:None),
    context_provider=lambda *a,**kw:(dict(output='worker-raw-fixture-r10',run_id='synthetic'),{},{},{},{},lease),guard_factory=Guard)
print(json.dumps(dict(code=code,first=life.POOL.first,until=life.POOL.until,events=events,packets=packets,receipts=receipts),indent=2))
assert code==1
assert report['observed_monotonic']==99.75
assert life.POOL.first==99.75 and life.POOL.until==109.75
assert any(p['kind']=='worker_wait' and p['report']==report for p in packets)
assert sum(p['kind']=='worker_wait' for p in packets)==1
assert 'Worker raw/outcome failure' in receipts[0][1]['error']
assert events.index(next(x for x in events if x['kind']=='worker_wait'))>events.index(next(x for x in events if x['kind']=='failure'))
control=life.FailurePool(90.)
control.fail(life.Stop('raw worker failure','publication_failure'),99.75,
             dict(timestamp=99.75,kind='direct_wait_observation',outcome='publication_failure'))
assert control.first==99.75 and control.until==109.75
result=dict(verdict='r9_source_timestamp_defect_repaired',raw_inner_code=code,worker_report=report,
            first_failure=life.POOL.first,cleanup_until=life.POOL.until,descriptor=life.POOL.first_global,
            expected_first=99.75,expected_until=109.75,control_first=control.first,control_until=control.until,
            events=events,packets=packets,receipts=receipts,extracted=extracted,
            limits='Exact supervise_owned/observed_failure/notify_failure/FailurePool; synthetic child/channel/clock/absence. No OS, ML, native, training, or acceptance evidence.')
(H/'worker-raw-proof-results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:result[k] for k in ('verdict','first_failure','cleanup_until','expected_first','expected_until','descriptor')},indent=2))
