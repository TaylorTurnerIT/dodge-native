"""Read-only stdlib proof of actual worker except/finally ACK ordering.

The original try/except/finally AST is preserved except its try body becomes one
controlled failure. Original worker_failure/outcome helpers execute unchanged.
Fake persistence records calls in memory; no ML import or real checkpoint write.
"""
import ast
import copy
from pathlib import Path
import traceback
import types
import unittest

PREP=Path(__file__).resolve().parent.parent/'postovernight-long-D2-prepare-r3'

class ProbeFailure(RuntimeError):pass
class AckFailure(RuntimeError):pass


def exercise(ack):
    source=(PREP/'long_d2.py').read_text();tree=ast.parse(source)
    worker=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='worker')
    owned_context=next(n for n in worker.body if isinstance(n,ast.With))
    probe=copy.deepcopy(owned_context.body[0])
    assert isinstance(probe,ast.Try)
    probe.body=[ast.Raise(exc=ast.Call(func=ast.Name(id='ProbeFailure',ctx=ast.Load()),args=[ast.Constant('injected worker failure')],keywords=[]),cause=None)]
    helpers=[copy.deepcopy(n) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('worker_failure','outcome_fields','result_code','failure_outcome')]
    module=ast.fix_missing_locations(ast.Module(body=helpers+[probe],type_ignores=[]))
    events=[]
    class Learner:
        model=object();progress={}
        def __init__(self):self.api=types.SimpleNamespace(absolute_deadline=7140);self.checkpoints=[]
        def checkpoint(self,*args,**kwargs):
            events.append(dict(operation='emergency_checkpoint',acknowledged=ack,deadline=self.api.absolute_deadline));return {}
        def close(self):events.append(dict(operation='learner_close'))
        def report(self):return {}
    learner=Learner()
    def notify_failure(error,at):
        events.append(dict(operation='notify_failure'))
        if not ack:raise AckFailure('injected missing or invalid executor ACK')
        return 10
    life=types.SimpleNamespace(notify_failure=notify_failure,POOL=types.SimpleNamespace(deadline=lambda _:10))
    guard=types.SimpleNamespace(failure_at=0,close=lambda:None,receipt=lambda:{})
    namespace=dict(ProbeFailure=ProbeFailure,learner=learner,guard=guard,life=life,args=types.SimpleNamespace(started=0,output=Path('/synthetic-output-not-created')),WORKER_SECONDS=7140,Stop=ProbeFailure,traceback=traceback,time=types.SimpleNamespace(monotonic=lambda:1),cancel=lambda:None,verify=lambda:None,streams=types.SimpleNamespace(close=lambda:None),save=lambda path,value:events.append(dict(operation='persistence_write',path=path.name)),require=lambda condition,*args:None,result={'experiment_status':'failed','outcome':'identity_or_lease_failure','expected_exit_code':1})
    try:exec(compile(module,'actual_r3_worker_except_finally','exec'),namespace)
    except AckFailure:pass
    return events,learner.api.absolute_deadline


class WorkerAckContract(unittest.TestCase):
    def test_missing_ack_must_block_failure_persistence(self):
        events,deadline=exercise(False)
        self.assertFalse(any(e['operation'] in ('emergency_checkpoint','persistence_write') for e in events),events)
    def test_acknowledged_failure_preserves_checkpoint_and_shared_deadline(self):
        events,deadline=exercise(True)
        self.assertEqual(deadline,10)
        checkpoints=[e for e in events if e['operation']=='emergency_checkpoint']
        self.assertEqual(len(checkpoints),1)
        self.assertTrue(checkpoints[0]['acknowledged'])
        self.assertEqual(checkpoints[0]['deadline'],10)

if __name__=='__main__':unittest.main(verbosity=2)
