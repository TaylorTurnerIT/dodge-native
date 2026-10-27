# Paired fixed-vs-linear PPO learning-rate study: preregistration design

Status: design proposal only. No experiment, inference, environment, checkpoint decode, lease, ledger, or source change was made. The parent owns all launch and registration authority. Machine-readable contract: `plan.json`. Input hashes and exclusions: `input-hashes.json`.

## 1. Context and limits

- Parent: `checkpoint-000324-candidate.pt` (local update 324, cumulative update 372), SHA-256 `c10d90ec…a04c8ddc`, receipt `76cb1573…f08`, accepted in `D2-retained300-parent-terminal-audit-20261026-r1`.
- Operational control: `D2-retained324-continuation-20261026-r1` is already running once. Constant LR 3e-5, master seed `4200000001`, local 324→384 (cumulative 372→432). Its original registration (`…prepare-luna-20261026-r2/registration.json`, SHA-256 `44ac8185…4c`) is unchanged.
- The control was not preregistered before its launch. This design does not treat it as one. Its use as the constant arm is a disclosed post-launch control, valid only if the parent confirms its frozen configuration equals the treatment except LR.
- The research basis is a Luna synthesis of a Haiku fallback. Evidence is limited: LR matters, decay effects are mixed and benchmark-specific, and no PPO-specific evidence was found for cosine decay or warmup. No Dodge schedule has been tested.
- The design relies on no control outcome. The performance figures used are only the accepted update-324 entry.

## 2. Arms

| Arm | Run ID | LR by cumulative update `c` | Notes |
|---|---|---|---|
| Constant | `D2-retained324-continuation-20261026-r1` (existing control) | `3e-5` for all updates | Operational control; not preregistered |
| Linear | `D2-retained324-paired-linear-LR-r1` (proposed name, parent registers) | `LR = 3e-5 − 2e-5·(u−1)/59`, `u = c − 372`, `u = 1..60`; floor `1e-5` for `u > 60` | Mean LR 2e-5 |

Shared settings, identical across arms: start state (checkpoint 324, cum 372), Adam state, RNG state, master seed `4200000001`, 4 epochs, minibatch 512, clip 0.2, target KL 0.03, 60 updates, 983,040 environment transitions (16,384 per update), and all other PPO settings. Realized optimizer steps may differ because target-KL early stop is a treatment outcome. Record them; do not force equality.

LR convention to fix before launch: the proposal sets the LR for cumulative update `c` (373..432) before that update's optimizer step. The parent must confirm this convention matches the implementation.

## 3. Schedule persistence and resume

Persist: `schedule_origin_cumulative_update = 372`, `horizon_updates = 60`, `completed_schedule_updates`, and a hash of the schedule specification. A campaign-local update counter alone is insufficient because it resets between campaigns.

Resume order: restore model, Adam, and RNG state first, then compute LR from saved schedule progress and apply it. Do not reset Adam or restart the schedule. Discarded branches do not advance the schedule. Resuming a selected checkpoint restores that checkpoint's progress.

## 4. Endpoint and metrics

- Fixed endpoint: local update 384 (cumulative 432) for both arms. No checkpoint selection.
- Scientific primary: mean alive raw frames over 64 episodes on an independent held-out pool, with Q1 and Q4 and death causes as secondary metrics. Q1 and Q4 are arithmetic means of the lowest and highest 16 episodes, using fractional frame means. Death causes are measured counts and survival by cause, with unknown and truncations reported separately. Per `teacher-qualification-v3.json`, the score is diagnostic only.
- Pairing and analysis: per-seed difference `linear − constant` on identical episode seeds. Report the mean difference and an uncertainty interval over the 64 seeds (bootstrap, with the draw schedule fixed before launch). This one training pair does not estimate training-replicate variance.
- Secondary: the existing 64 development seeds (`D0000000`–`D000003F`). These were used to select update 324 and are selection-biased. Report them for context only.
- Operational best retention: a separate decision on dev seeds, which does not change the scientific comparison.

## 5. Held-out seed manifest

Source facts, read from `python/dodge_rl/dev_eval.py`, `docs/v2-m3-run-protocol.json`, and `python/dodge_rl/ppo.py`:

- `development.seed_start` = `3489660928` = `0xD0000000`. Dev seeds are `0xD0000000`–`0xD000003F` (64 seeds). `dev_eval.require_development_seed` rejects any other seed.
- `training_excluded_ranges` = `[0xB0000000, 0xB00003E7]`, `[0xD0000000, 0xD000007F]`, `[0xE0000000, 0xE00003E7]`. The D block is 128 seeds, of which the upper 64 (`0xD0000040`–`0xD000007F`) are excluded from training but are not dev seeds.
- `ppo.py` `_RESERVED_RANGES` matches the B, D, and E reservations above.
- Sealed B and E (`0xB…` and `0xE…`) and the qualification D2/D3 draws are off limits. `qualification_B_opened = false`, `student_work = false`. The D2/D3 qualification draw schedule was not inspected.
- `dev_eval.summarize` requires exactly 64 rows with the dev seed list. An independent pool therefore needs a new registered helper or a new explicit-seed mode. It must not be a silent extension of dev_eval.

Candidate pool: `0xD0000040`–`0xD000007F` (decimal `3489660992`–`3489661055`, 64 seeds). This is defensible only as a candidate. It sits in the training-excluded D block, outside the dev seeds. Two things are unverified: no ledger or seed-manifest check has confirmed it is unused and unassigned, and the qualification draws were not inspected for overlap. The parent must confirm both and freeze the manifest before any evaluation. If either check fails, the parent must freeze a different, unused, non-sealed manifest. The design does not extend the study window or silently reuse the dev 64.

## 6. Budgets and resources

- Per training window: work ≤ 1790 s, total ≤ 1800 s including 10 s cleanup, RSS ≤ 6 GiB, MPS limit separate. One MPS run at a time.
- Evaluation window: separate registration, proposed total limit 1800 s, RSS ≤ 6 GiB. CPU, or one MPS run at a time after the current training terminal lease is cleared. No overlap with training.
- Evaluation wall time is unmeasured here. The parent must set the evaluation budget from a registered timing or the protocol reserve formula (`max(30, 2×before_evaluation_wall_seconds)+10`). The design sets no timing number.
- Window count: first pair is 1 new training window (linear; the constant training window is the existing control) plus 2 evaluation windows (one per arm). Full 3-seed design needs 6 training and 6 evaluation windows, each separately registered. Only the first pair is feasible to recommend. The full sweep is not authorized.

## 7. Failure, invalid, and cancellation rules

- No retry, no seed replacement, no cap increase, no window extension.
- Invalid if: parent or checkpoint hash mismatch; Adam or RNG restore mismatch; schedule origin, horizon, or `completed_schedule_updates` mismatch; any non-finite loss, gradient, or LR; missing per-group LR log or LR differing from the formula; evaluation incomplete, not 64 episodes, or seed order changed; wall or work budget exceeded; training and evaluation overlapping on MPS.
- Not invalid: early target-KL stop, changed realized epochs or optimizer steps, deaths, truncations. Record these as outcomes.
- Cancellation is terminal for that window. A new window requires a new registration.

## 8. Implementation validation (before launch)

1. Restored Adam state matches the saved hash. Only the LR is changed. `betas`, `eps`, `weight_decay`, and `amsgrad` are unchanged, and `step` counts are preserved.
2. Actual per-param-group LR is logged every update, with the group names. Confirm whether the optimizer uses one group or separate actor/critic groups (not yet verified in `ppo.py`).
3. Resume clamp: LR is computed from cumulative update `c`; fail if `c` is outside 373..432 for the study, and apply the 1e-5 floor only past the horizon.
4. Horizon is 60 updates; `completed_schedule_updates` is persisted and checked on resume.
5. Restored RNG (torch, numpy, env) matches the saved state before the first update.
6. Log realized epochs, optimizer steps, KL, clip fraction, entropy, gradient norm, losses, explained variance, and endpoint metrics.
7. The evaluation helper must check the seed list against the frozen manifest and write per-episode rows with seed, frames, and cause.

## 9. Unverified decisions (parent must resolve)

1. Whether `0xD0000040`–`0xD000007F` is unused and unassigned, and whether the qualification draws overlap it. Requires ledger or manifest check.
2. Exact frozen held-out manifest, or a replacement manifest if check 1 fails.
3. New helper or explicit-seed evaluation mode, registered under the v3 survival-only policy. Current `dev_eval.py` is tied to the v2 protocol.
4. Evaluation wall-time budget.
5. LR application convention (before or after the step for cumulative update `c`) and the optimizer group structure in `ppo.py`.
6. Equivalence of the existing control's frozen config to the treatment except LR. Verify from the registration config fields only, not from outcomes.
7. Whether the 2e-5 constant follow-up is needed. Default: no, not in the first budget.
8. Whether the treatment run ID and registration name are accepted.

## 10. Not authorized

Full 3-seed sweep, constant-2e-5 follow-up, any implementation change, any launch, any sealed B/E/D3 or student work, and any reliance on current control outcomes.
