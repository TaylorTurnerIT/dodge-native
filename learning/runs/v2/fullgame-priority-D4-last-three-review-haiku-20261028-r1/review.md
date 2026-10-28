# D4 last-three evaluator independent review (r1)

Reviewed: `learning/runs/v2/fullgame-priority-D4-last-three-evaluator-sonnet-20261028-r1/`
Narrow diff base: `fullgame-priority-D4-first-three-evaluator-sonnet-20261028-r1` (accepted, root-audited, comparison `f08e8d7d...`).

Hashes:
- source-manifest `31a9c03e2e2524cbd522a44312923b021d0a3df20c596e1c7e14217ce3d568d4` (21 entries, 0 mismatches)
- package-manifest `dea1e10724aa76f2ddadffd26cb1eb0c6b4e286a221307954735ee4d1db69c54`
- registration-draft `2ee3b511ed1cb2d39f2993e2e8f71dcded30a251ffbfb0bad3d3cd31f4bea87b`

## Verdict

No blocking findings. This review does not authorize launch. Four low and medium items (F1-F4) are cheapest to fix now, before source acceptance. F5 is a calibration note.

## Findings

**F1 (medium, before source acceptance): merge does not check producer equivalence.**
- Path: `merge.py:136-162` (`cross_check`), values returned at `merge.py:62-63`.
- Trigger: a producer whose registration has a different `source_manifest_sha256`, `runtime_manifest_sha256`, interpreter, `runtime_versions` or `training_pool_sha256`.
- Consequence: the merge accepts a mixed-runtime six-model table. The directive asks for runtime equivalence across all six producers. Current data is uniform (all six share source `a29e25b285d2...` and runtime `e032a5ab1d60...`, same interpreter), so this is a missing guard, not a present error.
- Fix: add equality asserts across the six in `cross_check`, with a `merge_tests.py` mutation case. This changes `merge.py`, which is in the source manifest, so re-seal and rebuild the draft.

**F2 (low, before source acceptance): merge fixtures are degenerate.**
- Path: `merge_tests.py:20` (`DELTAS`), `:162` (`test_pairs_and_average_are_exact_shifts`), `:266` (stored-interval test).
- Trigger: real per-seed variation in which `merge.bootstrap` (`merge.py:200-225`) and `paired_statistics.paired_intervals` consume the RNG or sort differently.
- Consequence: every synthetic interval collapses to `low == high == delta`, so the stored-interval reproduction (`merge.py:228-234`) is not tested on non-degenerate data. A mismatch would refuse the merge after both parts are spent. The result is fail-closed, not wrong, but the final output is blocked.
- Fix: add a deterministic per-seed-varying fixture, assert pair-1 and pair-3 intervals reproduce the part-stored intervals with nonzero width, and add a tamper case for the first-part stored interval (the existing test edits only the last part).

**F3 (low, before source acceptance): real-chain test is weaker than its name.**
- Path: `tests.py:569` (`AUDITS`), `:579` (`continue`).
- Trigger: `replica-3-opening_priority`'s audit is removed or replaced, or any listed audit changes. The test passes while at least two producers were checked.
- Consequence: the test does not pin all three last-part audits. Data is fine today; the gap is in the test.
- Fix: pin the `replica-3-opening_priority` audit sha256 and assert that all three layouts exist instead of continuing.

**F4 (low, before source acceptance): stale documentation.**
- Path: `README.md:34` (skip claim), `:36` (Activation steps), `package-manifest.json` `readiness_at_preparation` and `unresolved_blockers`.
- Trigger: README says two sealed-package tests skip until sealing. The run has 0 skipped, because `source-manifest.json` exists and `FullRegistrationPath` runs (`tests.py:651-656`). Activation step 1 and the manifest still describe `replica-3-opening_priority` as training and no draft existing. All six audits are accepted and the draft exists.
- Consequence: a reader would conclude the package is not yet built. Nothing in code depends on these statements.
- Fix: update `package-manifest.json` (not pinned by the draft, so no rebuild needed). Update `README.md` in the same pass as F1-F3, since it is a source-manifest member.

**F5 (low, calibration note, not blocking): effective margin is about 1.54x, not 3x.**
- Path: `binding.py:216` (`projected_work_seconds`).
- The 3x factor is calibrated on the older seven-policy run: 684.92 s / 15,487,746 raw frames = 44.2 us/frame. The accepted first part measured 579.87 s / 6,720,672 raw frames = 86.3 us/frame, about 1.95x slower per frame. Scaled to `RAW_CAP` (55,335,936), that is about 4,775 s against the 7,352 s work limit.
- The expected run is about 10 minutes, so the hard stop is generous. If it trips, the single attempt is spent (fail-closed). Record the effective margin in calibration acceptance, or raise the factor if the parent wants 3x against the latest rate.

## Checks passed

- Tests run in place with `python3 -I -B` over `tests` and `merge_tests`: 97 run (86 + 11), 0 failures, 0 errors, 0 skipped. The evaluator directory's sha256 listing was identical before and after.
- `validate_static(draft, require_registered=False, runtime_files=True)` passes with `python/.venv/bin/python` and `PYTHONPYCACHEPREFIX=<pkg>/empty-pycache`. Cache and interpreter checks are process-level, so a plain `python3` fails them. That is an invocation issue, not a draft defect.
- `check_staging(draft)` and `check_layouts_against_remap()` pass.
- All 20 `merge.FIXED_REG_FIELDS` are identical between the accepted first part and the draft.
- Draft `input_pins`: 21 entries, 0 drift. Draft `source_manifest_sha256` equals the source-manifest hash.
- Supervisor files `observe.py`, `execute_once.py`, `power_guard.py`, `dependency-binding.json` are byte-identical to the first part (`tests.MinimalDiff`).
- First part, real artifacts: `verify_part(first, FIRST_PART_POLICIES, pins=FIRST_PART_PINS, producers=False)` passes. Registration-final `6912f25e...`, audit `f9fff56a...` (matches the ledger's `parent_audit_sha256`), source `489708da...`, comparison `f08e8d7d...`. Journal: 1,671,390 steps, 3072 constructors, 3072 completions. Output manifest matches the output directory.
- Producer JSON chains, all six: audit accepted, exit codes 0, observer reaped, `terminal_update` 60, lease released after durable audit, output manifest sha, checkpoint/sidecar/worker-result sha in manifest, endpoint equals sidecar, endpoint identity sha, `promoted`/`automatic_selection`/`training_eligible` False. `learner_identity` reproduces for all six. Checkpoint bytes were not rehashed.
- Work limit: `ceil(3*684.92/15487746*55335936+10) = 7352` reproduces.
- Main-state cap check (`binding.py:246-248`) matches the training lease shape (`remaining_plan.py:152-153`, cap 6442450944).
- Merge statistics arithmetic matches `paired_statistics.py`: same RNG draw order, same milestone difference identity, same quantile method. Per-model summaries match `comparison.summarize`.
- Merge refuses with `NotReady` while the last part has no `parent-terminal-audit.json`.
- No torch, native, or checkpoint deserialization in the merge or builder path. `contracts` imports `rng_reference` and `transition`, both stdlib.
- `observe.py`, `worker.py`, `terminal.py`, `audit.py`, `launch.py`: schema-name-only changes. No behavioural change.

## Carried, not reopened

- Torn-read latch on `state.json` (first-part F1): code unchanged. The parent accepts resolution through the writer protocol. Verified: recovery `replace_state` writes a pending file, then `os.replace`, then `fsync` (`start_remaining_one.py:32-40`). Required check: no non-atomic writer touches `learning/runs/v2-orchestration/state.json` during the window. External orchestrator writers are outside this repo and were not inspected.
- Prior F2-F7 unchanged.

## Limits

- The merge was not run on real D4 rows. Only the first-part chain and producer JSON chains were checked on real artifacts.
- No checkpoint deserialization, no torch, no native import, no MPS, no evaluation, no D4 or D5 outcome read.
- Live preflight not executed (power, disk, process cache, `active_inference_*`, own ledger and markers, caffeinate wrapper). Main-state `active_long_campaign` is null at review time.

## Finalization requirements

1. Decide F1-F4. If any lands, re-seal `source-manifest.json`, rebuild the draft, re-run `validate_static` and the 97 tests, then request source review of the new hash.
2. Source acceptance pinned to the final source-manifest hash and the final draft hash.
3. Calibration acceptance restating work 7352, cleanup 10, postflight 120, total 7482, prior 684.92 s / 15,487,746 frames, first-part context 579.87 s / 6,720,672 frames, and the F5 margin.
4. Gate document: schema `fullgame_priority_d4_last3_evaluation_gate_acceptance_v1`, every `binding.GATES` entry passed, `registration_sha256` of the final registration. Record `user_parallel_exception` as not used, since no training is running.
5. Final registration built only by `build_registration.py` after all six producer audits (all six accepted now). Status `parent_registered`; ledger and main state not pinned.
6. Live preflight: `active_long_campaign` null, no `active_inference_*` leases, own ledger and `attempt.claimed`/`launch.claimed`/output absent, AC power, launch as `/usr/bin/caffeinate -ims <python> -B launch.py` from the native root session. Disk checked against the worst-case journal (first-part `evaluation-events.jsonl` is about 177 MB).
7. Re-run `tests.py` and `merge_tests.py` in a clean environment with the recorded command if source changes.
8. Confirm no non-atomic writer touches `state.json` during the run window.
