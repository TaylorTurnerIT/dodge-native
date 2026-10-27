"""Retained fixture correction after units-02; production controller unchanged."""
from pathlib import Path
import json
H=Path(__file__).resolve().parent
p=H/'test_worker_ack_contract.py';s=p.read_text()
s=s.replace('guard=types.SimpleNamespace(failure_at=2.0)','guard=types.SimpleNamespace(failure=None,failure_at=2.0)')
s=s.replace('def exercise(mode, preceding=False, late_guard=False, stream_failure=False):','def exercise(mode, preceding=False, late_guard=False, stream_failure=False, cancel_after=False, cancel_first=False):')
s=s.replace("    body.body=ast.parse(inject).body", "    if cancel_first:inject=inject.replace(\"raise Stop('injected worker failure','safety_stop')\",\"raise Stop('user cancellation','cancelled')\")\n    body.body=ast.parse(inject).body")
s=s.replace("            events.append(dict(operation='notify_send'", "            if cancel_after or cancel_first:\n                life.ACTIVE.cancellation_requests=1;life.ACTIVE.requested_signal=__import__('signal').SIGTERM\n            events.append(dict(operation='notify_send'",1)
s=s.replace("until=life.POOL.until,first=life.POOL.first)","until=life.POOL.until,first=life.POOL.first,worker_result=copy.deepcopy(result_holder[0]) if result_holder else {})")
s=s.replace("+('-stream' if stream_failure else '')","+('-stream' if stream_failure else '')+('-cleanup-TERM' if cancel_after else '')+('-user-first' if cancel_first else '')")
s=s.replace('class WorkerAckContract(unittest.TestCase):','''class WorkerAckContract(unittest.TestCase):
    def test_actual_worker_primary_then_cleanup_TERM(self):
        r=exercise('valid',cancel_after=True)
        self.assertEqual(r['code'],1)
        result=r['worker_result'];self.assertEqual(result['outcome'],'safety_stop')
        self.assertEqual(result['error'],"Stop('injected worker failure')")
        self.assertTrue(result['cancellation_secondary'])
        self.assertEqual(result['secondary_failures'][-1]['outcome'],'cancelled')
        self.assertEqual(r['until'],10)
    def test_actual_worker_user_cancel_first(self):
        r=exercise('valid',cancel_first=True)
        self.assertEqual(r['code'],1);result=r['worker_result']
        self.assertEqual(result['outcome'],'cancelled')
        self.assertEqual(result['error'],"Stop('user cancellation')")
        self.assertFalse(result['cancellation_secondary'])
''')
p.write_text(s)
(H/'units-02-fixture-correction.json').write_text(json.dumps(dict(prior_attempt='attempts/units-02',failure="AttributeError: 'types.SimpleNamespace' object has no attribute 'failure'",cause='Inherited minimal Guard stub omitted new primary ordering field',repair='Add failure=None to that fixture; add actual worker cancellation-tail controls',production_source_changed=False,justification='Fixture now reflects real Guard fields. No production repair or hidden retry; prior 67-method attempt fully retained.',next_attempt='attempts/units-03'),indent=2)+'\n')
