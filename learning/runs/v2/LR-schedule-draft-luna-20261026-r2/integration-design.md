# LR schedule helper: integration design

Status: CPU synthetic helper draft only. No production source or run state changed. No MPS, checkpoint load, rollout, training, environment access, launch, lease, marker, or seed operation occurred.

## Contract

- Verified original cumulative learner update count is 372. Create metadata only with `new_schedule_state(optimizer, actual_cumulative_updates=372)` on that explicit first-creation path.
- Every application passes actual completed cumulative learner updates. The helper requires `completed_schedule_updates == actual_cumulative_updates - 372`, then applies LR for `actual_cumulative_updates + 1`.
- Updates 373..432 linearly decay from `3e-5` to `1e-5`; update 432 is `1e-5`. Later updates hold `1e-5`.
- Persist uncapped `completed_schedule_updates`; after scheduled horizon it continues to track real completed updates. Missing, stale, reset, invalid, or spec-mismatched metadata is an error on resume.
- `apply_next_update_lr` returns proposed next metadata. Caller must stage it and commit only after the associated `ppo_update` succeeds. LR application alone is not a completed update.
- All metadata and every optimizer group LR validate before any LR mutation. Group membership is not individually identified by this helper; production restore must retain optimizer state and group structure.
- `frozen-manifest.json` binds the canonical spec declaration hash and exact `schedule.py` source hash. Formula is implemented directly in Python; no string evaluation.

## D2 runner source map (read-only inspection)

Applicable selected-324 D2 implementation is `learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2/runner.py`, which runs its own loop. It does not use a `Trainer` class or `train_teacher.py`'s `Experiment` loop.

- Parent checkpoint load: line 662; restore learner/model/Adam/RNG: line 668.
- Inherited cumulative counters copy: line 682. Require `inherited["updates"] == 372` before first schedule metadata creation.
- Local counters start at zero: line 699. Before each update, actual completed cumulative count is `inherited["updates"] + counters["updates"]`; next update count is that value plus one.
- Checkpoint dict is assembled by hand at lines 718-740. Store committed schedule metadata there. Resume path must require the field; never use `.get(..., new_schedule_state(...))` or infer it from local phase progress.
- Existing saved optimizer LR assertion is line 741; fixed LR pre-step assertion is line 772; `ppo_update` starts line 773. A successor runner must replace fixed-LR assumptions and apply schedule immediately before `ppo_update`.
- Stage returned metadata; commit it only after `ppo_update` and all accepted finite/result checks succeed. Persist that committed state in later checkpoints and metrics.
- Local successful update counter is set at line 786; cumulative counters are computed through `continuation_cumulative_counters(inherited, counters)` at line 811.

## Required successor integration work

The current runner is pinned and its campaign uses fixed `3e-5`. Do not edit it for this draft. A schedule-enabled successor needs a new registration with new runner/source pins and corresponding config/runtime registration validation. It must revise entry, per-update, and saved-checkpoint LR invariants; add schedule metadata to checkpoint creation and required resume validation; record actual cumulative update and each group LR; and test all paths before any separate authorization to run.

Current retained-324 campaign remains fixed at `3e-5`; this draft does not change it. The review note suggesting that existing run decays is incorrect.

## Verification limits

Tests cover synthetic CPU Adam state only. They do not establish checkpoint compatibility, PPO correctness, MPS behavior, runtime/resource compliance, registration readiness, campaign qualification, or scientific validity.
