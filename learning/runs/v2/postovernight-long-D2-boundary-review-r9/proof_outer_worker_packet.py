"""Exact outer pump consumes a validated nonzero worker wait without latching it."""
from pathlib import Path
from types import SimpleNamespace as NS
import ast,json,math,os,threading
H=Path(__file__).resolve().parent;B=H/'snapshot';clock=NS(monotonic=lambda:100.)
def extract(file,names,namespace):
    nodes=[n for n in ast.parse((B/file).read_text()).body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names]
    assert {n.name for n in nodes}==names
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(B/file),'exec'),namespace)
ln=dict(time=clock,math=math,threading=threading)
extract('lifecycle.py',{'Stop','remaining','FailurePool'},ln);life=NS(**ln)
cn=dict(Stop=life.Stop)
extract('long_d2.py',{'require'},cn);c=NS(require=cn['require'],INNER_SECONDS=7170,WORKER_SECONDS=7140,Guard=object)
pn=dict(os=os,life=life)
node=next(n for n in ast.parse(Path('learning/runs/v2/postovernight-long-D2-boundary-prepare-r9/processes.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='validate_report')
exec(compile(ast.Module(body=[node],type_ignores=[]),'processes.py','exec'),pn)
owned=NS(validate_report=pn['validate_report'])
report=dict(pid=300,reaped_by=200,direct_child_reaped=True,raw_wait_status=256,returncode=1,observed_monotonic=99.75)
class Channel:
    sock=object()
    def receive(self,deadline):return dict(kind='worker_wait',sender=200,report=report,t0_monotonic_hex=(90.).hex()),[]
ns=dict(c=c,life=life,owned=owned,time=clock,math=math,os=os,json=json,select=NS(select=lambda sockets,*a:(sockets,[],[])))
extract('long_d2_executor.py',{'Execution'},ns)
x=ns['Execution'].__new__(ns['Execution']);x.t0=90.;x.pool=life.FailurePool(90.)
x.child=NS(process=NS(pid=200));x.groups={'worker':dict(pid=300)}
x.worker_wait=x.worker_ready=None;x.super_channel=Channel();x.worker_channel=None
x.pump()
assert x.worker_wait is report and x.pool.until is None
result=dict(validated_nonzero_report_retained=x.worker_wait,first=x.pool.first,until=x.pool.until,
            conclusion='outer pump does not establish failure from worker report; it cannot repair the supervisor source-time loss',
            limits='Exact extracted pump; fake channel/select/clock, no OS operations or acceptance proof.')
(H/'outer-worker-packet-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
