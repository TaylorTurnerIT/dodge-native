"""CPU/stdlib lifecycle and evaluator fixtures; no native games or lease writes."""

import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

import common as c
import lifecycle
import run_once
from evaluate_worker import Executor,domain_seed,summary


class SourceTests(unittest.TestCase):
    def test_real_command_builder_to_dummy_child_and_direct_reap(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'r1-control';out.mkdir()
            (root/'worker.py').write_text('import argparse\np=argparse.ArgumentParser()\np.add_argument("--registration")\np.add_argument("--sha256")\np.add_argument("--job")\na=p.parse_args()\nassert a.job=="r1-control"\nprint(a.sha256)\n')
            with patch.object(c,'HERE',root):
                argv=run_once.argv_for(dict(interpreter=sys.executable),root/'no-real-registration','dummy-hash',dict(id='r1-control'))
                result=lifecycle.run_child(argv,out,dict(os.environ),lambda _:None,10)
            self.assertTrue(result['directly_reaped'] and result['group_absent'])
            self.assertEqual(result['raw_exit_code'],0)
            self.assertIn('dummy-hash',(out/'worker.log').read_text())

    def test_failed_dummy_preserves_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            with self.assertRaisesRegex(ValueError,'Child failure preserved'):
                lifecycle.run_child([sys.executable,'-B','-c','raise SystemExit(7)'],out,dict(os.environ),lambda _:None,10)
            result=c.read(out/'exit.json');self.assertEqual(result['raw_exit_code'],7)
            self.assertTrue(result['directly_reaped'] and result['group_absent'])

    def test_dummy_timeout_terminates_before_reap(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            with self.assertRaisesRegex(ValueError,'Child failure preserved'):
                lifecycle.run_child([sys.executable,'-B','-c','import time;time.sleep(60)'],out,dict(os.environ),lambda _:None,.15,2)
            result=c.read(out/'exit.json')
            self.assertTrue(result['directly_reaped'] and result['group_absent'])
            self.assertIn(int(signal.SIGTERM),result['cleanup_signals'])

    def test_clean_identity_delay_start_neutral_fifo_and_reset(self):
        actions=[2,8,1,7,4,3,6]
        for delay in (0,1,4):
            condition='clean' if delay==0 else 'delay'+str(delay)
            executor=Executor(100,condition)
            got=[executor.apply(x) for x in actions]
            self.assertEqual(got,([0]*delay+actions)[:len(actions)])
            self.assertEqual(Executor(100,condition).apply(2),0 if delay else 2)

    def test_epsilon_includes_original_and_realized_changes(self):
        class Fixed:
            def random(self):return 0.0
            def randrange(self,n):self.n=n;return 3
        executor=Executor(100,'epsilon0.05');executor.rng=Fixed()
        self.assertEqual(executor.apply(3),3)
        self.assertEqual(executor.realized_changes,0)
        self.assertEqual(executor.apply(2),3)
        self.assertEqual(executor.realized_changes,1)
        self.assertEqual(executor.rng.n,9)
        self.assertNotEqual(domain_seed('policy',100,'clean'),domain_seed('executor',100,'clean'))
        self.assertNotEqual(domain_seed('executor',100,'clean'),domain_seed('executor',100,'delay1'))

    def test_marginal_quartiles_sort_each_condition(self):
        self.assertEqual(summary([9,3,1,7]),dict(Worst=1,Q1=1,Mean=5,Q4=9,Best=9))

    def test_publication_is_exclusive_and_no_lease_writer_exists(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'first.json';c.save(p,dict(first=True))
            with self.assertRaises(FileExistsError):c.save(p,dict(second=True))
            self.assertEqual(c.read(p),dict(first=True))
        self.assertFalse(hasattr(c,'lease_change'))
        self.assertNotIn('lease_change(',Path(run_once.__file__).read_text())

    def test_fixed_25_groups_paired_marginal_bootstrap_synthetic_rows(self):
        from evaluation_analysis import analyze
        models=['420','r1-control','r1-rays','r2-rays','r2-control']
        conditions=['clean','epsilon0.01','epsilon0.05','delay1','delay4']
        settings=dict(models=models,conditions=conditions,range_inclusive=[100,1123],
            groups=[dict(model=m,condition=k,count=1024 if k=='clean' else 256) for m in models for k in conditions],
            bootstrap_seed=109,bootstrap_draws=2000,milestones=[1000],early_death_max_frames=600)
        rows=[]
        for m in models:
            for k in conditions:
                for i in range(1024 if k=='clean' else 256):
                    rows.append(dict(model=m,condition=k,seed=100+i,alive_frames=100+i+(3 if m.endswith('rays') else 0)-(7 if k!='clean' else 0),terminated=True))
        result=analyze(rows,settings)
        self.assertEqual(len(result['groups']),25)
        for row in result['contrasts']:
            expected=3 if 'rays-minus-control' in row['comparison'] else -7
            self.assertEqual(row['difference']['Q1'],expected)
            self.assertEqual(row['percentile95']['Q1'],[expected,expected])


if __name__=='__main__':unittest.main(verbosity=2)
