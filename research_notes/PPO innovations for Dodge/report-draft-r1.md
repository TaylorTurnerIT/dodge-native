# Test critic interference before architectural changes

**Bottom line:** Literature supports separating value and policy learning in on-policy agents, but no source read tests the one-way critic stop-gradient Dodge can run cheaply, and none covers PPO with an entity-token transformer. Dodge's late-window critic residual rose (**0.020 to 0.027**) while target variance barely moved (**0.067 to 0.063**). That fits trunk interference but does not establish it. Run first: log actor and critic trunk gradients separately (no training change). Then test a critic stop-gradient, a GAE lambda sweep, and running target normalization. PPG-style phasing waits on cost. Everything is unrun. Survival (mean alive frames) decides; EV is diagnostic only.

## Known methods separate critic learning, with narrow evidence

PPG separates policy and value phases. Its abstract argues that separate networks avoid interference while shared networks let features be shared, and its distillation phase tries to keep both ([Cobbe et al. 2020](https://arxiv.org/abs/2009.04416)). Andrychowicz et al. report separate policy and value networks as better in most of their environments, from a partial summary read of their Sec. 3.2 ([arXiv 2006.05990](https://arxiv.org/html/2006.05990v1)). Neither tests a one-way stop-gradient. Dodge's variant keeps the policy's gradient into the trunk and removes the critic's, so it can also strip value-shaped features the policy relies on. It is a Dodge-specific ablation, not a PPG method. Dodge also applies one global gradient clip (`max_grad_norm` 0.5, per the config; the training loop still needs checking). Removing critic gradients therefore changes the clip scale, so actor step size can shift. Isolation claims need that clipping logged.

For normalization, van Hasselt et al. 2016 proposed adaptive target normalization ([arXiv 1602.07714](https://arxiv.org/abs/1602.07714)), and Hessel et al. 2018 introduced PopArt for multi-task Atari-57 and DeepMind Lab ([arXiv 1809.04474](https://arxiv.org/abs/1809.04474)). Both are value-based. Running target statistics alone are not PopArt; PopArt also rescales the last layer to preserve outputs, and that optimizer interaction matters.

Dodge's critic is unclipped. Andrychowicz's summary reports clipping hurting at every threshold, and Engstrom et al. ([arXiv 2005.12729](https://arxiv.org/abs/2005.12729)) do not name it significant. It is a negative control at most.

## Dodge's diagnostics show residual growth, not proven interference

The same-batch diagnostic raised post-update EV and cut MSE on all 48 updates ([critic diagnostic](docs/v2-critic-diagnostic-2026-10-25.md)). Those fits are in-sample against self-bootstrapped targets, so they say nothing about held-out accuracy. From updates 9–16 to 41–48, pre-update EV fell from **0.694** to **0.562**. Target variance fell only slightly, so target contraction does not explain the drop. A growing trunk norm with a shrinking critic-head norm (earlier run) is consistent with an actor-dominated trunk, but the trunk norm mixes both gradient sources. Only split gradients can separate interference from capacity loss. Under a stop-gradient, lower EV could simply reflect fewer effective critic parameters.

Horizon arithmetic (K=4 at 60 Hz, 66.7 ms per decision; illustrative, not paper quotes): gamma 0.995 gives a 200-decision (13.3 s) geometric timescale, and GAE's gamma·lambda = 0.94525 gives about 18 decisions (1.22 s). These are weightings, not planning horizons or cutoffs. A death 3 s ahead gets about 8% of its GAE weight directly, so the critic's bootstrap carries most of that signal and lambda and critic quality are one question.

The 48-update cohort (update 48, 64 development seeds, argmax) is below. Earlier checkpoints are not matched controls: the 848 figure is a different training seed stream, and the 2240 best came from a longer run, selected from 24 evaluations.

| Cohort | Q1 alive frames | Q4 alive frames | Mean alive frames |
| --- | ---: | ---: | ---: |
| Current D2 diagnostic, update 48 (latest completed) | 521.0625 | 2401.1875 | 1101.9375 |
| Earlier run, update 48 (different seed stream) | 525.125 | 1481.5 | 848.328125 |
| Earlier run, update 320 (best, selected among 24) | 648.25 | 4508.8125 | 2240 |

## Ranked experiments, one variable each

| Rank | Experiment (unrun) | Literature basis | Keep if | Falsified if |
| --- | --- | --- | --- | --- |
| 1 | Log actor and critic trunk gradient norms and cosine per update; no training change | Dodge-specific; tests the interference premise | Late-window slopes are attributable per source | Actor trunk share does not grow and cosine stays near zero: rank 2 loses its motivation |
| 2 | Critic stop-gradient into trunk (value head on detached features) | PPG and Andrychowicz support separation, not this block | Survival gain beyond 2-seed spread, Q1 not lower | Gain within spread or Q1 falls; EV down with survival flat (capacity, not interference) |
| 3 | GAE lambda 0.90 or 0.99, gamma fixed | GAE bias–variance trade-off (abstract) | Same survival rule | Survival within spread in both directions |
| 4 | Running target normalization of GAE returns, no weight rescale | Van Hasselt 2016; Hessel 2018 (value-based) | Target-variance drift reduced and survival beyond spread | Target variance unchanged or survival within spread |
| Later | PPG-style auxiliary value phase | PPG (abstract) | Survival gain at matched wall-clock | Gain within spread or cost unjustified |

Plasticity methods ([Dohare et al. 2023](https://arxiv.org/abs/2306.13812); [Lyle et al. 2022](https://arxiv.org/abs/2204.09560)) rest on supervised or off-policy evidence and need 100+ updates, so they are not ranked. Memory is not ranked because Dodge's observation is visible-state. Exploration and curriculum for rare deaths had no source read.

Cost: one 48-update arm took 796.987 s locally. Two training seeds per arm (four arms, about 53 min) exceed the 30-minute window, which is a separate budget decision. Compare on fixed development episodes, qualify on fresh seeds, and log Q1, Q4, mean, and death causes.

## Source coverage and limits

Coverage is thin. Every web read was a WebFetch summary from a small model, not verbatim text. Abstract-only reads cover both PopArt papers, PPG, GAE, Ilyas et al., Lyle et al., and Dohare et al. Andrychowicz was read only for its first ~100,000 of ~218,000 characters. Nikishin et al. ([arXiv 2205.07802](https://arxiv.org/abs/2205.07802)) is a search snippet only. No PDFs were read, one search query was run, and this is not a systematic review. Unverifiable PopArt attributions and Atari figures from earlier notes are omitted. Checking Andrychowicz Sec. 3.2 and 3.4 and PPG Sec. 3 against PDFs would most change confidence.

## Conclusion

This is not a new algorithm. Logging can answer whether late critic decline comes from trunk interference before any architecture change. If split gradients show no actor-induced trunk pressure, drop the stop-gradient and move to lambda and target normalization. If they show pressure and the stop-gradient holds survival gains on fresh seeds, separate critic or PPG-style phasing earns its cost.
