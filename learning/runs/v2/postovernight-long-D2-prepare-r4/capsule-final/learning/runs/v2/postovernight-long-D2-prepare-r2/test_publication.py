"""Discriminating publication regressions, real Guard and stdlib owned workers."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import io
import test_long_d2 as t
from publication_probes import scenario

c=t.c
HERE=Path(__file__).resolve().parent
EVIDENCE=Path(os.environ.get('LONG_D2_PROBE_EVIDENCE',str(HERE/'tmp')))


class PublicationTests(unittest.TestCase):
    def run_probe(self,phase,mutation,mode='closure',delay=0):
        parent=Path(tempfile.mkdtemp(prefix='publication-',dir=EVIDENCE))
        root=parent/'scenario'
        command=[sys.executable,'-B',str(HERE/'publication_probes.py'),str(root),phase,mutation,mode,str(delay)]
        run=subprocess.run(command,capture_output=True,text=True,timeout=30,
                           env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        (parent/'subprocess.log').write_text(run.stdout+run.stderr)
        (parent/'subprocess-receipt.json').write_text(json.dumps(dict(argv=command,return_code=run.returncode),sort_keys=True,indent=2)+'\n')
        self.assertTrue((root/'observation.json').exists(),run.stderr)
        value=json.loads((root/'observation.json').read_bytes())
        self.assertEqual(run.returncode,value['return_code'])
        self.assertTrue(value['trigger_fired'])
        self.assertTrue(value['owned_group_positively_absent'])
        self.assertFalse(value['ML_imports'])
        self.assertTrue(value['manifest_still_matches'])
        self.assertTrue(all(not v['open_output_writers'] for v in value['artifact_hash_writer_checks']))
        return value
    def failed(self,value):
        self.assertEqual(value['return_code'],1)
        self.assertEqual(value['terminal']['experiment_status'],'failed')
        self.assertFalse(value['manifest_available'])
    def test_late_cancel_hash_real_guard_both_outcomes(self):
        for mode in ('closure','pass'):
            with self.subTest(mode=mode):self.failed(self.run_probe('hash-before','cancel',mode,.65))
    def test_late_input_hash_real_guard_both_outcomes(self):
        for mode in ('closure','pass'):
            with self.subTest(mode=mode):self.failed(self.run_probe('hash-after','input',mode,.65))
    def test_before_after_manifest_terminal_and_hash(self):
        for phase in ('hash-after','manifest-before','manifest-after','terminal-before','terminal-after'):
            for mutation in ('cancel','input'):
                for mode in ('closure','pass'):
                    with self.subTest(phase=phase,mutation=mutation,mode=mode):
                        self.failed(self.run_probe(phase,mutation,mode))
    def test_real_SIGINT_SIGTERM_outer_publication_alarm_exit(self):
        for sig in ('SIGINT','SIGTERM'):
            for mode in ('closure','pass'):
                with self.subTest(signal=sig,mode=mode):
                    value=self.run_probe('alarm-exit',sig,mode)
                    self.failed(value)
                    self.assertEqual(value['terminal']['outcome'],'cancelled')
                    event=next(e for e in value['events'] if e['event']=='real_signal')
                    self.assertNotEqual(event['handler'],'0')
    def test_final_authority_monitor_and_stream_closure_cancellations(self):
        for phase in ('authority-before','authority-after','monitor-close-before','monitor-close-after',
                      'stream-close-before','stream-close-after','full-verify-before','full-verify-after'):
            for sig in ('SIGINT','SIGTERM'):
                with self.subTest(phase=phase,signal=sig):self.failed(self.run_probe(phase,sig))
    def test_final_checks_and_context_closures_revalidate_inputs_and_lease(self):
        for phase in ('alarm-exit','monitor-close-after','stream-close-after','authority-after','full-verify-after'):
            for mutation in ('input','cancel'):
                with self.subTest(phase=phase,mutation=mutation):self.failed(self.run_probe(phase,mutation))
    def test_delayed_hash_has_live_observations_and_stable_manifest(self):
        value=self.run_probe('hash-before','none','closure',.7)
        self.assertEqual(value['return_code'],2)
        self.assertTrue(value['manifest_available'])
        self.assertTrue(any(v['live_memory_monitor'] for v in value['artifact_hash_writer_checks']))
        resources=value['terminal']['supervisor_resources_final']
        self.assertLessEqual(resources['maximum_sample_gap_seconds'],.5)
        self.assertLessEqual(resources['maximum_full_input_gap_seconds'],5)
        self.assertTrue(value['terminal']['final_authority_check_after_monitor_and_stream_close'])
    def test_slow_full_verification_does_not_block_resource_monitor(self):
        value=self.run_probe('full-verify-before','none','pass',.7)
        self.assertEqual(value['return_code'],0)
        resources=value['terminal']['supervisor_resources_final']
        self.assertLessEqual(resources['maximum_sample_gap_seconds'],.5)
        self.assertGreaterEqual(resources['maximum_full_input_gap_seconds'],.7)
        self.assertLessEqual(resources['maximum_full_input_gap_seconds'],5)
    def test_full_hash_duration_and_completed_gap_are_bounded(self):
        clock=t.Clock();verify=lambda:clock.advance(5.000001)
        g=c.Guard(20,lambda:None,verify,io.StringIO(),clock=clock,rss=lambda:0,peak=lambda:0)
        with self.assertRaisesRegex(c.Stop,'Full input verification gap'):g.sample(force=True)
    def test_outer_latch_restoration_revalidates_lease_and_inputs(self):
        for mutation in ('cancel','input'):
            for mode in ('closure','pass'):
                with self.subTest(mutation=mutation,mode=mode):self.failed(self.run_probe('latch-restore',mutation,mode))
    def test_masked_signals_during_post_restoration_final_checks(self):
        for phase in ('restoration-verify','restoration-final-sample'):
            for sig in ('SIGINT','SIGTERM'):
                with self.subTest(phase=phase,signal=sig):self.failed(self.run_probe(phase,sig))
    def test_outer_latch_own_handler_restoration_revokes_completion(self):
        for sig in ('SIGINT','SIGTERM'):
            with self.subTest(signal=sig):self.failed(self.run_probe('latch-restore',sig))
    def test_nested_context_keeps_same_handler_and_request_count(self):
        for sig in (signal.SIGINT,signal.SIGTERM):
            with c.cancellation_signals() as outer:
                outer();handler=signal.getsignal(sig)
                with c.cancellation_signals() as inner:
                    self.assertIs(inner,outer);os.kill(os.getpid(),sig)
                self.assertIs(signal.getsignal(sig),handler);os.kill(os.getpid(),sig)
            self.assertEqual(outer.cancellation_requests,2)


if __name__=='__main__':unittest.main(verbosity=2)
