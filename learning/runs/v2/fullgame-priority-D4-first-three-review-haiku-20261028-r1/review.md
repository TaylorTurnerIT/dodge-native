# D4 first-three evaluator independent review (r1)

Reviewed: `learning/runs/v2/fullgame-priority-D4-first-three-evaluator-sonnet-20261028-r1/`
Narrow diff base: `fullgame-priority-D4-evaluator-sonnet-20261028-r2` (independently reviewed, `fullgame-priority-D4-r2-review-haiku-20261028-r1`).

Hashes checked:
- source-manifest `489708daa2f225a3ce68cdae9ca0c0665636917e961309525e97cdb5093edc5b` (19 entries, 0 mismatches)
- package-manifest `22a65fcdda90be9b476b751e76b24fef64c33bec881e13ee3fe58bd9e5c07a5f`
- registration-draft `95a46ad7a015d5dbfeb7c6206e8b11b5e33c47cb579f5423b0a9668b5a217535`

## Verdict

No blocking findings for source review. One medium item (F1) is recommended before launch. This review does not authorize launch. Finalization items are listed below.

## Findings

**F1 (medium, recommended before launch): torn read of main state latches and kills the evaluation.**
- Path: `binding.py:220-230` (`check_main_state` → `read` at `:108`), `observe.py:276-277`, `worker.py:37`.
- Trigger: a non-atomic in-place write of `learning/runs/v2-orchestration/state.json` that an observer poll (~0.1 s) or worker check (~0.2 s) reads mid-write. The trainer's writer is atomic (`start_remaining_one.py:32-35`), but orchestrator heartbeat and edit writes have no atomic writer in the repo.
- Consequence: JSON decode error → `latch('lease_changed')` → evaluation killed. The single attempt is spent; a new reviewed registration is needed. Training is not affected.
- Fix: bounded retry on main-state read errors (e.g. 3 reads over ≤1 s) before latching; keep the unregistered-campaign latch unchanged; add a torn-file test. Or record atomic writes to state.json as a precondition.

**F2 (low): timing-sensitive ObserverRun success tests.** `tests.py:1239, 1266`. Fake clock steps 50 s from `WORK-30` past `term_at`; passes only if the stub child is reaped before the second poll. Same pattern as r2 finding 1. Static only; not reproduced.

**F3 (low): no real-timer test.** `observe.py:216-222, 298, 316-317, 391-395` run only with injected clock (carried from r2 finding 2). Add a Darwin-arm64 real-timer case.

**F4 (low): stuck own lease after audit crash.** `audit.py:74-75`. If the process dies between saving the audit and `clear_own_lease` (`audit.py:40`), re-run is refused (`audit.py:52`). The own ledger keeps an active lease with no documented recovery. Main state is unaffected. Document or make the recovery idempotent.

**F5 (low, calibration limit): 3× wall factor not measured under concurrent training.** Prior run: 684.92 s for 15,487,746 raw frames. If shared-GPU slowdown exceeds ~3×, the work deadline (7352 s) stops the run fail-closed; finished receipts are kept; the attempt is spent.

**F6 (low, latent): module name shadow.** `worker.py` exists in both the package and the clean source; `binding.contracts()` inserts SOURCE at `sys.path[0]` (`binding.py:167-168`). The clean `worker_cli.py:20` does `import worker`, but no current flow here imports it.

**F7 (low, efficiency): main state fully parsed on every poll** (~650 KB, `binding.py:220-239`). Cache by (mtime_ns, size) or lengthen the poll for the main-state check only.

## Checks passed

- Own lease is installed only in `evaluation-resource-ledger.json`, via exclusive `os.link` (`launch.py:25-32`). The ledger and main state are absent from `input_pins`.
- Main-state allowlist: null, or `kind=fullgame_seed_priority_recovery_attempt`, `study_id` and `run_id` in the three rows of `registration-index.json` (`binding.py:220-230`). The live `state.json` lease matches that shape (`fullgame-seed-priority-luna-20261027-r1-replica-2-opening_priority`). Index hash is pinned and re-checked by `validate_static` (`binding.py:436-464`).
- Audit saves `parent-terminal-audit.json` before clearing only the exact own lease (`audit.py:74-75`). The audit path never opens main state (`audit.py:53,57`).
- Observer and worker check the lease with `main_state=True` during the run (`observe.py:276`, `worker.py:37`).
- Deadlines: `term_at=started+work`, `hard_at=started+total` (`observe.py:194`). Work 7352 = `ceil(3·684.92/15487746·55335936+10)`; total 7482 = 7352+10+120.
- Caps unchanged: RSS and MPS 6442450944 each; raw 55335936 = 3072·(18000+13); steps 55296000; constructors 3072; resets 0; retries 0.
- Power guard runs before any lease or marker spend (`launch.py:52-54`). Bytes match recovery r2 (`83a410ae…`).
- `observe.py` and `execute_once.py` are byte-identical to r2.
- Producer audit prefixes match: `9d3902d8469d5910`, `809b21f1928366c8`, `2a9f1125a4567048`. Later-three remap sha `659597ce…`.
- Statistics: one primary pair (replica-1 opening_priority − uniform); bootstrap seed 2026102801, 2000 draws, 95% (`paired_statistics.py:25-47`). Replica-2 uniform is descriptive only (`comparison.py:40`). Milestones 1k/2k/4k/8k/12k/18k; Worst/Q1/Mean/Q4/Best.
- Row order is enforced by `expanded_eval._validate_rows` (seed list must equal the manifest), so position-based pairing is sound.

## Not verified

- Tests not run (83 test defs counted statically). Three conditional `skipTest` guards (`tests.py:536, 566, 623`) and a darwin-arm64-only class (`:1224`) mean "0 skipped" is unconfirmed.
- Narrow diff is not narrow: `binding.py` ~275 changed lines, `tests.py` ~390, `policy-plan.json` ~123. `binding.py`, `launch.py`, `audit.py`, `monitor.py`, `terminal.py`, `comparison.py`, `paired_statistics.py`, `power_guard.py` and `worker.py` read in full. `tests.py` covered by names, targeted greps and the ObserverRun harness.
- Power guard checked once before launch only. No mid-run AC or helper recheck.

## Finalization requirements (before any execution)

1. Source acceptance pinned to source-manifest `489708da…`, status `accepted_source_review_only` (`launch.py:44-46`).
2. Calibration acceptance restating work 7352, cleanup 10, postflight 120, total 7482, prior 684.92 s / 15487746 frames (r2 finding 3).
3. Gate document: schema `fullgame_priority_d4_first3_evaluation_gate_acceptance_v1`, status `approved_exactly_once_fixed_terminal60_d4_evaluation`, `registration_sha256` of the final registration, all 16 gates passed, pins covering `input_pins`.
4. Final registration built only by `build_registration.py` after the three accepted producer audits; status `parent_registered`; ledger and main state not pinned.
5. Live preflight: main state `active_long_campaign` null or a registered run ID; `active_inference_*` null; own ledger, `launch.claimed`, `attempt.claimed`, output, cancel and dispatch absent; AC power; launch as `/usr/bin/caffeinate -ims <env python> -B launch.py` from the native root session; disk space checked against worst-case journal.
6. Re-run `tests.py` in a clean environment with the recorded command before launch (not done here).
7. Decide F1 before launch: fix, or accept the torn-read latch risk explicitly.
