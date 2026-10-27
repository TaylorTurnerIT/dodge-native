# Frozen source-only review: expanded-runner integrated r5

Verdict: **Not cleared for benchmark launch.** Two benchmark-stage supervisor gaps remain (B-1 High, B-2 Medium), plus the open H3 heartbeat-cadence question that depends on evaluator source. Ranking and confirmation have separate blockers listed in their own section. No launch authority; parent owns lease, marker, and launch decisions.

## Scope and method

- Read-only. No runner, evaluator, native, Torch, MPS, checkpoint, game, lease, marker, or shared file touched. Nothing executed or imported.
- Read in full: `execute_once.py`, `worker.py`, `build_registration.py`, `accept_benchmark.py`, `test_runner.py`, `test_supervisor_cleanup.py`, `test_actual_lease_keys.py`, `receipt.json`, `tests.log`, `actual-lease-tests.log`.
- Read as context: `expanded-runner-r2-frozen-review-haiku-20261026-r1/review.md`, `benchmark-acceptance-r4-frozen-review-haiku-20261026-r1/review.md`.
- Hashed pinned data inputs with `shasum` (JSON/JSONL/py only, no checkpoints, native, or ledger). Results below.
- Test logs read as text only. Not re-run.

## Source hashes (sha256, match `receipt.json`)

| file | sha256 | match |
|---|---|---|
| accept_benchmark.py | 5f51cf1a3644702b72a22c5a42d717bbfdc9e6320b1108c2891702cb88ff7647 | yes |
| build_registration.py | 280650effba15ca1763707bbf054d081f6d4fb662da83f6a70a299243b07e8eb | yes |
| worker.py | 2b5d25d07c671671e6f9a4fb2c976b02af2cb8372ace30ad2d05544bb18a83e4 | yes |
| execute_once.py | b1020bd112dd79ae2c8486424907001292be64e8e81224aad68b38dd044a775c | yes |
| test_runner.py | 6b1c1ec9f289587c3520c962dfee65b82cebc7017bb075ecdb351cf1d922ec73 | yes |
| test_supervisor_cleanup.py | db86611976d5e5f4fb34ed342bcecc63d308c2de2d27dc7b7e54e5e5ccb9be86 | yes |
| test_actual_lease_keys.py | eb3b5869c9575dcd35e770e411bf3b8a7d241b3ab67f9c5c70f45d5342af4bc7 | yes |

Note: the scoped R4 review cites `execute_once.py` sha `6ec8ab00…f1570`. That is not the r5 file (`b1020bd1…`). Its line references to `execute_once.py` are stale for r5 and were not used here.

Pinned data inputs (sha256 computed at review; all match constants in code):

| input | sha256 | match |
|---|---|---|
| proposal.json | 187e0464ba966b29124b29cf606c831d7097adeea99ccfc0e336598ad3fc9765 | `execute_once.py:10` |
| training registration-final-r2.json | 0a6bf98221689ffcf62a28289dae7bb98eb89bc8d3c02b93127f4a04df75cb4e | `execute_once.py:12` |
| benchmark-dev64-seed-manifest.json | a57410e1848f8b35b874507afa21a4d90ced706efd3bd7a141e1dc3ad5df3695 | `execute_once.py:14` |
| development-000348.jsonl (golden) | d6e914345dcc955f678db41eb08d9f20af8e77490652f8d25f7ee09550a63a03 | `execute_once.py:16`, `worker.py:11` |
| expanded_eval.py (evaluator) | a3439c33152b082471cd9f9a36ef4bb03783b9544ae7c1e3fe1878e607b128aa | `build_registration.py:11` |
| retained-best-candidate-receipt.json | cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016 | `build_registration.py:8` |
| seed-lineage receipt.json | fe4b0cc6cbbc4b9ff4335c4462dbc120954f1bac0bac8c6c761d5c18636c0949 | not pinned in code; not checked against `proposal.seed_gate` |

Native `022d41dde…` pin is text-matched in code only (`execute_once.py:8`, `worker.py:9`, `build_registration.py:12`). Native file not opened.

## Status of R2 items

| R2 item | r5 status | evidence |
|---|---|---|
| B1 `limits` NameError | Fixed | `build_registration.py:80-82` defines `limits` before use. Ranking/confirmation draft path exercised only with fake fixtures. |
| B2 producer/consumer receipt | Fixed for benchmark chain | `worker.py:196-200` writes `expanded_eval_dev64_benchmark_receipt_v1`; `accept_benchmark.py:12-26` wraps it with outer receipt pin; readers `execute_once.py:86-112`, `build_registration.py:21-47`. |
| B3 wrong ledger keys | Fixed in code | `execute_once.py:136-140,251,290`; `worker.py:65-68`. `test_actual_lease_keys.py` covers `active_long_campaign` (2 tests passed). |
| B4 SIGTERM/SIGHUP bypass | **Partially fixed** | See B-1, B-2 below. |
| H1 test fixture disables pins | Open in tests | `test_runner.py:15-16` still sets `VERIFY_*=False` and rewrites native/golden pins. Production constants are `True` at `execute_once.py:6`. Parent reports real-pin preflight run separately; r5 static rerun pending. |
| H2 `ps` failure skips receipt | Fixed for in-loop and except paths | `sample_procs` at `execute_once.py:45-47` returns error instead of raising; stop/post-exit use it at `:265,274,278`. Gap in postflight window: see B-1. |
| H3 heartbeat cadence | Open | `execute_once.py:6,150`; `worker.py:157`. Depends on evaluator `check_guard` cadence. Evaluator not reviewed here. |
| H4 MPS fail-open | Mostly fixed | `worker.py:94,96` fail closed when backend `mps` and MPS unavailable/unsupported. Residual: `worker.py:91` returns `0` before torch import regardless of backend (low; no MPS allocation before import). |
| M1 exact-dict lease compare | Open, accepted by parent | `execute_once.py:136,138,251,287`; `worker.py:65`. Parent calls this deliberate for the new campaign. Effect: any ledger field change stops the run with `lease_invalid`. Not a safety hole. |
| M2 winner not re-derived | Open, confirmation-only | See ranking section. |
| M3 ranking refs not run-bound | Open, confirmation-only | `worker.py:121-131`. |
| M4 outer receipt collision | Fixed | `check_mode` plans receipt path (`execute_once.py:72-73`); `atomic_json` uses `os.link` (`:33`); collision test passes. |
| M5 cleanup budget edge | Open, low | `terminate_bounded` (`execute_once.py:310-333`): if `deadline` param is already past, `end<now` and SIGKILL goes out with no SIGTERM grace. Not reached in normal paths. |
| M6 builder `validate_final` pins | Open, defense in depth | `build_registration.py:85-120` omits cohort manifest and candidate pins. Preflight covers them (`execute_once.py:155-176`). |

## Benchmark-stage blockers (cleanup / signal / resource)

These block any benchmark launch under r5.

**B-1 (High). Signal handler is removed before postflight and final cleanup.**
- Path: `execute_once.py:220-221` installs `on_signal` for SIGTERM/SIGHUP. The `finally` at `:271-272` restores default handlers. Postflight (`:273-306`), including `validate_throughput_receipt`, hashing of runtime/candidate/manifest files, and the final receipt write (`:305`), runs with defaults. Final `terminate_bounded` for orphaned group members (`:276-277`) also runs with defaults.
- Trigger: SIGTERM, SIGHUP, or SIGINT (default KeyboardInterrupt, not caught by `except Exception` at `:304`) arrives after the monitor loop exits and before `:305`.
- Consequence: supervisor dies with no outer receipt. Any orphaned process-group members (possible after a normal worker exit, per `:274-277`) are left running with no bounded cleanup. Marker stays claimed.
- Not covered by tests: `test_supervisor_cleanup.py` signals only during the loop (`sleep_seconds=30`).
- Fix: keep `on_signal` installed through `:305` and through the final `terminate_bounded`, or move the handler restore to after the receipt write. Add a test that signals during postflight (e.g., a worker that exits 0 leaving a grandchild, with the signal sent after exit).

**B-2 (Medium, narrow). `Popen` race can write a false `process_group_absent: true` receipt and orphan the worker.**
- Path: `execute_once.py:228` `proc=subprocess.Popen(...)`. Signal handler installed at `:220`. If `SupervisorSignal` is raised after the child is forked but before the `proc=` assignment returns, the except block (`:258-270`) sees `proc is None`, skips cleanup, and sets `rows,sample_error=([],None)` (`:265`).
- Trigger: SIGTERM/SIGHUP inside `Popen` between fork and return (narrow window, includes error-pipe read).
- Consequence: worker keeps running in its own session with RSS/MPS unbounded, and the receipt at `:267` says `process_group_absent: true`. The marker is claimed, so a retry is blocked, but the false receipt is worse than a missing one.
- Fix: block SIGTERM/SIGHUP around `Popen` with `signal.pthread_sigmask`, or record the child pid via a pre-known pgid and kill it in the except path even when `proc` is `None`. Add a receipt rule: `process_group_absent` may be `true` only if the process group was sampled after `proc` is known.

**B-3 (Medium, gated on evaluator source). Heartbeat stale limit vs guard cadence (H3, unchanged).**
- `execute_once.py:6` / `build_registration.py:80` set `heartbeat_stale_seconds` to 2.0; preflight allows up to 5 (`execute_once.py:150`). Heartbeat is written only in `worker_guard` (`worker.py:79`), called from `check_guard` (`worker.py:158-164`).
- Trigger: evaluator span >2 s between guard calls (checkpoint load, native batch, MPS compile).
- Consequence: healthy run stopped with `heartbeat_invalid`. Fail-closed, not unsafe, but it can waste the one-shot benchmark budget.
- Blocking until the evaluator's guard placement is verified against `check_guard` calls. Not reviewed here.

**Benchmark non-blocking, tracked:**
- Marker claimed at `execute_once.py:210` before handler install at `:220`. Window is before any child exists. Low.
- Setsid/double-fork children escape group sampling (`ps` by pgid). Carried from R2. Low for benchmark given the single worker, but a limit to state.
- `worker.log` unbounded (`execute_once.py:227`). Low.
- Legacy `active_inference` key still read (`execute_once.py:139,251,290`; `worker.py:68`). R2 asked to drop or define it. Benign if absent; not blocking.
- SIGKILL unhandleable: state as a limit.

## Ranking and confirmation only (not benchmark blockers)

These do not affect the benchmark run and do not require a benchmark re-run to fix.

**R-1 (High, from scoped R4 review H-1, confirmed here). No ranking-to-confirmation producer and no comparator re-derivation.**
- `worker.py:203` writes `winner_update` (max `performance.mean`, tie lower update) and `candidate_results`. `validate_selection` (`worker.py:111-131`) requires `winner_checkpoint_sha256`, `incumbent_checkpoint_sha256`, and `ranking_results`, which the ranking output does not write.
- `validate_selection` never recomputes argmax from the six referenced results and does not check 1024 episodes or the proposal metric `mean_alive_frames_all_1024_including_caps`.
- Trigger: parent writes a selection naming update 300 while 324 has the higher mean, with six valid refs.
- Consequence: confirmation runs the wrong locked winner. Gate passes.
- Owner: independent selection-producer adapter being prepared by Luna (`ranking-selection-producer-luna-20261026-r1`). Must include argmax recompute and run binding.

**R-2 (Medium, M3). Ranking refs not bound to this run.** `worker.py:121-131` checks `complete`, `cohort_name`, update, and checkpoint pin only. No `run_id`, `registration_sha256`, evaluator SHA, or cohort SHA on referenced results. Confirmation only.

**R-3 (Medium). Metric and frame-accounting definitions unverified.**
- `worker.py:199-200` defines `raw_frames = sum(gameplay_frames)` with `gameplay_frames = alive_frames + 1 terminal frame`. Readers agree (`build_registration.py:42`, `execute_once.py:108`).
- Evaluator definition not reviewed here. Affects ranking/confirmation projections only (`build_registration.py:68-70,79`; `execute_once.py:113-120`).
- Projection uses two 64-episode calls to project 1024-episode and 2048-episode cohorts. Underprojection gives partial output. Ranking/confirmation only.

**R-4 (Low, ranking/confirmation). Throughput receipt chain is manual.** `accept_benchmark.py` is run by the parent. Preflight and postflight consume the accepted wrapper only for ranking/confirmation (`execute_once.py:186-187,297-298`). Benchmark does not depend on it.

**R-5 (Low, confirmation only). Selection import in preflight.** `execute_once.py:178-180` imports `worker.validate_selection` for confirmation only, after the worker hash check at `:128-129`. Benchmark path does not import worker. OK as is, noted for the later stage.

**R-6 (Test gap, not launch-blocking).** `test_runner.py:43-58` hand-writes ranking and selection fixtures. The producer-to-consumer chain is not exercised with real ranking output. `test_runner.py:16` disables frozen-runtime and proposal-candidate pins in the fixture copy. Parent says real-pin checks are run separately; r5 static rerun pending.

## Tests

- `tests.log`: 25 integrated fake tests, OK, per receipt.
- `actual-lease-tests.log`: 2 tests, exit 0, OK.
- Not covered: signal during postflight (B-1), `Popen` race (B-2), ledger `active_inference` absence/presence, real evaluator guard cadence (B-3).

## Limits

- Source-only. Nothing executed, imported, or run. Test results taken from logs.
- Evaluator source not reviewed. H3, R-3, and the frame-accounting definition depend on it.
- Live ledger not read. Key names taken from the R4 review's read-only key listing and the code. Not independently re-checked here.
- Seed-lineage receipt hash (`fe4b0cc6…`) computed but not compared to `proposal.seed_gate`.
- Native, MPS, checkpoint, and game behavior unverified.
- No launch authority granted or implied.
