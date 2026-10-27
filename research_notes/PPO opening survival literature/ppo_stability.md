# PPO stability and credit assignment

## Which PPO optimization effects fit Dodge results?

### Takeaway

Literature supports treating LR, rollout size, epochs/minibatch reuse, and KL stopping as consequential, interacting choices; it does not identify the cause of Dodge’s endpoint dips. Existing LR runs changed training seed/duration or reused a dev cohort, so their gains and regressions cannot isolate schedule effects.

### Cited Findings
- Andrychowicz et al. trained over 250,000 agents across five continuous-control tasks; choices interacted, LR had strong effects, rollout transitions per update affected performance, and linear LR decay helped four of five tasks but usually slightly. Their task, algorithm, and sample scale differ from this 9-action transformer game. [What Matters in On-Policy Reinforcement Learning? (2020)](https://arxiv.org/html/2006.05990)
- Same study found repeated passes important, batch-size increases did not hurt sample complexity in tested ranges, stale advantages could hurt, and recomputing advantages each pass helped. These findings motivate logging actual update size and KL/clip fraction, not blind epoch changes. [Andrychowicz et al. (2020)](https://arxiv.org/html/2006.05990)
- Engstrom et al. found PPO implementation choices produced larger effects than PPO-versus-TRPO core choice in tested MuJoCo tasks; they used at least 80 agents per estimate. It establishes implementation sensitivity, not a transferable recipe for Dodge. [Implementation Matters in Deep Policy Gradients (2020)](https://arxiv.org/abs/2005.12729)
- PPO clipping and target-KL early stopping constrain policy updates, but clipping is not a hard trust-region guarantee; target-KL is a practical early-stop rule. Dodge already uses clip .2 and targetKL .03, so first diagnostic is observed per-update KL, clip fraction, stopped epochs, and actor/critic losses. [PPO Algorithms (2017)](https://arxiv.org/abs/1707.06347)

### Inferences
- Highest-value offline analysis: correlate checkpoint-by-checkpoint evaluation changes with realized KL, clip fraction, value loss, explained variance, and optimizer step norm, keeping terminal endpoint separate from interim checkpoints. This can reveal association, not causal blame.
- If training later resumes, one isolated matched-seed LR schedule comparison is better motivated than an epoch/minibatch sweep: hold decisions, RNG policy, parent, eval protocol, and optimizer-state policy fixed; compare constant 3e-5 against predeclared linear decay. Only run under renewed authorization.

### Gaps
- No cited ablation matches shared-trunk entity-transformer PPO, discrete categorical actions, 60 updates, 983,040 decisions, gamma .995, and Dodge’s long survival objective.
- Dodge’s rollout is 64×256=16,384 decisions/update, with minibatch 512 and four epochs: 128 minibatch optimizer steps/update. Need actual KL/clip/early-stop logs before concluding updates were too large or too small.

## Does GAE horizon explain endpoint or opening effects?

### Takeaway

GAE explicitly trades variance for bias; gamma is task-dependent, and lambda shifts the credit horizon. Literature supports measuring sensitivity, not changing gamma/lambda from cross-domain defaults. At four game frames per decision, gamma .995 has a long nominal discounted horizon; lambda .95 discounts the GAE trace faster.

### Cited Findings
- GAE paper derives an exponentially weighted advantage estimator analogous to TD(lambda), trading lower variance against some bias. [High-Dimensional Continuous Control Using GAE (2015)](https://arxiv.org/abs/1506.02438)
- In five continuous-control tasks, Andrychowicz et al. found GAE/V-trace better than N-step, lambda .9 generally worked, and gamma strongly affected performance and should be tuned by environment. A non-significant difference between GAE and V-trace there does not establish equivalence in Dodge. [Andrychowicz et al. (2020)](https://arxiv.org/html/2006.05990)

### Inferences
- Best offline diagnostic: use saved trajectory/reward logs to report empirical reward-to-death/episode lengths and advantage autocorrelation by stage, plus bootstrap-target contributions at artificial cutoffs. This clarifies what credit horizon the current setting represents; it cannot establish that alternative gamma/lambda improves policy.
- Do not infer curriculum failure from absence of 1,000-frame mastery alone: all three curriculum arms missed mastery, while current result includes a modest +1.92 percentage-point opening success estimate and mixed per-policy effects.

### Gaps
- No Dodge-specific causal gamma/lambda comparison exists. Curriculum cutoffs were correctly bootstrapped, but their interaction with GAE targets still merits source-level/log audit if new training is later authorized.

## What do optimizer reset, endpoint regression, and evaluation uncertainty mean?

### Takeaway

Adam-state reset versus restore is a legitimate isolated question, but available reset evidence centers value-learning / high-update settings, not PPO continuation here. Evaluation-seed uncertainty and across-trained-policy variation are distinct: current intervals quantify conditional evaluation uncertainty for three trained pairs, not uncertainty over training seeds or methods.

### Cited Findings
- Resetting the Optimizer study examines Adam internal-state reset for iterative deep RL value-function approximation, where changing objectives can make optimizer history problematic. It does not establish reset as superior for PPO or this checkpoint continuation. [Resetting the Optimizer in Deep RL (NeurIPS 2023)](https://papers.neurips.cc/paper_files/paper/2023/hash/e4bf5c3245fd92a4554a16af9803b757-Abstract-Conference.html)
- rliable argues few-run point estimates are statistically uncertain and recommends interval estimates and robust summaries; it cautions against binary significance interpretations. Its multi-task IQM is not directly the right statistic for one Dodge game. [Deep RL at the Edge of the Statistical Precipice (NeurIPS 2021)](https://arxiv.org/abs/2108.13264)

### Inferences
- The paired fresh-seed intervals answer: for these fixed policies, how uncertain are means over evaluation seeds? They do not capture run-to-run training variability. Three matched training seed vectors allow a descriptive paired effect, not a strong population claim.
- Repeated 64-seed development selection risks cohort overfit; it can exaggerate apparent best-checkpoint gains. Fresh 1,024-seed results are not a regression against historical 64-seed means because cohort differs. Likewise, one shared 1,024-seed cohort is not three independent confirmation cohorts.
- Most useful future isolated proposal: if continuation is authorized, pair restored-Adam versus reset-Adam from the same accepted parent, same model weights, LR, data/RNG protocol, and fixed decision budget. Evaluate both on a truly untouched cohort. This tests the specific optimizer-state confound without claiming reset is literature-backed best practice.

### Gaps
- Need training-seed resampling or more independent matched training vectors to estimate method-level variation. Need a fresh held-out cohort for confirmatory selection claims. Non-significance cannot prove no effect.
