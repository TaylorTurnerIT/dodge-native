# Independent review: remaining seed-priority r3 bindings

Reviewed package: `learning/runs/v2/fullgame-priority-remaining-r3-bindings-sonnet-20261027-r1/`
Package manifest SHA-256: `730a516f2dc8bd01ea6fd4d0f12827072fa02efd6a353f99d895158a199b3b7e`

Full hashes of every reviewed file are in `review.json`, under `reviewed_files_sha256`. Every recorded hash was re-computed and matched.

## Verdict

**No blocking findings in the packet.** The packet is mechanically sound and its launcher refuses to spend or run without the promoted index, approved gates, a pinned authorization document naming the exact run and registration SHA, and a clean ledger. The packet is **not launch-ready yet**: the parent must promote the index and gates, write the authorization, and record the dispositions below. Each concrete run needs its own fresh user go.

This review does not grant launch authority. The candidate fields `launch_authority: true` and `status: parent_registered` are the schema form the r3 contract requires. They do not authorize anything.

## What I checked

- **Candidates versus r3 drafts.** Each of the five candidates differs from its draft only in run-private paths (`output`, `attempt_claim_path`, `launch_marker_path`), `expected_lease`, `import_policy.pycache_prefix`, `launch_authority`, `pending_parent_fields`, and `status`. The `priority` dict loses three flags (`frozen_labels`, `online_refresh`, `stale_transition_replay`). This is the same transform that reproduces the first run's registration byte-for-byte, and r3 `validate_static` requires exactly three priority keys.
- **Frozen budgets and inputs.** Vectors, initial episode indices, exclusion union, the 512-seed training pool, PPO (learning rate 3e-5), schedule (60 updates), shared config, limits (3780 s work, 3790 s total, 6 GiB RSS and MPS), and reference receipts are unchanged from the drafts.
- **Pairing.** Within each replica, uniform and opening_priority share the vector and differ only in the declared pair fields plus lease and path bookkeeping. Replica-1 opening_priority matches the audited first run except for those same fields.
- **Stream hashes.** I recomputed `slot_stream_sha256` and `slot_component_sha256` for all 64 slots of each candidate. All five match.
- **Exclusions.** No pool seed falls in the exclusion union.
- **Static contract.** `contracts.validate_static(reg, startup=False)` passes for all five candidates. Run with `-I -B`; torch, numpy, and `dodge_rl` were not imported.
- **Live ledger.** `active_long_campaign` is null, `training_hold` is inactive, `current_launch_authorized` is false. The packet pins no mutable `state.json`.
- **Spent paths.** Run homes contain only the candidate and an empty `empty-pycache/`. No candidate path points into an existing r3 attempt, marker, or output tree.
- **Launcher gates.** `gate_check` (`start_remaining_one.py:36-104`) is read-only. It refuses before any write unless every condition in `review.json` `checks_passed` holds.
- **Comparison with the proven first launcher.** `start_remaining_one.py` differs from `start_one.py` only in the gate and materialize steps and in the candidate-to-final copy. The spend ordering, state mutation, observer spawn, and progress loop are identical, so F1, F2, F3, and F7 below are inherited, not new.
- **`worker_group_absent`.** It is set unconditionally in the `finally` block of `observe.py` (line 331). It is not a blocker.

I did not re-run the 33 stdlib tests. `run_tests.py` rewrites `logs/test-summary.json`, and the fixtures write under the sealed package's `tmp/`. I assessed coverage by reading names and bodies.

## Findings

Full detail, triggers, and consequences are in `review.json`. Summary:

| ID | Severity | Where | Summary |
|----|----------|-------|---------|
| F1 | medium (inherited) | `start_remaining_one.py:129-138, 153-156` | A failure after `launch-approval.json` is written but before `launch.claimed` burns the registration. If state was already replaced, the ledger lease stays set and blocks all later launches until hand-restored. No training starts. |
| F2 | medium (inherited) | `start_remaining_one.py:162-199` | The observer runs in its own session. A launcher Ctrl-C or loop exception leaves the worker running and unsignalled, with no `execution-exit.json`. The cancel path is manual creation of `<run>/cancel`. The lease stays set, so a second launch is refused. |
| F3 | low (inherited) | `start_remaining_one.py:170` | `progress-reports.jsonl` opens with `x` after `Popen` and is not in the spent-path list. |
| F4 | low | `start_remaining_one.py:44-46` | The reviewed index proposal is not checked against `gates.registration_index_proposal_sha256`. Candidates stay pinned, so only the run list is unbound. One-line fix. |
| F5 | low | `start_remaining_one.py:71-79` | Authorization is parent-written and the launcher checks only that `user_message` is non-empty. It enforces exact run and SHA binding, not user authority. |
| F6 | low (inherited) | `contracts.py:230-241` | `launch_approval_document` hard-codes all eleven gates as `passed`. The approval file is not evidence. |
| F7 | low (inherited) | `start_remaining_one.py:25-33, 119-138` | `state.json` is replaced without a lock. Concurrent launches can lose an update, and the earlier run is then cancelled by its lease check. Operator must serialize launches. |
| F8 | low | `tests/test_remaining_bindings.py` | No test covers the mutating `launch()` path. |
| F9 | info | `watch_progress.py:1, 63`; `tmp/` | Docstring says completion wakes the controlling thread, but the code only prints and returns. A second run raises at the `x` open. An empty `tmp/` is not in the manifest. |

## Answers to the B-items

**B1, fresh user authorization.** A fresh go is a genuine boundary. The earlier go was consumed. Each run uses about 23 minutes and 6 GiB of MPS. The ledger note says each concrete run still needs its registered gates. The user does not need to type 64-hex SHA strings. A reasonable go names one run ID and the reviewed package. The parent then copies the registration SHA from `registration-index-proposal.json`, and the launcher checks that match mechanically.

Suggested shape: "Go: launch exactly one run, `fullgame-seed-priority-luna-20261027-r1-replica-1-opening_priority`, from the reviewed remaining r3 package (manifest SHA `730a516f…`), no retries."

**B2, independent review.** Satisfied by this review. Re-review is needed only if F1, F2, or F4 is fixed in code.

**B3, promotion.** Not performed here. Requirements are in `review.json` under `b_items.B3_promotion`. Apply F4 before promotion.

**B4, acceptance reuse.** The source acceptance (`9b2a4bde…`, study-level, exact source `a29e25b2…`) covers all five remaining registrations. The calibration acceptance covers budgets and bytes, with one caveat (D4 below). The packet's B4 text is stale. The parent's `reuse-acceptance.json` already records the first-run peaks: MPS 2,382,184,448 B, worker RSS 1,231,126,528 B, aggregate RSS 1,283,686,400 B, elapsed 1367.4 s. These sit well inside the 6 GiB caps and the 3780 s work limit. Worker RSS is about 27% above the highest calibration sample (969,637,888 B), so the parent should cite these figures when closing B4.

**B5, launch-time conditions.** Enforced by the launcher. Live state met them at review time. Empty pycache directories exist for all five. `contracts.cache_check` requires `PYTHONPYCACHEPREFIX` to match the registered path and the interpreter to be exactly the registered path.

## Parent dispositions required

- **D1.** Promote the index and gates as the README describes. Add the authorization to gate pins before computing `authorization_sha256`. Copy the user's message verbatim into `user_message`, and record the package manifest SHA.
- **D2.** Apply the F4 check, or record it as accepted risk.
- **D3.** Record that the source acceptance covers all five remaining runs.
- **D4.** Record that the calibration doc's "first registered trial establishes new seeded-profile execution" was satisfied for the uniform arm only. The opening_priority first run is the first MPS execution of priority-sampled seed lists. The native explicit-seed path and stream construction are identical across arms; only the seed integers differ. Accept that scope explicitly, or treat the first priority run as a monitored first run.
- **D5.** Close B4 by citing the first-run peaks already in `reuse-acceptance.json`. No calibration change is needed.
- **D6.** Decide F1 and F2 handling before the first remaining run. Do not interrupt the launcher with Ctrl-C.
- **D7.** Launch one run per fresh go. The suggested first run is replica-1 opening_priority. After each run: `watch_progress.py`, then `execution-exit.json`, then `audit.py`, then exact lease release. Do not start the next run until the lease is released.

## Limits

- Not executed: the 33 tests, native, torch, MPS, checkpoint restore, training, or evaluation.
- The launcher trusts parent-written promotion and authorization files (F5).
- No training result is interpreted. No heldout, D4, or D5 access.
- Priority-arm MPS execution is unexercised (D4).
- Absolute paths in candidates assume the worktree is not moved.
