"""Passive per-update instrumentation for a future registered diagnostic runner.

No game/model construction, seed draws, optimizer creation, lease acquisition or
campaign entry point. The caller must already own an authorized PreparedUpdates
session. Frozen DODGE-013 files are never edited. One session per process is
required: the temporary GAE observer changes a module attribute, not its source.
"""
from __future__ import annotations

from collections.abc import Callable
import json
import math
import os
from pathlib import Path
import time

import numpy as np


def array(value):
    if hasattr(value, 'detach'):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def moments(value):
    values = array(value).astype(np.float64, copy=False)
    if not values.size or not np.isfinite(values).all():
        raise ValueError('Telemetry requires nonempty finite values')
    return dict(count=int(values.size), mean=float(values.mean()),
                population_std=float(values.std()), rms=float(np.sqrt(np.square(values).mean())),
                minimum=float(values.min()), maximum=float(values.max()))


def finite(value, *, nonnegative=False):
    result = float(value)
    if not math.isfinite(result) or (nonnegative and result < 0):
        raise ValueError('Invalid telemetry scalar')
    return result


def verify_complete_rows(rows, expected_arms):
    """Check both registered arms' full update coverage; grants no run authority."""
    if {arm['action_repeat'] for arm in expected_arms.values()} != {1, 4}:
        raise ValueError('The warm-start diagnostic requires registered K1 and K4 arms')
    grouped = {name: [] for name in expected_arms}
    for row in rows:
        if (row.get('schema') != 'dodge_control_rate_update_telemetry_v1'
                or row.get('kind') != 'update_complete' or row.get('arm_id') not in grouped):
            raise ValueError('Incomplete, failed or unexpected telemetry row')
        grouped[row['arm_id']].append(row)
    for name, expected in expected_arms.items():
        records = grouped[name]
        if (type(expected['updates']) is not int or expected['updates'] <= 0
                or [row['local_update'] for row in records] != list(range(1, expected['updates'] + 1))):
            raise ValueError('Missing, duplicate or reordered update rows: ' + name)
        frames = decisions = 0
        for row in records:
            if row['action_repeat'] != expected['action_repeat']:
                raise ValueError('Telemetry arm K differs')
            count = row['policy_decisions_delta']
            frame_count = row['gameplay_frames_delta']
            if (type(count) is not int or count <= 0 or type(frame_count) is not int
                    or not count <= frame_count <= count * row['action_repeat']
                    or count != row['environment_count'] * row['actual_rollout_decisions_per_slot']):
                raise ValueError('Invalid telemetry exposure')
            frames += frame_count
            decisions += count
            if row['gameplay_frames_total'] != frames or row['policy_decisions_total'] != decisions:
                raise ValueError('Cumulative telemetry exposure differs')
            for key in ['entropy', 'value_loss', 'approx_kl', 'target_kl']:
                finite(row[key], nonnegative=True)
            if (len(row['epoch_approx_kls']) != row['epochs_completed']
                    or row['epochs_completed'] <= 0 or row['optimizer_steps'] <= 0
                    or row['approx_kl'] != row['epoch_approx_kls'][-1]
                    or type(row['early_stop_kl']) is not bool):
                raise ValueError('Incomplete KL/epoch telemetry')
            for value in row['epoch_approx_kls']:
                finite(value, nonnegative=True)
            for key in ['raw_advantages_before_minibatch_normalization', 'gae_returns',
                        'rollout_values', 'raw_reward', 'learner_reward']:
                if row[key]['count'] != count:
                    raise ValueError('Telemetry moment sample count differs')
                for statistic in ['mean', 'population_std', 'rms', 'minimum', 'maximum']:
                    finite(row[key][statistic], nonnegative=statistic in ['population_std', 'rms'])
            switches, comparisons = row['action_switches'], row['eligible_action_comparisons']
            if not 0 <= switches <= comparisons <= count:
                raise ValueError('Invalid action-switch counts')
            rate = None if comparisons == 0 else switches / comparisons
            if row['action_switch_rate'] != rate:
                raise ValueError('Action-switch denominator differs')
            if row['action_switches_per_1000_gameplay_frames'] != 1000 * switches / frame_count:
                raise ValueError('Action-switch frame normalization differs')
    return dict(status='both_arms_complete_update_telemetry_verified',
                updates_per_arm={name: len(records) for name, records in grouped.items()},
                launch_authority=False)


class JsonlSink:
    """Create a new telemetry journal; never replace an existing journal."""

    def __init__(self, path: str | Path):
        self.stream = Path(path).open('x')

    def __call__(self, row):
        self.stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + '\n')
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()


class Recorder:
    def __init__(self, arm_id: str, action_repeat: int):
        if not arm_id or action_repeat not in (1, 2, 4):
            raise ValueError('Named K1/K2/K4 arm required')
        self.arm_id, self.action_repeat = arm_id, action_repeat
        self.previous = {}
        self.switches = self.comparisons = self.frames = self.decisions = 0
        self.completed_updates = 0
        self.failed = False
        self.in_update = False

    def observe(self, actions, before, returned):
        actions = array(actions)
        elapsed = array(returned['elapsed_raw_frames'])
        if actions.shape != (len(before),) or elapsed.shape != actions.shape:
            raise ValueError('Action/episode/frame batch differs')
        if actions.dtype.kind not in 'iu' or elapsed.dtype.kind not in 'iu':
            raise ValueError('Integer actions and raw frames required')
        if not ((0 <= actions).all() and (actions <= 8).all()
                and (1 <= elapsed).all() and (elapsed <= self.action_repeat).all()):
            raise ValueError('Action or raw-frame count outside registered K')
        after = returned['info']
        if len(after) != len(before):
            raise ValueError('Returned episode metadata differs')
        for slot, (action, info, final) in enumerate(zip(actions, before, after, strict=True)):
            seed = info['seed']
            identity = (seed['slot'], seed['episode'], seed['actual_seed'])
            if identity[0] != slot or final['seed'] != seed:
                raise ValueError('Episode changed inside vector step')
            previous = self.previous.get(slot)
            if (previous is not None and previous[0] == identity and previous[2]
                    and info['gameplay_frames'] == previous[3]):
                self.comparisons += 1
                self.switches += int(previous[1] != int(action))
            self.previous[slot] = (identity, int(action), not (final['terminated'] or final['truncated']),
                                   final['gameplay_frames'])
        self.frames += int(elapsed.sum())
        self.decisions += len(actions)


class ObservedEnv:
    def __init__(self, env, recorder):
        self.env, self.recorder = env, recorder
        self.current = env.episode_info()
        if env.batch_info()['action_repeat'] != recorder.action_repeat:
            raise ValueError('Telemetry K differs from native K')

    def __getattr__(self, name):
        return getattr(self.env, name)

    def step(self, actions):
        result = self.env.step(actions)
        self.recorder.observe(actions, self.current, result)
        self.current = list(result['info'])
        return result

    def reset_done(self, indices):
        result = self.env.reset_done(indices)
        for index, info in zip(indices, result['info'], strict=True):
            self.current[index] = info
        return result


def instrument_update(prepared, ppo_module, recorder: Recorder, sink: Callable,
                      *, resource_snapshot: Callable, check_guard=None):
    """Run the existing authorized update once and forward its unchanged result.

    GAE targets and PPO return values are observed without replacement. Persistent
    Recorder state carries eligible action comparisons over rollout boundaries.
    Any failure emits a partial row and consumes this recorder; no retry occurs.
    """
    if recorder.failed or recorder.in_update:
        raise ValueError('Recorder already failed or is in use')
    if prepared.adapter.completed_updates != recorder.completed_updates:
        raise ValueError('Prepared session and telemetry update indices differ')
    absent = object()
    previous_active = getattr(ppo_module, '_diagnostic_telemetry_active', absent)
    if previous_active is not absent and previous_active:
        raise ValueError('Concurrent instrumentation of one PPO module refused')
    original_env = prepared.adapter.env
    original_gae = ppo_module.compute_gae
    recorder.in_update = True
    observed_env = None
    captured = []
    before = (recorder.switches, recorder.comparisons, recorder.frames, recorder.decisions)
    started = time.perf_counter()
    gae_observer_seconds = 0.0

    def observe_gae(*args, **kwargs):
        nonlocal gae_observer_seconds
        output = original_gae(*args, **kwargs)
        begin = time.perf_counter()
        captured.append(dict(raw_advantages_before_minibatch_normalization=moments(output[0]),
                             gae_returns=moments(output[1])))
        gae_observer_seconds += time.perf_counter() - begin
        return output

    ppo_module._diagnostic_telemetry_active = True
    try:
        observed_env = ObservedEnv(original_env, recorder)
        prepared.adapter.env = observed_env
        ppo_module.compute_gae = observe_gae
        collection, metrics, boundary = prepared.update_once(check_guard=check_guard)
        if len(captured) != 1:
            raise ValueError('This telemetry contract requires one frozen-target GAE calculation per update')
        epochs = metrics['epochs_completed']
        if type(epochs) is not int or epochs <= 0 or len(metrics['epoch_approx_kls']) != epochs:
            raise ValueError('Epoch KL accounting is incomplete')
        if type(metrics['optimizer_steps']) is not int or metrics['optimizer_steps'] <= 0:
            raise ValueError('Optimizer-step accounting is incomplete')
        if type(metrics['early_stop_kl']) is not bool:
            raise ValueError('KL-stop flag must be boolean')
        if metrics['approx_kl'] != metrics['epoch_approx_kls'][-1]:
            raise ValueError('Final KL differs from last epoch KL')
        batch, config = collection.batch, prepared.config
        raw, learner_rewards = array(batch.raw_rewards), array(batch.rewards)
        score = array(batch.score_delta_raw_fixed) / 65536.0
        alive = array(batch.alive_raw_frames) / 100.0
        death = -5.0 * array(batch.terminated)
        frames = int(array(batch.elapsed_raw_frames).sum())
        count = int(array(batch.actions).size)
        if raw.shape != array(batch.actions).shape or learner_rewards.shape != raw.shape:
            raise ValueError('Reward and action layouts differ')
        if not np.allclose(raw, score + alive + death, rtol=0, atol=1e-5):
            raise ValueError('Raw reward-component identity differs')
        if not np.array_equal(learner_rewards, raw * config.reward_scale):
            raise ValueError('Learner reward scale differs')
        if (frames != recorder.frames - before[2] or count != recorder.decisions - before[3]
                or metrics['transitions'] != count):
            raise ValueError('Telemetry and actual collected exposure differ')
        switches, comparisons = recorder.switches - before[0], recorder.comparisons - before[1]
        peaks = resource_snapshot()
        if any(type(peaks[name]) is not int or peaks[name] < 0
               for name in ['peak_rss_bytes', 'peak_mps_driver_bytes']):
            raise ValueError('Actual resource counters required')
        row = dict(schema='dodge_control_rate_update_telemetry_v1', kind='update_complete',
            arm_id=recorder.arm_id, action_repeat=recorder.action_repeat,
            local_update=recorder.completed_updates + 1,
            gameplay_frames_delta=frames, gameplay_frames_total=recorder.frames,
            policy_decisions_delta=count, policy_decisions_total=recorder.decisions,
            actual_rollout_decisions_per_slot=int(array(batch.actions).shape[0]),
            environment_count=int(array(batch.actions).shape[1]),
            approx_kl=finite(metrics['approx_kl'], nonnegative=True),
            epoch_approx_kls=[finite(v, nonnegative=True) for v in metrics['epoch_approx_kls']],
            target_kl=finite(config.target_kl, nonnegative=True),
            early_stop_kl=metrics['early_stop_kl'], epochs_completed=epochs,
            optimizer_steps=metrics['optimizer_steps'],
            entropy=finite(metrics['entropy'], nonnegative=True),
            entropy_definition='PPO optimization minibatch/sample-weighted categorical entropy',
            value_loss=finite(metrics['value_loss'], nonnegative=True),
            value_loss_definition='PPO minibatch/sample-weighted 0.5 * mean((V - GAE_return)^2), before vf_coef',
            **captured[0], rollout_values=moments(batch.values),
            raw_reward=moments(raw), learner_reward=moments(learner_rewards),
            raw_reward_components=dict(score_delta=moments(score), alive_bonus=moments(alive), death_penalty=moments(death)),
            action_switches=switches, eligible_action_comparisons=comparisons,
            action_switch_rate=None if comparisons == 0 else switches / comparisons,
            action_switches_per_1000_gameplay_frames=1000 * switches / frames,
            gamma=finite(config.gamma), gae_lambda=finite(config.gae_lambda),
            reward_scale=finite(config.reward_scale), learning_rate=finite(config.learning_rate),
            entropy_coefficient=finite(config.ent_coef), value_coefficient=finite(config.vf_coef),
            effective_minibatch_size=prepared.effective_minibatch_size,
            microbatch_size=prepared.microbatch_size, resources=peaks,
            update_seconds_including_telemetry=time.perf_counter() - started,
            gae_observer_seconds=gae_observer_seconds)
        sink(row)
        recorder.completed_updates += 1
        return collection, metrics, boundary
    except BaseException as error:
        recorder.failed = True
        try:
            sink(dict(schema='dodge_control_rate_update_telemetry_v1', kind='update_failure',
                      arm_id=recorder.arm_id, action_repeat=recorder.action_repeat,
                      attempted_local_update=recorder.completed_updates + 1,
                      first_failure=repr(error), complete=False,
                      partial_gameplay_frames=recorder.frames - before[2],
                      partial_policy_decisions=recorder.decisions - before[3]))
        except BaseException as journal_error:
            error.add_note('Failure journal also failed: ' + repr(journal_error))
        raise
    finally:
        ppo_module.compute_gae = original_gae
        if previous_active is absent:
            del ppo_module._diagnostic_telemetry_active
        else:
            ppo_module._diagnostic_telemetry_active = previous_active
        prepared.adapter.env = original_env
        recorder.in_update = False
