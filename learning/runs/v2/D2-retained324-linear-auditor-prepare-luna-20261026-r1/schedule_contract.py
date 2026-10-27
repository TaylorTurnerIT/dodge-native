"""Pure validation for retained324 linear-schedule checkpoint and metric evidence."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

import lr_schedule

ORIGIN = lr_schedule.ORIGIN_CUMULATIVE_UPDATE
HORIZON = lr_schedule.HORIZON_UPDATES
GROUP_COUNT_KEY = "optimizer_param_group_count"


class ScheduleAuditError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ScheduleAuditError(message)


def expected_lr(cumulative_update: int) -> float:
    if cumulative_update == ORIGIN:
        return lr_schedule.START_LR
    return lr_schedule.learning_rate_for_cumulative_update(cumulative_update)


def _check_state(schedule: object, group_count: int, *, local_updates: int) -> Mapping:
    require(isinstance(schedule, Mapping), "Checkpoint schedule metadata missing or invalid")
    expected = {
        "schedule_origin_cumulative_update": ORIGIN,
        "horizon_updates": HORIZON,
        "completed_schedule_updates": local_updates,
        "schedule_spec_sha256": lr_schedule.SCHEDULE_SPEC_SHA256,
        GROUP_COUNT_KEY: group_count,
    }
    require(group_count > 0, "Optimizer parameter groups missing")
    for key, value in expected.items():
        require(key in schedule, f"Schedule metadata missing {key}")
        require(type(schedule[key]) is type(value) and schedule[key] == value,
                f"Schedule metadata differs at {key}")
    return schedule


def validate_checkpoint_schedule(state: Mapping, *, inherited_updates: int,
                                 local_updates: int, cumulative_updates: int) -> float:
    """Bind checkpoint LR groups and schedule metadata to inherited + local progress."""
    require(type(inherited_updates) is int and inherited_updates == ORIGIN,
            "Inherited cumulative updates differ from schedule origin")
    require(type(local_updates) is int and 0 <= local_updates <= HORIZON,
            "Local schedule progress outside 0..60")
    require(type(cumulative_updates) is int and cumulative_updates == inherited_updates + local_updates,
            "Cumulative update differs from inherited plus local")
    optimizer = state.get("optimizer")
    require(isinstance(optimizer, Mapping), "Optimizer state missing")
    groups = optimizer.get("param_groups")
    require(isinstance(groups, list) and groups and all(isinstance(group, Mapping) for group in groups),
            "Optimizer parameter groups missing or invalid")
    _check_state(state.get("lr_schedule"), len(groups), local_updates=local_updates)
    expected = expected_lr(cumulative_updates)
    require(all(type(group.get("lr")) is float and math.isfinite(group["lr"])
                and group["lr"] == expected for group in groups),
            f"Saved optimizer LR differs from schedule at cumulative update {cumulative_updates}")
    return expected


def validate_metric_schedule(row: Mapping, *, inherited_updates: int, local_update: int,
                             group_count: int) -> float:
    """Bind every metric row's schedule metadata and reported group LRs to that update."""
    require(type(local_update) is int and 1 <= local_update <= HORIZON,
            "Metric local update outside 1..60")
    cumulative = inherited_updates + local_update
    require(type(inherited_updates) is int and inherited_updates == ORIGIN,
            "Metric inherited cumulative update differs from schedule origin")
    require(type(row.get("cumulative_updates")) is int and row["cumulative_updates"] == cumulative,
            "Metric cumulative update differs from inherited plus local")
    schedule = _check_state(row.get("lr_schedule"), group_count, local_updates=local_update)
    require(schedule["completed_schedule_updates"] == local_update,
            "Metric schedule progress differs from local update")
    reported = row.get("optimizer_group_lrs")
    require(isinstance(reported, list) and len(reported) == group_count,
            "Metric optimizer group LR list missing or wrong size")
    expected = expected_lr(cumulative)
    require(all(type(value) is float and math.isfinite(value) and value == expected for value in reported),
            f"Metric optimizer group LR differs from schedule at cumulative update {cumulative}")
    return expected


def validate_progression(rows: Sequence[Mapping], *, group_count: int) -> list[float]:
    """Validate full local 1..60 metric sequence and return expected LR per update."""
    require(len(rows) == HORIZON, "Full schedule audit requires 60 metric rows")
    return [validate_metric_schedule(row, inherited_updates=ORIGIN, local_update=index,
                                     group_count=group_count)
            for index, row in enumerate(rows, 1)]
