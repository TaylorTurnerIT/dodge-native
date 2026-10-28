# Review: three-run seed-priority recovery packet r2

Reviewed package: `learning/runs/v2/fullgame-priority-three-run-recovery-sonnet-20261028-r2/`
Package manifest SHA-256: `7e5e63e2cc03091af13f8946e3f8cfb333ce2fcdc5599980c0145b00310ab9c6`

## Verdict

No blocking packet findings. One high pre-launch condition (P1) must be recorded before fresh approval. It is an operational check, not a code change.

## Pre-launch condition

- **P1 (high), `start_remaining_one.py:194`.** The observer is started with `start_new_session=True`, and the caffeinate helper is a child of the dispatcher. If the root native exec session, or any caller, kills the dispatcher during a run, the power assertion is released while the observer and worker keep training. A sleep then stalls the run with no exit or terminal receipt and the lease stays held. This is the failure class of the 2026-10-27 incident. Root has not shown that the native exec session lacks a wall timeout at or below about 3800 s. Record that check, or accept the residual risk in writing, before approval.

## Findings

- **F2 (medium), `start_remaining_one.py:153`, `202-226`.** The power guard runs once before spending. Nothing re-checks the helper or its assertions during the observer wait. Accept as a limit.
- **F3 (medium), `tests/test_recovery_bindings.py:290-296, 654-663`.** `launch()` is not exercised by any of the 54 tests. The launch order, progress relay, exit receipt and power-before-spend ordering are verified only by reading. Accept for this one-time packet. A fake-`Popen` test is the next addition.
- **F4 (low), `launch-blockers.json:9`, `:20`; `README.md:36`.** Stale text: "48 stdlib/fake" tests (actual 54), and "probe pending" (the r2 native probe has passed). No gate reads these strings. Fixing them changes the manifest and needs re-review.
- **F5 (low), candidate `registration-final-candidate.json`.** Candidates carry `status: parent_registered` and `launch_authority: true`, while the README and manifest say no launch authority. A candidate file alone cannot launch: the gates, the authorization and the index are all still required (`start_remaining_one.py:61-62`, `103-106`).
- **F6 (low), `start_remaining_one.py:106`.** A naive `at_utc` raises `TypeError` before any spend. Fail-closed. The parent should write an aware UTC timestamp.
- **F7 (low), `start_remaining_one.py:169` then `193`.** The shared ledger is claimed before `Popen`. A failure in between blocks retries and needs manual ledger cleanup. Fail-closed.
- **F8 (info), `start_remaining_one.py:103-106`.** Freshness is parent-attested: the gate checks only that the message is not the single consumed text and that `at_utc` is later than the packet build time. A plain future "Go" is not rejected by this code. No gratuitous content constraint found.

## Checks performed

- Static: all 19 manifest members hash-match. Candidate SHAs match the index proposal, README, build receipt and activation template. Each candidate differs from the proven parent package candidate only in `output`, `attempt_claim_path`, `launch_marker_path`, `import_policy.pycache_prefix`, `expected_lease.kind` and `expected_lease.owner_token`, identically for all three. Superseded SHAs in the index match the failed run and the old drafts. Source, runtime, checkpoint, parent receipt, failure audit, lease release, source acceptance and dependency inventory hashes match the pins. `watch_progress.py` is byte-identical to the parent. The D4 policy plan is unchanged (`dd6ece…`). The remap covers three endpoints only. Ledger: `active_long_campaign` null, no diagnostic, no active training hold.
- Fake: 54 test functions counted statically (4+8+4+6+2+10+18+2). `run_tests.py` was not run, because it rewrites `logs/test-summary.json` and removes `tmp/` in the package. The existing summary reports 54 run, 0 failures.
- Actual non-learning guard: `fullgame-priority-three-run-recovery-parent-validation-20261028-r1/power-guard-r2-native-probe.json` records status passed, utility PID 10938, helper PID 10939, assertions PreventUserIdleSystemSleep, PreventSystemSleep and PreventDiskIdle, on AC, `training_launched: false`. Not rerun here.
- Runtime MPS: not exercised, and not required for this review.

## Limits

- Stream hashes were not recomputed (that needs the r3 `seed_priority` import). Byte equality with the proven parent candidates outside the six keys means they inherit the parent's verification. The build receipt reports the 64-slot, 3-run recomputation as passed.
- The checkpoint and receipt were hashed as bytes only. Nothing was deserialized.
- No checkpoint loading, no D4/D5 outcome, no held-out evaluation, no selection or promotion was reviewed or performed.
- The live process state from the probe cannot be verified now.
- No launch authority is created by this review. Only this review's two output files were written.
