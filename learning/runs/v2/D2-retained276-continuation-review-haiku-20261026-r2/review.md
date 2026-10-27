# D2 retained-276 continuation: frozen source review r2

Reviewer: independent Haiku review, source-only. Target: `learning/runs/v2/D2-retained276-continuation-prepare-luna-20261026-r2/` (registration `477217f3…866c`, source manifest `0c11fd83…b37d`). Supersedes the r1 review, which missed the missing `progress=progress` binding.

## Verdict

**No launch blockers.** The `progress=progress` binding is correct and its CPU test reproduces the r1 defect and the fix. Post-success checkpoints are fully complete. Four low advisories and one partially open evidence note; none blocks launch.

## Delta from r1

- `runner.py` differs from r1 by two lines: `RUN_ID` `r1` → `r2` (line 56), and `progress=progress` added to the `ppo_update` call (lines 774–776).
- `execute_once.py`, `cpu_restore_and_controls.py`, `continuation-config.json`, and the three focused tests are byte-identical to r1.
- Registration pins: 13787 (r1: 13786). The 13774 non-owned pins match r1 by path and hash. Owned-directory pins point to r2 paths, and `test_worker_progress_binding.py` is added. All 13 owned pin hashes equal on-disk bytes.

## Progress binding

- Pinned `ppo.py` accepts `progress` (line 405). It writes only through `progress.update` and never branches on it.
- `ppo.py:416-417` sets `in_update`, `complete=False` on entry. `:532` records `optimizer_steps` after each step. `:597` sets `complete=True` on the single return path (`:600`).
- Failure record (`runner.py:817`) now reports `in_update=true` for a mid-update failure, matching the parent repro.

## Test evidence

- Reviewer ran `test_worker_progress_binding.py` once with the registered venv Python (`-B`, `PYTHONDONTWRITEBYTECODE=1`, pycache prefix in this review directory). Exit 0. Log: `progress-binding-test.log`.
- Results: failure with binding → `complete=false, in_update=true, optimizer_steps=1`. Missing binding → `complete=true` (reproduces r1). Success → `complete=true, completed_updates=1`.
- The test extracts the real runner call by AST, so removing the binding fails it.
- No `.pyc` was written by this run. Six pre-existing `.pyc` files in the pinned runtime (mtime 20:28) predate this review.

## Post-success checkpoints

Only save site is `runner.py:743`, inside `evaluate_at`, after completion. `completed_updates` is set at `runner.py:785`, before evaluation. So post-success checkpoints carry `complete=true`, `in_update=false`, and the completed update count. `require_complete_update` (`checkpoints.py:131-134`) accepts them.

## Advisories

- **A1 (low, evidence-accounting, partially open).** `r1-attempt-accounting.json` covers 2 of the 5 `retained_failed_attempts` entries in the frozen r1 receipt. Still wrong: `preflight-attempt-01.log` (receipt says runtime-continuity pin defect; log says `Full audit candidate set differs`), `cpu-restore-attempt-02.log` (receipt: misplaced fingerprint assertion; log: `SyntaxError`), `cpu-restore-attempt-03.log` (receipt: wall-clock nesting; log: `Saved endpoint metadata and receipt wall fields differ`). Fix in a new note; do not edit the receipt.
- **A2 (low, unchanged, accepted).** `runner.py:297` `validate_runtime_continuity` still compares the tree with itself. Runtime binding holds through `verify_pins` and `runtime_sha256`.
- **F3 (low, failure-accounting window, found by reading, not executed).** Between `ppo_update` returning (`runner.py:776`) and `completed_updates = update` (`:785`) there are raising checks (`:777`, `:778`, `:780`, `:781`, `:783-784`). A failure there records `complete=true` with `completed_updates = update-1`, though update N's optimizer steps are applied. No checkpoint is written on that path, so no restore consumes it. Optional fix: set the count right after `ppo_update` returns. Any code change needs a new RUN_ID.
- **F4 (low, test scope).** The success branch of the test sets `completed_updates` itself, mirroring `:785` instead of executing it. `TinyTeacher` stands in for the production model. The test does verify the `ppo_update` boundary through the real call, which is what it claims.
- **F5 (low, evidence label).** `scope.optimizer_steps: 0` in `preparation-receipt.json` and `validation.json` counts game-weight campaign steps. The CPU test does 3 synthetic PPO steps (`synthetic_optimizer_steps: 3`). Parent is clarifying scope externally, per brief.

## Residual risks

- MPS RNG restore is not exercised by any CPU test. Worker fails closed on fingerprint mismatch (`ed93fb48…`). Parent's unmocked preflight and actual run must confirm.
- Full unmocked preflight with the real exact lease is parent-owned. Preparation mocked only the lease assertion.
- Reviewer did not re-run source-contract, entry-counter, entry-evaluation, or CPU restore checks. Their results come from parent `validation.json`.

## Checks run

- sha256 of all 18 `source-manifest.json` entries against disk: 0 mismatches.
- Registration pin diff against r1, and owned-pin hashes against disk.
- Diff of `runner.py` against r1; byte comparison of unchanged files.
- AST extraction and CPU execution of the progress test (exit 0).
- Stale-path grep in r2 scripts and registration: only parent-run identifiers (`D2-retained204-lr1e4-…-r1`) remain, which is correct.
- sha256 of parent checkpoint, parent terminal receipt, selected metadata, r1 attempt logs, preparation receipt, and `validation.log`: match cited values.

## Limits

No children, no MPS, no checkpoint load, no environment construction, no training or probe, no lease access, no source or state writes. Output confined to this review directory.
