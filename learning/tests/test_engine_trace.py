"""The engine's gameplay trace (Taylor Turner's recorder), read from Python."""

import numpy as np
import pytest

from dodge.env import DEATH_CAUSES, DodgeVecEnv, make_engine, native_available

pytestmark = pytest.mark.skipif(not native_available(), reason="dodge_rl is not installed")

# The trace names causes as Taylor's DeathCause does; the env as Telemetry does.
TRACE_CAUSES = {
    "normal_enemy": "normal",
    "kamikaze_enemy": "kamikaze",
    "kamikaze_explosion": "kamikaze_blast",
    "static_pattern_rect": "static_rect",
    "moving_pattern_rect": "moving_rect",
}


def _engine(batch, **kwargs):
    return make_engine(batch, step_frames=1, difficulty=3, patterns=True, powerups=True,
                       execution="serial", **kwargs)


def test_trace_is_off_by_default_and_on_after_enabling():
    engine = _engine(2)
    engine.reset_all(seeds=np.arange(2, dtype=np.uint32))
    engine.step(np.zeros(2, dtype=np.uint8))
    assert engine.slot_trace(0) is None
    assert engine.slot_sample(0) is None

    engine.set_trace_enabled(True)
    engine.reset_all(seeds=np.arange(2, dtype=np.uint32))
    engine.step(np.zeros(2, dtype=np.uint8))
    trace = engine.slot_trace(0)
    assert trace["frame"] == 1
    assert trace["death"] is None
    assert trace["patterns"] == []
    assert trace["contacts"] == [0] * 6
    sample = engine.slot_sample(0)
    assert sample["frame"] == 1
    assert sample["pattern_id"] is None
    assert 0 < sample["x"] < 128 and 0 < sample["y"] < 128


def test_death_trace_matches_existing_telemetry():
    lanes = 16
    engine = _engine(lanes, trace=True)
    engine.reset_all(seeds=np.arange(lanes, dtype=np.uint32))
    rng = np.random.default_rng(3)
    seen = {}
    filler = 1_000
    for _ in range(6_000):
        stepped = engine.step(rng.integers(0, 9, lanes, dtype=np.uint8))
        state = DodgeVecEnv._state(stepped)
        ended = np.flatnonzero(stepped["terminated"] | stepped["truncated"])
        for lane in ended:
            if lane in seen:
                continue
            trace = engine.slot_trace(int(lane))
            seen[lane] = trace
            death = trace["death"]
            assert TRACE_CAUSES[death["cause"]] == DEATH_CAUSES[int(state["death_cause"][lane])]
            active = death["active_pattern"]
            assert (active["id"] if active else -1) == int(state["death_pattern"][lane])
            assert death["frame"] == trace["frame"]
            assert sum(trace["contacts"]) >= 1
            if death["killer"] is not None:
                assert death["killer"]["fyou_spawned"] in (True, False)
                assert death["killer_path"][-1][0] == 1
        if len(seen) == lanes:
            break
        if len(ended):
            engine.reset_done(ended, seeds=np.arange(filler, filler + len(ended),
                                                     dtype=np.uint32))
            filler += len(ended)
    assert len(seen) == lanes


def test_slot_sample_frame_advances_one_per_frame():
    engine = _engine(1, trace=True)
    engine.reset_all(seeds=np.array([5], dtype=np.uint32))
    frames = []
    for _ in range(20):
        engine.step(np.array([1], dtype=np.uint8))
        frames.append(engine.slot_sample(0)["frame"])
    assert frames == list(range(1, 21))
