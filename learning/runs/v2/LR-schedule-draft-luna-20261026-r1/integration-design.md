# LR schedule helper and integration design

Status: CPU-only implementation draft. No production source changed; no training, environment, rollout, checkpoint access, campaign output, lease, marker, or launch used.

## Schedule contract

- Absolute origin is cumulative update 372. First scheduled update is cumulative 373 (`u=1`) at `3e-5`.
- Updates 373 through 432 inclusive use `3e-5 - 2e-5 * (u - 1) / 59`, where `u = cumulative_update - 372`. Update 432 is exactly `1e-5`.
- Updates after 432 hold at `1e-5`. Schedule progress is capped at 60 completed schedule updates; campaign-local counters never define schedule position.
- Metadata contains `schedule_origin_cumulative_update`, `horizon_updates`, `completed_schedule_updates`, `schedule_spec_sha256`, and `optimizer_param_group_count`. The final field binds restore to the optimizer grouping used when metadata was created.
- The spec hash is SHA-256 over canonical sorted compact JSON for the schedule name, version, origin, horizon, endpoints, formula, update convention, and post-horizon behavior.
- `apply_next_update_lr` validates all metadata, group count, and existing group LRs before changing any group. It changes only `param_group["lr"]`; Adam moments, step tensors, and other optimizer fields remain untouched.

## Exact production integration point

The applicable runtime implementation is `python/dodge_rl/ppo.py` with `python/dodge_rl/train_teacher.py` and `python/dodge_rl/checkpoints.py`:

1. `Trainer.__init__` at `python/dodge_rl/train_teacher.py` creates the model and Adam optimizer, then calls `ckpt.restore_learner` for a parent. That helper restores model weights, optimizer state, then RNG (`python/dodge_rl/checkpoints.py`). Add schedule-state restore immediately after this call. Validate the saved spec and optimizer group count there. Do not construct a replacement optimizer after restore.
2. `Trainer.update_once` collects the on-policy rollout, then calls `ppo_update`. Apply the next absolute-cumulative-update LR immediately before this `ppo_update` call. This is before every possible `optimizer.step()` in `ppo_update` (`python/dodge_rl/ppo.py`), and maps update `counters["updates"] + 1` onto the immutable cumulative origin, not `phase_updates`.
3. Stage the returned progress metadata until `ppo_update` completes successfully. Commit `completed_schedule_updates` only after success, alongside the existing successful counter increments. An interrupted update already cannot qualify as a learner restore (`require_complete_update`); do not count it as a completed schedule update.
4. Persist the schedule metadata in each learner checkpoint (for example, a dedicated `lr_schedule` field alongside `counters` and `update_progress` in `make_state` output). Restore it with the checkpoint. Never infer it from `phase_updates`, since `Trainer.__init__` resets that local counter to zero on a phase transition.
5. Emit actual absolute cumulative update and LR for each parameter group in update metrics. Current `make_optimizer` creates Adam with one parameter group, but helper checks actual count rather than assuming one.

Current checkpoint schema already stores optimizer state, RNG, counters, and `update_progress`. It has no LR schedule metadata field today. Current restore order is model, Adam, RNG; schedule validation/application must follow that complete restore. The helper itself does not implement checkpoint I/O or alter production code.

## Limits

These tests prove schedule arithmetic and synthetic CPU Adam resume behavior only. They do not establish compatibility with a real checkpoint, RNG parity in the production runner, PPO behavior, runtime budgets, campaign registration, or scientific validity. A parent-owned implementation review and authorization remain required before any integration or launch.
