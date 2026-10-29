"""CPU fake integration tests. They never import Torch or native runtime."""
from __future__ import annotations
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import binding as b
import evaluation
import terminal
import worker


class Journal:
    def __init__(self): self.rows=[]
    def emit(self,row): self.rows.append(row)
    def sync(self): pass


class FakeGuard:
    def __init__(self): self.arm=None; self.arm_frames=0
    def enter_arm(self,arm): self.arm=arm['id']; self.arm_frames=0
    def check(self,force=False): pass


class FakeSession:
    def __init__(self,arm,target): self.arm=arm; self.target=target; self.frames=0; self.calls=0; self.closed=False
    def update_once(self,*,check_guard):
        check_guard()
        self.calls+=1
        if getattr(self,'fail',False): raise RuntimeError('one-shot fake update fault')
        frame_count=64*self.arm['action_repeat']
        self.frames+=frame_count
        coll=SimpleNamespace(gameplay_frames=frame_count,decisions=1,startup_frames=13*64)
        metrics={'optimizer_steps':1,'epochs_completed':1,'early_stop_kl':False}
        boundary={'budget_reached':self.frames>=self.target,'gameplay_frames':self.frames}
        return coll,metrics,boundary
    def close(self): self.closed=True


class FakeRuntime:
    def __init__(self): self.sessions=[]; self.saved=[]; self.eval_calls=[]
    def begin_arm(self,arm,reg,stream_seeds,components,pool):
        self.asserted_capacity=len(stream_seeds[0])
        session=FakeSession(arm,reg['gameplay_frame_target_per_arm']);self.sessions.append(session);return session
    def save_final(self,session,out,arm,receipt,registration_sha):
        path=Path(out)/('checkpoint-'+arm['id']+'.fake')
        path.write_bytes(arm['id'].encode())
        item={'path':str(path),'sha256':b.sha(path),'model_fingerprint':arm['id']*2,
              'adam_fingerprint':arm['id']*2,'global_update':420+receipt['updates']}
        self.saved.append(item);return item
    def evaluate(self,path,digest,seeds,*,action_repeat,controller_seed,guard):
        import math
        guard(); self.eval_calls.append((Path(path).name,action_repeat,controller_seed))
        name=Path(path).name
        adjustment={'checkpoint-global-420.pt':0,'checkpoint-repeat4_training.fake':3,
                    'checkpoint-repeat1_training.fake':7}[name]
        rows=[]
        for index,seed in enumerate(seeds):
            alive=seed%50+adjustment; gameplay=alive+1
            rows.append(dict(episode_index=index,seed=seed,score_raw_fixed=0,
                score_delta_sum_raw_fixed=0,alive_frames=alive,gameplay_frames=gameplay,
                startup_frames=13,raw_frames=gameplay+13,action_repeat=action_repeat,
                terminated=True,truncated=False,policy_decisions=math.ceil(gameplay/action_repeat),
                episode_latency_ns=1,score=0.0,objective_return=alive/100-5,
                death_cause='unknown',fatal_gameplay_frame=gameplay,
                death_observed_lethal_contacts={'normal_enemy':0,'kamikaze_enemy':0,
                    'kamikaze_explosion':0,'static_pattern_rect':0,'moving_pattern_rect':0,'unknown':1}))
        return rows
    def empty_cache(self): pass


def fake_streams(reg):
    seeds=[[1000+slot]*reg['streams']['capacity_per_slot'] for slot in range(64)]
    return {'all':tuple(range(1024))},seeds,[['uniform']*len(row) for row in seeds]


class CapsuleTests(unittest.TestCase):
    def make_reg(self,out):
        p=b.protocol();d=b.design()
        starting=Path(out)/'checkpoint-global-420.pt';starting.write_bytes(b'starting420')
        return dict(run_id=b.RUN_ID,arms=d['arms'],gameplay_frame_target_per_arm=100,
            training_pair_seed=p['training_pair_seed'],streams={'capacity_per_slot':10},
            limits={'per_arm_gameplay_frames':10000,'max_updates_per_arm':8,'work_seconds':1000,
                'rss_bytes':1024,'mps_bytes':1024},
            evaluation=d['evaluation'],evaluation_seeds=p['evaluation']['seeds'],
            checkpoint_path=str(starting),checkpoint_sha256=b.sha(starting),
            exclusion_union=p['exclusion_union'],output=str(out))

    def test_campaign_evaluation_and_independent_terminal_recomputation(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);reg=self.make_reg(out);rt=FakeRuntime();guard=FakeGuard();journal=Journal()
            with patch.object(worker.seeds,'build_registered_streams',fake_streams):
                result=worker.campaign(reg,rt,out,guard,journal,'a'*64,dict())
            (out/'training.jsonl').write_text(''.join(json.dumps(row,separators=(',',':'))+'\n' for row in journal.rows))
            result.update(schema='one_frame_training_comparison_worker_v1',status='completed',run_id=b.RUN_ID,
                registration_sha256='a'*64,elapsed_seconds=1)
            resources=Journal();resources.emit({'rss_bytes':1,'mps_driver_bytes':1})
            resource_path=out/'resources.jsonl'
            resource_path.write_text(json.dumps(resources.rows[0],separators=(',',':'))+'\n')
            worker.evaluate_models(reg,rt,out,guard,result)
            result['status']='completed'
            report=terminal.validate_outputs(reg,result,'a'*64)
            self.assertEqual(report['status'],'complete')
            self.assertEqual(len(rt.eval_calls),6)
            self.assertEqual(result['paired_actual_gameplay_frames_difference'],128)
            self.assertEqual([s.calls for s in rt.sessions],[1,2])
            self.assertTrue(all(s.closed for s in rt.sessions))
            self.assertEqual(len(terminal.read_jsonl(out/'training.jsonl',strict=True)),5)

    def test_cluster_bootstrap_uses_shared_seed_draws_and_marginal_q1(self):
        seeds=list(range(1024))
        groups={name:[{'seed':seed,'alive_frames':seed%17+offset} for seed in seeds]
                for name,offset in (
                    ('starting420_repeat1_sampled',0),('starting420_repeat4_sampled',1),
                    ('repeat4_final_repeat1_sampled',2),('repeat4_final_repeat4_sampled',3),
                    ('repeat1_final_repeat1_sampled',8),('repeat1_final_repeat4_sampled',9))}
        left=evaluation.analyze(groups,seeds,draws=20,seed=202610290503)
        right=evaluation.analyze(groups,seeds,draws=20,seed=202610290503)
        self.assertEqual(left,right)
        self.assertEqual(left['primary'], 'repeat1_final minus repeat4_final Q1 under the same sampled repeat1 controller')
        self.assertFalse(left['automatic_selection'] or left['promoted'] or left['training_eligible'])

    def test_first_arm_fault_is_not_retried_or_advanced(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);reg=self.make_reg(out);rt=FakeRuntime();guard=FakeGuard();journal=Journal()
            def fail_begin(arm,reg,stream_seeds,components,pool):
                session=FakeSession(arm,reg['gameplay_frame_target_per_arm']);session.fail=True
                rt.sessions.append(session);return session
            rt.begin_arm=fail_begin
            with patch.object(worker.seeds,'build_registered_streams',fake_streams):
                with self.assertRaisesRegex(RuntimeError,'one-shot fake update fault'):
                    worker.campaign(reg,rt,out,guard,journal,'a'*64,{})
            self.assertEqual(len(rt.sessions),1)
            self.assertEqual(rt.sessions[0].calls,1)
            self.assertTrue(rt.sessions[0].closed)
            self.assertEqual(rt.saved,[])

if __name__=='__main__': unittest.main(verbosity=2)
