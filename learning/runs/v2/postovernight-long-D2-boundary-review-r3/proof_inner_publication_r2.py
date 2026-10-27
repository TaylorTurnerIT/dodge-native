"""Extract exact inner function; stop before any subprocess or ML path.

A fixture Guard.start raises one ordinary exception after the output directory
exists. All subsequent publication code is the candidate's unchanged code.
"""
import ast
import hashlib
import io
import json
import math
import signal
import threading
import time
from pathlib import Path
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
CANDIDATE=HERE.parent/'postovernight-long-D2-boundary-prepare-r3'
ROOT=HERE/'inner-publication-fixture-r2';ROOT.mkdir();(ROOT/'execution').mkdir()
life=SimpleNamespace(ACTIVE=SimpleNamespace(first_at=None,first_cancel_at=None,first_alarm_at=None,deadline=time.monotonic()+100,cancellation_requests=0,alarm_seen=False))
ns=dict(Path=Path,ROOT=ROOT,ORIGINAL_ROOT=ROOT,STATE_PATH=ROOT/'state.json',INNER_SECONDS=7170,
        WORKER_SECONDS=7140,json=json,PROTOCOL_SHA256='fixture',HASH_OBSERVER=None,time=time,threading=threading,
        math=math,signal=signal,io=io,life=life,capsule_context=lambda *a,**k:None,Guard=object)

def extract(filename,names):
    source=(CANDIDATE/filename).read_text();nodes=[n for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    assert {n.name for n in nodes}==set(names)
    (HERE/('inner-extracted-'+filename)).write_text('\n\n'.join(ast.get_source_segment(source,n) for n in nodes)+'\n')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(CANDIDATE/filename),'exec'),ns)
extract('lifecycle.py',{'Stop','remaining','FailurePool','notify_failure'})
life.Stop=ns['Stop'];life.remaining=ns['remaining'];life.POOL=ns['FailurePool'](time.monotonic()-1);life.CHANNEL=None
# notify_failure's globals normally refer directly to lifecycle state.
ns.update(POOL=life.POOL,ACTIVE=life.ACTIVE,CHANNEL=None)
life.notify_failure=ns['notify_failure']
extract('long_d2.py',{'require','save','replace_json','failure_outcome','outcome_fields','result_code','observed_failure','optional_timing','provisional','supervise_owned'})
ns['assert_lease']=lambda *a:None
output=ROOT/'campaign';receipt=output/'inner-failure.json'
events=[]
real_replace=ns['replace_json']
def replace(path,value):
    events.append(dict(event='mandatory',path=str(path)))
    return real_replace(path,value)
ns['replace_json']=replace
class Guard:
    failure=None
    failure_at=None
    thread=verify_thread=None
    event=threading.Event()
    def __init__(self,*args):pass
    def start(self):raise ValueError('injected inner startup source failure')
    def persist_timing(self,path,*args):
        events.append(dict(event='optional_timing',mandatory_receipt_exists=receipt.exists()))
        Path(path).write_text('partial optional diagnostic\n')
        raise OSError('injected optional timing write failure')
p=dict(output='campaign',run_id='fixture',terminal_lifecycle={'acceptance_receipt':'execution/acceptance-receipt.json'})
lease={'identity_sha256':'fixture','capsule_manifest_sha256':'fixture'}
args=SimpleNamespace(output=output,state_path=ns['STATE_PATH'],executor_pid=123)
code,guard=ns['supervise_owned'](args,time.monotonic(),dict(identity_sha256='fixture',capsule_manifest_sha256='fixture'),SimpleNamespace(close=lambda:None),context_provider=lambda *a,**k:(p,{},{},{},{},lease),guard_factory=Guard)
observed=dict(code=code,events=events,mandatory_receipt_eventually_exists=receipt.exists(),no_child_spawned=True)
(HERE/'inner-publication-proof-results-r2.json').write_text(json.dumps(observed,indent=2)+'\n')
print(json.dumps(observed,indent=2))
assert code==1 and [x['event'] for x in events]==['optional_timing','mandatory']
assert events[0]['mandatory_receipt_exists'] is False
assert receipt.exists()
print('CONFIRMED: real inner exception branch reaches optional diagnostic IO before attempting mandatory inner-failure.json.')
