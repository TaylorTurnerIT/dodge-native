# LR schedule draft: independent source review

Scope: static read only. No imports, tests, subprocesses, MPS, checkpoint, or environment access. No source edits, no launch. Output confined to this directory.

Reviewed (immutable draft): `learning/runs/v2/LR-schedule-draft-luna-20261026-r1/{schedule.py, test_schedule.py, integration-design.md, results.md, test.log, sha256sums.txt}`.

Also read for integration checks: `learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2/{runner.py, parent_adapter.py}`, `python/dodge_rl/{train_teacher.py, checkpoints.py, ppo.py}`.

## Hashes

- Recorded `sha256sums.txt` digests match the stated `schedule.py` digest `24729b8efb9f4be1981222882c737e0e06214bce104c076ce431a1f7ff5c5361` (line 1). Other recorded digests (`test_schedule.py` 9d09cf82…, `integration-design.md` 51b601a9…, `results.md` d8de262a…, `test.log` 2a8a4659…) were copied as recorded, not recomputed. Recomputing needs a subprocess, which this review excluded.
- Runner/adapter pins (`runner.py` constants, `parent_adapter.py` `RECEIPT_SHA`, `CHECKPOINT_SHA`, etc.) were read, not hashed. They are source-level claims only.

## Arithmetic (static, verified by reading)

- `u = c - 372`; `c = 373` gives `u = 1` and LR `3e-5` exactly (`schedule.py:55-58`, `(u-1)=0`).
- `u = 59` (`c = 431`) gives `1e-5 + 2e-5/59`; `u = 60` (`c = 432`) returns `END_LR` via the `u >= 60` branch (`schedule.py:56-57`). Formula at `u = 60` would also give `1e-5`, so the branch is consistent.
- `c >= 433` returns `END_LR` (hold). 60 scheduled updates are `373..432` inclusive. Matches intent.
- `apply_next_update_lr` maps `completed = k` to `c = 372 + k + 1` (`schedule.py:108-109`). `k = 0` gives `373`, `k = 59` gives `432`.
- Test expectations in `test_schedule.py:33-37` agree with this math. Not executed here.

## Findings

### 1. Cumulative counter is never bound (parent concern 1) — integration blocker, draft-acceptable as helper
- Where: `schedule.py:105-109` derives the update number only from `completed_schedule_updates`. `schedule.py:61-72` (`new_schedule_state`) hard-codes `completed = 0` with no input. `schedule.py:75-102` validates only the completed count range and group count.
- Trigger: a caller creates or restores schedule metadata whose `completed` is out of step with the learner's real cumulative update count. Examples: `new_schedule_state` on a resume, a stale or zeroed `completed` field, or a parent whose `cumulative_counters["updates"] != 372`.
- Consequence: LR silently restarts at `3e-5` or lags, with no error. Nothing in the API checks the learner's counter.
- Static mitigation found: `parent_adapter.py:18, 32` pins the selected receipt and requires `state["cumulative_counters"] == receipt["candidate_cumulative_counters"]`. That makes `inherited["updates"] == 372` hold for the D2 parent by pinned bytes, not by an assertion in the schedule code. `runner.py` does not assert it directly (line 682 copies `parent["cumulative_counters"]` without a check).
- Required before production: pass the learner's cumulative counter into `apply_next_update_lr` (or assert `completed == cumulative_counters["updates"] - 372` each update). Assert `inherited["updates"] == 372` at restore. Do not initialize with `new_schedule_state()` from a parent at any other point.

### 2. Integration design names the wrong code and wrong counter (parent concern 2) — doc blocker
- `integration-design.md:16-19` says `Trainer.__init__`, `Trainer.update_once`, and `make_state` in `train_teacher.py`/`checkpoints.py`. `train_teacher.py` has no `Trainer` class. The class is `Experiment` (`train_teacher.py:131`; restore at `:169`; `update_once` at `:260`; `ppo_update` call at `:274`).
- The actual D2 frozen runner does not use `train_teacher` at all. It runs its own loop: parent load `runner.py:662`; `ckpt.restore_learner` `:668`; `ppo_update` `:773` inside `for update in range(1, NEW_UPDATES+1)` (`:764`); checkpoint dict built by hand `:718-740` (not `make_state`).
- Counter convention differs by path:
  - `train_teacher.py`: `counters["updates"]` is restored cumulative (`:170`), so the design's `counters["updates"] + 1` fits there.
  - `runner.py`: `counters["updates"]` is local, starts at `0` (`:699`), and resets to `update` (`:786`). `counters["updates"] + 1` would give `1` instead of `373`. Cumulative is `inherited + local` (`:811`).
- Consequence: a literal implementation of the design gives a wrong schedule on the D2 path.
- Required: the design must name `runner.py` as the integration point, with `cumulative = inherited["updates"] + counters["updates"] + 1`, and the schedule-state field added in the `runner.py:718-740` dict.

### 3. Frozen-runner invariants fail once the schedule is applied (integration blocker for runner)
- `runner.py:772` `assert_effective_lr(optimizer, LEARNING_RATE)` runs before every `ppo_update`. It requires LR exactly `3e-5`. With the schedule applied, update 2 (`LR = 3e-5 - 2e-5/59`) raises.
- `runner.py:741` `assert_saved_optimizer_lr(state, LEARNING_RATE)` runs at every candidate checkpoint. First failure at `evaluate_at(336)` after local update 12, and only if update 2 did not already fail.
- `runner.py:680` checks the restored optimizer LR `3e-5` at entry. This one still holds for the selected324 parent: `parent_adapter.py:51` requires restored LR `3e-5`.
- Pins: `runner.py` is a pinned critical input (`validate_registration :155-158`, `load_registration :318-322`). `runner.py` changes the runner digest and requires a new registration and new `runtime`/`config` pins (`CONFIG_SHA`, `NEW_NATIVE_SHA` are unaffected by a Python-only change, but the registration and runner pins are). Treat as a new registration, not an edit in place.

### 4. Initialization and resume trap (parent concern 1, second part) — medium
- The parent `324` checkpoint has no schedule field. Any integration must reject a missing field on resume. A `.get("lr_schedule", new_schedule_state(...))` default would silently restart decay from `completed = 0`.
- `validate_schedule_state` already rejects a missing key (`state.get(key)` returns `None`, `schedule.py:87-89`), so the helper is safe. The risk is in the caller's default, not the helper.
- Required: explicit first-creation path from the verified parent cumulative counter, and hard rejection when the field is absent on any checkpoint written after this change.

### 5. Horizon cap makes `completed_schedule_updates` mean something else after 60 (parent concern 4) — low-medium
- `schedule.py:119` caps persisted `completed` at `60`. `schedule.py:91-92` rejects any stored value `> 60`.
- Consequence: after the 60th update, `completed` no longer equals the real update count. A caller that stores `completed + 1` uncapped, or reads `completed` for logging, will see a wrong count. A caller that does store uncapped values will fail validation on the next resume.
- LR math is still correct because the post-horizon branch is `END_LR` for any `c >= 433`.
- Required semantics: either document `completed` as `min(actual, 60)` in the metadata name and design, or store the real cumulative update separately from the schedule counter. Pick one before integration.
- No test covers `apply_next_update_lr` at `completed = 60`, or the cap at `schedule.py:119`.

### 6. Group membership is checked by count only (parent concern 3) — low, acceptable as draft limit
- `schedule.py:93-95` checks only `optimizer_param_group_count`. It does not bind which parameters belong to each group.
- Mitigation (external, not run here): `checkpoints.restore_learner` calls `optimizer.load_state_dict` (`checkpoints.py:141`) before schedule validation. PyTorch's Adam state-dict loader rejects a param-count mismatch per group (torch behavior, assumed from library knowledge). Schedule application happens after restore, so membership is covered on the D2 path.
- Acceptable for a draft. Not a production blocker if integration keeps the restore-then-schedule order that `integration-design.md:18` states.

### 7. Spec hash binds a declaration, not the code — low
- `schedule.py:21-35` hashes a dict whose `formula` is a string. No code derives `learning_rate_for_cumulative_update` from that string, and no test checks the two agree. A change to the formula in code leaves the hash unchanged.
- Required: test that the formula string matches the function on sample points, or generate the string from the same constants.

### 8. Test gaps — low
- `test_schedule.py:32-37` checks only endpoints. No test of the full 60-step sequence against the formula.
- No test for post-horizon apply or the `completed` cap (finding 5).
- No negative test for a missing key, a non-Mapping state, a float-valued `completed` (for example `1.0`), or a bool-valued count other than the `True` case at `:120`.
- `test_split_resume_matches_uninterrupted_adam` (`:51-79`) compares `full_state == resumed_state` (completed counter) and Adam state, but not the per-group `lr` after resume. A stale-LR bug on resume would not be caught by that assertion.
- `test.log` has no interpreter path, working directory, or command. Provenance is weak. Results.md names `python/.venv/bin/python -B`, but the log does not show it.
- Cosmetic: `test_schedule.py:24-30` has a dead branch (`groups` is the same in both arms).

## What holds

- Atomic validation: `apply_next_update_lr` validates state (`:107`), checks each group's LR is finite and nonnegative (`:111-114`), and only then mutates (`:116-117`). Test at `test_schedule.py:119-129` covers the NaN case.
- Optimizer state preservation: `apply_next_update_lr` changes only `param_groups[i]["lr"]`. Test at `:81-97` checks Adam state entries are unchanged.
- Spec hash covers name, version, origin, horizon, endpoints, formula, update convention, and post-horizon behavior, as the design claims (`schedule.py:21-35`).
- `restore_learner` order matches the design: model, Adam, RNG (`checkpoints.py:138-142`).
- A pending update does not count: `require_complete_update` (`checkpoints.py:129-135`) and `runner.py` progress updates (`:416-420`, `:783`) support "commit only after success" in principle. Note that `require_complete_update` accepts an empty `update_progress` as complete (`:131-134`). Schedule metadata must not rely on that path.

## Limits

- Static reading only. No schedule test was rerun. The 5 passing tests in `test.log` are recorded output, not re-verified.
- `runner.py` pins, `parent_adapter` byte pins, and the cost-anchor cumulative-to-phase offset (`parent_adapter.py:60`: phase 360 ↔ cumulative 408, offset 48, consistent with 324 ↔ 372) are read as source claims. Not checked against the files they pin.
- Not read: `identity.py`, `dev_eval.py`, `critic_diagnostics.py`, `registration_schema.py`, `models/teacher.py`.
- The selected branch rejected the endpoint-360 run (`parent_adapter.py`; `runner.py` docstring). The new run's updates 325..360 use decaying LR, not the constant `3e-5` used in the discarded branch. Intended by the draft, but the design should say so.

## Verdict

- The helper arithmetic and the atomic-validation design are sound as static reads. Not verified by execution.
- Not integration-ready. Blockers: finding 1 (counter binding), finding 2 (design names the wrong code and counter), finding 3 (runner invariants and pins need a new registration).
- Findings 4-8 are draft-level gaps. Fix before integration, not a reason to stop the draft.
- No launch or campaign-approval requirement follows from this review. It is a draft needing integration work.
