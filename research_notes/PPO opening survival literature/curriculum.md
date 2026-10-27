# RL Curriculum, Horizon Practice, and Late-Game Retention

## Does literature predict opening gains with late-tail cost from short-horizon practice?

### Takeaway
Curriculum literature supports possible learning-speed benefits from easier tasks, but does not establish opening gains with late-game harm. For Dodge it remains a hypothesis: opening success rose pooled +1.92 points while mean Q4 fell 180.31; three paired mean deltas were mixed (only three training pairs).

### Cited Findings
- Narvekar et al. (2020), “Curriculum Learning for Reinforcement Learning Domains: A Framework and Survey,” frames curricula as sequencing tasks/data to improve learning on a harder target; methods differ in assumptions, capabilities, and goals. It is a survey, not a retention guarantee. [JMLR paper](https://jmlr.csail.mit.edu/papers/v21/20-212.html)
- Klink et al. (2020), “Self-Paced Deep Reinforcement Learning,” progressively learns task distributions toward a target distribution, with curriculum pace controlled by agent learning; authors report gains across several environments/algorithms. This supports adaptive sampling, not the Dodge outcome. [NeurIPS paper](https://papers.neurips.cc/paper_files/paper/2020/hash/68a9750337a418a86fe06c1991a1d64c-Abstract.html)
- Liu et al. (2023), “Measuring and Mitigating Interference in Reinforcement Learning,” define and measure interference for value-based Fitted Q-Iteration/DQN; measured interference correlated with control instability, and online-aware methods reduced it in classic control. Its application to PPO is indirect. [Lifelong Learning Agents paper](https://proceedings.mlr.press/v232/liu23a.html)

### Inferences
- Short practice horizons can provide more repeated opening decisions per episode and reduce time until an episode reset; that may preferentially train early decisions. But 70% is an episode-assignment fraction, not a 70% decision or gradient fraction: stage episodes have a 1,000-frame cap while full episodes can last much longer. Measure exposure by decisions/frames and game age.
- Late-game cost is plausible if later situations become under-sampled or if shared parameters change under the shifted state distribution. The evaluation does not establish cause; log stage/age-conditioned exposure and returns.
- This curriculum did not advance beyond 1,000 frames in any replica. Thus full-game progression was not tested. Its 90% mastery threshold over two 100-episode windows with ≥200 eligible episodes may be conservative/noisy; it is a gate policy, not evidence that the learner has or has not mastered later gameplay.

### Gaps
- No literature result found that directly predicts opening improvement plus late-tail loss from a 70/30 short-cap/full-game assignment in PPO for a survival game.
- No age-binned exposure counts supplied.

## Does 70% short-stage / 30% full-game assignment preserve enough late-game exposure? What alternatives?

### Takeaway
Episode assignment cannot establish late-game exposure. Preserve full episodes and measure decision age; isolate assignment/weighting under matched budget and fixed endpoint evaluation.

### Cited Findings
- Pardo et al. (2018), “Time Limits in Reinforcement Learning,” distinguish environment termination from external time limits. For artificial truncation of continuing tasks, bootstrap from the end-state value; treating it as terminal biases learning. For finite-horizon tasks where the horizon is part of the task, time must be represented in state. [ICML/PMLR paper](https://proceedings.mlr.press/v80/pardo18a.html)
- Florensa et al. (2017), “Reverse Curriculum Generation for Reinforcement Learning,” grows training starts outward from goal states using states with intermediate success probability, targeting a frontier that is neither trivial nor unsolvable. Frontier sampling analogy; goal-reaching differs from Dodge. [CoRL/PMLR paper](https://proceedings.mlr.press/v78/florensa17a.html)
- Dennis et al. (2020), “Emergent Complexity and Zero-shot Transfer via Unsupervised Environment Design,” use protagonist/antagonist regret to generate increasingly complex but feasible environments; report stronger zero-shot transfer on novel tasks. This supports adaptive challenge, not a fixed ratio. [NeurIPS paper](https://research.google/pubs/emergent-complexity-and-zero-shot-transfer-via-unsupervised-environment-design/)
- Jiang et al. (2021), “Replay-Guided Adversarial Environment Design,” cast Prioritized Level Replay as curriculum design and report benefits on OOD zero-shot transfer tasks. Replay suggests prioritizing rare openings while retaining diversity, though it concerns levels, not episode windows. [NeurIPS paper](https://papers.neurips.cc/paper_files/paper/2021/hash/0e915db6326b6fb6a3c56546980a8c93-Abstract.html)

### Inferences
- **Option A, cleanest exposure control:** sample complete normal-start game episodes throughout; oversample a fixed set/distribution of opening seed or initial-state strata, while every sampled trajectory continues to death/18,000 cap. Small isolated comparison: baseline versus a predeclared opening-seed mixture; report opening success, age-conditioned survival/return, Q1/Q4, and action/decision counts by age. Risk: narrow coverage; retain uniform sampling.
- **Option B, horizon-weighted objective:** keep full episodes but add predeclared return/loss weighting by decision age (or age-stratified minibatch quotas) so opening signal is increased without truncating trajectory context. Test one weighting level against baseline. Report same metrics. Risk: changes objective/gradient scale.
- **Option C, mastery-gated adaptive mixture:** retain full-game episodes at a guaranteed floor; increase stage/horizon sampling only while held-out stage mastery is below threshold; advance only after repeated independent windows and never infer full-game mastery from capped episodes. Test one adaptive mixture against fixed 70/30. Risk: noisy mastery; preregister windows and report learning curves.

### Gaps
- Paper results do not identify a universally sufficient exposure share or mastery threshold for this game/PPO setup.
- Endpoint eval uses full starts/no cutoffs, but cannot reveal training exposure without age-binned logs.

## Artificial cutoff versus death; bootstrap interpretation

### Takeaway
Normal death is terminal; an imposed practice horizon truncates the continuing game and should bootstrap from its final state. Correct bootstrap avoids a false terminal target, but does not supply later-game action practice.

### Cited Findings
- Pardo et al. (2018) formalize partial-episode bootstrapping and report empirical improvement/stability for two existing algorithms when external time limits are handled this way. Their argument specifically concerns non-environmental termination causes. [ICML/PMLR paper](https://proceedings.mlr.press/v80/pardo18a.html)
- Dodge design says artificial curriculum cutoff bootstraps and uses reachable histories; normal enemy death remains common. This matches the distinction; it does not validate implementation or imply a bug.

### Inferences
- Do not attribute the observed Q4 change to incorrect terminal handling absent implementation evidence. Test cutoff-vs-natural death semantics separately with a tiny value-target audit or source inspection before any future training; no runtime/training action is proposed here.
- A cutoff bootstrap estimates continuation value at the horizon, but policy-gradient state/action samples after that horizon remain absent. Thus accurate bootstrap and adequate late-game practice are separate questions.

### Gaps
- Literature does not validate Dodge native GAE/collector boundary handling.
