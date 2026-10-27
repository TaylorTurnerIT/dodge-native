"""Resumable, CPU-agnostic LR schedule draft for the retained-324 proposal.

This module does not train or restore checkpoints. Caller restores model,
optimizer, and RNG first, then calls apply_next_update_lr before an update.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
from typing import Any

ORIGIN_CUMULATIVE_UPDATE = 372
HORIZON_UPDATES = 60
START_LR = 3e-5
END_LR = 1e-5
DECAY_SPAN = START_LR - END_LR

SCHEDULE_SPEC = {
    "name": "linear_3e-5_to_1e-5_then_hold",
    "version": 1,
    "origin_cumulative_update": ORIGIN_CUMULATIVE_UPDATE,
    "horizon_updates": HORIZON_UPDATES,
    "start_lr": START_LR,
    "end_lr": END_LR,
    "formula": "start_lr - (start_lr - end_lr) * (u - 1) / (horizon_updates - 1)",
    "u_definition": "cumulative_update - origin_cumulative_update",
    "application": "before_optimizer_step_for_cumulative_update",
    "after_horizon": "hold_end_lr",
}
SCHEDULE_SPEC_SHA256 = hashlib.sha256(
    json.dumps(SCHEDULE_SPEC, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
).hexdigest()


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def learning_rate_for_cumulative_update(cumulative_update: int) -> float:
    """Return LR for an update, using absolute cumulative update numbering."""
    c = _integer(cumulative_update, "cumulative_update", minimum=1)
    if c <= ORIGIN_CUMULATIVE_UPDATE:
        raise ValueError("cumulative_update must follow schedule origin")
    u = c - ORIGIN_CUMULATIVE_UPDATE
    if u >= HORIZON_UPDATES:
        return END_LR
    return START_LR - DECAY_SPAN * (u - 1) / (HORIZON_UPDATES - 1)


def new_schedule_state(optimizer: Any) -> dict[str, Any]:
    """Create serializable metadata after the optimizer's groups are finalized."""
    groups = getattr(optimizer, "param_groups", None)
    if not isinstance(groups, list) or not groups:
        raise ValueError("optimizer must have at least one parameter group")
    return {
        "schedule_origin_cumulative_update": ORIGIN_CUMULATIVE_UPDATE,
        "horizon_updates": HORIZON_UPDATES,
        "completed_schedule_updates": 0,
        "schedule_spec_sha256": SCHEDULE_SPEC_SHA256,
        "optimizer_param_group_count": len(groups),
    }


def validate_schedule_state(state: Mapping[str, Any], optimizer: Any) -> dict[str, int | str]:
    """Validate persisted progress and optimizer group shape; return normalized fields."""
    if not isinstance(state, Mapping):
        raise ValueError("schedule state must be a mapping")
    groups = getattr(optimizer, "param_groups", None)
    if not isinstance(groups, list) or not groups:
        raise ValueError("optimizer must have at least one parameter group")
    expected = {
        "schedule_origin_cumulative_update": ORIGIN_CUMULATIVE_UPDATE,
        "horizon_updates": HORIZON_UPDATES,
        "schedule_spec_sha256": SCHEDULE_SPEC_SHA256,
    }
    for key, value in expected.items():
        if state.get(key) != value or (key != "schedule_spec_sha256" and type(state.get(key)) is not int):
            raise ValueError(f"{key} does not match schedule specification")
    completed = _integer(state.get("completed_schedule_updates"), "completed_schedule_updates")
    if completed > HORIZON_UPDATES:
        raise ValueError("completed_schedule_updates exceeds schedule horizon")
    group_count = _integer(state.get("optimizer_param_group_count"), "optimizer_param_group_count", minimum=1)
    if group_count != len(groups):
        raise ValueError("optimizer parameter-group count does not match saved schedule state")
    return {
        "schedule_origin_cumulative_update": ORIGIN_CUMULATIVE_UPDATE,
        "horizon_updates": HORIZON_UPDATES,
        "completed_schedule_updates": completed,
        "schedule_spec_sha256": SCHEDULE_SPEC_SHA256,
        "optimizer_param_group_count": group_count,
    }


def apply_next_update_lr(optimizer: Any, state: Mapping[str, Any]) -> tuple[float, dict[str, Any]]:
    """Apply next absolute-update LR; mutate only each param group's ``lr``."""
    normalized = validate_schedule_state(state, optimizer)
    completed = int(normalized["completed_schedule_updates"])
    cumulative_update = ORIGIN_CUMULATIVE_UPDATE + completed + 1
    lr = _finite_number(learning_rate_for_cumulative_update(cumulative_update), "learning rate")
    for index, group in enumerate(optimizer.param_groups):
        current = _finite_number(group.get("lr"), f"optimizer param group {index} lr")
        if current < 0:
            raise ValueError(f"optimizer param group {index} lr must be nonnegative")
    # Validation completes before any group changes, avoiding partial application.
    for group in optimizer.param_groups:
        group["lr"] = lr
    updated = dict(normalized)
    updated["completed_schedule_updates"] = min(completed + 1, HORIZON_UPDATES)
    return lr, updated

