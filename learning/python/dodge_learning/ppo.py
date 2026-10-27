"""Bounded CPU PPO for the privileged-state teacher.

Rollouts retain one bounded window of encoded state and scalar transitions.
Death cuts value bootstrapping. A time-limit truncation bootstraps its final
observation but cuts the GAE trace before the next episode.
"""

from __future__ import annotations

import copy
import math
import time
from dataclasses import dataclass
from numbers import Real
from typing import Any, Callable

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from .teacher import (
    REQUIRED_NATIVE_FEATURE_SCHEMA_VERSION,
    StateActorCritic,
    batch_states,
    encode_state,
)
from .entity_teacher import (
    REQUIRED_PRIVILEGED_SCHEMA_VERSION,
    EntityActorCritic,
    batch_entities,
    encode_entities,
)


def _integer(value: Any, name: str, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")


def _real(value: Any, name: str, minimum: float, maximum: float, *, include_min: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be finite")
    if not (minimum <= value <= maximum if include_min else minimum < value <= maximum):
        bracket = "[" if include_min else "("
        raise ValueError(f"{name} must be in {bracket}{minimum}, {maximum}]")
    # Range checks precede float conversion: very large ints or Fractions can
    # raise OverflowError in math.isfinite even though they are valid Reals.
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class PPOConfig:
    total_frames: int = 10_000
    max_seconds: float = 1_800.0
    rollout_steps: int = 256
    epochs: int = 4
    minibatch_size: int = 64
    learning_rate: float = 3e-4
    reward_scale: float = 0.01
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_ratio: float = 0.2
    value_coef: float = 0.5
    critic_trunk_grad: bool = True
    entropy_coef: float = 0.01
    max_grad_norm: float = 0.5
    max_episode_frames: int = 18_000
    seed: int = 7
    train_seeds: tuple[int, ...] = tuple(range(1_000, 1_100))
    torch_threads: int = 1

    def __post_init__(self) -> None:
        for name, minimum, maximum in (
            ("total_frames", 1, 100_000),
            ("rollout_steps", 1, 4_096),
            ("epochs", 1, 16),
            ("minibatch_size", 1, 4_096),
            ("max_episode_frames", 1, 18_000),
            ("seed", 0, 0xFFFFFFFF),
            ("torch_threads", 1, 32),
        ):
            _integer(getattr(self, name), name, minimum, maximum)
        _real(self.max_seconds, "max_seconds", 0, 1_800)
        _real(self.learning_rate, "learning_rate", 0, 1)
        _real(self.reward_scale, "reward_scale", 0, 1)
        _real(self.gamma, "gamma", 0, 1)
        _real(self.gae_lambda, "gae_lambda", 0, 1, include_min=True)
        _real(self.clip_ratio, "clip_ratio", 0, 1)
        _real(self.value_coef, "value_coef", 0, 100)
        if type(self.critic_trunk_grad) is not bool:
            raise ValueError("critic_trunk_grad must be a boolean")
        _real(self.entropy_coef, "entropy_coef", 0, 100, include_min=True)
        _real(self.max_grad_norm, "max_grad_norm", 0, 1_000)
        if not isinstance(self.train_seeds, (tuple, list)) or not 1 <= len(self.train_seeds) <= 1_000:
            raise ValueError("train_seeds must contain from 1 to 1000 explicit episode seeds")
        seen = set()
        for seed in self.train_seeds:
            _integer(seed, "training seed", 0, 0xFFFFFFFF)
            normalized = 1 if seed == 0 else seed
            if normalized in seen:
                raise ValueError("train_seeds must not duplicate seeds or the equivalent 0/1 RNG streams")
            seen.add(normalized)
        object.__setattr__(self, "train_seeds", tuple(self.train_seeds))


@dataclass
class TrainingResult:
    model: nn.Module
    optimizer_state: dict[str, Any]
    metrics: dict[str, Any]
    config: PPOConfig


def compute_gae(
    rewards, values, next_values, terminated, truncated, *, gamma: float, gae_lambda: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return float32 advantages and value targets for explicit next observations.

    ``next_values[t]`` belongs to the observation immediately after transition
    ``t``, including the final observation of a truncated episode. A rollout
    boundary uses this value even when it is not an episode boundary.
    """
    _real(gamma, "gamma", 0, 1)
    _real(gae_lambda, "gae_lambda", 0, 1, include_min=True)
    try:
        numeric = [np.asarray(value, dtype=np.float64) for value in (rewards, values, next_values)]
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("GAE rewards and values must contain finite numbers") from error
    flags = [np.asarray(value) for value in (terminated, truncated)]
    shape = numeric[0].shape
    if len(shape) != 1 or any(value.shape != shape for value in [*numeric, *flags]):
        raise ValueError("GAE inputs must have matching one-dimensional shapes")
    if any(not np.isfinite(value).all() for value in numeric):
        raise ValueError("GAE rewards and values must be finite")
    if any(value.dtype.kind != "b" for value in flags):
        raise ValueError("GAE termination and truncation flags must be boolean")
    death, limit = (value.astype(np.bool_) for value in flags)
    if np.logical_and(death, limit).any():
        raise ValueError("death must take precedence over truncation")
    reward, value, following = numeric
    advantages = np.empty(shape, dtype=np.float64)
    trace = 0.0
    with np.errstate(over="raise", invalid="raise"):
        try:
            for index in range(len(reward) - 1, -1, -1):
                bootstrap = 0.0 if death[index] else following[index]
                delta = reward[index] + gamma * bootstrap - value[index]
                continuation = 0.0 if death[index] or limit[index] else 1.0
                trace = delta + gamma * gae_lambda * continuation * trace
                advantages[index] = trace
            returns = advantages + value
            advantages = advantages.astype(np.float32)
            returns = returns.astype(np.float32)
        except FloatingPointError as error:
            raise ValueError("GAE calculation produced nonfinite values") from error
    if not np.isfinite(advantages).all() or not np.isfinite(returns).all():
        raise ValueError("GAE calculation produced nonfinite values")
    return advantages, returns


def _encoded_observation(observation: dict[str, Any], provenance: dict[str, Any] | None, model: nn.Module):
    actual = observation["info"]["provenance"]
    if actual.get("feature_schema_version") != REQUIRED_NATIVE_FEATURE_SCHEMA_VERSION:
        raise RuntimeError("native feature schema does not match the teacher encoder")
    if provenance is not None and actual != provenance:
        raise RuntimeError("native provenance changed during teacher training")
    if isinstance(model, EntityActorCritic):
        if type(actual.get("privileged_schema_version")) is not int or actual["privileged_schema_version"] != REQUIRED_PRIVILEGED_SCHEMA_VERSION:
            raise RuntimeError("native privileged schema does not match the entity teacher encoder")
        return encode_entities(observation["privileged_state"])
    return encode_state(observation["train_only_state"])


def _forward(model: nn.Module, states, *, critic_trunk_grad: bool = True):
    if type(critic_trunk_grad) is not bool:
        raise ValueError("critic_trunk_grad must be a boolean")
    if not critic_trunk_grad and type(model) is not EntityActorCritic:
        raise ValueError("critic trunk detachment requires an EntityActorCritic")
    batch = batch_entities(states, device="cpu") if isinstance(model, EntityActorCritic) else batch_states(states, device="cpu")
    if critic_trunk_grad:
        logits, values = model(batch)
    else:
        output = model.distillation_outputs(batch)
        logits = output.logits
        # Keep the actor's transformer graph intact while the scalar critic
        # learns only its own head. Forward values remain numerically equal.
        values = model.value(output.latent.detach()).squeeze(-1)
    if logits.shape != (len(states), 9) or values.shape != (len(states),):
        raise RuntimeError("teacher must return logits [batch, 9] and values [batch]")
    if logits.device.type != "cpu" or values.device.type != "cpu":
        raise RuntimeError("the state teacher trainer supports CPU tensors only")
    if not bool(torch.isfinite(logits).all()) or not bool(torch.isfinite(values).all()):
        raise RuntimeError("teacher produced nonfinite logits or values")
    return logits, values


def train_teacher(
    config: PPOConfig, *, model: nn.Module | None = None,
    environment_factory: Callable[..., Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    architecture: str | None = None,
) -> TrainingResult:
    """Train within explicit frame/time limits, using only declared train seeds.

    A partial rollout is optimized when the frame limit is reached and time
    remains. The wall-time limit is checked before each native step and each
    optimizer step; exhausting it can leave collected samples unoptimized.
    Individual simulator, callback, or PyTorch operations cannot be preempted.
    """
    if not isinstance(config, PPOConfig):
        raise TypeError("config must be a PPOConfig")
    if architecture not in (None, "entity_transformer", "legacy_mlp"):
        raise ValueError("architecture must be entity_transformer or legacy_mlp")
    if not config.critic_trunk_grad and (
        architecture == "legacy_mlp" or (model is not None and type(model) is not EntityActorCritic)
    ):
        raise ValueError("critic trunk detachment requires an EntityActorCritic")
    if model is not None and architecture is not None:
        actual_architecture = "entity_transformer" if isinstance(model, EntityActorCritic) else "legacy_mlp"
        if actual_architecture != architecture:
            raise ValueError("model does not match the requested teacher architecture")
    started = time.monotonic()
    previous_threads = torch.get_num_threads()
    torch.set_num_threads(config.torch_threads)
    try:
        if model is None:
            with torch.random.fork_rng(devices=[]):
                torch.random.default_generator.manual_seed(config.seed)
                model = StateActorCritic() if architecture == "legacy_mlp" else EntityActorCritic()
        parameters = list(model.parameters())
        if not parameters or not any(parameter.requires_grad for parameter in parameters):
            raise ValueError("teacher must have trainable parameters")
        if any(tensor.device.type != "cpu" for tensor in [*parameters, *model.buffers()]):
            raise ValueError("teacher parameters and buffers must be on CPU")
        if any(not bool(torch.isfinite(parameter).all()) for parameter in parameters):
            raise ValueError("teacher parameters must be finite")
        optimizer = torch.optim.Adam(parameters, lr=config.learning_rate)
        permutation_rng = np.random.default_rng(config.seed)
        action_rng = torch.Generator(device="cpu").manual_seed(config.seed)
        model.train()
        # Only the two known stateless teacher architectures can reuse outputs.
        # Stochastic dropout and arbitrary caller-supplied modules must retain
        # their original forward-call behavior.
        cache_outputs = type(model) in (EntityActorCritic, StateActorCritic) and not any(
            (isinstance(module, nn.modules.dropout._DropoutNd) and module.p > 0)
            or (isinstance(module, nn.MultiheadAttention) and module.dropout > 0)
            for module in model.modules()
        )
        metrics: dict[str, Any] = {
            "architecture": "entity_transformer" if isinstance(model, EntityActorCritic) else "legacy_mlp",
            "reward_scale": config.reward_scale,
            "critic_trunk_grad": config.critic_trunk_grad,
            "episode_return_units": "native_survival_frames",
            "device": "cpu", "frames_collected": 0, "updates": 0, "optimizer_steps": 0,
            "samples_optimized": 0, "last_rollout_frames": 0, "unoptimized_frames": 0,
            "episodes_completed": 0, "terminal_episodes": 0, "truncated_episodes": 0,
            "completed_pattern_episodes": 0, "pattern_completions": 0,
            "episode_return_mean": None, "partial_episode_return": 0.0,
            "partial_episode_frames": 0, "episodes_started": 0,
            "stop_reason": "frame_budget", "elapsed_seconds": 0.0, "provenance": None,
            "policy_loss": None, "value_loss": None, "loss": None, "entropy": None,
            "approx_kl": None, "clip_fraction": None, "grad_norm": None,
        }
        return_total = 0.0
        if environment_factory is None:
            from .env import NativeEnvironment

            environment_factory = NativeEnvironment

        def expired() -> bool:
            return time.monotonic() - started >= config.max_seconds

        if expired():
            metrics["stop_reason"] = "time_budget"
            metrics["elapsed_seconds"] = max(0.0, time.monotonic() - started)
            return TrainingResult(model, optimizer.state_dict(), metrics, config)

        with environment_factory(
            seed=config.train_seeds[0], max_episode_frames=config.max_episode_frames,
            action_repeat=1, discount=config.gamma,
        ) as env:
            need_reset = True
            seed_index = 0
            observation = None
            encoded = None
            while metrics["frames_collected"] < config.total_frames:
                if expired():
                    metrics["stop_reason"] = "time_budget"
                    break
                states, actions, log_probs, rewards, values, next_values, deaths, limits = ([] for _ in range(8))
                # PPO updates change the policy between rollout windows. The
                # immutable encoded observation remains valid, but its logits
                # and value must be recomputed under the updated parameters.
                cached_forward = None
                cached_versions = None
                while len(states) < config.rollout_steps and metrics["frames_collected"] < config.total_frames:
                    if expired():
                        metrics["stop_reason"] = "time_budget"
                        break
                    if need_reset:
                        observation = env.reset(seed=config.train_seeds[seed_index % len(config.train_seeds)])
                        seed_index += 1
                        metrics["episodes_started"] += 1
                        if observation["info"]["terminated"] or observation["info"]["truncated"]:
                            raise RuntimeError("fresh reset returned a finished episode")
                        need_reset = False
                        encoded = None
                        cached_forward = None
                    if encoded is None:
                        encoded = _encoded_observation(observation, metrics["provenance"], model)
                    if metrics["provenance"] is None:
                        metrics["provenance"] = copy.deepcopy(observation["info"]["provenance"])
                    with torch.no_grad():
                        if cached_forward is not None and cached_versions == tuple(parameter._version for parameter in parameters):
                            logits, current_value = cached_forward
                        else:
                            logits, current_value = _forward(model, [encoded])
                        action = torch.multinomial(torch.softmax(logits, dim=-1), 1, generator=action_rng)
                        old_log_prob = F.log_softmax(logits, dim=-1).gather(1, action).item()
                    if expired():
                        metrics["stop_reason"] = "time_budget"
                        break
                    following = env.step(int(action.item()))
                    info = following["info"]
                    elapsed = info["elapsed_native_frames"]
                    if isinstance(elapsed, bool) or not isinstance(elapsed, int) or elapsed != 1:
                        raise RuntimeError("teacher PPO requires exactly one native frame per decision")
                    terminated, truncated = info["terminated"], info["truncated"]
                    if not isinstance(terminated, bool) or not isinstance(truncated, bool) or (terminated and truncated):
                        raise RuntimeError("invalid native episode flags; death must take precedence")
                    reward = float(following["reward_sum"])
                    if not math.isfinite(reward) or reward not in (0.0, 1.0):
                        raise RuntimeError("unexpected native survival reward")
                    following_encoded = _encoded_observation(following, metrics["provenance"], model)
                    with torch.no_grad():
                        following_forward = None if terminated else _forward(model, [following_encoded])
                        next_value = 0.0 if terminated else float(following_forward[1].item())
                    states.append(encoded)
                    actions.append(int(action.item()))
                    log_probs.append(old_log_prob)
                    # Scale only optimization targets. Native rewards and
                    # episode-return diagnostics retain raw survival frames.
                    rewards.append(reward * config.reward_scale)
                    values.append(float(current_value.item()))
                    next_values.append(next_value)
                    deaths.append(terminated)
                    limits.append(truncated)
                    metrics["frames_collected"] += 1
                    metrics["partial_episode_return"] += reward
                    metrics["partial_episode_frames"] += 1
                    if info["episode_frames"] != metrics["partial_episode_frames"]:
                        raise RuntimeError("native episode frame count disagrees with the PPO rollout")
                    if info["episode_frames"] >= config.max_episode_frames and not (terminated or truncated):
                        raise RuntimeError("native environment exceeded the episode frame limit")
                    observation = following
                    encoded = following_encoded
                    cached_forward = (
                        tuple(tensor.detach() for tensor in following_forward)
                        if cache_outputs and following_forward is not None and not truncated else None
                    )
                    cached_versions = tuple(parameter._version for parameter in parameters) if cached_forward is not None else None
                    if terminated or truncated:
                        metrics["episodes_completed"] += 1
                        metrics["terminal_episodes"] += int(terminated)
                        metrics["truncated_episodes"] += int(truncated)
                        completions = info.get("pattern_completions", 0)
                        if isinstance(completions, bool) or not isinstance(completions, int) or not 0 <= completions <= info["episode_frames"]:
                            raise RuntimeError("invalid native pattern completion count")
                        metrics["completed_pattern_episodes"] += int(completions > 0)
                        metrics["pattern_completions"] += completions
                        return_total += metrics["partial_episode_return"]
                        metrics["episode_return_mean"] = return_total / metrics["episodes_completed"]
                        metrics["partial_episode_return"] = 0.0
                        metrics["partial_episode_frames"] = 0
                        need_reset = True
                count = len(states)
                if not count:
                    break
                metrics["last_rollout_frames"] = count
                advantages, returns = compute_gae(
                    rewards, values, next_values, deaths, limits,
                    gamma=config.gamma, gae_lambda=config.gae_lambda,
                )
                advantage_tensor = torch.from_numpy(advantages)
                advantage_tensor = (advantage_tensor - advantage_tensor.mean()) / (
                    advantage_tensor.std(unbiased=False) + 1e-8
                )
                return_tensor = torch.from_numpy(returns)
                action_tensor = torch.tensor(actions, dtype=torch.long)
                old_log_prob_tensor = torch.tensor(log_probs, dtype=torch.float32)
                accumulated = {name: 0.0 for name in (
                    "policy_loss", "value_loss", "loss", "entropy", "approx_kl", "clip_fraction", "grad_norm",
                )}
                minibatches = 0
                samples_seen = set()
                for _ in range(config.epochs):
                    if expired():
                        metrics["stop_reason"] = "time_budget"
                        break
                    permutation = permutation_rng.permutation(count)
                    for offset in range(0, count, config.minibatch_size):
                        if expired():
                            metrics["stop_reason"] = "time_budget"
                            break
                        indices = permutation[offset:offset + config.minibatch_size]
                        selected_states = [states[int(index)] for index in indices]
                        if config.critic_trunk_grad:
                            batch_logits, predicted_values = _forward(model, selected_states)
                        else:
                            batch_logits, predicted_values = _forward(
                                model, selected_states, critic_trunk_grad=False,
                            )
                        distribution = torch.distributions.Categorical(logits=batch_logits)
                        new_log_prob = distribution.log_prob(action_tensor[indices])
                        log_ratio = new_log_prob - old_log_prob_tensor[indices]
                        ratio = log_ratio.exp()
                        selected_advantage = advantage_tensor[indices]
                        policy_loss = -torch.minimum(
                            ratio * selected_advantage,
                            ratio.clamp(1 - config.clip_ratio, 1 + config.clip_ratio) * selected_advantage,
                        ).mean()
                        value_loss = F.mse_loss(predicted_values, return_tensor[indices])
                        entropy = distribution.entropy().mean()
                        loss = policy_loss + config.value_coef * value_loss - config.entropy_coef * entropy
                        if not bool(torch.isfinite(loss)):
                            raise RuntimeError("PPO loss is nonfinite")
                        optimizer.zero_grad(set_to_none=True)
                        loss.backward()
                        grad_norm = nn.utils.clip_grad_norm_(parameters, config.max_grad_norm, error_if_nonfinite=True)
                        if expired():
                            optimizer.zero_grad(set_to_none=True)
                            metrics["stop_reason"] = "time_budget"
                            break
                        optimizer.step()
                        if any(not bool(torch.isfinite(parameter).all()) for parameter in parameters):
                            raise RuntimeError("PPO produced nonfinite teacher parameters")
                        with torch.no_grad():
                            measured = {
                                "policy_loss": policy_loss, "value_loss": value_loss,
                                "loss": loss, "entropy": entropy, "grad_norm": grad_norm,
                                "approx_kl": ((ratio - 1) - log_ratio).mean(),
                                "clip_fraction": ((ratio - 1).abs() > config.clip_ratio).float().mean(),
                            }
                        for name, tensor in measured.items():
                            number = float(tensor.detach().item())
                            if not math.isfinite(number):
                                raise RuntimeError(f"PPO {name} is nonfinite")
                            accumulated[name] += number
                        minibatches += 1
                        metrics["optimizer_steps"] += 1
                        metrics["samples_optimized"] += len(indices)
                        samples_seen.update(int(index) for index in indices)
                    if metrics["stop_reason"] == "time_budget":
                        break
                metrics["unoptimized_frames"] += count - len(samples_seen)
                if minibatches:
                    metrics["updates"] += 1
                    for name, total in accumulated.items():
                        metrics[name] = total / minibatches
                    metrics["elapsed_seconds"] = max(0.0, time.monotonic() - started)
                    if progress_callback is not None:
                        progress_callback(copy.deepcopy(metrics))
                if metrics["stop_reason"] == "time_budget":
                    break
        metrics["elapsed_seconds"] = max(0.0, time.monotonic() - started)
        return TrainingResult(model, optimizer.state_dict(), metrics, config)
    finally:
        torch.set_num_threads(previous_threads)
