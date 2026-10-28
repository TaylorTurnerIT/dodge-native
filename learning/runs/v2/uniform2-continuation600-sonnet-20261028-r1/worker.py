"""One exactly-once campaign: restore the selected learner, train 10 x 60 updates, evaluate 11 saved models on D6.

`campaign()` is runtime-agnostic (fake-testable on CPU). `RealRuntime` is the only code that imports numpy, torch
and the native runtime; it adapts the accepted seed-priority training adapter (r3 runtime_adapter) and the
accepted evaluator `_production_rows`. Training and evaluation are separate accounting roles.
"""
from __future__ import annotations
import argparse
import copy
import gc
import json
import os
from pathlib import Path
import resource
import sys
import time

import binding as b
import metrics
import seeds


class Journal:
    """Append-only JSONL; flushed per row, fsynced every 256 rows and at boundaries."""
    def __init__(self, path):
        self.stream = Path(path).open('x'); self.pending = 0

    def emit(self, value):
        self.stream.write(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n')
        self.stream.flush(); self.pending += 1
        if self.pending >= 256:
            self.sync()

    def sync(self):
        self.stream.flush(); os.fsync(self.stream.fileno()); self.pending = 0

    def close(self):
        self.sync(); self.stream.close()


class Guard:
    """Wall, role budgets, memory, cancel marker and exact lease. Training and evaluation counted separately."""
    def __init__(self, reg, started, resources, torch=None, clock=time.monotonic):
        self.reg, self.started, self.resources, self.torch, self.clock = reg, started, resources, torch, clock
        self.limits = reg['limits']
        self.role = 'setup'
        self.base = dict(raw=0, constructors=0, steps=0, resets=0)       # completed training segments
        self.live = None                                                 # callable for the active segment
        self.evaluation = dict(raw=0, constructors=0, steps=0, resets=0)
        self.seconds = dict(training=0.0, evaluation=0.0, setup=0.0)
        self.role_started = clock(); self.last = float('-inf'); self.peak_rss = self.peak_mps = 0
        self.lease_bytes = self.lease = None; self.calls = 0; self.open_episodes = {}

    def switch(self, role):
        now = self.clock(); self.seconds[self.role] += now-self.role_started
        self.role, self.role_started = role, now

    def training_counts(self):
        live = self.live() if self.live else dict(raw=0, constructors=0, steps=0, resets=0)
        return {k: self.base[k]+live[k] for k in self.base}

    def attach(self, live):
        self.live = live

    def detach(self, final):
        self.base = {k: self.base[k]+final[k] for k in self.base}; self.live = None

    def _lease(self):
        raw = Path(self.reg['state_path']).read_bytes()
        if raw != self.lease_bytes:
            self.lease = json.loads(raw).get('active_long_campaign'); self.lease_bytes = raw
        b.need(self.lease == self.reg['expected_lease'], 'exact resource lease changed')

    def check(self, force=False):
        now = self.clock(); self.calls += 1
        b.need(now-self.started < self.limits['work_seconds'], 'registered work deadline')
        train, ev = self.training_counts(), self.evaluation
        for name, counts, limits in (('training', train, self.limits['training']), ('evaluation', ev, self.limits['evaluation'])):
            b.need(counts['raw'] <= limits['raw_frames'] and counts['constructors'] <= limits['constructors']
                   and counts['steps'] <= limits['native_steps'] and counts['resets'] <= limits['resets'],
                   name+' raw-frame/constructor/step/reset ceiling')
        b.need(not os.path.lexists(b.HERE/'cancel'), 'parent cancellation')
        if force or now-self.last >= .25:
            self._lease()
            rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform == 'darwin' else 1024)
            mps = int(self.torch.mps.driver_allocated_memory()) if self.torch is not None else 0
            b.need(rss <= self.limits['rss_bytes'] and mps <= self.limits['mps_bytes'], 'RSS/MPS ceiling')
            self.peak_rss, self.peak_mps = max(self.peak_rss, rss), max(self.peak_mps, mps)
            self.resources.emit(dict(elapsed_seconds=now-self.started, rss_bytes=rss, mps_driver_bytes=mps, role=self.role))
            self.last = now


def learner_checks(fp, reg):
    b.need(fp == reg['parent']['restore_fingerprints'], 'restored model/Adam/RNG differs from the qualified fingerprints')


def validate_eval_state(state, reg, registration_sha, g, digest, recorded=None):
    """Checkpoint about to be evaluated: parent terminal60 for g=0, a continuation boundary otherwise."""
    if g == 0:
        p = reg['parent']
        b.need(state['schema'] == p['schema'] and state['identity'] == p['expected_identity']
               and state['identity_sha256'] == p['identity_sha256'] and digest == p['checkpoint_sha256']
               and (state['global_update'], state['phase_update'], state['cumulative_update']) == (60, b.PHASE_BASE, b.CUMULATIVE_BASE),
               'starting checkpoint differs from the qualified parent')
        return
    identity = b.learner_identity(reg, registration_sha)
    b.need(state['schema'] == b.CHECKPOINT_SCHEMA and state['identity'] == identity
           and state['identity_sha256'] == b.identity_hash(identity) and state['global_update'] == g
           and state['phase_update'] == b.PHASE_BASE+g and state['cumulative_update'] == b.CUMULATIVE_BASE+g
           and state['parent_checkpoint_sha256'] == reg['parent']['checkpoint_sha256']
           and state['promoted'] is False and state['automatic_selection'] is False and state['training_eligible'] is False
           and (recorded is None or state['model_fingerprint'] == recorded), 'continuation checkpoint identity differs')


def campaign(reg, rt, out, guard, journals, registration_sha, result, *, monitor=None, print_progress=print):
    """Ordered campaign. Raises on the first fault; there is no retry and no skip."""
    out = Path(out); training, evaluation = journals
    counters = dict(updates=0, optimizer_steps=0, environment_decisions=0, raw_frames=0)
    result.update(counters=counters, segments=[], checkpoints=[], evaluations=[])
    selection = metrics.Selection()
    parent = rt.load_parent()
    fp = rt.restore_learner(parent)
    learner_checks(fp, reg)
    result['restored_fingerprints'] = fp
    initial = list(reg['parent']['initial_episode_indices'])
    b.need(parent['next_episode_indices'] == initial, 'parent next episode indices differ from the qualified receipt')
    abandoned = copy.deepcopy(parent['abandoned_current_episodes'])
    b.need(len(abandoned) == b.SLOTS, 'explicit abandoned-episode list required')

    def evaluate(g, path, digest, recorded=None):
        guard.switch('evaluation'); guard.check(force=True)
        b.save(out/f'evaluation-{g:03d}.claim', dict(global_update=g, checkpoint_sha256=digest, registration_sha256=registration_sha))
        snap = rt.learner_snapshot()
        started = guard.clock(); raw_before = guard.evaluation['raw']
        try:
            rows, scratch = rt.evaluate(path, digest, g, lambda e: eval_event(guard, evaluation, g, e), guard.check,
                                        lambda state: validate_eval_state(state, reg, registration_sha, g, digest, recorded))
        finally:
            restored = rt.learner_restore(snap)   # raises unless RNG/flags/grad mode/weights/Adam are exactly equal
        summary = metrics.summarize(rows)
        receipt = dict(schema='uniform2_continuation600_evaluation_v1', global_update=g, checkpoint_path=str(path),
            checkpoint_sha256=digest, registration_sha256=registration_sha, cohort='D6', action_mode='sampled_categorical',
            normal_start=True, cutoff_enabled=False, summary=summary, rows=rows,
            raw_frames_including_startup=guard.evaluation['raw']-raw_before, elapsed_seconds=guard.clock()-started,
            scratch=scratch, learner_state_restored=restored, automatic_selection=False, promoted=False)
        b.save(out/f'evaluation-{g:03d}.json', receipt)
        best = selection.add(g, summary, digest)
        evaluation.emit(dict(kind='evaluation_receipt', global_update=g, Q1=summary['performance']['Q1'],
                             Mean=summary['performance']['Mean'], best_global_update=best['global_update']))
        evaluation.sync()
        result['evaluations'].append(dict(global_update=g, checkpoint_sha256=digest, Q1=summary['performance']['Q1'],
            Mean=summary['performance']['Mean'], receipt_sha256=b.sha(out/f'evaluation-{g:03d}.json')))
        print_progress(json.dumps(dict(status='evaluation_complete', global_update=g, Q1=summary['performance']['Q1'],
                                       selected_global_update=best['global_update'])), flush=True)
        guard.switch('training'); guard.check(force=True)

    evaluate(0, reg['parent']['checkpoint_path'], reg['parent']['checkpoint_sha256'])
    guard.switch('training')
    starts = initial
    for index in range(b.SEGMENTS):
        base = index*b.SEGMENT_UPDATES
        pool_all, identity = rt.pool_all, b.stream_identity(reg['parent']['expected_identity']['seed_vector'])
        streams, components = seeds.segment_streams(pool_all, identity, starts, frozen=rt.frozen_seed_priority)
        seed_digests, component_digests = seeds.digests(streams, components)
        if index == 0:
            b.need(seed_digests == reg['streams']['first_segment_slot_stream_sha256']
                   and component_digests == reg['streams']['first_segment_slot_component_sha256'],
                   'first-segment seed streams differ from the registration')
        seg = rt.begin_segment(starts, streams, components, lambda e, base=base: training_event(training, base, e))
        del streams, components
        guard.attach(seg.live_counts)
        training.emit(dict(kind='segment_initial', segment=index, global_update_base=base, next_episode_indices=starts,
                           slot_stream_sha256=seed_digests, slot_component_sha256=component_digests,
                           abandoned_from_previous=abandoned, initial_startup_frames=b.STARTUP*b.SLOTS))
        try:
            for local in range(1, b.SEGMENT_UPDATES+1):
                g = base+local
                if monitor is not None:
                    monitor.begin_update(g)
                guard.check()
                progress = {}
                info = seg.run_update(local, guard.check, lambda completed, resets, g=g: before_ppo(training, monitor, g, completed, resets), progress)
                counters['updates'] = g
                counters['optimizer_steps'] += info['optimizer_steps']
                counters['environment_decisions'] += info['decisions']
                counters['raw_frames'] += info['raw_frames']
                training.emit(dict(kind='update_metrics', global_update=g, phase_update=b.PHASE_BASE+g,
                    cumulative_update=b.CUMULATIVE_BASE+g, effective_learning_rate=3e-5, metrics=info['metrics'],
                    counters=dict(counters), progress=progress, elapsed_seconds=guard.clock()-guard.started))
                guard.check()
                if monitor is not None:
                    print_progress(json.dumps(monitor.finish_update(g), sort_keys=True, allow_nan=False), flush=True)
            b.need(counters['updates'] == base+b.SEGMENT_UPDATES
                   and counters['environment_decisions'] == b.DECISIONS_PER_UPDATE*counters['updates'], 'update budget differs')
            ckpt = rt.save_checkpoint(out, seg, index, base+b.SEGMENT_UPDATES, counters, registration_sha)
            end = seg.end_state()
        except BaseException:
            result['active_segment'] = index
            raise
        finally:
            final = seg.live_counts()
        guard.detach(final)
        training.emit(dict(kind='segment_end', segment=index, global_update=base+b.SEGMENT_UPDATES, counts=final,
                           next_episode_indices=end['next_episode_indices'], abandoned=end['abandoned_current_episodes']))
        training.sync()
        b.save(Path(ckpt['path']).with_name(Path(ckpt['path']).name+'.json'), ckpt)
        result['segments'].append(dict(segment=index, global_update=base+b.SEGMENT_UPDATES, counts=final,
            abandoned_episodes=len(end['abandoned_current_episodes']), snapshot=end['snapshot']))
        result['checkpoints'].append(ckpt)
        starts, abandoned = end['next_episode_indices'], end['abandoned_current_episodes']
        seg.close(); del seg; gc.collect()
        evaluate(base+b.SEGMENT_UPDATES, ckpt['path'], ckpt['sha256'], ckpt['model_fingerprint'])
    report = selection.report()
    b.need([e['global_update'] for e in report['candidates']] == b.EVAL_UPDATES, 'all eleven evaluations required')
    b.save(out/'selection.json', dict(schema='uniform2_continuation600_selection_v1', registration_sha256=registration_sha,
        cohort='D6', official_parent324_promotion=False, automatic_selection=False, promoted=False, **report))
    result.update(selection_sha256=b.sha(out/'selection.json'), selected=report['selected'])
    guard.switch('setup')


def eval_event(guard, journal, g, event):
    """Compact evaluation journal; per-episode step totals are written when the episode completes."""
    kind = event['kind']; state = guard.evaluation
    if kind == 'evaluation_constructor':
        state['raw'] += event['info']['startup_frames']; state['constructors'] += 1
        guard.open_episodes[(g, event['episode_index'])] = dict(steps=0, raw=0, seed=event['info']['seed']['actual_seed'])
    elif kind == 'evaluation_step':
        state['raw'] += event['elapsed_raw_frames']; state['steps'] += 1
        item = guard.open_episodes[(g, event['episode_index'])]; item['steps'] += 1; item['raw'] += event['elapsed_raw_frames']
        b.need(item['raw'] <= 18000, 'per-episode raw-frame cap')
    elif kind == 'evaluation_completed':
        row = event['row']; item = guard.open_episodes.pop((g, row['episode_index']))
        b.need(item['raw'] == row['gameplay_frames'] and item['seed'] == row['seed'], 'per-episode cost conservation differs')
        journal.emit(dict(kind='evaluation_episode', global_update=g, episode_index=row['episode_index'], seed=row['seed'],
                          startup_frames=row['startup_frames'], steps=item['steps'], raw=item['raw'],
                          alive_frames=row['alive_frames'], terminated=row['terminated']))
    else:
        raise ValueError('unexpected collector event')
    b.need(all(state[k] <= guard.limits['evaluation'][name] for k, name in
               (('raw', 'raw_frames'), ('constructors', 'constructors'), ('steps', 'native_steps'))),
           'returned evaluation raw-frame/constructor/step ceiling')


def training_event(journal, base, event):
    """Compact returned-native-work journal for the training role."""
    kind = event['kind']; g = base+event['update']
    if kind == 'returned_step_cost':
        journal.emit(dict(kind=kind, update=g, decision=event['decision'], raw=sum(event['elapsed_raw_frames'])))
    elif kind == 'seeded_step' and event['completed']:
        journal.emit(dict(kind='episodes_completed', update=g, decision=event['decision'], rows=[
            dict(slot=r['slot'], episode=r['seed']['episode'], seed=r['seed']['actual_seed'], alive_frames=r['alive_frames'],
                 gameplay_frames=r['gameplay_frames'], terminated=r['terminated'], truncated=r['truncated'],
                 component=r['sampling_component'], stratum=r['stratum']) for r in event['completed']]))
    elif kind == 'returned_reset':
        journal.emit(dict(kind=kind, update=g, decision=event['decision'], slots=event['indices'],
                          startup_frames=sum(int(i['startup_frames']) for i in event['info'])))
    elif kind == 'seeded_reset':
        journal.emit(dict(kind='assignments', update=g, decision=event['decision'],
            rows=[dict(slot=r['slot'], episode=r['seed']['episode'], seed=r['seed']['actual_seed']) for r in event['assignments']]))


def before_ppo(journal, monitor, g, completed, resets):
    if monitor is not None:
        monitor.enter('collection_journal')
    journal.emit(dict(kind='collection_complete_before_PPO', update=g, completed_episodes=len(completed), resets=len(resets)))
    journal.sync()
    if monitor is not None:
        monitor.enter('PPO')


class RealRuntime:
    """Imports numpy/torch/native only here, after the attempt is spent. Not exercised by the CPU fake tests."""
    def __init__(self, reg, modules, guard):
        import importlib
        self.reg, self.m, self.guard = reg, modules, guard
        c, ra, db = modules['contracts'], modules['runtime_adapter'], modules['driver_binding']
        b.need(not any(n == 'dodge_rl' or n.startswith('dodge_rl.') for n in sys.modules), 'runtime must start unloaded')
        sys.path.insert(0, reg['runtime_root'])
        self.np, self.torch = importlib.import_module('numpy'), importlib.import_module('torch')
        self.game = importlib.import_module('dodge_rl')
        self.ckpt = importlib.import_module('dodge_rl.checkpoints')
        self.ppo_module = importlib.import_module('dodge_rl.ppo')
        self.curriculum = importlib.import_module('dodge_rl.curriculum')
        self.seeded = importlib.import_module('dodge_rl.seeded_training')
        self.frozen_seed_priority = importlib.import_module('dodge_rl.seed_priority')
        self.teacher = importlib.import_module('dodge_rl.models.teacher')
        self.identity_module = importlib.import_module('dodge_rl.identity')
        b.need(Path(self.game.__file__).resolve() == Path(reg['runtime_root'])/'dodge_rl/__init__.py', 'native package origin differs')
        b.need(dict(python=sys.version.split()[0], torch=str(self.torch.__version__), numpy=str(self.np.__version__))
               == reg['runtime_versions'], 'loaded runtime versions differ')
        b.need(self.torch.backends.mps.is_available(), 'MPS unavailable')
        am, ac = ra.authenticate_module, ra.authenticate_class
        am(self.ckpt, 'dodge_rl/checkpoints.py', db.CHECKPOINT_FUNCTIONS+('load_checkpoint', 'save_checkpoint', 'episode_resume_state', '_cpu_copy'))
        am(self.ppo_module, 'dodge_rl/ppo.py', ('collect_rollout', 'ppo_update'))
        ac(self.teacher, 'OmniscientEntityTeacher'); ac(self.teacher, 'CustomTransformerLayer')
        ac(self.seeded, 'SeededTrainingAdapter')
        am(self.frozen_seed_priority, 'dodge_rl/seed_priority.py', ('canonical', 'sha256_bytes', 'validate_pool', '_draw_key',
           'sequence_entries', 'sequence', 'stream_digest', 'inclusion_probabilities'))
        ac(self.curriculum, 'CurriculumAdapter'); ac(self.curriculum, 'PreparedUpdates')
        runtime = Path(reg['runtime_root']); files = b.read(runtime.parent/'runtime-manifest.json')['files']
        for name, module in tuple(sys.modules.items()):
            if name == 'dodge_rl' or name.startswith('dodge_rl.'):
                path = Path(module.__file__).resolve()
                b.need(path.is_relative_to(runtime) and b.sha(path) == files.get(str(path.relative_to(runtime))),
                       'loaded module/native pin differs: '+name)
        self.finite_tree = ra.runner_namespace()['finite_tree']
        self.fingerprint = modules['fingerprints'].fingerprint
        self.torch.set_num_threads(4)
        pool_doc = b.read(b.POOL); pool = self.frozen_seed_priority.validate_pool(pool_doc)
        b.need(pool['pool_sha256'] == reg['streams']['training_pool_sha256'], 'pool semantic digest differs')
        self.pool_all, self.pool = list(pool['all']), pool
        self.strata = {row['seed']: row['stratum'] for row in pool_doc['seeds']}
        self.ppo = self.ppo_module.PPOConfig(**b.PPO)
        self.analysis, self.death_fields = modules['expanded_eval'], modules['death_telemetry'].death_fields

    # learner -----------------------------------------------------------
    def load_parent(self):
        p = self.reg['parent']
        state = self.ckpt.load_checkpoint(Path(p['checkpoint_path']), expected_sha256=p['checkpoint_sha256'],
                                          expected_identity=p['expected_identity'])
        self.ckpt.require_complete_update(state)
        validate_eval_state(state, self.reg, None, 0, p['checkpoint_sha256'])
        return state

    def restore_learner(self, state):
        fp = dict(model=self.fingerprint(state['model']), Adam=self.fingerprint(state['optimizer']), RNG=self.fingerprint(state['rng']))
        self.model = self.teacher.OmniscientEntityTeacher().to(device='mps', dtype=self.torch.float32)
        self.optimizer = self.torch.optim.Adam(self.model.parameters(), lr=3e-5, eps=b.PPO['adam_eps'])
        self.ckpt.restore_learner(state, self.model, self.optimizer, 'mps')
        actual = self.fingerprints()
        b.need(actual == fp, 'restored model/Adam/RNG differs from the checkpoint')
        b.need(all(g['lr'] == 3e-5 for g in self.optimizer.param_groups), 'restored LR changed')
        return actual

    def fingerprints(self):
        return dict(model=self.fingerprint(self.model.state_dict()), Adam=self.fingerprint(self.optimizer.state_dict()),
                    RNG=self.fingerprint(self.ckpt.capture_rng('mps')))

    def learner_snapshot(self):
        return dict(rng=self.ckpt.capture_rng('mps'), fingerprints=self.fingerprints(), grad=self.torch.is_grad_enabled(),
                    flags={n: m.training for n, m in self.model.named_modules()})

    def learner_restore(self, snap):
        self.ckpt.restore_rng(snap['rng'], 'mps')
        for name, module in self.model.named_modules():
            module.training = snap['flags'][name]
        b.need(self.torch.is_grad_enabled() == snap['grad'], 'global gradient mode changed')
        now = self.fingerprints()
        b.need(now == snap['fingerprints'], 'learner model/Adam/RNG differ after evaluation')
        b.need({n: m.training for n, m in self.model.named_modules()} == snap['flags'], 'learner train/eval flags differ')
        return dict(fingerprints=now, grad_enabled=snap['grad'], module_training_flags_equal=True)

    # training segment --------------------------------------------------
    def begin_segment(self, starts, streams, components, sink):
        reg = self.reg
        env = self.game.VecDodgeEnv(batch_size=64, action_repeat=4, difficulty=2, patterns_enabled=True, powerups_enabled=True,
            raw_frame_cap=18000, num_threads=4, chunk_size=8, render_pixels=False, auxiliary_targets=False,
            seeds_by_slot=streams, initial_episode_indices=starts, excluded_seed_ranges=[tuple(r) for r in reg['exclusion_union']])
        meta = env.batch_info()
        b.need(meta['seed_mode'] == dict(mode='evaluation', seeds_by_slot=streams) and meta['initial_episode_indices'] == starts,
               'native explicit seed-list metadata differs')
        boundary = self.seeded.SeededTrainingAdapter(env, seeds_by_slot=streams, components_by_slot=components,
            strata_by_seed=self.strata, training_pool_values=self.pool['all'], exclusions=reg['exclusion_union'])
        boundary.event_sink = sink
        prepared = self.curriculum.PreparedUpdates(self.model, self.optimizer, boundary, config=self.ppo, device='mps')
        return Segment(self, env, boundary, prepared)

    def save_checkpoint(self, out, seg, index, g, counters, registration_sha):
        b.need(seg.prepared.state == 'ready' and seg.boundary.completed_updates == b.SEGMENT_UPDATES, 'checkpoint requires a completed boundary')
        before = self.fingerprints(); identity = b.learner_identity(self.reg, registration_sha)
        next_indices, abandoned = self.ckpt.episode_resume_state(seg.env, 64)
        snap = seg.compact_snapshot()
        model_fp = self.fingerprint(self.model.state_dict())
        state = dict(version='teacher_checkpoint_v1', schema=b.CHECKPOINT_SCHEMA, resume_mode='fresh_env',
            tag='continuation_boundary', training_eligible=False, promoted=False, automatic_selection=False,
            identity=identity, identity_sha256=b.identity_hash(identity), model_fingerprint=model_fp,
            parent_lineage=dict(checkpoint_sha256=self.reg['parent']['checkpoint_sha256'],
                restore_fingerprints=self.reg['parent']['restore_fingerprints']),
            successor_runtime_manifest_sha256=self.reg['runtime_manifest_sha256'],
            model=self.ckpt._cpu_copy(self.model.state_dict()), optimizer=self.ckpt._cpu_copy(self.optimizer.state_dict()),
            rng=self.ckpt.capture_rng('mps'), next_episode_indices=next_indices, abandoned_current_episodes=abandoned,
            counters=copy.deepcopy(counters), phase_update=b.PHASE_BASE+g, cumulative_update=b.CUMULATIVE_BASE+g,
            global_update=g, segment=index, update_progress=copy.deepcopy(seg.prepared.progress), curriculum_state=snap,
            parent_checkpoint_sha256=self.reg['parent']['checkpoint_sha256'])
        b.need(all(x['lr'] == 3e-5 for x in state['optimizer']['param_groups']), 'saved LR is not constant')
        path = Path(out)/f'checkpoint-global-{g:03d}.pt'
        digest = self.ckpt.save_checkpoint(path, state)
        os.chmod(path, 0o444)
        b.need(self.fingerprints() == before, 'checkpoint save changed live learner state')
        seg.saved = dict(next_episode_indices=next_indices, abandoned_current_episodes=abandoned, snapshot=snap)
        return dict(path=str(path), sha256=digest, global_update=g, segment=index, phase_update=b.PHASE_BASE+g,
            cumulative_update=b.CUMULATIVE_BASE+g, identity_sha256=state['identity_sha256'], model_fingerprint=model_fp,
            optimizer_fingerprint=before['Adam'], rng_fingerprint=before['RNG'], next_episode_indices=next_indices,
            abandoned_current_episodes=len(abandoned), training_eligible=False, promoted=False, automatic_selection=False)

    # evaluation --------------------------------------------------------
    def evaluate(self, path, digest, g, sink, guard_check, validate):
        torch, ckpt = self.torch, self.ckpt
        state = ckpt.load_checkpoint(Path(path), expected_sha256=digest)
        ckpt.require_complete_update(state); validate(state)
        model = self.teacher.OmniscientEntityTeacher().to('mps')
        model.load_state_dict(state['model'], strict=True); model.eval(); model._expanded_eval_device = 'mps'
        before = self.fingerprint(model.state_dict())
        b.need(before == self.fingerprint(state['model']) == (state.get('model_fingerprint') or before), 'loaded evaluation weights differ')
        del state
        seed = self.reg['evaluation']['rng_seed']
        import random
        random.seed(seed); self.np.random.seed(seed % 2**32); torch.manual_seed(seed); torch.mps.manual_seed(seed)
        scratch_before = self.fingerprint(ckpt.capture_rng('mps'))
        rows = self.analysis._production_rows(model, self.game.VecDodgeEnv, b.NEURAL_INPUTS, self.death_fields, b.SEEDS,
            b.eval_excluded(self.reg['exclusion_union']), guard_check, batch_size=64, event_sink=sink)
        rows = self.analysis.validate_full_rows(rows, b.SEEDS)
        b.need(self.fingerprint(model.state_dict()) == before, 'evaluation changed weights')
        b.need(b.sha(path) == digest, 'checkpoint bytes changed')
        scratch = dict(rng_after_seed_sha256=scratch_before, rng_after_evaluation_sha256=self.fingerprint(ckpt.capture_rng('mps')),
                       model_fingerprint=before)
        del model; gc.collect(); torch.mps.empty_cache()
        return rows, scratch


class Segment:
    def __init__(self, rt, env, boundary, prepared):
        self.rt, self.env, self.boundary, self.prepared = rt, env, boundary, prepared
        self.saved = None

    def live_counts(self):
        bd = self.boundary
        return dict(raw=bd.initial_startup_frames+bd.observed_native_frames+bd.returned_reset_startup_frames,
                    constructors=1, steps=bd.observed_native_steps, resets=bd.reset_count)

    def run_update(self, local, guard_check, journal, progress):
        rt = self.rt
        b.need(all(g['lr'] == 3e-5 for g in rt.optimizer.param_groups), 'constant LR changed')
        collection, value, _boundary = self.prepared.update_once(check_guard=guard_check,
            journal_collection_events=journal, validate_metrics=rt.finite_tree)
        progress.update(self.prepared.progress)
        b.need(progress.get('complete') is True and progress.get('in_update') is False, 'incomplete update')
        return dict(metrics=value, optimizer_steps=value['optimizer_steps'], decisions=int(collection.batch.actions.numel()),
                    raw_frames=int(collection.batch.elapsed_raw_frames.sum().item()))

    def compact_snapshot(self):
        snap = self.boundary.snapshot(); snap.pop('returned_resets', None)
        return snap

    def end_state(self):
        return dict(next_episode_indices=self.saved['next_episode_indices'],
                    abandoned_current_episodes=self.saved['abandoned_current_episodes'], snapshot=self.saved['snapshot'])

    def close(self):
        self.prepared = self.boundary = self.env = None   # native ownership ends; the supervisor verifies cleanup


def finalize_result(guard, result):
    guard.switch('setup')
    result.update(roles=dict(training=dict(seconds=guard.seconds['training'], **guard.training_counts()),
        evaluation=dict(seconds=guard.seconds['evaluation'], **guard.evaluation)),
        setup_seconds=guard.seconds['setup'], peak_rss_bytes=guard.peak_rss, peak_mps_driver_bytes=guard.peak_mps)


def run(envelope_path, envelope_sha):
    e, reg = b.load_envelope(envelope_path, envelope_sha); b.verify_bound(e, reg, preflight=True)
    b.validate_static(reg, streams=True)
    # Spend the campaign before imports, checkpoint deserialization, seeds or games.
    b.save(reg['attempt_claim_path'], dict(schema=b.ATTEMPT_SCHEMA, run_id=reg['run_id'],
                                           registration_sha256=e['registration_sha256'], pid=os.getpid()))
    out = Path(reg['output']); out.mkdir(exist_ok=False)
    modules = b.frozen()
    result = dict(schema='uniform2_continuation600_worker_v1', status='failed', run_id=reg['run_id'],
        registration_sha256=e['registration_sha256'], automatic_selection=False, promoted=False, training_eligible=False,
        updates=0, no_retry=True)
    resources, training, evaluation = Journal(out/'resources.jsonl'), Journal(out/'training-events.jsonl'), Journal(out/'evaluation-events.jsonl')
    guard = rt = None; started = e['started']
    try:
        from progress_monitor import ProgressMonitor
        guard = Guard(reg, started, resources); guard.check(force=True)
        rt = RealRuntime(reg, modules, guard); guard.torch = rt.torch
        monitor = ProgressMonitor(started, reg['limits']['work_seconds'], b.UPDATES)
        campaign(reg, rt, out, guard, (training, evaluation), e['registration_sha256'], result, monitor=monitor)
        guard.check(force=True)
        result.update(status='completed', updates=result['counters']['updates'])
    except BaseException as error:
        result['first_failure'] = repr(error)
        raise
    finally:
        try:
            if guard is not None:
                finalize_result(guard, result)
        finally:
            for journal in (training, evaluation, resources):
                journal.close()
            result['elapsed_seconds'] = time.monotonic()-started
            b.save(out/'worker-result.json', result)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--envelope', required=True)
    parser.add_argument('--envelope-sha256', required=True); args = parser.parse_args()
    raise SystemExit(run(args.envelope, args.envelope_sha256))
