"""CPU stdlib fakes and source checks. No torch/MPS/native import, no checkpoint load, no launch.

Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=<pkg>/tests-pycache python/.venv/bin/python -B tests.py
Not exercised (parent qualification needed): native VecDodgeEnv with the long seed lists, real torch/MPS, checkpoint
deserialization, authenticate_module/class against the loaded runtime, the real observer/launch under caffeinate.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

import binding as b
import metrics
import power_guard
import seeds
import terminal
import worker

POOL = sorted(range(1000, 1000+512*7, 7))


def hexdigest(*parts):
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def fake_rows(g, quality):
    rows = []
    for i, seed in enumerate(b.SEEDS):
        alive = 100+((i*37)%900)+quality*(1+i%5)
        rows.append(dict(episode_index=i, seed=seed, score_raw_fixed=0, score=0.0, score_delta_sum_raw_fixed=0, alive_frames=alive,
            gameplay_frames=alive+1, startup_frames=13, terminated=True, truncated=False, death_cause='normal_enemy',
            fatal_gameplay_frame=alive+1, death_observed_lethal_contacts={k: int(k == 'normal_enemy') for k in metrics.DEATH_CAUSES[:-1]},
            objective_return=alive/100-5))
    return rows


class FakeSegment:
    def __init__(self, rt, starts):
        self.rt, self.starts, self.updates, self.closed = rt, starts, 0, False
        self.raw = b.STARTUP*b.SLOTS; self.steps = 0; self.resets = 0

    def live_counts(self):
        return dict(raw=self.raw, constructors=1, steps=self.steps, resets=self.resets)

    def run_update(self, local, guard_check, journal, progress):
        self.updates += 1
        for _ in range(b.ROLLOUT):
            self.steps += 1; self.raw += 4*b.SLOTS; guard_check()
            self.rt.sink(dict(kind='returned_step_cost', update=local, decision=0, elapsed_raw_frames=[4]*b.SLOTS))
        self.resets += 2; self.raw += 26
        self.rt.sink(dict(kind='returned_reset', update=local, decision=1, indices=[0, 1], info=[dict(startup_frames=13)]*2))
        journal([1], [1, 2]); self.rt.rng += local; self.rt.train_calls += 1
        progress.update(complete=True, in_update=False)
        return dict(metrics=dict(loss=1.0, optimizer_steps=128), optimizer_steps=128, decisions=b.DECISIONS_PER_UPDATE,
                    raw_frames=b.DECISIONS_PER_UPDATE*4)

    def end_state(self):
        return self.saved

    def close(self):
        self.closed = True


class FakeRuntime:
    """Records every call. `evaluate` perturbs the global RNG, like reseeding does; restore must undo it."""
    def __init__(self, reg, qualities, *, fail_eval=None, skip_restore=False):
        self.reg, self.qualities, self.fail_eval, self.skip_restore = reg, qualities, fail_eval, skip_restore
        self.rng, self.train_calls, self.calls, self.segments = 5, 0, [], []
        self.pool_all, self.frozen_seed_priority = POOL, None
        self.flags = {'model': True}; self.snapshots = 0; self.restores = 0; self.sink = lambda event: None

    def load_parent(self):
        self.calls.append('load_parent')
        p = self.reg['parent']
        return dict(next_episode_indices=list(p['initial_episode_indices']), abandoned_current_episodes=[dict(slot=i) for i in range(64)])

    def restore_learner(self, state):
        self.calls.append('restore'); return self.reg['parent']['restore_fingerprints']

    def fingerprints(self):
        return dict(model=hexdigest('m', self.train_calls), Adam=hexdigest('a', self.train_calls), RNG=hexdigest('r', self.rng))

    def learner_snapshot(self):
        self.snapshots += 1; self.calls.append('snapshot')
        return dict(rng=self.rng, fp=self.fingerprints(), flags=dict(self.flags))

    def learner_restore(self, snap):
        self.restores += 1; self.calls.append('learner_restore')
        if not self.skip_restore:
            self.rng = snap['rng']; self.flags = dict(snap['flags'])
        b.need(self.fingerprints() == snap['fp'], 'learner model/Adam/RNG differ after evaluation')
        return dict(fingerprints=self.fingerprints(), grad_enabled=True, module_training_flags_equal=True)

    def begin_segment(self, starts, streams, components, sink):
        self.calls.append('begin_segment'); self.sink = sink
        b.need(all(len(s) == st+seeds.EPISODES_PER_SEGMENT for s, st in zip(streams, starts)), 'stream length differs')
        seg = FakeSegment(self, starts); self.segments.append(seg); return seg

    def save_checkpoint(self, out, seg, index, g, counters, registration_sha):
        self.calls.append('checkpoint')
        path = Path(out)/f'checkpoint-global-{g:03d}.pt'
        path.write_bytes(('ckpt%d' % g).encode()); os.chmod(path, 0o444)
        nxt = [s+30+index for s in seg.starts]
        seg.saved = dict(next_episode_indices=nxt, abandoned_current_episodes=[dict(slot=i) for i in range(64)], snapshot=dict(completed_updates=60))
        fp = self.fingerprints(); self.last_model_fp = fp['model']
        receipt = dict(path=str(path), sha256=b.sha(path), global_update=g, segment=index, phase_update=b.PHASE_BASE+g,
            cumulative_update=b.CUMULATIVE_BASE+g, identity_sha256=b.identity_hash(b.learner_identity(self.reg, registration_sha)),
            model_fingerprint=fp['model'], optimizer_fingerprint=fp['Adam'], rng_fingerprint=fp['RNG'], next_episode_indices=nxt,
            abandoned_current_episodes=64, training_eligible=False, promoted=False, automatic_selection=False)
        return receipt

    def evaluate(self, path, digest, g, sink, guard_check, validate):
        self.calls.append('evaluate%d' % g)
        if self.fail_eval == g:
            raise RuntimeError('injected evaluation fault')
        self.rng += 1000; self.flags = {'model': False}   # reseed + eval() mutate the learner-visible globals
        rows = fake_rows(g, self.qualities[g//b.SEGMENT_UPDATES])
        for row in rows:
            guard_check()
            sink(dict(kind='evaluation_constructor', episode_index=row['episode_index'], info=dict(startup_frames=13, seed=dict(actual_seed=row['seed']))))
            half = row['gameplay_frames']//2
            for frames in (half, row['gameplay_frames']-half):
                sink(dict(kind='evaluation_step', episode_index=row['episode_index'], elapsed_raw_frames=frames))
            sink(dict(kind='evaluation_completed', row=row))
        return rows, dict(rng_after_seed_sha256='s', rng_after_evaluation_sha256='e', model_fingerprint=self.last_model_fp if g != b.CAMPAIGN_BASE else self.reg['parent']['restore_fingerprints']['model'])


def fake_reg(tmp):
    lease = dict(kind=b.LEASE_KIND, run_id=b.RUN_ID, study_id=b.STUDY_ID, owner_token='a'*32, RSS_bytes=b.CAP, MPS_driver_bytes=b.CAP)
    state = Path(tmp)/'state.json'; state.write_text(json.dumps(dict(active_long_campaign=lease)))
    vector = dict(seeds=dict(env_master_seed=11644207240444663193))
    starts = list(range(290, 354))
    streams, components = seeds.segment_streams(POOL, b.stream_identity(vector), starts)
    sd, cd = seeds.digests(streams, components)
    return dict(run_id=b.RUN_ID, study_id=b.STUDY_ID, backend='mps', runtime_manifest_sha256='r'*64, source_manifest_sha256='s'*64,
        runtime_versions=dict(a='1'), recipe=dict(x=1), exclusion_union=[[1, 2]], cohort=dict(name='D6'), schedule=b.SCHEDULE,
        streams=dict(first_segment_slot_stream_sha256=sd, first_segment_slot_component_sha256=cd),
        parent=dict(checkpoint_sha256='p'*64, identity_sha256='i'*64, run_id=b.PRODUCER_RUN, checkpoint_path=str(Path(tmp)/'parent.pt'),
                    initial_episode_indices=starts, expected_identity=dict(seed_vector=vector),
                    restore_fingerprints=dict(model=hexdigest('m', 0), Adam=hexdigest('a', 0), RNG=hexdigest('r', 5)),
                    schema='uniform2_continuation600_checkpoint_v1'),
        limits=dict(work_seconds=b.WORK_SECONDS, total_seconds=b.TOTAL_SECONDS, cleanup_seconds=10, postflight_seconds=120,
                    rss_bytes=b.CAP, mps_bytes=b.CAP, retries=0, training=b.TRAINING_LIMITS, evaluation=b.EVALUATION_LIMITS),
        state_path=str(state), expected_lease=lease, output=str(Path(tmp)/'out'), evaluation=b.EVALUATION)


class Run:
    def __init__(self, tmp, qualities, **kw):
        self.tmp = Path(tmp); self.reg = fake_reg(tmp); self.out = Path(self.reg['output']); self.out.mkdir()
        (self.tmp/'parent.pt').write_bytes(b'parent')
        self.reg['parent']['checkpoint_sha256'] = b.sha(self.tmp/'parent.pt')
        self.rt = FakeRuntime(self.reg, qualities, **kw)
        self.resources = worker.Journal(self.out/'resources.jsonl'); self.training = worker.Journal(self.out/'training-events.jsonl')
        self.evaluation = worker.Journal(self.out/'evaluation-events.jsonl')
        self.guard = worker.Guard(self.reg, 0.0, self.resources, clock=lambda: 1.0)
        self.result = dict(schema='uniform2_recovery240_worker_v1', status='failed', run_id=b.RUN_ID, registration_sha256='g'*64,
            automatic_selection=False, promoted=False, training_eligible=False, updates=0, no_retry=True)

    def close(self):
        for j in (self.training, self.evaluation, self.resources):
            j.close()

    def go(self):
        try:
            worker.campaign(self.reg, self.rt, self.out, self.guard, (self.training, self.evaluation), 'g'*64, self.result,
                            print_progress=lambda *a, **k: None)
            self.result.update(status='completed', updates=self.result['counters']['updates'])
        finally:
            worker.finalize_result(self.guard, self.result)
            for j in (self.training, self.evaluation, self.resources):
                j.close()
            self.result['elapsed_seconds'] = 1.0
        return self.result


class SeedTests(unittest.TestCase):
    def test_extension_matches_frozen_helper_and_extends_it(self):
        frozen = b.frozen()['seed_priority']
        pool = dict(all=tuple(POOL), hard=tuple(POOL[:256]))
        identity = dict(study_id=b.PRODUCER_STUDY, replica=2, master=11644207240444663193)
        for slot in (0, 17, 63):
            ref = frozen.sequence_entries(pool, study_id=b.PRODUCER_STUDY, replica=2, env_master_seed=identity['master'], arm='uniform', slot=slot, count=16384)
            mine = seeds.uniform_stream(POOL, slot=slot, count=16384, **identity)
            self.assertEqual([s for s, _ in ref], mine)
            self.assertEqual(seeds.uniform_stream(POOL, slot=slot, count=20000, **identity)[:16384], mine)
        with self.assertRaises(ValueError):
            frozen.sequence_entries(pool, study_id=b.PRODUCER_STUDY, replica=2, env_master_seed=identity['master'], arm='uniform', slot=0, count=16385)
        self.assertEqual(len(seeds.uniform_stream(POOL, slot=3, count=153601+334, **identity)), 153601+334)

    def test_segment_streams_cover_worst_case_and_cross_check(self):
        frozen = b.frozen()['seed_priority']
        identity = dict(study_id=b.PRODUCER_STUDY, replica=2, master=11644207240444663193)
        starts = list(range(290, 354))
        values, components = seeds.segment_streams(POOL, identity, starts, frozen=frozen)
        self.assertTrue(all(len(v) == s+15361 and set(v) <= set(POOL) for v, s in zip(values, starts)))
        self.assertEqual(set(components[0]), {'uniform'})
        late = [s+15361*9 for s in starts]   # ninth segment worst case: beyond the frozen bound, still derivable
        values, _ = seeds.segment_streams(POOL, identity, late, frozen=None)
        self.assertEqual(len(values[0]), late[0]+15361); self.assertGreater(len(values[0]), seeds.FROZEN_MAX_LENGTH)
        with self.assertRaises(ValueError):
            seeds.segment_streams(POOL, identity, starts[:63])
        with self.assertRaises(ValueError):
            seeds.uniform_stream(POOL[:511], slot=0, count=5, **identity)

    def test_train_streams_exclude_cohort_and_union(self):
        pool = b.read(b.POOL)['seeds']; union = b.cohort_union()
        self.assertEqual(len(union), 9)
        self.assertFalse(any(lo <= r['seed'] <= hi for r in pool for lo, hi in union))
        self.assertTrue(all(b.covers(union, *r) for r in (b.D4, b.D5, b.COHORT_RANGE)))
        excluded = b.eval_excluded(union)
        self.assertFalse(any(lo <= s <= hi for s in b.SEEDS for lo, hi in excluded))
        self.assertTrue(all(any(lo <= h[0] and h[1] <= hi for lo, hi in union) for h in excluded))


class MetricsTests(unittest.TestCase):
    def test_q1_and_selection(self):
        s = metrics.summarize(fake_rows(0, 0))
        ordered = sorted(r['alive_frames'] for r in fake_rows(0, 0))
        self.assertEqual(s['performance']['Q1'], sum(ordered[:256])/256)
        self.assertEqual(s['performance']['Q4'], sum(ordered[768:])/256)
        sel = metrics.Selection()
        mk = lambda q, m: dict(performance=dict(Q1=q, Mean=m))
        sel.add(0, mk(5, 9), 'a'); sel.add(60, mk(5, 8), 'b'); sel.add(120, mk(5, 9), 'c'); sel.add(180, mk(6, 1), 'd')
        self.assertEqual(sel.best['global_update'], 180)
        tie = metrics.Selection(); tie.add(0, mk(5, 9), 'a'); tie.add(60, mk(5, 9), 'b'); tie.add(120, mk(5, 10), 'c')
        self.assertEqual(tie.best['global_update'], 120)
        keep = metrics.Selection(); keep.add(0, mk(7, 1), 'a'); keep.add(60, mk(6, 9), 'b')
        self.assertTrue(keep.report()['selected_is_starting_model'] and keep.report()['best_trained_only']['global_update'] == 60)
        recovery = metrics.Selection(starting_update=360)
        recovery.add(360, mk(8, 9), 'baseline'); recovery.add(420, mk(7, 8), 'trained')
        self.assertEqual(recovery.report()['selected']['global_update'], 360)
        self.assertTrue(recovery.report()['selected_is_starting_model'])
        self.assertEqual(recovery.report()['best_trained_only']['global_update'], 420)
        with self.assertRaises(ValueError):
            keep.add(60, mk(1, 1), 'z')


class PowerTests(unittest.TestCase):
    OVERRIDE = dict(power_guard.OVERRIDE_FIELDS, recorded_at_utc='2026-10-28T16:48:02+00:00')

    def run_with(self, source, held, helpers=1, override=None, extra=''):
        pid = 100
        def run(argv):
            if argv[:3] == ['/usr/bin/pmset', '-g', 'batt']:
                return "Now drawing from '%s'\n -InternalBattery-0\t99%%; discharging" % source
            if argv[0] == '/bin/ps':
                rows = ['100 1 100 /usr/bin/python dispatcher']
                rows += ['%d 100 100 /usr/bin/caffeinate -ims /usr/bin/env x' % (200+i) for i in range(helpers)]
                return '\n'.join(rows)+extra
            return '\n'.join('   pid 200(caffeinate): [0x1] 00:01:00 %s named: "caffeinate command-line tool"' % name for name in held)
        return power_guard.check(run, pid, override=override)

    def test_ac_unchanged_requires_both(self):
        both = ('PreventUserIdleSystemSleep', 'PreventSystemSleep')
        self.assertTrue(self.run_with('AC Power', both)['on_ac'])
        with self.assertRaises(ValueError):
            self.run_with('AC Power', both[:1])
        with self.assertRaises(ValueError):
            self.run_with('AC Power', both, override=self.OVERRIDE, helpers=2)

    def test_battery_needs_pinned_override_and_idle_assertion_only(self):
        idle = ('PreventUserIdleSystemSleep',)
        receipt = self.run_with('Battery Power', idle, override=self.OVERRIDE)
        self.assertEqual((receipt['on_ac'], receipt['battery_override_used'], receipt['required_assertions']), (False, True, list(idle)))
        with self.assertRaises(ValueError):
            self.run_with('Battery Power', idle)
        with self.assertRaises(ValueError):
            self.run_with('Battery Power', (), override=self.OVERRIDE)
        with self.assertRaises(ValueError):
            self.run_with('Battery Power', idle, override=dict(self.OVERRIDE, ac_power_required=True))
        with self.assertRaises(ValueError):
            self.run_with('Battery Power', idle, override=dict(self.OVERRIDE, scope='anything'))
        with self.assertRaises(ValueError):
            self.run_with('Battery Power', idle, override=self.OVERRIDE, helpers=0)

    def test_real_override_record_and_historical_guard(self):
        power_guard.validate_override(b.read(b.BATTERY_OVERRIDE))
        self.assertEqual(b.sha(b.BATTERY_OVERRIDE), b.PINNED[b.BATTERY_OVERRIDE])
        self.assertEqual(b.sha(b.LAST3/'power_guard.py'), b.HISTORICAL_POWER_GUARD_SHA)
        self.assertNotEqual(b.sha(b.HERE/'power_guard.py'), b.HISTORICAL_POWER_GUARD_SHA)


class RuntimeLoaderTests(unittest.TestCase):
    def test_real_runtime_load_parent_validates_checkpoint_at_global360(self):
        class FakeCheckpoint:
            def __init__(self, state):
                self.state = state
                self.loaded = None
                self.complete_checked = False

            def load_checkpoint(self, path, *, expected_sha256, expected_identity):
                self.loaded = (path, expected_sha256, expected_identity)
                return self.state

            def require_complete_update(self, state):
                self.complete_checked = state is self.state

        with tempfile.TemporaryDirectory() as tmp:
            reg = fake_reg(tmp)
            parent = reg['parent']
            state = dict(schema=parent['schema'], identity=parent['expected_identity'],
                identity_sha256=parent['identity_sha256'], global_update=360, phase_update=744,
                cumulative_update=792)
            runtime = object.__new__(worker.RealRuntime)
            runtime.reg = reg
            runtime.ckpt = FakeCheckpoint(state)
            self.assertIs(runtime.load_parent(), state)
            self.assertEqual(runtime.ckpt.loaded, (Path(parent['checkpoint_path']), parent['checkpoint_sha256'],
                parent['expected_identity']))
            self.assertTrue(runtime.ckpt.complete_checked)


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.tmp)

    def test_full_fake_campaign_order_selection_and_exact_audit(self):
        qualities = [0, 3, 9, 4, 1, 12, 12, 2, 5, 6, 1]
        run = Run(self.tmp, qualities); result = run.go()
        self.assertEqual(result['status'], 'completed')
        calls = run.rt.calls
        self.assertEqual(calls[:5], ['load_parent', 'restore', 'snapshot', 'evaluate360', 'learner_restore'])
        self.assertEqual(calls.count('begin_segment'), 4); self.assertEqual(calls.count('checkpoint'), 4)
        self.assertEqual([c for c in calls if c.startswith('evaluate')], ['evaluate%d' % g for g in b.EVAL_UPDATES])
        self.assertEqual((run.rt.snapshots, run.rt.restores), (5, 5))
        self.assertTrue(all(s.closed for s in run.rt.segments))
        for i, c in enumerate(calls):   # each checkpoint is evaluated only after its segment closed; eval is snapshot-bracketed
            if c.startswith('evaluate'):
                self.assertEqual((calls[i-1], calls[i+1]), ('snapshot', 'learner_restore'))
        self.assertEqual(result['counters']['updates'], 240); self.assertEqual(result['counters']['environment_decisions'], b.DECISIONS)
        sel = b.read(run.out/'selection.json')
        self.assertEqual(sel['selected']['global_update'], 360)   # baseline360 wins synthetic recovery fixture
        self.assertTrue(sel['selected_is_starting_model'])
        self.assertEqual(sel['best_trained_only']['global_update'], 540)
        self.assertFalse(sel['official_parent324_promotion'] or sel['promoted'] or sel['automatic_selection'])
        # learner RNG after evaluating == RNG of an identical run in which evaluation never ran
        self.assertEqual(run.rt.rng, 5+sum(sum(range(1, 61)) for _ in range(4)))
        # end-to-end terminal validation against the real frozen row validator
        report = terminal.validate_outputs(run.reg, result, 'g'*64)
        self.assertEqual(report['training']['steps'], b.TRAINING_LIMITS['native_steps']); self.assertEqual(report['evaluation']['constructors'], b.EVAL_EPISODES)
        self.assertEqual(report['training']['resets'], 480)
        self.assertEqual(result['roles']['evaluation']['resets'], 0)

    def test_terminal_detects_tampering(self):
        run = Run(self.tmp, [0]*11); result = run.go()
        path = run.out/'evaluation-420.json'; os.chmod(path, 0o644)
        value = b.read(path); value['summary']['performance']['Q1'] += 1; path.unlink(); b.save(path, value)
        with self.assertRaises(ValueError):
            terminal.validate_outputs(run.reg, result, 'g'*64)

    def test_eval_fault_restores_learner_and_stops_without_retry(self):
        run = Run(self.tmp, [0]*11, fail_eval=480)
        with self.assertRaises(RuntimeError):
            run.go()
        self.assertEqual(run.rt.calls.count('evaluate480'), 1)           # exactly once, no retry
        self.assertEqual(run.rt.calls[-1], 'learner_restore')
        self.assertEqual(run.rt.calls.count('begin_segment'), 2)         # nothing after the fault
        self.assertFalse((run.out/'selection.json').exists())
        self.assertEqual(run.result['status'], 'failed')

    def test_eval_checkpoint_identity_validation(self):
        reg = fake_reg(self.tmp); p = reg['parent']; digest = 'd'*64
        parent = dict(schema=p['schema'], identity=p['expected_identity'], identity_sha256=p['identity_sha256'], global_update=360,
                      phase_update=744, cumulative_update=792)
        p['checkpoint_sha256'] = digest
        worker.validate_eval_state(parent, reg, 'g'*64, b.CAMPAIGN_BASE, digest)
        with self.assertRaises(ValueError):
            worker.validate_eval_state(dict(parent, global_update=359), reg, 'g'*64, b.CAMPAIGN_BASE, digest)
        identity = b.learner_identity(reg, 'g'*64)
        state = dict(schema=b.CHECKPOINT_SCHEMA, identity=identity, identity_sha256=b.identity_hash(identity), global_update=420,
                     phase_update=804, cumulative_update=852, parent_checkpoint_sha256=digest, promoted=False,
                     automatic_selection=False, training_eligible=False, model_fingerprint='m')
        worker.validate_eval_state(state, reg, 'g'*64, 420, 'x', 'm')
        for bad in (dict(state, global_update=60), dict(state, promoted=True), dict(state, model_fingerprint='n'),
                    dict(state, parent_checkpoint_sha256='z'*64)):
            with self.assertRaises(ValueError):
                worker.validate_eval_state(bad, reg, 'g'*64, 420, 'x', 'm')
        with self.assertRaises(ValueError):
            worker.validate_eval_state(state, reg, 'h'*64, 420, 'x', 'm')   # other registration's identity

    def test_missing_restore_is_detected(self):
        run = Run(self.tmp, [0]*11, skip_restore=True)
        with self.assertRaises(ValueError):
            run.go()

    def test_budget_and_lease_guards_fail_closed(self):
        run = Run(self.tmp, [0]*11)
        run.guard.base['raw'] = b.TRAINING_LIMITS['raw_frames']+1
        with self.assertRaises(ValueError):
            run.guard.check()
        run.close()
        run = Run(tempfile.mkdtemp(), [0]*11); self.addCleanup(shutil.rmtree, str(run.tmp))
        run.guard.evaluation['steps'] = b.EVALUATION_LIMITS['native_steps']+1
        with self.assertRaises(ValueError):
            run.guard.check()
        run.close()
        run = Run(tempfile.mkdtemp(), [0]*11); self.addCleanup(shutil.rmtree, str(run.tmp))
        Path(run.reg['state_path']).write_text(json.dumps(dict(active_long_campaign=None)))
        with self.assertRaises(ValueError):
            run.guard.check(force=True)
        run.close()

    def test_main_ledger_install_and_exact_clear(self):
        import audit
        import launch
        reg = fake_reg(self.tmp); path = Path(reg['state_path'])
        with self.assertRaises(ValueError):
            launch.main_state_free(reg)                                   # lease already held
        path.write_text(json.dumps(dict(active_long_campaign=None, keep='x')))
        launch.install_lease(reg)
        self.assertEqual(b.read(path)['active_long_campaign'], reg['expected_lease']); self.assertEqual(b.read(path)['keep'], 'x')
        audit.clear_lease(reg, None)
        self.assertEqual(b.read(path), dict(active_long_campaign=None, keep='x', last_update_at_utc=b.read(path)['last_update_at_utc']))
        with self.assertRaises(ValueError):
            audit.clear_lease(reg, None)
        path.write_text(json.dumps(dict(active_long_campaign=None, training_hold=dict(active=True))))
        with self.assertRaises(ValueError):
            launch.main_state_free(reg)


class StaticTests(unittest.TestCase):
    def test_pins_and_constants(self):
        b.check_pins({str(p): d for p, d in b.PINNED.items()})
        self.assertEqual(b.TRAINING_LIMITS, dict(raw_frames=b.DECISIONS*(4+b.STARTUP)+b.SEGMENTS*b.SLOTS*b.STARTUP, constructors=4, native_steps=240*256, resets=b.DECISIONS))
        self.assertEqual(b.EVALUATION_LIMITS, dict(raw_frames=b.EVAL_EPISODES*18013, constructors=b.EVAL_EPISODES, native_steps=b.EVAL_EPISODES*18000, resets=0))
        self.assertEqual((b.WORK_SECONDS, b.TOTAL_SECONDS, b.DECISIONS, b.EVAL_UPDATES[:3], b.EVAL_UPDATES[-1]), (14400, 14530, b.DECISIONS, [360, 420, 480], 600))
        self.assertEqual((b.SCHEDULE['cumulative_first'], b.SCHEDULE['cumulative_last'], b.SCHEDULE['phase_last']), (793, 1032, 984))
        cohort = b.read(b.COHORT); self.assertEqual((cohort['seeds'], cohort['evaluation_rng_seed']), (b.SEEDS, b.EVAL_RNG_SEED))
        auth = b.read(b.AUTHORIZATION); self.assertEqual((auth['updates'], auth['maximum_work_seconds']), (240, 14400))
        qual = b.read(b.RESTORE_QUAL)
        self.assertEqual((min(qual['next_episode_indices']), max(qual['next_episode_indices']), len(qual['abandoned_current_episodes'])), (443, 505, 64))
        cal = b.calibration_values(dict(training_seconds_per_60_updates=1037.2198662500596, evaluation_prior_seconds=579.8708765000338,
            evaluation_prior_raw_frames=6720672, expected_mean_alive_frames=18000))
        self.assertLess(cal['projected_total_worst_case_seconds'], b.WORK_SECONDS)
        limits = dict(work_seconds=14400, total_seconds=14530, cleanup_seconds=10, postflight_seconds=120, rss_bytes=b.CAP,
                      mps_bytes=b.CAP, retries=0, training=b.TRAINING_LIMITS, evaluation=b.EVALUATION_LIMITS)
        b.validate_limits(limits)
        for key, value in (('retries', 1), ('work_seconds', 14401), ('rss_bytes', b.CAP+1)):
            with self.assertRaises(ValueError):
                b.validate_limits(dict(limits, **{key: value}))
        with self.assertRaises(ValueError):
            b.validate_limits(dict(limits, evaluation=dict(b.EVALUATION_LIMITS, resets=1)))

    def test_historical_files_untouched_and_observer_interface(self):
        for name, digest in b.HISTORICAL_COPIES.items():
            if digest:
                self.assertEqual(b.sha(b.HERE/name), digest); self.assertEqual(b.sha(b.LAST3/name), digest)
        self.assertEqual(b.sha(b.HERE/'dependency-binding.json'), b.sha(b.LAST3/'dependency-binding.json'))
        used = set(re.findall(r'\bb\.([A-Za-z_]+)', (b.HERE/'observe.py').read_text()))
        self.assertFalse(sorted(n for n in used if not hasattr(b, n)))
        used = set(re.findall(r'\bterminal\.([A-Za-z_]+)', (b.HERE/'observe.py').read_text()))
        self.assertFalse(sorted(n for n in used if not hasattr(terminal, n)))

    def test_frozen_sources_load_and_snapshot_is_json_safe(self):
        modules = b.frozen()
        self.assertTrue(all(Path(m.__file__).resolve().parent == b.PRODUCER_PKG for m in modules.values()))
        json.dumps(terminal.accounting(tempfile.mkdtemp(), {}))

    def test_worker_imports_runtime_only_inside_real_runtime(self):
        text = (b.HERE/'worker.py').read_text()
        head = text.split('class RealRuntime')[0]
        self.assertFalse(re.search(r'^\s*(import|from)\s+(torch|numpy|dodge_rl)', head, re.M))
        self.assertIn('rt.learner_restore(snap)', text); self.assertIn('ckpt.restore_learner(state, self.model', text)
        self.assertNotIn('retry(', text.lower()); self.assertNotIn('time.sleep', text)
        self.assertIn("os.chmod(path, 0o444)", text)

    def test_sealed_source_and_draft(self):
        if not (b.HERE/'source-manifest.json').exists():
            self.skipTest('not sealed')
        b.check_owned_source()
        draft = b.HERE/'registration-draft.json'
        if draft.exists() and os.environ.get('PYTHONPYCACHEPREFIX') == str(b.HERE/'empty-pycache'):
            reg = b.read(draft); self.assertEqual((reg['status'], reg['launch_authority']), (b.DRAFT_STATUS, False))
            self.assertIs(reg['calibration']['parent_accepted'], False)
            self.assertEqual(reg['authorization']['battery_override_sha256'], b.PINNED[b.BATTERY_OVERRIDE])


if __name__ == '__main__':
    unittest.main(verbosity=1)
