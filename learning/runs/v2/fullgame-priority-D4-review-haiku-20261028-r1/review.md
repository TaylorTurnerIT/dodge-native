# Independent review: D4 terminal60 evaluator package

Reviewed: `learning/runs/v2/fullgame-priority-D4-evaluator-sonnet-20261028-r1/`
Source manifest SHA-256: `f766afb84bfce0e6f2cbdd25a233781da1382dd73d1cd54ae949a43aed995c04` (re-verified; all 18 owned members match).
Package manifest SHA-256: `a991b56dd83246db65edeeb1753828611c12053fdbe7ed45d8c465f879c95856` (19 entries, all match).

Scope: read-only static review, plus stdlib-only checks. No torch, numpy, native, MPS, checkpoint deserialization, D4/D5 outcome, ledger write, launch or commit.

## Verdict

No blocking source findings. The package is a sound source basis for registration, subject to the non-blocking findings below and the prerequisites at the end. Launch authority is not implied.

Non-blocking findings, ordered by severity:

1. **Medium. Postflight time is not in the wall budget.** `build_registration.py:87` sets `total_seconds = work + 10`, and `binding.py:188` enforces that equality. `observe.py:194` makes `hard_at` equal `started + total_seconds`. The observer runs `terminal.validate_outputs` and `verify_bound` after worker exit (`observe.py:306-307`), and `terminal.accounting` after that (`observe.py:342`). Those steps read the full journal (strict) and re-run `validate_static`. The 10 s margin covers only cleanup in the README's model. The prior proven run had observer wall 694.33 s against worker elapsed 684.92 s, a 9.4 s non-worker overhead at roughly one-eighth of registered journal size. Scaling that by about 8.3x gives a postflight estimate of roughly 80 s, well above 10 s. Trigger: the worker finishes within that postflight time of `work_seconds`. Consequence: `deadline_consumed`, status `failed`, and a finished 7168-episode run needs incident handling. This is fail-closed, not a cap loophole. Fix: add an explicit postflight allowance to `total_seconds`. Fix now, because a source change needs a new package revision (`seal.py` forbids resealing a reviewed predecessor).

2. **Medium. Worker runtime path has no pre-attempt execution coverage.** `tests.py` (53 tests) covers statics, the `Guard` counters, synthetic terminal outputs, tamper cases, and the producer chain. No test drives `worker.run()` (`worker.py:85-150`) or `observe.main()` with stubs. Trigger: any defect in the new worker-only code (constructor/step counters, `comparison` module, `report` naming, parent and producer checkpoint branches) on the first real run. Consequence: the single attempt is spent. Mitigation: `observe.main` already accepts `popen`, `clock` and `sleep` injection, so a fake-worker integration test plus a stubbed `ckpt`/`teacher`/`_production_rows` test of `worker.run()` is feasible without torch.

3. **Low. Per-episode cap is checked only after the run.** `terminal.py:39` enforces `gameplay_frames <= 18000` per episode. The worker enforces only the global raw ceiling (`worker.py:32`, `58`). Trigger: a native episode over 18000 frames. Consequence: the run completes, then fails in postflight (overlaps finding 1). The global bound still holds. Fix: add the same per-episode check in `Guard.journal`.

4. **Low. Process receipts are pinned by hash only.** `binding.producer_policy` (`binding.py:241-275`) pins `parent-execution.json` and `execution-exit.json` but never reads their contents. Trigger: an exit receipt that disagrees with the audit (nonzero `raw_observer_exit_code`, wrong `registration_sha256`). Consequence: an inconsistent producer is accepted. Fix: assert `raw_observer_exit_code == 0`, `observer_directly_reaped`, and matching `registration_sha256` in both files. Verified in the one accepted producer I could read: `execution-exit` has code 0, direct-reaped and the right registration SHA.

5. **Low. `resets` is declared but not telemetered.** `binding.py:192` and `build_registration.py:88` fix `resets = 0`. `Guard.journal` counts only constructors and steps. In the current code paths, `_production_rows` never resets an env (it constructs once, steps, and deletes at terminal), so the value holds by construction, but nothing counts it.

6. **Low. MPS cap is self-reported.** `worker.py:39-40` reads `driver_allocated_memory` inside the worker. `observe.py:273` checks only the worker's own `resources.jsonl`. RSS is independently sampled by the observer via `ps` (aggregate). Accept as a limitation.

7. **Low. Observer cost grows with run length.** `observe.py:268` calls `b.worker_resources(out)` on every loop iteration, re-reading the whole `resources.jsonl`. At projected length (about 30k rows over roughly 5,700 s) this is quadratic and takes a noticeable share of one core. SIGALRM still enforces deadlines. `observe.py` is byte-identical to the proven source, so changing it would need re-proof. Accept.

8. **Low. Journal disk growth is not budgeted.** The prior run wrote 471 MB for 3.85M steps (about 122 bytes per line). Registered worst-case steps (129M) would be roughly 15.7 GB. Free space on the volume is about 305 GiB. Add a free-space check before launch.

9. **Low. Acceptance content is trusted beyond the hash.** `finalize_registration.py` checks only the calibration acceptance's SHA. `binding.verify_bound` checks only the source acceptance's `source_manifest_sha256`, not its status (`launch.py` does check `accepted_source_review_only`). These are parent-authored; a schema check on the calibration acceptance (for example `work_seconds == proposed_work_seconds`) would be cheap.

10. **Info. No cap overshoot allowance.** The raw ceiling is checked after each event against an exact sum (`7168 x 18013`). Overshoot is at most one native step (at most 4 frames), already spent and counted. The full worst case is bounded.

11. **Info. `worker_group_absent` is not a blocker.** `observe.py` `finally` sets `owned_group_absent=absent, worker_group_absent=absent` unconditionally.

## Verified

- **Supervisor byte identity.** `observe.py` (`95b8758e...`) and `execute_once.py` (`48440567...`) are byte-identical to the proven progressive1000 evaluator. Source-manifest members all match disk.
- **Clean source and runtime.** Clean source manifest `51aa867e...` and runtime manifest `84e730ee...` match. The runtime file set is exact (12 members). Producer runtime `e032a5ab...` differs from clean only in `dodge_rl/ppo.py`, `dodge_rl/seed_priority.py`, `dodge_rl/seeded_training.py`, all outside the inference member list. This matches the Sonnet claim.
- **Identity reproduction.** Calling `binding.learner_identity` on the producer `replica-1-uniform` registration reproduces the sidecar `identity` exactly, and `identity_hash` equals `identity_sha256` (`3c1e83eb...`). The raw unsorted producer `exclusion_union` is used for identity; only the evaluation registration sorts it. Identity and lineage are unchanged.
- **Producer chain, read-only.** `producer_policy` passes for `replica-1-uniform` and `replica-1-opening_priority`, covering registration identity, audit status and flags, lease release hash, output manifest, checkpoint/sidecar/worker-result membership, learner identity, endpoint fields, and runtime member bytes. `build_registration.py --check` reports 2 of 6 ready (exit 3, not 1 of 6 as in the manifest). Four producers are not ready; `replica-2-uniform` is still training.
- **Checkpoint compatibility, static only.** Clean `load_checkpoint` requires `version == teacher_checkpoint_v1`, `resume_mode == fresh_env`, and a matching identity hash. The producer writer (`fullgame-seed-priority-experiment-luna-20261027-r3/runtime_adapter.py:237`) sets these, and gates the save on `update_progress` complete and not in-update (same file, line 219), which matches `require_complete_update`. The parent checkpoint `c10d90ec...` already ran through this same loader and `validate_checkpoint` in the prior proven evaluator (completed, 7 policies). Residual first-load risk for the six producer checkpoints: model `strict` load and update-progress content are not verified without deserialization.
- **Import origins.** `contracts()` verifies all top-level SOURCE `.py` bytes and the exact runtime set. `authenticate_runtime` checks the origin and bytes of every loaded `dodge_rl` module. `driver_binding`, `runtime_adapter`, `fingerprints`, `death_telemetry` and `successor_identity` resolve to SOURCE through `sys.path` order, and their bytes are covered by the SOURCE manifest. No `comparison` or `paired_statistics` name collides with SOURCE.
- **Dependency pins.** `verify_dependencies` checks 13,513 files (0.83 s warm). `interpreter` bytes are pinned.
- **Cohort and cap arithmetic.** D4 `0xD4000000..0xD40003FF` and D5 `0xD5000000..0xD50007FF` match the registry, D5 unopened, D4 never in `excluded`, and the training pool is disjoint from D4/D5 (512 seeds). The exclusion union is sorted and merged, and it covers D4 and D5 as single ranges.
- **Wall derivation.** `ceil(3 x 684.9216 / 15,487,746 x 129,117,184 + 10) = 17141` recomputed exactly. Linear estimate is about 5,710 s (22,612 frames/s prior rate), so the registered bound is about three times the linear estimate. This is a hard bound, not an expected runtime.
- **Statistics.** `Worst` (min), `Q1` (bottom 256), `Mean`, `Q4` (top 256) and `Best` (max) match the spec. Milestones are 1000, 2000, 4000, 8000, 12000, 18000. Death-cause and cap counts conserve to 1024. Priority-minus-uniform is per replica, with a three-pair descriptive mean and min/max/stdev. The paired bootstrap uses 2000 draws, 95%, seed `2026102801`, shared indices across policies, and labels three-pair and extrema intervals as descriptive.
- **Evaluation RNG.** `random`, `numpy`, `torch` and `torch.mps` are reseeded to `2026102802` before each policy (`worker.py:117-118`). Sampling depends on batch composition (batch 64, active set), so the package does not claim per-seed common random numbers. Both `comparison.py` and `paired_statistics.py` document this.
- **Tests.** `python3 -B tests.py` ran 53 tests, OK. Writes were checked with a before/after SHA snapshot of the package and the ledger: none.
- **Parent gate.** Parent `324` identity and checkpoint path match `D2-retained300-continuation-20261026-r1` and `c10d90ec...`. Parent entry does not depend on any producer audit.

## Limits

- No deserialization, so producer checkpoint first-load behavior is static only.
- Tests are stdlib fakes. Nothing exercises torch, MPS, the native env, or the observer's real subprocess path.
- The mutable ledger (`state.json`, currently holding an active training-operator `active_long_campaign`) is not pinned. Lease checks are the only coupling, and the ledger is written with atomic `os.replace`.
- Parent-authored acceptances are checked by hash, with the exceptions noted above.

## Remaining prerequisites

1. All six producer terminal audits accepted (2 of 6 at review time).
2. Decide on findings 1 and 2 before registration. Each needs a new package revision, since the reviewed source is sealed.
3. Build the draft (`build_registration.py --output`), which refuses until all six are ready.
4. Independent source acceptance (`accepted_source_review_only`) for the final source manifest SHA.
5. Parent wall and resource calibration acceptance (17141 s, or a revised value).
6. Parent gate approval, with the registration SHA and every gate `passed`.
7. Operator quiescent and lease free before launch; disk free-space check.
8. Recommended, not blocking: fake-runtime integration tests (finding 2) before launch.
