"""One-use, paired equal-gameplay-frame training worker with fakeable orchestration."""
from __future__ import annotations
import argparse
import copy
import gc
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import sys
import time

import binding as b
import evaluation
import fingerprints
import seeds


class Journal:
    def __init__(self, path):
        self.stream = Path(path).open('x')

    def emit(self, value):
        self.stream.write(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n')
        self.stream.flush()

    def sync(self):
        self.stream.flush(); os.fsync(self.stream.fileno())

    def close(self):
        self.sync(); self.stream.close()


class Guard:
    """Bound each arm, wall time, memory, exact lease and parent cancellation."""
    def __init__(self, reg, started, resources, torch=None, clock=time.monotonic):
        self.reg, self.started, self.resources, self.torch, self.clock = reg, started, resources, torch, clock
        self.peak_rss = self.peak_mps = 0
        self.arm = None
        self.arm_frames = 0
        self.last = float('-inf')

    def enter_arm(self, arm):
        self.arm = arm['id']; self.arm_frames = 0

    def check(self, force=False):
        now = self.clock(); lim = self.reg['limits']
        b.need(now-self.started < lim['work_seconds'], 'registered work deadline')
        b.need(not os.path.lexists(b.CANCEL), 'parent cancellation marker exists')
        b.need(self.arm_frames <= lim['per_arm_gameplay_frames'], 'per-arm actual gameplay-frame cap')
        if force or now-self.last >= .25:
            b.check_lease(self.reg)
            rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform == 'darwin' else 1024)
            mps = int(self.torch.mps.driver_allocated_memory()) if self.torch is not None else 0
            b.need(rss <= lim['rss_bytes'] and mps <= lim['mps_bytes'], 'worker RSS/MPS ceiling')
            self.peak_rss, self.peak_mps = max(self.peak_rss, rss), max(self.peak_mps, mps)
            self.resources.emit(dict(elapsed_seconds=now-self.started, rss_bytes=rss,
                                     mps_driver_bytes=mps, arm=self.arm))
            self.last = now


def capture_recovery_episode_metadata(env, stream_seeds):
    """Read current native per-slot metadata without stepping or resetting the environment."""
    b.need(callable(getattr(env,'episode_info',None)), 'native episode_info read API missing')
    infos=env.episode_info()
    b.need(type(infos) in (list,tuple) and len(infos)==64,
        'recovery capture requires exactly64 native episode slots')
    b.need(type(stream_seeds) is list and len(stream_seeds)==64,
        'recovery seed binding requires exactly64 registered slot streams')
    rows=[]; indices={}; actual_seeds={}
    for slot,info in enumerate(infos):
        b.need(type(info) is dict and type(info.get('seed')) is dict,
            'native recovery episode metadata malformed')
        seed=info['seed']; episode=seed.get('episode'); actual=seed.get('actual_seed')
        # Native explicit training-pool streams carry evaluation=True; actual
        # training role is established by exact registered per-slot seed binding.
        b.need(type(seed.get('slot')) is int and seed.get('slot')==slot
            and seed.get('evaluation') is True
            and type(episode) is int and 0<=episode<len(stream_seeds[slot])
            and type(actual) is int and 0<=actual<=0xffffffff
            and actual==stream_seeds[slot][episode],
            'native recovery episode seed/index differs from registered slot stream')
        terminated=info.get('terminated'); truncated=info.get('truncated')
        b.need(type(terminated) is bool and type(truncated) is bool,
            'native recovery episode terminal flags malformed')
        indices[str(slot)]=episode; actual_seeds[str(slot)]=actual
        rows.append(dict(slot=slot,episode_index=episode,actual_seed=actual,
            in_flight=not (terminated or truncated),native_info=copy.deepcopy(info)))
    b.need(set(indices)=={str(slot) for slot in range(64)},
        'native recovery slot/index/seed map is incomplete or duplicated')
    metadata_sha=hashlib.sha256(b.canonical(rows)).hexdigest()
    seed_binding_sha=hashlib.sha256(b.canonical(dict(episode_indices=indices,actual_seeds=actual_seeds))).hexdigest()
    return dict(native_episode_indices=indices,native_episode_seeds=actual_seeds,
        in_flight_metadata=rows,in_flight_slots=sum(row['in_flight'] for row in rows),
        in_flight_metadata_sha256=metadata_sha,slot_seed_binding_sha256=seed_binding_sha)


def campaign(reg, rt, out, guard, training, registration_sha, result):
    """Run two arms in fixed order, restoring the exact checkpoint independently."""
    out = Path(out); result.update(arms=[], training_eligible=False, promoted=False, automatic_selection=False)
    pool, stream_seeds, components = seeds.build_registered_streams(reg)
    b.need(len(stream_seeds) == 64 and all(len(row) == reg['streams']['capacity_per_slot'] for row in stream_seeds),
           'registered per-slot stream dimensions differ')
    totals = []
    for index, arm in enumerate(reg['arms']):
        guard.enter_arm(arm)
        update_bound=reg['update_bounds']['formal_by_arm'][arm['id']]
        session = rt.begin_arm(arm, reg, stream_seeds, components, pool)
        arm_result = dict(id=arm['id'], action_repeat=arm['action_repeat'], updates=0,
                          update_bound=update_bound,
                          optimizer_steps=0, policy_decisions=0, gameplay_frames=0,
                          startup_frames=0, update_metrics=[], recovery_checkpoints=[])
        next_recovery=reg['recovery_checkpoint_gameplay_interval']
        try:
            while True:
                guard.check(force=True)
                if arm_result['gameplay_frames'] >= reg['gameplay_frame_target_per_arm']:
                    break
                b.need(arm_result['updates'] < update_bound, 'formal arm update bound exhausted before target')
                collection, metrics, boundary = session.update_once(check_guard=guard.check)
                frames = int(collection.gameplay_frames)
                decisions = int(collection.decisions)
                startup = int(collection.startup_frames)
                b.need(frames > 0 and decisions > 0 and startup >= 0, 'returned PPO update lacks frame accounting')
                arm_result['updates'] += 1
                arm_result['optimizer_steps'] += int(metrics['optimizer_steps'])
                arm_result['policy_decisions'] += decisions * 64
                arm_result['gameplay_frames'] += frames
                arm_result['startup_frames'] += startup
                guard.arm_frames = arm_result['gameplay_frames']
                row = dict(update=arm_result['updates'], decisions=decisions, gameplay_frames=frames,
                           startup_frames=startup, optimizer_steps=int(metrics['optimizer_steps']),
                           epochs_completed=metrics.get('epochs_completed'), early_stop_kl=metrics.get('early_stop_kl'),
                           budget_reached=bool(boundary['budget_reached']))
                arm_result['update_metrics'].append(row)
                training.emit(dict(kind='update', arm=arm['id'], **row))
                guard.check()
                while arm_result['gameplay_frames'] >= next_recovery:
                    snapshot=rt.save_recovery_snapshot(session,out,arm,arm_result,
                        next_recovery,registration_sha)
                    arm_result['recovery_checkpoints'].append(snapshot)
                    training.emit(dict(kind='recovery_checkpoint',arm=arm['id'],snapshot=snapshot))
                    next_recovery+=reg['recovery_checkpoint_gameplay_interval']
                b.need(arm_result['updates'] <= update_bound, 'formal per-arm update ceiling exceeded')
                b.need(arm_result['gameplay_frames'] <= reg['limits']['per_arm_gameplay_frames'],
                       'per-arm frame ceiling exceeded')
                b.need(bool(boundary['budget_reached']) ==
                       (arm_result['gameplay_frames'] >= reg['gameplay_frame_target_per_arm']),
                       'adapter frame-target boundary differs')
                if boundary['budget_reached']:
                    break
            target = reg['gameplay_frame_target_per_arm']; cap = reg['limits']['per_arm_gameplay_frames']
            b.need(target <= arm_result['gameplay_frames'] <= cap, 'arm did not close registered frame budget')
            b.need(arm_result['gameplay_frames']-target < 64*arm['action_repeat'],
                   'final vector call overshoot differs')
            checkpoint = rt.save_final(session, out, arm, arm_result, registration_sha)
            arm_result['checkpoint'] = checkpoint
        finally:
            session.close()
            del session
            gc.collect()
            rt.empty_cache()
        totals.append(arm_result['gameplay_frames'])
        result['arms'].append(arm_result)
        training.emit(dict(kind='arm_complete', arm=arm_result))
        training.sync()
    b.need(abs(totals[0]-totals[1]) <= 256, 'paired arm frame totals differ by more than256')
    result['paired_actual_gameplay_frames_difference'] = abs(totals[0]-totals[1])
    return result


def qualification_campaign(reg, qualification, rt, guard, training, registration_sha):
    """Run disposable resource qualification through the same one-update API; no save or eval calls."""
    b.need(qualification['launch_authority'] is False
        and all(qualification[k] is True for k in ('no_checkpoint_writes','no_evaluation_seed_use',
            'no_formal_weight_reuse','no_promotion','no_retry')),
        'qualification authority boundary differs')
    target=qualification['gameplay_frame_target_per_arm']
    frame_cap=qualification['gameplay_frame_cap_per_arm']
    update_cap=qualification['max_PPO_updates_per_arm']
    b.need(type(target) is int and type(frame_cap) is int and type(update_cap) is int
        and target>0 and frame_cap>=target and 0<update_cap<=8,
        'qualification frame/update bounds differ')
    pool=seeds.validate_pool(b.read(b.TRAINING_POOL))
    seeds.verify_exclusions(pool,reg['exclusion_union'])
    capacity=seeds.frame_stream_capacity(target)
    b.need(capacity==reg['streams']['qualification_capacity_per_slot'],
        'qualification seed capacity is not derived from its own frame target')
    stream_seeds,components,digests=seeds.materialize(pool,reg['training_pair_seed'],capacity)
    b.need(digests==reg['streams']['qualification_slot_stream_digests'],
        'qualification paired seed streams differ from registered digests')
    qreg=dict(reg)
    qreg['gameplay_frame_target_per_arm']=target
    qreg['limits']=dict(reg['limits'],work_seconds=qualification['wall_cap_seconds'],
        per_arm_gameplay_frames=frame_cap,rss_bytes=qualification['RSS_bytes'],
        mps_bytes=qualification['MPS_driver_bytes'])
    guard.reg=qreg
    report=dict(schema='one_frame_training_resource_qualification_receipt_v1',
        run_id=qualification['run_id'],registration_sha256=registration_sha,
        qualification_protocol_sha256=b.sha(b.PARENT/'qualification-protocol.json'),
        checkpoint_sha256=reg['checkpoint_sha256'],arms=[],no_checkpoint_writes=True,
        no_evaluation_seed_use=True,no_formal_weight_reuse=True,no_retry=True,
        checkpoint_writes=0,evaluation_calls=0,
        promoted=False,training_eligible=False,automatic_selection=False)
    totals=[]
    for arm in reg['arms']:
        guard.enter_arm(arm)
        session=rt.begin_arm(arm,qreg,stream_seeds,components,pool)
        item=dict(id=arm['id'],action_repeat=arm['action_repeat'],updates=0,optimizer_steps=0,
            vector_calls=0,policy_decisions=0,gameplay_frames=0,startup_frames=0,
            update_metrics=[])
        try:
            while item['gameplay_frames']<target:
                guard.check(force=True)
                b.need(item['updates']<update_cap,'qualification PPO update cap reached before frame target')
                collection,metrics,boundary=session.update_once(check_guard=guard.check)
                frames=int(collection.gameplay_frames); calls=int(collection.decisions)
                startup=int(collection.startup_frames)
                b.need(frames>0 and calls>0 and startup>=0,'qualification update lacks returned cost')
                item['updates']+=1; item['optimizer_steps']+=int(metrics['optimizer_steps'])
                item['vector_calls']+=calls; item['policy_decisions']+=calls*64
                item['gameplay_frames']+=frames; item['startup_frames']+=startup
                guard.arm_frames=item['gameplay_frames']
                row=dict(update=item['updates'],vector_calls=calls,gameplay_frames=frames,
                    startup_frames=startup,optimizer_steps=int(metrics['optimizer_steps']),
                    epochs_completed=metrics.get('epochs_completed'),
                    budget_reached=bool(boundary['budget_reached']))
                item['update_metrics'].append(row)
                training.emit(dict(kind='qualification_update',arm=arm['id'],**row))
                b.need(item['gameplay_frames']<=frame_cap
                    and item['startup_frames']<=qualification['max_startup_frames_per_arm']
                    and item['policy_decisions']<=qualification['max_policy_decisions_per_arm']
                    and item['vector_calls']<=qualification['max_vector_calls_per_arm'],
                    'qualification per-arm frame/startup/decision/vector cap exceeded')
                b.need(bool(boundary['budget_reached'])==(item['gameplay_frames']>=target),
                    'qualification final partial update did not close exact registered frame target')
                guard.check()
                if boundary['budget_reached']: break
            b.need(target<=item['gameplay_frames']<=frame_cap
                and item['gameplay_frames']-target<64*arm['action_repeat'],
                'qualification frame target/one-vector-call overshoot differs')
            b.need(item['updates']<=update_cap and item['updates']>0,
                'qualification update count exceeds its separate eight-update cap')
            b.need(item['gameplay_frames']+item['startup_frames']
                <=qualification['max_raw_frames_including_startup_per_arm'],
                'qualification raw-frame cap exceeded')
        finally:
            session.close(); del session; gc.collect(); rt.empty_cache()
        item['peak_rss_bytes']=guard.peak_rss
        item['peak_mps_driver_bytes']=guard.peak_mps
        b.need(item['peak_rss_bytes']<=qualification['RSS_bytes']
            and item['peak_mps_driver_bytes']<=qualification['MPS_driver_bytes'],
            'qualification measured resource limit exceeded')
        totals.append(item['gameplay_frames']); report['arms'].append(item)
        training.emit(dict(kind='qualification_arm_complete',arm=item)); training.sync()
    b.need(abs(totals[0]-totals[1])<=256,'qualification paired frame totals differ by more than256')
    report['paired_actual_gameplay_frames_difference']=abs(totals[0]-totals[1])
    report['status']='completed'
    return report


def evaluate_models(reg, rt, out, guard, result):
    import screen
    groups = {}
    models = [('starting420', reg['checkpoint_path'], reg['checkpoint_sha256'])]
    for arm in result['arms']:
        models.append((arm['id'].replace('_training', '_final'), arm['checkpoint']['path'], arm['checkpoint']['sha256']))
    for model_id, path, digest in models:
        for repeat in reg['evaluation']['control_repeats']:
            group_id = f'{model_id}_repeat{repeat}_sampled'
            guard.check(force=True)
            rows = rt.evaluate(path, digest, reg['evaluation_seeds'], action_repeat=repeat,
                               controller_seed=reg['evaluation']['controller_seed'], guard=guard.check)
            screen.validate_rows(rows, reg['evaluation_seeds'])
            groups[group_id] = rows
            receipt = dict(schema='one_frame_training_comparison_evaluation_group_v1', group=group_id,
                           model=model_id, action_repeat=repeat, checkpoint_sha256=digest,
                           seeds_sha256=evaluation.digest(reg['evaluation_seeds']), rows=rows)
            b.save(out/(group_id+'.json'), receipt)
            result.setdefault('evaluations', []).append(dict(group=group_id, rows=len(rows), sha256=b.sha(out/(group_id+'.json'))))
    report = evaluation.analyze(groups, reg['evaluation_seeds'], draws=reg['evaluation']['bootstrap_draws'],
                                seed=reg['evaluation']['bootstrap_seed'])
    b.save(out/'comparison.json', report)
    result['comparison_sha256'] = b.sha(out/'comparison.json')
    result['primary_success'] = report['primary_success']
    return report


class RealRuntime:
    """Loads only pinned runtime members after accepted worker startup."""
    def __init__(self, reg, torch=None, registration_sha256=None):
        import importlib
        self.reg = reg
        self.registration_sha256 = registration_sha256
        b.need(not any(name == 'dodge_rl' or name.startswith('dodge_rl.') for name in sys.modules),
               'dodge_rl must start unloaded')
        sys.path.insert(0, reg['runtime_root'])
        self.np = importlib.import_module('numpy')
        self.torch = importlib.import_module('torch') if torch is None else torch
        self.game = importlib.import_module('dodge_rl')
        self.ckpt = importlib.import_module('dodge_rl.checkpoints')
        self.ppo = importlib.import_module('dodge_rl.ppo')
        self.seeded = importlib.import_module('dodge_rl.seeded_training')
        self.curriculum = importlib.import_module('dodge_rl.curriculum')
        self.teacher = importlib.import_module('dodge_rl.models.teacher')
        self.fingerprint = fingerprints.fingerprint
        manifest, root = b.runtime_files()
        for name, module in tuple(sys.modules.items()):
            if name == 'dodge_rl' or name.startswith('dodge_rl.'):
                path = Path(module.__file__).resolve()
                b.need(path.is_relative_to(root) and b.sha(path) == manifest['files'].get(str(path.relative_to(root))),
                       'loaded module origin or runtime pin differs: '+name)
        b.need(self.torch.backends.mps.is_available(), 'MPS unavailable')
        self.torch.set_num_threads(4)
        self.pool_doc = b.read(b.TRAINING_POOL)
        self.pool = seeds.validate_pool(self.pool_doc)
        self.strata = {row['seed']: row['stratum'] for row in self.pool_doc['seeds']}

    def begin_arm(self, arm, reg, stream_seeds, components, pool):
        torch = self.torch
        state = self.ckpt.load_checkpoint(Path(reg['checkpoint_path']), expected_sha256=reg['checkpoint_sha256'])
        self.ckpt.require_complete_update(state)
        b.need((state.get('global_update'), state.get('phase_update'), state.get('cumulative_update')) == (420, 804, 852),
               'starting learner update identity differs')
        model = self.teacher.OmniscientEntityTeacher().to(device='mps', dtype=torch.float32)
        model.load_state_dict(state['model'], strict=True)
        optimizer = torch.optim.Adam(model.parameters(), lr=3e-5, eps=1e-5)
        optimizer.load_state_dict(state['optimizer'])
        b.need(self.fingerprint(model.state_dict()) == reg['model_fingerprint'], 'checkpoint model fingerprint differs')
        b.need(self.fingerprint(optimizer.state_dict()) == reg['adam_fingerprint'], 'checkpoint Adam fingerprint differs')
        b.need(all(group['lr'] == 3e-5 and group['eps'] == 1e-5 for group in optimizer.param_groups),
               'restored Adam learning rate/epsilon differs')
        random.seed(reg['training_pair_seed']); self.np.random.seed(reg['training_pair_seed'] % 2**32)
        torch.manual_seed(reg['training_pair_seed']); torch.mps.manual_seed(reg['training_pair_seed'])
        env = self.game.VecDodgeEnv(batch_size=64, action_repeat=arm['action_repeat'], difficulty=2,
            patterns_enabled=True, powerups_enabled=True, raw_frame_cap=18000, num_threads=4, chunk_size=8,
            render_pixels=False, auxiliary_targets=False, seeds_by_slot=stream_seeds,
            initial_episode_indices=[0]*64, excluded_seed_ranges=[tuple(r) for r in reg['exclusion_union']])
        adapter = self.seeded.SeededTrainingAdapter(env, seeds_by_slot=stream_seeds, components_by_slot=components,
            strata_by_seed=self.strata, training_pool_values=pool['all'], exclusions=reg['exclusion_union'],
            rollout_steps=arm['rollout_steps'], gameplay_frame_target=reg['gameplay_frame_target_per_arm'])
        config = self.ppo.PPOConfig(gamma=arm['gamma'], gae_lambda=arm['gae_lambda'], learning_rate=3e-5,
            adam_eps=1e-5, clip_coef=.2, vf_coef=.5, ent_coef=.01, max_grad_norm=.5, update_epochs=4,
            minibatch_size=arm['microbatch'], target_kl=.03, reward_scale=.1)
        prepared = self.curriculum.PreparedUpdates(model, optimizer, adapter, config=config, device='mps',
            rollout_steps=arm['rollout_steps'], microbatch_size=arm['microbatch'],
            effective_minibatch_size=arm['effective_minibatch'],
            gameplay_frame_target=reg['gameplay_frame_target_per_arm'])
        return RealArm(self, env, model, optimizer, adapter, prepared, state)

    def _save_torch_artifact(self,path,state):
        torch = self.torch
        import tempfile
        fd, staging = tempfile.mkstemp(prefix='.'+path.name+'.pending-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as f:
                torch.save(state, f); f.flush(); os.fsync(f.fileno())
            os.link(staging, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            os.unlink(staging)
        return b.sha(path)

    def _rng_state(self):
        return dict(python=random.getstate(), numpy=self.np.random.get_state(),
            torch_cpu=self.torch.get_rng_state(), torch_mps=self.torch.mps.get_rng_state())

    def save_recovery_snapshot(self,session,out,arm,receipt,boundary,registration_sha):
        adapter=session.adapter.snapshot()
        native=capture_recovery_episode_metadata(session.env,session.adapter.seeds_by_slot)
        path=Path(out)/('recovery-'+arm['id']+'-frame-'+f'{boundary:012d}'+'.pt')
        state=dict(schema='one_frame_training_formal_recovery_snapshot_v1',run_id=b.RUN_ID,
            registration_sha256=registration_sha,arm=arm,checkpoint_role='recovery_only_ineligible',
            recovery_boundary_gameplay_frames=boundary,actual_gameplay_frames=receipt['gameplay_frames'],
            startup_frames=receipt['startup_frames'],completed_updates=receipt['updates'],
            global_update=420+session.prepared.adapter.completed_updates,
            model=self.ckpt._cpu_copy(session.model.state_dict()),
            optimizer=self.ckpt._cpu_copy(session.optimizer.state_dict()),rng=self._rng_state(),
            model_fingerprint=self.fingerprint(session.model.state_dict()),
            adam_fingerprint=self.fingerprint(session.optimizer.state_dict()),
            native_episode_indices=native['native_episode_indices'],
            native_episode_seeds=native['native_episode_seeds'],
            in_flight_metadata=native['in_flight_metadata'],
            in_flight_metadata_sha256=native['in_flight_metadata_sha256'],
            slot_seed_binding_sha256=native['slot_seed_binding_sha256'],
            adapter_metadata=adapter,full_environment_state_captured=False,
            automatic_resume_authorized=False,training_eligible=False,promoted=False,
            automatic_selection=False)
        digest=self._save_torch_artifact(path,state)
        sidecar=Path(str(path)+'.json')
        doc=dict(schema='one_frame_training_formal_recovery_sidecar_v1',run_id=b.RUN_ID,
            registration_sha256=registration_sha,arm=arm['id'],path=str(path),sha256=digest,
            recovery_boundary_gameplay_frames=boundary,actual_gameplay_frames=receipt['gameplay_frames'],
            startup_frames=receipt['startup_frames'],completed_updates=receipt['updates'],
            global_update=state['global_update'],model_fingerprint=state['model_fingerprint'],
            adam_fingerprint=state['adam_fingerprint'],
            native_episode_indices=native['native_episode_indices'],
            native_episode_seeds=native['native_episode_seeds'],
            in_flight_metadata=native['in_flight_metadata'],
            in_flight_metadata_sha256=native['in_flight_metadata_sha256'],
            slot_seed_binding_sha256=native['slot_seed_binding_sha256'],
            in_flight_slots=native['in_flight_slots'],model_optimizer_rng_included=True,
            full_environment_state_captured=False,automatic_resume_authorized=False,
            training_eligible=False,promoted=False,automatic_selection=False)
        b.save(sidecar,doc)
        return dict(path=str(path),sha256=digest,sidecar_path=str(sidecar),sidecar_sha256=b.sha(sidecar),
            recovery_boundary_gameplay_frames=boundary,actual_gameplay_frames=receipt['gameplay_frames'],
            completed_updates=receipt['updates'],global_update=state['global_update'])

    def save_final(self, session, out, arm, receipt, registration_sha):
        path = Path(out)/('checkpoint-'+arm['id']+'-final.pt')
        state = dict(schema='one_frame_training_comparison_checkpoint_v1', run_id=b.RUN_ID,
            registration_sha256=registration_sha, arm=arm, global_update=420+session.prepared.adapter.completed_updates,
            model=self.ckpt._cpu_copy(session.model.state_dict()), optimizer=self.ckpt._cpu_copy(session.optimizer.state_dict()),
            model_fingerprint=self.fingerprint(session.model.state_dict()),
            adam_fingerprint=self.fingerprint(session.optimizer.state_dict()),
            actual_gameplay_frames=receipt['gameplay_frames'], training_eligible=False,
            promoted=False, automatic_selection=False)
        digest=self._save_torch_artifact(path,state)
        return dict(path=str(path), sha256=digest, model_fingerprint=state['model_fingerprint'],
                    adam_fingerprint=state['adam_fingerprint'], global_update=state['global_update'])

    def evaluate(self, path, digest, eval_seeds, *, action_repeat, controller_seed, guard):
        import screen
        from death_telemetry import death_fields
        b.need(b.sha(path) == digest, 'evaluation model bytes changed before load')
        if Path(path).resolve() == b.CHECKPOINT.resolve():
            state = self.ckpt.load_checkpoint(Path(path), expected_sha256=digest)
            b.need((state.get('global_update'),state.get('phase_update'),state.get('cumulative_update'))==(420,804,852)
                and self.fingerprint(state['model'])==self.reg['model_fingerprint'],
                'starting420 checkpoint metadata/model differs')
        else:
            state = self.torch.load(path, map_location='cpu', weights_only=False)
            b.need(state.get('schema')=='one_frame_training_comparison_checkpoint_v1'
                and state.get('run_id')==b.RUN_ID and state.get('registration_sha256')==self.registration_sha256
                and state.get('promoted') is False and state.get('automatic_selection') is False
                and state.get('training_eligible') is False
                and self.fingerprint(state['model'])==state.get('model_fingerprint'),
                'final checkpoint identity/model fingerprint differs')
        model = self.teacher.OmniscientEntityTeacher().to('mps', dtype=self.torch.float32)
        model.load_state_dict(state['model'], strict=True); model.eval(); model._expanded_eval_device = 'mps'
        random.seed(controller_seed); self.np.random.seed(controller_seed % 2**32)
        self.torch.manual_seed(controller_seed); self.torch.mps.manual_seed(controller_seed)
        rows = screen._production_rows(model, self.game.VecDodgeEnv, screen.NEURAL_INPUTS, death_fields,
            eval_seeds, reg_eval_exclusions(self.reg), guard, action_repeat=action_repeat,
            action_mode='sampled_categorical', batch_size=64)
        del model, state; gc.collect(); self.torch.mps.empty_cache()
        return rows

    def empty_cache(self):
        gc.collect(); self.torch.mps.empty_cache()


def reg_eval_exclusions(reg):
    seeds=reg['evaluation_seeds']; low,high=seeds[0],seeds[-1]
    excluded=[]
    for a,z in reg['exclusion_union']:
        if a < low: excluded.append([a,min(z,low-1)])
        if z > high: excluded.append([max(a,high+1),z])
    b.need(not any(a <= s <= z for s in seeds for a,z in excluded),
           'evaluation seeds remain in native exclusion ranges')
    return excluded


def run(envelope_path, envelope_sha256):
    envelope, reg = b.load_envelope(envelope_path, envelope_sha256)
    phase=envelope.get('phase','formal')
    b.verify_bound(envelope, reg, preflight=True)
    b.need(reg['status'] == 'parent_registered', 'parent registration is not accepted')
    source=b.read(envelope['source_acceptance'])
    gate=b.read(envelope['gate_acceptance'])
    b.need(b.sha(envelope['source_acceptance'])==envelope['source_acceptance_sha256']
        and source==b.source_acceptance_document(reg['source_manifest_sha256']),
        'independent source acceptance differs at worker start')
    b.need(b.sha(envelope['gate_acceptance'])==envelope['gate_acceptance_sha256']
        and gate==b.approval_document(envelope['registration_sha256'],reg['source_manifest_sha256'],
            gate.get('pins'),run_id=reg['run_id']),
        'parent gate acceptance differs at worker start')
    b.verify_pins(gate['pins'])
    b.need(gate['pins'].get(str(Path(envelope['source_acceptance']).resolve()))
        ==envelope['source_acceptance_sha256'],'worker gate omits exact source acceptance pin')
    b.validate_runtime_source_acceptance(reg,gate['pins'])
    if phase=='formal': b.validate_resource_acceptance(reg,gate['pins'])
    attempt=b.read(reg['attempt_claim_path']); marker=b.read(reg['launch_marker_path'])
    b.need(attempt.get('schema')==b.ATTEMPT_SCHEMA and attempt.get('run_id')==reg['run_id']
        and attempt.get('registration_sha256')==envelope['registration_sha256']
        and marker.get('run_id')==reg['run_id'] and marker.get('registration_sha256')==envelope['registration_sha256']
        and marker.get('envelope_sha256')==envelope_sha256,
        'exact-once parent attempt/launch marker differs')
    out = Path(reg['output'])
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    result = dict(schema=('one_frame_training_resource_qualification_receipt_v1' if phase=='qualification'
                          else 'one_frame_training_comparison_worker_v1'), status='failed', run_id=reg['run_id'],
        registration_sha256=envelope['registration_sha256'], envelope_sha256=envelope_sha256,
        training_eligible=False, promoted=False, automatic_selection=False,
        source_manifest_sha256=reg['source_manifest_sha256'],
        runtime_manifest_sha256=reg['runtime_manifest_sha256'])
    journals = [Journal(out/name) for name in ('training.jsonl', 'resources.jsonl')]
    training, resources = journals
    guard = None
    try:
        guard = Guard(reg, started, resources)
        guard.check(force=True)
        rt = RealRuntime(reg, registration_sha256=envelope['registration_sha256'])
        guard.torch = rt.torch
        guard.check(force=True)
        if phase == 'qualification':
            qualification=b.read(b.PARENT/'qualification-protocol.json')
            b.need(reg['qualification_protocol_sha256']==b.sha(b.PARENT/'qualification-protocol.json')
                and reg['qualification_protocol_path']==str(b.PARENT/'qualification-protocol.json'),
                'qualification protocol pin differs at worker start')
            qreport=qualification_campaign(reg,qualification,rt,guard,training,envelope['registration_sha256'])
            result.update(qreport)
        else:
            campaign(reg, rt, out, guard, training, envelope['registration_sha256'], result)
            evaluation_started = time.monotonic()
            report = evaluate_models(reg, rt, out, guard, result)
            result['evaluation_seconds'] = time.monotonic()-evaluation_started
        result.update(status='completed', elapsed_seconds=time.monotonic()-started,
            peak_rss_bytes=guard.peak_rss, peak_mps_driver_bytes=guard.peak_mps)
    except BaseException as error:
        result['first_failure'] = repr(error)
        result['traceback'] = __import__('traceback').format_exc()
        raise
    finally:
        for journal in journals:
            journal.close()
        result['elapsed_seconds'] = time.monotonic()-started
        resources=b.worker_resources(out)
        result['resource_summary']={key:resources[key] for key in
            ('samples','peak_rss_bytes','peak_mps_driver_bytes')}
        b.save(out/'worker-result.json', result)
    return 0


class RealArm:
    def __init__(self, runtime, env, model, optimizer, adapter, prepared, parent_state):
        self.rt, self.env, self.model, self.optimizer = runtime, env, model, optimizer
        self.adapter, self.prepared, self.parent_state = adapter, prepared, parent_state

    def update_once(self, *, check_guard):
        collection, metrics, boundary = self.prepared.update_once(check_guard=check_guard)
        return collection, metrics, boundary

    def close(self):
        self.prepared = self.adapter = self.env = self.model = self.optimizer = self.parent_state = None


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--envelope', required=True)
    parser.add_argument('--envelope-sha256', required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.envelope, args.envelope_sha256))
