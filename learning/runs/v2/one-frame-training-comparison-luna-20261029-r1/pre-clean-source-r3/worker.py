"""One-use, paired equal-gameplay-frame training worker with fakeable orchestration."""
from __future__ import annotations
import argparse
import gc
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


def campaign(reg, rt, out, guard, training, registration_sha, result):
    """Run two arms in fixed order, restoring the exact checkpoint independently."""
    out = Path(out); result.update(arms=[], training_eligible=False, promoted=False, automatic_selection=False)
    pool, stream_seeds, components = seeds.build_registered_streams(reg)
    b.need(len(stream_seeds) == 64 and all(len(row) == reg['streams']['capacity_per_slot'] for row in stream_seeds),
           'registered per-slot stream dimensions differ')
    totals = []
    for index, arm in enumerate(reg['arms']):
        guard.enter_arm(arm)
        session = rt.begin_arm(arm, reg, stream_seeds, components, pool)
        arm_result = dict(id=arm['id'], action_repeat=arm['action_repeat'], updates=0,
                          optimizer_steps=0, policy_decisions=0, gameplay_frames=0,
                          startup_frames=0, update_metrics=[])
        try:
            while True:
                guard.check(force=True)
                if arm_result['gameplay_frames'] >= reg['gameplay_frame_target_per_arm']:
                    break
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
                b.need(arm_result['updates'] <= reg['limits']['max_updates_per_arm'], 'per-arm update ceiling exceeded')
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

    def save_final(self, session, out, arm, receipt, registration_sha):
        path = Path(out)/('checkpoint-'+arm['id']+'-final.pt')
        state = dict(schema='one_frame_training_comparison_checkpoint_v1', run_id=b.RUN_ID,
            registration_sha256=registration_sha, arm=arm, global_update=420+session.prepared.adapter.completed_updates,
            model=self.ckpt._cpu_copy(session.model.state_dict()), optimizer=self.ckpt._cpu_copy(session.optimizer.state_dict()),
            model_fingerprint=self.fingerprint(session.model.state_dict()),
            adam_fingerprint=self.fingerprint(session.optimizer.state_dict()),
            actual_gameplay_frames=receipt['gameplay_frames'], training_eligible=False,
            promoted=False, automatic_selection=False)
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
        return dict(path=str(path), sha256=b.sha(path), model_fingerprint=state['model_fingerprint'],
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
    b.verify_bound(envelope, reg, preflight=True)
    b.need(reg['status'] == 'parent_registered', 'parent registration is not accepted')
    source=b.read(envelope['source_acceptance'])
    gate=b.read(envelope['gate_acceptance'])
    b.need(b.sha(envelope['source_acceptance'])==envelope['source_acceptance_sha256']
        and source==b.source_acceptance_document(reg['source_manifest_sha256']),
        'independent source acceptance differs at worker start')
    b.need(b.sha(envelope['gate_acceptance'])==envelope['gate_acceptance_sha256']
        and gate==b.approval_document(envelope['registration_sha256'],reg['source_manifest_sha256'],gate.get('pins')),
        'parent gate acceptance differs at worker start')
    b.verify_pins(gate['pins'])
    attempt=b.read(reg['attempt_claim_path']); marker=b.read(reg['launch_marker_path'])
    b.need(attempt.get('schema')==b.ATTEMPT_SCHEMA and attempt.get('run_id')==reg['run_id']
        and attempt.get('registration_sha256')==envelope['registration_sha256']
        and marker.get('run_id')==reg['run_id'] and marker.get('registration_sha256')==envelope['registration_sha256']
        and marker.get('envelope_sha256')==envelope_sha256,
        'exact-once parent attempt/launch marker differs')
    out = Path(reg['output'])
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    result = dict(schema='one_frame_training_comparison_worker_v1', status='failed', run_id=reg['run_id'],
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
        result['resource_summary'] = b.worker_resources(out)
        b.save(out/'worker-result.json', result)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--envelope', required=True)
    parser.add_argument('--envelope-sha256', required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.envelope, args.envelope_sha256))


class RealArm:
    def __init__(self, runtime, env, model, optimizer, adapter, prepared, parent_state):
        self.rt, self.env, self.model, self.optimizer = runtime, env, model, optimizer
        self.adapter, self.prepared, self.parent_state = adapter, prepared, parent_state

    def update_once(self, *, check_guard):
        collection, metrics, boundary = self.prepared.update_once(check_guard=check_guard)
        return collection, metrics, boundary

    def close(self):
        self.prepared = self.adapter = self.env = self.model = self.optimizer = self.parent_state = None
