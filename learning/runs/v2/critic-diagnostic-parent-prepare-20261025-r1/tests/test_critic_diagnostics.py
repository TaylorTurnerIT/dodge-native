"""Independent critic-moment checks and fixed-buffer learner noninterference."""
from __future__ import annotations

import copy
from dataclasses import fields
import json
import statistics
from types import SimpleNamespace

import pytest
import torch
from torch import nn
from torch.distributions import Categorical

from dodge_rl.critic_diagnostics import critic_statistics, measure_critic_update
from dodge_rl.ppo import PPOConfig, RolloutBatch, compute_gae, ppo_update


@pytest.fixture(autouse=True)
def controlled_cpu():
    state, threads = torch.get_rng_state(), torch.get_num_threads()
    torch.set_num_threads(min(4, threads))
    torch.manual_seed(317)
    yield
    torch.set_rng_state(state)
    torch.set_num_threads(threads)


def test_moments_match_independent_scalar_oracle():
    target = [1., 2., 4., 8.]
    predicted = [0., 3., 2., 7.]
    residual = [a - b for a, b in zip(target, predicted)]
    result = critic_statistics(torch.tensor(target), torch.tensor(predicted))
    assert result["count"] == 4
    assert result["target_mean"] == statistics.mean(target)
    assert result["target_variance"] == statistics.pvariance(target)
    assert result["prediction_mean"] == statistics.mean(predicted)
    assert result["prediction_variance"] == statistics.pvariance(predicted)
    assert result["target_prediction_covariance"] == statistics.mean(
        (a - statistics.mean(target)) * (b - statistics.mean(predicted))
        for a, b in zip(target, predicted))
    assert result["residual_mean"] == statistics.mean(residual)
    assert result["residual_variance"] == statistics.pvariance(residual)
    assert result["residual_mse"] == statistics.mean(x * x for x in residual)
    assert result["explained_variance"] == 1 - statistics.pvariance(residual) / statistics.pvariance(target)
    json.dumps(result, allow_nan=False)


def test_constant_bias_is_visible_in_mean_and_mse_even_with_perfect_ev():
    target = torch.tensor([-1., 0., 2., 3.])
    result = critic_statistics(target, target - 5)
    assert result["explained_variance"] == 1
    assert result["residual_variance"] == 0
    assert result["residual_mean"] == 5
    assert result["residual_mse"] == 25


@pytest.mark.parametrize("target", [torch.tensor([1.]), torch.ones(5), torch.tensor([1., 1. + 1e-7])])
def test_degenerate_target_variance_has_no_ev(target):
    result = critic_statistics(target, torch.arange(target.numel(), dtype=torch.float32))
    assert result["explained_variance"] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("target,prediction,error", [
    (torch.tensor([float("nan")]), torch.ones(1), FloatingPointError),
    (torch.ones(1), torch.tensor([float("inf")]), FloatingPointError),
    (torch.zeros(0), torch.zeros(0), ValueError),
    (torch.zeros((1, 2)), torch.zeros((1, 2)), ValueError),
    (torch.ones(2), torch.ones(3), ValueError),
    (torch.ones(1, dtype=torch.int64), torch.ones(1), ValueError),
    (torch.tensor([1e300], dtype=torch.float64), torch.zeros(1), FloatingPointError),
])
def test_invalid_or_overflowing_measurements_rejected(target, prediction, error):
    with pytest.raises(error):
        critic_statistics(target, prediction)


class TaggedCritic(nn.Module):
    def __init__(self, nonfinite=False):
        super().__init__()
        self.offset = nn.Parameter(torch.tensor(1.))
        self.child = nn.Dropout(.8)
        self.register_buffer("visits", torch.tensor(0))
        self.calls = []
        self.grad_flags = []
        self.nonfinite = nonfinite

    def forward(self, tags):
        self.calls.append(tags[:, 0].tolist())
        self.grad_flags.append(torch.is_grad_enabled())
        self.visits.add_(1)
        # Even an eval-mode stochastic diagnostic forward must not advance
        # the learner RNG or leave registered buffer mutations behind.
        value = tags[:, 0] + self.offset + torch.rand(len(tags)) * 0
        if self.nonfinite:
            value[:] = float("nan")
        return SimpleNamespace(values=value)


def predict_tagged(model, observations, device):
    return model(observations["tags"].to(device))


def tagged_measurement(model, guard=None):
    tags = torch.arange(7, dtype=torch.float32)
    return measure_critic_update(
        model, {"tags": tags[:, None]}, tags + 2, tags,
        device=torch.device("cpu"), minibatch_size=3,
        predict=predict_tagged, check_guard=guard,
    )


def test_same_batch_chunks_preserve_order_modes_buffers_gradients_and_rng():
    model = TaggedCritic()
    model.train()
    model.child.eval()  # Preserve a mixed-mode module hierarchy too.
    model.offset.grad = torch.tensor(9.)
    rng = torch.get_rng_state().clone()
    before = copy.deepcopy(model.state_dict())
    calls = []
    result = tagged_measurement(model, lambda: calls.append("guard"))
    assert model.calls == [[0., 1., 2.], [3., 4., 5.], [6.]]
    assert model.grad_flags == [False, False, False]
    assert len(calls) == 6
    assert model.training and not model.child.training
    assert torch.equal(torch.get_rng_state(), rng)
    assert model.offset.grad.item() == 9
    for name, tensor in before.items():
        assert torch.equal(model.state_dict()[name], tensor)
    assert result["pre_update"]["residual_mean"] == 2
    assert result["pre_update"]["residual_mse"] == 4
    assert result["post_update"]["residual_mean"] == 1
    assert result["post_update"]["residual_mse"] == 1
    assert result["mean_absolute_value_change"] == 1
    assert result["mean_value_change"] == result["rms_value_change"] == 1
    assert result["pre_update"]["target_mean"] == result["post_update"]["target_mean"] == 5
    assert result["variance_ddof"] == 0
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("failure", ["guard", "nonfinite"])
def test_post_measurement_failure_restores_mode_rng_and_buffers(failure):
    model = TaggedCritic(nonfinite=failure == "nonfinite")
    model.eval()
    model.child.train()
    state = copy.deepcopy(model.state_dict())
    rng = torch.get_rng_state().clone()
    calls = 0

    def guard():
        nonlocal calls
        calls += 1
        if calls == 2 and failure == "guard":
            raise RuntimeError("owned guard")

    with pytest.raises((RuntimeError, FloatingPointError)):
        tagged_measurement(model, guard)
    assert not model.training and model.child.training
    assert torch.equal(torch.get_rng_state(), rng)
    for name, value in state.items():
        assert torch.equal(model.state_dict()[name], value)


class TinyTeacher(nn.Module):
    def __init__(self):
        super().__init__()
        self.trunk = nn.Linear(14, 8)
        self.actor_head = nn.Linear(8, 9)
        self.critic_head = nn.Linear(8, 1)

    def forward(self, global_feats, entity_feats, entity_types, entity_mask):
        hidden = torch.tanh(self.trunk(global_feats[:, 0]))
        return SimpleNamespace(logits=self.actor_head(hidden), values=self.critic_head(hidden).squeeze(-1))


def frozen_batch(model):
    time_steps, slots = 4, 3
    observation = {
        "global_feats": torch.randn(time_steps, slots, 1, 14),
        "entity_feats": torch.zeros(time_steps, slots, 80, 16),
        "entity_types": torch.zeros(time_steps, slots, 80, dtype=torch.int64),
        "entity_mask": torch.zeros(time_steps, slots, 80, dtype=torch.bool),
    }
    actions = (torch.arange(12) % 9).reshape(time_steps, slots)
    with torch.no_grad():
        result = model(*(value.flatten(0, 1) for value in observation.values()))
        log_probs = Categorical(logits=result.logits).log_prob(actions.flatten()).reshape(time_steps, slots)
    return RolloutBatch(
        **observation, actions=actions, old_log_probs=log_probs,
        values=result.values.reshape(time_steps, slots), rewards=torch.linspace(-1., 1., 12).reshape(time_steps, slots),
        next_values=result.values.reshape(time_steps, slots) + .1,
        terminated=torch.zeros(time_steps, slots, dtype=torch.bool),
        truncated=torch.zeros(time_steps, slots, dtype=torch.bool),
    )


def assert_tree_equal(lhs, rhs):
    if isinstance(lhs, torch.Tensor):
        assert torch.equal(lhs, rhs)
    elif isinstance(lhs, dict):
        assert lhs.keys() == rhs.keys()
        for key in lhs:
            assert_tree_equal(lhs[key], rhs[key])
    elif isinstance(lhs, (list, tuple)):
        assert len(lhs) == len(rhs)
        for left, right in zip(lhs, rhs):
            assert_tree_equal(left, right)
    else:
        assert lhs == rhs


def test_opt_in_preserves_exact_cpu_learner_adam_rng_and_old_metrics():
    source = TinyTeacher()
    config = PPOConfig(update_epochs=2, minibatch_size=5, target_kl=1e6)
    models = [copy.deepcopy(source), copy.deepcopy(source)]
    optimizers = [torch.optim.Adam(model.parameters(), lr=config.learning_rate, eps=config.adam_eps) for model in models]
    # The second update starts with nonempty Adam state. Each iteration gets
    # a newly frozen buffer from the common current policy.
    for _ in range(2):
        batch = frozen_batch(models[0])
        original_batch = copy.deepcopy(batch)
        rng = torch.get_rng_state().clone()
        results, rng_after = [], []
        for enabled, model, optimizer in zip((False, True), models, optimizers):
            model.eval()
            torch.set_rng_state(rng)
            results.append(ppo_update(model, optimizer, batch, config, critic_diagnostics=enabled))
            rng_after.append(torch.get_rng_state().clone())
            assert not model.training
        assert_tree_equal(models[0].state_dict(), models[1].state_dict())
        assert_tree_equal(optimizers[0].state_dict(), optimizers[1].state_dict())
        assert torch.equal(rng_after[0], rng_after[1])
        assert {key: value for key, value in results[1].items() if key != "critic_diagnostics"} == results[0]
        assert "critic_diagnostics" not in results[0]
        for field in fields(batch):
            lhs, rhs = getattr(batch, field.name), getattr(original_batch, field.name)
            if lhs is not None:
                assert torch.equal(lhs, rhs)
    moments = results[1]["critic_diagnostics"]
    _, targets = compute_gae(batch.rewards, batch.values, batch.next_values,
                             batch.terminated, batch.truncated, config.gamma, config.gae_lambda)
    assert moments["pre_update"] == critic_statistics(targets.flatten(), batch.values.flatten())
    assert moments["pre_update"]["explained_variance"] == pytest.approx(results[1]["explained_variance"], abs=2e-7)
    with torch.no_grad():
        post = models[1](*(getattr(batch, key).flatten(0, 1) for key in
                          ("global_feats", "entity_feats", "entity_types", "entity_mask"))).values
    expected = critic_statistics(targets.flatten(), post)
    for key, value in expected.items():
        assert moments["post_update"][key] == pytest.approx(value, abs=2e-7)
    json.dumps(results[1], allow_nan=False)


def test_diagnostic_guard_failure_keeps_update_incomplete_with_actual_steps():
    model = TinyTeacher()
    batch = frozen_batch(model)
    config = PPOConfig(update_epochs=1, minibatch_size=5)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate, eps=config.adam_eps)
    progress = {}

    def guard():
        if progress.get("phase") == "critic_diagnostics":
            raise RuntimeError("diagnostic deadline")

    with pytest.raises(RuntimeError, match="diagnostic deadline"):
        ppo_update(model, optimizer, batch, config, critic_diagnostics=True,
                   check_guard=guard, progress=progress)
    assert progress["optimizer_steps"] == 3 and progress["in_update"] and not progress["complete"]


def test_diagnostic_flag_is_boolean_before_any_update():
    model = TinyTeacher()
    batch = frozen_batch(model)
    config = PPOConfig()
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate, eps=config.adam_eps)
    before = copy.deepcopy(model.state_dict())
    with pytest.raises(ValueError, match="flag must be boolean"):
        ppo_update(model, optimizer, batch, config, critic_diagnostics=1)
    assert optimizer.state == {}
    assert_tree_equal(before, model.state_dict())


@pytest.mark.skipif(not torch.backends.mps.is_available(), reason="MPS unavailable")
def test_mps_predictions_move_to_cpu_before_float64_and_restore_mps_rng():
    class MPSCritic(nn.Module):
        def __init__(self):
            super().__init__()
            self.offset = nn.Parameter(torch.tensor(1., device="mps"))

        def forward(self, tags):
            return SimpleNamespace(values=tags[:, 0] + self.offset + torch.rand_like(tags[:, 0]) * 0)

    model = MPSCritic()
    tags = torch.arange(7, dtype=torch.float32)
    cpu_rng, mps_rng = torch.get_rng_state().clone(), torch.mps.get_rng_state().clone()
    try:
        result = measure_critic_update(
            model, {"tags": tags[:, None]}, tags + 2, tags,
            device=torch.device("mps"), minibatch_size=3, predict=predict_tagged,
        )
        assert model.training
        assert result["statistics_device_dtype"] == "cpu_float64"
        assert result["mean_absolute_value_change"] == 1
        assert result["post_update"]["residual_mean"] == 1
        assert torch.equal(torch.get_rng_state(), cpu_rng)
        assert torch.equal(torch.mps.get_rng_state(), mps_rng)
    finally:
        torch.mps.set_rng_state(mps_rng)
