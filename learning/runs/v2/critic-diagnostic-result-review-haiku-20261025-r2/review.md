# Critic diagnostic D2 r2: result review (Haiku 5.5, read-only)

Scope: `critic-diagnostic-D2-20261025-r2`, updates 1-48, deterministic evals at updates 0, 24, 48. Diagnostic only; `training_eligible: false`, `promoted: false`. No checkpoints loaded, no imports of native/Torch/model code, no inference or training. Inputs and hashes are in `receipt.json`; numbers are in `analysis.json`.

## Integrity verdict

No blocking findings. All checks passed on recomputation:

- Artifact manifest: all 20 entries match SHA-256. Registration `registration-r4.json` matches `6ae91ee5...4dab6e`.
- Counters: 48 metric lines; `counters.updates` and `phase_update` equal 1..48; optimizer steps = 128 × update; transitions = 16384 each update; environment decisions = 786432 at update 48; final `raw_frames` = 3139120, equal to `worker-result.json`. `raw_frames` strictly increasing.
- Finiteness: 1776 float fields, 0 non-finite. All `finite` flags true. `early_stop_kl` never fired. `epochs_completed` = 4 every update.
- Critic moment identities hold to float64 rounding (max abs error ≈ 2.4e-16): `residual_mean = target_mean − prediction_mean`; `residual_mse = residual_variance + residual_mean²`; `residual_variance = tv + pv − 2·cov`; `EV = 1 − residual_variance / target_variance`.
- Target mean and variance are identical in `pre_update` and `post_update` at every update, so the pre/post comparison uses the same targets.
- Legacy `explained_variance` equals `pre_update.explained_variance` within 2.8e-8 at every update. It is the pre-update value, not post-fit.
- Evals: 64 episodes each, all terminated, none truncated. `alive_frames = fatal_gameplay_frame − 1` for every episode. Death-cause tallies match the rows. Each row has exactly one lethal contact. Seeds are identical across the three evals (3489660928 onward), so comparisons are paired. Recorded raw frames = sum of gameplay frames (18960 / 56807 / 70588).
- Per-episode `.jsonl` rows are in completion order, not episode order. Keyed by `episode_index` they equal the `.json` rows.

Minor, not defects:

- Each metric has its own cohort. `alive_frames` Q1/Q4 are the bottom/top 16 episodes sorted by alive frames. `score` Q1/Q4 are the bottom/top 16 sorted by score. Recomputation reproduces the recorded score Q1/Q4 only with the score-sorted cohort, at all three evals. Report labels should say so, because the two cohorts are different episode sets.
- Score-cohort boundaries have ties (42 zero-score episodes at update 0 bottom 16). Tied keys have equal values, so the reported means do not depend on tie-breaking.
- `diagnostic_survival_gate_passed: false` comes from `progress_passed("D2", …)` in `python/dodge_rl/survival_gate.py`. Its docstring says there is no score condition; I did not inspect `_alive`.
- `value_loss` is computed on training minibatches (`0.5 * mean((new_value − GAE_return)²)`). It is not the post-fit residual and is not used here to infer target variance.

## Critic fit: descriptive

- Within-batch fitting improves in-sample on all 48 updates. Post-update EV exceeds pre-update EV every time. Post-update residual variance is lower than pre every time; the post/pre ratio averages 0.77 (range 0.49–0.83). Pre-update EV is lowest at update 1 (−0.020).
- The post-minus-pre EV gap is larger early (about 0.135 for updates 1–8) than later (about 0.07–0.09). This is in-sample on the same batch and says nothing about held-out accuracy.

Window means (updates 9–16 → 41–48):

| quantity | 9–16 | 41–48 |
|---|---|---|
| pre EV | 0.694 | 0.562 |
| target variance | 0.0674 | 0.0628 |
| pre residual variance | 0.0201 | 0.0275 |
| pre prediction variance | 0.0573 | 0.0406 |
| target–prediction correlation (per-update mean) | 0.837 | 0.752 |
| squared mean residual | 0.00065 | 0.00005 |

- In the late window, the EV fall is driven by growing residual variance (+37%), not by shrinking target variance (−7%). Shrinking prediction spread and lower target–prediction correlation account for the residual growth.
- Changed bias is negligible after update 8. Early pre-update residual mean is about −0.10 (updates 1–5), then near zero.
- Early target variance fell sharply (0.113 in updates 1–8 to 0.067 in 9–16) while EV rose. Later target variance is flat (0.05–0.07).
- Per-update pre EV is noisy (about ±0.1 update to update, e.g. 0.611 at update 41, 0.494 at 47). Read window means, not single updates.

Training-side trends (window means, updates 1–8 → 41–48), descriptive only:

- approx_kl: 0.0148 → 0.0234
- clip_fraction: 0.148 → 0.204
- entropy: 1.873 → 1.762
- grad_norm: 0.595 → 0.740; trunk_grad_norm: 0.308 → 0.528
- actor_grad_norm: flat (about 0.50–0.51)

These do not establish a cause for the critic trend.

## Eval: descriptive

| eval | alive mean | median | alive Q1 (bottom 16) | alive Q4 (top 16) | score mean | score Q1 / Q4 |
|---|---|---|---|---|---|---|
| 0 | 295.25 | 166 | 165.44 | 566.38 | 1.48 | 0.00 / 4.81 |
| 24 | 886.61 | 634 | 490.31 | 1648.06 | 5.62 | 0.94 / 13.38 |
| 48 | 1101.94 | 665 | 521.06 | 2401.19 | 8.31 | 1.91 / 21.53 |

- Paired on the same 64 seeds, update 0 → 48: 58 episodes improved, 6 worse, median +493.5 alive frames.
- Update 24 → 48: 40 improved, 24 worse, 0 tied, median +54.5, mean +215.3. The later gain is smaller and mixed. Update 0 → 24 gained mean +591.4.
- Q1 rose 165 → 490 → 521 (most of the gain in the first 24 updates). Q4 rose 566 → 1648 → 2401.
- Death causes (first fatal contact; not counterfactual): normal_enemy 44 → 29 → 36; moving_pattern_rect 8 → 14 → 9; static_pattern_rect 12 → 13 → 7; kamikaze_enemy 0 → 7 → 11; kamikaze_explosion 0 → 1 → 1. Kamikaze deaths appear only in later evals. This is a descriptive mix shift, not a cause.
- Historical best (2240 mean, 4508.8 Q4, 648.25 Q1) came from a different, longer run with 24 evals. It is not duration-matched, so this run neither proves nor disproves superiority.
- No evidence in this run that more training harmed the policy: the mean and median alive frames rose from update 0 to 48. Late gains are smaller and noisier.

## Answers to the brief's questions

- Does within-batch fitting improve? Yes, in-sample, on all 48 updates.
- Is the EV fall driven by shrinking target variance, growing residual variance, or changed bias? In updates 9–48, growing residual variance with shrinking prediction spread and lower target–prediction correlation. Not target variance (flat), not bias (negligible).
- Does the run show harm from more training? Not supported by these data.

## Limits

- Updates 1–48 only; the historical late384 EV decline is not covered.
- Post-update EV is in-sample on self-bootstrapped fixed GAE targets. No held-out value estimate, no pass threshold.
- One run, one seed family (`run_seed` 3192039780), three eval points, one deterministic policy per eval.
- Q1/Q4 are bottom/top-16 means, not percentile cutoffs.
- Death causes are first fatal contacts, not counterfactual causes.
- `reports/PPO explained variance diagnosis.md` was not read; its hash is in `receipt.json`.

## Suggested next bounded step (unchanged learner)

1. Cheapest: stdlib-only, read-only analysis of `training-episodes.jsonl` (7.1 MB, not inspected beyond existence). If it carries per-episode return and length fields, check whether target variance and residual variance track episode length or reward spread across updates. Answers: which rollout property moves the target variance. Cannot answer: held-out accuracy or generalization of the critic.
2. If the parent authorizes one more run: the same unchanged learner, extended past 48 updates with evals at 72 and 96, to see whether residual variance keeps growing within one run. Cannot answer: comparison with the historical best or any claim about harm from longer training.

I have not authorized or scheduled either step.
