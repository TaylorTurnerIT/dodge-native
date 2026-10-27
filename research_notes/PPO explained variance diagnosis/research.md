# PPO explained variance diagnosis (Dodge teacher, long D2 run r2)

Scope: whether the observed EV decline (first20 0.598 → last20 0.317) means more training of the unchanged config is likely harmful. Source authority: frozen `learning/runs/v2/postovernight-long-D2-boundary-prepare-r14/capsule-final/python/dodge_rl/ppo.py` (SHA256 533055b0…4b239a58, identical to current `python/dodge_rl/ppo.py`). Not the unused `learning/python/dodge_learning/ppo.py`. Log stats below are stdlib recomputations from `learning/runs/v2/postovernight-long-D2-campaign-r2/training-metrics.jsonl` (384 rows, SHA256 c81cc153…6afc23). Current best D2 development checkpoint (deterministic argmax, 64 fixed seeds): survival Q1=648.25, Q4=4508.8125, mean=2240 frames (gate mean ≥3060); score Q1=3.5, Q4=46.59375, mean=20.59375. Final checkpoint mean alive 1654.546875. Best is selected among 24 development evals, not held-out.

## Q1. What EV measures here, and is lower EV necessarily bad?

### Takeaway
In this implementation EV = 1 − Var(Â)/Var(V_old + Â): it scores the previous update's critic, on fresh data from the current policy, against λ-returns that are themselves bootstrapped from that critic. Lower EV is not automatically bad and does not imply that more training must lower it; it is ambiguous between benign target/policy shift and growing critic residual.

### Cited Findings
- SB3 defines EV as `1 - np.var(y_true - y_pred) / var_y`; per its docstring (paraphrased by fetch tool) 1 = perfect, 0 = no better than predicting zero, negative = worse than that; NaN when target variance is 0 — [SB3 utils.py](https://raw.githubusercontent.com/DLR-RM/stable-baselines3/master/stable_baselines3/common/utils.py)
- SB3 PPO computes EV from `rollout_buffer.values` and `rollout_buffer.returns`, i.e. rollout-time predictions, not post-update predictions — [SB3 ppo.py](https://raw.githubusercontent.com/DLR-RM/stable-baselines3/master/stable_baselines3/ppo/ppo.py)
- CleanRL computes `explained_var = 1 - np.var(y_true - y_pred) / var_y` with `y_pred = b_values` collected under `torch.no_grad()` during the rollout — [CleanRL ppo.py](https://raw.githubusercontent.com/vwxyzjn/cleanrl/master/cleanrl/ppo.py); docs describe it only as "the explained variance for the value function" — [CleanRL PPO docs](https://docs.cleanrl.dev/rl-algorithms/ppo/)
- GAE trades variance for bias via an exponentially weighted (TD(λ)-like) estimator using a learned value function — [Schulman et al. 2015, GAE](https://arxiv.org/abs/1506.02438)
- Learned PPO value estimators "fail to fit the true value function" even when agents train successfully — [Ilyas et al. 2018](https://arxiv.org/abs/1811.02553)

### Current measured / source facts (this repo)
- `compute_gae` sets `returns = advantages + values` (ppo.py:171). EV at ppo.py:547-549 uses `returns - batch.values`, so the residual is exactly the GAE advantage Â. EV = 1 − Var(Â)/Var(V_old+Â). It is computed after optimization but with frozen rollout predictions; it says nothing about the post-update critic.
- Because the variance of the residual is taken (not MSE), a constant bias in V is invisible to EV; it is also invisible in the advantage after per-minibatch normalization (ppo.py:476-477). A scale miscalibration (e.g. V = 0.5·true) is penalized only partially.
- Targets are self-referential: λ=0.95, γ=0.995 per K4 decision (effective λγ horizon ≈ 1/(1−0.94525) ≈ 18 decisions ≈ 73 raw frames; γ horizon ≈ 200 decisions ≈ 800 frames). Most of the target beyond ~18 decisions comes from the critic itself, so EV is not a Monte-Carlo fit statistic.
- `value_loss` (0.5·MSE of the evolving critic over minibatches, ppo.py:487) is a different quantity from EV's residual. Do not compare their trends as if same predictions.

### Inferences
- EV falls if (a) Var(Â) rises (critic residual, or a larger policy change between collection and evaluation shifting returns away from V_old), or (b) Var(returns) falls (e.g. fewer deaths per decision removing the high-variance −0.5 learner-scale penalty). (b) is benign; (a) can be benign (fast policy improvement) or harmful (critic underfitting/instability).
- There is no general theorem that more PPO training lowers EV; in typical successful runs EV rises then plateaus. A trend in one run under constant LR cannot separate a time effect from a state (policy-distribution) effect.
- Distinguishing benign shift from critic failure requires measurements absent from logs: Var(returns), Var(Â), mean(Â) (bias), post-update EV on the same batch, and Monte-Carlo-return fit on completed episodes.

### Gaps
- No raw rollout return/advantage variance logs exist, so the numerator/denominator split cannot be measured from retained data.
- No source found giving a quantitative "healthy EV" threshold; such thresholds are folklore and are not used here.

## Q2. Source-grounded assessment of the observed trajectory

### Takeaway
Logs are most consistent with a rising critic residual under a growing, KL-capped policy step through a shared trunk, not with target-variance collapse — but this rests on a crude proxy and is a hypothesis, not a demonstrated critic failure. No bug was found.

### Cited Findings
- Shared policy/value networks can suffer "interference between objectives"; separate networks avoid it, and PPG lets the value function be "more aggressively optimized with a higher level of sample reuse" — [Cobbe et al. 2020, PPG](https://arxiv.org/abs/2009.04416)
- In the ICLR implementation-details study, Atari PPO uses a shared network and MuJoCo separate networks; separate networks "clearly outperform" in simpler environments, attributed to "competing objectives of the policy and value functions"; approx_kl "stays below 0.02" in their runs; value-loss clipping found unhelpful/harmful by Engstrom et al. and Andrychowicz et al.; reward scaling "can significantly affect performance" — [Huang et al., ICLR Blog Track 2022](https://iclr-blog-track.github.io/2022/03/25/ppo-implementation-details/)
- SB3 stops at `approx_kl_div > 1.5 * target_kl` per minibatch; CleanRL checks `approx_kl > target_kl` after each epoch, disabled by default — [SB3 ppo.py](https://raw.githubusercontent.com/DLR-RM/stable-baselines3/master/stable_baselines3/ppo/ppo.py); [CleanRL ppo.py](https://raw.githubusercontent.com/vwxyzjn/cleanrl/master/cleanrl/ppo.py)

### Current measured facts (48-update bins, updates 1-384)
| metric | bin1 | bin4 | bin8 |
|---|---|---|---|
| EV | 0.586 | 0.503 | 0.340 |
| value_loss | 0.0119 | 0.0163 | 0.0191 |
| approx_kl (epoch-end, full rollout) | 0.0174 | 0.0305 | 0.0316 |
| clip_fraction | 0.173 | 0.221 | 0.221 |
| epochs completed | 4.00 | 3.65 | 3.42 |
| critic-head grad norm | 0.0458 | 0.0360 | 0.0339 |
| trunk grad norm | 0.393 | 0.642 | 0.708 |
| actor-head grad norm | 0.502 | 0.442 | 0.427 |
| 4 − raw_frames/decision (death-truncated frames proxy) | 0.00933 | 0.00671 | 0.00572 |
- Pearson corr across updates: EV vs value_loss −0.77; EV vs approx_kl −0.57; EV vs entropy +0.32. No negative EV after update 1 (update 1 EV −0.0287 is the phase-start baseline). EV per-update SD ≈0.054 (first 100) and ≈0.061 (last 100).
- Proxy Var(returns) ≈ 2·value_loss/(1−EV) stays ≈0.058-0.066 across bins (first20 0.068, last20 0.058). Crude: uses post-update value_loss as stand-in for the pre-update residual, so it understates the residual; directionally it suggests the denominator did not collapse while the residual rose.
- Lost frames per decision fell ~39%, consistent with fewer deaths per decision (longer rollout episodes) — the -0.5 death term contributes less target variance, while score events per decision may rise. Net effect on Var(returns) is unmeasured.
- Constant LR 3e-4 (no annealing in ppo.py config), clip 0.2, max_grad_norm 0.5 global over actor+critic+trunk; vf_coef 0.5; reward_scale 0.1 fixed; no value clipping or return normalization; critic head 128→128→1 GELU on shared CLS latent (teacher.py:97-103,172-175).
- Truncation bootstrap: `next_values` uses V(final obs) on truncation and 0 on termination (ppo.py:336-338); recurrence stops at either boundary (ppo.py:166-169). This matches standard practice; no defect seen.

### Hypotheses (unproven, ranked)
1. Shared-trunk drift: trunk gradient grows (0.39→0.71) while critic-head gradient shrinks; policy steps at the KL ceiling move the shared representation each update, so V_old is stale on new-policy states. Moderate confidence it contributes; causal size unknown.
2. Critic under-optimized relative to target nonstationarity: KL early stop cuts epochs (4.0→3.4), reducing critic steps too, since critic and actor share one loop; global grad clipping lets the larger policy/trunk gradient dominate the clip budget. Moderate-low confidence.
3. Benign target shift: longer survival changes the return distribution (more score-driven variance, fewer deaths), raising irreducible residual within an ~18-decision λ horizon. Cannot be excluded without Var/MC data.
4. Reward scale / vf_coef: learner returns are small (proxy Var ≈0.06), so value gradients are small vs policy gradients (critic-head norm ≈0.034 vs actor ≈0.43). Plausible contributor to (1)/(2); not shown.

### Gaps
- No per-minibatch KL or clip-hit statistics; gradnorm averages >0.5 do not show every minibatch clipped.
- Development score/survival is not monotone; the EV decline coincides with improving smoothed development score (6.87→17.46), so EV decline has not been shown to harm returns.

## Q3. Separation of cited, measured, inferred
- Cited general facts: EV definitions and rollout-time timing (SB3, CleanRL); GAE bias/variance (Schulman 2015); learned critics poorly fit true values even in working PPO (Ilyas 2018); shared-network interference (PPG; ICLR details blog).
- Measured: table above; source anchors ppo.py:166-171, 336-338, 476-477, 487, 501, 539, 547-549.
- Hypotheses: Q2 list; none established as cause.

## Q4. Cheapest next discriminator (proposal only; authorizes nothing)
Add read-only critic diagnostics to a short continuation (e.g. 48 updates, same seed lineage, unchanged hyperparameters) from the best/ final checkpoint, and per update log: Var(returns), Var(Â), mean(Â); post-update EV on the same batch (recompute V with updated model, no grad); EV of V_old against discounted Monte-Carlo returns on episodes completed inside the rollout; EV split by terminal-containing vs alive-only windows; fraction of minibatches where clip_grad_norm actually clipped; critic-only gradient-norm share before clipping. Decision rules: (A) if Var(returns) falls and post-update EV stays high (≥ the pre-update EV of early updates, ~0.55-0.6) → decline is mostly target/staleness shift; unchanged longer training is justified on the survival gate, EV not a gate. (B) if post-update EV is also low and MC-return EV falls, with Var(returns) flat → critic underfitting; justify a critic correction test (separate critic or more value epochs/PPG-style auxiliary phase, or higher vf_coef), compared on the D2 survival mean. (C) if post-update EV is high but pre-update EV low and mean |ΔV| between consecutive updates large → staleness from shared-trunk drift; consider lower LR/KL target before a long run. Avoid requiring rising EV as success.
