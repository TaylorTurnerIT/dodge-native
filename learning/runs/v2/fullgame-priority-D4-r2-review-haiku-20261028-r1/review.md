# Independent narrow successor review: D4 terminal60 evaluator r2

Reviewed: `learning/runs/v2/fullgame-priority-D4-evaluator-sonnet-20261028-r2/`
Predecessor (left untouched): `fullgame-priority-D4-evaluator-sonnet-20261028-r1`, reviewed in `fullgame-priority-D4-review-haiku-20261028-r1` (source `f766afb8...`).

Source manifest SHA-256: `daaa54babd0537f712a6bf45b936b9d5c52b6531598c4f264890eda9b1cafacf` (re-verified, 18 members match disk, no unlisted sealed-type files).
Package manifest SHA-256: `3e3e55276b329e3cac634bddcee2077ce45b92f49c28c53412cf51a3385c05a8` (19 entries match disk). Per-file hashes are in `review.json`.

Scope: read-only static review of the r1-to-r2 diff plus the integration evidence in `tests.py`. Writes limited to this directory. The 68-test suite was not executed here: it writes to temp directories outside this review's output, and the brief allows test runs only when all writes are the reviewer's own output. The reported `68 OK, 0 skipped` is a recorded claim (package manifest `tests` field); the count of `def test_` in `tests.py` is 68. No torch, numpy, MPS, native environment, checkpoint deserialization, D4/D5 outcome, ledger, lease, marker, launch or commit. The five-run training operator was not touched.

## Verdict

No blocking findings. The r2 changes repair M1 and M2 and the per-episode cap as far as static review and the integration tests can show. Launch authority is not implied. Source proof is not runtime qualification.

## Disposition of prior findings

- **M1, postflight outside the wall budget: resolved.** `total_seconds = work + CLEANUP(10) + POSTFLIGHT(120)` is enforced in `binding.py:190-198`, the builder uses it (`build_registration.py:87`), the calibration carries `postflight_allowance_seconds`, and `binding.py:369-370` checks it. The observer's SIGALRM is re-armed to `hard_at` after the worker exits (`observe.py:298`), so the success path gets up to `total - work` = 130 s after a worker that finishes at `work`. The timeout path still TERMs at `work` and breaks at `term_sent+10` (`observe.py:280-296`), so the worker never gets the 120 s. Arithmetic: 17141 + 10 + 120 = 17271 (`policy-plan.json`, README). The 120 s allowance is 1.53x the linearly scaled prior gap (9.40 s x 8.34 = 78.4 s).
- **M2, no integration tests: largely resolved, with a coverage gap.** `WorkerRun` (`tests.py:895-996`) calls the real `worker.run`, `Guard`, `comparison`, `paired_statistics`, `terminal.validate_outputs` and `validate_checkpoint`; only the native loop, torch/MPS/numpy, the checkpoint loader and the runtime authenticator are faked. `ObserverRun` (`tests.py:1012-1080`) calls the real `observe.main` with a real `Popen` stub child and real Darwin `waitid`. It injects `clock`/`sleep`, so the real SIGALRM path is not exercised (finding 2).
- **Per-episode cap (r1 L3): resolved.** `worker.py:54-64` counts gameplay frames per `(policy_id, episode_index)` and raises after the journal row and before `evaluation_completed` is emitted. The limit is 18000 (`binding.SEMANTICS['raw_frame_cap']`), the same quantity `terminal.py:39` checks post-run, so the two agree. Exact 18000 is allowed (`tests.py:162-173`).

## Event semantics checked

- Constructor frames (13) go into `raw` and `constructors`; step frames (`elapsed_raw_frames`, 1 to 4) go into `raw` and `steps`. `RAW_CAP = 7168 x 18013 = 129,117,184` covers startup plus gameplay. The per-episode cap counts gameplay only, which matches terminal's `gameplay_frames`.
- The native loop (`progressive1000-...-r1/expanded_eval.py:64-123`) emits constructor, step and completed events in journal order. Its row validator (`expanded_eval.py:38`, `:53-55`) requires truncated rows to have `gameplay_frames == alive_frames == 18000` and terminated rows `alive+1 == gameplay`. The new cap therefore does not misclassify truncation: a truncated episode sums to exactly 18000 and passes.
- `terminal.py:62` requires worker `elapsed_seconds < work_seconds`. Worker and observer share the origin `envelope['started']` (`launch.py:40`, `worker.py:31`), so the three work-deadline checks agree.

## Findings (all non-blocking)

1. **Low, test determinism. `ObserverRun.test_success_with_postflight_inside_registered_headroom` (`tests.py:1049`) can fail under load.** `begin = WORK-30` = 970 s. The first loop iteration sees `now = 970`. If the stub child has not been reaped by that first `observe_exit` (`observe.py:257`), `FakeClock.sleep` (`tests.py:1007-1010`) advances the clock by 50 s to 1020. The second iteration then latches `external_work_deadline` (`observe.py:279`) and the run exits 1, failing the assertion. Passing depends on child start-up and `ps` finishing before the first poll. Consequence: a flaky test, plausibly worse while the training operator is running. Fix: make the first step small near `term_at`, or wait for the child to exit before the first observer poll in the test.

2. **Low, coverage. Real SIGALRM arming and re-arming is not tested.** Every `ObserverRun` case passes `clock=`, so `use_timer` is False (`observe.py:168`) and the timer code is skipped: arm at `term_at` (`observe.py:220-222`), re-arm to `hard_at` after the loop (`observe.py:298`), re-arm on failure (`:316-317`), restore (`:391-395`). By reading, these align: `term_at = started + work` and `hard_at = started + total`. The `deadline_alarm` handler (`:210-219`) raises `Cancelled` when the alarm fires outside launch, so a postflight that runs past `hard_at` fails closed. The arithmetic is consistent, but nothing exercises it. Consequence if the reading is wrong: a success path whose postflight is cut at `work` would fail after the full 17141 s run and need incident handling. Fix (test-only, `observe.py` stays byte-identical): one Darwin real-timer timeout case with `work` = 2 s, expecting `elapsed <= work + 10`, plus one real-timer success case.

3. **Low, acceptance. The calibration acceptance is still checked by hash only** (carried from r1 finding 9). Postflight is now a parent-facing number. `finalize_registration.py` and `binding.verify_bound` do not check that the acceptance restates work 17141, postflight 120 and total 17271. Fix: the acceptance must carry those values, and finalize must compare them against the draft before copying.

4. **Info. No mutation-style tests exist despite the brief's expectation.** Coverage is behavioural. Removing the per-episode check fails `test_guard_per_episode_cap_checked_after_journal_row` (`tests.py:162`) and `test_per_episode_cap_fails_before_episode_result_with_journal_conserved` (`tests.py:944`). Removing the postflight term fails `test_limits` and `test_postflight_allowance_is_separate_from_work_and_cleanup` (`tests.py:105`, `:121`) and `test_postflight_beyond_registered_headroom_fails_closed` (`tests.py:1063`). No code-mutation harness was run here.

5. **Info. The 120 s allowance rests on one prior sample.** The 9.40 s gap is for 15.5M frames on one run. Scaling linearly to 129M frames gives 78.4 s, which is conservative for the fixed parts (worker teardown and `ps` polling) but has no variance estimate. The bound is fail-closed (`deadline_consumed`), so exceeding it causes an incident, not a silent overrun.

6. **Info. Timeout-path total wall can still reach `work+130`.** After cleanup, failure accounting in `finally` (`observe.py:341-346`) runs up to `hard_at`. This is by design, since the worker never gets that time. Noted for the wall-time expectation.

Carried limits from r1, unchanged and accepted: receipt contents pinned by hash only (`binding.py:241-275`); reset0 by construction; self-reported MPS; quadratic `resources.jsonl` reads (`observe.py:268`); journal disk about 15.7 GB worst case; parent acceptances hash-only.

## Expected-runtime note

The worst-case bound is 17141 s of work. The README's "about 12 min" expected figure assumes the six priority policies survive about as long as the prior evaluator's 7168 episodes (15.5M raw frames). That assumption is untested. The bound covers the full 129M-frame ceiling, about 3x the linear 5710 s estimate.

## Required checks before registration, calibration, gate and launch

1. Six producer audits accepted. `build_registration.py --check` currently shows 2 of 6 ready and exit 3. `build()` refuses until all six are ready, so no draft exists yet.
2. Draft limits: `work_seconds` 17141, `total_seconds` 17271, `cleanup_seconds` 10, `calibration.postflight_allowance_seconds` 120, `source_manifest_sha256` `daaa54ba...`, `status` `source_review_pending`, `parent_accepted` false.
3. Independent source acceptance of `source-manifest.json` `daaa54ba...` and the 18 member hashes in `review.json`, with the registered `status: accepted_source_review_only`.
4. Calibration acceptance pinned by hash, restating work 17141, postflight 120, total 17271, and labelled as a worst-case bound (finding 3).
5. Gate acceptance with the exact `registration_sha256`, every `binding.GATES` entry `passed`, and byte-pinned review records.
6. Live preflight: operator quiescent, lease free, marker absent, disk free space at least about 16 GB above the expected journal, and the `cancel` file absent.
7. Recommended before launch: the real-timer timeout test (finding 2) and a run of the ObserverRun success case under load (finding 1).
8. Re-run the recorded test command `PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=<package>/tests-pycache python/.venv/bin/python -B tests.py` once in a clean environment. This review did not reproduce the 68/OK result.

## Limits of this review

Static and fake-facade evidence only. The six real producer checkpoints have not been deserialized. The native `_production_rows` loop, torch/MPS, the real checkpoint loader and the real runtime authenticator were not exercised. The real SIGALRM path is not covered by tests. None of this qualifies the native runtime.
