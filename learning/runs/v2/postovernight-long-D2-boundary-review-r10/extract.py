from pathlib import Path
from types import SimpleNamespace as NS
import ast,math,os,signal,threading
H=Path(__file__).resolve().parent
B=H/'snapshot'
clock=NS(value=100.)
clock.monotonic=lambda:clock.value
clock.sleep=lambda n:setattr(clock,'value',clock.value+n)
extractions=[]
def extract(file,names,namespace):
 source=(B/file).read_text()
 nodes=[n for n in ast.parse(source).body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names]
 assert {n.name for n in nodes}==set(names)
 extractions.extend(dict(file=file,name=n.name,line=n.lineno,end_line=n.end_lineno) for n in nodes)
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(B/file),'exec'),namespace)
ln=dict(time=clock,math=math,threading=threading,ACTIVE=None,CHANNEL=None,POOL=None)
extract('lifecycle.py',{'Stop','FailurePool','remaining','notify_failure'},ln)
life=NS(**ln,OWNED={signal.SIGINT,signal.SIGTERM,signal.SIGALRM})
cn=dict(Stop=life.Stop,life=life,time=clock,math=math,signal=signal)
extract('long_d2.py',{'require','failure_outcome','observed_failure','worker_raw_failure'},cn)
c=NS(**{k:cn[k] for k in ('require','failure_outcome','observed_failure','worker_raw_failure')},Stop=life.Stop,WORKER_SECONDS=7140,INNER_SECONDS=7170,Guard=object)
pn=dict(os=os,life=life)
extract('processes.py',{'validate_report'},pn)
owned=NS(validate_report=pn['validate_report'],signal_once=lambda *a:None,absent=lambda *a:True)
cn['owned']=owned
