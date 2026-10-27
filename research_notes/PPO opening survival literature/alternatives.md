# Alternatives for early survival without later-survival loss

## Which next training intervention has strongest fit?

### Takeaway

First test policy-current, training-only seed prioritization with uniform exploration floor and full normal-start episodes. This targets the mixed evidence that opening1000 rose only +1.92 percentage points on average, with replica changes +6.54, +0.78, and -1.56 points, while full-run later survival fell in Q4 by 180.31 frames on average. It preserves rewards and tests whether training seeds drive early failures.

### Cited Findings

- Prioritized Level Replay (PLR, ICML 2021) samples procedurally generated training levels by estimated current-policy learning potential; authors report improved sample efficiency and test generalization on Procgen. It does not establish Dodge gains or authorize evaluation-seed reuse. [Jiang et al., “Prioritized Level Replay”](https://proceedings.mlr.press/v139/jiang21b.html)
- ACCEL (ICML 2022) edits levels toward the frontier of agent capability and reports empirical gains across its tested environments; authors note environment design methods can struggle to find effective levels, while evolutionary approaches can be resource-heavy. Fixed gameplay patterns and no level editor make ACCEL costly here. [Parker-Holder et al., “Evolving Curricula with Regret-Based Environment Design”](https://proceedings.mlr.press/v162/parker-holder22a.html)
- PLR's evidence concerns selecting training levels, not replaying old on-policy transitions. PPO ratios compare current and old policy probabilities; stale trajectories need off-policy correction. [Schulman et al., “Proximal Policy Optimization Algorithms”](https://arxiv.org/abs/1707.06347)

### Inferences

- Minimal experiment: hold reward, checkpoint, LR, budget, and full RNG seed vectors constant. Reserve a fixed assignment fraction for uniform sampling; prioritize other training-only normal-start seeds by smoothed current-policy TD error, refresh with fresh rollouts, and cap per-seed share. Keep 3 replicas and 983040 decisions/arm. Never mine evaluation cohorts.
- Discriminating diagnostic: before training, correlate seed-level opening1000 survival, full-episode frames, score, and death cause under current policy. Recheck those plus fresh reserved-cohort mean, Q1, Q4, and opening survival after training. Training-seed gains without reserved-cohort gains indicate overfit.
- Predicted: if a stable subset of training seeds contains learnable early threats, opening survival and Q1 should improve; uniform floor and full-episode exposure may protect Q4. No numeric forecast is supported. Unstable seed rankings may add variance.
- Cost/risk: moderate instrumentation and scheduler work; low environment change. Scoring may chase noise, starve coverage, or overfit finite seeds. Seal fresh cohort; report paired deltas.
- Do not start with ACCEL: first establish that selecting among fixed training seeds helps. Avoid replacing PPO rollout data with archived transitions.

### Gaps

No reviewed primary source demonstrates PLR on this Dodge environment, its eight-action/4-frame dynamics, or this run budget. Death cause counts are competing risks, not exposure-normalized hazards; seed-level association is needed before claiming a causal threat.

## Should objective or risk criterion change?

### Takeaway

Keep the existing score-plus-survival training reward for the first experiment. Separately test the already-defined survival-only gate as a controlled reward ablation only if decision-makers explicitly choose survival as the objective. CVaR or worst-case optimization can lift the tail while reducing mean or best-case performance, so it is a later, explicitly tradeoff-bearing experiment.

### Cited Findings

- Reward-misspecification experiments found stronger optimization often increased proxy reward while lowering true reward, including phase transitions; the authors include a game where survival-only proxy and game score differ. [Pan et al., “The Effects of Reward Misspecification”](https://arxiv.org/abs/2201.03544)
- Formal reward-gaming analysis shows omitting reward terms is generally not guaranteed to preserve alignment for stochastic policies. [Skalse et al., “Defining and Characterizing Reward Gaming”](https://proceedings.neurips.cc/paper_files/paper/2022/hash/3d719fee332caa23d5038b8a90e81796-Abstract-Conference.html)
- CVaR-PPO work explicitly constrains CVaR to a threshold; predictive CVaR policy gradients reweight terms toward a CVaR objective. These papers support risk-sensitive methods as objective-specific tools, not free improvements to both mean and tail. [Yang et al., “Towards Safe RL via Constraining CVaR”](https://ijcai.org/proceedings/2022/510); [Kim & Min, “Risk-Sensitive Policy Optimization via Predictive CVaR Policy Gradient”](https://proceedings.mlr.press/v235/kim24x.html)

### Inferences

- First diagnostic: paired per-seed association between score, alive frames, opening survival, Q1/Q4, and death cause. If training reward rises while survival gate and later tail fall, inspect the score/survival tradeoff before changing optimization.
- If survival-only is selected for a single ablation, train matched replicas from same checkpoint with same seeds, budget, LR, and sampler; change only score reward term. Predict longer survival if score-seeking competes with evasion, but score may fall and behavior may change sharply. Gate-only scoring must not be reported as evidence that training reward was survival-only.
- Do not choose CVaR casually. A later fixed lower-tail objective experiment must specify alpha, estimate uncertainty, and retain mean/Q4 as guardrails. It tests willingness to trade average/best outcomes for tail stability.

### Gaps

Current evaluation does not show whether score pursuit causes early death. No evidence justifies arbitrary later starts, frozen-opening behavior, or modifying reward weights without this diagnosis.

## Which tempting alternatives lack support?

### Takeaway

Use targeted evidence before changing architecture or policy memory. Current diagnostics do not support critic replacement, larger networks, or weak-policy BC.

### Cited Findings

- PLR ranks levels by estimated learning potential for the current policy; it does not imply copying behavior from low-return trajectories. [Jiang et al., “Prioritized Level Replay”](https://proceedings.mlr.press/v139/jiang21b.html)
- PPO's clipped objective is defined around old-policy samples and probability ratios; it does not validate blind replay of stale on-policy trajectories. [Schulman et al., “Proximal Policy Optimization Algorithms”](https://arxiv.org/abs/1707.06347)

### Inferences

- Before memory/plasticity work, log observation sufficiency around failures: visible threat, action distribution, entropy, value prediction, and death cause over the opening. Critic norm (~2% actor norm) and actor cosine (~0.02) make interference lower priority, not ruled out.
- Do not infer that more capacity helps: reward-misspecification work shows capacity can worsen proxy/true-objective gaps. Do not train BC on the same bad policy's openings without a better demonstrated target; it can preserve the failure.
- Three ranked alternatives: (1) capped PLR-style fresh-rollout seed prioritization, reward unchanged; (2) diagnose objective conflict, then isolated survival-only training-reward ablation if justified; (3) only after explicit mean-tail tradeoff approval, a constrained lower-tail objective. Each uses matched full-run budget and a sealed future evaluation cohort.

### Gaps

No evidence ties partial observability, recurrent failure, or actor-critic interference to D1/D2 collapse. Instrument before memory or capacity changes.
