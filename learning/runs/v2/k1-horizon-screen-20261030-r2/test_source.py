"""Source/math and real dummy-child fixtures only; no Torch/native/model imports."""
import copy
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
from run_once import argv_for
import predecessor
import prepare


def row(index=1):
    n = 65536
    x = dict(schema='dodge_control_rate_update_telemetry_v2', kind='update_complete',
        arm_id='test', action_repeat=1, local_update=index, gameplay_frames_delta=n,
        policy_decisions_delta=n, gameplay_frames_total=index*n, policy_decisions_total=index*n,
        environment_count=64, actual_rollout_decisions_per_slot=1024, gamma=.99, gae_lambda=.9,
        maximum_epochs=4, effective_minibatch_size=2048, microbatch_size=512,
        learning_rate=3e-5, target_kl=.03, reward_scale=.1, epochs_completed=4,
        optimizer_steps=128, epoch_approx_kls=[.001,.002,.003,.004], approx_kl=.004,
        early_stop_kl=False, action_switches=10, eligible_action_comparisons=n-64,
        action_switch_rate=10/(n-64), entropy=1.2,value_loss=.5,clip_fraction=.1,
        explained_variance=None,explained_variance_defined=False,
        explained_variance_undefined_reason='PPO reports target population variance <= 1e-12',
        epochs_avoided=0,kl_threshold_hit=False,stopped_before_maximum_epochs=False,
        action_switches_per_1000_gameplay_frames=10000/n)
    for key in ['raw_advantages_before_minibatch_normalization','gae_returns','rollout_values','raw_reward','learner_reward']:
        x[key]=dict(count=n,mean=0.,population_std=1.,rms=1.,minimum=-1.,maximum=1.)
    return x


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.reg=dict(updates=36,envs=64,rollout=1024,effective_minibatch=2048,microbatch=512,
            arms=dict(shorter=dict(gamma=.99,gae_lambda=.9)),
            ppo=dict(update_epochs=4,learning_rate=3e-5,target_kl=.03,reward_scale=.1))
        self.job=dict(id='test',arm='shorter')

    def test_full_exposure_and_Adam_counts(self):
        out=c.validate_telemetry([row(i) for i in range(1,37)],self.reg,self.job)
        self.assertEqual(out,dict(updates=36,frames=2359296,Adam_steps=4608))

    def test_missing_duplicate_wrong_horizon_and_partial_optimizer_rejected(self):
        rows=[row(i) for i in range(1,37)]
        cases=[rows[:-1],rows[1:]+[rows[-1]]]
        for field,value in [('gamma',.995),('optimizer_steps',127),('clip_fraction',1.1),('explained_variance_defined',True)]:
            altered=copy.deepcopy(rows);altered[0][field]=value;cases.append(altered)
        for case in cases:
            with self.assertRaises(ValueError):c.validate_telemetry(case,self.reg,self.job)

    def test_publish_is_durable_exclusive_and_preserves_failed_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'receipt.json';c.save(p,dict(original=True));original=p.read_bytes()
            with self.assertRaises(FileExistsError):c.save(p,dict(replaced=True))
            self.assertEqual(p.read_bytes(),original)
            self.assertTrue(Path(str(p)+'.partial').exists())

    def test_command_uses_lexical_venv_and_exact_registration(self):
        reg=dict(interpreter='/project/python/.venv/bin/python')
        command=argv_for(reg,Path('/registration.json'),'a'*64,dict(id='job'))
        self.assertEqual(command[0],reg['interpreter'])
        self.assertEqual(command[1],'-B');self.assertEqual(command[-1],'job')
        self.assertIn('/registration.json',command);self.assertIn('a'*64,command)

    def test_exact_predecessor_lease_handoff_never_clears_or_overwrites_foreign_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json'
            old=dict(owner='failed');new=dict(owner='successor')
            path.write_text(json.dumps(dict(active_long_campaign=old,other_field=42)))
            reg=dict(state_path=str(path))
            c.lease_change(reg,old,new)
            self.assertEqual(c.read(path),dict(active_long_campaign=new,other_field=42))
            original=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'Exact lease differs'):
                c.lease_change(reg,old,None)
            self.assertEqual(path.read_bytes(),original)

    def test_failed_predecessor_read_only_audit(self):
        reg=prepare.registration(1)
        report=predecessor.audit(reg)
        self.assertEqual(report['status'],'acknowledged_failed_attempt_not_success')
        self.assertFalse(report['failed_attempt_accepted'])
        self.assertFalse(report['partial_weights_used'])

    def test_predecessor_rejects_recipe_change_and_live_group(self):
        reg=prepare.registration(1)
        altered=copy.deepcopy(reg);altered['ppo']['learning_rate']=1e-4
        with self.assertRaisesRegex(ValueError,'Restart recipe/input/limits changed'):
            predecessor.audit(altered)
        with patch.object(predecessor,'group_members',return_value=[dict(pid=123,rss_bytes=1)]):
            with self.assertRaisesRegex(ValueError,'Predecessor process group remains'):
                predecessor.audit(reg)

    @unittest.skipUnless(sys.platform=='darwin','Verified Darwin ABI fixture')
    def test_real_dummy_child_success_and_dead_group(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            result=lifecycle.run_child([sys.executable,'-B','-c','print("dummy")'],out,dict(os.environ),lambda _:None,10)
            self.assertTrue(result['directly_reaped']);self.assertTrue(result['group_absent'])
            self.assertEqual(result['raw_exit_code'],0)

    @unittest.skipUnless(sys.platform=='darwin','Verified Darwin ABI fixture')
    def test_real_dummy_nonzero_exit_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            with self.assertRaisesRegex(ValueError,'Child failure preserved'):
                lifecycle.run_child([sys.executable,'-B','-c','raise SystemExit(7)'],out,dict(os.environ),lambda _:None,10)
            r=c.read(out/'exit.json');self.assertEqual(r['raw_exit_code'],7);self.assertTrue(r['group_absent'])

    @unittest.skipUnless(sys.platform=='darwin','Verified Darwin ABI fixture')
    def test_real_dummy_timeout_terminates_before_reap(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            with self.assertRaisesRegex(ValueError,'Child failure preserved'):
                lifecycle.run_child([sys.executable,'-B','-c','import time;time.sleep(60)'],out,dict(os.environ),lambda _:None,.15,2)
            r=c.read(out/'exit.json');self.assertTrue(r['directly_reaped']);self.assertTrue(r['group_absent'])
            self.assertIn(int(signal.SIGTERM),r['cleanup_signals'])

    @unittest.skipUnless(sys.platform=='darwin','Verified Darwin ABI fixture')
    def test_post_spawn_receipt_failure_still_cleans_child(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);c.save(out/'launch.json',dict(existing=True))
            with self.assertRaisesRegex(ValueError,'Child failure preserved'):
                lifecycle.run_child([sys.executable,'-B','-c','import time;time.sleep(60)'],out,dict(os.environ),lambda _:None,10,2)
            self.assertTrue(c.read(out/'exit.json')['group_absent'])
            self.assertTrue(c.read(out/'launch.json')['existing'])


if __name__=='__main__':
    unittest.main(verbosity=2)
