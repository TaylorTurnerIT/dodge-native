"""CPU fake integration tests. They never import Torch or native runtime."""
from __future__ import annotations
import hashlib
import ast
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import binding as b
import audit
import evaluation
import launch
import observe
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
    def __init__(self): self.sessions=[]; self.saved=[]; self.recovery_calls=[]; self.eval_calls=[]
    def begin_arm(self,arm,reg,stream_seeds,components,pool):
        self.asserted_capacity=len(stream_seeds[0])
        session=FakeSession(arm,reg['gameplay_frame_target_per_arm'])
        session.stream_seeds=stream_seeds;session.env=FakeRecoveryEnv(stream_seeds)
        self.sessions.append(session);return session
    def save_final(self,session,out,arm,receipt,registration_sha):
        path=Path(out)/('checkpoint-'+arm['id']+'.fake')
        path.write_bytes(arm['id'].encode())
        item={'path':str(path),'sha256':b.sha(path),'model_fingerprint':arm['id']*2,
              'adam_fingerprint':arm['id']*2,'global_update':420+receipt['updates']}
        self.saved.append(item);return item
    def save_recovery_snapshot(self,session,out,arm,receipt,boundary,registration_sha):
        native=worker.capture_recovery_episode_metadata(session.env,session.stream_seeds)
        path=Path(out)/('recovery-'+arm['id']+'-'+str(boundary)+'.fake')
        path.write_bytes((arm['id']+str(boundary)).encode())
        sidecar=Path(str(path)+'.json')
        payload=dict(schema='one_frame_training_formal_recovery_sidecar_v1',run_id=b.RUN_ID,
            registration_sha256=registration_sha,arm=arm['id'],path=str(path),sha256=b.sha(path),
            recovery_boundary_gameplay_frames=boundary,actual_gameplay_frames=receipt['gameplay_frames'],
            completed_updates=receipt['updates'],global_update=420+receipt['updates'],
            model_fingerprint='a'*64,adam_fingerprint='b'*64,
            native_episode_indices=native['native_episode_indices'],
            native_episode_seeds=native['native_episode_seeds'],
            in_flight_metadata=native['in_flight_metadata'],
            in_flight_metadata_sha256=native['in_flight_metadata_sha256'],
            slot_seed_binding_sha256=native['slot_seed_binding_sha256'],
            in_flight_slots=native['in_flight_slots'],
            model_optimizer_rng_included=True,
            full_environment_state_captured=False,automatic_resume_authorized=False,
            training_eligible=False,promoted=False,automatic_selection=False)
        b.save(sidecar,payload);self.recovery_calls.append((arm['id'],boundary))
        return dict(path=str(path),sha256=b.sha(path),sidecar_path=str(sidecar),sidecar_sha256=b.sha(sidecar),
            recovery_boundary_gameplay_frames=boundary,actual_gameplay_frames=receipt['gameplay_frames'],
            completed_updates=receipt['updates'])
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


class FakeQualificationSession:
    def __init__(self,arm,target): self.arm=arm;self.target=target;self.frames=0;self.closed=False
    def update_once(self,*,check_guard):
        check_guard()
        count=min(64*self.arm['rollout_steps']*self.arm['action_repeat'],self.target-self.frames)
        self.frames+=count
        calls=min(self.arm['rollout_steps'],max(1,(count+64*self.arm['action_repeat']-1)//(64*self.arm['action_repeat'])))
        coll=SimpleNamespace(gameplay_frames=count,decisions=calls,startup_frames=64)
        metrics={'optimizer_steps':1,'epochs_completed':1,'early_stop_kl':False}
        return coll,metrics,{'budget_reached':self.frames>=self.target,'gameplay_frames':self.frames}
    def close(self): self.closed=True


class FakeQualificationRuntime:
    def __init__(self,*args,**kwargs): self.torch=None;self.sessions=[];self.saved=[];self.eval_calls=[]
    def begin_arm(self,arm,reg,stream_seeds,components,pool):
        session=FakeQualificationSession(arm,reg['gameplay_frame_target_per_arm']);self.sessions.append(session);return session
    def save_final(self,*args,**kwargs): self.saved.append(args);raise AssertionError('qualification attempted checkpoint write')
    def evaluate(self,*args,**kwargs): self.eval_calls.append(args);raise AssertionError('qualification attempted evaluation')
    def empty_cache(self): pass


def fake_streams(reg):
    seeds=[[1000+slot]*reg['streams']['capacity_per_slot'] for slot in range(64)]
    pool=worker.seeds.validate_pool(b.read(b.TRAINING_POOL))
    streams,components,_=worker.seeds.materialize(pool,reg['training_pair_seed'],10)
    return pool,streams,components


class FakeRecoveryEnv:
    def __init__(self,stream_seeds):
        self.stream_seeds=stream_seeds;self.episode_info_calls=0;self.step_calls=0;self.reset_calls=0
    def episode_info(self):
        self.episode_info_calls+=1
        return [dict(seed=dict(slot=slot,episode=0,actual_seed=self.stream_seeds[slot][0],evaluation=False),
            terminated=False,truncated=False,startup_frames=0,gameplay_frames=0)
            for slot in range(64)]
    def step(self,*args,**kwargs): self.step_calls+=1;raise AssertionError('capture stepped native environment')
    def reset(self,*args,**kwargs): self.reset_calls+=1;raise AssertionError('capture reset native environment')


class CapsuleTests(unittest.TestCase):
    def make_reg(self,out):
        p=b.protocol();d=b.design()
        starting=Path(out).parent/'checkpoint-global-420.pt';starting.write_bytes(b'starting420')
        return dict(run_id=b.RUN_ID,arms=d['arms'],gameplay_frame_target_per_arm=256,
            recovery_checkpoint_gameplay_interval=128,
            checkpoint_global_update=420,
            update_bounds={'formal_by_arm':{arm['id']:40 for arm in d['arms']}},
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
            result['resource_summary']=dict(samples=1,peak_rss_bytes=1,peak_mps_driver_bytes=1)
            (out/'worker-result.json').write_text(json.dumps(result,separators=(',',':')))
            report=terminal.validate_outputs(reg,result,'a'*64)
            self.assertEqual(report['status'],'complete')
            self.assertEqual(len(rt.eval_calls),6)
            self.assertEqual(len(rt.recovery_calls),4)
            self.assertEqual(result['paired_actual_gameplay_frames_difference'],0)
            self.assertEqual([s.calls for s in rt.sessions],[1,4])
            self.assertTrue(all(s.closed for s in rt.sessions))
            self.assertEqual(len(terminal.read_jsonl(out/'training.jsonl',strict=True)),11)

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

    def test_script_entrypoint_runs_after_realarm_definition(self):
        tree=ast.parse(Path(worker.__file__).read_text())
        class_index=next(i for i,node in enumerate(tree.body)
            if isinstance(node,ast.ClassDef) and node.name=='RealArm')
        main_index=next(i for i,node in enumerate(tree.body)
            if isinstance(node,ast.If) and isinstance(node.test,ast.Compare)
            and isinstance(node.test.left,ast.Name) and node.test.left.id=='__name__')
        self.assertLess(class_index,main_index)

    def test_qualification_deadline_uses_phase_limits_not_formal_limits(self):
        formal=dict(limits={'work_seconds':32400,'total_seconds':32530})
        qualification=dict(limits={'work_seconds':1800,'total_seconds':1930})
        self.assertEqual(observe.phase_deadlines(formal,100),(32500,32630))
        self.assertEqual(observe.phase_deadlines(qualification,100),(1900,2030))

    def test_parent_audit_requires_exact_flat_artifact_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);(out/'receipt.json').write_text('{}\n')
            manifest={'receipt.json':b.sha(out/'receipt.json')}
            self.assertEqual(audit.validate_artifact_manifest(out,manifest),manifest)
            with self.assertRaisesRegex(ValueError,'artifact manifest'):
                audit.validate_artifact_manifest(out,{'receipt.json':'0'*64})
            (out/'receipt.json').write_text('changed\n')
            with self.assertRaisesRegex(ValueError,'artifact manifest'):
                audit.validate_artifact_manifest(out,manifest)

    def test_recovery_capture_preserves_64_native_slots_without_step_or_reset(self):
        pool=worker.seeds.validate_pool(b.read(b.TRAINING_POOL))
        stream_seeds,_,_=worker.seeds.materialize(pool,b.protocol()['training_pair_seed'],64)
        env=FakeRecoveryEnv(stream_seeds)
        captured=worker.capture_recovery_episode_metadata(env,stream_seeds)
        self.assertEqual(env.episode_info_calls,1)
        self.assertEqual((env.step_calls,env.reset_calls),(0,0))
        self.assertEqual(set(captured['native_episode_indices']),{str(slot) for slot in range(64)})
        self.assertEqual(len(captured['in_flight_metadata']),64)
        self.assertEqual(captured['in_flight_slots'],64)
        reg={'training_pair_seed':b.protocol()['training_pair_seed'],
            'streams':{'capacity_per_slot':64}}
        payload=dict(captured)
        self.assertTrue(terminal.validate_recovery_episode_metadata(payload,reg,pool))
        wrong=copy.deepcopy(payload);wrong['native_episode_indices']['0']=1
        with self.assertRaisesRegex(ValueError,'registered stream'):
            terminal.validate_recovery_episode_metadata(wrong,reg,pool)
        for infos in ([],[{}]*63):
            broken=FakeRecoveryEnv(stream_seeds);broken.episode_info=lambda infos=infos:infos
            with self.assertRaises(ValueError):
                worker.capture_recovery_episode_metadata(broken,stream_seeds)
        duplicate=FakeRecoveryEnv(stream_seeds)
        duplicate.episode_info=lambda:[dict(row,seed=dict(row['seed'],slot=0)) if i==1 else row
            for i,row in enumerate(FakeRecoveryEnv(stream_seeds).episode_info())]
        with self.assertRaisesRegex(ValueError,'native recovery episode seed/index'):
            worker.capture_recovery_episode_metadata(duplicate,stream_seeds)

    def test_qualification_rejects_target_that_needs_more_than_eight_updates(self):
        q=b.read(b.PARENT/'qualification-protocol.json')
        target=9*65536;q=dict(q,gameplay_frame_target_per_arm=target,
            gameplay_frame_cap_per_arm=target,max_PPO_updates_per_arm=8,
            max_startup_frames_per_arm=100000,max_policy_decisions_per_arm=1000000,
            max_vector_calls_per_arm=1000000,max_raw_frames_including_startup_per_arm=1000000)
        capacity=9
        reg=dict(run_id=b.RUN_ID,gameplay_frame_target_per_arm=target,
            training_pair_seed=q['training_pair_seed'],
            checkpoint_sha256=q['checkpoint_sha256'],
            streams={'qualification_capacity_per_slot':capacity,'qualification_slot_stream_digests':['b'*64]*64},
            arms=b.design()['arms'],exclusion_union=[],limits={'work_seconds':1800,
                'per_arm_gameplay_frames':target,'rss_bytes':2**40,'mps_bytes':2**40})
        pool={'all':tuple(range(512))};stream_rows=[[1]*capacity for _ in range(64)]
        materialized=(stream_rows,[['uniform']*capacity for _ in range(64)],['b'*64]*64)
        rt=FakeQualificationRuntime();journal=Journal();guard=FakeGuard()
        with patch.object(worker.seeds,'validate_pool',return_value=pool), \
             patch.object(worker.seeds,'verify_exclusions',return_value=None), \
             patch.object(worker.seeds,'frame_stream_capacity',return_value=capacity), \
             patch.object(worker.seeds,'materialize',return_value=materialized):
            with self.assertRaisesRegex(ValueError,'update cap reached before frame target'):
                worker.qualification_campaign(reg,q,rt,guard,journal,'c'*64)
        self.assertEqual(rt.sessions[0].frames,8*65536)
        self.assertTrue(rt.sessions[0].closed)

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

    def test_formal_arm_bound_allows_more_than_eight_updates(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);reg=self.make_reg(out);reg['gameplay_frame_target_per_arm']=2304
            rt=FakeRuntime();guard=FakeGuard();journal=Journal()
            with patch.object(worker.seeds,'build_registered_streams',fake_streams):
                worker.campaign(reg,rt,out,guard,journal,'a'*64,{})
            self.assertEqual([s.calls for s in rt.sessions],[9,36])

    def test_qualification_acceptance_dispatch_and_terminal_have_no_checkpoint_or_eval(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);q=b.read(b.PARENT/'qualification-protocol.json')
            reg=dict(run_id=q['run_id'],phase='qualification',status='parent_registered',
                launch_authority=False,
                qualification_protocol_path=str(b.PARENT/'qualification-protocol.json'),
                qualification_protocol_sha256=b.sha(b.PARENT/'qualification-protocol.json'),
                checkpoint_sha256=q['checkpoint_sha256'],arms=b.design()['arms'],
                training_pair_seed=q['training_pair_seed'],
                gameplay_frame_target_per_arm=q['gameplay_frame_target_per_arm'],
                streams={'qualification_capacity_per_slot':7170,
                    'qualification_slot_stream_digests':['b'*64]*64},
                limits=q['limits'],exclusion_union=[],output=str(root/'worker-output'),
                attempt_claim_path=str(root/'attempt.claimed'),launch_marker_path=str(root/'launch.claimed'),
                import_policy={'pycache_prefix':str(root/'empty-pycache')},
                runtime_manifest_sha256='e'*64,source_manifest_path='/nonexistent/source.json',
                source_manifest_sha256='a'*64)
            reg_path=root/'registration.json';b.save(reg_path,reg);reg_sha=b.sha(reg_path)
            source_path=root/'source.json';b.save(source_path,b.source_acceptance_document(reg['source_manifest_sha256']))
            source_sha=b.sha(source_path);gate_path=root/'gate.json'
            gate_pins={str(source_path.resolve()):source_sha}
            gate=b.approval_document(reg_sha,reg['source_manifest_sha256'],gate_pins,run_id=reg['run_id'])
            b.save(gate_path,gate);gate_sha=b.sha(gate_path)
            with patch.object(b,'validate_static',return_value=True), \
                 patch.object(b,'validate_runtime_source_acceptance',return_value={}):
                accepted,_=launch.acceptances(str(reg_path),reg_sha,str(gate_path),gate_sha,
                    str(source_path),source_sha)
            self.assertEqual(accepted['phase'],'qualification')
            envelope_path=root/'envelope.json';envelope_sha='c'*64
            b.save(reg['attempt_claim_path'],dict(schema=b.ATTEMPT_SCHEMA,run_id=reg['run_id'],
                registration_sha256=reg_sha))
            b.save(reg['launch_marker_path'],dict(run_id=reg['run_id'],registration_sha256=reg_sha,
                envelope_sha256=envelope_sha))
            envelope=dict(phase='qualification',run_id=reg['run_id'],registration=str(reg_path),
                registration_sha256=reg_sha,source_acceptance=str(source_path),source_acceptance_sha256=source_sha,
                gate_acceptance=str(gate_path),gate_acceptance_sha256=gate_sha,path=str(envelope_path),sha256=envelope_sha)
            rt=FakeQualificationRuntime()
            pool={'all':tuple(range(512)),'pool_sha256':'d'*64}
            materialized=([[1000+slot]*7170 for slot in range(64)],
                [['uniform']*7170 for _ in range(64)],['b'*64]*64)
            with patch.object(b,'load_envelope',return_value=(envelope,reg)), \
                 patch.object(b,'verify_bound',return_value=True), \
                 patch.object(b,'check_lease',return_value=None), \
                 patch.object(b,'validate_runtime_source_acceptance',return_value={}), \
                 patch.object(worker,'RealRuntime',return_value=rt), \
                 patch.object(worker.seeds,'validate_pool',return_value=pool), \
                 patch.object(worker.seeds,'verify_exclusions',return_value=None), \
                 patch.object(worker.seeds,'materialize',return_value=materialized):
                worker.run(str(envelope_path),envelope_sha)
            receipt=b.read(Path(reg['output'])/'worker-result.json')
            audit=terminal.validate_qualification_outputs(reg,receipt,reg_sha)
            self.assertEqual(audit['status'],'qualification_complete')
            self.assertEqual([session.frames for session in rt.sessions],[458816,458816])
            self.assertTrue(all(session.closed for session in rt.sessions))
            self.assertEqual(rt.saved,[]);self.assertEqual(rt.eval_calls,[])

    def test_incremental_resource_tail_handles_partial_append_and_matches_strict_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);out.mkdir(exist_ok=True)
            path=out/'resources.jsonl';tail=b.WorkerResourceTail(out)
            self.assertEqual(tail.poll()['samples'],0)
            first=json.dumps({'rss_bytes':11,'mps_driver_bytes':7},separators=(',',':'))+'\n'
            second=json.dumps({'rss_bytes':5,'mps_driver_bytes':19},separators=(',',':'))
            path.write_bytes(first.encode()+second[:12].encode())
            self.assertEqual(tail.poll(),dict(samples=1,peak_rss_bytes=11,peak_mps_driver_bytes=7))
            with path.open('ab') as stream: stream.write((second[12:]+'\n').encode())
            summary=tail.poll()
            audited=b.worker_resources(out,strict=True)
            self.assertEqual(summary,dict(samples=audited['samples'],
                peak_rss_bytes=audited['peak_rss_bytes'],
                peak_mps_driver_bytes=audited['peak_mps_driver_bytes']))
            self.assertEqual(tail.summary(strict=True),summary)

    def test_incremental_resource_tail_rejects_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);path=out/'resources.jsonl'
            path.write_text('{"rss_bytes":1,"mps_driver_bytes":2}\n')
            tail=b.WorkerResourceTail(out);tail.poll()
            path.write_bytes(b'')
            with self.assertRaisesRegex(ValueError,'truncated after observation'):
                tail.poll()

if __name__=='__main__': unittest.main(verbosity=2)
