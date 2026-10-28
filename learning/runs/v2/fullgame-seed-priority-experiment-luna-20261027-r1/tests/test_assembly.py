"""Successor integration controls. Artificial seeds, rows and learner only."""
import copy
from dataclasses import fields
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch

import contracts as c
import expanded_eval as evaluation
from deferred import evaluator_cli
import runtime_adapter
import successor_identity
import worker
from successor import ppo
from successor.curriculum import CurriculumAdapter, PreparedUpdates, HISTORICAL_RANGES
from fakes import FakeEnv,TinyNet


TOY_SEEDS=list(range(1,1025))


def row(index,alive=999,cause='unavailable'):
    cap=alive==18000
    return dict(episode_index=index,seed=TOY_SEEDS[index],score_raw_fixed=0,score_delta_sum_raw_fixed=0,
        score=0,alive_frames=alive,gameplay_frames=alive+int(not cap),startup_frames=13,
        terminated=not cap,truncated=cap,death_cause=None if cap else cause,
        fatal_gameplay_frame=None,death_observed_lethal_contacts=None,
        objective_return=alive/100-5*int(not cap))


class IdentityTests(unittest.TestCase):
    def templates(self):
        return [c.read(c.HERE/f'registration-template-replica-1-{arm}.json') for arm in c.ARMS]

    def test_matched_pair_and_shared_constant_optimizer(self):
        left,right=self.templates()
        self.assertEqual(set(successor_identity.matched_pair(left,right)),{'arm','curriculum_enabled','run_id'})
        right['ppo']['target_kl']=.04
        with self.assertRaisesRegex(ValueError,'beyond enablement'):
            successor_identity.matched_pair(left,right)
        for arm in c.ARMS:
            self.assertEqual({c.transition.controller_lr(arm,u) for u in range(373,433)},{3e-5})

    def test_inert_and_pending_states_fail_before_source_or_constructor(self):
        for reg in self.templates():
            with patch.object(c,'verify_inputs',side_effect=AssertionError('must not reach imports')):
                with self.assertRaisesRegex(ValueError,'inert template'):c.validate_static(reg)
                reg['status']='parent_registered'
                with self.assertRaisesRegex(ValueError,'pending/unreserved'):c.validate_static(reg)

    def test_full_union_required_before_environment_constructor(self):
        reg=self.templates()[0]
        reg['exclusion_union']=[list(r) for r in HISTORICAL_RANGES]
        constructed=[]
        adapter=object.__new__(runtime_adapter.RuntimeAdapter)
        adapter.reg=reg;adapter.game=SimpleNamespace(VecDodgeEnv=lambda **kw:constructed.append(kw))
        adapter.context={}
        with self.assertRaisesRegex(ValueError,'six ranges'):adapter.make_env()
        self.assertEqual(constructed,[])

    def test_seed_hash_transcription_known_independent_tuple(self):
        # This known tuple was computed from the frozen native documented tuple,
        # not from any study vector or actual environment.
        vector={'seeds':dict(constructor_init_seed=11,python_random_seed=12,numpy_global_seed=13,
            torch_cpu_global_seed=14,action_sampler_torch_mps_seed=15,env_master_seed=16)}
        union=[list(r) for r in c.transition.EXPECTED_EXCLUSION_RANGES]
        controls=c.episode_controls(vector,[0]*64,union)
        def finalizer(value):
            value &= 0xffffffffffffffff
            value=(value^(value>>30))*0xbf58476d1ce4e5b9 & 0xffffffffffffffff
            value=(value^(value>>27))*0x94d049bb133111eb & 0xffffffffffffffff
            return value^(value>>31)
        base=finalizer(16^0x444f4447455f5632)^finalizer(0x9e3779b97f4a7c15)^finalizer(0xd1b54a32d192ed03)
        self.assertEqual(controls[0]['first_actual_seed'],finalizer(base^finalizer(0x94d049bb133111eb))>>32)
        bad=copy.deepcopy(union);bad.remove([0xD3000000,0xD30003FF])
        with self.assertRaises(ValueError):c.episode_controls(vector,[0]*64,bad)

    def test_reset_batch_collision_refuses_before_native_construction(self):
        adapter=object.__new__(runtime_adapter.RuntimeAdapter)
        adapter.reg={'exclusion_union':[list(r) for r in c.transition.EXPECTED_EXCLUSION_RANGES],
                     'vector':{'seeds':{'env_master_seed':16}}}
        adapter.boundary=SimpleNamespace(consumed_actual_seeds={123})
        ended={slot:{'seed':{'episode':0}} for slot in (0,1)}
        with patch.object(c,'seed_metadata',return_value={'first_actual_seed':123,'rejection_counter':0}):
            with self.assertRaisesRegex(ValueError,'collision'):adapter.preflight_reset([0],ended)
        self.assertFalse(hasattr(adapter,'pending_reset_seeds'))
        with patch.object(c,'seed_metadata',return_value={'first_actual_seed':456,'rejection_counter':0}):
            with self.assertRaisesRegex(ValueError,'collision'):adapter.preflight_reset([0,1],ended)
        self.assertFalse(hasattr(adapter,'pending_reset_seeds'))

    def test_runtime_source_native_member_drift_and_substitution(self):
        manifest=c.read(c.HERE/'runtime-manifest.json')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'member.py').write_text('safe')
            m=root/'manifest.json';m.write_text(json.dumps({'files':{'member.py':c.sha(root/'member.py')}}))
            expected=c.sha(m);c.verify_manifest(m,expected,root)
            (root/'member.py').write_text('substitute')
            with self.assertRaisesRegex(ValueError,'pin drift'):c.verify_manifest(m,expected,root)
        self.assertIn('dodge_rl/_native.cpython-312-darwin.so',manifest['files'])
        self.assertNotEqual(manifest['files']['dodge_rl/_native.cpython-312-darwin.so'],'29d49a1317ebe1367932e88514f744242a8e67cf7e6d7d0ab64d5f008cbed567')


class UpdateTests(unittest.TestCase):
    def prepared(self):
        env=FakeEnv(64);model=TinyNet()
        boundary=CurriculumAdapter(env,enabled=True,digest='a'*64,replica=1,exclusion_ranges=HISTORICAL_RANGES)
        optimizer=torch.optim.Adam(model.parameters(),lr=3e-5,eps=1e-5)
        return PreparedUpdates(model,optimizer,boundary,device='cpu'),env,boundary

    def test_registered_device_guard_and_neural_allowlist(self):
        prepared,env,boundary=self.prepared()
        for device in ('cuda','cpu:0',True,None):
            with self.assertRaisesRegex(ValueError,'registered cpu or mps'):
                PreparedUpdates(prepared.model,prepared.optimizer,boundary,device=device)
        with patch.object(torch.backends.mps,'is_available',return_value=False):
            with self.assertRaisesRegex(ValueError,'unavailable'):
                PreparedUpdates(prepared.model,prepared.optimizer,boundary,device='mps')
        observation=env.observations();observation.update(seed=123,generation=17,hidden_state='forbidden')
        self.assertEqual(tuple(ppo._observation_tensors(observation)),successor_identity.NEURAL_INPUTS)
        self.assertEqual(set(f.name for f in fields(ppo.RolloutBatch)),set(ppo.RolloutBatch.__dataclass_fields__))
        self.assertNotIn('generation',ppo.RolloutBatch.__dataclass_fields__)

    def test_events_durable_before_PPO_failure_and_scheduler_stays(self):
        prepared,env,boundary=self.prepared()
        expected_opening_completions=sum(row.horizon==1000 for row in boundary.assignments.values())
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'events.jsonl'
            with path.open('x') as stream:
                boundary.event_sink=lambda event:worker.emit(stream,event)
                def failure(*args,**kw):
                    rows=[json.loads(line) for line in path.read_text().splitlines()]
                    self.assertEqual(sum(r['kind']=='completion' for r in rows),expected_opening_completions)
                    self.assertEqual(sum(r['kind']=='returned_reset' for r in rows),1)
                    self.assertEqual(sum(r['kind']=='reset_assignment' for r in rows),expected_opening_completions)
                    self.assertTrue(any(r['kind']=='before_PPO' for r in rows))
                    raise RuntimeError('synthetic PPO failure after durable events')
                with patch.object(ppo,'ppo_update',side_effect=failure):
                    with self.assertRaisesRegex(RuntimeError,'durable events'):
                        prepared.update_once(journal_collection_events=lambda a,b:worker.emit(stream,dict(kind='before_PPO')))
            self.assertEqual(boundary.scheduler.update,0)
            self.assertEqual(prepared.state,'failed')
            before=env.step_calls
            with self.assertRaises(ValueError):prepared.update_once()
            self.assertEqual(env.step_calls,before)

    def test_guard_and_journal_failure_consume_before_PPO(self):
        prepared,env,boundary=self.prepared()
        with patch.object(ppo,'ppo_update',side_effect=AssertionError('must not optimize')):
            with self.assertRaisesRegex(RuntimeError,'journal failed'):
                prepared.update_once(journal_collection_events=lambda a,b:(_ for _ in ()).throw(RuntimeError('journal failed')))
        self.assertEqual(boundary.completed_updates,0)
        self.assertEqual(prepared.state,'failed')
        prepared,env,boundary=self.prepared()
        with self.assertRaisesRegex(RuntimeError,'guard'):
            prepared.update_once(check_guard=lambda:(_ for _ in ()).throw(RuntimeError('guard')))
        self.assertEqual(env.step_calls,0)
        self.assertEqual(prepared.state,'failed')

    def test_incomplete_PPO_cannot_promote_and_actual_steps_no_topup(self):
        prepared,env,boundary=self.prepared()
        def incomplete(*args,**kw):
            kw['progress'].update(complete=False,in_update=True,optimizer_steps=3)
            return {'optimizer_steps':3}
        with patch.object(ppo,'ppo_update',side_effect=incomplete):
            with self.assertRaisesRegex(ValueError,'incomplete PPO'):prepared.update_once()
        self.assertEqual(boundary.scheduler.update,0)
        self.assertEqual(prepared.actual_optimizer_steps,0)
        self.assertEqual(prepared.progress['optimizer_steps'],3)

    def test_failed_collection_does_not_double_count_prior_Adam_steps(self):
        prepared,env,boundary=self.prepared()
        prepared.actual_optimizer_steps=32
        prepared.progress={'complete':True,'in_update':False,'optimizer_steps':32}
        with self.assertRaisesRegex(RuntimeError,'new collection stopped'):
            prepared.update_once(check_guard=lambda:(_ for _ in ()).throw(RuntimeError('new collection stopped')))
        self.assertEqual(prepared.snapshot()['actual_optimizer_steps_including_failed_update'],32)

    def test_worker_global60_fixed_cadence_no_selection(self):
        class Field:
            def numel(self):return 16384
            def sum(self):return self
            def item(self):return 65536
        class Adapter:
            def __init__(self):
                self.parent={'abandoned_current_episodes':[]}
                self.env=SimpleNamespace(episode_info=lambda:[],batch_info=lambda:{'next_episode_indices':[1]*64})
                self.boundary=SimpleNamespace(event_sink=None,assignment_events=[])
                self.optimizer=SimpleNamespace(param_groups=[{'lr':3e-5}]);self.calls=0
            def make_env(self):pass
            def snapshot(self):return {'calls':self.calls}
            def update(self,guard,progress,journal):
                self.calls+=1;journal([],[]);progress.update(complete=True,in_update=False)
                return {'optimizer_steps':1},SimpleNamespace(batch=SimpleNamespace(actions=Field(),elapsed_raw_frames=Field())),{'promoted':False}
            def integrity_checkpoint(self,out,local,counters,digest):
                return dict(path=str(out/f'integrity-{local}'),global_update=local,formal_comparison_endpoint=local==60)
        adapter=Adapter();reg={'output':'unused','limits':{'work_seconds':1790}}
        with tempfile.TemporaryDirectory() as directory:
            result={}
            worker.study_loop(reg,adapter,Path(directory),SimpleNamespace(check=lambda:None),'fake',0,result)
            self.assertEqual(adapter.calls,60)
            self.assertEqual(result['counters']['optimizer_steps'],60)
            self.assertEqual([p['global_update'] for p in result['integrity_checkpoints']],[12,24,36,48,60])
            self.assertEqual(result['evaluated_updates'],[])
            self.assertFalse(result['automatic_selection']);self.assertFalse(result['promoted'])
        adapter=Adapter()
        reg.update(purpose='timing_probe24',schedule=c.PROBE_SCHEDULE)
        with tempfile.TemporaryDirectory() as directory:
            result={}
            worker.study_loop(reg,adapter,Path(directory),SimpleNamespace(check=lambda:None),'fake',0,result)
            self.assertEqual(adapter.calls,24)
            self.assertEqual(result['status'],'completed_timing_probe')
            self.assertIsNone(result['formal_comparison_endpoint'])
            self.assertEqual([p['global_update'] for p in result['integrity_checkpoints']],[12,24])
            self.assertEqual(result['counters']['environment_decisions'],393216)
            self.assertEqual((result['phase_update'],result['cumulative_update']),(348,396))


class EvaluationTests(unittest.TestCase):
    def test_milestone_tie_fatal_exclusion_quarters_and_outcomes(self):
        rows=[row(i,999 if i<256 else 1000 if i<768 else 18000) for i in range(1024)]
        result=evaluation.summarize(rows,TOY_SEEDS)
        self.assertEqual(result['performance'],dict(Worst=999,Q1=999,Mean=(256*999+512*1000+256*18000)/1024,Q4=18000,Best=18000))
        self.assertEqual(result['milestones']['1000']['numerator'],768)
        self.assertEqual(rows[0]['gameplay_frames'],1000)
        self.assertEqual(sum(result['death_causes'].values())+result['caps'],1024)
        self.assertEqual(result['death_causes']['unavailable'],768)

    def test_named_unknown_cap_conservation_and_invalid_missing(self):
        rows=[row(i,1000) for i in range(1024)]
        for index,cause in [(0,'normal_enemy'),(1,'unknown')]:
            rows[index].update(death_cause=cause,fatal_gameplay_frame=1001,
                death_observed_lethal_contacts={name:int(name==cause) for name in evaluation.DEATH_CAUSES[:-1]})
        result=evaluation.summarize(rows,TOY_SEEDS)
        self.assertEqual(result['death_causes']['normal_enemy'],1)
        self.assertEqual(result['death_causes']['unknown'],1)
        with self.assertRaisesRegex(ValueError,'row count'):evaluation.summarize(rows[:-1],TOY_SEEDS)
        partial=evaluation.incomplete_accounting(rows[:-1]+[dict(rows[-1],alive_frames=1001)],TOY_SEEDS)
        self.assertEqual(partial['missing_rows'],1);self.assertEqual(partial['invalid_rows'],1)
        self.assertEqual(sum(partial['death_causes'].values())+partial['caps'],1023)

    def test_fixed_pairs_shared_parent_and_descriptive_spread(self):
        policies={name:[row(i,1000) for i in range(1024)] for name in evaluation.POLICY_IDS}
        for replica in range(1,4):
            policies[f'replica-{replica}-{c.ARMS[1]}']=[row(i,1000+replica) for i in range(1024)]
        result=evaluation.compare(policies,TOY_SEEDS)
        self.assertEqual(result['planned_episodes'],7168)
        self.assertEqual(result['parent_evaluations'],1)
        self.assertEqual(result['across_three_descriptive']['curriculum_minus_control']['Q1'],dict(values=[1,2,3],mean=2,min=1,max=3,sample_stddev=1))
        del policies[evaluation.POLICY_IDS[0]]
        with self.assertRaisesRegex(ValueError,'incomplete pair'):evaluation.compare(policies,TOY_SEEDS)

    def test_evaluator_template_and_semantic_drift_fail_before_imports(self):
        reg=c.read(c.HERE/'deferred/evaluation-template.json')
        with self.assertRaisesRegex(ValueError,'template is inert'):evaluator_cli.validate_evaluation(reg)
        reg.update(status='parent_registered',cohort_state='reserved_parent_approved',history_state='freshness_parent_approved',reservation_state='parent_reserved')
        for key,value in [('action_mode','greedy'),('cutoff_enabled',True),('row_count',1023),('normal_start',False)]:
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'pin differs'):
                evaluator_cli.validate_evaluation({**reg,key:value})

    def test_production_loop_uses_sampled_actions_and_owned_tuple_exclusions(self):
        seen=[]
        class Env:
            def __init__(self,**kw):
                self.seed=kw['seeds_by_slot'][0][0]
                self.assertions=kw
                seen.append(kw['excluded_seed_ranges'])
            def episode_info(self):return [dict(seed=dict(evaluation=True,actual_seed=self.seed),startup_frames=13,gameplay_frames=0)]
            def observations(self):return {'global_feats':np.zeros((1,1),dtype=np.float32)}
            def step(self,actions):
                self.action=int(actions[0]);seen.append(self.action)
                info=dict(seed=dict(actual_seed=self.seed),bootstrap=False,score_raw_fixed=0,
                    score_delta_sum_raw_fixed=0,alive_frames=0,gameplay_frames=1,startup_frames=13,objective_return=-5)
                return dict(info=[info],elapsed_raw_frames=[1],terminated=[True],truncated=[False])
        class Policy:
            _expanded_eval_device='cpu'
            def __call__(self,*args):return SimpleNamespace(logits=torch.tensor([[100.,0.,0.,0.,0.,0.,0.,0.,0.]]))
        with patch.object(torch.distributions.Categorical,'sample',return_value=torch.tensor([7])) as sample:
            rows=evaluation._production_rows(Policy(),Env,('global_feats',),lambda *args:dict(death_cause='unavailable',fatal_gameplay_frame=None,death_observed_lethal_contacts=None),[1],[(2,3)],lambda:None)
        self.assertEqual(seen,[[(2,3)],7]);self.assertEqual(sample.call_count,1)
        self.assertEqual(rows[0]['alive_frames'],0)
