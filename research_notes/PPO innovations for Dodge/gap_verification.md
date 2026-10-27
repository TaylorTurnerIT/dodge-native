# PPO innovations for Dodge: gap verification (follow-up pass)

Date: 2026-10-25. One verification round, no further research round. Scope: literature plus frozen source read. No agents, no source implementation, no model/checkpoint/native/inference/training/env execution. Existing notes in this folder (`literature.md`, `source_log.json`, `experiments.json`) are unchanged. Machine-readable outputs: `gap_source_log.json`, `gap_experiments.json`.

Access limits: every web read is a WebFetch summary from a small model, not verbatim text. No PDF was read. Quoted phrases below are the summarizer's quotes of the page and should be checked against the PDF before a final report quotes them. Abstract-level reads cover 1602.07714, 1809.04474, 2009.04416, and 1506.02438. Section-level reads cover 2006.05990 (first 100,000 of 218,241 characters only) and 2005.12729. Local source was read directly with grep and sed.

## Gap 1: bibliographic integrity (Pop-Art attribution)

### Takeaway
The earlier attribution is wrong. arXiv 1602.07714 is Van Hasselt et al. 2016, "Learning values across many orders of magnitude". It proposes adaptive target normalization but never names it Pop-Art. The name PopArt, and the multi-task Atari-57 result, belong to Hessel et al. 2018, arXiv 1809.04474. Cite the two papers separately.

### Cited Findings
- arXiv 1602.07714 metadata: "Learning values across many orders of magnitude", Hado van Hasselt, Arthur Guez, Matteo Hessel, Volodymyr Mnih, David Silver; first submitted 24 Feb 2016. The abstract opens "Most learning algorithms are not invariant to the scale of the function that is being approximated" and proposes to "adaptively normalize the targets used in learning". Neither "Pop-Art" nor "PopArt" appears on the abstract page. [arXiv abs 1602.07714](https://arxiv.org/abs/1602.07714). Read scope: abstract, via summarizer.
- arXiv 1809.04474: "Multi-task Deep Reinforcement Learning with PopArt", Matteo Hessel, Hubert Soyer, Lasse Espeholt, Wojciech Czarnecki, Simon Schmitt, Hado van Hasselt; submitted 12 Sep 2018. The abstract reports results on the 57 Atari games with a single set of weights, and on 30 DeepMind Lab tasks. [arXiv abs 1809.04474](https://arxiv.org/abs/1809.04474). Read scope: abstract, via summarizer.
- Earlier-note claims that are NOT verified this round: the "Double DQN + PopArt matched or beat clipped Double DQN on 32 of 57 games (median +0.4%, mean +34%)", "Table 1", "median gradient-norm span about two orders smaller (Fig. 1b)", and "gamma 0.99". These came from an earlier html read of 1602.07714 v2. Since 1602.07714 is the normalization paper, not the PopArt paper, those numbers must be re-read from 1809.04474 full text (or its PDF) before any report cites them. Until then they are unverified and are omitted from the proposals.

### Inferences
- Cite 1602.07714 for adaptive target normalization as the origin of the idea, and 1809.04474 for the PopArt name and the multi-task application. Do not give 1602.07714 as the PopArt source.
- Both papers are value-based (DQN-family) work. Neither tests PPO. Any PPO claim is a Dodge adaptation.

### Gaps
- Full text of 1602.07714 and 1809.04474 was not read. The equation and algorithm claims ("Eq. 4", "Algorithm 1", "Prop. 1") are unverified this round.

## Gap 2: critic gradient isolation (stop-gradient) vs canonical separate networks / PPG

### Takeaway
The proposed stop-gradient (value-loss gradients blocked from the shared trunk) is not PPG and not the Andrychowicz "separate networks" setting. Canonical separate networks remove the shared trunk. PPG separates the policy and value phases and distills features between them. The stop-gradient is a cheaper, one-directional Dodge-specific ablation. It cannot separate interference from capacity loss by itself.

### Cited Findings
- PPG (Cobbe, Hilton, Klimov, Schulman; arXiv 2009.04416, submitted 9 Sep 2020). Abstract: PPG "separat[es] policy and value function training into distinct phases"; prior methods force a choice between shared and separate networks; "Using separate networks avoids interference between objectives," while "using a shared network allows useful features to be shared." PPG keeps both benefits through a phase that "distills features." The value function is optimized more aggressively with more sample reuse. The abstract says PPG "significantly improves sample efficiency" on Procgen. [arXiv abs 2009.04416](https://arxiv.org/abs/2009.04416). Read scope: abstract, via summarizer. The abstract does not use "auxiliary". The earlier claim that PPG's auxiliary value loss and joint loss "share no parameter dependencies" comes from the html read and is not re-verified this round.
- Andrychowicz et al. 2020 (arXiv 2006.05990), Sec. 3.2 (networks architecture): "Separate value and policy networks" "appear to lead to better performance on four out of five environments." [arXiv HTML v1](https://arxiv.org/html/2006.05990v1). Read scope: summarizer, first 100,000 characters only.
- Dodge frozen source: the shared-trunk design is confirmed only by the design notes, not by `ppo.py` alone. `ppo.py` gives total loss `policy_loss + vf_coef * value_loss - ent_coef * entropy` (vf_coef 0.5, ent_coef 0.01, max_grad_norm 0.5). Gradient clipping in this code is over the total gradient (one clip for all parameters), which is the mechanism by which value gradients can shrink the policy step. Confirm in the training loop before relying on it. [python/dodge_rl/ppo.py](../../python/dodge_rl/ppo.py), lines 57-72 and 496.

### Inferences
Direction of interference is the crux. Three conditional hypotheses, none proven for Dodge:

- H1 (value-to-trunk interference): critic gradients in the shared trunk hurt policy features. A stop-gradient should improve survival. Evidence in the source: PPG and Andrychowicz support separating value and policy learning, but not this specific one-directional block.
- H2 (lost value-shaped representation): the trunk no longer receives value information. The critic head reads features the policy shaped, so critic fit and EV should get worse, and survival may not improve. This predicts the opposite of H1 for EV.
- H3 (capacity confound): under a stop-gradient the critic can only use the trunk's frozen features. Lower EV can come from fewer effective critic parameters, not from interference. This would also change the effective trunk learning rate, since the total trunk gradient loses its value term.

Ranking (conditional on the stated hypothesis, not on the data): H1 is the only one that predicts the survival gain the project wants. H2 and H3 both predict EV change without survival change. Only a measurement that separates them (actor and critic gradient norms logged separately, plus target and residual variance, plus survival) can rank them after the run. A true separate network removes both coupling directions at once, so it cannot distinguish them.

### Gaps
- Dodge's late-window EV decline is not attributed to any of H1-H3 by the current data. The trunk gradient norm mixes actor and critic (earlier report); the head norm does not identify interference.
- No source tests a stop-gradient ablation on a transformer or entity-token trunk.

## Gap 3: value clipping on or off (current frozen code)

### Takeaway
Verified: the frozen code has no value clipping. Adding clipping is a test of a change, not a repair of the current critic. The strongest source found (Andrychowicz Sec. 3.4) says clipping hurts. Clipping is therefore low priority and should be treated as a negative control, not a candidate fix.

### Cited Findings
- Frozen source: `value_loss` is `0.5 * mean((new_value - GAE_return) ** 2)`, and the config contains `"value_clipping": False` (python/dodge_rl/ppo.py, lines 4-6 and 93-95). Clip coefficient 0.2 applies only to the policy ratio. [python/dodge_rl/ppo.py](../../python/dodge_rl/ppo.py).
- Andrychowicz et al. 2020, Sec. 3.4: value-function clipping "hurts the performance regardless of the clipping threshold" (figure reference Fig. 43). [arXiv HTML v1 2006.05990](https://arxiv.org/html/2006.05990v1). Read scope: summarizer; threshold range not stated in the returned text.
- Engstrom et al. 2020 (arXiv 2005.12729), Sec. 3, item 1: the standard PPO implementation "fits the value network with a PPO-like objective," clipping value estimates around the previous iteration's values. The ablation covers four optimizations including "value clipping," but the Figure 1 caption names reward normalization, Adam annealing, and network initialization as significant. Value clipping is not named as significant in that finding, and no separate harmful-or-helpful result for it was returned. [arXiv HTML v1 2005.12729](https://arxiv.org/html/2005.12729v1). Read scope: summarizer.
- Correction to earlier notes: Engstrom's finding is about reward normalization, not reward scaling. The earlier notes' wording "reward scaling ... necessary" should be corrected in any report.

### Inferences
- The two sources do not truly conflict: Engstrom did not report harm from value clipping, and Andrychowicz reported harm. Only the second is a direct statement. Dodge's current unclipped critic matches the setting Andrychowicz favored.
- Ranking: below critic-side options. It predicts harm or no change, so it is the least useful experiment for explaining the EV decline.

### Gaps
- No direct PPO-with-transformer value-clipping source. Andrychowicz threshold range not read.

## Gap 4: temporal credit and memory (GAE, gamma, horizon, memory)

### Takeaway
Verified arithmetic (below), using the config values in `ppo.py` and the K=4, 60 Hz setting from the request. The horizon is set by gamma times lambda in the advantage, not by gamma alone. No recurrent-PO benchmark was re-read this round, so memory evidence is still the earlier POPGym note (unverified this round).

### Cited Findings
- Frozen config (python/dodge_rl/ppo.py, lines 58-61): gamma 0.995, gae_lambda 0.95. K=4 is enforced (`action_repeat == 4`, line 276). One decision is 4 raw frames, which is 66.67 ms at 60 Hz. The rollout length of 256 decisions is the user's stated setting. `collect_rollout` takes `rollout_steps` as a parameter; the 256 value was not confirmed in code this round.
- GAE (Schulman et al. 2015, arXiv 1506.02438, v6). The abstract describes an "exponentially-weighted estimator of the advantage function that is analogous to TD(lambda)" and says value functions reduce variance "at the cost of some bias". The lambda formula is not in the abstract; use the paper body (standard form: advantage is the sum over k of (gamma*lambda)^k times TD errors) before quoting it. [arXiv abs 1506.02438](https://arxiv.org/abs/1506.02438). Read scope: abstract, via summarizer.
- Source-code check: `compute_gae` returns `returns = advantages + values` (ppo.py line 171), and the EV diagnostic uses frozen rollout values and GAE returns (lines 553 onward). Bootstrap uses `next_values`, so the rollout end is bootstrapped by the critic, not zero.

### Exact calculations (K=4, 60 Hz, one decision = 4/60 s = 0.0667 s)

Let d = decisions (steps). Frames = 4d. Seconds = 4d/60.

| Quantity | Formula | Value | Meaning |
| --- | --- | --- | --- |
| gamma per decision | 0.995 | 0.995 | Discount applied per decision |
| Discount horizon (1/(1-gamma)) | 1/(1-0.995) | 200 decisions = 800 frames = 13.3 s | Scale of the return's discount, not of the advantage |
| Discount half-life | ln 0.5 / ln 0.995 | 138.3 decisions = 553 frames = 9.2 s | Reward half as weighted after this long |
| gamma^256 | 0.995^256 | 0.277 | Share of value weight left at the end of a 256-decision rollout |
| GAE decay | gamma*lambda = 0.995*0.95 | 0.94525 | Per-decision weight on TD errors |
| GAE effective window (1/(1-gamma*lambda)) | 1/(1-0.94525) | 18.3 decisions = 73 frames = 1.22 s | Scale of the advantage weighting. This is a weighting, not a planning horizon |
| GAE half-life | ln 0.5 / ln 0.94525 | 12.3 decisions = 49 frames = 0.82 s | Half weight after this long |
| (gamma*lambda)^256 | 0.94525^256 | ~5.5e-7 | Advantage weight left at the end of the rollout (negligible) |
| Rollout length | 256 decisions | 1024 frames = 17.1 s | Span of one rollout |

Examples (lag k decisions before a death or reward):
- Death 1 s before (15 decisions, 60 frames): gamma weight 0.928; GAE weight (gamma*lambda)^15 = 0.430.
- Death 3 s before (45 decisions, 180 frames): gamma weight 0.798; GAE weight (gamma*lambda)^45 = 0.079.

Sensitivity of the GAE window: lambda 0.90 gives gamma*lambda = 0.8955, window 9.6 decisions (0.64 s). lambda 0.99 gives 0.98505, window 66.9 decisions (4.5 s, 268 frames). These are the single-variable options in the candidate list.

### Inferences
- Dodge's advantage weighting is short (about 1.2 s) compared with the 17 s rollout. A rare lethal event 3 s away gets about 8% of GAE weight directly. The critic must carry most of that information through its bootstrap. This ties the temporal question to the critic question (Gap 2), since lambda changes depend on critic quality.
- The gamma horizon (13 s) is long relative to the advantage window (1.2 s). If the rare-death signal matters on a longer scale, changing lambda is the variable that controls it. Changing gamma alone changes the value target scale and the effect of far-future reward.
- Memory: the 81-token state is a visible-state policy. An architectural memory ablation (for example a GRU or frame stack in the policy) is a different variable from changing the observation allowlist (adding velocity or prior-frame features to the existing input). The second changes the information content of the state. The first keeps the state fixed and adds a recurrent state. Both are separate experiments. Neither should be called "memory" without naming which.
- The teacher should not be called fully observable merely because it is trained with privileged labels. Labels used for supervision are not inputs. Confirm the teacher's observation schema before any claim about observability.

### Gaps
- No recurrent-PO benchmark was re-read this round. The POPGym numbers in the earlier note (GRU MMER 0.349) are unverified here.
- No source tests gamma or lambda in the Dodge-like setting (decision-level K=4 action repeat with an entity-token transformer).
- The 256-decision rollout length is taken from the request. Confirm the default in the training config before a final report.

## Gap 5: re-ranked one-variable candidates

Candidates are one-variable ablations from the frozen D2 setup. Labels: **published** = known method in the literature; **Dodge adaptation** = known idea applied to Dodge without a published PPO test; **speculative** = not supported by a source read here. Full details (cost, failure, criteria) are in `gap_experiments.json`.

| Rank | Candidate | Label | Literature basis (verified level) | Why this rank |
| --- | --- | --- | --- | --- |
| 1 | Critic stop-gradient into shared trunk | Dodge adaptation (of separate-critic idea) | PPG and Andrychowicz support separate value/policy learning, not this exact block (abstract/summary level) | Cheapest to implement, fits the 48-update local window (about 13.3 min per arm), and directly tests H1 vs H2/H3 |
| 2 | Running target-std normalization of critic targets (no weight rescaling) | Dodge adaptation of published method (PopArt origin in 1809.04474; normalization origin in 1602.07714) | Abstract-level only for both; PPO application untested | Cheap, and the discriminator (target variance, critic gradient norm) is already logged. Held below rank 1 because it is untested in PPO and the 0.067 target variance drift is small |
| 3 | GAE lambda change (0.90 or 0.99), gamma fixed | Published method family (GAE, lambda tuning) | GAE abstract: bias-variance tradeoff (summary level) | Tests the temporal weighting question with no architecture change. Speculative as a survival lever, since no source here ties lambda to rare lethal events |
| 4 | PPG-style infrequent auxiliary value phase | Published method (PPG), Dodge adaptation | PPG abstract: phased value optimization (summary level) | Needs more gradient steps per rollout. Likely exceeds the 30-min local cap, and it depends on rank 1 result |
| 5 | Plasticity intervention in the critic | Published methods, speculative for PPO | Earlier notes only (abstract-level, supervised or off-policy) | Needs 100+ updates; measurement-only first |

Deprioritized: value clipping on (Gap 3). Predicted harm by Andrychowicz Sec. 3.4, and not a fix for Dodge's current unclipped critic. Keep as a negative control only if budget remains.

Not ranked: memory/GRU wrapper (no Dodge-state reason to expect gain, since the observation is visible); exploration and curriculum for rare deaths (no source read).

### Measurement, budget, and failure notes (summary; see JSON for full fields)
- Matched baseline: the D2 update-48 reference (Q1 521.0625, Q4 2401.1875, mean 1101.9375 frames, one training seed, 64 dev seeds for selection). Keep the same dev-seed selection rule, and evaluate candidates on fresh seeds for any claim.
- Local cost: one 48-update arm is 796.987 s (about 13.3 min) on one launcher and one worker, from the reference doc. That fits the 30-min, 6 GiB local cap for one arm. A second training seed for both candidate and baseline (four arms, about 53 min) does not fit one 30-min window. That is a proposal for approval, not automatic capex.
- Keep/reject rule: survival (mean alive frames) is primary. Keep only if the gain exceeds seed spread across at least two training seeds and Q1 does not fall. Reject if the gain is within spread or Q1 falls. EV, target variance, and residual variance are diagnostics only. No EV threshold is used. Rewards are unchanged.

## Coverage and limits
- Reads: 6 WebFetch summary reads (4 arXiv abstracts, 2 arXiv HTML section reads) plus direct local source reads. No WebSearch this round.
- Fetch truncation: 2006.05990 was read for characters 0-100,000 of 218,241 only. Value-clipping threshold range (Sec. 3.4, Fig. 43) and the PPG and Andrychowicz numbers were not verified.
- Not verified this round: all numeric claims from the PopArt paper, PPG Procgen numbers, POPGym numbers, Lyle/Dohare/Nikishin claims (abstract or search-only in earlier notes).
- Summarizer quotes are not verbatim. Check before quoting in the final report.
