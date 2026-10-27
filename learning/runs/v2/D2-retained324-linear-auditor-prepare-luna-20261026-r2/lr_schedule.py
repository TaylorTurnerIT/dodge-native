"""Synthetic-friendly resumable LR schedule helper; no checkpoint or training I/O."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ORIGIN_CUMULATIVE_UPDATE = 372
HORIZON_UPDATES = 60
START_LR = 3e-5
END_LR = 1e-5
DECAY_SPAN = START_LR - END_LR
SCHEDULE_SPEC = {
    "name": "linear_3e-5_to_1e-5_then_hold", "version": 1,
    "origin_cumulative_update": ORIGIN_CUMULATIVE_UPDATE,
    "horizon_updates": HORIZON_UPDATES, "start_lr": START_LR, "end_lr": END_LR,
    "formula": "start_lr - (start_lr - end_lr) * (u - 1) / (horizon_updates - 1)",
    "u_definition": "cumulative_update - origin_cumulative_update",
    "application": "before_optimizer_step_for_cumulative_update",
    "after_horizon": "hold_end_lr",
}
SCHEDULE_SPEC_SHA256 = hashlib.sha256(
    json.dumps(SCHEDULE_SPEC, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
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
    c = _integer(cumulative_update, "cumulative_update", minimum=1)
    if c <= ORIGIN_CUMULATIVE_UPDATE:
        raise ValueError("cumulative_update must follow schedule origin")
    u = c - ORIGIN_CUMULATIVE_UPDATE
    if u >= HORIZON_UPDATES:
        return END_LR
    return START_LR - DECAY_SPAN * (u - 1) / (HORIZON_UPDATES - 1)


def new_schedule_state(optimizer: Any, actual_cumulative_updates: int) -> dict[str, Any]:
    """Create first metadata only at the verified schedule origin."""
    actual = _integer(actual_cumulative_updates, "actual_cumulative_updates")
    if actual != ORIGIN_CUMULATIVE_UPDATE:
        raise ValueError("fresh schedule requires original cumulative update 372")
    groups = getattr(optimizer, "param_groups", None)
    if not isinstance(groups, list) or not groups:
        raise ValueError("optimizer must have at least one parameter group")
    return {"schedule_origin_cumulative_update": ORIGIN_CUMULATIVE_UPDATE,
            "horizon_updates": HORIZON_UPDATES, "completed_schedule_updates": 0,
            "schedule_spec_sha256": SCHEDULE_SPEC_SHA256,
            "optimizer_param_group_count": len(groups)}


def validate_schedule_state(state: Mapping[str, Any], optimizer: Any) -> dict[str, Any]:
    if not isinstance(state, Mapping):
        raise ValueError("schedule state must be a mapping")
    groups = getattr(optimizer, "param_groups", None)
    if not isinstance(groups, list) or not groups:
        raise ValueError("optimizer must have at least one parameter group")
    required = {"schedule_origin_cumulative_update", "horizon_updates",
                "completed_schedule_updates", "schedule_spec_sha256",
                "optimizer_param_group_count"}
    if not required.issubset(state):
        raise ValueError("schedule state is missing required metadata")
    for key, expected in (("schedule_origin_cumulative_update", ORIGIN_CUMULATIVE_UPDATE),
                          ("horizon_updates", HORIZON_UPDATES)):
        if type(state[key]) is not int or state[key] != expected:
            raise ValueError(f"{key} does not match schedule specification")
    if type(state["schedule_spec_sha256"]) is not str or state["schedule_spec_sha256"] != SCHEDULE_SPEC_SHA256:
        raise ValueError("schedule_spec_sha256 does not match schedule specification")
    completed = _integer(state["completed_schedule_updates"], "completed_schedule_updates")
    count = _integer(state["optimizer_param_group_count"], "optimizer_param_group_count", minimum=1)
    if count != len(groups):
        raise ValueError("optimizer parameter-group count does not match saved schedule state")
    return {"schedule_origin_cumulative_update": ORIGIN_CUMULATIVE_UPDATE,
            "horizon_updates": HORIZON_UPDATES, "completed_schedule_updates": completed,
            "schedule_spec_sha256": SCHEDULE_SPEC_SHA256,
            "optimizer_param_group_count": count}


def apply_next_update_lr(optimizer: Any, state: Mapping[str, Any],
                         actual_cumulative_updates: int) -> tuple[float, dict[str, Any]]:
    """Validate actual progress, apply next LR, and return staged metadata.

    Caller must commit returned metadata only after PPO update succeeds.
    """
    actual = _integer(actual_cumulative_updates, "actual_cumulative_updates")
    normalized = validate_schedule_state(state, optimizer)
    completed = normalized["completed_schedule_updates"]
    if completed != actual - ORIGIN_CUMULATIVE_UPDATE:
        raise ValueError("completed schedule updates do not match actual cumulative updates")
    lr = _finite_number(learning_rate_for_cumulative_update(actual + 1), "learning rate")
    for index, group in enumerate(optimizer.param_groups):
        current = _finite_number(group.get("lr"), f"optimizer param group {index} lr")
        if current < 0:
            raise ValueError(f"optimizer param group {index} lr must be nonnegative")
    for group in optimizer.param_groups:
        group["lr"] = lr
    staged = dict(normalized)
    staged["completed_schedule_updates"] = completed + 1
    return lr, staged


def verify_frozen_manifest(directory: Path) -> None:
    """Verify helper bytes and schedule spec against this auditor's frozen manifest."""
    manifest = json.loads((directory / "frozen-manifest.json").read_text())
    source_sha = hashlib.sha256((directory / "lr_schedule.py").read_bytes()).hexdigest()
    spec_sha = hashlib.sha256(json.dumps(SCHEDULE_SPEC, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if (manifest.get("schema") != "d2_retained324_linear_auditor_frozen_manifest_v2"
            or manifest.get("schedule_spec_sha256") != spec_sha
            or manifest.get("auditor_sources", {}).get("lr_schedule.py") != source_sha
            or manifest.get("files", {}).get("lr_schedule.py") != source_sha):
        raise ValueError("frozen schedule manifest mismatch")
