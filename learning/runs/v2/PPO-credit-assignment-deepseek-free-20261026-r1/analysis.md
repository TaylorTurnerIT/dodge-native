# PPO temporal credit assignment audit (D2 retained-324, fixed vs linear LR)

Scope: closed JSON/JSONL certificates plus frozen source text only. No torch/runtime/native imports, no checkpoint
binary loads, no environment runs, no leases, no shared-state edits, no B/E/D3/student data. Writes confined to this
directory. Provenance: task metadata reports providerInstanceId `opencode`, model
`opencode/deepseek-v4.1-flash-free`; no paid fallback was used.

## Bottom line

1. **No reproducible GAE or bootstrap bug.** `compute_gae` handles termination and time-limit truncation correctly
   (`ppo.py:163-174`), `next_values` are zeroed only at termination (`ppo.py:337-338`), and the reward/scale identity is
   re-audited inside the update (`ppo.py:435-440`). The truncation path is also never exercised in these runs: 0 of
   1,934 fixed and 0 of 1,848 linear completed training episodes hit the 18,000-frame cap, and all 12 dev certificates
   report `caps: 0`. A mask bug cannot explain any fixed/linear difference here.
2. **The arithmetic horizon is short relative to the episode and to the eval metric.** γ=0.995 is per decision
   (K=4): 200 decisions = 800 raw frames; GAE (γλ=0.94525) carries 18.3 decisions = 73 frames of direct credit, with a
   49-frame half-life. Training episodes average 1,984/2,070 frames (496/518 decisions), dev episodes 2,270–3,098 frames
   (568–775 decisions). The −5 death penalty (scaled −0.5) keeps 36% of its weight at 18 decisions, 6% at 50 and 0.36% at
   100; at a 3,000-frame episode it is worth 0.0117 of a 1.48 value at episode start (0.8%).
3. **The dev effect size sits below the critic's own noise.** The selected 348 gain of +158.72 mean alive frames is worth
   about 0.0081 learner-scaled value units, i.e. 4.2% of one critic residual sd (0.193). The critic explains 0.38/0.42 of
   in-sample target variance (fixed/linear) and its predictions have only 0.41/0.43 of the targets' variance.
4. **No sustained schedule effect in the certificates.** Post-baseline mean alive, linear − fixed, is +87.9 ± 155.2
   (35/64 seeds positive). The 348 peak is smaller than the typical maximum of six noisy phase means under a
   seed-bootstrap null (null max mean +238.9, p95 +503.5; observed +158.7, p=0.689). The 384 endpoint is −377.8 ± 297.7
   between arms and −668.8 ± 258.1 versus its own 324 start. Treat 348 as a selected dev point, not evidence of a
   schedule effect.

## 1. Start state and the one changed variable

Both arms restore model/Adam/RNG to the identical component hashes (`entry-restoration.json`: model
`3b72815f…`, Adam `cf5e2a7a…`, RNG `cb96ee8d…`, `matched: true`), from parent
`c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc` with `run_seed 4200000001`. Update 1 is the same
rollout (same 20 completed episodes, seeds, frames and scores) and the same update to ~1e-7 relative (MPS kernel
nondeterminism, not a divergence), so both arms start at LR 3e-5.

LR: fixed = constant 3e-5 (not logged in `training-metrics.jsonl`; supported by the inherited arm config and by
update-1 equality with the linear arm, which logs 3e-5). Linear:
`3e-5 − 2e-5·(u−1)/59`, origin cumulative 372, hold after; 2.2203e-5 at local 24, 1.0e-5 at local 60. Total LR mass
1.8e-3 vs 1.2e-3. Both arms: 60 updates, 128 optimizer steps/update (16,384 transitions, 512-sample minibatches,
4 epochs), 7,680 steps, 0 KL early stops, all metrics finite.

Unresolved provenance anomaly: the 324 checkpoint binaries differ byte-wise between arms
(`bffa63a8…` vs `d976b257…`) while component hashes, the 324 dev rows, and update 1 all match. Cause cannot be
determined without binary inspection, which this brief forbids.

## 2. Development certificates (64 fixed seeds, deterministic argmax)

`Q1`/`Q4` below are the certificates' fields. They are **quartile-group means** (mean of the lowest 16 and highest 16
episodes, `runner.py:729`), not percentiles; recomputing row-wise percentiles gives different numbers. Medians are
included so the spread is readable.

| Phase | Arm | Mean alive | Median | Q1 group | Q4 group | Mean score | Caps |
|---|---|---|---|---|---|---|---|
| 324 | fixed/linear | 2939.40625 | 2569.5 | 767.5 | 5468.6875 | 29.53125 | 0 |
| 336 | fixed | 2708.32813 | 2322.5 | 719.3125 | 5259.875 | 27.32813 | 0 |
| 336 | linear | 2531.31250 | 2409.5 | 644.0625 | 4673.75 | 23.92969 | 0 |
| 348 | fixed | 2351.67188 | 1976.5 | 664.5625 | 4491.875 | 22.10938 | 0 |
| 348 | linear | **3098.12500** | 2896.5 | 867.0625 | 6003.875 | 31.51563 | 0 |
| 360 | fixed | 2372.65625 | 1933.5 | 655.875 | 4768.5625 | 22.78906 | 0 |
| 360 | linear | 2535.14063 | 1981.0 | 835.4375 | 4831.3125 | 24.46094 | 0 |
| 372 | fixed | 2561.31250 | 2499.5 | 662.0625 | 4762.5625 | 24.63281 | 0 |
| 372 | linear | 2646.56250 | 1997.0 | 755.75 | 5093.8125 | 26.73438 | 0 |
| 384 | fixed | 2648.37500 | 2333.0 | 702.4375 | 5087.4375 | 27.14844 | 0 |
| 384 | linear | **2270.59375** | 1954.5 | 637.9375 | 4431.8125 | 21.78906 | 0 |

Paired linear − fixed (64 seeds): 336 −177.0 ± 330.1; 348 +746.5 ± 335.9 (40/24); 360 +162.5 ± 287.7; 372 +85.3 ± 320.3;
384 −377.8 ± 297.7.

Within-arm versus the shared 324 start: linear 348 +158.7 ± 287.2, linear 384 −668.8 ± 258.1; fixed 348 −587.7 ± 323.0,
fixed 384 −291.0 ± 332.0. `dev-phases.csv` and `per-update.csv` hold the tables; per-seed rows are reproducible from
the certificates.

Selection check: bootstrap over seeds with each phase's mean removed (20,000 draws, seeded). The null distribution of the
best of the five post-baseline phase means has mean +238.9 and p95 +503.5 for the linear arm; the observed 348−324 value
is +158.7, p=0.689. Block signs at 348: between-arm +798/+201/+391/+1596 across the four fixed 16-seed blocks, but
within-arm versus 324: −351/−173/+450/+710. At 384 the between-arm difference is negative in three of four blocks and the
within-arm change is negative in all four.

## 3. Horizon accounting, in decisions and raw frames

| Quantity | Decisions | Raw frames |
|---|---|---|
| Action repeat K | 1 | 4 |
| γ=0.995 horizon, 1/(1−γ) | 200 | 800 |
| GAE trace mass, 1/(1−γλ) | 18.26 | 73.1 |
| GAE half-life, ln½/ln(γλ) | 12.31 | 49.2 |
| Rollout window | 256 | 1,024 |
| Training episode, mean | 496 (fixed) / 518 (linear) | 1,984 / 2,070 |
| Training episode, median | 435 / 451 | 1,739 / 1,803 |
| Dev episode 348, mean | 775 | 3,098 |
| Raw-frame cap | 4,500 | 18,000 |

Consequences drawn from the reward function alone (γ per decision, reward scale 0.1 applied once, `ppo.py:333`):

- Direct terminal credit decays as (γλ)^d. The −5 death penalty (scaled −0.5) contributes −0.285 at 10 decisions,
  −0.181 at 18, −0.122 at 25, −0.030 at 50, −0.0018 at 100, ≈6e-6 at 200. Only ~9.4% of transitions are
  within 50 decisions of a death and ~1.9% within 10.
- Everything further back must be carried by the bootstrap value. In learner units the dense reward is
  0.0076/decision (`(0.01 alive + 0.009 score)/frame × 4 × 0.1`). Episode-start value of surviving T frames:
  500→0.444, 1,000→0.948, 2,000→1.361, 3,000→1.479, 4,000→1.513, 6,000→1.525, 18,000→1.527. Marginal value per extra
  frame at 3,000 frames is γ^750≈0.023 of a frame's reward.
- Closed-loop check of that arithmetic: predicted trajectory-mean value from each episode's realised reward stream and
  length is 0.889 (fixed) / 0.911 (linear) against logged GAE target means 0.931 / 0.954 — a 4.6% gap, consistent with
  bootstrap and sampling, so γ-per-decision and the reward scale are as registered.
- The 348 gain of 158.72 frames is worth 0.0081 learner units at the point of realisation (extra dense reward plus a
  later death), against critic residual sd 0.193. That is 4.2% of the critic's noise: the metric difference the trial
  selected on is far below the value error the policy gradient has to work through.

What this does **not** show: that the horizon *causes* the fixed/linear difference. The dev band 2,270–3,098 frames
corresponds to episode-start values 1.40–1.48; the 159-frame within-arm gain is ~0.5% of that value band and the 746-frame
between-arm gap at 348 is ~2.4%, both inside the across-seed eval noise. The horizon argument explains why differences of
this size are hard to learn and measure; it does not assign them a cause.

## 4. Source audit (pinned runtime, `ppo.py` sha256 `b3cef91b…`)

GAE (`ppo.py:163-174`):

```python
bootstrap    = (~terminated[step])
continuation = (~(terminated[step] | truncated[step]))
delta  = rewards[step] + gamma * next_values[step] * bootstrap - values[step]
carry  = delta + gamma * gae_lambda * continuation * carry
```

- Termination: `bootstrap=0` and `next_values` is already zeroed at `ppo.py:337-338`; the recurrence stops.
- Time-limit truncation: `bootstrap=1` (final observation's value is used) and the recurrence stops. This is the correct
  treatment for a non-terminal time limit.
- Overlap is rejected (`ppo.py:162`), so the double-mask case cannot silently occur.
- Initial `carry=0` is the ordinary rollout-window cut, not a bug: step T−1 bootstraps from `next_values[T-1]`.
- The repo copy of `compute_gae` is identical (the only runtime delta is the gradient-alignment hook), and
  `python/tests/test_ppo.py:31-71` asserts the truncation-bootstrap case explicitly.

Reward path: `env.rs:216-224` counts alive only on non-dead frames, sets `truncated` at `gameplay_frames >= cap` and
breaks on either boundary; `env.rs:451-452` builds the step reward; `ppo.py:245` and `ppo.py:435` recompute the identity
`score/65536 + alive/100 − 5·terminated`, and `ppo.py:440` re-checks `rewards == raw × 0.1` exactly.

Loss and diagnostics:
- No value clipping anywhere (`ppo.py:6`, `ppo.py:505`), so no clip-masked value target; value loss is plain
  `0.5·mean((V−return)²)`.
- Advantages are normalised per minibatch (512 samples, `ppo.py:485-486`), not per rollout. Relative ordering is
  preserved, but the effective advantage scale varies between minibatches.
- Explained variance (`ppo.py:573-575`) is in-sample and self-bootstrapped: targets are `advantage + rollout value`, so
  the targets are built from the critic itself. Target variance therefore depends on the critic's own dispersion, EV is
  not comparable across arms with different critics, and it is not a generalisation measure.
  `critic_diagnostics.py:131` states `in_sample_self_bootstrapped_targets;not_held_out`; post-update EV adds four epochs
  of fit on the same 16,384 rows.
- Gradient interference: one CPU-shadow probe per update, at the first minibatch of epoch 0 only, on a float32 CPU clone
  (`ppo.py:488-495`, `gradient_alignment.py:67-89`, `measures_live_MPS_gradients: false`). Weighted critic norm is
  1.7–1.8% of actor norm; cosine is +0.006 ± 0.094 (linear) and −0.003 ± 0.081 (fixed), i.e. sign-random at the
  512-sample probe. It cannot support a 60-update divergence claim, in either direction.
- Diagnostic label defect (not a training bug): `gradient_alignment.py:88` reports `minibatch_count = len(actions)`,
  which is 512 samples, not the 32 minibatches per epoch.

## 5. Training-side evidence (both arms, 60 updates)

| Metric | Fixed | Linear |
|---|---|---|
| EV pre / post (in-sample) | 0.383 / 0.409 | 0.415 / 0.434 |
| Target variance (pre) | 0.0625 | 0.0636 |
| Prediction variance / target variance | 0.41 | 0.43 |
| Entropy | 1.659 | 1.649 |
| approx_kl | 0.0060 | 0.0043 |
| clip_fraction | 0.0314 | 0.0191 |
| Deaths per episode cohort | 1,934 completed: normal 1,014, kamikaze 357, static 339, moving 186, explosion 38 | 1,848: 872 / 376 / 363 / 190 / 47 |
| Abandoned parent episodes at resume | 64 | 64 |

- EV pre rises 0.303→0.357 (fixed) and 0.303→0.444 (linear). The critic does improve in-sample; it still leaves ~57%
  of target variance unexplained, and it captures under half of the target spread. In-sample EV is higher in the arm
  whose late dev endpoints are worse (384: 2,270.6 vs 2,648.4), so EV does not track policy outcome.
- Entropy stays near 1.65 (ln 9 = 2.197) in both arms for 60 updates: the training policy remains broadly stochastic.
  Dev evaluation is deterministic argmax, so a dev row has no run-to-run noise; the ±300-frame SEs above are across-seed
  standard errors (uncertainty over the seed population), not repeated-evaluation noise.
- The 64 `abandoned_on_fresh_env_resume` rows at local update 1 are parent in-flight episodes dropped because the
  continuation starts a fresh environment at the saved next episode index. They are not in any PPO buffer, are equal
  across arms, and are not a GAE defect.
- Death-cause counts swing across checkpoints (e.g. kamikaze 9→15→9 linear; 9→19 fixed at 384) and death cause changes
  on most seeds. Descriptive only; they do not identify a mechanism.

## 6. Bug vs hypothesis vs evidence

| Claim | Status |
|---|---|
| GAE terminal/truncation masks or bootstrap wrong | **Ruled out for this regime.** Code correct by inspection and unit test; truncation never fires (0 episodes at cap in training, 0 caps in all dev certificates). |
| Death penalty double-counted or reward scale applied twice | **Ruled out.** `env.rs:451-452` plus runtime audits `ppo.py:245,435,440`. |
| Value clipping distorts the critic | **Not applicable.** No clipping exists. |
| In-sample EV read as generalisation or as schedule benefit | **Interpretation error risk.** EV is self-bootstrapped and in-sample, saturates ~0.44, and is higher in the worse-endpoint arm. |
| Gradient interference explains the divergence | **Not supported.** 1.7–1.8% relative critic norm, sign-random single-probe cosine, CPU shadow only. |
| Linear 348 is a real, sustained gain | **Not supported as stated.** Selected maximum; null max mean +238.9 vs observed +158.7 (p=0.689); sustained +87.9 ± 155.2. |
| Short effective credit horizon relative to episode length limits what 60 updates can learn | **Supported arithmetic, unproven mechanism.** Direct death credit decays in ~100 decisions; the dev effect is 4% of critic residual sd. Needs the diagnostic below. |
| Critic error, not the LR schedule, dominates the 348/384 swings | **Hypothesis.** Not tested; the closed files contain no per-transition advantages or value errors. |

## 7. One recommended next diagnostic (cheap, falsifiable, no training)

**Critic long-horizon calibration probe on the retained 348 checkpoint.** One deterministic dev replay over the same 64
registered seeds (the existing `dev_eval` path, ~10 s, no optimizer steps), logging per-decision reward and `V(s_t)`, and
comparing `V(s_0)` with the exact discounted Monte-Carlo return `G_0` computed from the logged rewards. Cost: one dev
evaluation, no new seeds, no training, no checkpoint writes.

Pre-register before running: pass = |mean(V(s0) − G0)| ≤ 0.10 learner units and Pearson r ≥ 0.5; fail = |bias| > 0.20 or
r < 0.3. Expected magnitudes from this audit: mean G0 ≈ 0.9–1.5, critic residual sd ≈ 0.19.

- If it fails, credit assignment is critic-limited at the episode scale and the next lever is critic capacity/targets
  (e.g. value loss weight, longer critic warm-up, or λ), not the LR schedule.
- If it passes, the critic carries long-horizon value at episode start and the 348/384 swings are better explained by
  policy sampling noise or optimisation, and the hold-LR experiment becomes the more informative next run.

Why not the hold-LR continuation first: it changes one LR constant but its endpoint has ±300-frame dev noise over 12
updates, so it is underpowered against the effect it would test, and it does not measure credit assignment at all.

## 8. Limitations

1. n = 1 training pair, one training seed family, one parent checkpoint; all phase comparisons use the same 64 dev
   seeds, and 348 was selected on them.
2. Fixed-arm LR is inferred (constant 3e-5) from the inherited config and update-1 equality; it is not logged per update.
3. The horizon/leverage analysis is arithmetic on the reward function and γ, not a measurement of advantage quality;
   per-transition advantages and value errors are not in the closed files.
4. The value-unit conversion of a dev gain uses the 348 mean alive frame as the realisation point and is order-of-magnitude,
   not exact.
5. The 324 checkpoint binary hash discrepancy between arms is unexplained.
6. Formal retention of the linear 348 receipt is still pending; `competence_passed` is a gate flag, not acceptance.

## 9. Evidence

`evidence.json` (this directory) carries all numbers, source hashes, certificate hashes, and the audit strings.
`horizon_audit.py` regenerates everything with `python3 -I horizon_audit.py` (stdlib only).

| Source | SHA-256 prefix |
|---|---|
| `runtime/dodge_rl/ppo.py` | `b3cef91b1293056e` |
| `runtime/dodge_rl/critic_diagnostics.py` | `272059f7c12ebe30` |
| `runtime/dodge_rl/gradient_alignment.py` | `cd7d16aebe9eed24` |
| `runtime/dodge_rl/dev_eval.py` | `eecf71936f109381` |
| `crates/dodge-rl-env/src/env.rs` | `39f7ea0720e349ab` |
| `crates/dodge-rl-env/src/config.rs` | `49d631bed0bd99fc` |
| `docs/SPEC_PRIVILEGED_VIT_RL.md` | `02230eea7a3b36c7` |
| `registration-final-r2.json` | `0a6bf98221689ffc` |
| fixed `training-metrics.jsonl` | `2229013ee8930f22` |
| linear `training-metrics.jsonl` | `588cbd13e12d0eb5` |
| fixed `development-000348.json` | `f9ad28da316c8194` |
| linear `development-000348.json` | `f0da173689fd7d74` |
| linear `development-000384.json` | `7fd51bc029e6e8b4` |
| fixed `development-000384.json` | `b1b02f1f217b0f3a` |

Repo `README.md` hash at read time: `be478416b33c772a7ff9c28f2c974f767c205f7df77bcf7346ab36133d384652` (matches the
protected value).
