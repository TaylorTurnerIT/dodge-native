"""Real mixed assignment policy on synthetic CPU fixtures, never native games."""
import copy
from dataclasses import fields
import importlib
from pathlib import Path
import sys
import types
import unittest

import torch

from successor import ppo
from successor.curriculum import CurriculumAdapter, HISTORICAL_RANGES, PINNED_PPO, PreparedUpdates
from successor.scheduler_reference import Completion, Scheduler
from fingerprints import fingerprint
from fakes import FakeEnv, TinyNet

DIGEST='a'*64


class MaintenanceTests(unittest.TestCase):
    def make(self,env,enabled=True):
        return CurriculumAdapter(env,enabled=enabled,digest=DIGEST,replica=1,
            exclusion_ranges=HISTORICAL_RANGES)

    def test_opening_cutoffs_leave_full_game_assignments_running(self):
        env=FakeEnv(64)
        boundary=self.make(env)
        stage=[slot for slot,row in boundary.assignments.items() if row.horizon==1000]
        full=[slot for slot,row in boundary.assignments.items() if row.horizon==18000]
        self.assertTrue(stage)
        self.assertTrue(full)
        self.assertEqual(sorted(stage+full),list(range(64)))
        boundary.begin_update(1)
        result=ppo.collect_rollout(TinyNet(),env,256,'cpu',config=PINNED_PPO,boundary_adapter=boundary)
        self.assertEqual(env.cutoffs,[(stage,[1000]*len(stage))])
        self.assertEqual(env.resets,[stage])
        self.assertEqual(len(result.completed_episodes),len(stage))
        self.assertTrue(all(row['horizon']==1000 for row in boundary.completions))
        for slot in full:
            self.assertEqual(env.infos[slot]['gameplay_frames'],1024)
            self.assertFalse(env.infos[slot]['terminated'])
            self.assertFalse(env.infos[slot]['truncated'])
            self.assertEqual(boundary.assignments[slot].horizon,18000)
        snap=boundary.snapshot()
        self.assertEqual(sum(row['raw_frames'] for row in snap['update_exposure']),64*1024)

    def test_full_game_completions_do_not_count_as_opening_mastery(self):
        scheduler=Scheduler(DIGEST)
        opening=[Completion(i//64,i%64,0,1000,True) for i in range(199)]
        full=[Completion(10+i//64,i%64,0,18000,True) for i in range(200)]
        scheduler.finish_update(1,opening+full)
        self.assertEqual(scheduler.target_episodes,199)
        self.assertEqual(scheduler.streak,1)
        for update in range(2,10):scheduler.finish_update(update,[])
        self.assertEqual(scheduler.generation,0)
        self.assertTrue(scheduler.finish_update(10,[Completion(0,0,0,1000,True)])['promoted'])

    def test_disabled_control_matches_completed_control_source_after_real_cpu_PPO(self):
        # Load the completed control's exact Python runtime under an inert alias.
        # Its package __init__ (which imports native code) is never executed.
        baseline=Path(__file__).resolve().parents[2]/'progressive1000-throughput-runtime-parent-20261027-r2/runtime/dodge_rl'
        package=types.ModuleType('completed_control_cpu_runtime')
        package.__path__=[str(baseline)]
        sys.modules[package.__name__]=package
        old=importlib.import_module(package.__name__+'.curriculum')
        old_ppo=importlib.import_module(package.__name__+'.ppo')
        first=TinyNet();second=copy.deepcopy(first)
        env1,env2=FakeEnv(64),FakeEnv(64)
        config=old_ppo.PPOConfig(learning_rate=3e-5)
        a=old.CurriculumAdapter(env1,enabled=False,digest=DIGEST,replica=1,exclusion_ranges=HISTORICAL_RANGES)
        b=self.make(env2,False)
        opt1=torch.optim.Adam(first.parameters(),lr=3e-5,eps=1e-5)
        opt2=torch.optim.Adam(second.parameters(),lr=3e-5,eps=1e-5)
        runner1=old.PreparedUpdates(first,opt1,a,config=config)
        runner2=PreparedUpdates(second,opt2,b)
        before=torch.random.get_rng_state()
        left,lmetrics,_=runner1.update_once()
        after=torch.random.get_rng_state()
        torch.random.set_rng_state(before)
        right,rmetrics,_=runner2.update_once()
        self.assertTrue(torch.equal(after,torch.random.get_rng_state()))
        self.assertEqual(fingerprint(first.state_dict()),fingerprint(second.state_dict()))
        self.assertEqual(fingerprint(opt1.state_dict()),fingerprint(opt2.state_dict()))
        self.assertEqual(lmetrics,rmetrics)
        for field in fields(right.batch):
            lvalue,rvalue=getattr(left.batch,field.name),getattr(right.batch,field.name)
            if rvalue is not None:self.assertTrue(torch.equal(lvalue,rvalue),field.name)
        self.assertEqual(env1.cutoffs,[])
        self.assertEqual(env2.cutoffs,[])


if __name__=='__main__':unittest.main()
