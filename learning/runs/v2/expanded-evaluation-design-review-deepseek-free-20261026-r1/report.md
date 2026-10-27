# Adversarial review — expanded D2 evaluation proposal (parent r2)

Review only. No launch, no checkpoint deserialization, no native/Torch/MPS, no environment, no B/E outcomes, no gate/lease/state/shared edits. Outputs are confined to this directory.

- Parent: `learning/runs/v2/expanded-evaluation-registration-proposal-parent-20261026-r2/proposal.json`
- Parent SHA-256: `a1070cc5a6d6d01edfbbc04b67aadf58184a606516ee8643d6857edbaa3f1cb2` (matches the review brief)
- Reviewer: `opencode/deepseek-v4.1-flash-free` (free tier); no paid fallback, no subagents.

## Verdict

The byte reconciliation, seed-range arithmetic, and the `147456000` frame bound verify. The proposal is **not ready to register**:

1. the training replication has no sampler-RNG seed vector (the parent's open concern), no evaluation cohort, no analysis unit, no decision rule, and no compute budget;
2. `n=3` (minimum 2) paired training seeds cannot support a confirmatory arm claim;
3. 348 is labeled incumbent before parent acceptance;
4. the seed-exposure proof is explicitly incomplete and not cited;
5. the confirmation is underpowered for the pilot 348-vs-324 gap.

No launch authority is claimed.

## What verifies

| Item | Result |
| --- | --- |
| Manifest file hashes | all 4 briefed files match (`proposal.json`, `proposal.md`, both seed manifests); the parent `manifest.json` also matches `3f83150e...` |
| Candidate checkpoint bytes | all 6 match the proposal and the original receipts/audit |
| Receipt/audit hashes | all 6 match, and each receipt/audit contains the checkpoint SHA-256 |
| 348 status | full audit passed; parent terminal acceptance still pending (`authority.terminal_acceptance=false`) |
| Seed ranges | 1,024 contiguous seeds each; disjoint from B, D128, E, dev-64, and each other |
| `147456000` | `8192 * 18000 = 147456000` — correct for ranking + confirmation only |
| Host memory | 48 GiB; proposal says do not add RSS and MPS (12 GiB cap); even ultra-conservative `2 * (6+6) GiB = 24 GiB` disjoint sum + `12 GiB` headroom = 36 GiB < 48 GiB |
| Partial seed exposure | sibling audit 686,717 records / 1,608 files / 85,391 distinct seeds, 0 collisions; this review's subset scan 919 files / 170,972 seed tokens, 0 hits — subset proofs only |

The candidate bytes are the original retained checkpoints, not newly serialized entry copies: 180 is `D2-gradient-alignment.../checkpoint-000180` (`105e0f7a...`), 276 is `D2-retained204-lr1e4.../checkpoint-000276` (`0b5cf72b...`), and 300 is `D2-retained276-lr3em5.../checkpoint-000300` (`e2c8fbe4...`). Each is pinned by the cited receipt/audit.

## Blocking findings

### F1 — Sampler RNG seeds are absent from the replication seed vector

`training_replication` lists only `new_environment_master_seeds = three_distinct_ids_to_freeze_before_launch` and `same_saved_model_Adam_RNG_before_registered_seed_transition = true`. There is no sampler/action-RNG field; the only `sampler` hit in `proposal.json` is `resource_sampler`. This is exactly the parent's open concern.

**Correction.** Define a frozen vector `S_i = {env_master_seed_i, sampler_rng_seed_i, and any torch/numpy/python/env RNG stream used by training}`. `S_i` must be distinct across `i=1..3`, identical across arms A and B, and set only **after** verified model/Adam/RNG restore. Record `S_i` in the registration, run identity, and receipt; verify the effective sampler seed at runtime; add `S_i` to `concurrency.per_run`.

### F2 — The replication has no evaluation cohort, analysis unit, decision rule, or compute budget

`training_replication` covers arms, parent, seeds, endpoint, and minimum only. `evaluation` describes the 6 candidate checkpoints. `budget.raw_frames_max` covers 8,192 episodes (ranking + confirmation) and excludes the replication.

**Correction.** Register (a) the replication evaluation cohort (fresh reserved block, descriptive reuse of ranking-1024, or defer to a separate registration), (b) the unit = paired training seed (`n=3`), (c) the estimator and interval, (d) the primary endpoint, (e) the frame budget. Add these to `launch_blockers` until frozen.

### F3 — `n=3` (minimum 2) cannot support a confirmatory arm claim

Exact one-sided sign-test minimum `p` is `0.125` at `n=3` and `0.25` at `n=2` when all pairs agree. A paired `t` at `df=2` needs `|t|>2.92`. The proposal states no decision rule, so "replication" risks being read as confirmation.

**Correction.** Label the replication descriptive/pilot unless seeds are increased to at least 5–6 per arm. Pre-register: 3 planned complete pairs; if fewer than 3 complete pairs, report descriptively only and make no interval-based claim; do not silently fall back to 2. Never bootstrap over episodes or use 1,024-seed precision as the arm-comparison unit.

### F4 — 348 is labeled incumbent before parent acceptance

`confirmation.incumbent_phase_update=348` and `incumbent_checkpoint_sha256=b95228e5...`, but the 348 audit status is `all_candidates_audited_pending_parent_terminal_acceptance` with `authority.terminal_acceptance=false`. The launch blockers do include `selected348_parent_receipt_not_published`, but the confirmation section still names 348 as the incumbent. The predecessor Luna draft records `current_incumbent_update=324` and 348 finalizer review pending.

**Correction.** Call 348 the **proposed comparator pending acceptance**; keep 324 as the accepted incumbent. State that if the 348 parent receipt is not published, the registration is void or must be reissued against 324. The controller origin and expected component fingerprints also depend on the accepted 348 receipt.

### F5 — Replication compute is not in the `147456000` frame bound

`147456000 = 8192 * 18000` covers ranking + confirmation only.

| Item | Frames |
| --- | ---: |
| Replication training, 6 runs (`6 * 3929306`) | 23,575,836 |
| Replication training, 9 runs (optional control) | 35,363,754 |
| Replication eval max, 6 checkpoints × 1024 × 18000 | 110,592,000 |
| Replication eval max, 9 checkpoints | 165,888,000 |
| Total eval max with replication (2 arms / 3 arms) | 258,048,000 / 313,344,000 |
| Total training + eval max (2 arms / 3 arms) | 281,623,836 / 348,707,754 |

**Correction.** Either register the replication evaluation and training frames explicitly or defer the replication to a separate registration. State that `147456000` is not the campaign total. If the replication is evaluated on 1,024 seeds, justify why episode-level precision is needed when the run-level `n` is 3; a 256-seed per-run cohort may suffice.

### F6 — Seed-exposure proof is explicitly incomplete and not cited

The sibling audit (`expanded-evaluation-seed-exposure-audit-luna-20261026-r1/audit.json`) scanned 686,717 records / 1,608 files / 85,391 distinct seeds with 0 collisions, but its limits include no checkpoint binaries, no reservation registry/config union, and no parent-receipt episode-index reconciliation. The sibling reconciliation (`expanded-evaluation-seed-coverage-reconcile-luna-20261026-r2/reconciliation.json`) states "complete seed identity unavailable in receipt fields" and lists the missing artifacts: per-run master seed + SplitMix64 source hash, a closed construction/attempt inventory, the 348 parent receipt, and journal-to-receipt reconciliation. The proposal's launch blockers do include `retrospective_seed_exposure_and_future_exclusions_not_verified`, but the proposal does not cite either sibling artifact.

**Correction.** Cite both sibling artifacts by path and hash in the proposal and manifest; require the reconciliation's minimal missing artifacts before launch; audit the derived per-episode `actual_seed` values and sampler draws, covering **training and evaluation** exposure, completed/abandoned/in-flight. A partial collision voids the manifest; do not silently drop a seed. The proposal's "training ancestry seed_ids" wording is too narrow.

## Major findings

### F7 — Throughput sample may use ranking seeds

`budget.measurement` requires the throughput sample to be separate from **confirmation** only. Running the model on ranking seeds before the ranking opens the outcomes and contaminates selection.

**Correction.** Require the throughput/benchmark sample to be disjoint from **both** ranking and confirmation (use dev-64 or a third reserved block).

### F8 — Post-Adam LR controller mechanics are underspecified

`Adam_then_LR = restore_Adam_first_then_apply_explicit_registered_controller_transition;preserve_prior_schedule_metadata`. The existing linear run uses `origin_cumulative_update=372`, `horizon=60`, spec SHA `7ceed85c...`, verifies model/Adam/RNG restore before env construction, and logs per-update group LR from `3e-5` (`u=1`) to `1e-5` (`u=60`). 348 is at cumulative 396, `u=24`, LR ≈ `2.2203e-5`.

**Correction.** Register the new controller: origin = 348 cumulative (expected 396), `u = cumulative - origin`, first new update cumulative 397 → `3e-5`, last `u=60` → `1e-5`. Verify 348 component fingerprints (`model b106e8e1...`, `Adam 29108e84...`, `RNG 831d8fa2...`) in an entry-restoration record before env construction. Keep the old spec as provenance only; do not restore the old scheduler as active. Preserve Adam step count. Log and assert per-update group LR for both arms. Record the shared first-step jump from ≈`2.2203e-5` to `3e-5`.

### F9 — Confirmation is underpowered for the pilot 348-vs-324 gap

Pilot dev-64 paired `348 - 324`: mean `158.72`, SD `2297.51`, SE at 1,024 = `71.80`.

| Quantity | Value |
| --- | ---: |
| LB>0 threshold (50% power) | 118.11 frames |
| 80% MDE | 178.53 frames |
| 90% MDE | 210.12 frames |
| Power at the pilot effect, `N=1024` | 0.714 |
| `N` for 80% / 90% at the pilot effect | 1,296 / 1,795 |
| 348's own 1,024-seed mean CI half-width | 125.10 |

**Correction.** State the MDE and treat a null as inconclusive, not as evidence of no difference. Either increase confirmation `N` to ~1,300 (80%) or ~1,800 (90%) for the pilot effect, or pre-register the ~118-frame threshold as the practical margin and justify it. Pre-register a minimum meaningful difference, not only `LB>0`.

### F10 — If 348 wins, the one-use confirmation cohort is spent on a descriptive estimate

`if_winner_is_incumbent = single1024seed_estimate_and_CI;no_improvement_test_against_itself_or_pointer_change`; `cohort_openings=1`. The pilot suggests 348 is the likely ranking winner, so the expected path spends 1,024 seeds and up to 36.8M frames without a confirmatory test.

**Correction.** Make cohort opening conditional on `winner != 348`, or justify the descriptive 348 estimate explicitly and state that the one-use block is spent. Label that branch descriptive, not confirmation.

### F11 — Concurrency conflicts with the frozen single-lease guard; evaluation runs and MPS enforcement are not attributed

`current_legacy_lease = unchanged;normal_parent_finalization_only`, `registry = ...no_bypass_of_frozen_singlelease_guards`, `initial_max_active_training_campaigns=2`, `operational_qualification = new_registry...review_required_before_concurrentlaunch`. `per_run` lacks the seed vector, controller spec, and eval manifest. MPS driver bytes is a recommended working set, not a hard cap.

**Correction.** State that the 2-campaign registry is a separately authorized lease-registry successor and this proposal does not authorize it. Include evaluation runs in the registry or serialize them against training. Require an enforcement/watchdog on MPS breach and a measured free-memory/pressure check. State the accounting basis: the proposal says `do_not_add_RSS_and_MPS` for unified memory (12 GiB cap); even the ultra-conservative disjoint sum (24 GiB) plus 12 GiB headroom is 36 GiB < 48 GiB, so capacity is not the blocker. Add seed vector, controller spec SHA, and eval manifest SHA to `per_run`.

### F12 — Q1/Q4 ordering basis is missing

`evaluation.Q1 = mean_lowest256_alive_frames`; `Q4 = mean_highest256_alive_frames`; `quarter_group_size=256`; no definition of what orders the 1,024 episodes. The predecessor Luna draft had `q1_q4_definition = means for lowest and highest quarter groups of the fixed 1024-seed cohort; not quantiles`.

**Correction.** Define per-candidate ordering by alive frames: bottom 256 and top 256 of that candidate's 1,024 episodes, caps included, not a common seed partition and not quartiles of the seed cohort; label descriptive. Alternatively define a common seed partition and justify it.

### F13 — Ranking selection bias and multiplicity are not labeled

`ranking_metric = mean_alive_frames_all_1024_including_caps`; 6 candidates; `tie_break = earlier_phase_update`; no claim-limit text. The confirmation is a single test, but the proposal does not say so explicitly.

**Correction.** State that ranking is selection-only, the winner's ranking mean is upward-biased (winner's curse), and no pairwise ranking claim is made. State that the single winner-vs-348 test on fresh seeds needs no multiplicity adjustment because it is one test, the selection is independent of the confirmation data, and the winner is frozen before the cohort opens. Future pairwise or sequential claims require a separate alpha policy.

### F14 — Replication best-checkpoint selection can contaminate the arm comparison

`endpoint = same60updates;best_checkpoint_selection_reported_separately`. The existing 348 was selected on the 64-seed eval (`selection_basis = mean_alive_frames_including_entry324_no_score_gate`).

**Correction.** Pre-register the primary endpoint as the final update (60) for both arms. If a best-checkpoint analysis is reported, select on a disjoint validation block or a training-time metric, label it exploratory, and never select on the eval cohort used for the arm comparison.

## Minor findings and notes

- **F15 — Nested lineage.** 180 → 204 → 276 → 300 → 324 → 348 is one ancestry chain (204 branches from 180). The ranking selects a checkpoint, not an independent method. Add that claim limit.
- **F16 — 348's 64-seed mean is selected.** `3098.125` is the max of 6 on dev-64 (baseline 324 `2939.40625`). Use the fresh 1,024-seed estimate for reporting; do not present `3098.125` as an unbiased incumbent mean.
- **F17 — "Accepted receipt" wording.** 348 has an audit, not an accepted parent receipt. Say "accepted receipts for 180–324 and a full audit for 348; parent acceptance pending."
- **F18 — Backend/determinism.** Pin one backend for all candidates and both stages; record device/library versions; run a two-repeat determinism check on one candidate before the full ranking; specify env independence/reset and fixed chunk order.
- **F19 — Audit fields.** Reuse the frozen 64-harness conservation/audit contract (`terminated XOR truncated`, `alive <= gameplay <= cap`, score identity, `startup_frames == 13`) and require unknown/unavailable death-cause counts to be reported and investigated if nonzero.
- **F20 — Bootstrap wording.** Clarify that `method: "linear"` means quantile interpolation (as in `numpy.quantile(method="linear")`), not a normal interval. Record the bootstrap code hash; consider BCa for bounded/censored data or justify percentile; state whether the target is the cohort mean or a superpopulation of seeds.
- **F21 — Wall budget.** Use the observed anchors (348 run `1131.14 s` for 60 updates; 64-episode eval `8.76 s`) for the projection, but keep the wall limit as a separate registered budget; do not convert the frame bound into a timing claim.
- **F22 — B/E label.** The proposal says `B_E_outcomes_remain_unopened=true`; the earlier 64-seed audit flagged that B-block baseline episode files exist on disk (hash matches qualification v2). This review did not open B/E. Reconcile the label before relying on it.
- **F23 — Strength.** The contiguous 1,024-seed blocks are easy to audit and are disjoint from all known ranges. Keep them and install the union in the training exclusion config before any environment construction.

## Quantitative checks

All arithmetic is stdlib-only and reproducible via `arithmetic.py` → `arithmetic-output.json`.

### Frames

- `6144 + 2048 = 8192` episodes; `8192 * 18000 = 147456000` — matches the proposal.
- Replication training: `6 * 3929306 = 23575836` raw frames; `9 * 3929306 = 35363754` with the optional control.
- Replication eval max: `6 * 1024 * 18000 = 110592000`; `9 * 1024 * 18000 = 165888000`.
- Total eval max with replication: `258048000` (2 arms) / `313344000` (3 arms).
- Total training + eval max: `281623836` / `348707754`.

### Memory

- Host `48 GiB`; per campaign `6 GiB RSS + 6 GiB MPS`; 2 campaigns.
- The proposal says `do_not_add_RSS_and_MPS` (unified memory), giving a `12 GiB` cap; even the ultra-conservative disjoint sum is `24 GiB`; plus `12 GiB` headroom = `36 GiB < 48 GiB`; slack `12 GiB`.
- Observed 348 peaks: `2.10 GiB` RSS, `2.29 GiB` MPS. The 6 GiB caps are generous but advisory; enforce them.

### Pilot power (dev-64 paired rows, not the proposed cohorts)

| Pair vs 348 | Mean diff | SD diff | SE at 1024 | LB>0 threshold | 80% MDE | Power at pilot effect | N for 80% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 324 | 158.72 | 2297.51 | 71.80 | 118.11 | 178.53 | 0.714 | 1,296 |
| 300 | 393.73 | 2834.33 | 88.57 | 145.70 | 220.25 | 0.997 | 320 |
| 276 | 614.47 | 2988.38 | 93.39 | 153.62 | 232.22 | ~1.000 | 146 |
| 204 | 1176.95 | 2234.99 | 69.84 | 114.89 | 173.67 | 1.000 | 22 |
| 180 | 1243.66 | 2189.35 | 68.42 | 112.55 | 170.13 | 1.000 | 19 |

The close pair is the problem: the proposed 1,024-seed confirmation has ~71% power for the pilot 348-vs-324 gap and ~50% power at ~118 frames. A null result would be inconclusive.

### Replication inference

| `n` pairs | Min one-sided sign-test `p` (all same direction) | Paired `t` critical (95% one-sided) |
| ---: | ---: | ---: |
| 2 | 0.25 | 6.31 |
| 3 | 0.125 | 2.92 |
| 4 | 0.0625 | 2.35 |
| 5 | 0.03125 | 2.13 |
| 6 | 0.015625 | 2.02 |

`n=3` cannot reach 5% one-sided with a sign test; `n=2` is worse. The replication is a pilot unless seeds increase.

### Post-Adam LR controller

- Existing linear schedule: origin `372`, horizon `60`, spec SHA `7ceed85c...`; `u = cumulative - origin`; `u=1` → `3e-5`, `u=60` → `1e-5`.
- 348: cumulative `396`, `u=24`, LR ≈ `2.2203e-5`.
- New arms: origin `396`, first new update cumulative `397` → `3e-5`; last `u=60` → `1e-5`. Both arms share the jump from ≈`2.2203e-5` to `3e-5`.

## Claim limits the proposal should add

1. Ranking is a selection device; the winner's ranking mean is upward-biased; no pairwise ranking claims.
2. The only confirmatory test is the single winner-vs-348 comparison on fresh seeds; no multiplicity adjustment now; future pairwise or sequential claims need a separate alpha policy.
3. The confirmation is conditional on the candidate set and on parent acceptance of 348; if 348 is not accepted, the registration is void or must be reissued against 324.
4. A null confirmation is inconclusive, not evidence of no difference; the MDE is ~113–154 frames at 50% power and ~170–234 at 80% power across the pilot pairs.
5. The training replication is descriptive/pilot at `n=3` (min 2); no 95% arm claim; never use episode-level precision as the arm-comparison unit.
6. Without the constant `2e-5` control, no schedule-shape claim; the two arms differ in average LR (`3e-5` vs `2e-5`) and reset to `3e-5` from 348's ≈`2.2203e-5`.
7. No qualification, holdout, stage-promotion, or B/E claim; all gates unchanged.
8. The `147456000` frame bound is a cap for ranking + confirmation only, not a campaign total and not a timing claim.

## Ordered corrections

1. Add the full seed vector `S_i` (env master + sampler + other RNG streams), identical across arms, distinct across replicates, set after verified restore, recorded in registration/identity/receipt.
2. Define the replication evaluation cohort, unit, estimator, primary endpoint, and frame budget; label it descriptive/pilot at `n=3`.
3. Relabel 348 as proposed comparator pending acceptance; keep 324 as accepted incumbent; define void/reissue.
4. Add the replication frames to the budget or defer the replication to a separate registration.
5. Cite the sibling seed audit and reconciliation by hash; require the reconciliation's minimal missing artifacts before launch.
6. Require the throughput sample to be disjoint from both ranking and confirmation.
7. Register the post-Adam controller origin/`u`/first-step LR, the 348 component fingerprints, and the per-update LR assertions.
8. State the confirmation MDE and either increase `N` or pre-register the practical margin; make the 348-wins branch conditional or explicitly descriptive.
9. Resolve the 2-campaign registry vs frozen single-lease guard; include evaluation runs in resource attribution; enforce the MPS cap.
10. Restore the Q1/Q4 ordering definition; add the selection-bias/multiplicity claim limits; pre-register the replication primary endpoint.

## Outputs and reproduction

- `report.md` — this review.
- `findings.json` — structured findings F1–F23, verified items, quantitative summary, claim limits.
- `arithmetic.py` / `arithmetic-output.json` — stdlib-only hash, seed-range, frame, memory, pilot-power, LR, and replication-unit arithmetic.
- `seed-scan.py` / `seed-scan-summary.json` — read-only subset scan of 919 accessible training/dev-eval logs (170,972 seed tokens, 0 hits).
- `manifest.json` — hashes of these outputs and the inputs reviewed.

The sibling audit/reconciliation are read-only evidence, not launch authority. No checkpoint was deserialized; candidate checks are byte hashes only. No B/E outcome path was opened.
