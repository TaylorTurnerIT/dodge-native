"""Schedule integration contract. Deliberately has no checkpoint or training I/O."""
from __future__ import annotations
from collections.abc import Mapping
import schedule

RUN_ID = "D2-retained324-linear-lr-20261026-r1"
TRAINING_MASTER_SEED = 4200000001  # Pairing intent only; never register or consume here.

def need(ok, message):
    if not ok:
        raise ValueError(message)

def actual_cumulative_updates(inherited, counters):
    need(isinstance(inherited, Mapping) and isinstance(counters, Mapping), "counter mappings required")
    need(inherited.get("updates") == 372, "inherited updates must equal 372")
    local = counters.get("updates")
    need(type(local) is int and local >= 0, "local updates must be nonnegative integer")
    return inherited["updates"] + local

def initialize_at_verified_origin(optimizer, inherited, counters):
    actual = actual_cumulative_updates(inherited, counters)
    need(actual == 372, "fresh schedule metadata allowed only at verified origin 372")
    return schedule.new_schedule_state(optimizer, actual)

def restore_schedule_state(checkpoint, optimizer):
    need(isinstance(checkpoint, Mapping) and "lr_schedule" in checkpoint,
         "scheduled checkpoint missing lr_schedule metadata")
    return schedule.validate_schedule_state(checkpoint["lr_schedule"], optimizer)

def stage_before_ppo(optimizer, state, inherited, counters):
    actual = actual_cumulative_updates(inherited, counters)
    lr, staged = schedule.apply_next_update_lr(optimizer, state, actual)
    return lr, staged  # Caller commits staged metadata only after successful PPO update.

def expected_saved_lr(state, cumulative_update):
    schedule.validate_schedule_state(state, type("Optimizer", (), {"param_groups": [{}]})())
    if cumulative_update == 372 and state["completed_schedule_updates"] == 0:
        return schedule.START_LR
    if cumulative_update <= 372:
        raise ValueError("scheduled candidate must be at or after schedule origin")
    return schedule.learning_rate_for_cumulative_update(cumulative_update)
