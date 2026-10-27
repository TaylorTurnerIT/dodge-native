# Test critic interference before architectural changes

Revision r2: editorial and source-evidence correction of the prior draft ([report-draft-r1.md](../research_notes/PPO%20innovations%20for%20Dodge/report-draft-r1.md)). No new research, experiments, or source, model, state, or training edits.

Literature supports separating value and policy learning in some on-policy settings, but the sources read do not test the one-way critic stop-gradient Dodge can run, and none covers PPO with an entity-token transformer. Dodge's late-window critic residual rose (**0.020 to 0.027**) while target variance barely moved (**0.067 to 0.063**). That fits trunk interference but does not establish it. Everything is unrun. Survival (mean alive frames) is the goal; explained variance (EV) is diagnostic only.

## Known methods: narrow evidence

PPG separates policy and value phases; its abstract argues separate networks avoid interference while shared networks let features be shared ([Cobbe et al. 2020](https://arxiv.org/abs/2009.04416)). Andrychowicz et al. report separate networks as better in most environments, from a partial read ([arXiv 2006.05990](https://arxiv.org/html/2006.05990v1)). Neither tests a one-way stop-gradient. Dodge's variant keeps the policy's gradient into the trunk and removes the critic's, so it can strip value-shaped features the policy uses. It is a Dodge-specific ablation, not a PPG method.

Dodge uses one global gradient clip (`max_grad_norm` 0.5 per config; the training loop still needs checking). Removing critic gradients changes the clip scale, so log clipping in any isolation claim. Clipping evidence is thin ([arXiv 2005.12729](https://arxiv.org/abs/2005.12729) does not name it significant).

Van Hasselt et al. 2016, "Learning values across many orders of magnitude" ([arXiv 1602.07714](https://arxiv.org/abs/1602.07714)), and Hessel et al. 2018, "Multi-task Deep Reinforcement Learning with PopArt" ([arXiv 1809.04474](https://arxiv.org/abs/1809.04474)), belong to the adaptive value-target normalization family. Abstract-level reads do not establish how they relate or which element each introduced. Running target statistics alone are not PopArt, which also rescales the last layer to preserve outputs. No novelty or originality is claimed for either.

## Dodge diagnostics: residual growth, not proven interference

The same-batch diagnostic raised post-update EV on all 48 updates ([critic diagnostic](../docs/v2-critic-diagnostic-2026-10-25.md)), but those fits are in-sample against self-bootstrapped targets. From updates 9–16 to 41–48, pre-update EV fell from **0.694** to **0.562**. Target variance fell only slightly, so target contraction does not explain the drop.

Gradient norms and cosine are a conditional diagnostic. They show whether actor and critic trunk gradients align or conflict, and whether the trunk is actor-dominated. They cannot alone separate interference from capacity loss; a causal case needs a controlled ablation and behavioral outcomes. A stop-gradient also changes critic feature learning and global clipping, so it is not a clean isolation test.

Timescales (K=4 at 60 Hz, 66.7 ms per decision; illustrative): gamma 0.995 gives a 200-decision (13.3 s) timescale; GAE's gamma·lambda = 0.94525 gives about 18 decisions (1.22 s). These are weighting timescales, not planning horizons. A death 45 decisions (3 s) ahead gets geometric GAE weight (γλ)^45 ≈ 8% on its TD residual, before terminal masks. That is not a fraction of all training returns, and the report does not quantify how much the critic bootstrap carries the rest.

| Cohort (64 dev seeds, argmax) | Q1 alive frames | Q4 alive frames | Mean alive frames |
| --- | ---: | ---: | ---: |
| Current D2 diagnostic, update 48 (latest completed) | 521.0625 | 2401.1875 | 1101.9375 |
| Earlier run, update 48 (different seed stream) | 525.125 | 1481.5 | 848.328125 |
| Earlier run, update 320 (best, selected among 24) | 648.25 | 4508.8125 | 2240 |

Earlier cohorts are not matched controls.

## Ranked experiments (all unrun)

| Rank | Experiment | Basis | Keep if | Falsified if |
| --- | --- | --- | --- | --- |
| 1 | Log actor and critic trunk gradient norms and cosine per update. Measurement meant to preserve the optimizer trajectory; validate RNG, mode, gradient, and parity, since added autograd can perturb training | Dodge-specific | Late-window trunk pressure attributable to each source | Actor trunk share flat, cosine near zero; weakens rank 2, does not rule out capacity loss |
| 2 | Critic stop-gradient into trunk | Separate-network evidence (PPG, Andrychowicz); no direct test | Survival gain beyond 2-seed spread, Q1 not lower | Gain within spread, or Q1 falls. EV down with flat survival fits capacity loss, not proof |
| 3 | GAE lambda 0.90 or 0.99, gamma fixed | GAE bias–variance trade-off | Same survival rule | Survival within spread both ways |
| 4 | Running target std normalization of GAE returns, raw value units kept | Adaptive target normalization family | Target-variance drift reduced and survival beyond spread | Survival within spread. Changes objective scale and critic coefficient; not a proven cheap gain |
| Later | PPG-style auxiliary value phase | PPG | Survival gain at matched wall-clock | Gain within spread, or cost unjustified |

Lower target variance is an optimization diagnostic, not a survival guarantee.

Recurrent memory is a plausible architectural alternative, not ruled out. Visible features do not establish full observability: hidden RNG, scheduling, and anti-camp state are excluded, and past context may matter. Testing it needs an aliased-state or history diagnostic; source coverage is insufficient to rank it. Plasticity methods ([Dohare et al. 2023](https://arxiv.org/abs/2306.13812); [Lyle et al. 2022](https://arxiv.org/abs/2204.09560)) rest on supervised or off-policy evidence, so they are not ranked.

Cost: one 48-update arm took 796.987 s locally. Four arms × 796.987 s ≈ 53 min matches one seed per arm, not two; two seeds per arm would be about 106 min. Treat 53 min as an aggregate across separately bounded runs, not permission to exceed the 30-minute cap on any run.

## Source coverage and limits

Coverage is thin. Web reads were WebFetch summaries from a small model, not verbatim text. Abstract-only reads cover both normalization papers, PPG, GAE, and the plasticity papers, which does not establish algorithm lineage. Andrychowicz was read only for its first ~100,000 of ~218,000 characters. Nikishin et al. ([arXiv 2205.07802](https://arxiv.org/abs/2205.07802)) is a search snippet only. No PDFs were read, one search query was run, and this is not a systematic review. Unverifiable PopArt attributions and Atari figures from earlier notes are omitted.
