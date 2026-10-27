"""Independent bounded checks of two-thread Guard failure and shutdown paths."""
import io
import json
from pathlib import Path
import sys
import threading
import time
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'postovernight-long-D2-prepare-r2'))
import test_long_d2 as t
c = t.c

class IndependentGuardTests(unittest.TestCase):
    def guard(self, verify=lambda:None, **kwargs):
        return c.Guard(time.monotonic()+20,lambda:None,verify,io.StringIO(),rss=lambda:0,peak=lambda:0,**kwargs)

    def test_resource_monitor_runs_during_slow_full_verification(self):
        calls=[]
        g=self.guard(lambda:time.sleep(.7))
        g.lease_check=lambda:calls.append(time.monotonic())
        g.start()
        try:
            self.assertGreaterEqual(len(calls),4)
            self.assertLessEqual(max(b-a for a,b in zip(calls,calls[1:])),.5)
            g.check()
        finally:g.close()
        self.assertFalse(g.thread.is_alive());self.assertFalse(g.verify_thread.is_alive())

    def test_background_full_failure_stays_latched_after_input_recovers(self):
        g=self.guard();g.start()
        try:
            def fail():raise c.Stop('independent transient full-hash failure')
            with g.verify_lock:
                g.verify=fail;g.last_full=time.monotonic()-4.05
            end=time.monotonic()+1
            while g.failure is None and time.monotonic()<end:time.sleep(.01)
            self.assertIsNotNone(g.failure)
            g.verify=lambda:None
            with self.assertRaises(c.Stop):g.check(force=True)
            with self.assertRaises(c.Stop):g.close()
        finally:
            g.event.set()
            for thread in (g.thread,g.verify_thread):thread.join(1)
        self.assertFalse(g.thread.is_alive());self.assertFalse(g.verify_thread.is_alive())

    def test_join_refuses_to_claim_blocked_verifier_stopped(self):
        entered=threading.Event();release=threading.Event()
        g=self.guard();g.start()
        def blocked():entered.set();release.wait(3)
        try:
            with g.verify_lock:
                g.verify=blocked;g.last_full=time.monotonic()-4.05
            self.assertTrue(entered.wait(1))
            with self.assertRaisesRegex(c.Stop,'Guard sampler did not stop'):g.close()
            self.assertTrue(g.verify_thread.is_alive())
        finally:
            release.set();g.event.set()
            g.thread.join(1);g.verify_thread.join(1)
        self.assertFalse(g.thread.is_alive());self.assertFalse(g.verify_thread.is_alive())

    def test_nonfinite_negative_and_noninteger_resource_observations_fail(self):
        for value in (float('nan'),float('inf'),-1,0.0,True):
            for field in ('rss','peak','mps'):
                with self.subTest(value=str(value),field=field):
                    g=self.guard();setattr(g,field,lambda:value)
                    with self.assertRaises(c.Stop):g.sample()

    def test_forced_full_hash_checks_deadline_after_io(self):
        clock=t.Clock(0)
        g=c.Guard(1,lambda:None,lambda:clock.advance(1),io.StringIO(),clock=clock,rss=lambda:0,peak=lambda:0)
        with self.assertRaises(c.Stop) as caught:g.sample(force=True)
        self.assertEqual(caught.exception.outcome,'wall_guard')

    def test_resource_probe_duration_and_full_duration_bounds(self):
        clock=t.Clock(0)
        g=c.Guard(10,lambda:None,lambda:None,io.StringIO(),clock=clock,rss=lambda:(clock.advance(.500001) or 0),peak=lambda:0)
        with self.assertRaisesRegex(c.Stop,'Resource probe exceeded'):g.sample()
        clock=t.Clock(0)
        g=c.Guard(10,lambda:None,lambda:clock.advance(5.000001),io.StringIO(),clock=clock,rss=lambda:0,peak=lambda:0)
        with self.assertRaisesRegex(c.Stop,'Full input verification gap'):g.sample(force=True)

if __name__=='__main__':unittest.main(verbosity=2)
