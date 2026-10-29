from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import sys

import numpy as np
import pytest
import torch
from torch import nn
from torch.distributions import Categorical

RUNTIME_ROOT = (Path(__file__).resolve().parents[5] / "learning/runs/v2/one-frame-training-comparison-luna-20261029-r1/runtime-clean-r2").resolve()
sys.path.insert(0, str(RUNTIME_ROOT))
from dodge_rl import ppo
from dodge_rl.seeded_training import SeededTrainingAdapter

assert Path(ppo.__file__).resolve() == RUNTIME_ROOT / "dodge_rl/ppo.py"
assert Path(sys.modules[SeededTrainingAdapter.__module__].__file__).resolve() == RUNTIME_ROOT / "dodge_rl/seeded_training.py"


class TinyTeacher(nn.Module):
    def __init__(self):
        super().__init__()
        self.actor_head = nn.Linear(14, 9)
        self.critic_head = nn.Linear(14, 1)

    def forward(self, global_feats, entity_feats, entity_types, entity_mask):
        global_feats = global_feats.squeeze(-2)
        return SimpleNamespace(logits=self.actor_head(global_feats),
                               values=self.critic_head(global_feats).squeeze(-1))


def make_batch(seed=71, shape=(32, 64)):
    generator = torch.Generator().manual_seed(seed)
    time, slots = shape
    global_feats = torch.randn(time, slots, 1, 14, generator=generator)
    entity_feats = torch.zeros(time, slots, 80, 16)
    entity_types = torch.zeros(time, slots, 80, dtype=torch.int64)
    entity_mask = torch.zeros(time, slots, 80, dtype=torch.bool)
    actions = torch.randint(0, 9, shape, generator=generator)
    old_log_probs = torch.randn(shape, generator=generator) * 0.01
    values = torch.randn(shape, generator=generator) * 0.1
    rewards = torch.randn(shape, generator=generator) * 0.1
    next_values = torch.randn(shape, generator=generator) * 0.1
    terminated = torch.zeros(shape, dtype=torch.bool)
    truncated = torch.zeros(shape, dtype=torch.bool)
    return ppo.RolloutBatch(global_feats, entity_feats, entity_types, entity_mask,
        actions, old_log_probs, values, rewards, next_values, terminated, truncated)


def test_gae_termination_truncation_and_live_boundaries():
    rewards = torch.tensor([[1.0], [2.0], [3.0]])
    values = torch.zeros_like(rewards)
    next_values = torch.tensor([[10.0], [20.0], [30.0]])
    terminated = torch.tensor([[True], [False], [False]])
    truncated = torch.tensor([[False], [True], [False]])
    adv, _ = ppo.compute_gae(rewards, values, next_values, terminated, truncated,
                             gamma=0.5, gae_lambda=0.5)
    assert torch.equal(adv, torch.tensor([[1.0], [12.0], [18.0]]))


def test_microbatch_accumulation_matches_one_effective_batch_step():
    initial = TinyTeacher().state_dict()
    batch = make_batch()
    config = ppo.PPOConfig(update_epochs=1, minibatch_size=512, target_kl=100.0)
    outputs = []
    metrics = []
    for micro_size in (512, 2048):
        model = TinyTeacher()
        model.load_state_dict(initial)
        optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate, eps=config.adam_eps)
        torch.manual_seed(991)
        metrics.append(ppo.ppo_update(model, optimizer, batch, config,
            microbatch_size=micro_size, effective_minibatch_size=2048))
        outputs.append({key: value.detach().clone() for key, value in model.state_dict().items()})
    for key in outputs[0]:
        assert torch.allclose(outputs[0][key], outputs[1][key], atol=2e-7, rtol=2e-6)
    assert metrics[0]["optimizer_steps"] == metrics[1]["optimizer_steps"] == 1
    assert metrics[0]["transitions"] == 2048


def test_registered_k4_default_matches_explicit_one_microbatch():
    initial = TinyTeacher().state_dict()
    batch = make_batch(shape=(2, 64))
    config = ppo.PPOConfig(update_epochs=1, minibatch_size=512, target_kl=100.0)
    outputs = []
    for explicit in (False, True):
        model = TinyTeacher()
        model.load_state_dict(initial)
        optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate, eps=config.adam_eps)
        torch.manual_seed(33)
        kwargs = ({"microbatch_size": 512, "effective_minibatch_size": 512}
                  if explicit else {})
        ppo.ppo_update(model, optimizer, batch, config, **kwargs)
        outputs.append(model.state_dict())
    for key in outputs[0]:
        assert torch.equal(outputs[0][key], outputs[1][key])


def test_partial_macro_batch_and_kl_stop():
    model = TinyTeacher()
    config = ppo.PPOConfig(update_epochs=4, minibatch_size=512, target_kl=0.0)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate, eps=config.adam_eps)
    metrics = ppo.ppo_update(model, optimizer, make_batch(shape=(1, 64)), config,
        microbatch_size=512, effective_minibatch_size=2048)
    assert metrics["transitions"] == 64
    assert metrics["optimizer_steps"] == 1
    assert metrics["epochs_completed"] == 1
    assert metrics["early_stop_kl"] is True


def _obs(batch_size):
    return {
        "global_feats": np.zeros((batch_size, 1, 14), dtype=np.float32),
        "entity_feats": np.zeros((batch_size, 80, 16), dtype=np.float32),
        "entity_types": np.zeros((batch_size, 80), dtype=np.int64),
        "entity_mask": np.zeros((batch_size, 80), dtype=np.bool_),
    }


class ClosingEnv:
    def __init__(self):
        self.batch_size = 2
        self._obs = _obs(self.batch_size)
        self.step_calls = 0
        self.reset_calls = 0

    def batch_info(self):
        return {"seed_mode": {"mode": "training"}, "effective_excluded_seed_ranges": [
            [0xB0000000, 0xB00003E7], [0xD0000000, 0xD000007F], [0xE0000000, 0xE00003E7]],
            "action_repeat": 1, "batch_size": self.batch_size, "raw_frame_cap": 18000}

    def _episode(self, slot, *, terminated=False, gameplay_frames=0, alive_frames=0):
        seed = {"actual_seed": 123 + slot, "evaluation": False, "slot": slot, "episode": 0}
        return {"seed": seed, "startup_frames": 13, "alive_frames": alive_frames,
            "gameplay_frames": gameplay_frames, "terminated": terminated, "truncated": False,
            "bootstrap": not terminated, "score_raw_fixed": 0,
            "score_delta_sum_raw_fixed": 0,
            "objective_return": alive_frames / 100 - 5 * terminated}

    def episode_info(self):
        return [self._episode(i) for i in range(self.batch_size)]

    def observations(self):
        return self._obs

    def step(self, actions):
        self.step_calls += 1
        infos = [self._episode(i, terminated=True, gameplay_frames=1) for i in range(self.batch_size)]
        return {"terminated": np.ones(self.batch_size, dtype=np.bool_),
            "truncated": np.zeros(self.batch_size, dtype=np.bool_),
            "score_delta_raw_fixed": np.zeros(self.batch_size, dtype=np.int64),
            "alive_raw_frames": np.zeros(self.batch_size, dtype=np.int64),
            "elapsed_raw_frames": np.ones(self.batch_size, dtype=np.int64),
            "rewards": np.full(self.batch_size, -5.0, dtype=np.float32),
            "info": infos, "observations": self._obs}

    def reset_done(self, indices):
        self.reset_calls += 1
        raise AssertionError("final frame-budget step must not reset ended slots")


def test_final_vector_call_closes_budget_without_reset_and_slices_batch():
    env = ClosingEnv()
    collection = ppo.collect_rollout(TinyTeacher(), env, 8, "cpu",
                                     gameplay_frame_budget=1)
    assert collection.budget_reached is True
    assert collection.decisions == 1
    assert collection.gameplay_frames == 2
    assert collection.startup_frames == 26
    assert collection.batch.shape == (1, 2)
    assert len(collection.completed_episodes) == 2
    assert collection.reset_info == []
    assert env.step_calls == 1
    assert env.reset_calls == 0


class SeededMetadataEnv:
    def __init__(self, initial_episode=3, capacity=70):
        self.seeds_by_slot = [[100 + slot] * capacity for slot in range(2)]
        self.initial_episode = initial_episode

    def batch_info(self):
        return {"seed_mode": {"mode": "evaluation", "seeds_by_slot": self.seeds_by_slot},
            "batch_size": 2, "action_repeat": 1}

    def episode_info(self):
        rows = []
        for slot in range(2):
            rows.append({"seed": {"actual_seed": 100 + slot, "evaluation": True,
                "slot": slot, "episode": self.initial_episode}, "startup_frames": 13,
                "alive_frames": 0, "gameplay_frames": 0, "terminated": False,
                "truncated": False, "bootstrap": True, "score_raw_fixed": 0,
                "score_delta_sum_raw_fixed": 0, "objective_return": 0.0})
        return rows


def test_seed_stream_bound_is_relative_to_native_initial_episode_index():
    env = SeededMetadataEnv()
    exclusions = ((0xB0000000, 0xB00003E7), (0xD0000000, 0xD000007F),
                  (0xE0000000, 0xE00003E7))
    adapter = SeededTrainingAdapter(env, seeds_by_slot=env.seeds_by_slot,
        components_by_slot=[["uniform"] * 70 for _ in range(2)],
        strata_by_seed={100: "easy", 101: "hard"},
        training_pool_values={100, 101}, exclusions=exclusions,
        rollout_steps=1024, gameplay_frame_target=129)
    assert adapter.initial_episode_indices == [3, 3]
    assert adapter.max_new_seed_entries == 65
    adapter.expected_reset = [0]
    with pytest.raises(ValueError, match="frame-target worst-case seed stream bound"):
        adapter.before_reset([0], {0: {"seed": {"episode": 67}}})
