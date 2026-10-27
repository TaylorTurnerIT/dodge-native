# Frozen source-only review: expanded-runner benchmark acceptance r4

Verdict: **No new blocker in the scoped R4 acceptance chain.** Source-only qualification of the R4 scoped acceptance changes (accepted-wrapper chain, benchmark receipt, lease key names, MPS fail-closed). **No launch clearance.** Ranking/confirmation stage use stays blocked on the High finding H-1. Supervisor items B4 and H2 are tracked in the separate supervisor-cleanup repair and are not demanded here.

## Scope and method

- Read-only. No runner, evaluator, native, torch, MPS, game, checkpoint, lease, marker, or shared file touched. Nothing executed or imported. `tests.log` read as text only; the 20 tests were not re-run.
- Read: `accept_benchmark.py`, `build_registration.py`, `execute_once.py`, `worker.py`, `test_runner.py`, `manifest.json`, `tests.log`; R2 `review.md` for carry-forward status.
- Ledger key names checked by read-only JSON key listing of `learning/runs/v2/user-best-checkpoint-policy-20261026-r1/state-after.json`. No code run.
- Caveman skill read per `/Users/taylor/AGENTS.md` and `~/.claude/CLAUDE.md`.

## Reviewed bytes (sha256, computed at review start, re-checked at review end)

| file | sha256 | matches manifest |
|---|---|---|
| accept_benchmark.py | 5f51cf1a3644702b72a22c5a42d717bbfdc9e6320b1108c2891702cb88ff7647 | yes |
| build_registration.py | 280650effba15ca1763707bbf054d081f6d4fb662da83f6a70a299243b07e8eb | yes |
| execute_once.py | 6ec8ab00d01daf15f9ff7d77be24ddac9ebb67af85abc844bd34e56da72f1570 | yes |
| worker.py | 2b5d25d07c671671e6f9a4fb2c976b02af2cb8372ace30ad2d05544bb18a83e4 | yes |
| test_runner.py | 6b1c1ec9f289587c3520c962dfee65b82cebc7017bb075ecdb351cf1d922ec73 | yes |
| manifest.json | 7ac3e6f13990b022e3a01fc85d4ba11697156e3c3b25a370811e3ef86868d3ed | n/a |
| tests.log | 9fcdbe179bd2301a63b895f8cb73082910ca034c536f9a3f6241e46380078306 | n/a |

Pins re-hashed at review and matching the constants in code:
- evaluator `a3439c33152b082471cd9f9a36ef4bb03783b9544ae7c1e3fe1878e607b128aa`
- proposal `187e0464ba966b29124b29cf606c831d7097adeea99ccfc0e336598ad3fc9765`
- accepted incumbent receipt `cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016`
- training registration `0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e`
- golden `d6e914345dcc955f678db41eb08d9f20af8e77490652f8d25f7ee09550a63a03`
- benchmark dev64 manifest `a57410e1848f8b35b874507afa21a4d90ced706efd3bd7a141e1dc3ad5df3695`
- native `022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e` (pins: `worker.py:9`, `execute_once.py:8`, `build_registration.py:12`)

## Status of R2 blockers and highs

| R2 item | R4 status | evidence |
|---|---|---|
| B1 `limits` NameError in ranking/confirmation draft | **Fixed** | `build_registration.py:80` defines `limits` before `reg` (`:82`); `test_runner.py:79-91` runs ranking and confirmation drafts. |
| B2 worker receipt vs builder format | **Fixed** | Worker writes canonical `expanded_eval_dev64_benchmark_receipt_v1` (`worker.py:196-200`). Exclusive wrapper (`accept_benchmark.py:23-26`). Builder rejects raw receipt (`build_registration.py:24`); launcher rejects raw receipt (`execute_once.py:83`). |
| B3 wrong lease keys | **Fixed in code, untested** | Code checks `active_long_campaign` (`worker.py:66`, `execute_once.py:130,234,267`). Ledger confirmed: `state-after.json` has `active_long_campaign` and `active_inference_diagnostic`; no `active_long` or `active_inference` keys. Fixture still uses the dead keys (see M-2). |
| B4 SIGTERM/SIGHUP bypasses cleanup | **Open, tracked separately** | No signal handler in `execute_once.py` (only `os.killpg` sends at `:288`, `:298`). Separate supervisor repair per scope. |
| H1 tests disable production checks | **Open** | `test_runner.py:16` sets `VERIFY_FROZEN_RUNTIME=False` and `VERIFY_PROPOSAL_CANDIDATES=False`; `:15` rewrites native and golden pins. Production checks at `execute_once.py:158,162` never run under test. |
| H2 `active_procs` failures escape receipt | **Open, tracked separately** | `execute_once.py:243-244` (handler), `:251`, `:255` (post-`try`) call `ps`-based `active_procs` unguarded. |
| H3 heartbeat freshness vs guard cadence | **Open** | `worker.py:157`, `execute_once.py:52`; evaluator guard cadence not verifiable from source here. |
| H4 MPS cap fails open | **Fixed for `mps` with torch loaded** | `worker.py:94` returns `None` when backend is `mps` and MPS unavailable; `worker_guard` raises (`:75`). See L-5 for residual. |
| M1 exact-dict lease compare | **Open** | `worker.py:65`; `execute_once.py:129,131,234,264`. Live lease object has mutable fields (`cancel_requested`, `review_status`, `harness_sha256`, `campaign_launch_authorized`, …) per `state-after.json`. |
| M2 winner not re-derived | **Open** | See H-1. |
| M3 ranking results not bound to run | **Open** | `worker.py:123-130`. |
| M4 outer receipt path collision | **Mitigated** | Receipt path lives in `output_dir` (`execute_once.py:206`); non-empty output dir rejected at `execute_once.py:145`. |
| M5 cleanup budget edge | **Open** | `execute_once.py:287`. |
| M6 builder `validate_final` pins | **Open (defense in depth)** | `build_registration.py:85-120` does not check candidate, cohort-manifest, or runtime pins; preflight does when `VERIFY_*` is True. |

## High

**H-1. Ranking-to-confirmation selection has no runner producer and no comparator re-derivation.** `worker.py:116-131`, `worker.py:203`, `test_runner.py:43-58`.
- `validate_selection` reads `winner_update`, `winner_checkpoint_sha256`, `incumbent_checkpoint_sha256`, and `ranking_results` (`worker.py:116,121`). The ranking-stage output writes `winner_update` and `candidate_results` only (`worker.py:203`). No code writes a selection record with the fields `validate_selection` reads.
- Winner is `max(performance.mean)`, tie to lower update (`worker.py:203`). Nothing checks 1024 episodes per candidate, the proposal metric `mean_alive_frames_all_1024_including_caps`, or argmax over the six referenced results. `validate_selection` never recomputes the winner.
- Ranking refs carry no `run_id`, `registration_sha256`, evaluator SHA, or cohort SHA (`worker.py:123-130`).
- The test `confirmation_setup` hand-writes the selection file and fake `rank-*.json` (`test_runner.py:43-58`), so the chain is never exercised with real ranking output.
- **Trigger:** parent writes `selection.json` naming update 300 while 324 has the higher mean, with six valid refs and matching checkpoint pins.
- **Consequence:** `validate_selection` passes (`worker.py:118-131`); confirmation runs the locked wrong winner. Runner does not detect it.
- **Fix:** define one selection producer in code. Recompute argmax from the six referenced per-candidate files using the proposal comparator. Require 1024 episodes and `cohort_name == ranking`. Bind each ref to this ranking run's `run_id` and `registration_sha256`. Add a negative test where the record's winner is not argmax.

## Medium

**M-1. Exact lease-object comparison (carry M1).** `worker.py:65`, `execute_once.py:129,131,234,264`. The ledger's live lease object carries mutable fields. Any update to `cancel_requested` or `review_status` causes `lease_invalid` (`execute_once.py:234`) or `inference lease lost` (`worker.py:65`). Consequence: false stops, not unsafe. Fix: compare an immutable identity field, such as `run_id` plus `kind`.

**M-2. Lease tests use dead keys and no negative test for `active_long_campaign`.** `test_runner.py:25` and `:151` use `active_long` and `active_inference`. No test sets `active_long_campaign` non-null. Code is correct; a future regression would pass the suite. Fix: fixture uses real key names; add a test where `active_long_campaign` is non-null and expect a stop at preflight and in the worker guard.

**M-3. Production pin checks disabled in tests (carry H1).** `test_runner.py:15-16`. Frozen runtime root/member/version checks (`execute_once.py:158`) and candidate-to-proposal pins (`execute_once.py:162`) never run. Fix: run tests with the production flags, or add a test that flips each flag and expects the corresponding `PreflightError`.

**M-4. Launcher imports unpinned `worker` module.** `execute_once.py:172` and `:277` use `from worker import validate_selection`. Import resolves through `sys.path` (script directory), not the hash-pinned `--worker` path. Preflight pins only the path given (`execute_once.py:121-123`). **Trigger:** `--worker` points at a `worker.py` in a different directory than `execute_once.py`. **Consequence:** unpinned `validate_selection` code runs during preflight and postflight. **Fix:** load the module with `importlib.util.spec_from_file_location` from the pinned path after its hash check, or assert `sys.modules['worker'].__file__` equals the pinned path.

**M-5. Benchmark throughput measurement not bound to ranking run's code and runtime.** `build_registration.py:21-47`, `execute_once.py:79-113`, `execute_once.py:316`. The outer receipt records `worker_sha256` and `evaluator_sha256` (`execute_once.py:316`), but neither builder nor launcher compares them to the registration's source pins. Runtime members of the benchmark run are not compared either. **Trigger:** benchmark run under evaluator or runtime X, ranking under Y. **Consequence:** work budget sized from timing of different code. **Fix:** require `outer.worker_sha256`, `outer.evaluator_sha256`, and the runtime member map to match the ranking registration.

**M-6. MPS test exercises the wrong branch.** `test_runner.py:105-115`. The fake `torch` has no `mps` attribute, so the function returns on `not hasattr(torch,'mps')` (`worker.py:94`) and never reaches `torch.backends.mps.is_available()`. On real macOS torch, `torch.mps` exists and `is_available()` is False; a regression in that line would not be caught. Fix: add `mps=SimpleNamespace()` to the fake so the `is_available` branch runs. Also add a `worker_guard`-level test.

**M-7. No test feeds `make_draft` output into `validate_final` or launcher preflight.** `test_runner.py:79-91` builds drafts and stops. `:215` reaches `validate_final` only to hit the source-review gate. The builder-to-launcher handoff (registration fields, `review_records` pins, `benchmark_measurement` summary) is untested end to end. Fix: after `make_draft`, set `evaluator_review_status` to accepted in a test copy, call `validate_final`, then run `invoke` in ranking mode.

## Low

- **L-1. Hash-then-parse TOCTOU.** `accept_benchmark.py:13-14`, `build_registration.py:26-27`, `execute_once.py:84-86`, `worker.py:126`. Each hashes a path and then re-reads it. Fix: read bytes once, hash and parse the same bytes.
- **L-2. Accept adapter skips worker identity.** `accept_benchmark.py:15` checks schema and `complete` only. No check of `candidate_update == 348` or `cohort_name == benchmark_dev64` on the worker receipt. Downstream checks catch it; defense in depth.
- **L-3. `None` handling inconsistent.** `build_registration.py:31` iterates `outer.get('output_artifacts',[])`, which raises `TypeError` on JSON `null`. `accept_benchmark.py:20` handles it with `or []`. `accept_benchmark.py:23` (`worker['run_id']`) raises `KeyError` on a malformed worker receipt, not `ValueError`. Fix: one consistent guard.
- **L-4. Runtime executable count.** `build_registration.py:64` appends without dedupe; `validate_final` requires at least one (`build_registration.py:95`). `worker.py:53` and `execute_once.py:175-176` require exactly one. Late failure at preflight; fails closed.
- **L-5. MPS fail-open residual.** `worker.py:91` returns `0` whenever `torch` is not in `sys.modules`, for any backend. An `mps` run whose evaluator never imports torch passes every MPS guard. Fix: after evaluator import, if backend is `mps` and torch is absent, return `None`.
- **L-6. Ps-based RSS fail-closed under load.** `worker.py:86` (`timeout=0.2`) returns `None` on failure and `worker.py:74` raises. A slow `ps` kills a healthy run. Availability only. Same class as H2.
- **L-7. Empty-string `Path`.** `execute_once.py:153` uses `Path(rt.get('pycache_prefix',''))`. When absent, `Path('')` is `.`, and the check inspects the current directory. Fail closed but misleading message.
- **L-8. Cleanup budget edge (carry M5).** `execute_once.py:287` `end=min(time.monotonic()+CLEANUP, deadline+CLEANUP)`. If stop is detected after `deadline+10`, SIGKILL goes out with zero SIGTERM grace (`execute_once.py:290`).
- **L-9. Test fixture typo leaks state.** `test_runner.py:91` restores `build_registration.GOLD` and `GOLD_SHA` (typo). `GOLDEN` and `GOLDEN_SHA` stay patched for later tests in the same process.
- **L-10. Accept wrapper write.** `accept_benchmark.py:22-26`. Failed `os.link` leaves the tmp file. `output_path` is not checked against the run's output dir.
- **L-11. Unbounded worker log.** `execute_once.py:211` (carry).
- **L-12. Projection from 128 episodes to 6144 or 4096.** `build_registration.py:68-70`, `execute_once.py:106-113` (carry R2 low note). Underprojection yields partial output with no resume.
- **L-13. Ranking and confirmation manifests read in preflight.** `execute_once.py:164-169` loads seed lists of the ranking and confirmation manifests. Seeds only, no outcomes. Parent should confirm this matches the "other cohorts unopened" intent.
- **L-14. Runtime-ledger key not guarded.** `state-after.json` has `active_native_design`, which neither worker nor supervisor consults. Whether it should block a run is a policy question for the parent.

## Acceptance-chain checks requested

- **Receipt chain:** worker receipt (`worker.py:196-200`) → exclusive wrapper (`accept_benchmark.py:23-26`) → builder and launcher both require the wrapper and re-verify worker and outer pins, run id, registration SHA, stage output path and hash, and outer postflight. Chain logic is consistent across the three readers.
- **Outer postflight:** `accept_benchmark.py:16` and `execute_once.py:87` require `raw_exit_code == 0`, `stop_reason is None`, and `process_group_absent is True`. `passed` is computed before postflight (`execute_once.py:257`), and every postflight exception sets `reason` (`execute_once.py:281`), so a postflight failure cannot yield `stop_reason: null`.
- **Repeated golden checks:** worker (`worker.py:185-190`, `:195`), builder (`build_registration.py:36-46`), launcher (`execute_once.py:95-105`). Same 12 fields, same seed set. Consistent.
- **Raw frames:** `raw_frames = sum(gameplay_frames)` (`worker.py:199`, `build_registration.py:42`, `execute_once.py:101`). `gameplay_frames` is pinned to golden (`worker.py:189-190`), so raw frames inherit the golden terminal-frame accounting.
- **Elapsed and projection:** builder `build_registration.py:68-70,79` and launcher `execute_once.py:106-113` use the same formula: `ceil(2*elapsed/raw*cap + CLEANUP)`. Consistent. Launcher also requires `work_seconds == ceil(projected)` (`execute_once.py:113`).
- **Producer-consumer:** worker writes canonical receipt; accept wraps; builder and launcher consume. Test `test_actual_fake_benchmark_evidence_builds_ranking_and_confirmation_drafts` (`test_runner.py:79-91`) runs the real worker through the adapter into `make_draft`. Good. Launcher consumption is exercised by `test_ranking_uses_one_worker_for_six_serial_calls` (`:190-194`). Gap: M-7.
- **MPS:** first pre-import guard returns `0` (allowed). After torch load, `is_available()` False with backend `mps` raises (`worker.py:94`, `:75`). Unit test hits the wrong branch (M-6). Residual L-5.
- **Guard identity:** heartbeat binds `run_id`, `registration_sha256`, `pid` (`execute_once.py:50`, `worker.py:79`). Adequate. Lease identity is exact-dict (M-1).

## Ranking selection provenance and comparator guards (requested)

- **Count guard:** present. `worker.py:202` requires six results with the exact candidate set; `worker.py:131` requires six refs covering the set in `validate_selection`.
- **Comparator:** not enforced. `worker.py:203` uses `performance.mean`, not the proposal metric; no 1024-episode check; no argmax recompute on the referenced files. Open (H-1).
- **Provenance:** no runner-produced selection record exists. Refs not bound to run (M3). Open (H-1).

## Limits

- Source-only. No execution. `tests.log` is text only, does not bind to source hashes, and was not replayed; the parent is replaying the 20 fake tests.
- Evaluator source not reviewed here (pinned only). H3 and the guard-cadence question depend on it.
- Native, MPS, checkpoint, and game behavior unverified.
- Ledger key names checked on one state file (`user-best-checkpoint-policy-20261026-r1/state-after.json`) only.
- Does not qualify launch, lease, or marker decisions. Those remain with the parent.
