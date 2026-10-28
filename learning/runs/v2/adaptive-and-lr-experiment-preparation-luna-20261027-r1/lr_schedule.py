"""Pure LR schedule/optimizer-group contract; no torch import."""
from __future__ import annotations
import math

UPDATES = 60
START_LR = 3e-5
END_LR = 1e-5


def learning_rate_for_update(update: int, *, updates: int = UPDATES,
                             start: float = START_LR, end: float = END_LR) -> float:
    """Linear endpoint-inclusive schedule, indexed by completed update1..updates."""
    if type(updates) is not int or updates < 2:
        raise ValueError("updates must be integer>=2")
    if type(update) is not int or not 1 <= update <= updates:
        raise ValueError("update outside registered schedule")
    if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
           for v in (start, end)):
        raise ValueError("learning rates must be finite and positive")
    if update == 1:
        return float(start)
    if update == updates:
        return float(end)
    return float(start + (end - start) * ((update - 1) / (updates - 1)))


def set_and_check_optimizer_lr(optimizer, expected_lr: float) -> list[float]:
    """Set before PPO, then validate every group; caller journals return value."""
    if type(expected_lr) not in (int, float) or not math.isfinite(expected_lr) or expected_lr <= 0:
        raise ValueError("expected LR must be finite and positive")
    groups = getattr(optimizer, "param_groups", None)
    if not isinstance(groups, list) or not groups:
        raise ValueError("optimizer param_groups required")
    previous = []
    for group in groups:
        if not isinstance(group, dict) or "lr" not in group:
            raise ValueError("optimizer group lacks lr")
        old = group["lr"]
        if type(old) not in (int, float) or not math.isfinite(old) or old <= 0:
            raise ValueError("optimizer group LR invalid")
        previous.append(float(old))
    for group in groups:
        group["lr"] = float(expected_lr)
    if any(group["lr"] != float(expected_lr) for group in groups):
        raise ValueError("effective optimizer LR differs after assignment")
    return previous


def require_restored_lr(optimizer, expected_lr: float) -> list[float]:
    """Check saved Adam LR before any schedule override or PPO call."""
    groups = getattr(optimizer, "param_groups", None)
    if not isinstance(groups, list) or not groups:
        raise ValueError("optimizer param_groups required")
    values = []
    for group in groups:
        if not isinstance(group, dict) or type(group.get("lr")) not in (int, float):
            raise ValueError("optimizer group LR missing")
        value = float(group["lr"])
        if not math.isfinite(value) or value != float(expected_lr):
            raise ValueError("restored optimizer LR differs from expected schedule start")
        values.append(value)
    return values
