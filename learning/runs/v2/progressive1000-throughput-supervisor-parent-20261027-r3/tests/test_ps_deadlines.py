"""Actual subprocess.run/communicate interruption; synthetic supervisor gates."""
from contextlib import contextmanager
import os
from pathlib import Path
import signal
import subprocess
import time
from unittest.mock import patch

import test_real_processes as original
from test_real_processes import RealProcesses, b, observe, OWN, PYTHON

PS = ['/bin/ps', '-axo', 'pid=,ppid=,pgid=,rss=,lstart=,command=']
PS_HELPER = str(OWN/'tests/delayed_ps.py')


class PsDeadlines(RealProcesses):
    # The separate runner selects only these four methods, not inherited tests.
    @contextmanager
    def ps_boundary(self, delay, *, exit_code=0, count=1):
        real_popen = subprocess.Popen
        handles = []
        observations = []

        def popen(argv, **kwargs):
            if argv != PS or len(handles) >= count:
                return real_popen(argv, **kwargs)
            home = self.home/('ps-'+str(len(handles)+1))
            home.mkdir()
            b.save(home/'plan.json', dict(delay_seconds=delay, exit_code=exit_code))
            self.assertNotIn('start_new_session', kwargs)
            proc = real_popen([PYTHON, '-I', '-B', PS_HELPER, str(home)],
                              start_new_session=True, **kwargs)
            handles.append((proc, home))
            original.OWNED[proc.pid] = proc
            return proc

        # Only executable selection changes. process_rows, subprocess.run,
        # communicate, context-manager cleanup and SIGALRM remain real.
        with patch.object(subprocess, 'Popen', side_effect=popen):
            try:
                yield handles
            finally:
                self.assertEqual(len(handles), count)
                for proc, home in handles:
                    ready = b.read(home/'ready.json')
                    self.assertEqual((ready['pid'], ready['ppid'], ready['pgid']),
                                     (proc.pid, os.getpid(), proc.pid))
                    self.assertIsNotNone(proc.returncode, 'run must reap its ps helper')
                    with self.assertRaises(ChildProcessError):
                        os.waitpid(proc.pid, os.WNOHANG)
                    self.assertFalse(observe.group_exists(proc.pid))
                    self.assertNotIn(proc.pid, observe.process_rows())
                    observations.append(dict(pid=proc.pid, raw_exit=proc.returncode,
                        directly_reaped_before_test_teardown=True,
                        ECHILD_confirmed=True, group_absent=True,
                        helper_plan=ready['plan']))
                self.case['checks']['ps_helpers'] = observations

    def assert_worker_reaped(self, receipt):
        pid = receipt['worker_pid']
        self.assertEqual(receipt['observed_worker_raw_exit'], -15)
        self.assertTrue(receipt['directly_reaped'])
        self.assertFalse(observe.group_exists(pid))
        self.assertNotIn(pid, observe.process_rows())
        with self.assertRaises(ChildProcessError):
            os.waitpid(pid, os.WNOHANG)
        self.case['checks']['worker_ECHILD_and_group_absent_before_teardown'] = True

    def test_ps_slower_than_one_second_within_work_budget(self):
        real_rows = observe.process_rows
        returned = []
        limits = dict(b.LIMITS, work_seconds=4, total_seconds=6)

        def rows():
            start = time.monotonic()
            current = real_rows()
            if not returned:
                worker = next(p for p, proc in original.OWNED.items()
                              if proc.args[:4] == original.command('wait', self.home)[:4])
                self.assertIn(worker, current)
                self.assertEqual(current[worker]['pgid'], worker)
                self.assertGreater(current[worker]['rss_bytes'], 0)
                self.assertTrue(current[worker]['start_identity'])
                elapsed = time.monotonic()-start
                self.assertGreater(elapsed, 1)
                returned.append(dict(elapsed_seconds=elapsed, valid_worker_row=True,
                                     current_observer_row=os.getpid() in current))
                # End this finite test only after a valid slow observation.
                Path(self.home/'cancel').touch()
            return current

        start = time.monotonic()
        with self.ps_boundary(1.25) as helpers, \
             patch.object(b, 'LIMITS', limits), \
             patch.object(observe, 'process_rows', side_effect=rows):
            receipt, _ = self.run_controller(rows=rows)
            self.assertEqual(helpers[0][0].returncode, 0)
        self.assertEqual(receipt['first_event']['kind'], 'cancel_marker')
        self.assertNotIn('error', receipt['first_event'])
        self.assertFalse(receipt['deadline_consumed'])
        self.assertGreater(receipt['max_aggregate_rss_bytes'], 0)
        self.assertLess(time.monotonic()-start, limits['work_seconds'])
        self.assert_worker_reaped(receipt)
        self.case['checks'].update(slow_valid_observations=returned,
            synthetic_limits=limits, elapsed_seconds=time.monotonic()-start,
            termination='deliberate cancellation only after slow valid ps observation')

    def test_ps_crossing_work_alarm_interrupts_and_reaps(self):
        limits = dict(b.LIMITS, work_seconds=.35, total_seconds=6.5)
        start = time.monotonic()
        with self.ps_boundary(3) as helpers:
            receipt, _ = self.run_controller(limits=limits)
            self.assertEqual(helpers[0][0].returncode, -signal.SIGKILL)
        self.assertEqual(receipt['first_event']['kind'], 'external_work_deadline')
        self.assertIn('Cancelled', receipt['error'])
        self.assertIn('process_rows', receipt['traceback'])
        self.assertIn('communicate', receipt['traceback'])
        self.assertFalse(receipt['deadline_consumed'])
        self.assertEqual(receipt['max_aggregate_rss_bytes'], 0)
        self.assertEqual((self.home/'control/observer-resources.jsonl').read_text(), '')
        self.assert_worker_reaped(receipt)
        self.assertLess(time.monotonic()-start, limits['total_seconds'])
        self.case['checks'].update(synthetic_limits=limits,
            no_stale_resource_sample=True, elapsed_seconds=time.monotonic()-start)

    def test_ps_crossing_total_alarm_during_cleanup_is_sticky(self):
        limits = dict(b.LIMITS, work_seconds=.35, total_seconds=.9)
        real_signal = observe.signal_owned
        accounting_calls = []

        def send(proc, anchors, sig, record):
            real_signal(proc, anchors, sig, record)
            if sig == signal.SIGTERM:
                # First ps consumes work alarm. This real second observation
                # runs during cleanup, with the original total alarm armed.
                observe.process_rows()

        def accounting(*args):
            accounting_calls.append(True)
            self.fail('accounting after sticky total deadline')

        start = time.monotonic()
        with self.ps_boundary(3, count=2) as helpers, \
             patch.object(observe, 'signal_owned', side_effect=send), \
             patch.object(observe.terminal, 'accounting', side_effect=accounting):
            receipt, _ = self.run_controller(limits=limits)
            self.assertEqual([p.returncode for p, _ in helpers], [-9, -9])
        self.assertEqual(receipt['first_event']['kind'], 'external_work_deadline')
        self.assertTrue(receipt['deadline_consumed'])
        self.assertEqual(receipt['terminal_accounting_deferred'], 'total_deadline_consumed')
        self.assertTrue(any('Cancelled' in error for error in receipt['cleanup']['errors']))
        self.assertEqual(accounting_calls, [])
        self.assertNotIn('terminal_accounting', receipt)
        self.assertEqual((self.home/'control/observer-resources.jsonl').read_text(), '')
        self.assert_worker_reaped(receipt)
        self.assertLess(time.monotonic()-start, 1.5)
        self.case['checks'].update(synthetic_limits=limits,
            first_work_then_total_ps_interruptions=True, accounting_calls=0,
            no_stale_resource_sample=True, elapsed_seconds=time.monotonic()-start)

    def test_failed_ps_command_still_fails_closed_and_reaps(self):
        limits = dict(b.LIMITS, work_seconds=4, total_seconds=7)
        start = time.monotonic()
        with self.ps_boundary(0, exit_code=23) as helpers:
            receipt, _ = self.run_controller(limits=limits)
            self.assertEqual(helpers[0][0].returncode, 23)
        self.assertEqual(receipt['first_event']['kind'], 'observer_failure')
        self.assertIn('CalledProcessError', receipt['first_event']['error'])
        self.assertIn('23', receipt['first_event']['error'])
        self.assertFalse(receipt['deadline_consumed'])
        self.assertEqual(receipt['max_aggregate_rss_bytes'], 0)
        self.assertEqual((self.home/'control/observer-resources.jsonl').read_text(), '')
        self.assert_worker_reaped(receipt)
        self.assertLess(time.monotonic()-start, limits['total_seconds'])
        self.case['checks'].update(synthetic_limits=limits,
            no_stale_resource_sample=True, elapsed_seconds=time.monotonic()-start)
