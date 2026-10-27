"""Direct critic measurements on fixed PPO targets, without optimizer effects.

Post-update fit is in-sample fit to self-bootstrapped GAE targets. It is not a
held-out value estimate or a pass/fail criterion. Moments use detached CPU
float64 vectors and population variance; learner targets keep their original
fixed reward scale (0.1 by default).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import math
from typing import Any

import torch
from torch import Tensor, nn


def _vector(value: Tensor, name: str) -> Tensor:
    if not isinstance(value, Tensor) or value.ndim != 1 or not value.is_floating_point() or value.numel() == 0:
        raise ValueError(f"Critic diagnostic {name} must be a nonempty floating vector")
    # Transfer first, then promote: never request an unsupported MPS float64
    # conversion on the source device.
    copied = value.detach().to(device="cpu").to(dtype=torch.float64).clone()
    if not bool(torch.isfinite(copied).all()):
        raise FloatingPointError(f"Nonfinite critic diagnostic {name}")
    return copied


def critic_statistics(targets: Tensor, predictions: Tensor) -> dict[str, Any]:
    """Measure target, prediction and target-minus-prediction moments directly."""
    target = _vector(targets, "targets")
    prediction = _vector(predictions, "predictions")
    if target.shape != prediction.shape:
        raise ValueError("Critic diagnostic target/prediction layouts differ")
    residual = target - prediction
    target_variance = float(target.var(unbiased=False).item())
    residual_variance = float(residual.var(unbiased=False).item())
    output = {
        "count": target.numel(),
        "target_mean": float(target.mean().item()),
        "target_variance": target_variance,
        "prediction_mean": float(prediction.mean().item()),
        "prediction_variance": float(prediction.var(unbiased=False).item()),
        "target_prediction_covariance": float(
            ((target - target.mean()) * (prediction - prediction.mean())).mean().item()),
        "residual_mean": float(residual.mean().item()),
        "residual_variance": residual_variance,
        "residual_mse": float(residual.square().mean().item()),
        "explained_variance": None if target_variance <= 1e-12 else 1 - residual_variance / target_variance,
    }
    if not all(value is None or math.isfinite(value) for value in output.values()):
        raise FloatingPointError("Nonfinite critic diagnostic moment")
    return output


def measure_critic_update(
    model: nn.Module, observations: Mapping[str, Tensor], targets: Tensor, rollout_values: Tensor,
    *, device: torch.device, minibatch_size: int,
    predict: Callable[[nn.Module, dict[str, Tensor], torch.device], Any],
    check_guard: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Compare frozen rollout predictions to post-update predictions in order.

    Model parameters and gradients are never written. Evaluation mode prevents
    ordinary dropout and BatchNorm training effects. Existing per-module modes,
    registered buffer values and Torch RNG states are restored even if a guard
    or prediction fails. Calls are bounded by the supplied minibatch size.
    """
    if type(minibatch_size) is not int or minibatch_size <= 0:
        raise ValueError("Critic diagnostic minibatch size must be positive")
    target = _vector(targets, "targets")
    old = _vector(rollout_values, "rollout values")
    if target.shape != old.shape or not observations:
        raise ValueError("Critic diagnostic frozen layouts differ")
    count = target.numel()
    if any(not isinstance(value, Tensor) or value.ndim == 0 or value.shape[0] != count
           for value in observations.values()):
        raise ValueError("Critic diagnostic observation order/layout differs")
    pre = critic_statistics(target, old)
    modes = [(module, module.training) for module in model.modules()]
    buffers = [(buffer, buffer.detach().clone()) for buffer in model.buffers()]
    cpu_rng = torch.get_rng_state()
    accelerator_rng = None
    if device.type == "mps":
        accelerator_rng = torch.mps.get_rng_state()
    elif device.type == "cuda":
        accelerator_rng = torch.cuda.get_rng_state(device)
    chunks = []
    try:
        model.eval()
        with torch.no_grad():
            for start in range(0, count, minibatch_size):
                if check_guard is not None:
                    check_guard()
                stop = min(count, start + minibatch_size)
                observation = {name: value[start:stop].to(device) for name, value in observations.items()}
                values = predict(model, observation, device).values
                if values.shape != (stop - start,):
                    raise ValueError("Critic diagnostic prediction layout differs")
                chunks.append(_vector(values, "post-update predictions"))
                if check_guard is not None:
                    check_guard()
    finally:
        with torch.no_grad():
            for buffer, saved in buffers:
                buffer.copy_(saved)
        for module, training in modes:
            module.training = training
        torch.set_rng_state(cpu_rng)
        if device.type == "mps" and accelerator_rng is not None:
            torch.mps.set_rng_state(accelerator_rng)
        elif device.type == "cuda" and accelerator_rng is not None:
            torch.cuda.set_rng_state(accelerator_rng, device)
    post_values = torch.cat(chunks)
    delta_values = post_values - old
    changes = {
        "mean_value_change": float(delta_values.mean().item()),
        "mean_absolute_value_change": float(delta_values.abs().mean().item()),
        "rms_value_change": float(delta_values.square().mean().sqrt().item()),
    }
    if not all(math.isfinite(value) for value in changes.values()):
        raise FloatingPointError("Nonfinite critic diagnostic value change")
    return {
        "version": "same_batch_critic_diagnostics_v1",
        "units": "learner_scaled_returns",
        "variance_ddof": 0,
        "statistics_device_dtype": "cpu_float64",
        "target_timing": "frozen_pre_update_GAE_targets",
        "pre_prediction_timing": "frozen_rollout_values",
        "post_prediction_timing": "post_update_eval_mode_same_observations",
        "fit_scope": "in_sample_self_bootstrapped_targets;not_held_out;no_pass_threshold",
        "pre_update": pre,
        "post_update": critic_statistics(target, post_values),
        **changes,
    }
