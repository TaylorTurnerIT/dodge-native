"""Real temporary-ledger handoff; no learner, native runtime or cloud access."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]/'experiments/teacher_local_dispatch_20261031_r1.py'
spec = importlib.util.spec_from_file_location('local066_dispatch_test', SOURCE)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


class HandoffTests(unittest.TestCase):
    def test_durable_failed_disposition_before_exact_nonnull_handoff(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); packet = root/'packet'; packet.mkdir(); (packet/'outputs').mkdir()
            (packet/'outputs/job').mkdir(); state = root/'state.json'
            old, new = {'record':'DODGE-065'}, {'record':'DODGE-066'}
            state.write_text(json.dumps(dict(active_long_campaign=old, unrelated=42)))
            reg = dict(state_path=str(state), package=str(packet), jobs=[dict(id='job')],
                       expected_lease=new, coordinator_thread='fixture')
            disposition = dict(exact_lease=old, record='DODGE-065', campaign_success=False)
            output = root/'dispatch'; actual_handoff = c.base.exact_handoff
            def observed_handoff(*args):
                receipt = c.read(output/'failure-disposition.json')
                self.assertFalse(receipt['campaign_success'])
                self.assertEqual(c.read(state)['active_long_campaign'], old)
                actual_handoff(*args)
            with patch.object(c, 'PARENT', root), patch.object(c, 'validate', return_value=(reg, disposition)), \
                    patch.object(c.base, 'exact_handoff', side_effect=observed_handoff):
                result = c.dispatch(dict(registration_sha256='registered', review_sha256='reviewed', authority_sha256='approved'), output)
                self.assertEqual(c.read(state), dict(active_long_campaign=new, unrelated=42))
                gate = c.read(result['dispatch_path'])
                self.assertEqual(gate['failure_disposition_sha256'], c.sha(output/'failure-disposition.json'))
                self.assertTrue(c.read(output/'lease-handoff.json')['never_cleared_to_null'])
                with self.assertRaises(ValueError): c.dispatch({}, output)

    def test_wrong_failed_owner_cannot_change_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = root/'state.json'; state.write_text('{"active_long_campaign":{"record":"other"}}')
            reg = dict(state_path=str(state)); disposition = dict(exact_lease={'record':'DODGE-065'})
            original = state.read_bytes()
            with patch.object(c, 'PARENT', root), patch.object(c, 'validate', return_value=(reg, disposition)):
                with self.assertRaisesRegex(ValueError, 'Exact failed065'): c.dispatch({}, root/'out')
            self.assertEqual(state.read_bytes(), original)
            self.assertFalse((root/'out').exists())


if __name__ == '__main__': unittest.main()
