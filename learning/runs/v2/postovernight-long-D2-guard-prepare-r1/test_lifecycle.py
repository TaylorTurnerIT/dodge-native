"""Current source assertions and independent stdlib lifecycle controls."""
import ast
import io
import json
import math
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import long_d2 as c
import long_d2_executor as e
import lifecycle as life
HERE=Path(__file__).resolve().parent
EVIDENCE=Path(os.environ['LONG_D2_TEST_EVIDENCE'])


def nodes(path):
    s=path.read_text();lines=s.splitlines(True)
    return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(s).body
            if isinstance(n,(ast.FunctionDef,ast.ClassDef))}


class SourceTests(unittest.TestCase):
    def test_frozen_ML_nodes_exact(self):
        old=nodes(HERE.parent/'postovernight-long-D2-prepare-r2/long_d2.py');new=nodes(HERE/'long_d2.py')
        for name in ('Learner','Schedule','run_schedule','environment_kwargs','counter_report','compare_control',
                     'tree_fingerprint','assert_equal_tree','validate_long_config','expected_lease','assert_lease',
                     'check_module_origins','outcome_fields','result_code'):
            with self.subTest(name=name):self.assertEqual(old[name],new[name])
    def test_worker_ML_try_body_byte_identical_to_r3(self):
        def body(path):
            source=path.read_text();tree=ast.parse(source)
            worker=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='worker')
            block=next(n for n in worker.body if isinstance(n,ast.With)).body[0]
            lines=source.splitlines(True)
            return ''.join(lines[block.body[0].lineno-1:block.body[-1].end_lineno])
        self.assertEqual(body(HERE/'long_d2.py'),body(HERE.parent/'postovernight-long-D2-prepare-r3/long_d2.py'))
    def test_outer_normal_IO_keeps_lifetime_alarm_interrupting(self):
        source=nodes(HERE/'long_d2_executor.py')['Execution']
        normal=source[source.index('    def run(self):'):source.index('        except BaseException as error:',source.index('    def run(self):'))]
        self.assertNotIn('self.latch()',normal)
        self.assertLess(normal.index('self.watchdog.join'),normal.index('self.authority(True)  # Includes watchdog'))
        self.assertIn("self.latch.phase='FAILURE'",source)
    def test_no_restore_or_rearm_in_final_leaf(self):
        node=nodes(HERE/'lifecycle.py')['final_exit']
        self.assertNotIn('SIG_SETMASK',node);self.assertNotIn('SIG_DFL',node)
        self.assertNotIn('finally',node.replace('caller finally','caller cleanup'))
        self.assertEqual(node.count('setitimer'),1)
        self.assertIn('os._exit',node)
    def test_no_ML_top_level_imports(self):
        for name in ('long_d2.py','long_d2_executor.py','lifecycle.py','processes.py','freeze.py'):
            for n in ast.parse((HERE/name).read_text()).body:
                if isinstance(n,(ast.Import,ast.ImportFrom)):
                    values=[a.name for a in n.names] if isinstance(n,ast.Import) else [n.module]
                    self.assertFalse(any(v and v.split('.')[0] in ('torch','numpy','dodge_rl') for v in values))
    def test_deadlines_and_protocol_exact(self):
        p=c.registered_protocol(c.ORIGINAL_ROOT/c.PROTOCOL_REL)
        self.assertEqual(c.sha(c.ORIGINAL_ROOT/c.PROTOCOL_REL),'b5329fdf58d984c9e38d36119973e5852601b204265a2422e6e476b0952052da')
        self.assertEqual((c.WORKER_SECONDS,c.INNER_SECONDS,e.NORMAL_SECONDS),(7140,7170,7200))
        self.assertEqual(p['guard']['deadline_origin'],'executor_T0_before_ordinary_imports_shared_by_worker_inner_and_outer')


class PoolTests(unittest.TestCase):
    def test_later_earlier_report_tightens_and_never_resets(self):
        now=time.monotonic();p=life.FailurePool(now-10)
        first=p.fail('executor',now-1);second=p.fail('worker',now-4)
        self.assertEqual(second,now+6);self.assertLess(second,first)
        self.assertEqual(p.fail('later'),second)
    def test_cap_and_invalid_timestamps(self):
        now=time.monotonic();p=life.FailurePool(now-7200)
        self.assertLessEqual(p.fail('deadline'),p.t0+7210)
        for at in (float('nan'),float('inf'),now+100,p.t0-1):
            with self.subTest(at=at),self.assertRaises(c.Stop):p.fail('invalid',at)
    def test_expired_timeout_never_becomes_positive(self):
        with self.assertRaises(c.Stop):life.remaining(time.monotonic()-1)
    def test_no_parent_receipt_only_acceptance(self):
        for raw in (None,1,-2,-9,-14,-15,3):self.assertFalse(e.accept_observed({'accepted':True},raw,1))
        for elapsed in (None,float('nan'),float('inf'),7200.01):self.assertFalse(e.accept_observed({},2,elapsed))


class SignalTests(unittest.TestCase):
    def test_real_lifetime_alarm_normal_defer_failure_expired_pending(self):
        for mode in ('normal','defer','failure','expired','pending-alarm','positive'):
            with self.subTest(mode=mode):
                out=EVIDENCE/('latch-'+mode+'.json')
                command=[sys.executable,'-B',str(HERE/'latch_probe.py'),mode,str(out)]
                r=subprocess.run(command,capture_output=True,text=True,timeout=3)
                (EVIDENCE/('latch-'+mode+'.log')).write_text(r.stdout+r.stderr)
                (EVIDENCE/('latch-'+mode+'-command.json')).write_text(json.dumps(dict(argv=command,raw_exit=r.returncode)))
                self.assertEqual(r.returncode,2 if mode=='positive' else 1,r.stderr)
                value=c.read_json(out)
                self.assertEqual(value['nonzero_arms'],0 if mode=='expired' else 1)
                self.assertTrue(value['no_default_restore'])
                self.assertEqual(value['raised'],1 if mode in ('normal','expired') else 0)
                if mode in ('normal','defer','failure'):self.assertEqual(value['cancellation_requests'],3)


class IndependentGuardTests(unittest.TestCase):
    def test_slow_full_hash_keeps_resource_observations(self):
        g=c.Guard(time.monotonic()+3,lambda:None,lambda:time.sleep(.7),None,rss=lambda:0,peak=lambda:0)
        g.start();g.close()
        self.assertLessEqual(g.maximum_sample_gap,.5);self.assertGreaterEqual(g.maximum_full_gap,.7)
        self.assertFalse(g.thread.is_alive());self.assertFalse(g.verify_thread.is_alive())
    def test_invalid_observations_and_inclusive_caps(self):
        for value in (-1,True,float('nan'),float('inf'),c.LIMIT+1):
            g=c.Guard(time.monotonic()+1,lambda:None,lambda:None,None,rss=lambda:value,peak=lambda:0)
            with self.subTest(value=value),self.assertRaises(c.Stop):g.sample()
        g=c.Guard(time.monotonic()+1,lambda:None,lambda:None,None,rss=lambda:c.LIMIT,peak=lambda:c.LIMIT,mps=lambda:c.LIMIT)
        g.sample()
    def test_wedged_verifier_cannot_claim_joined(self):
        block=threading.Event();g=c.Guard(time.monotonic()+3,lambda:None,lambda:None,None,rss=lambda:0,peak=lambda:0)
        g.start();g.verify=lambda:block.wait(2);g.last_full=time.monotonic()-4
        time.sleep(.08)
        try:
            with self.assertRaises(c.Stop):g.close()
            self.assertTrue(g.verify_thread.is_alive())
        finally:
            block.set();g.verify_thread.join(.5);g.thread.join(.5)
        self.assertFalse(g.verify_thread.is_alive())
    def test_slow_resource_and_full_IO_reject(self):
        for delay,full in ((.51,False),(5.01,True)):
            clock=[0.0]
            def slow():clock[0]+=delay;return 0
            g=c.Guard(20,lambda:None,slow if full else lambda:None,None,clock=lambda:clock[0],
                      rss=(lambda:0) if full else slow,peak=lambda:0)
            with self.subTest(full=full),self.assertRaises(c.Stop):g.sample(force=True)



class OwnershipAndIPCControls(unittest.TestCase):
    def test_unproven_group_never_signaled(self):
        import processes
        record=dict(pid=os.getpid(),pgid=os.getpid(),new_session_verified=False)
        with patch.object(os,'killpg') as kill:
            with self.assertRaises(c.Stop):processes.signal_once(record,signal.SIGTERM)
            kill.assert_not_called()
    def test_permission_census_failure_never_proves_absence(self):
        import processes
        with patch.object(os,'killpg',side_effect=PermissionError('injected owned probe EPERM')), \
             patch.object(processes,'census',side_effect=c.Stop('injected census unavailable')):
            with self.assertRaises(c.Stop):processes.absent(os.getpid()+1000000,time.monotonic()+1)
    def test_private_fd_sender_schema_sequence_and_T0(self):
        left,right=life.pair()
        a,b=life.Channel(left),life.Channel(right)
        try:
            a.send(dict(kind='start',t0_monotonic_hex=time.monotonic().hex()),time.monotonic()+1)
            with self.assertRaises(c.Stop):b.receive(time.monotonic()+1,sender=os.getpid()+1)
        finally:left.close();right.close()
    def test_exact_retained_9675_pin_union(self):
        import freeze
        old=freeze.old_union()
        self.assertEqual(len(old),9675)
        c.verify_files(old)

if __name__=='__main__':unittest.main(verbosity=2,failfast=True)
