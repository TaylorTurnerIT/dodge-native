"""Assertions against retained executions, including intentional finding failures."""
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
def load(path):return json.loads((HERE/path).read_bytes())

class SupportedRepairs(unittest.TestCase):
    def test_unmutated_outer_unmask_controls_complete_and_bind(self):
        for mode,code in (('closure',2),('pass',0)):
            with self.subTest(mode=mode):
                v=load('final-unmask-none-'+mode+'/independent-observation.json')
                self.assertEqual(v['return_code'],code)
                self.assertTrue(v['manifest_still_matches'])
                self.assertTrue(v['owned_group_positively_absent'])
    def test_exact_earlier_publication_boundaries_repaired(self):
        values=list((HERE/'fresh-publication-evidence').glob('*/scenario/observation.json'))
        self.assertEqual(len(values),66)
        for path in values:
            with self.subTest(path=str(path.relative_to(HERE))):
                v=json.loads(path.read_bytes())
                self.assertTrue(v['actual_guard']);self.assertTrue(v['actual_supervise'])
                self.assertTrue(v['owned_group_positively_absent'])
                self.assertTrue(v['manifest_still_matches']);self.assertFalse(v['ML_imports'])
                self.assertTrue(all(not w['open_output_writers'] for w in v['artifact_hash_writer_checks']))
                if v['mutation']!='none':
                    self.assertEqual(v['return_code'],1)
                    self.assertFalse(v['manifest_available'])
                    self.assertEqual(v['terminal']['experiment_status'],'failed')
    def test_old_regressions_except_retained_unknown_alarm_exit(self):
        rows=load('old-boundary-summary.json')
        self.assertEqual(len(rows),17)
        self.assertEqual([v['name'] for v in rows if v['test_process_exit']!=0],['old-late-terminal-write-closure'])
        for row in rows:
            if row['test_process_exit']!=0:continue
            with self.subTest(name=row['name']):
                v=load(row['name']+'/independent-observation.json')
                self.assertEqual(v['return_code'],1)
                self.assertFalse(v['manifest_available'])
                self.assertTrue(v['owned_group_positively_absent'])
    def test_signal_injections_follow_complete_publication_and_guard_shutdown(self):
        for sig in ('SIGINT','SIGTERM'):
            for mode in ('closure','pass'):
                with self.subTest(signal=sig,mode=mode):
                    v=load('final-unmask-'+sig+'-'+mode+'/final-unmask-event.json')
                    self.assertEqual(v['live_guard_threads'],[])
                    self.assertTrue(v['active_latch_is_None'])
                    self.assertIn(v['real_signal_sent'],v['pending_after_send'])
                    self.assertEqual(v['terminal_before']['experiment_status'],'complete')

class UnmetFinalUnmaskContract(unittest.TestCase):
    def test_late_lease_cancellation_must_fail_both_outcomes(self):
        for mode in ('closure','pass'):
            with self.subTest(mode=mode):
                v=load('delayed-unmask-cancel-'+mode+'/independent-observation.json')
                self.assertTrue(v['cancel_requested'])
                self.assertEqual(v['return_code'],1,'0.65s after lease cancellation must not return complete')
    def test_changed_pinned_input_must_fail_both_outcomes(self):
        for mode in ('closure','pass'):
            with self.subTest(mode=mode):
                v=load('delayed-unmask-input-'+mode+'/independent-observation.json')
                self.assertFalse(v['input_matches'])
                self.assertEqual(v['return_code'],1,'5.1s after input change must not return complete')
    def test_outer_unmask_deadline_crossing_must_fail(self):
        for mode in ('closure','pass'):
            with self.subTest(mode=mode):
                v=load('delayed-unmask-none-'+mode+'/independent-observation.json')
                self.assertEqual(v['return_code'],1,'Final context teardown exceeded 0.8s absolute budget')
    def test_pending_SIGTERM_at_final_unmask_must_revoke_complete(self):
        for mode in ('closure','pass'):
            with self.subTest(mode=mode):
                v=load('final-unmask-SIGTERM-'+mode+'/campaign/finalization-result.json')
                self.assertEqual(v['experiment_status'],'failed','Pending SIGTERM dispatched to restored SIG_DFL')
    def test_pending_SIGINT_at_final_unmask_must_revoke_complete(self):
        for mode in ('closure','pass'):
            with self.subTest(mode=mode):
                v=load('final-unmask-SIGINT-'+mode+'/campaign/finalization-result.json')
                self.assertEqual(v['experiment_status'],'failed','Pending SIGINT escaped outer cancellation latch')

if __name__=='__main__':unittest.main(verbosity=2)
