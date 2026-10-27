"""Bounded synthetic forward/backward diagnostic for the optional vision model.

This command does not learn Dodge, evaluate a game policy, or save weights.
Its timing includes diagnostic checks and is not a deployment benchmark.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import platform
import time
from typing import Any


def _bounded_integer(value: int, maximum: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer from 1 to {maximum}")
    return value


def resolve_device(requested: str = "cpu") -> Any:
    """Choose CPU or MPS explicitly; unsupported MPS work never retries on CPU."""

    import torch

    if requested not in ("cpu", "mps", "auto"):
        raise ValueError("device must be cpu, mps, or auto")
    available = torch.backends.mps.is_built() and torch.backends.mps.is_available()
    chosen = "mps" if requested == "auto" and available else requested
    if chosen == "auto":
        chosen = "cpu"
    if chosen == "mps":
        if not available:
            raise RuntimeError("MPS was requested but this PyTorch runtime cannot use MPS")
        if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0") not in ("", "0"):
            raise RuntimeError(
                "MPS diagnostics require PYTORCH_ENABLE_MPS_FALLBACK unset or 0"
            )
    return torch.device(chosen)


def run_smoke(
    device: str = "cpu",
    *,
    steps: int = 1,
    batch_size: int = 2,
    architecture: str = "vit",
    patch_size: int = 16,
) -> dict[str, Any]:
    """Run at most ten synthetic optimization steps and return JSON-safe facts."""

    _bounded_integer(steps, 10, "steps")
    _bounded_integer(batch_size, 64, "batch_size")
    if architecture not in ("cnn", "vit"):
        raise ValueError("architecture must be cnn or vit")
    if isinstance(patch_size, bool) or not isinstance(patch_size, int) or patch_size not in (4, 8, 16):
        raise ValueError("patch_size must be 4, 8, or 16")

    import torch

    from .models import VisionPolicy, distillation_loss

    selected = resolve_device(device)
    generator = torch.Generator(device="cpu").manual_seed(0)
    # Keep model initialization from advancing the caller's CPU random stream.
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(0)
        if architecture == "vit":
            from .vit import ViTConfig, ViTPolicy

            config = ViTConfig(patch_size=patch_size)
            model = ViTPolicy(config).to(selected)
            architecture_config = {
                **asdict(config),
                "image_channels": 4,
                "image_size": 128,
                "num_tokens": config.num_tokens,
                "num_actions": 9,
            }
        else:
            model = VisionPolicy().to(selected)
            architecture_config = {
                "image_channels": 12,
                "image_size": 128,
                "channels": [32, 64, 64],
                "pooled_size": [4, 4],
                "hidden_dim": 256,
                "num_actions": 9,
            }
    model.train()
    images = torch.rand(batch_size, architecture_config["image_channels"], 128, 128, generator=generator).to(selected)
    teacher_logits = torch.randn(batch_size, 9, generator=generator).to(selected)
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-3)

    def synchronize() -> None:
        if selected.type == "mps":
            torch.mps.synchronize()

    losses = []
    max_abs_gradient = 0.0
    synchronize()
    started = time.perf_counter()
    for _ in range(steps):
        optimizer.zero_grad(set_to_none=True)
        logits = model(images)
        loss = distillation_loss(logits, teacher_logits)
        loss.backward()
        for parameter in model.parameters():
            gradient = parameter.grad
            if gradient is None or not bool(torch.isfinite(gradient).all()):
                raise RuntimeError("model produced a missing or nonfinite gradient")
            max_abs_gradient = max(max_abs_gradient, float(gradient.detach().abs().max()))
        optimizer.step()
        if not all(bool(torch.isfinite(p.detach()).all()) for p in model.parameters()):
            raise RuntimeError("optimization produced nonfinite model parameters")
        losses.append(float(loss.detach()))
    synchronize()
    elapsed = time.perf_counter() - started
    if max_abs_gradient == 0:
        raise RuntimeError("synthetic diagnostic produced no nonzero gradients")

    return {
        "diagnostic": "synthetic_forward_backward",
        "trained_policy": False,
        "game_evaluation": False,
        "architecture": architecture,
        "config": architecture_config,
        "requested_device": device,
        "device": str(selected),
        "torch_version": str(torch.__version__),
        "python_version": platform.python_version(),
        "machine": platform.machine(),
        "mps_built": bool(torch.backends.mps.is_built()),
        "mps_available": bool(torch.backends.mps.is_available()),
        "seed": 0,
        "steps": steps,
        "batch_size": batch_size,
        "model_parameters": sum(p.numel() for p in model.parameters()),
        "losses": losses,
        "max_abs_gradient": max_abs_gradient,
        "parameters_finite": True,
        "elapsed_seconds": elapsed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("cpu", "mps", "auto"), default="cpu")
    parser.add_argument("--steps", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--architecture", choices=("cnn", "vit"), default="vit")
    parser.add_argument("--patch-size", type=int, choices=(4, 8, 16), default=16)
    args = parser.parse_args(argv)
    try:
        result = run_smoke(
            args.device,
            steps=args.steps,
            batch_size=args.batch_size,
            architecture=args.architecture,
            patch_size=args.patch_size,
        )
    except ModuleNotFoundError as error:
        if error.name == "torch":
            parser.exit(2, "PyTorch is required; install the learner's models extra.\n")
        raise
    except (ValueError, RuntimeError) as error:
        parser.exit(2, f"model smoke failed: {error}\n")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
