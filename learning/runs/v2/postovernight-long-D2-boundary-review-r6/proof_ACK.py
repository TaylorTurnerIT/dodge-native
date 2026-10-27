"""Exact failure/ACK/write gate functions; fake clock and directed peer only."""
from pathlib import Path
from types import SimpleNamespace as NS
import ast,json,math,signal,threading
H=Path(__file__).resolve().parent;B=H.parent/'postovernight-long-D2-boundary-prepare-r6'
clock=NS(monotonic=lambda:100.)
def extract(file,names,ns):
    nodes=[n for n in ast.parse((B/file).read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    assert {n.name for n in nodes}==set(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(B/file),'exec'),ns)
ln=dict(math=math,time=clock,threading=threading,ACTIVE=None,CHANNEL=None,POOL=None)
extract('lifecycle.py',{'Stop','remaining','FailurePool','notify_failure'},ln)
life=NS(**ln)
cn=dict(life=life,Stop=life.Stop,time=clock,math=math,signal=signal,WORKER_SECONDS=7140)
extract('long_d2.py',{'require','failure_outcome','outcome_fields','result_code','observed_failure','primary_error','record_primary_failure','worker_failure','worker_write_permission'},cn)
def descriptor(at,outcome):return dict(timestamp=at,kind='source',outcome=outcome,role='worker',timing_basis='synthetic_actual_source',signal=None)
results={}
class Peer:
    def __init__(self,missing=False):self.missing=missing;self.sends=0
    def send(self,*a):self.sends+=1
    def receive(self,until):
        if self.missing:raise life.Stop('missing ACK')
        return dict(kind='failure_ack',t0_monotonic_hex=(90.).hex(),first_monotonic_hex=(99.5).hex(),cleanup_until_monotonic_hex=(109.5).hex(),descriptor=descriptor(99.5,'cancelled')),[]
def setup(missing=False):
    pool=life.FailurePool(90.);peer=Peer(missing);ln.update(POOL=pool,CHANNEL=peer)
    life.POOL=pool;life.CHANNEL=peer
    permission=dict(failed=False,ack_failed=False,acknowledged_until=None)
    error=life.Stop('worker source','resource_stop');error.first_failure_descriptor=descriptor(99.8,'resource_stop')
    return pool,peer,permission,error,cn['outcome_fields']('failed')
pool,peer,permission,error,result=setup()
assert cn['worker_failure'](error,None,None,None,result,permission)
assert pool.first_local['timestamp']==99.8 and pool.first_global['timestamp']==99.5 and pool.until==109.5
assert permission['acknowledged_until']==109.5 and result['outcome']=='cancelled'
results['late_earlier_ACK']=dict(first_local=pool.first_local,first_global=pool.first_global,until=pool.until,sends=peer.sends)
try:life.notify_failure(error,99.9)
except life.Stop as e:assert str(e)=='Failure descriptor timestamp differs'
else:raise AssertionError('explicit conflict accepted')
results['explicit_conflict_rejected']=True
pool,peer,permission,error,result=setup(True)
assert cn['worker_failure'](error,None,None,None,result,permission) is False
assert cn['worker_failure'](error,None,None,None,result,permission) is False
assert peer.sends==1
try:cn['worker_write_permission'](NS(started=90.),result,permission)
except life.Stop as e:assert str(e)=='Unacknowledged failed-worker persistence forbidden'
else:raise AssertionError('write permitted after missing ACK')
results['missing_ACK']=dict(sends=peer.sends,ack_failed=permission['ack_failed'],writes_rejected=True,until=pool.until)
(H/'ACK-proof-results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
