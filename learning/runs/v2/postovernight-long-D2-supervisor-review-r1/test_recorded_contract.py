"""Contract assertions against retained executions of the frozen supervisor.

These tests inspect observed OS-worker runs, not a reimplementation of helpers.
Failures are intentional evidence of the reviewed candidate's defects.
"""
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


def observation(name):
    return json.loads((HERE / name / 'observation.json').read_bytes())


class RepairedBoundaryChecks(unittest.TestCase):
    def test_late_final_verification_revokes_completion(self):
        value = observation('late-final-verify')
        self.assertEqual(value['return_code'], 1)
        self.assertFalse(value['manifest_available'])
        self.assertEqual(value['terminal']['outcome'], 'wall_guard')

    def test_late_artifact_hash_revokes_completion(self):
        value = observation('late-artifact-hash')
        self.assertEqual(value['return_code'], 1)
        self.assertFalse(value['manifest_available'])

    def test_unproven_group_blocks_manifest(self):
        value = observation('unproven-group')
        self.assertEqual(value['return_code'], 1)
        self.assertFalse(value['manifest_available'])

    def test_deferred_cancellation_is_counted(self):
        for name in ('deferred-cleanup-cancel', 'deferred-final-verify-cancel'):
            with self.subTest(name=name):
                value = observation(name)
                self.assertEqual(value['return_code'], 1)
                self.assertEqual(value['terminal']['outcome'], 'cancelled')
                run = json.loads((HERE / name / 'campaign/long-run-result.json').read_bytes())
                self.assertEqual(run['cancellation_requests'], 2)


class UnmetPublicationContract(unittest.TestCase):
    def test_late_parent_cancellation_must_revoke_clean_closure(self):
        value = observation('late-lease-cancel-real-guard')
        self.assertTrue(value['lease_cancel_requested'])
        self.assertEqual(value['return_code'], 1, 'Cancellation after guard close cannot return complete exit 2')

    def test_late_parent_cancellation_must_revoke_gate_pass(self):
        value = observation('late-lease-cancel-pass')
        self.assertTrue(value['lease_cancel_requested'])
        self.assertEqual(value['return_code'], 1, 'Cancellation during hashing cannot return gate-pass exit 0')

    def test_late_pinned_input_change_must_revoke_completion(self):
        value = observation('late-input-change-real-guard')
        self.assertFalse(value['pinned_input_still_matches'])
        self.assertEqual(value['return_code'], 1, 'Changed pinned inputs cannot return complete exit 2')

    def test_outer_context_SIGTERM_must_revoke_complete_terminal(self):
        root = HERE / 'outer-alarm-SIGTERM'
        events = json.loads((root / 'events.json').read_bytes())
        self.assertEqual(events[-1]['signal'], 15)
        self.assertEqual(events[-1]['current_handler'], '0')
        terminal = json.loads((root / 'campaign/finalization-result.json').read_bytes())
        self.assertEqual(terminal['experiment_status'], 'failed',
                         'SIGTERM at outer publication context exit leaves a complete authoritative receipt')


if __name__ == '__main__':
    unittest.main(verbosity=2)
