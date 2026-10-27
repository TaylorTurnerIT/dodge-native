"""Small, real-extension tests. Long M2 campaigns belong to the parent harness."""
from __future__ import annotations

import ctypes
import sys
import threading
import time

import numpy as np
import pytest

from dodge_rl import VecDodgeEnv
import dodge_rl._native as native

B = (0xB0000000, 0xB00003E7)
D = (0xD0000000, 0xD000007F)
E = (0xE0000000, 0xE00003E7)
MASK64 = (1 << 64) - 1


def reference_seed(run, slot, episode, exclusions=(B,)):
    def mix(z):
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return z ^ (z >> 31)

    base = (mix(run ^ 0x444F4447455F5632)
            ^ mix((slot + 0x9E3779B97F4A7C15) & MASK64)
            ^ mix((episode + 0xD1B54A32D192ED03) & MASK64))
    counter = 0
    while True:
        candidate = mix(base ^ mix((counter + 0x94D049BB133111EB) & MASK64)) >> 32
        if not any(lo <= candidate <= hi for lo, hi in exclusions):
            return candidate, counter
        counter += 1


def equal_tree(a, b):
    if isinstance(a, np.ndarray):
        np.testing.assert_array_equal(a, b)
    elif isinstance(a, dict):
        assert a.keys() == b.keys()
        for key in a:
            equal_tree(a[key], b[key])
    elif isinstance(a, list):
        assert len(a) == len(b)
        for left, right in zip(a, b, strict=True):
            equal_tree(left, right)
    else:
        assert a == b


def numeric_arrays(tree):
    if isinstance(tree, np.ndarray):
        yield tree
    elif isinstance(tree, dict):
        for value in tree.values():
            yield from numeric_arrays(value)
    elif isinstance(tree, list):
        for value in tree:
            yield from numeric_arrays(value)


def check_observation(obs, b, pixels=False, auxiliary=False):
    schema = {
        'global_feats': ((b, 1, 14), np.float32),
        'entity_feats': ((b, 80, 16), np.float32),
        'entity_types': ((b, 80), np.int64),
        'entity_mask': ((b, 80), np.bool_),
        'pixel_valid': ((b,), np.bool_),
        'pixel_aux_pair_valid': ((b,), np.bool_),
    }
    if pixels:
        schema['pixels'] = ((b, 4, 128, 128), np.uint8)
    else:
        assert obs['pixels'] is None
    if auxiliary:
        schema['auxiliary'] = ((b, 5, 16, 16), np.float32)
    else:
        assert obs['auxiliary'] is None
    for key, (shape, dtype) in schema.items():
        value = obs[key]
        assert value.shape == shape
        assert value.dtype == dtype
        assert value.flags.c_contiguous
        assert np.isfinite(value).all()
    assert obs['indices'].shape == (b,)
    assert np.issubdtype(obs['indices'].dtype, np.integer)
    mask = obs['entity_mask']
    assert (obs['entity_types'][~mask] == 0).all()
    assert (obs['entity_feats'][~mask] == 0).all()
    assert ((obs['entity_types'][mask] >= 1) & (obs['entity_types'][mask] <= 8)).all()
    assert len(obs['diagnostics']) == b
    if pixels:
        assert (obs['pixels'] <= 15).all()
    if auxiliary:
        assert np.isin(obs['auxiliary'], [0.0, 1.0]).all()


def test_real_extension_default_schema_and_metadata():
    assert native.__file__.endswith('.so')
    env = VecDodgeEnv()
    obs = env.observations()
    check_observation(obs, 1)
    assert not obs['pixel_valid'].any()
    assert not obs['pixel_aux_pair_valid'].any()
    info = env.batch_info()
    assert info['batch_size'] == 1
    assert info['action_repeat'] == 4
    assert info['raw_frame_cap'] == 18000
    assert info['difficulty'] == 2
    assert info['patterns_enabled'] and info['powerups_enabled']
    assert info['excluded_seed_ranges'] == [B]
    assert info['initial_episode_indices'] == [0]
    assert info['next_episode_indices'] == [1]
    assert info['seed_stream_version'] == 'dodge_slot_splitmix64_high32_reject_v1'
    assert info['motion_version'] == 'measured_center_delta_v1'
    assert info['seed_exclusion_version']
    assert info['observation_schema_version']
    assert list(info['theme_background_shadow']) == [12, 1]
    assert info['initial_highscores_raw_fixed'] == [0] * 12
    episode = env.episode_info()[0]
    assert episode['startup_frames'] == 13
    assert episode['gameplay_frames'] == episode['alive_frames'] == 0
    assert not env.is_poisoned()
    assert env.last_failures() == []


@pytest.mark.parametrize('pixels,auxiliary', [(False, True), (True, False), (True, True)])
def test_optional_schema_initial_stack_and_pair_markers(pixels, auxiliary):
    env = VecDodgeEnv(batch_size=3, render_pixels=pixels, auxiliary_targets=auxiliary)
    obs = env.observations()
    check_observation(obs, 3, pixels, auxiliary)
    assert obs['pixel_valid'].tolist() == [pixels] * 3
    assert obs['pixel_aux_pair_valid'].tolist() == [pixels and auxiliary] * 3
    if pixels:
        for frame in range(1, 4):
            np.testing.assert_array_equal(obs['pixels'][:, 0], obs['pixels'][:, frame])
    step = env.step(np.array([0, 1, 8], dtype=np.int64))
    check_observation(step['observations'], 3, pixels, auxiliary)
    for key, dtype in [('rewards', np.float32), ('score_delta_raw_fixed', np.int64),
                       ('alive_raw_frames', np.uint32), ('elapsed_raw_frames', np.uint32),
                       ('terminated', np.bool_), ('truncated', np.bool_)]:
        assert step[key].shape == (3,)
        assert step[key].dtype == dtype
        assert step[key].flags.c_contiguous


@pytest.mark.parametrize('bad', [
    [], [0], [0, 0, 9], [0, -1, 0], [0, 0, 2**63],
    [0, 0.0, 0], [0, True, 0], [[0], [0], [0]], None, 0, '000',
    np.array([0, 0, 0], dtype=np.int32),
    np.array([0, 0, 0], dtype=np.float64),
    np.array([False] * 3), np.zeros((3, 1), dtype=np.int64),
    np.array(0, dtype=np.int64), np.array([0, 0, 9], dtype=np.int64),
])
def test_action_whole_call_validation_does_not_mutate(bad):
    env = VecDodgeEnv(batch_size=3)
    before = env.episode_info()
    observations = env.observations()
    with pytest.raises((ValueError, TypeError, OverflowError)):
        env.step(bad)
    assert env.episode_info() == before
    equal_tree(env.observations(), observations)
    assert not env.is_poisoned()
    assert env.last_failures() == []


def test_noncontiguous_int64_inputs_are_copied_in_logical_order():
    a, b = VecDodgeEnv(batch_size=3), VecDodgeEnv(batch_size=3)
    actions = np.array([0, 99, 8, 99, 3, 99], dtype=np.int64)[::2]
    assert not actions.flags.c_contiguous
    equal_tree(a.step(actions), b.step([0, 8, 3]))
    equal_tree(a.step(actions[::-1]), b.step((3, 8, 0)))


@pytest.mark.parametrize('kwargs', [
    {'batch_size': 0}, {'action_repeat': 1}, {'action_repeat': 5},
    {'difficulty': 0}, {'difficulty': 4}, {'raw_frame_cap': 0},
    {'num_threads': 0}, {'chunk_size': 0}, {'run_seed': -1}, {'run_seed': 2**64},
    {'seeds_by_slot': []}, {'seeds_by_slot': [[]]},
    {'seeds_by_slot': [[2**32]]}, {'seeds_by_slot': [[-1]]},
    {'excluded_seed_ranges': [(2, 1)]}, {'excluded_seed_ranges': [(0, 2**32 - 1)]},
    {'excluded_seed_ranges': [(0, 99), (100, 2**32 - 1)]},
    {'excluded_seed_ranges': [(-1, 9)]}, {'excluded_seed_ranges': [(0, 2**32)]},
    {'excluded_seed_ranges': [(0.0, 3)]},
    {'initial_episode_indices': []}, {'initial_episode_indices': [0, 1]},
    {'initial_episode_indices': [-1]}, {'initial_episode_indices': [2**64]},
    {'initial_episode_indices': [0.0]},
])
def test_invalid_constructor_config_fails_visibly(kwargs):
    with pytest.raises((ValueError, TypeError, OverflowError)):
        VecDodgeEnv(**kwargs)


def test_reservations_known_candidate_high_run_seed_and_initial_offsets():
    run = 2**64 - 1
    first, _ = reference_seed(run, 0, 9)
    extra = [E, D, (first, first), (5, 7), (3, 4), (7, 8)]
    env = VecDodgeEnv(batch_size=2, run_seed=run,
                      excluded_seed_ranges=extra, initial_episode_indices=[9, 27])
    metadata = env.batch_info()
    assert metadata['additional_excluded_seed_ranges'] == extra
    assert metadata['excluded_seed_ranges'] == sorted([(3, 8), B, D, E, (first, first)])
    assert metadata['initial_episode_indices'] == [9, 27]
    assert metadata['next_episode_indices'] == [10, 28]
    for slot, offset in enumerate([9, 27]):
        seed = env.episode_info()[slot]['seed']
        actual, counter = reference_seed(run, slot, offset, [B, *extra])
        assert seed == dict(slot=slot, episode=offset, actual_seed=actual,
                            counter=counter, evaluation=False)
        assert all(not lo <= actual <= hi for lo, hi in [B, *extra])
    assert env.episode_info()[0]['seed']['counter'] > 0
    reset = env.reset_all()
    for slot, offset in enumerate([10, 28]):
        actual, counter = reference_seed(run, slot, offset, [B, *extra])
        assert reset['info'][slot]['seed']['actual_seed'] == actual
        assert reset['info'][slot]['seed']['counter'] == counter
        assert reset['info'][slot]['seed']['episode'] == offset


def test_evaluation_reserved_seeds_offsets_exhaustion_and_no_generator_fallback():
    env = VecDodgeEnv(batch_size=2, seeds_by_slot=[[42, B[0], E[1]], [7, D[0]]],
                      initial_episode_indices=[1, 0], excluded_seed_ranges=[D, E])
    assert env.episode_info()[0]['seed']['actual_seed'] == B[0]
    assert env.episode_info()[0]['seed']['evaluation']
    reset = env.reset_all()
    assert [i['seed']['actual_seed'] for i in reset['info']] == [E[1], D[0]]
    before = env.episode_info()
    with pytest.raises(RuntimeError, match='SeedExhausted'):
        env.reset_all()
    assert env.episode_info() == before
    assert not env.is_poisoned()
    with pytest.raises(RuntimeError, match='SeedExhausted'):
        VecDodgeEnv(seeds_by_slot=[[42]], initial_episode_indices=[1])


def test_max_counter_reset_overflow_validates_all_slots_before_mutation():
    env = VecDodgeEnv(batch_size=2, initial_episode_indices=[0, 2**64 - 1])
    before = env.episode_info()
    assert env.batch_info()['next_episode_indices'] == [1, None]
    with pytest.raises(RuntimeError, match='CounterExhausted'):
        env.reset_all()
    assert env.episode_info() == before
    assert not env.is_poisoned()


def test_short_cap_ragged_repeat_bootstrap_subset_order_and_explicit_reset():
    env = VecDodgeEnv(batch_size=3, raw_frame_cap=5, render_pixels=True, auxiliary_targets=True)
    first = env.step([1, 2, 8])
    assert first['elapsed_raw_frames'].tolist() == [4] * 3
    final = env.step([1, 2, 8])
    assert final['elapsed_raw_frames'].tolist() == [1] * 3
    assert final['alive_raw_frames'].tolist() == [1] * 3
    assert final['terminated'].tolist() == [False] * 3
    assert final['truncated'].tolist() == [True] * 3
    assert final['observations']['pixel_valid'].all()
    assert final['observations']['pixel_aux_pair_valid'].all()
    assert all(i['bootstrap'] and i['gameplay_frames'] == 5 for i in final['info'])
    before = env.episode_info()
    with pytest.raises(ValueError, match='SlotEnded'):
        env.step([0, 0, 0])
    assert env.episode_info() == before
    final_copy = final['observations']['global_feats'].copy()
    reset = env.reset_done(np.array([2, 0], dtype=np.int64))
    assert reset['observations']['indices'].tolist() == [2, 0]
    assert [i['seed']['slot'] for i in reset['info']] == [2, 0]
    assert [i['seed']['episode'] for i in reset['info']] == [1, 1]
    assert env.episode_info()[1] == before[1]
    equal_tree(final['observations']['global_feats'], final_copy)
    assert not np.array_equal(reset['observations']['global_feats'][1], final_copy[0])
    for frame in range(1, 4):
        np.testing.assert_array_equal(reset['observations']['pixels'][:, 0], reset['observations']['pixels'][:, frame])
    empty = env.reset_done([])
    check_observation(empty['observations'], 0, True, True)
    assert empty['info'] == []


@pytest.mark.parametrize('indices,ended', [([0], False), ([1, 0], False),
    ([0, 0], True), ([1, 9], True), ([-1], True), ([0, 1.0], True),
    (np.array([[0]], dtype=np.int64), True), (np.array([0], dtype=np.int32), True)])
def test_reset_whole_validation_no_implicit_reset(indices, ended):
    env = VecDodgeEnv(batch_size=2, raw_frame_cap=1)
    if ended:
        env.step([0, 0])
    before = env.episode_info()
    with pytest.raises((TypeError, ValueError, OverflowError)):
        env.reset_done(indices)
    assert env.episode_info() == before
    assert not env.is_poisoned()


def test_owned_arrays_survive_environment_changes_mutation_and_destruction():
    env = VecDodgeEnv(batch_size=2, render_pixels=True, auxiliary_targets=True)
    reference = VecDodgeEnv(batch_size=2, render_pixels=True, auxiliary_targets=True)
    old = env.observations()
    retained = {key: value.copy() for key, value in old.items() if isinstance(value, np.ndarray)}
    step = env.step([3, 7])
    expected = reference.step([3, 7])
    equal_tree(step, expected)
    for key, saved in retained.items():
        np.testing.assert_array_equal(old[key], saved)
    all_old = list(numeric_arrays(old)) + list(numeric_arrays(step))
    for left_index, left in enumerate(all_old):
        for right in all_old[left_index + 1:]:
            assert not np.shares_memory(left, right)
    for value in all_old:
        value[...] = 0
    equal_tree(env.observations(), reference.observations())
    reset = env.reset_all()
    expected_reset = reference.reset_all()
    equal_tree(reset, expected_reset)
    for previous in all_old:
        for current in numeric_arrays(reset):
            assert not np.shares_memory(previous, current)
    retained_reset = {k: v.copy() for k, v in reset['observations'].items() if isinstance(v, np.ndarray)}
    del env
    for key, saved in retained_reset.items():
        np.testing.assert_array_equal(reset['observations'][key], saved)


def test_same_real_trajectories_threads_chunks_reservations_and_explicit_resets():
    kwargs = dict(batch_size=9, raw_frame_cap=203, render_pixels=True,
                  auxiliary_targets=True, run_seed=2**63 + 9,
                  excluded_seed_ranges=[D, E], initial_episode_indices=list(range(9)))
    a = VecDodgeEnv(**kwargs, num_threads=1, chunk_size=1)
    b = VecDodgeEnv(**kwargs, num_threads=4, chunk_size=3)
    equal_tree(a.observations(), b.observations())
    resets = 0
    for decision in range(120):
        actions = np.array([(decision + slot) % 9 for slot in range(9)], dtype=np.int64)
        left, right = a.step(actions), b.step(actions)
        equal_tree(left, right)
        ended = np.flatnonzero(left['terminated'] | left['truncated']).astype(np.int64)[::-1]
        if len(ended):
            equal_tree(a.reset_done(ended), b.reset_done(ended))
            resets += len(ended)
    assert resets >= 18


def test_real_death_terminal_features_retained_pixels_reward_identity_and_reset():
    env = VecDodgeEnv(seeds_by_slot=[[B[0], B[1]]], render_pixels=True, auxiliary_targets=True)
    score_sum = 0
    alive_sum = 0
    reward_sum = 0.0
    death_count = 0
    previous = env.observations()
    for _ in range(4500):
        result = env.step([0])
        score = int(result['score_delta_raw_fixed'][0])
        alive = int(result['alive_raw_frames'][0])
        death = bool(result['terminated'][0])
        expected = score / 65536 + 0.01 * alive - 5 * death
        np.testing.assert_allclose(result['rewards'][0], expected, atol=3e-7, rtol=1e-7)
        score_sum += score
        alive_sum += alive
        reward_sum += float(result['rewards'][0])
        death_count += death
        info = result['info'][0]
        assert info['score_delta_sum_raw_fixed'] == score_sum
        assert info['alive_frames'] == alive_sum
        assert info['objective_return'] == score_sum / 65536 + alive_sum / 100 - 5 * death_count
        if death:
            assert not result['truncated'][0]
            assert not info['bootstrap']
            assert not result['observations']['pixel_valid'][0]
            assert not result['observations']['pixel_aux_pair_valid'][0]
            np.testing.assert_array_equal(result['observations']['pixels'], previous['pixels'])
            assert not np.array_equal(result['observations']['entity_feats'], previous['entity_feats'])
            assert info['gameplay_frames'] - info['alive_frames'] == 1
            break
        previous = result['observations']
    else:
        pytest.fail('fixed neutral trajectory did not die before the fixed cap')
    assert death_count == 1
    assert abs(reward_sum - info['objective_return']) < 2e-4
    final_feats = result['observations']['entity_feats'].copy()
    before = env.episode_info()
    with pytest.raises(ValueError, match='SlotEnded'):
        env.step([0])
    assert env.episode_info() == before
    reset = env.reset_done([0])
    assert reset['info'][0]['seed']['actual_seed'] == B[1]
    assert reset['info'][0]['gameplay_frames'] == 0
    assert reset['observations']['pixel_aux_pair_valid'][0]
    assert not np.array_equal(final_feats, reset['observations']['entity_feats'])
    np.testing.assert_array_equal(final_feats, result['observations']['entity_feats'])


def one_native_call_with_witness(call, witness=lambda: None):
    """No Python payload loop; a 60s switch interval excludes bytecode yielding.

    The witness blocks before a single native call. It must run after that call
    begins and before it returns. This would fail if that call retained the GIL.
    """
    ready, trigger = threading.Event(), threading.Event()
    observations = []

    def worker():
        ready.set()
        trigger.wait()
        try:
            value = witness()
        except BaseException as error:
            value = error
        observations.append((time.perf_counter_ns(), value))

    thread = threading.Thread(target=worker)
    thread.start()
    assert ready.wait(3)
    old_interval = sys.getswitchinterval()
    try:
        sys.setswitchinterval(60)
        started = time.perf_counter_ns()
        trigger.set()
        result = call()
        ended = time.perf_counter_ns()
    finally:
        sys.setswitchinterval(old_interval)
    thread.join(3)
    assert not thread.is_alive()
    assert len(observations) == 1
    print({'gil_call_ns': ended - started, 'witness_after_start_ns': observations[0][0] - started,
           'witness_before_return_ns': ended - observations[0][0]})
    assert started < observations[0][0] < ended
    return result, observations[0][1]


def test_gil_released_during_single_constructor_without_python_payload_loop():
    env, _ = one_native_call_with_witness(
        lambda: VecDodgeEnv(batch_size=512, render_pixels=True, auxiliary_targets=True))
    assert env.batch_info()['batch_size'] == 512


@pytest.mark.parametrize('method', ['step', 'reset_all', 'reset_done'])
def test_gil_release_and_same_env_concurrent_borrow_fail_safely(method):
    env = VecDodgeEnv(batch_size=512, render_pixels=True, auxiliary_targets=True, raw_frame_cap=1)
    if method == 'reset_done':
        env.step([0] * 512)
    if method == 'step':
        actions = np.zeros(512, dtype=np.int64)
        call = lambda: env.step(actions)
    elif method == 'reset_done':
        indices = np.arange(512, dtype=np.int64)
        call = lambda: env.reset_done(indices)
    else:
        call = env.reset_all
    _, error = one_native_call_with_witness(call, env.reset_all)
    assert isinstance(error, RuntimeError)
    assert 'borrow' in str(error).lower()
    assert not env.is_poisoned()
    assert env.last_failures() == []


def test_gil_witness_rejects_a_native_call_that_holds_the_gil():
    # PyDLL deliberately retains the GIL, unlike ctypes.CDLL. This negative
    # control uses the same synchronization as the extension checks.
    process = ctypes.PyDLL(None)
    process.usleep.argtypes = [ctypes.c_uint]
    process.usleep.restype = ctypes.c_int
    with pytest.raises(AssertionError):
        one_native_call_with_witness(lambda: process.usleep(20_000))


def test_numpy_actions_copied_before_detach_even_when_caller_mutates_input():
    kwargs = dict(batch_size=512, render_pixels=True, auxiliary_targets=True)
    env, reference = VecDodgeEnv(**kwargs), VecDodgeEnv(**kwargs)
    actions = np.zeros(512, dtype=np.int64)
    expected = reference.step(actions)
    result, _ = one_native_call_with_witness(
        lambda: env.step(actions), lambda: actions.fill(9))
    assert (actions == 9).all()
    equal_tree(result, expected)
