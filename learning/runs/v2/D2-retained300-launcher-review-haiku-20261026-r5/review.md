# Read-only static review: D2-retained300 launcher execute_once.py (r5)

Scope: `learning/runs/v2/D2-retained300-launcher-luna-20261026-r5/execute_once.py`, sha256 `7215ae6628c364fe74bafba68e66cb1c688000a3b7d648dba9248fc2d812310e`. Reviewed against immutable base `D2-retained276-lr3em5-prepare-luna-20261026-r2/execute_once.py` (sha256 `fd7298a8d6a7885a341c2f5c5d1eb4c5e407654a579f15403f9f342fffc8aa2d`), the addendum, manifest, test file, and the parent integration contract. No execution, imports, tests, or writes outside this review directory.

## Verdict

No blocking findings in `execute_once.py`. Two non-blocking defects should be fixed or explicitly accepted before parent integration (F1, F2). This is not launch qualification. The fixture tests are synthetic and do not qualify integration.

## Verified (from the diff and file read)

- **Pre-mutation preflight.** `r.read` → `validate_identity` → `r.load_registration(registration, registration_sha)` now run before `out.mkdir` and the launch marker. Base ran full load inside `try` after marker creation. Moved, not added, so no extra load.
- **One-shot.** Marker is written with `r.save`. In the base runner that uses `open("x")`, so it is exclusive and a second launcher fails there. That failure sits outside `try` and does not clobber `execution-result.json`. The `worker.log` open with `"x"` is a second exclusive guard. Base runner is the only one read. R5 runner was not read (excluded as mutating), so this is unverified against the R5 runner.
- **Actual subprocess path.** `popen(command, env, cwd=reg["root"], start_new_session=True, stdout=log)` with `command = [interpreter, "-B", runner_path, "--registration", ..., "--registration-sha256", ..., "--started", ...]`. Unchanged from base.
- **Terminal checks.** Worker raw exit 0, owned group absent after leader reap, postflight `load_registration`, finalization/publication deadlines, and return code logic are unchanged.
- **Cleanup.** `stop_owned` (5 s TERM, 5 s KILL, exact owned pgid, refuses pgid of self) is unchanged. Called only if the group is not already marked absent.
- **Deadline.** `started` is taken before preflight, so preflight counts toward `work_seconds` (1790) and `total_seconds` (1800). The new preflight check `clock() - started < work_seconds` is additional. Per-loop total-deadline checks unchanged.
- **Counters.** Launcher uses `r.PHASE_START`, `r.PHASE_END`, `r.NEW_UPDATES`, `r.PARENT_LOCAL_UPDATES`, `r.PARENT_TOTAL_UPDATES`, `r.EXPECTED_TOTAL`, and checks parent `phase_update==PHASE_START`, `local_update==PARENT_LOCAL_UPDATES`, `cumulative_counters.updates==PARENT_TOTAL_UPDATES`. Integration contract values (300/360/24/348/60/408) match what the launcher expects. Base runner still has 276/324/72/384, which is expected parent work.
- **LR.** Launcher uses `r.LEARNING_RATE` and `r.assert_saved_optimizer_lr(...)` for parent and entry states. `lr-transition.json` check removed. Line 85 still hard-codes `0.00003` (inherited, see below).
- **Signature.** `validate_parent_checkpoint_for_restore(state, checkpoint_sha256=PARENT_SHA, receipt=None)` in base runner matches the three-argument launcher call.

## Findings

### F1 — medium — addendum misstates entry-restoration receipt checks (new)
- File: `learning/runs/v2/D2-retained300-launcher-luna-20261026-r5/contract-addendum.json:7`; launcher `execute_once.py:118-127`.
- Addendum says launcher expects `entry-restoration.json` with `learning_rate` 0.00003, empty `changed_fields`, parent receipt/config/checkpoint hashes. Launcher actually checks `before_environment_or_gradients is True`, `parent_sha256 == PARENT_SHA`, `matched == {model,Adam,RNG: True}`, and per component `matched`, `mismatch_paths == []`, `expected_sha256 == restored_sha256`.
- Trigger: parent/runner author builds the receipt from the addendum's field list.
- Consequence: runner output that matches the addendum but lacks `before_environment_or_gradients` or per-component `components` fails at launch time, after the one-shot marker. LR is checked elsewhere (via checkpoint state), so the addendum's LR check is not enforced by the receipt.
- Classification: new. Integration/doc dependency. Fix addendum to list actual launcher fields, or add the addendum fields to the launcher.

### F2 — low-medium — entry checkpoint is not identity-bound (new)
- File: `execute_once.py:128-133`.
- `entry_certificate["checkpoint"]` is read from a worker-written JSON and loaded with only `require_complete_update` and `assert_saved_optimizer_lr(LEARNING_RATE)`. Candidate checkpoints (lines 207-225) get path-name, sidecar, phase, counter, `inherited_counters`, `registration_sha256`, `parent_checkpoint_sha256`, and `config_sha256` binding. Entry does not.
- Trigger: entry certificate points to a different complete checkpoint at LR 3e-5 (e.g., a stale or wrong-phase checkpoint).
- Consequence: entry state's phase, counters, parent lineage, and registration identity are not verified by the launcher. Partial mitigation: `entry-restoration.json` pins model/Adam/RNG to parent sha, and entry evaluation rows are compared to the predecessor (line 235).
- Fix: apply `validate_terminal_candidate_binding(entry_state, PHASE_START, zero counters)` and check `inherited_counters == parent cumulative`, `parent_checkpoint_sha256`, `registration_sha256`, plus path name equality, mirroring lines 207-225.

### F3 — low — preflight failures leave no execution receipt (new, design-consistent)
- File: `execute_once.py:292-299`.
- `validate_identity`, `load_registration`, and the deadline check run outside `try` and before the marker. A failure raises an uncaught exception: no `execution-result.json`, no `publication-failure.json`, no marker.
- Trigger: invalid pin, stale lease, or preflight beyond 1790 s.
- Consequence: nonzero exit with traceback only. One-shot is not consumed (intended by the addendum: "before ... marker creation"). Parent must treat "no marker, no result" as a preflight failure. Acceptable if documented.

### F4 — low — test coverage gaps (new)
- File: `test_launcher_contract.py` (the four tests).
- The fixture does not exercise `validate_outputs` (entry-restoration, entry-checkpoint, counter, or cumulative branches). The AST test asserts `load_registration` and `check_lease` are called in `execute`, but not that `load_registration` precedes marker creation. The preflight-deadline branch (line 295) is untested. Fixture result counts (four passed) are synthetic and do not qualify integration.

## Inherited, unchanged (not blocking)
- Line 85: `validate_terminal_candidate_binding` hard-codes `0.00003` while elsewhere `r.LEARNING_RATE` is used. Consistent today; drift risk.
- Lines 398-404: `execution-result.json` may say `status: "passed"` while return code is 1 (publication budget overrun). Known base behavior.
- Lines 396-397: `execution-result.json` save failure escapes `finally` without return code. Base behavior.
- `stop_owned` and the 5/5 s TERM/KILL policy: unchanged.

## Scoped integration dependencies (parent work, not launcher defects)
- Runner must export `LEARNING_RATE=0.00003`, `PARENT_LOCAL_UPDATES=24`, `PARENT_TOTAL_UPDATES=348`, `PHASE_START=300`, `PHASE_END=360`, `NEW_UPDATES=60`, `EVALUATION_UPDATES=(300,312,324,336,348,360)`, `EXPECTED_TOTAL=408`, `LIMITS` with `work_seconds` 1790 and `total_seconds` 1800, selected300 parent narrow-clock constants, and `continuation_cumulative_counters`, `validate_gradient_alignment`, `validate_episode_journal`, `performance`, `Cancelled`. Base runner has 276/324/72/384 and no `LEARNING_RATE`. The addendum's runner-export list omits `EXPECTED_TOTAL`, `NEW_UPDATES`, and `EVALUATION_UPDATES`.
- R5 runner was excluded. `r.save` exclusivity, `load_registration` pre-mutation semantics, and entry-restoration writer are unverified against the R5 runner.

## Limits
- Read: launcher, base launcher, addendum, manifest, test file, integration contract, and the top-level keys of `evidence-map-reconciliation.json`. The full evidence map was not read beyond keys and status (`evidence_map_accepted_with_parent_corrections;not_launch_qualification`).
- Not read: `launcher-source.diff` and `test-results.txt` contents (hashed only), parent adapter validation files, mutating R5 runner, R6 builder. Launcher-source diff vs. file equality was not verified.
- Not executed. No imports, tests, MPS, environment, training, ledger, lease, or source changes.
- Known builder `prepare_registration.py` defects intentionally excluded.
