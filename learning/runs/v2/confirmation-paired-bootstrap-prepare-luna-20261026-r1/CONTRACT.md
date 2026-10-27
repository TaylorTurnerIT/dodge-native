# Inert confirmation statistics adapter

`adapter.analyze(registration, selection, terminal_audit, winner_result, incumbent_result)` consumes five externally supplied JSON-like objects. It imports NumPy only. It does not read files, checkpoints, environments, game code, episode data, ledgers, or registries; it writes no result.

## Input contract

- Final registration: `status=final_frozen`; confirmation rule exactly matches adapter constants; explicit ordered `cohort_seeds`, its canonical JSON SHA-256, `backend`, and locked incumbent checkpoint SHA-256 at phase update 348 (`b95228e5e2934c915597595f7eb3c8618ee5f7c2182dde1481a060d01c270369`).
- Frozen selection: `frozen=true`, winner phase update 324, winner checkpoint SHA-256, and `selection_sha256` over the object without that field.
- Successful terminal audit receipt: `status=successful`, `terminal=true`, and `receipt_sha256` over object without that field.
- Each external candidate-result binding: `expected_output_sha256` pinned outside the result plus a `result` object containing checkpoint and cohort SHA-256, backend, exact ordered seeds D2000000..D20007FF, 2048 alive-frame values, full native death-cause counts, cap count, and `output_sha256` over result object without that field. Both the result digest and separate pinned digest must match. Hash encoding is compact sorted-key UTF-8 JSON with NaN forbidden.

Each result must bind to its expected checkpoint, the registered cohort hash, and the same backend. The ordered seed vector must match exactly. Alive-frame values must be finite and in [0,18000]. Death counts must total uncapped episodes; cap count must equal count of values at 18000. The adapter fails closed on any mismatch.

## Statistics

Difference is paired, seed-wise winner minus accepted 348, with capped episodes included. Report exact finite-cohort mean difference; each candidate's Worst, Q1 mean of lowest 512, Mean, Q4 mean of highest 512, Best, full death counts, and cap count. Bootstrap uses NumPy 2.5.4 `Generator(PCG64(4200261026))`, 20,000 resamples of 2,048 seed indices, same indices for both models, and 5th percentile via `quantile(method="linear")`. Resample chunks of 128 preserve one generator stream and bound temporary index memory.

`LB > 0` alone returns `eligible`; `LB <= 0` returns `inconclusive`. Eligibility is a statistics result only. No promotion, ledger write, or rerun authority. Bootstrap coverage is approximate; no exact finite-sample guarantee, method-A/B claim, qualification, or stage-promotion claim.

## Unresolved integration binding

The proposal at `learning/runs/v2/expanded-evaluation-registration-proposal-parent-20261026-r5/proposal.json` provides the statistical rule, but final confirmation registration schema does not exist yet. The explicit input object shape above is a provisional adapter boundary, not a registration. Parent must bind this adapter to the eventual schema and independently review it before integration.
