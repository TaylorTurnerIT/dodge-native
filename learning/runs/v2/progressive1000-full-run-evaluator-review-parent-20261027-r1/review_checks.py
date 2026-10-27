"""Independent stdlib checks; no native runtime or checkpoint deserialization."""
from pathlib import Path
import io
import sys
import types
import unittest
from unittest.mock import patch

PACKAGE=Path(__file__).resolve().parents[1]/'progressive1000-full-run-evaluator-parent-20261027-r2'
sys.path.insert(0,str(PACKAGE))
import binding as b
import worker

class GuardChecks(unittest.TestCase):
    def make_guard(self):
        reg=dict(limits=dict(work_seconds=100,raw_frames=100,rss_bytes=b.CAP,mps_bytes=b.CAP))
        api=types.SimpleNamespace(mps=types.SimpleNamespace(driver_allocated_memory=lambda:0))
        return worker.Guard(reg,0,api,io.StringIO(),io.StringIO())

    def test_expensive_lease_checks_throttled(self):
        guard=self.make_guard()
        with patch.object(worker.time,'monotonic',side_effect=[1,1.1,1.21]),patch.object(b,'check_lease') as lease,patch.object(worker.os.path,'lexists',return_value=False):
            guard.check();guard.check();guard.check()
            self.assertEqual(lease.call_count,2)

    def test_raw_limit_checked_even_between_resource_samples(self):
        guard=self.make_guard();guard.last=1;guard.raw=101
        with patch.object(worker.time,'monotonic',return_value=1.1),patch.object(b,'check_lease') as lease,patch.object(worker.os.path,'lexists',return_value=False):
            with self.assertRaisesRegex(ValueError,'total raw-frame'):guard.check()
            lease.assert_not_called()

    def test_cancel_checked_even_between_resource_samples(self):
        guard=self.make_guard();guard.last=1
        with patch.object(worker.time,'monotonic',return_value=1.1),patch.object(worker.os.path,'lexists',return_value=True):
            with self.assertRaisesRegex(ValueError,'parent cancellation'):guard.check()

    def test_constructor_and_step_journals_cost(self):
        guard=self.make_guard()
        guard.journal(b.POLICIES[0],dict(kind='evaluation_constructor',episode_index=0,info=dict(startup_frames=13,seed=dict(actual_seed=b.SEEDS[0]))))
        guard.journal(b.POLICIES[0],dict(kind='evaluation_step',episode_index=0,elapsed_raw_frames=4))
        self.assertEqual(guard.raw,17)
        self.assertEqual(len(guard.events.getvalue().splitlines()),2)

if __name__=='__main__':unittest.main()
