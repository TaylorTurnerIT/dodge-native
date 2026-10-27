# D2 retained276 → 348 plateau diagnosis (Haiku, read-only)

Scope: completed runs `D2-retained204-lr1e4-20261026-r1` (204→276) and `D2-retained276-continuation-20261026-r2` (276→348), both LR 1e-4. Analysis only: no checkpoint load, model, environment, MPS, training, evaluation, lease, or source change. Script `analyze.py`; numbers in `metrics.json`; input hashes in `receipt.json`. Survival is the goal; EV is diagnostic only. All numbers are on the fixed 64 development seeds, which were reused for selection, so none are held-out.

## Observations

**1. The 204→276 gain is borderline, and 276 was the max of 7.** Mean alive frames: 1921 (204), 1578, 1853, 1974, 2244, 2188, **2484 (276)**. Paired against 276 (seed bootstrap, 2000 draws):

| Comparison (276 minus candidate) | Mean diff (frames) | 95% CI | Improved / worsened seeds |
| --- | ---: | ---: | ---: |
| vs 204 | +562.5 | [−27.7, +1149.2] | 38 / 26 |
| vs 216 | +906.0 | [406.3, 1453.2] | |
| vs 228 | +630.9 | [92.7, 1177.0] | |
| vs 240 | +509.2 | [4.0, 1006.4] | |
| vs 252 | +239.3 | [−294.7, 792.7] | |
| vs 264 | +295.7 | [−284.9, 868.7] | |

The 276 win over 204 is at the CI edge, and 276 was chosen as the highest of seven on these same seeds, so its advantage is optimistic.

**2. The 276→348 continuation is flat.** Candidate means: 276 2484, 288 2301, 300 2137, 312 2468, 324 2437, 336 2237, 348 2273. Slope across the 7 candidates is −1.37 frames/update (bootstrap CI [−6.9, +4.5]). The six post-276 candidates average 2309 (SD 125). 276 sits +175 above that average. Every post-276 paired difference is negative (−15 to −346 frames), and every CI spans zero. No candidate beats 276 with significance, and none is clearly worse.

**3. Tail shape shifted.** Q1 rose from 567 (276) to 682–861 for 288–348. Q4 fell from 5172 to 4004–5117. Caution: paired tail changes conditioned on 276's own ranking are biased toward regression to the mean, so they are descriptive only.

**4. Death mix.** 276: normal 26, static 14, kamikaze 13, moving 10, explosion 1. 348: normal 32, kamikaze 16, static 9, moving 5, explosion 2. Counts are small; no death-cause claim is supported.

**5. Critic values (learner-scaled returns).** EV logged at update start equals `critic_diagnostics.pre_update.explained_variance` in 72/72 updates of both runs. Bin means (early / mid / late updates):

| Key | 204→276 | 276→348 |
| --- | --- | --- |
| EV pre | 0.423 / 0.376 / 0.440 | 0.412 / 0.433 / 0.416 |
| EV post (same batch, in-sample) | 0.476 / 0.435 / 0.494 | 0.470 / 0.487 / 0.472 |
| Target variance (pre) | 0.0633 / 0.0615 / 0.0685 | 0.0652 / 0.0681 / 0.0681 |
| Residual variance (pre) | 0.0364 / 0.0382 / 0.0383 | 0.0381 / 0.0384 / 0.0398 |

EV does not fall monotonically in either run: consecutive rises vs falls are 37/34 and 34/37. Per-update slope for EV pre is +0.00052 (CI [−0.00003, 0.00108]) in the first run and +0.00010 (CI [−0.00057, 0.00073]) in the second. Target and residual variance rose slightly in the first run, so EV was roughly stable. This does not reproduce the earlier falling-EV run (0.598→0.317 in `reports/PPO explained variance diagnosis.md`).

**6. Policy movement and entropy.**

| Key | 204→276 | 276→348 |
| --- | --- | --- |
| approx_kl (last epoch) | 0.0123 / 0.0138 / 0.0145 | 0.0153 / 0.0157 / 0.0161 |
| clip_fraction (PPO ratio clip) | 0.092 / 0.102 / 0.109 | 0.111 / 0.116 / 0.117 |
| Entropy | 1.731 / 1.707 / 1.676 (slope −0.00116, CI [−0.00134, −0.00099]) | 1.676 / 1.648 / 1.672 (slope −0.00003, CI [−0.00029, +0.00021]) |

Entropy fell steadily in the improving phase and was flat in the plateau. This fits, but does not establish, an exploration story. Early epoch stopping never fired: `early_stop_kl` was false in 72/72 updates and all updates ran 4 epochs (128 optimizer steps each, 9216 in total). The target KL of 0.03 never bound. The earlier run's 230/384 early stops do not apply here.

**7. Gradient norms.** Actor grad norm: 0.469 / 0.483 / 0.487 (204→276), 0.490 / 0.495 / 0.482 (276→348). Critic grad norm: 0.036 / 0.039 / 0.039 and 0.041 / 0.041 / 0.042. Trunk grad norm: 0.720 / 0.782 / 0.832 (rises 0.0025 per update, CI [0.0021, 0.0028]) and 0.871 / 0.933 / 0.913. The trunk norm rose more than the actor or critic norms. The fields do not identify its source. The trunk norm may include parts of the combined gradient, so this is an open question, not a finding.

**8. Gradient alignment (CPU shadow, one probe per update).** The probe is the first minibatch of epoch 0, pre-optimizer, on 33 shared parameters (286,976 elements). It is not live MPS and not Adam's update direction.

| Metric | 204→276 | 276→348 |
| --- | --- | --- |
| Cosine mean (SE) | −0.0128 (0.0125) | +0.0008 (0.0124) |
| Cosine median | −0.0071 | +0.0038 |
| Negative cosines | 38/72 (mean of negatives −0.090) | 35/72 (mean of negatives −0.079) |
| Cosine < −0.10 / > +0.10 | 14 / 7 | 10 / 11 |
| Cosine range | −0.230 to +0.416 | −0.372 to +0.234 |
| Critic / actor norm ratio, bin means | 0.0172 / 0.0186 / 0.0189 | 0.0177 / 0.0198 / 0.0197 |
| Max rotation of combined gradient, median (deg) | 1.04 (max 1.61) | 1.03 (max 1.97) |

Near-zero and negative cosines occur in about half of updates. Strong negatives are rare (10–14 of 72). Because the critic part of the shared-trunk gradient is about 2% of the actor norm, the combined direction rotates by at most about 1–2°, even at the most negative cosines. The data do not show harmful interference of meaningful size. Per-group cosines (embeddings, final_norm, layers.0, layers.1) have bin means within ±0.06 and no per-group CI was computed. They are treated as unresolved. The final_norm group has the largest ratio, bin means 0.043–0.057 across both runs, so its rotation bound is about 3°.

**9. Gradient clipping is always active in the probe.** `live_clip_coefficient` < 1 in 72/72 updates, with mean 0.43 (204→276) and 0.38 (276→348). The live pre-clip norm is above `max_grad_norm` 0.5. Adam's per-parameter normalization largely offsets global scaling, so this is a confound on relative gradient weights, not a clear step-size effect. The clip-fraction logged as `clip_fraction` is the PPO ratio clip, a different quantity.

**10. Horizon and timescale (structural, untested).** At `action_repeat` 4, the mean alive frames of 2300–2500 correspond to about 580–620 decisions. Gamma 0.995 has a timescale of about 200 decisions, so the discount at 600 decisions is about 0.05. This is an existing-doc calculation, not a measured effect.

## Observation vs hypothesis vs confound

| Item | Status |
| --- | --- |
| 276 advantage over 204/216/228/240 at 95% | Observed; optimistic because 276 is the max of 7 on the same seeds |
| 276→348 plateau (slope CI spans 0) | Observed |
| EV does not fall monotonically; EV pre/post stable | Observed |
| Entropy fell in 204→276 and was flat in 276→348 | Observed; link to plateau is a hypothesis |
| Critic share of shared-trunk gradient about 2%; rotation ≤ ~2° | Observed on the probe; does not measure live Adam direction |
| LR 3e-4→1e-4 coincided with the 204→276 gain | Observed; the LR change and the improving updates are the same transition, so the LR effect cannot be isolated from it |
| Selection of 276 as max of 7; seed reuse | Confound: inflates 276 |
| 64-seed paired CI half-width about 500–600 frames | Constraint: effects below about 500 frames are not resolvable in one run |
| Horizon too short for long survivals | Hypothesis, untested |
| Trunk-norm rise source | Open question |

## Ranked next options (one variable each, all from retained276)

**1. Lower LR, 1e-4 → 3e-5 (recommended).** Evidence: the only confirmed improving phase came with an LR drop; the same LR gave no gain in 276→348; the previously tested 3e-4 branch regressed (docs). Approx KL (~0.015) and clip fraction (~0.11) are well below the KL target, so this is not an obvious instability. Discriminator: whether the plateau is step-noise limited. Expected signs if LR-limited: `approx_kl` falls, entropy slope stays negative, and mean or Q1 rises. Expected if capacity- or horizon-limited: slope and paired differences stay flat. Falsifiers: (a) `approx_kl` does not fall, meaning the LR override did not take effect; (b) all candidate paired CIs span zero and the slope CI spans zero, meaning no detectable effect; (c) mean drops with CI excluding zero. Implementation: reuse the LR-override hook recorded in `lr-transition.json`, applied after exact model/Adam/RNG restore, with one `param_groups[*].lr` change.

**2. Entropy coefficient 0.01 → 0.02 (exploration).** Evidence: entropy fell in the improving phase and was flat in the plateau. Direction is ambiguous; the sign of the effect on survival is unknown. Discriminator: entropy slope and the kamikaze/explosion counts. Falsifier: entropy stays flat and paired diffs stay within CI. Ranked below option 1 because it has no direct evidence that exploration limits survival.

**3. Discount horizon, gamma 0.995 → 0.998.** Evidence: structural only; discount at 600 decisions is about 0.05. Discriminator: change in Q4 and in the paired tail. Falsifier: no paired gain with CI excluding zero. Ranked last because gamma also rescales the value targets, so the critic refits and the change is not a clean single-variable test.

**Not chosen.** Critic coefficient change and critic stop-gradient: the critic share of the trunk gradient is about 2% and EV is stable, so interference evidence is weak. Lower priority than the existing innovation-report rank implied. More training at 1e-4: flat slope and no post-276 candidate beats 276. Fresh seed with same config: measures seed spread and cannot improve the model.

## Recommendation

Run option 1 once: retained276 model, Adam state, and RNG restored; LR 1e-4 → 3e-5; 72 updates; same 64 development seeds and evaluation cadence; 1800 s outer cap; 6 GiB caps; exact-once. Pre-register the decision rule before launch: a candidate counts only if its paired CI against 276 excludes zero, and the slope CI over 72 updates is reported. Use `approx_kl` as the in-run check that the override applied. Expect only large effects (>~500 frames) to be detectable.

This is a diagnosis. It does not authorize training, change any checkpoint metadata or limits, or qualify any result. Parent acceptance of the 276→348 run remains pending.
