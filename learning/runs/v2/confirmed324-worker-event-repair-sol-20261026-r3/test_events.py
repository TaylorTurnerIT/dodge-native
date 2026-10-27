"""R2-01 regressions: real worker/adapter methods with stdlib fake runtime APIs."""
import copy
import json
import os
from pathlib import Path
import time
import types
import unittest
from unittest.mock import patch

import contracts as c
import runtime_adapter as runtime
import test_worker
import transition
import worker


class EventTests(unittest.TestCase):
    def setup_adapter(self, mode):
        helper = test_worker.WorkerTests()
        self.addCleanup(helper.doCleanups)
        fixture = helper.fixture()
        adapter, expected, claim, _ = helper.fake_bound_adapter(fixture)
        out = fixture.path / 'worker-output'
        adapter.reg.update(output=str(out), import_policy=dict(
            dont_write_bytecode=True, pycache_prefix=str(c.HERE / 'empty-pycache')))
        adapter.parent['abandoned_current_episodes'] = []
        adapter.context['parent']['candidate_cumulative_counters'] = dict(
            updates=372, optimizer_steps=20, environment_decisions=30, raw_frames=40)
        adapter.runner = runtime.runner_namespace()
        calls = dict(collect=0, ppo=0, candidate=0, close=0, fsync=0)
        collections = []
        adapter.env = types.SimpleNamespace(episode_info=lambda: [],
            batch_info=lambda: {'next_episode_indices': [100] * 64})
        adapter.make_env = lambda: None
        adapter.observation = {'fake': 'initial'}
        adapter.ppo = object()

        def rows():
            path = out / 'training-episodes.jsonl'
            return [json.loads(line) for line in path.read_text().splitlines()]

        def events_for(local):
            seed = dict(slot=7, episode=100+local, actual_seed=123400+local, counter=0)
            ended = dict(rollout_step=9, seed=seed, terminated=False, truncated=True,
                boundary_reason='raw_frame_cap', alive_frames=18000, score_raw_fixed=123)
            fresh = dict(seed={**seed, 'episode': seed['episode']+1,
                              'actual_seed': seed['actual_seed']+1},
                terminated=False, truncated=False, alive_frames=0, score_raw_fixed=0)
            reset = dict(rollout_step=9, indices=[7], info=[fresh])
            return [ended], [reset]

        def collect(*args, **kwargs):
            calls['collect'] += 1
            completed, resets = events_for(calls['collect'])
            batch = types.SimpleNamespace(actions=types.SimpleNamespace(numel=lambda: 16384),
                elapsed_raw_frames=types.SimpleNamespace(sum=lambda:
                    types.SimpleNamespace(item=lambda: 65536)))
            result = types.SimpleNamespace(completed_episodes=completed, reset_info=resets,
                observations={'fake': calls['collect']}, batch=batch)
            collections.append(result)
            return result

        def ppo(*args, progress, **kwargs):
            calls['ppo'] += 1
            # Read the actual file before PPO: callback must already have flushed
            # and fsynced both records for this collection.
            self.assertEqual(rows()[-2:], expected_events(calls['collect']))
            self.assertGreaterEqual(calls['fsync'], 2*calls['collect'])
            progress.update(complete=False, in_update=True, optimizer_steps=1,
                            phase='optimization', fake_progress='retained')
            if mode == 'ppo_failure':
                raise RuntimeError('fake PPO failure after rollout')
            progress.update(complete=True, in_update=False, optimizer_steps=32,
                            phase='complete')
            return dict(optimizer_steps=32, actor_grad_norm=1, critic_grad_norm=1,
                explained_variance=.25, gradient_alignment_diagnostics={},
                critic_diagnostics=dict(version='same_batch_critic_diagnostics_v1',
                                        pre_update={'explained_variance': .25}))

        def expected_events(local):
            completed, resets = events_for(local)
            return [dict(kind='completed', phase_update=324+local, info=completed[0]),
                    dict(kind='reset', phase_update=324+local, info=resets[0])]

        adapter.ppo_module = types.SimpleNamespace(collect_rollout=collect, ppo_update=ppo)
        adapter.runner['validate_gradient_alignment'] = lambda value: None
        if mode == 'diagnostic_failure':
            def diagnostic(value):
                raise ValueError('fake post-PPO diagnostic failure')
            adapter.runner['validate_gradient_alignment'] = diagnostic

        def candidate(out, local, counters, progress, *args):
            calls['candidate'] += 1
            self.assertEqual(progress['completed_updates'], local)
            return dict(checkpoint=f'fake-candidate-{local}', local_update=local)
        adapter.candidate = candidate
        return helper, fixture, adapter, expected, claim, out, calls, rows, expected_events, collections

    def execute_case(self, mode):
        helper, fixture, adapter, expected, claim, out, calls, rows, events, collections = self.setup_adapter(mode)
        original_emit, original_fsync = worker.emit, worker.os.fsync
        guard = types.SimpleNamespace(check=lambda **kwargs: None, peak_rss=0, peak_mps=0)

        def initialize(instance, reg, context):
            instance.__dict__.update(adapter.__dict__)

        def close(instance):
            calls['close'] += 1
            self.assertEqual(rows()[1:], events(1)[:1] if mode in ('writer_failure', 'fsync_failure')
                             else [event for local in range(1, calls['collect']+1) for event in events(local)])
            instance.env = None

        def emit(stream, value):
            if mode == 'writer_failure' and value.get('kind') == 'reset':
                raise OSError('fake event writer failure')
            return original_emit(stream, value)

        def fsync(fd):
            # Count only event-journal syncs, not R5 claim or result files.
            if (out / 'training-episodes.jsonl').exists():
                if (out / 'training-episodes.jsonl').stat().st_ino == os.fstat(fd).st_ino:
                    calls['fsync'] += 1
                    if mode == 'fsync_failure':
                        raise OSError('fake event fsync failure')
            return original_fsync(fd)

        with helper.pins(fixture), patch.object(transition, 'EXPECTED_PARENT', expected), \
             patch.object(runtime.RuntimeAdapter, '__init__', initialize), \
             patch.object(runtime.RuntimeAdapter, 'close', close), \
             patch.object(worker, 'Guard', return_value=guard), \
             patch.object(worker, 'emit', side_effect=emit), \
             patch.object(worker.os, 'fsync', side_effect=fsync):
            code = worker.execute(adapter.reg, adapter.context, 'f'*64, time.monotonic())
        result = json.loads((out / 'worker-result.json').read_text())
        self.assertTrue(claim.exists())
        claim_bytes = claim.read_bytes()
        with self.assertRaises(FileExistsError):
            worker.run_transition(adapter.reg, adapter)
        self.assertEqual(claim.read_bytes(), claim_bytes)
        self.assertEqual(fixture.events.count('restore_model'), 1)
        self.assertEqual(fixture.events.count('restore_adam'), 1)
        self.assertEqual(calls['close'], 1)
        self.assertNotIn('finalization_error', result)
        if mode != 'success':
            self.assertEqual(code, 1)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['updates'], 0)
            self.assertEqual(result['counters']['updates'], 0)
            self.assertEqual(result['update_progress']['completed_updates'], 0)
            self.assertEqual(result['candidates'], [])
            self.assertEqual(calls['candidate'], 0)
            self.assertFalse(list(out.glob('*candidate*')))
            self.assertEqual((out / 'training-metrics.jsonl').read_text(), '')
        return code, result, calls, rows(), events

    def test_nonempty_rollout_survives_ppo_failure_with_progress_and_spent_claim(self):
        _, result, calls, rows, events = self.execute_case('ppo_failure')
        self.assertEqual(rows[1:], events(1))
        self.assertIn('fake PPO failure after rollout', result['first_failure'])
        self.assertEqual(result['update_progress']['optimizer_steps'], 1)
        self.assertEqual(result['update_progress']['fake_progress'], 'retained')
        self.assertTrue(result['update_progress']['in_update'])
        self.assertEqual(calls['ppo'], 1)

    def test_nonempty_rollout_survives_post_ppo_diagnostic_failure(self):
        _, result, calls, rows, events = self.execute_case('diagnostic_failure')
        self.assertEqual(rows[1:], events(1))
        self.assertIn('fake post-PPO diagnostic failure', result['first_failure'])
        self.assertEqual(result['update_progress']['optimizer_steps'], 32)
        self.assertTrue(result['update_progress']['complete'])
        self.assertFalse(result['update_progress']['in_update'])
        self.assertEqual(calls['ppo'], 1)

    def test_success_journals_each_collection_exactly_once_before_ppo(self):
        code, result, calls, rows, events = self.execute_case('success')
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(calls['collect'], 60)
        self.assertEqual(calls['ppo'], 60)
        self.assertEqual(calls['candidate'], 5)
        self.assertEqual(rows[1:], [event for local in range(1, 61) for event in events(local)])
        self.assertEqual(len(rows), 121)
        self.assertEqual(result['counters']['updates'], 60)

    def test_event_writer_failure_retains_durable_prefix_and_prevents_ppo(self):
        _, result, calls, rows, events = self.execute_case('writer_failure')
        self.assertEqual(rows[1:], events(1)[:1])
        self.assertIn('fake event writer failure', result['first_failure'])
        self.assertEqual(calls['ppo'], 0)
        self.assertEqual(result['update_progress'], dict(complete=True, in_update=False, completed_updates=0))

    def test_event_fsync_failure_fails_closed_without_ppo_or_replay(self):
        _, result, calls, rows, events = self.execute_case('fsync_failure')
        self.assertEqual(rows[1:], events(1)[:1])
        self.assertIn('fake event fsync failure', result['first_failure'])
        self.assertEqual(calls['ppo'], 0)
        self.assertEqual(calls['fsync'], 1)

    def test_callback_payload_mutation_cannot_change_collection(self):
        _, _, adapter, _, _, _, _, _, _, collections = self.setup_adapter('mutation')
        # Exercise actual adapter ordering without the worker's file writer.
        observed = []
        def callback(completed, resets):
            observed.append(copy.deepcopy((completed, resets)))
            completed[0]['seed']['actual_seed'] = -1
            resets[0]['info'][0]['seed']['episode'] = -1
            completed.clear()
            return 'ignored'
        adapter.model = object()
        adapter.optimizer = object()
        adapter.ppo_module.ppo_update = lambda *args, progress, **kwargs: (
            progress.update(complete=True, in_update=False) or
            dict(explained_variance=None, gradient_alignment_diagnostics={},
                 critic_diagnostics=dict(version='same_batch_critic_diagnostics_v1',
                                         pre_update={'explained_variance': None})))
        _, collection = adapter.update(lambda: None, {}, callback)
        self.assertEqual(len(observed), 1)
        self.assertEqual((collection.completed_episodes, collection.reset_info), observed[0])
        self.assertIs(collection, collections[0])
