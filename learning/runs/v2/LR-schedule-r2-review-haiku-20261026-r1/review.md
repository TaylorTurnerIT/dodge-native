# LR schedule draft r2: independent static review

Scope: static read only. No imports, tests, Python runs, subprocesses beyond `shasum` hashing, MPS, checkpoint, rollout, training, or environment access. No edits outside this directory. No launch, lease, marker, or campaign change. Current retained-324 control stays fixed `3e-5`.

Reviewed (immutable draft): `learning/runs/v2/LR-schedule-draft-luna-20261026-r2/{schedule.py, test_schedule.py, integration-design.md, results.md, frozen-manifest.json, test.log, sha256sums.txt}`.

Read for integration checks (read-only): `learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2/{runner.py, parent_adapter.py}`, prior round `learning/runs/v2/LR-schedule-draft-review-haiku-20261026-r1/review.md`.

## Hashes

- `shasum -a 256` matches `sha256sums.txt` and `results.md` pins for: `schedule.py` `35fee3a7…`, `test_schedule.py` `48165b0e…`, `integration-design.md` `3404f7c9…`, `results.md` `0f6413ea…`, `frozen-manifest.json` `8cbd1c22…`, `test.log` `6c6214f3…`.
- Frozen r1 `schedule.py` `24729b8e…` matches `results.md`.
- `D2 runner.py` `43e93f74…` matches `results.md`.
- Manifest `schedule_spec_sha256` `7ceed85c…` reproduced by hand: canonical sorted-key, no-space JSON of `SCHEDULE_SPEC` piped to `shasum`. Matches. This is the same canonicalization `schedule.py:26-28` uses, reproduced without Python.
- Manifest `schedule_source_sha256` equals the `schedule.py` hash above.

## Test evidence

- `test.log` shows 7 test names. First run: `FAILED`, raw exit 1, in `test_split_resume_exact_adam_state_and_group_lrs`, param mismatch at `assert_close` (max abs diff `6.9e-4`). Retry: `OK`, raw exit 0. Recorded output only; not re-run.
- Failure cause is a fixture bug, not a schedule bug. The first version did not copy saved params into the resumed optimizer. The fix at `test_schedule.py:114-121` copies them. Honest and retained in the log.
- `test.log` now records cwd, command, and interpreter, which fixes the r1 provenance gap.

## Prior round status

| r1 item | r2 status |
|---|---|
| 1. Counter not bound (silent restart) | Helper: mitigated. `apply_next_update_lr` requires `completed == actual - 372` (`schedule.py:103-104`). Local-counter or stale-counter misuse raises at first update. Residual: the helper cannot check that `actual` is the learner's real counter. See F3. |
| 2. Design names wrong code/counter | Fixed. Design cites `runner.py` lines 662, 668, 682, 699, 718-740, 741, 772, 773, 786, 811. All checked against the file. No `Trainer` references remain. |
| 3. Runner invariants and pins | Open, but correctly scoped as future successor work. `runner.py:680, 741, 772` still assert fixed `3e-5`. Pins at `runner.py:322-324` are still the registration. |
| 4. Missing-field fallback trap | Helper: fixed. Missing keys raise (`schedule.py:76-77`), non-Mapping raises (`:68-69`). Caller-default trap is documented as forbidden in the design. Enforcement is still future. |
| 5. Capped `completed` | Fixed. Uncapped (`schedule.py:113`). Tests cover 61st and resumed 62nd update (`test_schedule.py:50-59`). |
| 6. Count-only group check | Still count-only (`schedule.py:85-87`). See F5. Assessed below. |
| 7. Spec hash is declaration-only | Partly mitigated by source-byte pin. See F4. |
| 8. Test gaps | Mostly fixed. Full 60-step sequence (`:42-60`), per-group LR after resume (`:127`), missing key, float, and bool negatives (`:74-91`). Remaining: no test ties the formula string to code. |

## Findings (r2)

No draft-helper blocker found. Every item below is either integration work or low-severity hardening.

### F1. No runtime assertion of inherited cumulative count 372 (medium, integration)
- Where: `runner.py:131-134` is the only constant check, and it compares constants (`PARENT_TOTAL_UPDATES + NEW_UPDATES == EXPECTED_TOTAL`). It does not inspect the parent. `runner.py:682` copies `parent["cumulative_counters"]` unchecked.
- The 372 origin is enforced only by pinned bytes: `parent_adapter.py:29-32` requires `state["cumulative_counters"] == receipt["candidate_cumulative_counters"]`, and the receipt and checkpoint are SHA-pinned.
- Trigger: a successor calls `new_schedule_state(optimizer, actual)` at restore, using an actual count that was not derived from the parent, or a registration change that unpins the receipt.
- Consequence: wrong origin, so the decay is offset. The helper's origin check only protects the value passed in.
- Fix: add `need(inherited["updates"] == 372)` at the successor restore point, next to `runner.py:682`.

### F2. Helper trusts caller's `actual` (medium, integration)
- Where: `schedule.py:94-104`. The only independent check is `completed == actual - 372`.
- Trigger: a caller derives `actual` from schedule metadata (circular), or passes the wrong counter that happens to satisfy the same equation.
- Consequence: the helper passes silently. Wrong-local-counter misuse, the r1 case, is caught: local `0` gives `-372` and raises. Circular derivation is not caught.
- Fix: successor must pass `inherited["updates"] + counters["updates"]` from the runner's own counters (design says so; no code enforces it). Add an integration test that asserts `actual` equals the runner counter at every apply.

### F3. Same-count group limitation (low, accepted for draft)
- Where: `schedule.py:85-87` checks group count only, not membership.
- Assessment: the pinned runner builds one group (`runner.py:667`, `model.parameters()`), so count = 1 is effectively the full structural check there. `apply_next_update_lr` sets one LR across all groups (`schedule.py:110-111`), so a membership swap in a multi-group optimizer cannot change the LR values the helper writes. The remaining exposure is Adam state mapped to the wrong parameters. That belongs to `optimizer.load_state_dict`, which the helper does not touch. Not verified here: PyTorch's per-group size check is library behavior, assumed, not run.
- Caveat: the uniform-LR design would overwrite distinct per-group base LRs silently. Not an issue today; flag it if per-group LR is ever added.

### F4. Spec formula is a declaration string (low, largely mitigated)
- Where: `schedule.py:21-25` (formula string), `:43-50` (code). Test `test_schedule.py:47` hard-codes the formula in the test, not from `SCHEDULE_SPEC`.
- Assessment: the r1 concern was that a code edit leaves the spec hash unchanged. Any edit to `schedule.py` changes the source hash, so `verify_frozen_manifest` (`schedule.py:117-124`) fails. The residual gap is that a future versioned source could change the formula string and code together without updating the test. Low.
- Note: `verify_frozen_manifest` only runs inside the test. Nothing enforces it at runtime. Registration pins would have to carry it.

### F5. Test `test_metadata_rejects...` spec-hash line is tautological (cosmetic)
- `test_schedule.py:92-93` recomputes the hash with the same code path and compares it to the module constant. It does not compare against the manifest. The manifest is checked only by `test_frozen_manifest_binds_spec_and_source` (`:152-153`).

### F6. Staged metadata: LR mutates before PPO (verified safe, note only)
- `schedule.py:110-111` writes LR before `ppo_update`. Commit is a caller contract, not enforced. I checked the failure path: if PPO fails after LR is written, a retry with the same `actual` recomputes the same LR and the same staged dict. Resume from a committed checkpoint restores the checkpoint's LR, then `apply_next_update_lr` overwrites it. Idempotent. No bug.

### F7. Integration: fixed-LR runner asserts (blocker for successor, not for draft)
- `runner.py:741` (`assert_saved_optimizer_lr`) on every candidate checkpoint. `runner.py:772` (`assert_effective_lr`) before every `ppo_update`. Both fail once decay is applied (update 2 is `3e-5 - 2e-5/59`). Entry check `runner.py:680` still holds (parent LR `3e-5`).
- Successor needs new registration and runner pins (`runner.py:318-324`), new expected-LR logic at both asserts, and schedule metadata in the checkpoint dict (`runner.py:718-740`) with a required-field resume check.

## Integration design check

- Design claims at `integration-design.md:19-26` match `runner.py` line-for-line (listed above).
- Design: "Updates 373..432 linearly decay; 432 is `1e-5`." Checked: `c = 373` gives `u = 1`, LR `3e-5`. `c = 432` gives `u = 60`, `END_LR`. Runner local updates `1..60` map to cumulative `373..432` (offset 48 from phase, 372 origin). Consistent.
- Design: "Current retained-324 campaign remains fixed at `3e-5`." Confirmed by `runner.py:41, 667, 680, 741, 772`.
- Design does not state that the successor would change the phase `325..360` LR from the discarded endpoint-360 branch. r1 noted this. Still unstated; minor.

## Verdict

- Draft helper (`schedule.py` + tests, CPU synthetic): ready as a draft unit. Checked by reading, hashes, and recorded output. Not re-executed. No blockers.
- Integrated campaign qualification: not ready and not started. Needs the runner successor registration, runner edits (F7), explicit 372 assert (F1), a runtime `actual` source check (F2), schedule checkpoint field and resume validation, and path tests. Separate authorization required before any run.
- Current control: fixed `3e-5`, unaffected. The r1 review's note implying current training decays was wrong for the current run. Not propagated here.

## Limits

- Static reading only. No Python run. `test.log` is recorded output, not re-verified.
- Hashes via `shasum`, not Python. Manifest spec hash reproduced by hand-built canonical JSON.
- Assumed (not checked): PyTorch `load_state_dict` per-group size validation; `python/dodge_rl/checkpoints.py` behavior beyond `restore_learner` (`:138-142`).
- Not hashed: `parent_adapter.py` byte pins, `runner.py` pins other than `runner.py` itself.
- Did not check runtime checkpoint contents, MPS behavior, resource compliance, PPO correctness, or scientific validity.
