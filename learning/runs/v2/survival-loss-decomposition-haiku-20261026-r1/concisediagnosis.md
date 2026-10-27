# D2 180 → 252 survival-loss decomposition

Scope: frozen 64-seed development endpoints only (argmax, no caps). Paired by seed. No held-out, population, or training-replicate claim. No checkpoint load, environment step, gradient, or training. Numbers come from `analysis.json` (`analyze.py`, `python3 -I`). Hashes in `receipt.json`.

Status: 252 stays provisional and non-eligible. 180 stays the accepted reference. Nothing here changes eligibility.

## Endpoints

| | 180 | 252 |
|---|---|---|
| Mean alive frames | 1854.47 | 1604.08 |
| Median alive frames | 1707.5 | 1370 |
| Q1 (bottom-16 mean) | 585.63 | 532.81 |
| Q4 (top-16 mean) | 3502.56 | 3192.31 |
| Mean score | 16.11 | 13.59 |
| Mean objective return | 29.65 | 24.63 |
| Deaths: normal / kamikaze / explosion / moving / static | 32 / 11 / 0 / 11 / 10 | 24 / 9 / 3 / 13 / 15 |

Integrity: `objective_return = 0.01·alive_frames + score − 5` holds for all 128 rows (max residual 1.4e-14). Every episode terminated by death, none truncated. Every death has exactly one observed lethal contact, matching `death_cause`.

Reproduction: mean change −250.39 (−13.50%) and paired bootstrap CI [−691.5, +176.4] match the frozen reconciliation and diagnosis.

## Where the observed mean loss comes from

**Paired change (252 − 180, same seed)**

| Quantity | Mean | Median | Better / worse | Bootstrap 95% CI | Sign test p |
|---|---|---|---|---|---|
| Alive frames | −250.4 | −136 | 28 / 36 | [−691, +176] | 0.38 |
| Score | −2.52 | −2.5 | 27 / 35 (2 tied) | [−7.41, +2.20] | 0.37 |
| Objective return | −5.03 | −3.71 | 28 / 36 | [−14.27, +3.98] | 0.38 |

Return splits evenly: survival term −2.50, score term −2.52. CIs cross zero. This does not show equivalence.

**Largest losses**
- Gross loss over seeds: 55,900 frames. Gross gain: 39,875. Net: −16,025.
- The 16 worst seeds sum to −40,527, which is 72% of gross loss. The other 48 seeds sum to +24,502.
- The 8 worst seeds sum to −25,250. Worst single seed: 3489660975, static → explosion, −3844 frames.

**First fatal cause, 180 → 252 (per policy, same environment seed)**
- 48 of 64 seeds change first fatal cause. Each seed's trajectory diverges, so these are post-divergence transitions.
- Median Δalive by the 252 cause (changed seeds only): static +1105 (n=14), normal −199 (n=12), moving −1309 (n=11), kamikaze −1442 (n=8), explosion −2109 (n=3).
- Mean alive at death: kamikaze 1695 → 995, static 2302 → 2275, moving 1467 → 1354, normal 1903 → 1656.

**Q1/Q4 membership**
- Bottom-16 overlap is 1 of 16 (15 left, 15 entered). Under independence P(overlap ≤ 1) = 0.040. This is lower persistence than chance on this pair.
- Top-16 overlap is 4 of 16. Expected 4.0 under independence, P(≤4) = 0.64.
- Q1 change −52.8, CI [−227.6, +64.2]. Q4 change −310.3, CI [−1074, +431]. Both cross zero.

**Strata by 180 membership (descriptive; selected on the 180 outcome, so regression-to-the-mean inflates the gaps)**
- 180 bottom-16: Δalive +1278 (14 better, 2 worse).
- 180 middle-32: Δalive −45.
- 180 top-16: Δalive −2188 (0 better, 16 worse).

**Score-matched survival (descriptive covariance, not causal adjustment)**
- Pooled common slope: 87.5 alive frames per score point.
- Score-matched Δalive: −29.7, CI [−100.0, +36.7]. Raw Δ is −250.4.
- Roughly 220 of the 250-frame raw drop lines up with the −2.52 score drop along the shared score-survival line. Score is a co-outcome, so this is a covariance split, not a causal adjustment.

## Hypotheses

**H1. Checkpoint-specific seed variation with regression to the mean.**
- Observations: sign p = 0.38; CI spans zero; bottom-16 overlap 1/16 (P = 0.04 under independence); 180 bottom-16 gains and top-16 losses are opposite in sign; Q1 CI spans zero.
- Predicts: on fresh seeds, the 252 − 180 gap shrinks toward zero and its CI crosses zero.
- Against: the gap persists with CI below zero on fresh seeds in both action modes.
- Discriminator: X1 from the parent plan. Eval-only on frozen 132/180/252 with a pre-registered fresh seed set (≥256, disjoint from the 64 dev seeds), argmax and sampled. Reuses existing checkpoints. No new instrumentation.

**H2. Worse handling of kamikaze lethal contacts at 252.**
- Observations: kamikaze deaths fall 11 → 9 but mean alive at kamikaze death falls 1695 → 995. Kamikaze-into seeds have median Δalive −1442 (n = 8), and three of the ten worst seeds are kamikaze-into (3489660952, 3489660980, 3489660984). Explosion deaths rise 0 → 3 with mean alive 748.
- Predicts: 252 reaches its first lethal kamikaze contact earlier in episodes than 180 does, relative to other causes.
- Against: kamikaze share of deaths is roughly stable (11/64 → 9/64), and per-seed comparisons are post-divergence.
- Discriminator: per-death telemetry giving time since the first kamikaze entered a threshold proximity, and the kamikaze state at that moment, for both checkpoints on the same seeds. Check `docs/v2-death-telemetry-2026-10-25.md` for existing fields first. Needs bounded instrumentation, not a new framework. Observed contacts are not counterfactual killers, so telemetry must not be read as causal.

**H3. Score-driven native difficulty and reward-value shift.**
- Observations: score and alive co-move (slope 87.5 frames per point; Pearson 0.985 at 180 and 0.978 at 252 per the frozen diagnosis). Score-matched Δalive is −30 (CI −100 to +37), versus raw −250. The reward split is even (survival −2.50, score −2.52). Static-pattern deaths have the highest score (21 at 252) and the longest survival (2275). Median score falls 13.5 → 9.75.
- Two readings: (a) native difficulty confounding. Score increments drive `apply_difficulty` and pattern enablement, so score drops are upstream of survival. (b) Reward value. The policy trades score events against the 0.01-per-frame survival term.
- Predicts (a): the survival drop tracks difficulty state at death, not checkpoint identity. (b): training-reward share from score events falls for 252 relative to 180.
- Against: a matched Δ near zero would support (a) alone. The −30 point estimate is consistent with that but not separable from zero.
- Discriminator: (a) per-death difficulty and `patterns_enabled` state, with score-event timing. (b) reuse the existing `training-episodes.jsonl` to split per-episode return into score and survival terms. Only if (b) favors reward value would a controlled reweighting experiment be justified, and that is framework work.

## Carried EV and gradient findings (quoted from prior artifacts, not recomputed)

- Child window EV pre-update first-8 → last-8: 0.435 → 0.460. This is rising, which means no EV decline in the 252 window. The parent window declined 0.492 → 0.433. Neither supports or refutes H1–H3.
- Critic MSE fits: 72/72 improved (as reported). This has no bearing on survival endpoints.
- CPU shadow gradient cosine: mean 0.0101, 31/72 negative. This is a raw single-probe CPU shadow, not Adam-preconditioned, so it is not a causal measure.
- Critic/actor weighted-norm ratio: 0.0189, consistent with the reported 1.89%.
- None of H1–H3 depends on these numbers. H2 could relate to critic value of kamikaze approaches, but nothing here tests that.

## Limits

- One lineage, two checkpoints, 64 fixed seeds. The bootstrap is conditional on this seed pair, not a training-seed CI.
- Death causes are censored endpoints and observed contacts, not hazard rates or counterfactual killers. No collision geometry, reaction-time, or resimulation claims.
- Score-conditioning is covariance, not adjustment: score is a co-outcome of survival.
- Q1/Q4 are bottom-16/top-16 means, not percentiles.
- Strata by 180 membership are selected on the outcome and are descriptive only.
- CIs crossing zero do not establish equivalence.
