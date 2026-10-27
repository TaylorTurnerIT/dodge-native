"""Execute actual worker except/finally AND tail AST; replace only ML try body.

No real ML imports or persistence. Real notify_failure validates fake IPC ACKs.
Each probe retains events, AST and source digest under the unique test attempt.
"""
import ast
import copy
from contextlib import contextmanager
from pathlib import Path
import json
import os
import types
import unittest
from unittest.mock import patch
import long_d2 as c
import lifecycle as life
HERE=Path(__file__).resolve().parent
EVIDENCE=Path(os.environ['LONG_D2_TEST_EVIDENCE'])


def exercise(mode, preceding=False, late_guard=False, stream_failure=False):
    source=(HERE/'long_d2.py').read_text();tree=ast.parse(source)
    worker=copy.deepcopy(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='worker'))
    body=next(n for n in worker.body if isinstance(n,ast.With)).body[0]
    assert isinstance(body,ast.Try)
    inject='learner = probe_learner\nguard = probe_guard\n'
    if preceding:inject+="result = outcome_fields('budget_closed_below_gate',True)\n"
    if not late_guard and not stream_failure:inject+="raise Stop('injected worker failure','safety_stop')\n"
    body.body=ast.parse(inject).body
    # Verify is a native evidence seam, never the actual IO/package validator.
    verify=next(n for n in worker.body if isinstance(n,ast.FunctionDef) and n.name=='verify')
    verify.body=ast.parse("events.append(dict(operation='ordinary_verify'))").body
    module=ast.fix_missing_locations(ast.Module(body=[worker],type_ignores=[]))
    events=[];clock=[1.0]
    class Latch:
        first_at=None;deadline=7140;phase='NORMAL';cancellation_requests=0
        def __call__(self):self.phase='DEFER' if self.phase!='FAILURE' else 'FAILURE'
    class Channel:
        def send(self,value,until):
            events.append(dict(operation='notify_send',until=until,failed=result_holder[0].get('experiment_status') if result_holder else None,learner_deadline=learner.api.absolute_deadline))
            if mode=='send-exception':raise OSError('injected send failure')
        def receive(self,until):
            events.append(dict(operation='ACK_attempt'))
            if mode in ('missing','timeout'):raise TimeoutError('injected missing ACK' if mode=='missing' else 'injected ACK timeout')
            value=dict(kind='failure_ack',t0_monotonic_hex=0.0.hex(),first_monotonic_hex=0.0.hex(),cleanup_until_monotonic_hex=10.0.hex())
            if mode=='invalid':value['cleanup_until_monotonic_hex']=11.0.hex()
            return value,[]
    class Learner:
        model=object();progress={};checkpoints=[]
        def __init__(self):self.api=types.SimpleNamespace(absolute_deadline=7140)
        def checkpoint(self,*args,**kwargs):
            events.append(dict(operation='checkpoint',deadline=self.api.absolute_deadline,now=clock[0]));return {}
        def close(self):events.append(dict(operation='learner_close'))
        def report(self):return {}
    learner=Learner()
    def close_guard():
        events.append(dict(operation='guard_close'))
        if late_guard:raise c.Stop('injected late Guard failure')
    guard=types.SimpleNamespace(failure_at=0.0,close=close_guard,receipt=lambda:{})
    def close_streams():
        events.append(dict(operation='streams_close'))
        if stream_failure:raise OSError('injected stream close failure')
    @contextmanager
    def signals():yield life.ACTIVE
    result_holder=[]
    def save(path,value):
        events.append(dict(operation='persistence',path=path.name,deadline=learner.api.absolute_deadline,now=clock[0],status=value.get('experiment_status') if isinstance(value,dict) else None))
    namespace=dict(vars(c));namespace.update(probe_learner=learner,probe_guard=guard,events=events,cancellation_signals=signals,
        ExitStack=lambda:types.SimpleNamespace(close=close_streams),save=save,ROOT=Path('/not-created'),check_module_origins=lambda *a:{})
    # Inspect the live result object immediately before send without changing it.
    original_failure=c.worker_failure
    def failure(error,args,guard,learner,result,permission):
        result_holder[:]=[result]
        return original_failure(error,args,guard,learner,result,permission)
    namespace['worker_failure']=failure
    with patch.object(life,'POOL',life.FailurePool(0.0)),patch.object(life,'CHANNEL',Channel()),patch.object(life,'ACTIVE',Latch()),patch.object(life.time,'monotonic',lambda:clock[0]):
        exec(compile(module,'actual_r4_worker_except_finally_and_tail','exec'),namespace)
        code=namespace['worker'](types.SimpleNamespace(started=0.0,output=Path('/not-created')),({'run_id':'probe'}, {}, {}, {}, {}, {'identity_sha256':'c'*64}))
        result=dict(code=code,events=events,learner_deadline=learner.api.absolute_deadline,until=life.POOL.until,first=life.POOL.first)
    name='worker-'+mode+('-preceding' if preceding else '')+('-guard' if late_guard else '')+('-stream' if stream_failure else '')
    c.save(EVIDENCE/(name+'.json'),result)
    with (EVIDENCE/(name+'.ast.txt')).open('x') as out:out.write(ast.dump(module,indent=2))
    return result


class WorkerAckContract(unittest.TestCase):
    def test_missing_invalid_send_timeout_block_all_new_persistence(self):
        for mode in ('missing','invalid','send-exception','timeout'):
            with self.subTest(mode=mode):
                r=exercise(mode)
                self.assertEqual(r['code'],1)
                self.assertFalse(any(e['operation'] in ('checkpoint','persistence','ordinary_verify') for e in r['events']),r)
                sent=[e for e in r['events'] if e['operation']=='notify_send']
                self.assertEqual(len(sent),1)
                self.assertEqual(sent[0]['failed'],'failed');self.assertEqual(sent[0]['learner_deadline'],10)
    def test_valid_ack_allows_exact_deadline10(self):
        r=exercise('valid');self.assertEqual(r['code'],1)
        writes=[e for e in r['events'] if e['operation'] in ('checkpoint','persistence')]
        self.assertEqual(len(writes),3,r)
        self.assertTrue(all(e['deadline']==10 and e['now']<10 for e in writes))
    def test_preceding_success_late_guard_ACK_failure_never_verifies_or_persists(self):
        r=exercise('missing',preceding=True,late_guard=True)
        self.assertEqual(r['code'],1)
        self.assertFalse(any(e['operation'] in ('checkpoint','persistence','ordinary_verify') for e in r['events']),r)
    def test_preceding_success_stream_failure_ACK_failure_skips_result_and_index(self):
        r=exercise('timeout',preceding=True,stream_failure=True)
        self.assertEqual(r['code'],1)
        self.assertFalse(any(e['operation']=='persistence' for e in r['events']),r)
    def test_later_earlier_ACK_tightens_and_permission_never_extends(self):
        pool=life.FailurePool(0.0);permission=dict(failed=False,acknowledged_until=None,ack_failed=False)
        result=c.outcome_fields('budget_closed_below_gate',True);learner=types.SimpleNamespace(api=types.SimpleNamespace(absolute_deadline=7140))
        guard=types.SimpleNamespace(failure_at=2.0)
        class Channel:
            first=2.0
            def send(self,value,deadline):pass
            def receive(self,deadline):
                return dict(kind='failure_ack',t0_monotonic_hex=0.0.hex(),first_monotonic_hex=self.first.hex(),cleanup_until_monotonic_hex=(self.first+10).hex()),[]
        channel=Channel()
        with patch.object(life,'POOL',pool),patch.object(life,'CHANNEL',channel),patch.object(life,'ACTIVE',None),patch.object(life.time,'monotonic',lambda:3.0):
            self.assertTrue(c.worker_failure(c.Stop('first'),types.SimpleNamespace(),guard,learner,result,permission));self.assertEqual(learner.api.absolute_deadline,12)
            # Executor ACK reports an earlier failure than the local worker saw.
            channel.first=0.0
            self.assertTrue(c.worker_failure(c.Stop('earlier ACK'),types.SimpleNamespace(),guard,learner,result,permission));self.assertEqual(learner.api.absolute_deadline,10)
            guard.failure_at=2.5
            self.assertTrue(c.worker_failure(c.Stop('later'),types.SimpleNamespace(),guard,learner,result,permission));self.assertEqual(learner.api.absolute_deadline,10)
            permission['acknowledged_until']=12
            with self.assertRaises(c.Stop):c.worker_write_permission(types.SimpleNamespace(started=0),result,permission,learner)

    def test_expired_or_unacknowledged_shared_deadline_forbids_each_write(self):
        pool=life.FailurePool(0.0)
        with patch.object(life,'POOL',pool),patch.object(life.time,'monotonic',lambda:1.0):pool.fail('failure',0.0)
        result=c.outcome_fields('safety_stop');permission=dict(failed=True,acknowledged_until=10.0,ack_failed=False)
        with patch.object(life,'POOL',pool),patch.object(life.time,'monotonic',lambda:10.0):
            with self.assertRaises(c.Stop):c.worker_write_permission(types.SimpleNamespace(started=0),result,permission)
        permission['ack_failed']=True
        with patch.object(life,'POOL',pool),patch.object(life.time,'monotonic',lambda:1.0):
            with self.assertRaises(c.Stop):c.worker_write_permission(types.SimpleNamespace(started=0),result,permission)

if __name__=='__main__':unittest.main(verbosity=2,failfast=True)
