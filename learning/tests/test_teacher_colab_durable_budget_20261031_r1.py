"""Pure accounting fixtures; no account, VM, native engine or training calls."""
import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'experiments/teacher_colab_durable_budget_20261031_r1.py'
spec=importlib.util.spec_from_file_location('durable_budget_fixture',SOURCE)
c=importlib.util.module_from_spec(spec);sys.modules[spec.name]=c;spec.loader.exec_module(c)
ASSIGNMENTS=[dict(endpoint='owned',accelerator='A100')]


def raw(balance=100.,rate=6.73,count=1):
    return dict(currentBalance=balance,consumptionRateHourly=rate,assignmentsCount=count)


def observe(guard,now,balance=100.,phase='training',**kwargs):
    return guard.observe(raw(balance,**kwargs),ASSIGNMENTS,'owned',now,
                         request_started=now-1,phase=phase)


class BudgetTests(unittest.TestCase):
    def test_unchanged_balance_all_work_then_final_assignment_absence(self):
        guard=c.TrainingBudget(100.,0)
        observe(guard,1,phase='setup')
        for now in [1200,3600,10800,18000,22519]:
            result=observe(guard,now)
            self.assertTrue(result['work_admitted'])
            self.assertFalse(result['balance_freshness_proven'])
            self.assertAlmostEqual(result['projected_total_CU'],3+23000*7/3600)
        result=guard.final(raw(count=0,rate=0),[],23000,request_started=22999)
        self.assertTrue(result['budget_within_limits'])

    def test_reported_six_hour_debit_does_not_double_count_elapsed_charge(self):
        guard=c.TrainingBudget(100.,0)
        for now in [1,1200,3600,10800,18000,22519]:
            result=observe(guard,now,balance=100.-3.-now*6.73/3600)
            self.assertLessEqual(result['projected_total_CU'],48)

    def test_bad_quotes_fail_before_work(self):
        for rate in [0,7.001,None,float('nan'),float('inf')]:
            with self.subTest(rate=rate),self.assertRaises(ValueError):
                observe(c.TrainingBudget(100.,0),1,rate=rate)

    def test_ownership_and_unexpected_cost_reject(self):
        with self.assertRaisesRegex(ValueError,'Projected cost'):
            observe(c.TrainingBudget(100.,0),1,balance=95.8)
        guard=c.TrainingBudget(100.,0)
        with self.assertRaisesRegex(ValueError,'Exact owned A100'):
            guard.observe(raw(),[dict(endpoint='foreign',accelerator='T4')],'owned',1,
                          request_started=0,phase='training')

    def test_setup_work_deadline_suspend_and_backwards_clock_reject(self):
        with self.assertRaisesRegex(ValueError,'setup exceeded'):
            observe(c.TrainingBudget(100.,0),1201,phase='setup')
        with self.assertRaisesRegex(ValueError,'Work deadline'):
            observe(c.TrainingBudget(100.,0),22520)
        guard=c.TrainingBudget(100.,0);observe(guard,1200)
        with self.assertRaisesRegex(ValueError,'clock reversed'):observe(guard,1199)
        with self.assertRaisesRegex(ValueError,'assigned-time'):observe(guard,30000)

    def test_final_requires_fresh_absence_and_no_budget_relaxation(self):
        with self.assertRaisesRegex(ValueError,'zero-assignment'):
            c.TrainingBudget(100.,0).final(raw(),ASSIGNMENTS,1,request_started=0)
        with self.assertRaisesRegex(ValueError,'limits differ'):
            c.TrainingBudget(100.,0,c.Config(maximum_assigned_seconds=23001))
        with self.assertRaisesRegex(ValueError,'insufficient'):
            c.TrainingBudget(47.99,0)

    def test_receipt_reserve_cannot_restart_training(self):
        guard=c.TrainingBudget(100.,0);observe(guard,1200)
        result=observe(guard,22520,phase='retrieval')
        self.assertFalse(result['work_admitted']);self.assertTrue(result['receipt_retrieval_admitted'])
        with self.assertRaisesRegex(ValueError,'cannot rearm'):observe(guard,22521)


if __name__=='__main__':unittest.main(verbosity=2)
