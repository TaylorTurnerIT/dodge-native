"""On-policy PPO for the privileged Dodge teacher.

Environment rewards remain unscaled. Only the learner multiplies them by the
fixed ``reward_scale``. Value loss is ``0.5 * mean((value - GAE_return)**2)``;
the optimized loss is policy_loss + vf_coef * value_loss - ent_coef * entropy.
There is no value clipping, running normalization, or auxiliary policy target.

Rollouts own CPU tensors. Minibatches move to the model's device when used, so
holding a rollout does not require retaining inference or attention graphs.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
import math
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
import torch
from torch import Tensor, nn
from torch.distributions import Categorical

__all__ = [
    "PPOConfig", "RolloutBatch", "RolloutCollection", "compute_gae",
    "collect_rollout", "ppo_update",
]

_OBSERVATIONS = {
    "global_feats": ((1, 14), torch.float32),
    "entity_feats": ((80, 16), torch.float32),
    "entity_types": ((80,), torch.int64),
    "entity_mask": ((80,), torch.bool),
}
_RESERVED_RANGES = (
    (0xB0000000, 0xB00003E7),
    (0xD0000000, 0xD000007F),
    (0xE0000000, 0xE00003E7),
)
Guard = Callable[[], None] | None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _guard(check_guard: Guard) -> None:
    if check_guard is not None:
        check_guard()


def _finite(value: Tensor, name: str) -> None:
    if not bool(torch.isfinite(value).all()):
        raise FloatingPointError(f"Nonfinite {name}")


@dataclass(frozen=True)
class PPOConfig:
    gamma: float = 0.995
    gae_lambda: float = 0.95
    learning_rate: float = 3e-4
    adam_eps: float = 1e-5
    clip_coef: float = 0.2
    vf_coef: float = 0.5
    ent_coef: float = 0.01
    max_grad_norm: float = 0.5
    update_epochs: int = 4
    minibatch_size: int = 512
    target_kl: float = 0.03
    reward_scale: float = 0.1

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            _require(isinstance(value, (int, float)) and not isinstance(value, bool)
                     and math.isfinite(value), f"Invalid PPO setting {name}")
        _require(0 <= self.gamma <= 1 and 0 <= self.gae_lambda <= 1,
                 "Gamma and GAE lambda must be in [0,1]")
        _require(self.learning_rate > 0 and self.adam_eps > 0,
                 "Adam learning rate and epsilon must be positive")
        _require(0 < self.clip_coef < 1 and self.max_grad_norm > 0,
                 "Clip coefficient and gradient cap are invalid")
        _require(self.vf_coef >= 0 and self.ent_coef >= 0 and self.target_kl >= 0,
                 "Loss coefficients and KL threshold must be nonnegative")
        _require(self.reward_scale > 0, "Reward scale must be positive")
        for name in ("update_epochs", "minibatch_size"):
            _require(isinstance(getattr(self, name), int) and getattr(self, name) > 0,
                     f"{name} must be a positive integer")

    def description(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "value_loss": "0.5 * mean((new_value - GAE_return) ** 2)",
            "total_loss": "policy_loss + vf_coef * value_loss - ent_coef * entropy",
            "value_clipping": False,
            "advantage_normalization": "per_minibatch_population_std_plus_1e-8",
            "running_observation_or_reward_normalization": False,
            "approximate_kl": "mean(exp(logratio) - 1 - logratio)",
            "kl_stop": "full_rollout_at_epoch_end; stop_additional_epochs",
            "rollout_storage": "independently_owned_CPU_tensors",
            "raw_step_reward_abs_tolerance": 1e-5,
            "episode_objective_abs_tolerance": 1e-9,
        }


@dataclass
class RolloutBatch:
    global_feats: Tensor
    entity_feats: Tensor
    entity_types: Tensor
    entity_mask: Tensor
    actions: Tensor
    old_log_probs: Tensor
    values: Tensor
    rewards: Tensor
    next_values: Tensor
    terminated: Tensor
    truncated: Tensor
    raw_rewards: Tensor | None = None
    score_delta_raw_fixed: Tensor | None = None
    alive_raw_frames: Tensor | None = None
    elapsed_raw_frames: Tensor | None = None

    @property
    def shape(self) -> tuple[int, int]:
        return tuple(self.actions.shape)

    @property
    def transitions(self) -> int:
        return self.actions.numel()


@dataclass
class RolloutCollection:
    batch: RolloutBatch
    observations: dict[str, Any]
    completed_episodes: list[dict[str, Any]]
    reset_info: list[dict[str, Any]]
    batch_info: dict[str, Any]


@torch.no_grad()
def compute_gae(
    rewards: Tensor, values: Tensor, next_values: Tensor,
    terminated: Tensor, truncated: Tensor,
    gamma: float = 0.995, gae_lambda: float = 0.95,
) -> tuple[Tensor, Tensor]:
    """Bootstrap alive truncations, but stop the recurrence at either boundary."""
    _require(rewards.ndim == 2 and min(rewards.shape) > 0,
             "GAE expects nonempty [T,N] tensors")
    _require(math.isfinite(gamma) and math.isfinite(gae_lambda)
             and 0 <= gamma <= 1 and 0 <= gae_lambda <= 1,
             "Invalid GAE discount or lambda")
    for name, value in (("rewards", rewards), ("values", values), ("next_values", next_values)):
        _require(value.shape == rewards.shape and value.dtype == rewards.dtype
                 and value.device == rewards.device and value.is_floating_point(),
                 f"GAE {name} shape, dtype, or device differs")
        _finite(value, f"GAE {name}")
    for name, value in (("terminated", terminated), ("truncated", truncated)):
        _require(value.shape == rewards.shape and value.dtype == torch.bool
                 and value.device == rewards.device, f"GAE {name} layout differs")
    _require(not bool((terminated & truncated).any()), "Termination and truncation overlap")
    advantages = torch.empty_like(rewards)
    carry = torch.zeros_like(rewards[0])
    for step in range(rewards.shape[0] - 1, -1, -1):
        bootstrap = (~terminated[step]).to(rewards.dtype)
        continuation = (~(terminated[step] | truncated[step])).to(rewards.dtype)
        delta = rewards[step] + gamma * next_values[step] * bootstrap - values[step]
        carry = delta + gamma * gae_lambda * continuation * carry
        advantages[step].copy_(carry)
    returns = advantages + values
    _finite(advantages, "GAE advantages")
    _finite(returns, "GAE returns")
    return advantages, returns


def _observation_tensors(observation: Mapping[str, Any], batch_size: int | None = None) -> dict[str, Tensor]:
    """Copy only allowlisted neural arrays; diagnostic metadata never enters the model."""
    output = {}
    for name, (suffix, dtype) in _OBSERVATIONS.items():
        value = torch.as_tensor(observation[name])
        if batch_size is None:
            _require(value.ndim > 0, "Observation is missing its batch dimension")
            batch_size = value.shape[0]
        _require(batch_size > 0 and tuple(value.shape) == (batch_size, *suffix)
                 and value.dtype == dtype, f"Wrong observation layout for {name}")
        if value.is_floating_point():
            _finite(value, name)
        output[name] = value.detach().to(device="cpu").clone()
    return output


def _model_output(model: nn.Module, observation: dict[str, Tensor], device: torch.device) -> Any:
    output = model(*(observation[name].to(device) for name in _OBSERVATIONS))
    batch_size = observation["global_feats"].shape[0]
    _require(output.logits.shape == (batch_size, 9) and output.values.shape == (batch_size,),
             "Teacher output shape differs from the actor/critic contract")
    _finite(output.logits, "actor logits")
    _finite(output.values, "critic values")
    return output


def _integer_vector(value: Any, batch_size: int, name: str) -> np.ndarray:
    array = np.asarray(value)
    _require(array.shape == (batch_size,) and array.dtype.kind in "iu", f"Invalid {name}")
    return array


def _boolean_vector(value: Any, batch_size: int, name: str) -> np.ndarray:
    array = np.asarray(value)
    _require(array.shape == (batch_size,) and array.dtype == np.bool_, f"Invalid {name}")
    return array


def _audit_episode(info: Mapping[str, Any], cap: int) -> None:
    _require(not info["seed"]["evaluation"], "Evaluation seed entered PPO collection")
    actual_seed = info["seed"]["actual_seed"]
    _require(0 <= actual_seed <= 0xFFFFFFFF and all(
        not low <= actual_seed <= high for low, high in _RESERVED_RANGES
    ), "Reserved or invalid seed entered PPO collection")
    _require(info["startup_frames"] == 13
             and 0 <= info["alive_frames"] <= info["gameplay_frames"] <= cap,
             "Episode startup or raw-frame accounting differs")
    _require(not (info["terminated"] and info["truncated"]), "Both episode boundary flags set")
    _require(info["bootstrap"] == (not info["terminated"]), "Wrong episode bootstrap flag")
    _require(info["score_raw_fixed"] == info["score_delta_sum_raw_fixed"],
             "Cumulative score delta differs from native score")
    expected = info["score_raw_fixed"] / 65536 + info["alive_frames"] / 100 - 5 * info["terminated"]
    _require(math.isfinite(info["objective_return"]) and math.isclose(
        info["objective_return"], expected, rel_tol=0, abs_tol=1e-9),
             "Unscaled episode objective differs")


def _audit_step(result: Mapping[str, Any], batch_size: int, cap: int) -> dict[str, np.ndarray]:
    terminated = _boolean_vector(result["terminated"], batch_size, "terminated")
    truncated = _boolean_vector(result["truncated"], batch_size, "truncated")
    score = _integer_vector(result["score_delta_raw_fixed"], batch_size, "score_delta_raw_fixed")
    alive = _integer_vector(result["alive_raw_frames"], batch_size, "alive_raw_frames")
    elapsed = _integer_vector(result["elapsed_raw_frames"], batch_size, "elapsed_raw_frames")
    _require(not bool((terminated & truncated).any()), "Both step boundary flags set")
    _require(bool((score >= 0).all()) and bool(((elapsed >= 1) & (elapsed <= 4)).all())
             and bool((alive == elapsed - terminated.astype(np.int64)).all()),
             "Raw score, alive, or action-repeat accounting differs")
    rewards = np.asarray(result["rewards"])
    expected = score.astype(np.float64) / 65536 + alive.astype(np.float64) / 100 - 5 * terminated
    _require(rewards.shape == (batch_size,) and rewards.dtype.kind == "f"
             and bool(np.isfinite(rewards).all())
             and bool(np.allclose(rewards, expected, rtol=0, atol=1e-5)),
             "Unscaled step reward differs from score + alive - one death penalty")
    _require(len(result["info"]) == batch_size, "Step episode metadata is incomplete")
    for index, info in enumerate(result["info"]):
        _audit_episode(info, cap)
        _require(info["terminated"] == bool(terminated[index])
                 and info["truncated"] == bool(truncated[index]),
                 "Step and episode boundary flags differ")
    return dict(terminated=terminated, truncated=truncated, raw_rewards=rewards,
                score_delta_raw_fixed=score,
                alive_raw_frames=alive, elapsed_raw_frames=elapsed)


def collect_rollout(
    model: nn.Module, env: Any, rollout_steps: int, device: str | torch.device,
    *, observation: Mapping[str, Any] | None = None,
    config: PPOConfig | None = None, check_guard: Guard = None,
) -> RolloutCollection:
    """Collect one fixed on-policy buffer; failures never imply environment rollback."""
    config = PPOConfig() if config is None else config
    _require(isinstance(rollout_steps, int) and not isinstance(rollout_steps, bool)
             and rollout_steps > 0, "rollout_steps must be a positive integer")
    _guard(check_guard)
    metadata = env.batch_info()
    _require(metadata["seed_mode"]["mode"] == "training", "PPO requires a training seed stream")
    ranges = metadata["effective_excluded_seed_ranges"]
    _require(all(any(low <= a and high >= b for low, high in ranges)
                 for a, b in _RESERVED_RANGES), "Training stream must exclude B, D, and E before construction")
    _require(metadata["action_repeat"] == 4, "This PPO configuration requires K=4")
    batch_size, cap = metadata["batch_size"], metadata["raw_frame_cap"]
    _require(batch_size > 0 and cap > 0, "Invalid environment batch or cap")
    episode_info = copy.deepcopy(env.episode_info())
    _require(len(episode_info) == batch_size, "Initial episode metadata is incomplete")
    for index, info in enumerate(episode_info):
        _audit_episode(info, cap)
        _require(info["seed"]["slot"] == index
                 and not info["terminated"] and not info["truncated"],
                 "Collection must start with active, aligned environment slots")
    current = env.observations() if observation is None else observation
    first = _observation_tensors(current, batch_size)
    storage = {
        name: torch.empty((rollout_steps, batch_size, *suffix), dtype=dtype)
        for name, (suffix, dtype) in _OBSERVATIONS.items()
    }
    for name, dtype in (("actions", torch.int64), ("old_log_probs", torch.float32),
                        ("values", torch.float32), ("rewards", torch.float32),
                        ("next_values", torch.float32), ("terminated", torch.bool),
                        ("truncated", torch.bool), ("raw_rewards", torch.float32),
                        ("score_delta_raw_fixed", torch.int64),
                        ("alive_raw_frames", torch.int64), ("elapsed_raw_frames", torch.int64)):
        storage[name] = torch.empty((rollout_steps, batch_size), dtype=dtype)
    completed_episodes, reset_info = [], []
    device = torch.device(device)
    was_training = model.training
    model.eval()
    try:
        with torch.no_grad():
            for step in range(rollout_steps):
                _guard(check_guard)
                tensors = first if step == 0 else _observation_tensors(current, batch_size)
                for name in _OBSERVATIONS:
                    storage[name][step].copy_(tensors[name])
                output = _model_output(model, tensors, device)
                policy = Categorical(logits=output.logits)
                actions = policy.sample()
                storage["actions"][step].copy_(actions.cpu())
                storage["old_log_probs"][step].copy_(policy.log_prob(actions).cpu())
                storage["values"][step].copy_(output.values.cpu())
                _guard(check_guard)
                result = env.step(actions.detach().cpu().numpy().copy())
                _guard(check_guard)
                audited = _audit_step(result, batch_size, cap)
                for index, info in enumerate(result["info"]):
                    previous = episode_info[index]
                    _require(info["seed"] == previous["seed"], "Episode identity changed without reset")
                    _require(info["score_raw_fixed"] == previous["score_raw_fixed"]
                             + int(audited["score_delta_raw_fixed"][index])
                             and info["alive_frames"] == previous["alive_frames"]
                             + int(audited["alive_raw_frames"][index])
                             and info["gameplay_frames"] == previous["gameplay_frames"]
                             + int(audited["elapsed_raw_frames"][index]),
                             "Cumulative episode score/alive/frame counters differ from executed steps")
                episode_info = copy.deepcopy(result["info"])
                for name, array in audited.items():
                    storage[name][step].copy_(torch.as_tensor(array))
                storage["rewards"][step].copy_(storage["raw_rewards"][step] * config.reward_scale)
                # Read actual final observations before reset_done mutates the environment.
                final = _observation_tensors(result["observations"], batch_size)
                final_values = _model_output(model, final, device).values.cpu()
                storage["next_values"][step].copy_(torch.where(
                    storage["terminated"][step], torch.zeros_like(final_values), final_values))
                _guard(check_guard)
                ended = np.flatnonzero(audited["terminated"] | audited["truncated"]).tolist()
                for index in ended:
                    completed_episodes.append({**copy.deepcopy(result["info"][index]), "rollout_step": step})
                if ended:
                    ended_info = {index: copy.deepcopy(episode_info[index]) for index in ended}
                    _guard(check_guard)
                    reset = env.reset_done(ended)
                    _guard(check_guard)
                    _require(len(reset["info"]) == len(ended), "Reset metadata is incomplete")
                    for index, info in zip(ended, reset["info"], strict=True):
                        _audit_episode(info, cap)
                        _require(info["seed"]["slot"] == index
                                 and info["seed"]["episode"] == ended_info[index]["seed"]["episode"] + 1,
                                 "Reset did not construct the next episode in its slot")
                        _require(info["score_raw_fixed"] == info["alive_frames"] == info["gameplay_frames"] == 0
                                 and not info["terminated"] and not info["truncated"],
                                 "Reset did not clear episode counters and boundary flags")
                        episode_info[index] = copy.deepcopy(info)
                    reset_info.append({"rollout_step": step, "indices": ended,
                                       "info": copy.deepcopy(reset["info"])})
                    current = env.observations()
                else:
                    current = result["observations"]
    finally:
        model.train(was_training)
    _guard(check_guard)
    return RolloutCollection(RolloutBatch(**storage), copy.deepcopy(dict(current)),
                             completed_episodes, reset_info, copy.deepcopy(env.batch_info()))


def _validate_batch(batch: RolloutBatch) -> tuple[int, int]:
    _require(batch.actions.ndim == 2 and min(batch.actions.shape) > 0,
             "PPO batch must have nonempty [T,N] dimensions")
    shape = tuple(batch.actions.shape)
    for name, (suffix, dtype) in _OBSERVATIONS.items():
        value = getattr(batch, name)
        _require(tuple(value.shape) == (*shape, *suffix) and value.dtype == dtype,
                 f"Wrong rollout observation layout for {name}")
        if value.is_floating_point():
            _finite(value, name)
    for name in ("old_log_probs", "values", "rewards", "next_values"):
        value = getattr(batch, name)
        _require(tuple(value.shape) == shape and value.is_floating_point(), f"Invalid rollout {name}")
        _finite(value, name)
    _require(batch.actions.dtype == torch.int64 and bool(((batch.actions >= 0) & (batch.actions < 9)).all()),
             "Rollout action IDs differ from the nine-action contract")
    for name in ("terminated", "truncated"):
        value = getattr(batch, name)
        _require(tuple(value.shape) == shape and value.dtype == torch.bool, f"Invalid rollout {name}")
    _require(not bool((batch.terminated & batch.truncated).any()), "Both rollout boundary flags set")
    _require(all(not getattr(batch, name).requires_grad for name in (
        *_OBSERVATIONS, "actions", "old_log_probs", "values", "rewards", "next_values")),
        "PPO rollout tensors must be detached from the old policy")
    return shape


def _gradient_norm(parameters: list[nn.Parameter]) -> float:
    norms = [parameter.grad.detach().norm(2) for parameter in parameters if parameter.grad is not None]
    if not norms:
        return 0.0
    return float(torch.stack(norms).norm(2).item())


def ppo_update(
    model: nn.Module, optimizer: torch.optim.Optimizer, batch: RolloutBatch,
    config: PPOConfig, *, check_guard: Guard = None, progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Optimize a frozen on-policy buffer, stopping additional epochs on epoch-end KL."""
    if progress is not None:
        progress.update(state="in_update", in_update=True, complete=False,
                        phase="validation", epoch=0, minibatch=0,
                        optimizer_steps=0, epochs_completed=0)
    _guard(check_guard)
    shape = _validate_batch(batch)
    raw_fields = (batch.raw_rewards, batch.score_delta_raw_fixed,
                  batch.alive_raw_frames, batch.elapsed_raw_frames)
    if any(value is not None for value in raw_fields):
        _require(all(value is not None for value in raw_fields), "Raw rollout audit fields must be complete")
        for name, dtype in (("raw_rewards", torch.float32), ("score_delta_raw_fixed", torch.int64),
                            ("alive_raw_frames", torch.int64), ("elapsed_raw_frames", torch.int64)):
            value = getattr(batch, name)
            _require(tuple(value.shape) == shape and value.dtype == dtype, f"Invalid rollout {name}")
        raw = batch.raw_rewards.detach().cpu()
        score = batch.score_delta_raw_fixed.detach().cpu()
        alive = batch.alive_raw_frames.detach().cpu()
        elapsed = batch.elapsed_raw_frames.detach().cpu()
        terminated = batch.terminated.detach().cpu()
        expected = score.double() / 65536 + alive.double() / 100 - 5 * terminated
        _require(bool((score >= 0).all()) and bool(((elapsed >= 1) & (elapsed <= 4)).all())
                 and bool((alive == elapsed - terminated.long()).all())
                 and bool(torch.allclose(raw.double(), expected, rtol=0, atol=1e-5)),
                 "Raw rollout reward/counter identity differs")
        _require(torch.equal(batch.rewards.detach().cpu(), raw * config.reward_scale),
                 "Learner reward scale differs from raw float32 reward multiplication")
    parameters = [p for p in model.parameters() if p.requires_grad]
    _require(bool(parameters), "PPO model has no trainable parameters")
    device = parameters[0].device
    _require(all(p.device == device for p in parameters), "Model spans multiple devices")
    optimized = [p for group in optimizer.param_groups for p in group["params"]]
    _require(len(optimized) == len(parameters) and {id(p) for p in optimized} == {id(p) for p in parameters},
             "Optimizer must own every trainable model parameter exactly once")
    advantages, returns = compute_gae(batch.rewards, batch.values, batch.next_values,
                                      batch.terminated, batch.truncated,
                                      config.gamma, config.gae_lambda)
    flat = {name: getattr(batch, name).detach().flatten(0, 1) for name in _OBSERVATIONS}
    actions = batch.actions.detach().flatten()
    old_log_probs = batch.old_log_probs.detach().flatten()
    advantages, returns = advantages.flatten(), returns.flatten()
    count = shape[0] * shape[1]
    actor_parameters = list(model.actor_head.parameters()) if hasattr(model, "actor_head") else []
    critic_parameters = list(model.critic_head.parameters()) if hasattr(model, "critic_head") else []
    head_ids = {id(p) for p in actor_parameters + critic_parameters}
    trunk_parameters = [p for p in parameters if id(p) not in head_ids]
    sums = {key: 0.0 for key in ("loss", "policy_loss", "value_loss", "entropy", "clip_fraction",
                                 "grad_norm", "actor_grad_norm", "critic_grad_norm", "trunk_grad_norm")}
    weighted_samples = optimizer_steps = epochs_completed = 0
    epoch_kls = []
    early_stop = False
    was_training = model.training
    model.train()
    try:
        for _epoch in range(config.update_epochs):
            if progress is not None:
                progress.update(epoch=_epoch, phase="optimization")
            _guard(check_guard)
            order = torch.randperm(count, device="cpu")
            for start in range(0, count, config.minibatch_size):
                if progress is not None:
                    progress.update(minibatch=start // config.minibatch_size)
                _guard(check_guard)
                indices = order[start:start + config.minibatch_size]
                observation = {name: value[indices.to(value.device)].to(device) for name, value in flat.items()}
                selected_actions = actions[indices.to(actions.device)].to(device)
                selected_old = old_log_probs[indices.to(old_log_probs.device)].to(device)
                selected_returns = returns[indices.to(returns.device)].to(device)
                selected_advantages = advantages[indices.to(advantages.device)].to(device)
                selected_advantages = (selected_advantages - selected_advantages.mean()) / (
                    selected_advantages.std(unbiased=False) + 1e-8)
                optimizer.zero_grad(set_to_none=True)
                output = _model_output(model, observation, device)
                policy = Categorical(logits=output.logits)
                logratio = policy.log_prob(selected_actions) - selected_old
                ratio = logratio.exp()
                _finite(ratio, "policy probability ratio")
                unclipped = -selected_advantages * ratio
                clipped = -selected_advantages * ratio.clamp(1 - config.clip_coef, 1 + config.clip_coef)
                policy_loss = torch.maximum(unclipped, clipped).mean()
                value_loss = 0.5 * (output.values - selected_returns).square().mean()
                entropy = policy.entropy().mean()
                loss = policy_loss + config.vf_coef * value_loss - config.ent_coef * entropy
                _finite(loss, "PPO loss")
                _guard(check_guard)
                loss.backward()
                for parameter in parameters:
                    if parameter.grad is not None:
                        _finite(parameter.grad, "PPO gradient")
                gradients = {
                    "actor_grad_norm": _gradient_norm(actor_parameters),
                    "critic_grad_norm": _gradient_norm(critic_parameters),
                    "trunk_grad_norm": _gradient_norm(trunk_parameters),
                }
                grad_norm = nn.utils.clip_grad_norm_(parameters, config.max_grad_norm, error_if_nonfinite=True)
                _guard(check_guard)
                optimizer.step()
                optimizer_steps += 1
                if progress is not None:
                    progress.update(optimizer_steps=optimizer_steps)
                _guard(check_guard)
                size = len(indices)
                values = {
                    "loss": float(loss.detach().item()), "policy_loss": float(policy_loss.detach().item()),
                    "value_loss": float(value_loss.detach().item()), "entropy": float(entropy.detach().item()),
                    "clip_fraction": float(((ratio - 1).abs() > config.clip_coef).float().mean().item()),
                    "grad_norm": float(grad_norm.item()), **gradients,
                }
                _require(all(math.isfinite(v) for v in values.values()), "Nonfinite PPO metric")
                for name, value in values.items():
                    sums[name] += size * value
                weighted_samples += size
            epochs_completed += 1
            if progress is not None:
                progress.update(epochs_completed=epochs_completed, phase="epoch_kl")
            # Measure the policy at the end of the epoch, rather than averaging
            # stale ratios produced before successive minibatch updates.
            kl_total = 0.0
            with torch.no_grad():
                for start in range(0, count, config.minibatch_size):
                    _guard(check_guard)
                    stop = min(count, start + config.minibatch_size)
                    observation = {name: value[start:stop].to(device) for name, value in flat.items()}
                    output = _model_output(model, observation, device)
                    new_log_probs = Categorical(logits=output.logits).log_prob(actions[start:stop].to(device))
                    logratio = new_log_probs - old_log_probs[start:stop].to(device)
                    kl = logratio.exp() - 1 - logratio
                    _finite(kl, "epoch approximate KL")
                    kl_total += float(kl.sum().item())
                    _guard(check_guard)
            epoch_kl = max(0.0, kl_total / count)
            epoch_kls.append(epoch_kl)
            if epoch_kl > config.target_kl:
                early_stop = True
                break
    finally:
        model.train(was_training)
    _guard(check_guard)
    _require(optimizer_steps > 0, "PPO update completed no optimizer steps")
    # Explained variance uses the rollout's frozen predictions and GAE targets.
    target_variance = float(returns.var(unbiased=False).item())
    residual_variance = float((returns - batch.values.detach().flatten()).var(unbiased=False).item())
    explained_variance = None if target_variance <= 1e-12 else 1 - residual_variance / target_variance
    metrics = {
        **{name: value / weighted_samples for name, value in sums.items()},
        "optimizer_steps": optimizer_steps, "epochs_completed": epochs_completed,
        "transitions": count, "approx_kl": epoch_kls[-1], "epoch_approx_kls": epoch_kls,
        "early_stop_kl": early_stop, "explained_variance": explained_variance,
        "finite": True, "value_loss_formula": "0.5 * mean((new_value - GAE_return) ** 2)",
        "head_gradient_metrics_available": bool(actor_parameters and critic_parameters),
    }
    _require(explained_variance is None or math.isfinite(explained_variance), "Nonfinite explained variance")
    if progress is not None:
        progress.update(state="complete", in_update=False, complete=True,
                        phase="complete", optimizer_steps=optimizer_steps,
                        epochs_completed=epochs_completed)
    return metrics
