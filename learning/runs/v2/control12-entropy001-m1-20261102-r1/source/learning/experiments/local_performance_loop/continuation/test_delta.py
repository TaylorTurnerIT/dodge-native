"""Only warm-start, mean-policy, machine-admission and paired-analysis deltas."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import common as c
from policy import advance
from warmstart import verify_only_lr_changed,load_control
from analysis import compare

R=dict(games=512,Mean=4500,Q1=1800,early_deaths=7,mean_score=50)
S=dict(initial_updates=72,segment_updates=12,patience_checks=3,gain_fraction=.02,max_checks=2500,
       minimum_Q1_fraction=.90,early_death_allowance_fraction=.02)
def fingerprint(x):return hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()


class DeltaTests(unittest.TestCase):
    def test_mean_gain_with_slight_Q1_dip_is_selected(self):
        _,d=advance({},dict(R,Mean=4700,Q1=1780),12,R,S)
        self.assertTrue(d['selected_as_best']);self.assertTrue(d['meaningful_mean_gain'])
    def test_tail_and_early_death_guardrails(self):
        for metrics in [dict(R,Mean=6000,Q1=1619),dict(R,Mean=6000,early_deaths=19)]:
            _,d=advance({},metrics,12,R,S);self.assertFalse(d['selected_as_best'])
    def test_real_mean_progress_continues_after72(self):
        state={}
        for u in range(12,97,12):state,d=advance(state,dict(R,Mean=4500*1.03**(u//12)),u,R,S)
        self.assertTrue(d['continue_training']);self.assertEqual(d['best_update'],96)
    def test_flat_run_honors_initial_horizon_then_stops(self):
        state={}
        for u in range(12,61,12):
            state,d=advance(state,R,u,R,S);self.assertTrue(d['continue_training'])
        state,d=advance(state,R,72,R,S)
        self.assertEqual(d['stop_reason'],'three_checks_without_2percent_mean_gain')
    def test_regression_never_erases_best(self):
        state,d=advance({},dict(R,Mean=4800),12,R,S)
        for u in range(24,73,12):state,d=advance(state,dict(R,Mean=4400),u,R,S)
        self.assertEqual(d['best_update'],12);self.assertFalse(d['continue_training'])
    def test_optimizer_only_lr_may_change(self):
        before=dict(state={'0':{'step':1536,'exp_avg':[1,2],'exp_avg_sq':[3,4]}},param_groups=[dict(params=[0],lr=3e-5,eps=1e-5)])
        after=copy.deepcopy(before);after['param_groups'][0]['lr']=1e-5
        verify_only_lr_changed(before,after,fingerprint)
        after['state']['0']['exp_avg'][0]=99
        with self.assertRaises(ValueError):verify_only_lr_changed(before,after,fingerprint)
        self.assertEqual(before['param_groups'][0]['lr'],3e-5)
    def test_warmstart_rejects_wrong_complete_boundary(self):
        state=dict(schema='performance_loop_learner_v1',arm='control',completed_updates=12,
            actual_gameplay_frames=786432,actual_Adam_steps=1536,full_environment_state_captured=False,
            promoted=False,registration_sha256='source-registration',model={'weights':[1,2]},optimizer={'moments':[3,4]})
        state['model_fingerprint']=fingerprint(state['model']);state['adam_fingerprint']=fingerprint(state['optimizer'])
        class TorchFixture:
            @staticmethod
            def load(*a,**kw):return copy.deepcopy(state)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'checkpoint.pt';path.write_bytes(b'fixture')
            binding=dict(path=str(path),sha256=c.sha(path),registration_sha256='source-registration',
                model_fingerprint=state['model_fingerprint'],adam_fingerprint=state['adam_fingerprint'])
            self.assertEqual(load_control({'warmstart':binding},TorchFixture,fingerprint)['completed_updates'],12)
            state['actual_Adam_steps']=1535
            with self.assertRaises(ValueError):load_control({'warmstart':binding},TorchFixture,fingerprint)
    def test_machine_admission_rejects_foreign_and_contender(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json';identity={'fixture':'M1'}
            state=dict(schema='dodge_machine_accelerator_v1',machine=identity,active_long_campaign=None,active_inference_diagnostic=None)
            c.save(path,state);reg=dict(state_path=str(path),machine={'fixture':'foreign'},expected_lease={'owner':'one'})
            with self.assertRaises(ValueError):c.cas_ledger(reg,None,reg['expected_lease'])
            self.assertEqual(c.read(path),state)
            reg['machine']=identity;c.cas_ledger(reg,None,reg['expected_lease'])
            with self.assertRaises(ValueError):c.cas_ledger(reg,None,{'owner':'two'})
            self.assertEqual(c.read(path)['active_long_campaign'],reg['expected_lease'])
    def test_paired_uncertainty_is_descriptive_and_deterministic(self):
        import numpy as np
        rows=[dict(seed=i,alive_frames=i) for i in range(512)]
        ref=[dict(seed=i,alive_frames=i-1) for i in range(512)]
        result=compare(rows,ref,np)
        self.assertEqual(result['mean_paired_bootstrap95_frames'],[1.,1.])
        self.assertEqual(result,compare(rows,ref,np))
        self.assertTrue(result['development_selection'])


if __name__=='__main__':unittest.main()
