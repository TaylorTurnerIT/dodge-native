"""A real production checkpoint plays on the new engine.

The checkpoint is local data and never committed: the tests skip unless
velocity-flow-v2-best.zip is under artifacts/models, or under DODGE_MODELS_DIR.
"""

import os
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("stable_baselines3")

from dodge.env import DodgeVecEnv, native_available
from dodge.evaluate import evaluate_model

pytestmark = pytest.mark.skipif(not native_available(), reason="dodge_rl not installed")

MODELS = Path(os.environ.get("DODGE_MODELS_DIR",
                             Path(__file__).resolve().parents[1] / "artifacts" / "models"))
CHECKPOINT = MODELS / "velocity-flow-v2-best.zip"


@pytest.fixture(scope="module")
def model():
    if not CHECKPOINT.exists():
        pytest.skip(f"{CHECKPOINT.name} is not present")
    from stable_baselines3 import PPO
    return PPO.load(CHECKPOINT, device="cpu")


def test_the_checkpoint_plays_a_few_hundred_decisions(model):
    env = DodgeVecEnv(n_envs=4, seed=1, difficulty=3, patterns=True, powerups=True,
                      action_repeat=1)
    assert env.observation_space.shape == model.observation_space.shape
    observation = env.reset()
    for _ in range(300):
        actions, _ = model.predict(observation, deterministic=True)
        assert actions.shape == (4,) and ((0 <= actions) & (actions < 9)).all()
        observation, _, done, _ = env.step(actions)
        assert np.isfinite(observation).all()
    assert env.total_frames == 4 * 300


def test_the_checkpoint_survives_on_a_few_seeds(model):
    result = evaluate_model(model, [1, 2, 3, 4], frame_cap=3000, difficulty=3,
                            patterns=True, powerups=True, step_frames=1)
    print("v2-best frames survived per seed:", list(map(int, result.frames)))
    assert len(result.frames) == 4 and min(result.frames) > 0
