"""Observation-only gameplay trace exposed by the native extension.

Exercises whichever extension binary is importable and skips when it predates
the trace source change; it never builds or installs an extension.
"""
import numpy as np
import pytest

from dodge_rl.identity import OBSERVATION_KEYS

SEEDS = [0xDA000000, 0xDA000001, 0xDA000002]


def make_env(**overrides):
    from dodge_rl import VecDodgeEnv
    config = dict(batch_size=1, action_repeat=4, difficulty=2, patterns_enabled=True,
                  powerups_enabled=True, raw_frame_cap=18000, num_threads=1, chunk_size=1,
                  render_pixels=False, auxiliary_targets=False, seeds_by_slot=[[SEEDS[0]]],
                  excluded_seed_ranges=[])
    config.update(overrides)
    try:
        return VecDodgeEnv(**config)
    except TypeError as error:
        if "trace" in str(error):
            pytest.skip("importable extension predates the gameplay trace (no build performed)")
        raise


def action_for(step):
    # Camp most of the time (fyou fires) with bursts of movement.
    return step * 7 % 9 if (step // 40) % 3 == 0 else 0


def run(trace, repeat, seed):
    env = make_env(action_repeat=repeat, trace=trace, seeds_by_slot=[[seed]])
    trail, step = [], 0
    while True:
        result = env.step(np.array([action_for(step)], dtype=np.int64))
        info = dict(result["info"][0])
        trail.append((info.pop("trace"), info, {k: result["observations"][k].tobytes() for k in OBSERVATION_KEYS},
                      result["rewards"].tobytes()))
        step += 1
        if result["terminated"][0] or result["truncated"][0]:
            return trail


@pytest.mark.parametrize("repeat", [1, 4])
def test_trace_on_off_is_bit_identical_except_for_the_trace(repeat):
    for seed in SEEDS:
        off, on = run(False, repeat, seed), run(True, repeat, seed)
        assert len(off) == len(on)
        assert all(a[0] is None for a in off)
        for a, b in zip(off, on):
            assert a[1:] == b[1:]
        # Live steps carry no trace; only the ended episode does.
        assert all(step[0] is None for step in on[:-1]) and on[-1][0] is not None


def test_ended_trace_matches_env_counters_and_death_telemetry():
    for seed in SEEDS:
        trail = run(True, 1, seed)
        trace, info = trail[-1][0], trail[-1][1]
        assert trace["frames"] == info["gameplay_frames"]
        assert trace["fyou_trigger_frames"] == sorted(trace["fyou_trigger_frames"])
        assert len(trace["fyou_trigger_frames"]) == len(trace["fyou_trigger_spawned"])
        assert all(isinstance(n, int) for n in trace["fyou_trigger_spawned"])
        if info["terminated"]:
            death = trace["death"]
            assert death["frame"] == info["fatal_gameplay_frame"]
            assert death["cause"] == info["death_cause"]
            if info["death_cause"] in ("normal_enemy", "kamikaze_enemy", "kamikaze_explosion"):
                assert death["killer"] is not None
            else:
                assert death["killer"] is None
        else:
            assert trace["death"] is None
        ends = [p["end_frame"] for p in trace["patterns"]]
        assert all(end is not None for end in ends[:-1])


def test_trace_off_by_default_and_reported_in_config():
    from dodge_rl import VecDodgeEnv
    default = VecDodgeEnv(batch_size=1, seeds_by_slot=[[SEEDS[0]]], excluded_seed_ranges=[])
    assert default.batch_info()["trace"] is False
    assert make_env(trace=True).batch_info()["trace"] is True
