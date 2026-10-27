# Frozen source-only benchmark-scope review: expanded-runner R6

**Verdict:** No source-level blocker proven for the 348 old-dev64 benchmark stage in the R6 bytes. This is not a launch clearance. Three pre-claim gates (G1-G3) must close first, because any failure after the one-shot marker is claimed spends that marker.

## Scope and method

Read-only. Nothing imported, executed, or run. No Torch, MPS, native binary, checkpoint, game, lease, marker, or shared ledger was touched. The 11 R6 source/test files, `receipt.json`, and both test logs were read as text. Carry-forward read: R4 `benchmark-acceptance-r4-frozen-review-haiku-20261026-r1/review.md`, R5 `expanded-runner-integrated-r5-review-haiku-20261026-r1/review.md`, heartbeat `independent-heartbeat-parent-r2-review-haiku-20261026-r1/review.md`. Parent's new `benchmark-r6-real-pin-parent-validation-20261026-r1/receipt.json` was read; it is fixture-only and is not treated as launch evidence. Pins for the evaluator, golden, training registration, and manifest were taken from code constants and not re-hashed here.

## Reviewed bytes (sha256)

Re-hashed at review start and again before writing. Unchanged since the brief.

| file | sha256 |
|---|---|
| execute_once.py | e68567f0225fa2bbc49944c1fc28518250747be1e0dcf274c23586dbac79b09f |
| worker.py | da212582802e9119095b96057d38158d400d046128299ff1b845d420e236b162 |
| build_registration.py | 280650effba15ca1763707bbf054d081f6d4fb662da83f6a70a299243b07e8eb |
| accept_benchmark.py | 5f51cf1a3644702b72a22c5a42d717bbfdc9e6320b1108c2891702cb88ff7647 |
| test_runner.py | 265d005e8b6864e94ab779e33af6ca0d797910aa5dddfc425ad2f4ab38bd03bb |
| test_signal_windows.py | 78881ab2957dcd94f0177d2cbeb44b035c323f7ae3a88ec7c220f6514cc96139 |
| test_signal_assignment.py | c1f8119260f451f224931b307601b3163d6d8123c53312a6c533373510b9dd1f |
| test_supervisor_cleanup.py | db86611976d5e5f4fb34ed342bcecc63d308c2de2d27dc7b7e54e5e5ccb9be86 |
| test_worker_lifecycle.py | d1dc82c114770bb891270bf7afbe13b7613481b52be245c73ab01d10b043d159 |
| test_heartbeat.py | 9d2b95d21f5d15872b0c30982a2313630c25e4de099e2e3964e169c773ec7874 |
| test_actual_lease_keys.py | eb3b5869c9575dcd35e770e411bf3b8a7d241b3ab67f9c5c70f45d5342af4bc7 |
| tests.log | f821386a873b1c3eb926e81f32537a0de0e16d034aa77e6f54caa68f1ca3b1ba |
| assignment-final-tests.log | 6c3f504bc906a0c11ab10fe4eadc87f033e5f0dd6d898283e5ae71ffc0c8ca94 |
| receipt.json | 2c269ac1294f97c2d7203c57220fa82fd4d0d3e9f9b34368bb200c35589edc35 |

Supervisor and worker SHAs match the brief. Native pin `022d41dd...` matches `worker.py:9` and `execute_once.py:8`.

## Verified by reading

- **Signal lifetime.** Handlers are installed at `execute_once.py:222-224` and restored in `finally` at `:327-328`. That span covers marker claim through receipt write.
- **Popen window.** `spawning` (`:233-236`) defers the handler until the child handle is assigned. Termination signals are no longer blocked around fork, so the child inherits unblocked signals. `test_signal_assignment.py` checks this.
- **Single bounded cleanup.** `terminate_bounded` (`:330-354`) sends SIGTERM, then SIGKILL, within `CLEANUP=10`. Repeated signals are ignored while `handling_signal` is set (`:216`, `:269`, `:317`).
- **Unknown PID is never absence.** With no child, `rows=None` and `process_group_absent` is False (`:273`, `:323`, and `receipt` at `:362`).
- **Postflight survivors fail.** Same-group survivors after worker exit set `process_group_survived` after a terminate attempt (`:283-287`). The benchmark stage does not clear them.
- **Heartbeat identity.** `run_id`, registration SHA, pid, and freshness are checked (`:52-60`).
- **Benchmark evidence chain.** Worker checks golden rows, two repeats, and `raw_frames == sum(gameplay_frames)` in-process (`worker.py:212-217`). Golden pin is checked at `worker.py:168-172` and `execute_once.py:199-202`. `validate_throughput_receipt` runs only for ranking and confirmation (`:185-187`, `:305`).
- **Budget.** Benchmark is fixed at 170/180 (`execute_once.py:148`). Worker deadline equals supervisor deadline (`:210`), on the same monotonic clock on darwin.
- **Test counts.** 37 (`tests.log`) + 4 (`assignment-final-tests.log`) = 41, matching `receipt.json:20`. Count is consistent; freshness is the gap below (G3).
- **Carry-forward closed in R6.** The worker `ps` path is replaced by `getrusage` (`worker.py:70-74`). The postflight signal window (R5 B-1) is covered by handler lifetime.

## Pre-claim gates (not source defects)

**G1. Startup grace versus cold torch import (High consequence, unmeasured).**
- `startup_grace_seconds=12` (`build_registration.py:80`). Cap is `START_GRACE=12` (`execute_once.py:6`, `:146`).
- The sampler clock starts at `worker.py:105`, before `exec_module` of the evaluator (`worker.py:187`, `:195`). While torch is partially imported, phase is `startup` (`worker.py:92`). The sampler raises after 12 s (`worker.py:114`).
- The supervisor's heartbeat-missing check is also 12 s from Popen (`execute_once.py:237`, `:250`).
- Trigger: torch import in `python/.venv/bin/python` takes longer than about 12 s from sampler start.
- Consequence: heartbeat goes stale, the run is killed, and the marker is spent.
- No receipt in the repo measures cold import time under this interpreter. Carry-forward of R2 F4, still open.
- Gate: measure cold and warm import wall time on this machine before claim.

**G2. 170 s work budget versus real throughput (unmeasured).**
- Golden per-repeat gameplay frames: 64 rows summing to 198,344 (`development-000348.jsonl`). Two repeats = 396,688 raw frames.
- Need at least 2,334 frames/s over 170 s, or about 2,511 frames/s over the 158 s left after 12 s startup.
- No measured throughput for this evaluator and runtime exists in the repo. `synthetic-throughput-NOT-RUN.json` is not a measurement. `expanded-dev64-benchmark-parent-20261026-r1/outputs` is empty.
- Trigger: average throughput below the figure above.
- Consequence: `wall_limit` (`execute_once.py:240`), marker spent, no timing evidence.
- Gate: measure full 348 two-repeat throughput on target, or accept the risk explicitly.

**G3. Test-log freshness.**
- `tests.log` mtime 17:56. `execute_once.py` and `test_signal_assignment.py` mtime 17:57. The 37-test log therefore predates the final `execute_once.py` bytes.
- Only the 4 assignment tests were rerun after the final edits (`assignment-final-tests.log`).
- Gate: rerun all 41 against current hashes and replace `tests.log` with a hash-pinned log.

## Source findings (ranked)

**S1. Medium, reachability. One `ps` failure kills a healthy run.** `execute_once.py:38` (`timeout=0.2`), `:242-244`. The supervisor samples at 5 Hz. A single timeout or exception breaks the loop with `process_group_sampling_failed` and terminates the group, spending the marker. Fail-closed, not unsafe. Fix: raise the timeout to about 1 s, keep it under the 2 s heartbeat stale floor, and tolerate a bounded number of consecutive failures in the loop. Keep strict handling at postflight (`:281`) and in termination.

**S2. Medium, reachability. Unguarded ledger read.** `execute_once.py:258` (`state=read(reg['state_path'])`) sits outside any `try`. The worker reads the same file at `worker.py:64`, inside `worker_guard` on the sampler thread (`:117`). A torn in-place rewrite of the shared ledger by another session during the run would kill the run. Verifying whether the ledger writer is atomic was out of scope. Fix: atomic ledger writes, or no concurrent ledger writers during the run.

**S3. Low, evidence scope. Runtime pin excludes interpreter site-packages.** The 13-member pin covers only `dodge_rl/` files under the frozen runtime root, about 1.30 MB total. The interpreter `python/.venv/bin/python` site-packages (torch, numpy) are not hashed. `torch_version` and `numpy_version` are only presence-checked (`worker.py:41-42`) and compared to the training-registration string (`execute_once.py:165`). They are never compared to live `torch.__version__` or `numpy.__version__`. A receipt therefore cannot show which torch binary ran. Record only; the native and 13-member pins were already accepted.

**S4. Low, narrow signal windows.**
- (a) Handlers are installed at `:222-224`, before the `try` at `:225`. A signal in that gap escapes without restoring handlers. No claim is made, so no receipt is needed. No evidence effect.
- (b) The marker is written at `:226` before `claimed=True`. A signal during the atomic write leaves a marker with no outer receipt. Fail-closed, since the marker blocks reuse. Fix: set `claimed=True` before the marker write.
- (c) A signal after the receipt write (`:312`) but before `return rec` (`:314`) leaves a passing receipt while the caller sees `SupervisorSignal`. Receipt content is correct. Caller-visible exit differs.

**S5. Low, test hygiene. Replacement anchors without `assertIn`.** `test_signal_windows.py:15` and `:17`; `test_signal_assignment.py:36`, `:48`, `:58`. If an anchor drifts, the test passes without installing its hook. `test_signal_assignment.py:63` shows the correct pattern.

## Rank-only (not benchmark)

- `execute_once.py:179` and `:307`: `from worker import validate_selection` loads an unpinned module. Reached only for the confirmation stage (`:178`, `:306`). Benchmark unaffected. R4 M-4 still open.
- Ranking and confirmation selection and throughput gates: separate blocked stage, per brief.

## Accepted limits (not findings)

- SIGKILL (`:343`) and process-group escape (setsid or setpgid) are group-only accounting.
- Global GIL starvation of the sampler thread, bounded by the 2 s stale window (`worker.py:117-118`, `execute_once.py:245-247`).
- RSS (6 GiB group, worker peak) and MPS driver (6 GiB) are checked separately, not against total unified memory.
- Outer budget excludes preflight (`:122-203`, hashing before start) and postflight (`:280-313`). Both are small here.
- Evaluator guard cadence and MPS tensor device use: evaluator not in this scope. R5 H3 now bears only on GIL starvation.

## Parent real-pin receipt

`benchmark-r6-real-pin-parent-validation-20261026-r1/receipt.json` reports the builder, evaluator static, and supervisor preflight passing against 6 checkpoint hashes and 13 runtime hashes, with production flags True, marker unspent, and cache empty. It is fixture-only (`status: passed_fixtureonly_not_launchclearance`). It does not replace G1-G3, and it does not make the benchmark launch-ready.

## Limits of this review

- Source-only. No execution. Test logs were read as text and not replayed.
- Pinned external inputs were not re-hashed here; they were taken from code constants.
- Evaluator, native, MPS, checkpoint, and game behavior are unverified.
- No lease, marker, or ledger change was made or inspected beyond reading file contents.
