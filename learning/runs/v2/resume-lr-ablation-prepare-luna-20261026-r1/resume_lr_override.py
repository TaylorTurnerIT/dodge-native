"""Narrow post-restore PPO learning-rate transition for a registered arm."""
from __future__ import annotations

import math


PARENT_LR = 3e-4
ARM_LR = 1e-4


def assert_effective_lr(optimizer, expected_lr: float = ARM_LR) -> None:
    """Fail closed unless every Adam parameter group has the registered LR."""
    if not optimizer.param_groups:
        raise ValueError("Optimizer has no parameter groups")
    if not math.isfinite(expected_lr) or expected_lr <= 0:
        raise ValueError("Requested learning rate must be finite and positive")
    if any(group.get("lr") != expected_lr for group in optimizer.param_groups):
        raise ValueError("Effective optimizer learning rate differs from registered arm")


def apply_resume_lr_override(optimizer, config_lr: float) -> dict:
    """After exact parent restore, change only group LR; reject before mutation."""
    if not math.isfinite(config_lr) or config_lr != ARM_LR:
        raise ValueError("Arm config learning rate must be exactly 0.0001")
    groups = optimizer.param_groups
    if not groups:
        raise ValueError("Optimizer has no parameter groups")
    if any(group.get("lr") != PARENT_LR for group in groups):
        raise ValueError("Restored parent learning rate differs from 0.0003")

    # Validate every group before the first write. All other group fields and
    # optimizer state remain owned by the exact restored parent.
    previous = [group["lr"] for group in groups]
    try:
        for group in groups:
            group["lr"] = config_lr
        assert_effective_lr(optimizer, config_lr)
    except BaseException:
        for group, old_lr in zip(groups, previous):
            group["lr"] = old_lr
        raise
    return {"parent_lr": PARENT_LR, "effective_lr": config_lr,
            "changed_fields": ["optimizer.param_groups[*].lr"]}
