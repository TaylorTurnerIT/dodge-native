"""SpaceBot on the dodge_rl engine: deterministic, and far better than doing nothing."""

import pytest

pytest.importorskip("dodge_rl._native", reason="build the binding: pip install ./crates/dodge-rl-env")

from dodge.engine import NEUTRAL, Engine
from dodge.heuristics import BOTS
from dodge.heuristics.space import SpaceBot
from dodge.overlay import Overlay

SEEDS = (1, 2, 3)
CAP = 400      # frames; SpaceBot usually lives far longer, this just bounds the test


def play(bot_factory, seed, cap=CAP):
    """Frames lived (at most `cap`) and the actions taken."""
    engine = Engine(seed=seed, difficulty=3)
    bot = bot_factory()
    actions = []
    while len(actions) < cap:
        state = engine.lane_state(0)
        bot.observe(state)
        actions.append(bot.act(state))
        if engine.step(actions[-1]):
            break
    return len(actions), actions


def neutral_frames(seed):
    engine = Engine(seed=seed, difficulty=3)
    frames = 1
    while not engine.step(NEUTRAL):
        frames += 1
    return frames


def test_the_same_seed_plays_the_same_game():
    first = play(SpaceBot, 1, cap=200)
    second = play(SpaceBot, 1, cap=200)
    assert first == second


@pytest.mark.parametrize("seed", SEEDS)
def test_spacebot_outlives_a_neutral_policy(seed):
    idle = neutral_frames(seed)
    frames, _ = play(SpaceBot, seed)
    assert frames >= CAP or frames > 2 * idle
    assert frames > idle


def test_the_overlay_is_produced_after_a_decision():
    engine = Engine(seed=1, difficulty=3)
    bot = SpaceBot()
    for _ in range(20):
        state = engine.lane_state(0)
        bot.observe(state)
        engine.step(bot.act(state))
    overlay = bot.overlay()
    assert isinstance(overlay, Overlay)
    assert overlay.field is not None and overlay.field.ndim == 2
    assert overlay.paths or overlay.boxes


def test_the_registry_bots_decide_valid_actions_and_draw():
    assert {"space", "taylor-m0"} <= set(BOTS)
    for _, make_bot in BOTS.values():
        engine = Engine(seed=2, difficulty=3)
        bot = make_bot()
        for _ in range(40):
            state = engine.lane_state(0)
            bot.observe(state)
            action = bot.act(state)
            assert 0 <= action <= 8
            engine.step(action)
        assert isinstance(bot.overlay(), Overlay)


def test_the_engine_reports_state_and_frames():
    engine = Engine(seed=5, difficulty=3)
    state = engine.lane_state(0)
    assert {"px", "py", "enemies", "cp"} <= set(state)
    frame = engine.frame()
    assert frame.shape == (128, 128) and frame.dtype.name == "uint8" and frame.max() <= 15
    engine.reset(7)
    engine.reset(5)
    assert engine.lane_state(0) == state
