"""Standalone synthetic tests. No Dodge imports, native envs, teacher or MPS forward."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('action_mode_runner', HERE / 'runner.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


_import_guard = None

def setUpModule():
    import builtins
    global _import_guard
    original = builtins.__import__
    def no_native_import(name, *args, **kwargs):
        if name == 'dodge_rl' or name.startswith('dodge_rl.'):
            raise AssertionError('Native/model imports forbidden in preparation tests')
        return original(name, *args, **kwargs)
    _import_guard = patch.object(builtins, '__import__', side_effect=no_native_import)
    _import_guard.start()

def tearDownModule():
    _import_guard.stop()
    assert not any(name == 'dodge_rl' or name.startswith('dodge_rl.') for name in sys.modules)


class FakeGuard:
    def check(self):
        pass


def row(index, alive=100, score=2):
    return {'episode_index': index, 'seed': r.SEEDS[index], 'score_raw_fixed': int(score * 65536),
            'score': score, 'alive_frames': alive, 'gameplay_frames': alive + 1,
            'terminated': True, 'truncated': False, 'objective_return': score + alive / 100 - 5}


def config(seed, stage):
    assert seed in r.SEEDS and stage == 'D2'
    return {'batch_size': 1, 'action_repeat': 4, 'difficulty': 2, 'patterns_enabled': True,
            'powerups_enabled': True, 'raw_frame_cap': 18000, 'num_threads': 1,
            'chunk_size': 1, 'render_pixels': False, 'auxiliary_targets': False,
            'seeds_by_slot': [[seed]], 'excluded_seed_ranges': [(1, 2)]}


class FakeEnv:
    constructed = []
    def __init__(self, **kwargs):
        self.config = kwargs
        self.index = r.SEEDS.index(kwargs['seeds_by_slot'][0][0])
        self.steps = 0
        self.frames = 0
        self.score = 0
        self.done = False
        self.actions = []
        FakeEnv.constructed.append(self)

    def info(self):
        return {'seed': {'evaluation': True, 'actual_seed': r.SEEDS[self.index], 'episode': 0},
                'startup_frames': 13, 'gameplay_frames': self.frames,
                'alive_frames': self.frames - int(self.done), 'score_raw_fixed': self.score * 65536,
                'score': self.score, 'score_delta_sum_raw_fixed': self.score * 65536,
                'terminated': self.done, 'truncated': False, 'bootstrap': not self.done,
                'objective_return': self.score + (self.frames - int(self.done)) / 100 - 5 * self.done,
                'diagnostics': {'admitted_enemies': self.index % 3,
                                'admitted_rectangles': int(self.steps >= 2), 'onscreen_warnings': 0}}

    def episode_info(self):
        return [self.info()]

    def observations(self):
        g = np.zeros((1, 1, 14), dtype=np.float32)
        g[0, 0, 0] = self.index
        return {'global_feats': g, 'entity_feats': np.zeros((1, 80, 16), np.float32),
                'entity_types': np.zeros((1, 80), np.int64), 'entity_mask': np.zeros((1, 80), bool)}

    def step(self, actions):
        assert not self.done and actions.shape == (1,) and actions.dtype == np.int64
        self.actions.append(int(actions[0]))
        self.steps += 1
        self.frames += 4
        self.score += int(actions[0] == 1)
        self.done = self.steps == 1 + self.index % 4
        return {'info': [self.info()], 'terminated': np.array([self.done]),
                'truncated': np.array([False]), 'observations': self.observations()}


class TinyPolicy(torch.nn.Module):
    def __init__(self, nonfinite=False):
        super().__init__()
        self.nonfinite = nonfinite
        self.active_batches = []

    def forward(self, global_feats, entity_feats, entity_types, entity_mask):
        assert not self.training and not torch.is_grad_enabled()
        assert global_feats.device.type == 'cpu'
        indices = global_feats[:, 0, 0]
        self.active_batches.append(indices.tolist())
        logits = torch.arange(9, dtype=torch.float32).repeat(len(indices), 1) / 7
        logits[:, 1] += indices / 64
        if self.nonfinite:
            logits[0, 0] = float('nan')
        return type('Output', (), {'logits': logits})()


def synthetic_evaluation(mode='sample', seed=64001, policy=None, config_factory=config):
    FakeEnv.constructed = []
    episodes, traces = io.StringIO(), io.StringIO()
    counters = r.baseline_result()
    policy = policy or TinyPolicy()
    rows = r.evaluate(policy, mode, seed if mode == 'sample' else None, 'entry', FakeGuard(),
                      episodes, traces, counters, torch=torch, np=np, env_factory=FakeEnv,
                      config_factory=config_factory, device='cpu')
    return rows, episodes.getvalue(), traces.getvalue(), counters, policy


def matrix(alive_delta=0, score_delta=0):
    d = {}
    for label in r.LABELS:
        d[f'{label}_argmax'] = [row(i, 500 + i, 10) for i in range(64)]
        for j, seed in enumerate(r.CONTROLLER_SEEDS):
            # Replicates differ substantially; their within-seed average is the registered contrast.
            d[f'{label}_sample{seed}'] = [row(i, 500 + i + alive_delta + (j - 1) * 90,
                                               10 + score_delta + j - 1) for i in range(64)]
    return d


class EvaluationTests(unittest.TestCase):
    def test_seeded_trace_repeatable_and_all_64_once(self):
        a, b = synthetic_evaluation(), synthetic_evaluation()
        self.assertEqual(a[:4], b[:4])
        self.assertEqual([x['seed'] for x in a[0]], list(r.SEEDS))
        self.assertEqual(a[3]['episodes_completed'], 64)
        self.assertEqual(a[3]['environments_created'], 64)
        self.assertEqual(a[3]['inference_calls'], 4)

    def test_sorted_shrinking_active_batches_no_reset_or_fillers(self):
        result = synthetic_evaluation()
        batches = result[4].active_batches
        self.assertEqual(batches[0], list(range(64)))
        for step, batch in enumerate(batches):
            self.assertEqual(batch, [i for i in range(64) if i % 4 >= step])
        self.assertEqual(len(FakeEnv.constructed), 64)
        self.assertTrue(all(e.done for e in FakeEnv.constructed))

    def test_batched_categorical_draw_order_matches_independent_reference(self):
        result = synthetic_evaluation()
        actual = [json.loads(line) for line in result[2].splitlines()]
        torch.manual_seed(64001)
        expected = []
        for step in range(4):
            active = [i for i in range(64) if i % 4 >= step]
            logits = torch.arange(9, dtype=torch.float32).repeat(len(active), 1) / 7
            logits[:, 1] += torch.tensor(active) / 64
            choices = torch.distributions.Categorical(logits=logits).sample().tolist()
            expected.extend((r.SEEDS[i], step, a) for i, a in zip(active, choices))
        self.assertEqual([(x['episode_seed'], x['decision_index'], x['chosen_action']) for x in actual], expected)

    def test_controller_seed_once_per_evaluation(self):
        original = torch.manual_seed
        with patch.object(torch, 'manual_seed', wraps=original) as mocked:
            synthetic_evaluation()
        mocked.assert_called_once_with(64001)

    def test_argmax_does_not_reseed(self):
        with patch.object(torch, 'manual_seed', side_effect=AssertionError('argmax reseeded')):
            result = synthetic_evaluation('argmax')
        self.assertEqual(result[3]['episodes_completed'], 64)

    def test_all_nine_real_probabilities_logged(self):
        result = synthetic_evaluation('argmax')
        for line in result[2].splitlines():
            d = json.loads(line)
            self.assertEqual(len(d['probabilities9']), 9)
            self.assertAlmostEqual(sum(d['probabilities9']), 1, places=5)
            self.assertGreater(d['entropy'], 0)
            self.assertGreaterEqual(d['top1_top2_margin'], 0)
            self.assertEqual(d['chosen_action'], d['argmax_action'])

    def test_context_is_presence_and_visibility_not_killer(self):
        result = synthetic_evaluation()
        episodes = [json.loads(line) for line in result[1].splitlines()]
        for item in episodes:
            c = item['context']
            self.assertEqual(c['death_cause'], 'UNKNOWN')
            self.assertTrue(c['context_presence_only'])
            expected = None if item['decisions'] == 1 else 8
            self.assertEqual(c['first_observed_pattern_gameplay_frame'], expected)
            self.assertEqual(c['startup_native_updates'], 7)

    def test_nonfinite_rejected_before_any_step(self):
        with self.assertRaisesRegex(r.Stop, 'Nonfinite'):
            synthetic_evaluation(policy=TinyPolicy(nonfinite=True))
        self.assertTrue(all(e.steps == 0 for e in FakeEnv.constructed))

    def test_wrong_cap_rejected_before_environment(self):
        def wrong(seed, stage):
            return {**config(seed, stage), 'raw_frame_cap': 2000}
        with self.assertRaisesRegex(r.Stop, 'configuration'):
            synthetic_evaluation(config_factory=wrong)
        self.assertEqual(FakeEnv.constructed, [])

    def test_only_D2_and_D_seeds_constructed(self):
        synthetic_evaluation()
        self.assertEqual([e.config['seeds_by_slot'][0][0] for e in FakeEnv.constructed], list(r.SEEDS))
        self.assertTrue(all(e.config['difficulty'] == 2 and e.config['patterns_enabled']
                            and e.config['powerups_enabled'] for e in FakeEnv.constructed))

    def test_wrong_fresh_episode_rejected(self):
        original = FakeEnv.episode_info
        def wrong(env):
            v = original(env)
            v[0]['seed']['episode'] = 1
            return v
        with patch.object(FakeEnv, 'episode_info', wrong), self.assertRaisesRegex(r.Stop, 'Fresh'):
            synthetic_evaluation()

    def test_wrong_startup_rejected(self):
        original = FakeEnv.episode_info
        def wrong(env):
            v = original(env)
            v[0]['startup_frames'] = 14
            return v
        with patch.object(FakeEnv, 'episode_info', wrong), self.assertRaisesRegex(r.Stop, 'Fresh'):
            synthetic_evaluation()


class PairingTests(unittest.TestCase):
    def test_cluster_average_math(self):
        stats = r.paired_statistics(matrix(120, 2), np)
        for d in stats.values():
            self.assertEqual(d['seed_clusters'], 64)
            self.assertEqual(d['sampled_episodes'], 192)
            self.assertEqual(d['metrics']['alive_frames']['paired_mean_delta'], 120)
            self.assertEqual(d['metrics']['alive_frames']['ci95'], [120, 120])
            self.assertEqual(d['metrics']['score']['ci95'], [2, 2])
            self.assertEqual(d['decision'], 'meaningful_stochastic_advantage')

    def test_similarity_requires_both_strict_intervals_inside_margins(self):
        self.assertEqual(r.paired_statistics(matrix(0, 0), np)['phase104']['decision'], 'practical_similarity')
        self.assertEqual(r.paired_statistics(matrix(100, 0), np)['phase104']['decision'], 'mixed_or_inconclusive')
        self.assertEqual(r.paired_statistics(matrix(0, 1), np)['phase104']['decision'], 'mixed_or_inconclusive')

    def test_argmax_advantage(self):
        self.assertEqual(r.paired_statistics(matrix(-120, -2), np)['phase104']['decision'], 'meaningful_argmax_advantage')

    def test_disagreeing_metrics_inconclusive(self):
        self.assertEqual(r.paired_statistics(matrix(120, -2), np)['phase104']['decision'], 'mixed_or_inconclusive')

    def test_bootstrap_matches_independent_seed_cluster_reference(self):
        data = matrix()
        for label in r.LABELS:
            for s in r.CONTROLLER_SEEDS:
                data[f'{label}_sample{s}'] = [row(i, 500 + 2 * i, 10 + i / 4) for i in range(64)]
        stats = r.paired_statistics(data, np)
        indices = np.random.default_rng(764002).integers(0, 64, (10000, 64))
        means = np.arange(64)[indices].mean(1)
        expected = np.percentile(means, [2.5, 97.5])
        for d in stats.values():
            np.testing.assert_allclose(d['metrics']['alive_frames']['ci95'], expected)
            np.testing.assert_allclose(d['metrics']['score']['ci95'], expected / 4)

    def test_missing_replicate_or_duplicate_seed_rejected(self):
        d = matrix()
        del d['entry_sample64001']
        with self.assertRaisesRegex(r.Stop, 'Incomplete'):
            r.paired_statistics(d, np)
        rows = [row(i) for i in range(64)]
        rows[-1] = rows[0]
        with self.assertRaisesRegex(r.Stop, 'duplicate'):
            r.indexed_rows(rows)

    def test_control_compares_fields_not_completion_order(self):
        rows = [row(i) for i in range(64)]
        self.assertTrue(r.compare_control(rows, rows[::-1])['matched'])
        changed = copy.deepcopy(rows)
        changed[0]['objective_return'] += 1e-10
        with self.assertRaisesRegex(r.Stop, 'control mismatch'):
            r.compare_control(rows, changed)

    def test_first_control_mismatch_stops_before_any_sample(self):
        data = matrix()
        calls, events = [], io.StringIO()
        def evaluate(label, mode, seed):
            calls.append((label, mode, seed))
            return data[f'{label}_argmax']
        controls = {'entry': [row(i) for i in range(64)], 'phase96': data['phase96_argmax']}
        order = [f'{l}_argmax' for l in r.LABELS] + [f'{l}_sample{s}' for s in r.CONTROLLER_SEEDS for l in r.LABELS]
        with self.assertRaisesRegex(r.Stop, 'control mismatch'):
            r.execute_order({'order': order}, evaluate, controls, FakeGuard(), events)
        self.assertEqual(calls, [('entry', 'argmax', None)])
        self.assertIn('evaluation_complete', events.getvalue())

    def test_exact_protocol_order_and_768_denominator(self):
        data, calls = matrix(), []
        def evaluate(label, mode, seed):
            name = f'{label}_{"argmax" if mode == "argmax" else "sample" + str(seed)}'
            calls.append(name)
            return data[name]
        order = [f'{l}_argmax' for l in r.LABELS] + [f'{l}_sample{s}' for s in r.CONTROLLER_SEEDS for l in r.LABELS]
        result, matches = r.execute_order({'order': order}, evaluate,
            {l: data[f'{l}_argmax'] for l in ('entry', 'phase96')}, FakeGuard(), io.StringIO())
        self.assertEqual(calls, order)
        self.assertEqual(sum(map(len, result.values())), 768)
        self.assertEqual(set(matches), {'entry', 'phase96'})


class GuardAndIdentityTests(unittest.TestCase):
    def guard(self, now, **kwargs):
        return r.DiagnosticGuard(600, lambda: None, io.StringIO(), clock=lambda: now[0],
                                 rss=kwargs.get('rss', lambda: 10), peak=lambda: 20,
                                 mps=kwargs.get('mps', lambda: 30))

    def test_deadline_inclusive_boundary(self):
        now = [599.999]
        g = self.guard(now)
        g.check()
        now[0] = 600
        with self.assertRaisesRegex(r.Stop, 'deadline'):
            g.check()

    def test_resources_at_limit_allowed_over_limit_rejected(self):
        for field in ('rss', 'mps'):
            with self.subTest(field=field):
                self.guard([0], **{field: lambda: r.LIMIT}).sample()
                with self.assertRaisesRegex(r.Stop, 'limit'):
                    self.guard([0], **{field: lambda: r.LIMIT + 1}).sample()

    def test_self_peak_separate_from_sampled_rss(self):
        g = self.guard([0])
        g.sample()
        self.assertEqual(g.receipt()['maximum_sampled_rss_bytes'], 10)
        self.assertEqual(g.receipt()['maximum_self_peak_rss_bytes'], 20)

    def test_slow_identity_check_crossing_deadline_rejected(self):
        now = [599]
        g = self.guard(now)
        g.verify = lambda: now.__setitem__(0, 600)
        with self.assertRaisesRegex(r.Stop, 'deadline'):
            g.sample()

    def test_sample_gap_over_half_second_rejected(self):
        now = [0]
        g = self.guard(now)
        g.sample()
        now[0] = 0.501
        with self.assertRaisesRegex(r.Stop, 'interval'):
            g.sample()

    def test_identity_every_sample_and_latched_failure(self):
        now, calls = [0], []
        g = self.guard(now)
        g.verify = lambda: calls.append(1)
        g.sample()
        now[0] = .25
        g.sample()
        self.assertEqual(len(calls), 2)
        g.failure = 'hash mismatch'
        with self.assertRaisesRegex(r.Stop, 'Latched'):
            g.check()

    def test_strict_hash_detects_changed_and_missing_inputs(self):
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            p = Path(td) / 'input'
            p.write_text('a')
            pins = {str(p): r.sha(p)}
            r.verify_files(pins)
            p.write_text('b')
            with self.assertRaisesRegex(r.Stop, 'hash mismatch'):
                r.verify_files(pins)
            p.unlink()
            with self.assertRaisesRegex(r.Stop, 'hash mismatch'):
                r.verify_files(pins)

    def test_fixture_exact_lease_checks_and_cancel(self):
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            p = Path(td) / 'fixture-state.json'
            protocol = {'run_id': 'fixture_only'}
            lease = {'kind': 'M3_action_mode_diagnostic', 'authorization': 'new_postovernight_inference_only',
                     'run_id': 'fixture_only', 'protocol_sha256': 'p', 'harness_sha256': 'h',
                     'frozen_capsule_manifest_sha256': 'c', 'frozen_capsule_path': str(r.ROOT)}
            for field in tuple(lease):
                bad = dict(lease, **{field: 'wrong'})
                p.write_text(json.dumps({'active_long_campaign': bad}))
                with self.subTest(field=field), self.assertRaisesRegex(r.Stop, 'lease'):
                    r.assert_lease(p, protocol, 'p', 'h', 'c')
            p.write_text(json.dumps({'active_long_campaign': lease}))
            r.assert_lease(p, protocol, 'p', 'h', 'c')
            p.write_text(json.dumps({'active_long_campaign': {**lease, 'cancel_requested': True}}))
            with self.assertRaisesRegex(r.Stop, 'cancellation'):
                r.assert_lease(p, protocol, 'p', 'h', 'c')

    def test_old_teacher_lease_not_accepted(self):
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            p = Path(td) / 'fixture-state.json'
            p.write_text(json.dumps({'active_long_campaign': {'kind': 'M3_teacher'}}))
            with self.assertRaisesRegex(r.Stop, 'lease'):
                r.assert_lease(p, {'run_id': 'fixture'}, 'p', 'h', 'c')

    def test_readonly_original_checkout_rejected(self):
        with self.assertRaisesRegex(r.Stop, 'read-only capsule'):
            r.assert_readonly_capsule({'version': 'action_mode_capsule_v1', 'files': {}})

    def test_checkpoint_complete_and_identity_semantics(self):
        identity = {'config': {'parent_checkpoint_sha256': 'parent'}}
        item = {'label': 'phase104', 'phase_updates': 104}
        state = {'version': 'teacher_checkpoint_v1', 'resume_mode': 'fresh_env', 'tag': 'periodic',
                 'identity': identity, 'identity_sha256': r.hashlib.sha256(r.canonical(identity)).hexdigest(),
                 'update_progress': {'complete': True, 'in_update': False},
                 'parent_checkpoint_sha256': 'parent',
                 'counters': {'updates': 152, 'phase_updates': 104, 'optimizer_steps': 19392,
                              'environment_decisions': 2490368, 'raw_frames': 9942803, 'checkpoint_index': 23}}
        r.validate_checkpoint(state, item, identity)
        for progress in ({'complete': False}, {'complete': True, 'in_update': True}):
            with self.assertRaisesRegex(r.Stop, 'Incomplete'):
                r.validate_checkpoint({**state, 'update_progress': progress}, item, identity)
        with self.assertRaisesRegex(r.Stop, 'Incomplete'):
            r.validate_checkpoint({**state, 'tag': 'interrupted_mid_update'}, item, identity)
        with self.assertRaisesRegex(r.Stop, 'identity'):
            r.validate_checkpoint({**state, 'identity_sha256': 'wrong'}, item, identity)
        with self.assertRaisesRegex(r.Stop, 'counters'):
            r.validate_checkpoint({**state, 'counters': {**state['counters'], 'updates': 153}}, item, identity)

    def test_source_has_no_training_or_eligibility_calls(self):
        import ast
        tree = ast.parse((HERE / 'runner.py').read_text())
        forbidden = {'validate_transition', 'restore_learner', 'restore_rng', 'save_checkpoint',
                     'make_optimizer', 'backward', 'ppo_update', 'check_budget'}
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
                 n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        self.assertFalse(names & forbidden)
        # Production writes are restricted by path construction to campaign artifacts.
        self.assertNotIn('write_text', names)
        self.assertNotIn('torch.save', (HERE / 'runner.py').read_text())

    def test_dummy_new_session_group_cleanup_and_reap(self):
        process = subprocess.Popen([sys.executable, '-c', 'import time; print("ready", flush=True); time.sleep(30)'],
                                   start_new_session=True, stdout=subprocess.PIPE, text=True)
        self.assertEqual(process.stdout.readline().strip(), 'ready')
        try:
            receipt = r.stop_owned(process)
            self.assertTrue(receipt['reaped'])
            self.assertTrue(receipt['group_empty'])
            self.assertEqual(receipt['owned_pgid'], process.pid)
            self.assertLess(receipt['cleanup_seconds'], 10.1)
            with self.assertRaises(ProcessLookupError):
                os.killpg(process.pid, 0)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            process.stdout.close()

    def test_cancel_signal_restores_handlers(self):
        before = signal.getsignal(signal.SIGTERM)
        with self.assertRaises(KeyboardInterrupt):
            with r.cancellation_signals():
                os.kill(os.getpid(), signal.SIGTERM)
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)

    def test_receipts_exclusive_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            p = Path(td) / 'result.json'
            r.save(p, {'one': 1})
            with self.assertRaises(FileExistsError):
                r.save(p, {'two': 2})
            self.assertEqual(json.loads(p.read_text()), {'one': 1})


class AdditionalBoundaryTests(unittest.TestCase):
    def test_safe_reader_uses_weights_only_and_rejects_shape_before_device(self):
        identity = {'config': {'parent_checkpoint_sha256': 'parent'}}
        item = {'label': 'entry', 'phase_updates': 0, 'path': 'fixture.bin'}
        class LoadPolicy(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(torch.zeros(2))
            def architecture_description(self):
                return {'fixture': True}
            def to(self, **kwargs):
                raise AssertionError('No device allocation permitted in synthetic reader test')
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            root = Path(td)
            (root / 'fixture.bin').write_bytes(b'fixture-only')
            item['sha256'] = r.sha(root / 'fixture.bin')
            state = {'version': 'teacher_checkpoint_v1', 'resume_mode': 'fresh_env', 'tag': 'candidate',
                     'identity': identity, 'identity_sha256': r.hashlib.sha256(r.canonical(identity)).hexdigest(),
                     'update_progress': {}, 'parent_checkpoint_sha256': 'parent',
                     'counters': {'updates': 48, 'phase_updates': 0, 'optimizer_steps': 0,
                                  'environment_decisions': 0, 'raw_frames': 0, 'checkpoint_index': 10},
                     'model': {'weight': torch.zeros(3)}}
            with patch.object(r, 'ROOT', root), patch.object(torch, 'load', return_value=state) as load:
                with self.assertRaisesRegex(r.Stop, 'shapes'):
                    r.load_diagnostic_model(torch, np, LoadPolicy, item,
                        {'checkpoints': [item], 'architecture': {'fixture': True}}, identity, FakeGuard())
                self.assertTrue(load.call_args.kwargs['weights_only'])
                self.assertEqual(load.call_args.kwargs['map_location'], 'cpu')

    def test_unpinned_checkpoint_rejected_before_read(self):
        with self.assertRaisesRegex(r.Stop, 'Unpinned'):
            r.load_diagnostic_model(torch, np, None, {'path': 'not-authorized'},
                                    {'checkpoints': []}, {}, FakeGuard())

    def test_sampler_thread_latches_resource_exception(self):
        calls = [0]
        def rss():
            calls[0] += 1
            if calls[0] > 1:
                raise r.Stop('fixture resource failure')
            return 1
        guard = r.DiagnosticGuard(time.monotonic() + 2, lambda: None, io.StringIO(),
                                  rss=rss, peak=lambda: 1, mps=lambda: 0)
        guard.start()
        try:
            self.assertTrue(guard.stop_event.wait(.001) is False)
            limit = time.monotonic() + 1
            while guard.failure is None and time.monotonic() < limit:
                time.sleep(.01)
            with self.assertRaisesRegex(r.Stop, 'Latched'):
                guard.check()
        finally:
            guard.close()

    def test_supervisor_baseexception_retains_receipt_and_reaps_dummy(self):
        self.supervisor_fixture('BaseException')

    def test_supervisor_SIGINT_reaps_dummy(self):
        self.supervisor_fixture('SIGINT')

    def test_supervisor_SIGTERM_reaps_dummy(self):
        self.supervisor_fixture('SIGTERM')

    def test_supervisor_timeout_reaps_dummy(self):
        self.supervisor_fixture('timeout')

    def supervisor_fixture(self, failure_mode):
        # All state/output/capsule paths are owned test fixtures. No real worker
        # entry point, production ledger, campaign directory or native imports.
        import argparse
        with tempfile.TemporaryDirectory(dir=HERE) as td:
            base = Path(td)
            root, original = base / 'capsule', base / 'original'
            root.mkdir()
            original.mkdir()
            dummy = root / 'dummy.py'
            dummy.write_text('import time, signal; signal.pthread_sigmask(signal.SIG_SETMASK, set()); print("ready", flush=True); time.sleep(2)')
            manifest = {'version': 'action_mode_capsule_v1', 'files': {'dummy.py': r.sha(dummy)}}
            (root / 'capsule-manifest.json').write_text(json.dumps(manifest))
            p = {'run_id': 'fixture_only', 'output': 'fixture_campaign', 'runner': 'dummy.py'}
            lease = {'kind': 'M3_action_mode_diagnostic', 'authorization': 'new_postovernight_inference_only',
                     'run_id': p['run_id'], 'protocol_sha256': r.PROTOCOL_SHA256,
                     'harness_sha256': r.sha(dummy), 'frozen_capsule_manifest_sha256': r.sha(root / 'capsule-manifest.json'),
                     'frozen_capsule_path': str(root)}
            state = base / 'fixture-state.json'
            state.write_text(json.dumps({'active_long_campaign': lease}))
            args = argparse.Namespace(protocol=base / 'fixture-protocol.json',
                                      output=original / 'fixture_campaign', state_path=state)
            original_popen = subprocess.Popen
            owned = []
            def spawn(*a, **kw):
                child = original_popen(*a, **kw)
                owned.append(child)
                end = time.monotonic() + 1
                while time.monotonic() < end:
                    if (args.output / 'worker.stdout.log').read_text().strip() == 'ready':
                        break
                    time.sleep(.01)
                return child
            class InterruptGuard(r.DiagnosticGuard):
                def start(self):
                    pass
                def check(self):
                    if failure_mode in {'SIGINT', 'SIGTERM'}:
                        os.kill(os.getpid(), getattr(signal, failure_mode))
                    elif failure_mode == 'timeout':
                        raise r.Stop('600-second diagnostic deadline reached (fixture)')
                    else:
                        raise KeyboardInterrupt('fixture BaseException after spawn')
            with patch.object(r, 'ROOT', root), patch.object(r, 'ORIGINAL_ROOT', original), \
                 patch.object(r, '__file__', str(dummy)), patch.object(r, 'LAUNCH_MONOTONIC', time.monotonic()), \
                 patch.object(r, 'registered_protocol', return_value=p), \
                 patch.object(r, 'assert_readonly_capsule'), \
                 patch.object(r, 'input_pins', return_value=({str(dummy): r.sha(dummy)}, {})), \
                 patch.object(r, 'DiagnosticGuard', InterruptGuard), patch.object(r.subprocess, 'Popen', side_effect=spawn):
                code = r.supervise(args)
            self.assertEqual(code, 1)
            self.assertEqual(len(owned), 1)
            self.assertIn(owned[0].poll(), (-signal.SIGTERM, -signal.SIGKILL))
            result = json.loads((args.output / 'run-result.json').read_text())
            self.assertEqual(result['status'], 'failed')
            self.assertTrue(result['owned_process_stop']['reaped'])
            self.assertIn('Stop' if failure_mode == 'timeout' else 'KeyboardInterrupt', result['error'])
            self.assertEqual(result['automatic_retries'], 0)
            self.assertTrue((args.output / 'artifact-manifest.json').is_file())

    def test_control_failure_retains_prior_match(self):
        data = matrix()
        controls = {label: copy.deepcopy(data[f'{label}_argmax']) for label in ('entry', 'phase96')}
        controls['phase96'][0] = row(0, 300, 5)
        matches = {}
        calls = []
        def evaluate(label, mode, seed):
            calls.append(label)
            return data[f'{label}_argmax']
        with self.assertRaisesRegex(r.Stop, 'control mismatch'):
            r.execute_order({'order': ['entry_argmax', 'phase96_argmax', 'phase104_argmax']},
                            evaluate, controls, FakeGuard(), io.StringIO(), matches)
        self.assertTrue(matches['entry']['matched'])
        self.assertEqual(calls, ['entry', 'phase96'])


if __name__ == '__main__':
    torch.set_num_threads(1)
    unittest.main(verbosity=2)
