# D2 retained324 finalizer source review (relocated execution)

Scope: source-only read review. No imports, tests, subprocesses, or finalizer execution. Only read-only hash, `cmp`, `ls`, and `grep` checks were run.

## Verdict

No blockers for the relocated execution as proposed (byte-copy of reviewed `finalize_parent.py` into `learning/runs/v2/D2-retained324-parent-terminal-audit-20261026-r1/`, executed once from there). Caveats below, one medium.

## Relocated execution checks

- Path depth: `ROOT = Path(__file__).resolve().parents[4]`. From the target dir, parents[0..4] reach `learning/runs/v2/...` and then the repo root, same depth as the prep dir. `ROOT` is correct. `OWN` resolves to the target dir. All `write()` outputs and `relative_to(ROOT)` paths land there. Confirmed.
- Byte identity: `cmp` shows the target copy identical to the reviewed source. SHA-256 is `02fc54416758aa5426b614d739e61f6683a5c60d1752127b42107f3252cd1393`, matching the prep `output-manifest.json`.
- Collisions: target dir currently has no `audit.json`, `completed-iteration-receipt.json`, `retained-best-decision.json`, `report.md`, or `state-*.json`. Exclusive `"x"` writes will not collide now. Existing files present: `artifact-inventory-check.json`, `full-audit-command.json`, `full-audit-raw-exit.json`, `full-audit.log`, `preaudit-process-check.json`, `review-reconciliation.json`.
- Hardcoded inputs are absolute-by-construction from `ROOT`, not from `OWN`. `PREP`, `RUN`, `OBSERVER`, `AUDITOR`, and `OLD_RECEIPT` point to the same locations regardless of where the script lives. Relocation changes only the output directory.
- Ledger path: `registration.json` `state_path` is `learning/runs/v2-orchestration/state.json`. `cancel_path` is `learning/runs/v2/D2-retained324-continuation-20261026-r1.cancel`. The finalizer task key `retained324_terminal_finalizer_prepare_luna_20261026_r1` exists in the ledger (one match).
- Lease state: a grep of `active_long_campaign` in the ledger matched three lines, one an object and two `null`. The top-level value is not confirmed by this read. The script's `validate_parent_guard` will refuse to proceed unless `state["active_long_campaign"]` equals the registered lease exactly. Parent should rely on that runtime guard, or verify the top-level value by a non-executing method.

## Caveats

1. **medium** `finalize_parent.py:136-239`: partial-failure ordering. `audit.json`, `completed-iteration-receipt.json`, `retained-best-decision.json`, and `report.md` are written before the ledger guard and replace. If the guard or byte compare fails after line 177, those files remain marked accepted, the lease stays set, and the ledger is unchanged. The `"x"` mode then blocks any rerun. This matches the "no rerun/retry" policy but leaves an accepted-looking receipt set without ledger acceptance. Parent should record this state if it occurs.
2. **low** `finalize_parent.py:233-240`: `NamedTemporaryFile(delete=False)` leaves a `.retained324-finalize-*` temp file in the state dir on any failure before `os.replace`. Not cleaned up.
3. **low** `finalize_parent.py:128-134`: `os.killpg(pgid, 0)` raises `PermissionError` on EPERM, which is not caught. It aborts after the audit files are written (same partial state as caveat 1).
4. **low** `finalize_parent.py:221`: `latest_completed_cumulative_updates=432` is a literal. It is not asserted against `worker["cumulative_counters"]`. Unverified by this review.
5. **low** `finalize_parent.py:225-227`: the selection-policy and receipt-pointer checks compare the same file read twice, so they are only stale-vs-current checks. They do not compare against any independent original.
6. **README stale after relocation**: `README.md` line 3 says the explicit invocation writes "this directory", meaning the prep dir. After relocation the writes go to the audit dir. The prep README and prep `output-manifest.json` do not list the target copy. Parent should record the target copy SHA `02fc5441...` in the audit or ledger receipt. The audit does not currently record the script hash.
7. **Do not execute the prep copy.** If run from the prep dir, `OWN` is the prep dir and the outputs would land there, contrary to the README's "does not write the preparation" intent. Relocated execution avoids this.

## Helper controls (four claimed; none run here)

1. `test_import_has_no_finalization_call` (`test_finalizer_controls.py:16-19`): AST check only over top-level `tree.body`. Catches a bare top-level `finalize_parent()` call. Misses calls nested in `with`/`try`/`if` at module level. Weak, but accurate for what it claims.
2. `test_exact_lease_and_no_inference_synthetic` (`:22-37`): real. Exercises `validate_parent_guard` with wrong lease, inference lease, cancel file, and `cancel_requested=True`. Accurate. Does not cover the positive path with inference keys set to falsy values, and does not exercise the full flow.
3. `test_concurrent_ledger_change_synthetic` (`:40-48`): accurate but trivial. It tests a two-line byte-compare helper. It does not test that `_validate_and_prepare` calls it at each boundary.
4. `test_incumbent_and_no_replacement_literals_are_pinned` (`:51-57`): string-containment on source. Passes if the literal text is present, even in dead code. Not a behavioral check.

Net: the controls exercise only helpers. They do not exercise the publication path, `os.replace`, or the process checks. Passing them is not evidence of finalizer correctness.

## Limits

- Not verified: numeric literals (means, 13846 pins, counters 983040/7680, resource caps, 1066.47 observer seconds) against `full-audit.json`, `observation.json`, `worker-result.json`, or `development-000324.json`. The script asserts most of them at runtime.
- Not verified: `full-audit.json`, `review.md`, `bootstrap.py`, `wrapper.py` contents. Only the script's runtime hash checks were reviewed.
- Not run: the four helper tests, any finalizer path, any subprocess.
