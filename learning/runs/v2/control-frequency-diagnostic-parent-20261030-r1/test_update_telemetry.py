"""CPU synthetic integration tests only: no Torch, native games or Adam steps."""
import copy
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

from update_telemetry import JsonlSink, Recorder, instrument_update, moments, verify_complete_rows


class FakeEnv:
    def __init__(self, k):
        self.k, self.episode, self.frames = k, 0, 0

    def info(self, terminated=False):
        return dict(seed=dict(slot=0, episode=self.episode, actual_seed=7),
                    gameplay_frames=self.frames, terminated=terminated, truncated=False)

    def episode_info(self):
        return [self.info()]

    def batch_info(self):
        return dict(action_repeat=self.k)

    def step(self, actions):
        self.frames += self.k
        ended = self.frames == 2 * self.k
        return dict(info=[self.info(ended)], elapsed_raw_frames=np.array([self.k], dtype=np.int64))

    def reset_done(self, indices):
        self.episode += 1
        self.frames = 0
        return dict(info=[self.info()])


class FakePrepared:
    def __init__(self, k=4):
        self.adapter = SimpleNamespace(env=FakeEnv(k), completed_updates=0)
        self.config = SimpleNamespace(gamma=.995 ** (k / 4), gae_lambda=.95 ** (k / 4),
            reward_scale=.1, learning_rate=3e-5, target_kl=.03, ent_coef=.01, vf_coef=.5)
        self.microbatch_size = self.effective_minibatch_size = 512
        self.adv = np.array([[1], [2], [3]], dtype=np.float32)
        self.targets = self.adv * 2
        self.original_gae = lambda *args, **kw: (self.adv, self.targets)
        self.ppo = SimpleNamespace(compute_gae=self.original_gae)
        self.fail = self.nan_entropy = False
        self.calls = 0

    def update_once(self, check_guard=None):
        self.calls += 1
        k = self.adapter.env.batch_info()['action_repeat']
        actions = np.array([[0], [1], [2]], dtype=np.int64)
        ended = []
        for action in actions:
            if check_guard:
                check_guard()
            returned = self.adapter.env.step(action)
            if self.fail:
                raise RuntimeError('synthetic stop')
            ended.append([returned['info'][0]['terminated']])
            if ended[-1][0]:
                self.adapter.env.reset_done([0])
        terminated = np.array(ended, dtype=np.bool_)
        alive = np.full((3, 1), k, dtype=np.int64) - terminated
        raw = (alive / 100 - 5 * terminated).astype(np.float32)
        batch = SimpleNamespace(actions=actions, raw_rewards=raw,
            rewards=raw * self.config.reward_scale, score_delta_raw_fixed=np.zeros((3, 1), dtype=np.int64),
            alive_raw_frames=alive, elapsed_raw_frames=np.full((3, 1), k, dtype=np.int64),
            terminated=terminated, values=np.zeros((3, 1), dtype=np.float32))
        gae = self.ppo.compute_gae()
        assert gae[0] is self.adv and gae[1] is self.targets
        metrics = dict(epochs_completed=2, optimizer_steps=3, epoch_approx_kls=[.01, .02],
            approx_kl=.02, early_stop_kl=False, entropy=math.nan if self.nan_entropy else 1.2,
            value_loss=2.5, transitions=3)
        self.adapter.completed_updates += 1
        self.result = (SimpleNamespace(batch=batch), metrics, dict(completed_updates=self.adapter.completed_updates))
        return self.result


def run(prepared, recorder, rows):
    return instrument_update(prepared, prepared.ppo, recorder, rows.append,
        resource_snapshot=lambda: dict(peak_rss_bytes=0, peak_mps_driver_bytes=0))


class TelemetryTests(unittest.TestCase):
    def test_both_arms_emit_required_metrics_without_changing_results(self):
        for k in [1, 2, 4]:
            p, rows = FakePrepared(k), []
            original_env = p.adapter.env
            returned = run(p, Recorder('arm-K' + str(k), k), rows)
            self.assertTrue(all(a is b for a, b in zip(returned, p.result)))
            self.assertIs(p.ppo.compute_gae, p.original_gae)
            self.assertIs(p.adapter.env, original_env)
            self.assertFalse(hasattr(p.ppo, '_diagnostic_telemetry_active'))
            row = rows[0]
            for field in ['approx_kl', 'epoch_approx_kls', 'entropy', 'value_loss',
                          'raw_advantages_before_minibatch_normalization', 'action_switch_rate']:
                self.assertIn(field, row)
            self.assertEqual(row['gameplay_frames_delta'], 3 * k)
            self.assertEqual(row['eligible_action_comparisons'], 1)
            self.assertEqual(row['action_switches'], 1)
            self.assertEqual(row['action_switch_rate'], 1)
            self.assertEqual(row['raw_advantages_before_minibatch_normalization']['mean'], 2)
            self.assertAlmostEqual(row['raw_advantages_before_minibatch_normalization']['population_std'], math.sqrt(2 / 3))
            json.dumps(row, allow_nan=False)

    def test_switch_denominator_carries_across_rollouts_but_not_resets(self):
        p, rows, recorder = FakePrepared(), [], Recorder('four', 4)
        run(p, recorder, rows)
        run(p, recorder, rows)
        # Update two compares its first decision with the last live decision of
        # update one, then excludes the newly reset episode's first decision.
        self.assertEqual(rows[1]['eligible_action_comparisons'], 2)
        self.assertEqual(rows[1]['action_switches'], 2)
        self.assertEqual(rows[1]['local_update'], 2)
        self.assertEqual(recorder.frames, 24)

    def test_restart_with_repeated_seed_and_episode_does_not_make_a_switch(self):
        r = Recorder('one', 1)
        before = dict(seed=dict(slot=0, episode=0, actual_seed=7), gameplay_frames=10)
        after = dict(before, gameplay_frames=11, terminated=False, truncated=False)
        r.observe([0], [before], dict(info=[after], elapsed_raw_frames=[1]))
        restart = dict(before, gameplay_frames=0)
        r.observe([1], [restart], dict(info=[dict(after, gameplay_frames=1)], elapsed_raw_frames=[1]))
        self.assertEqual(r.comparisons, 0)

    def test_failure_preserves_partial_counters_and_restores_hooks(self):
        p, rows, recorder = FakePrepared(), [], Recorder('four', 4)
        p.fail = True
        env = p.adapter.env
        with self.assertRaisesRegex(RuntimeError, 'synthetic stop'):
            run(p, recorder, rows)
        self.assertTrue(recorder.failed)
        self.assertEqual(rows[0]['kind'], 'update_failure')
        self.assertEqual(rows[0]['partial_gameplay_frames'], 4)
        self.assertIs(p.adapter.env, env)
        self.assertIs(p.ppo.compute_gae, p.original_gae)
        with self.assertRaisesRegex(ValueError, 'already failed'):
            run(p, recorder, rows)
        self.assertEqual(p.calls, 1)

    def test_nonfinite_metric_refuses_complete_row(self):
        p, rows, recorder = FakePrepared(), [], Recorder('four', 4)
        p.nan_entropy = True
        with self.assertRaisesRegex(ValueError, 'Invalid telemetry scalar'):
            run(p, recorder, rows)
        self.assertEqual([row['kind'] for row in rows], ['update_failure'])
        self.assertTrue(recorder.failed)

    def test_k_mismatch_fails_before_prepared_update(self):
        p, rows = FakePrepared(4), []
        with self.assertRaisesRegex(ValueError, 'differs from native K'):
            run(p, Recorder('one', 1), rows)
        self.assertEqual(p.calls, 0)
        self.assertIs(p.adapter.env.__class__, FakeEnv)

    def test_existing_false_module_marker_is_preserved(self):
        p, rows = FakePrepared(), []
        p.ppo._diagnostic_telemetry_active = False
        run(p, Recorder('four', 4), rows)
        self.assertIs(p.ppo._diagnostic_telemetry_active, False)

    def test_active_module_marker_refuses_overlapping_instrumentation(self):
        p, rows = FakePrepared(), []
        p.ppo._diagnostic_telemetry_active = True
        with self.assertRaisesRegex(ValueError, 'Concurrent instrumentation'):
            run(p, Recorder('four', 4), rows)
        self.assertEqual(p.calls, 0)

    def test_failure_sink_does_not_replace_first_error(self):
        p, recorder = FakePrepared(), Recorder('four', 4)
        p.fail = True
        def broken_sink(row):
            raise OSError('synthetic journal failure')
        with self.assertRaisesRegex(RuntimeError, 'synthetic stop') as caught:
            instrument_update(p, p.ppo, recorder, broken_sink,
                resource_snapshot=lambda: dict(peak_rss_bytes=0, peak_mps_driver_bytes=0))
        self.assertIn('journal failure', caught.exception.__notes__[0])

    def test_advantage_summary_uses_population_scale(self):
        result = moments([2, 2, 2])
        self.assertEqual(result['population_std'], 0)
        self.assertEqual(result['rms'], 2)
        with self.assertRaises(ValueError):
            moments([math.inf])

    def test_writer_is_exclusive_and_preserves_existing_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'updates.jsonl'
            writer = JsonlSink(path)
            writer(dict(arm_id='one', local_update=1))
            writer.close()
            original = path.read_bytes()
            with self.assertRaises(FileExistsError):
                JsonlSink(path)
            self.assertEqual(path.read_bytes(), original)

    def test_strict_audit_requires_every_update_of_both_arms(self):
        rows = []
        for k in [1, 4]:
            p, recorder = FakePrepared(k), Recorder(str(k), k)
            run(p, recorder, rows)
            run(p, recorder, rows)
        expected = {'1': dict(action_repeat=1, updates=2), '4': dict(action_repeat=4, updates=2)}
        self.assertFalse(verify_complete_rows(rows, expected)['launch_authority'])
        with self.assertRaisesRegex(ValueError, 'Missing, duplicate'):
            verify_complete_rows(rows[:-1], expected)
        with self.assertRaisesRegex(ValueError, 'Missing, duplicate'):
            verify_complete_rows(rows + [rows[-1]], expected)
        missing_scale = copy.deepcopy(rows)
        del missing_scale[0]['raw_advantages_before_minibatch_normalization']
        with self.assertRaises(KeyError):
            verify_complete_rows(missing_scale, expected)
        bad_rate = copy.deepcopy(rows)
        bad_rate[0]['action_switch_rate'] = .5
        with self.assertRaisesRegex(ValueError, 'denominator'):
            verify_complete_rows(bad_rate, expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
