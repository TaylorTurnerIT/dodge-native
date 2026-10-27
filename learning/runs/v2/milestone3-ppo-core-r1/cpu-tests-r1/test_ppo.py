"""Synthetic PPO correctness tests; no NativeGame/VecDodgeEnv is constructed."""
from __future__ import annotations

import copy
from dataclasses import fields, replace
import io
import json
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from torch import nn
from torch.distributions import Categorical

from dodge_rl.ppo import (
    PPOConfig, RolloutBatch, collect_rollout, compute_gae, ppo_update,
)


@pytest.fixture(autouse=True)
def controlled_cpu_rng_and_threads():
    state, threads = torch.get_rng_state(), torch.get_num_threads()
    torch.set_num_threads(min(4, threads))
    torch.manual_seed(2026)
    yield
    torch.set_rng_state(state)
    torch.set_num_threads(threads)


def scalar_gae_reference(rewards, values, next_values, terminated, truncated, gamma, lam):
    # Independent episode segments: sum deltas explicitly instead of using
    # the production backward recurrence.
    time_steps, envs = rewards.shape
    result = np.empty((time_steps, envs), dtype=np.float64)
    for slot in range(envs):
        for first in range(time_steps):
            total, weight = 0.0, 1.0
            for step in range(first, time_steps):
                bootstrap = 0.0 if terminated[step, slot] else next_values[step, slot]
                total += weight * (rewards[step, slot] + gamma * bootstrap - values[step, slot])
                if terminated[step, slot] or truncated[step, slot]:
                    break
                weight *= gamma * lam
            result[first, slot] = total
    return result


def test_gae_matches_independent_segment_reference_mixed_boundaries():
    reward = torch.tensor([[1., 3.], [2., -4.], [.2, .5], [5., 7.]], dtype=torch.float64)
    values = torch.tensor([[.3, 2.], [.8, -1.], [.1, .2], [2., 1.]], dtype=torch.float64)
    final_values = torch.tensor([[.8, -1.], [999., 12.], [2., 1.], [4., 999.]], dtype=torch.float64)
    terminated = torch.tensor([[False, False], [True, False], [False, False], [False, True]])
    truncated = torch.tensor([[False, False], [False, True], [False, False], [False, False]])
    actual, returns = compute_gae(reward, values, final_values, terminated, truncated, .91, .83)
    expected = scalar_gae_reference(*(v.numpy() for v in (reward, values, final_values, terminated, truncated)), .91, .83)
    np.testing.assert_allclose(actual.numpy(), expected, rtol=0, atol=1e-12)
    torch.testing.assert_close(returns, actual + values, rtol=0, atol=0)
    assert actual[1, 0].item() == 2 - .8  # Death ignores its large final value.
    assert actual[1, 1].item() == -4 + .91 * 12 + 1  # Alive truncation bootstraps.


def test_gae_boundaries_prevent_next_episode_reward_leakage():
    values = torch.zeros((3, 2))
    next_values = torch.tensor([[99., 5.], [0., 0.], [0., 0.]])
    terminated = torch.tensor([[True, False], [False, False], [False, False]])
    truncated = torch.tensor([[False, True], [False, False], [False, False]])
    first, _ = compute_gae(torch.tensor([[1., 1.], [2., 2.], [3., 3.]]), values, next_values,
                           terminated, truncated, 1., 1.)
    second, _ = compute_gae(torch.tensor([[1., 1.], [2000., 2000.], [3000., 3000.]]), values,
                            next_values, terminated, truncated, 1., 1.)
    torch.testing.assert_close(first[0], torch.tensor([1., 6.]), rtol=0, atol=0)
    torch.testing.assert_close(first[0], second[0], rtol=0, atol=0)


def test_gae_rollout_end_bootstraps_and_outputs_are_detached():
    rewards = torch.tensor([[2.]], requires_grad=True)
    values = torch.tensor([[1.]], requires_grad=True)
    next_values = torch.tensor([[3.]], requires_grad=True)
    advantages, returns = compute_gae(rewards, values, next_values, torch.tensor([[False]]),
                                      torch.tensor([[False]]), .5, .8)
    assert advantages.item() == 2.5 and returns.item() == 3.5
    assert not advantages.requires_grad and not returns.requires_grad
    assert rewards.grad is None and values.grad is None


@pytest.mark.parametrize("error", ["nan", "shape", "both_boundaries", "wrong_flags", "discount"])
def test_gae_rejects_invalid_data(error):
    rewards, values, next_values = (torch.zeros((2, 1)) for _ in range(3))
    terminated, truncated = (torch.zeros((2, 1), dtype=torch.bool) for _ in range(2))
    kwargs = {}
    if error == "nan":
        rewards[0, 0] = float("nan")
    elif error == "shape":
        next_values = torch.zeros((1, 1))
    elif error == "both_boundaries":
        terminated[0, 0] = truncated[0, 0] = True
    elif error == "wrong_flags":
        terminated = terminated.float()
    else:
        kwargs["gamma"] = 1.1
    with pytest.raises((ValueError, FloatingPointError)):
        compute_gae(rewards, values, next_values, terminated, truncated, **kwargs)


class TaggedTeacher(nn.Module):
    """A critic that reveals exactly which state supplied each value."""
    def __init__(self):
        super().__init__()
        self.anchor = nn.Parameter(torch.zeros(()))
        self.forward_tags = []
        self.grad_enabled = []

    def forward(self, global_feats, entity_feats, entity_types, entity_mask):
        self.forward_tags.append(global_feats[:, 0, 0].detach().clone())
        self.grad_enabled.append(torch.is_grad_enabled())
        return SimpleNamespace(logits=torch.zeros((len(global_feats), 9), device=global_feats.device) + self.anchor,
                               values=global_feats[:, 0, 0] + self.anchor)


class TaggedEnv:
    """Two mutable slots; collection starts partway through slot zero's episode."""
    def __init__(self):
        self.step_calls = 0
        self.episodes = [0, 0]
        self.frames = [13, 0]
        self.alive = [13, 0]
        self.scores = [32768, 0]
        self.terminated = [False, False]
        self.truncated = [False, False]
        self.tags = [1., 2.]
        self.global_array = np.zeros((2, 1, 14), dtype=np.float32)
        self.entities = np.zeros((2, 80, 16), dtype=np.float32)
        self.types = np.zeros((2, 80), dtype=np.int64)
        self.mask = np.zeros((2, 80), dtype=np.bool_)
        self.actions = []
        self.resets = []

    def batch_info(self):
        return dict(batch_size=2, raw_frame_cap=17, action_repeat=4,
                    seed_mode={"mode": "training"},
                    effective_excluded_seed_ranges=[(0xB0000000, 0xB00003E7),
                        (0xD0000000, 0xD000007F), (0xE0000000, 0xE00003E7)],
                    next_episode_indices=[v + 1 for v in self.episodes])

    def observations(self):
        self.global_array[:, 0, 0] = self.tags
        return dict(global_feats=self.global_array, entity_feats=self.entities,
                    entity_types=self.types, entity_mask=self.mask, indices=np.arange(2),
                    hidden_schedule_metadata="must_never_enter_network")

    def episode_info(self):
        return [dict(seed=dict(slot=i, episode=self.episodes[i], counter=0,
                               actual_seed=100 + 10 * self.episodes[i] + i, evaluation=False),
                     startup_frames=13, gameplay_frames=self.frames[i], alive_frames=self.alive[i],
                     score_raw_fixed=self.scores[i], score=self.scores[i] / 65536,
                     score_delta_sum_raw_fixed=self.scores[i],
                     objective_return=self.scores[i] / 65536 + self.alive[i] / 100 - 5 * self.terminated[i],
                     terminated=self.terminated[i], truncated=self.truncated[i],
                     bootstrap=not self.terminated[i], death_event_count=2 if self.terminated[i] else 0)
                for i in range(2)]

    def step(self, actions):
        assert not any(self.terminated) and not any(self.truncated)
        self.actions.append(actions.copy())
        schedules = [([10., 20.], [4, 4], [0, 32768], [False, False], [True, False]),
                     ([110., 99.], [4, 2], [65536, 32768], [False, True], [False, False]),
                     ([120., 220.], [4, 4], [0, 0], [False, False], [False, False])]
        tags, elapsed, scores, term, trunc = schedules[self.step_calls]
        self.step_calls += 1
        self.tags, self.terminated, self.truncated = tags, term, trunc
        alive = [elapsed[i] - int(term[i]) for i in range(2)]
        for i in range(2):
            self.frames[i] += elapsed[i]
            self.alive[i] += alive[i]
            self.scores[i] += scores[i]
        reward = np.asarray(scores, np.float64) / 65536 + np.asarray(alive) / 100 - 5 * np.asarray(term)
        return dict(observations=self.observations(), rewards=reward.astype(np.float32),
                    score_delta_raw_fixed=np.asarray(scores, dtype=np.int32),
                    alive_raw_frames=np.asarray(alive, dtype=np.uint32),
                    elapsed_raw_frames=np.asarray(elapsed, dtype=np.uint32),
                    terminated=np.asarray(term, dtype=np.bool_), truncated=np.asarray(trunc, dtype=np.bool_),
                    info=self.episode_info())

    def reset_done(self, indices):
        self.resets.append(list(indices))
        for index in indices:
            assert self.terminated[index] or self.truncated[index]
            self.episodes[index] += 1
            self.frames[index] = self.alive[index] = self.scores[index] = 0
            self.terminated[index] = self.truncated[index] = False
            self.tags[index] = 100. * (index + 1)
        observation = self.observations()
        return dict(observations={key: value[indices].copy() for key, value in observation.items()
                                  if isinstance(value, np.ndarray)},
                    info=[self.episode_info()[i] for i in indices])


def test_collector_tags_prove_final_bootstrap_and_reset_action_alignment():
    env, model = TaggedEnv(), TaggedTeacher()
    result = collect_rollout(model, env, 3, "cpu")
    torch.testing.assert_close(result.batch.values, torch.tensor([[1., 2.], [100., 20.], [110., 200.]]))
    torch.testing.assert_close(result.batch.next_values, torch.tensor([[10., 20.], [110., 0.], [120., 220.]]))
    torch.testing.assert_close(result.batch.global_feats[:, :, 0, 0], result.batch.values)
    assert env.resets == [[0], [1]]
    assert [x["rollout_step"] for x in result.completed_episodes] == [0, 1]
    assert result.completed_episodes[0]["truncated"]
    assert result.completed_episodes[1]["terminated"]
    assert result.batch_info["next_episode_indices"] == [2, 2]
    assert model.training and not any(model.grad_enabled)
    assert all(parameter.grad is None for parameter in model.parameters())


def test_collector_keeps_exact_raw_audit_fields_and_one_death_penalty():
    result = collect_rollout(TaggedTeacher(), TaggedEnv(), 3, "cpu")
    batch = result.batch
    assert batch.score_delta_raw_fixed.dtype == batch.alive_raw_frames.dtype == batch.elapsed_raw_frames.dtype == torch.int64
    torch.testing.assert_close(batch.score_delta_raw_fixed, torch.tensor([[0, 32768], [65536, 32768], [0, 0]]))
    assert result.completed_episodes[1]["death_event_count"] == 2
    assert batch.raw_rewards[1, 1].item() == pytest.approx(-4.49, abs=1e-6)
    assert torch.equal(batch.rewards, batch.raw_rewards * PPOConfig().reward_scale)
    assert result.completed_episodes[0]["score_raw_fixed"] == 32768  # Partial episode started before this rollout.
    assert result.completed_episodes[0]["alive_frames"] == 17


def test_collector_storage_and_next_observation_do_not_alias_mutable_environment():
    env = TaggedEnv()
    result = collect_rollout(TaggedTeacher(), env, 3, "cpu")
    expected = result.batch.global_feats.clone()
    env.global_array.fill(-999)
    result.observations["global_feats"].fill(333)
    torch.testing.assert_close(result.batch.global_feats, expected, rtol=0, atol=0)
    for item in fields(result.batch):
        value = getattr(result.batch, item.name)
        if value is not None:
            assert value.device.type == "cpu" and not value.requires_grad and value.is_leaf


def test_collection_continues_nonzero_episode_counters_across_rollouts():
    torch.manual_seed(40)
    whole = collect_rollout(TaggedTeacher(), TaggedEnv(), 3, "cpu")
    torch.manual_seed(40)
    env, model = TaggedEnv(), TaggedTeacher()
    left = collect_rollout(model, env, 2, "cpu")
    right = collect_rollout(model, env, 1, "cpu", observation=left.observations)
    for name in ("global_feats", "actions", "values", "next_values", "rewards", "score_delta_raw_fixed"):
        torch.testing.assert_close(torch.cat([getattr(left.batch, name), getattr(right.batch, name)]),
                                   getattr(whole.batch, name), rtol=0, atol=0)


@pytest.mark.parametrize("counter", ["score", "alive", "gameplay"])
def test_collector_rejects_self_consistent_but_wrong_cumulative_metadata(counter):
    class TamperedEnv(TaggedEnv):
        def step(self, actions):
            result = super().step(actions)
            info = result["info"][1]
            if counter == "score":
                info["score_raw_fixed"] += 32768
                info["score_delta_sum_raw_fixed"] += 32768
            elif counter == "alive":
                info["alive_frames"] -= 1
            else:
                info["gameplay_frames"] += 1
            info["objective_return"] = info["score_raw_fixed"] / 65536 + info["alive_frames"] / 100 - 5 * info["terminated"]
            return result
    with pytest.raises(ValueError, match="Cumulative episode"):
        collect_rollout(TaggedTeacher(), TamperedEnv(), 1, "cpu")


def test_collector_rejects_wrong_reward_without_reset_or_further_step():
    class WrongReward(TaggedEnv):
        def step(self, actions):
            result = super().step(actions)
            result["rewards"][0] += 1
            return result
    env = WrongReward()
    with pytest.raises(ValueError, match="Unscaled step reward"):
        collect_rollout(TaggedTeacher(), env, 3, "cpu")
    assert env.step_calls == 1 and env.resets == []


def test_collector_requires_preconstruction_B_D_E_exclusions():
    class MissingExclusions(TaggedEnv):
        def batch_info(self):
            info = super().batch_info()
            info["effective_excluded_seed_ranges"] = [(0xB0000000, 0xB00003E7)]
            return info
    env = MissingExclusions()
    with pytest.raises(ValueError, match="exclude B, D, and E"):
        collect_rollout(TaggedTeacher(), env, 1, "cpu")
    assert env.step_calls == 0


def test_collector_guard_failure_preserves_mode_without_silent_retry():
    env, model = TaggedEnv(), TaggedTeacher()
    calls = 0
    def guard():
        nonlocal calls
        calls += 1
        if env.step_calls == 1:
            raise RuntimeError("owned deadline")
    with pytest.raises(RuntimeError, match="owned deadline"):
        collect_rollout(model, env, 3, "cpu", check_guard=guard)
    assert env.step_calls == 1 and env.resets == [] and model.training


class TinyTeacher(nn.Module):
    def __init__(self):
        super().__init__()
        self.trunk = nn.Linear(14, 8)
        self.actor_head = nn.Linear(8, 9)
        self.critic_head = nn.Linear(8, 1)

    def forward(self, global_feats, entity_feats, entity_types, entity_mask):
        hidden = torch.tanh(self.trunk(global_feats[:, 0]))
        return SimpleNamespace(logits=self.actor_head(hidden), values=self.critic_head(hidden).squeeze(-1))


def synthetic_batch(model, time_steps=4, envs=3):
    observation = dict(global_feats=torch.randn((time_steps, envs, 1, 14)),
                       entity_feats=torch.zeros((time_steps, envs, 80, 16)),
                       entity_types=torch.zeros((time_steps, envs, 80), dtype=torch.int64),
                       entity_mask=torch.zeros((time_steps, envs, 80), dtype=torch.bool))
    count = time_steps * envs
    actions = (torch.arange(count) % 9).reshape(time_steps, envs)
    with torch.no_grad():
        output = model(*(v.flatten(0, 1) for v in observation.values()))
        old_log_probs = Categorical(logits=output.logits).log_prob(actions.flatten()).reshape(time_steps, envs)
        values = output.values.reshape(time_steps, envs).clone()
    return RolloutBatch(**observation, actions=actions, old_log_probs=old_log_probs,
                        values=values, rewards=torch.linspace(-1., 2., count).reshape(time_steps, envs),
                        next_values=values + .2,
                        terminated=torch.zeros((time_steps, envs), dtype=torch.bool),
                        truncated=torch.zeros((time_steps, envs), dtype=torch.bool))


def optimizer_for(model, config):
    return torch.optim.Adam(model.parameters(), lr=config.learning_rate, eps=config.adam_eps)


def test_ppo_defaults_and_loss_identity_are_registered_and_json_serializable():
    config = PPOConfig()
    assert (config.gamma, config.gae_lambda, config.update_epochs, config.minibatch_size) == (.995, .95, 4, 512)
    assert (config.clip_coef, config.vf_coef, config.ent_coef, config.max_grad_norm) == (.2, .5, .01, .5)
    assert (config.learning_rate, config.adam_eps, config.reward_scale, config.target_kl) == (3e-4, 1e-5, .1, .03)
    description = config.description()
    assert description["value_clipping"] is False
    assert description["value_loss"] == "0.5 * mean((new_value - GAE_return) ** 2)"
    json.dumps(description, allow_nan=False)


@pytest.mark.parametrize("setting", [dict(gamma=1.1), dict(gae_lambda=-.1), dict(reward_scale=0),
    dict(update_epochs=True), dict(minibatch_size=0), dict(learning_rate=float("nan")),
    dict(adam_eps=-1), dict(clip_coef=0), dict(vf_coef=-1), dict(target_kl=-1)])
def test_ppo_config_rejects_invalid_settings(setting):
    with pytest.raises(ValueError):
        PPOConfig(**setting)


def test_ppo_finite_update_routes_actor_critic_and_trunk_gradients():
    model = TinyTeacher()
    batch = synthetic_batch(model)
    frozen = copy.deepcopy(batch)
    config = PPOConfig(minibatch_size=5, target_kl=1e6)
    before = copy.deepcopy(model.state_dict())
    progress = {}
    metrics = ppo_update(model, optimizer_for(model, config), batch, config, progress=progress)
    assert metrics["optimizer_steps"] == 12 and metrics["epochs_completed"] == 4
    assert metrics["actor_grad_norm"] > 0 and metrics["critic_grad_norm"] > 0 and metrics["trunk_grad_norm"] > 0
    assert metrics["finite"] and not metrics["early_stop_kl"]
    assert progress["complete"] and not progress["in_update"] and progress["optimizer_steps"] == 12
    assert any(not torch.equal(value, before[name]) for name, value in model.state_dict().items())
    for item in fields(batch):
        value = getattr(batch, item.name)
        if value is not None:
            torch.testing.assert_close(value, getattr(frozen, item.name), rtol=0, atol=0)
    json.dumps(metrics, allow_nan=False)


def test_ppo_loss_matches_independent_clipped_surrogate_before_optimizer_step():
    model = TinyTeacher()
    batch = synthetic_batch(model)
    batch.old_log_probs += torch.linspace(-.7, .7, batch.transitions).reshape(batch.shape)
    config = PPOConfig(update_epochs=1, minibatch_size=batch.transitions)
    expected_adv = scalar_gae_reference(*(v.numpy() for v in (
        batch.rewards, batch.values, batch.next_values, batch.terminated, batch.truncated)),
        config.gamma, config.gae_lambda).reshape(-1)
    expected_returns = expected_adv + batch.values.numpy().reshape(-1)
    normalized = (expected_adv - expected_adv.mean()) / (expected_adv.std() + 1e-8)
    with torch.no_grad():
        output = model(*(getattr(batch, name).flatten(0, 1) for name in
            ("global_feats", "entity_feats", "entity_types", "entity_mask")))
        distribution = Categorical(logits=output.logits)
        ratios = np.exp(distribution.log_prob(batch.actions.flatten()).numpy() - batch.old_log_probs.numpy().reshape(-1))
        expected_policy = np.maximum(-normalized * ratios,
                                     -normalized * np.clip(ratios, .8, 1.2)).mean()
        expected_value = .5 * np.square(output.values.numpy() - expected_returns).mean()
        expected_entropy = distribution.entropy().mean().item()
    metrics = ppo_update(model, optimizer_for(model, config), batch, config)
    assert metrics["policy_loss"] == pytest.approx(expected_policy, abs=2e-7)
    assert metrics["value_loss"] == pytest.approx(expected_value, abs=5e-7)
    assert metrics["loss"] == pytest.approx(expected_policy + .5 * expected_value - .01 * expected_entropy, abs=5e-7)
    assert metrics["clip_fraction"] > 0


def test_ppo_epoch_KL_is_current_full_buffer_and_stops_additional_epochs():
    model = TinyTeacher()
    batch = synthetic_batch(model)
    config = PPOConfig(update_epochs=4, minibatch_size=5, target_kl=0.)
    metrics = ppo_update(model, optimizer_for(model, config), batch, config)
    with torch.no_grad():
        output = model(*(getattr(batch, name).flatten(0, 1) for name in
            ("global_feats", "entity_feats", "entity_types", "entity_mask")))
        logratio = Categorical(logits=output.logits).log_prob(batch.actions.flatten()) - batch.old_log_probs.flatten()
        expected = (logratio.exp() - 1 - logratio).mean().item()
    assert metrics["approx_kl"] == pytest.approx(expected, abs=1e-9)
    assert metrics["early_stop_kl"] and metrics["epochs_completed"] == 1
    assert metrics["optimizer_steps"] == 3


def test_ppo_cpu_rng_and_fixed_buffer_save_load_reproduce_learner_update():
    model = TinyTeacher()
    batch = synthetic_batch(model)
    config = PPOConfig(minibatch_size=5, update_epochs=2, target_kl=1e6)
    optimizer = optimizer_for(model, config)
    ppo_update(model, optimizer, batch, config)
    checkpoint = io.BytesIO()
    torch.save(dict(model=model.state_dict(), optimizer=optimizer.state_dict(),
                    rng=torch.get_rng_state(), batch=batch), checkpoint)
    rng = torch.get_rng_state()
    expected = ppo_update(model, optimizer, batch, config)
    checkpoint.seek(0)
    saved = torch.load(checkpoint, weights_only=False)
    restored = TinyTeacher()
    restored.load_state_dict(saved["model"])
    restored_optimizer = optimizer_for(restored, config)
    restored_optimizer.load_state_dict(saved["optimizer"])
    torch.set_rng_state(saved["rng"])
    assert torch.equal(saved["rng"], rng)
    actual = ppo_update(restored, restored_optimizer, saved["batch"], config)
    assert actual == expected
    for name, value in model.state_dict().items():
        torch.testing.assert_close(value, restored.state_dict()[name], rtol=0, atol=0)
    for index, state in optimizer.state_dict()["state"].items():
        for name, value in state.items():
            torch.testing.assert_close(value, restored_optimizer.state_dict()["state"][index][name], rtol=0, atol=0)


def test_ppo_interrupted_update_progress_counts_actual_optimizer_step():
    model = TinyTeacher()
    batch = synthetic_batch(model)
    config = PPOConfig(minibatch_size=5)
    optimizer = optimizer_for(model, config)
    before = copy.deepcopy(model.state_dict())
    progress = {}
    def guard():
        if progress.get("optimizer_steps") == 1:
            raise RuntimeError("owned resource deadline")
    with pytest.raises(RuntimeError, match="owned resource deadline"):
        ppo_update(model, optimizer, batch, config, check_guard=guard, progress=progress)
    assert progress["in_update"] and not progress["complete"]
    assert progress["state"] == "in_update" and progress["epoch"] == progress["minibatch"] == 0
    assert progress["optimizer_steps"] == 1 and progress["epochs_completed"] == 0
    assert all(state["step"].item() == 1 for state in optimizer.state.values())
    assert any(not torch.equal(before[name], value) for name, value in model.state_dict().items())


@pytest.mark.parametrize("failure", ["reward", "gradient", "old_graph", "optimizer_missing"])
def test_ppo_rejects_invalid_update_before_weight_mutation(failure):
    model = TinyTeacher()
    batch = synthetic_batch(model)
    config = PPOConfig()
    optimizer = optimizer_for(model, config)
    if failure == "reward":
        batch.rewards[0, 0] = float("nan")
    elif failure == "gradient":
        model.actor_head.weight.register_hook(lambda gradient: gradient * float("nan"))
    elif failure == "old_graph":
        batch.old_log_probs.requires_grad_(True)
    else:
        optimizer = torch.optim.Adam(model.actor_head.parameters(), lr=config.learning_rate, eps=config.adam_eps)
    before = copy.deepcopy(model.state_dict())
    with pytest.raises((ValueError, FloatingPointError)):
        ppo_update(model, optimizer, batch, config)
    for name, value in model.state_dict().items():
        torch.testing.assert_close(value, before[name], rtol=0, atol=0)
    assert optimizer.state == {}


@pytest.mark.parametrize("field", ["raw_reward", "scale", "missing_raw_field"])
def test_ppo_rechecks_collected_raw_audit_fields_before_update(field):
    batch = collect_rollout(TaggedTeacher(), TaggedEnv(), 3, "cpu").batch
    model = TinyTeacher()
    # Replace the synthetic old actor/critic predictions only; keep actual raw
    # audit data from the tagged environment unchanged until the injected defect.
    with torch.no_grad():
        output = model(*(getattr(batch, name).flatten(0, 1) for name in
            ("global_feats", "entity_feats", "entity_types", "entity_mask")))
        batch.values = output.values.reshape(batch.shape)
        batch.old_log_probs = Categorical(logits=output.logits).log_prob(batch.actions.flatten()).reshape(batch.shape)
    if field == "raw_reward":
        batch.raw_rewards[0, 0] += 1
    elif field == "scale":
        batch.rewards *= 2
    else:
        batch.score_delta_raw_fixed = None
    with pytest.raises(ValueError, match="Raw rollout|Learner reward|Raw rollout audit"):
        ppo_update(model, optimizer_for(model, PPOConfig()), batch, PPOConfig())
