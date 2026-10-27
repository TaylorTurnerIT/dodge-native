# Confirmation proof parent R4: independent source review

Verdict: no blocking source finding in the reviewed R4 confirmation proof binding. R2's provenance-binding, loader TOCTOU, and double-read findings appear repaired in current source: `worker.py:155` uses `read_pinned` for selection bytes; `worker.py:165` uses it for each of six ranking results; `worker.py:171-180` replays the pinned ranking registration and binds evaluator SHA, canonical 13-member runtime-map digest, ranking-manifest path/hash, and distinct run IDs to confirmation registration; `worker.py:186-194` hashes, compiles, and executes one validator byte buffer. `execute_once.py:207-214` does the same for worker source before claim, then post-checks the source pin.

Reviewed R4 `source-hashes.json`: all 16 listed source files present and matching. Parent `tests.log` records 58 CPU/std-lib tests passing, including compatibility mismatches, stale pins, path swaps after read, pre-claim rejection, and postflight tampering. I did not rerun tests.

## Final-registration gates

This review does not establish a usable final registration. Parent must still pin and validate an accepted evaluator review, exact evaluator/worker/launcher source bytes, the ranking selection-validator review record, runtime executable, and successful old-dev64 benchmark receipt; set the final unique run ID, parent lease and ledger paths, and exact output paths; and verify the intended final runtime inventory/backend and projection budget. `build_registration.py:99-110,119-129` enforces several of these at final validation; `execute_once.py:165-190` checks frozen runtime, proposal candidate identities, cohort manifests, runtime executable, receipt, and projection before claim. Draft builder is not final registration or launch authority.

## Evidence limits

Source review only. No real ranking proof files, confirmation outcomes, checkpoints, runtime imports/deserialization, MPS/game/env, registration, ledger, lease, marker, launch, training, or ranking/confirmation episode outcome reads. Parent-reported replay timings are proof-validation-only, not inference timing. The 58-test log is synthetic CPU evidence, not runtime qualification, acceptance, or authorization for the single 2048-seed confirmation campaign. Preserve R4's failed Haiku review provenance: `receipt.json` and `prior-review.md` record Luna R3 findings and R4 repair; no result is attributed to the failed Haiku provider.
