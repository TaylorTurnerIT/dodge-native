# Dodge Native: research and iteration plan

Archived snapshot from commit `3d43988`, migrated to the [local SQLite research notebook](../learning/research/README.md).
Use `learning/scripts/research_log.py` for current plans and results; the text below preserves the original discussion record.

Agreed format, 2026-10-28. Each experiment records four things: what we do, what we predict before running it, what we measure, and which explanations the measurements support or weaken. The explanation must lead to the next test. Discussion stays in chat; this file holds the durable plan and result links.

The goal is to improve the weakest games, with Q1 defined as mean survival in the worst 25% of games. Also report Worst, Mean, Q4, Best, score, and milestone success. Keep game frames, policy decisions, PPO updates, optimizer steps, and wall time separate.

## 1. Finish the current 600-update continuation

**What we're doing:** Continue Uniform #2 for 600 PPO updates, evaluating the starting model and every 60-update saved model on the registered full-game D6 cohort. Keep architecture, reward, uniform training pool, and learning rate unchanged. This is the existing running experiment; its registration governs execution.

**What we expect to happen:** If insufficient training is a major bottleneck, Q1 should rise above the starting model and improvements should persist across several checkpoints. Competing predictions are a plateau, temporary gains followed by regression, or gains in mean survival without gains in Q1. We are testing whether additional training is useful, not assuming that it must be.

**What actually happened:** In progress. The 2026-10-28 18:35:04 UTC check counted 191 of 600 completed updates. That is progress evidence, not a final performance result. Record the eleven evaluated models and the audited selection here after completion. No interim performance conclusion is recorded in this plan.

**Why might it have happened?** Sustained Q1 gains would support continuing this recipe. A plateau would motivate investigating control, representation, or objective limitations. Later regression would motivate tests of interference or optimization behavior. A single trajectory cannot distinguish those causes by itself. Compare against this run's D6 starting-model evaluation, rather than treating its earlier D4 score as the baseline.

## 2. Separate action sampling from control frequency

**What we're doing:** Freeze Uniform #2 and compare four conditions on the same newly reserved development game seeds: four-frame sampled actions, four-frame argmax, one-frame sampled actions, and one-frame argmax. Proposed screening budget: 256 game seeds, three fixed controller-randomness repetitions per sampled condition, and one evaluation per argmax condition: 2,048 complete games. Record actual frame counts and use the same 18,000-frame cap. No weights or reward change. Reserve seeds and calibrate resources before execution.

**What we expect to happen:** Our leading prediction is an interaction: faster control may help argmax more than sampling because it offers both quicker reactions and more chances to sample a harmful action. If argmax helps at both repeat settings, action selection is a stronger lead. If both one-frame conditions help, four-frame control timing is a stronger lead. If only one-frame argmax helps, the interaction becomes the next target. If none improves, investigate the policy's decisions and information rather than treating this as proof that one-frame training cannot help.

**What actually happened:** Not run. Fill in all four conditions, Q1 differences, milestone rates, and consistency across controller repetitions. Keep the repetitions grouped by game seed; do not present them as additional independent game seeds or training replicas.

**Why might it have happened?** Distinguish latency, action-selection randomness, and closed-loop distribution changes. An argmax gain would show that changing the selector changes performance; it would not identify the entropy coefficient as the cause. A one-frame gain with frozen weights would show useful control is available without retraining. Repeat the promising comparison on a separate cohort before choosing a lasting change.

## 3. Separate difficult seeds from variable outcomes, and trace failures

**What we're doing:** Select 10 weak seeds by a recorded rule from the preceding screen and 10 randomly chosen control seeds. Run each 32 times with the frozen policy and distinct registered controller randomness: 640 complete games. These selected cases are diagnostic, not a new estimate of population performance. Record action probabilities, chosen actions, player motion, score and pickups, visible hazards, center dwell time, and first fatal contact. Measure center dwell from observed position history; any native timer used to validate telemetry stays diagnostic-only.

**What we expect to happen:** Some seeds may produce both short failures and long successes, pointing toward action-dependent variability. Others may repeatedly produce the same failure, pointing toward a reproducible policy weakness. The sampling hypothesis predicts harmful choices where substantial probability already belongs to better actions. The risky-scoring hypothesis predicts failures clustered around particular score or pickup events. The memory hypothesis predicts outcome differences associated with recent center occupancy even in similar current observations.

**What actually happened:** Not run. Record within-seed and between-seed variation, representative traces, action confidence before failures, and event timing. Compare score and hazards at matched game ages while episodes are alive; do not compare a short episode's death score directly with a much older survivor's score.

**Why might it have happened?** Repeated failure by one fixed policy does not make a seed unavoidable. Mixed outcomes can reflect divergent strategies as well as one-action slips. Score-event and center-dwell associations nominate mechanisms; they do not establish them. Use those associations to choose states for the counterfactual test below.

## 4. Test action quality with counterfactual branches

**What we're doing:** Reconstruct up to 12 reachable pre-failure states from the recorded cases. Restore the full simulator state, RNG, and required observation-wrapper history. From each state, test all nine initial movement actions, followed by the frozen policy, with eight continuation-randomness repetitions and a 512-raw-frame horizon. This is up to 864 short branches. Validate restoration before interpreting comparisons; arbitrary frame-counter jumps are invalid.

**What we expect to happen:** If a harmful sampled choice is the immediate problem, some alternative actions should survive while the selected action fails. If useful actions have little policy probability, learning or representation becomes a stronger lead. If every tested action fails, move the branch point earlier to investigate how the policy entered trouble. The finite set of branches does not establish an optimal action or an unavoidable death.

**What actually happened:** Not run. Record short-horizon survival, score and reward, estimated action rankings, and policy probability assigned to useful alternatives. Include a replay of the recorded action as a restoration/control check.

**Why might it have happened?** These comparisons can distinguish local action-selection problems from earlier planning failures. They also suggest a route to better advantage estimates or training examples. The best simulated branch is a diagnostic reference using extra computation, not a deployable policy. Check full-game behavior before claiming an intervention improves survival.

## 5. Run the queued one-frame training comparison

**What we're doing:** After the current campaign and initial diagnostics, prepare a matched training comparison of one-frame and four-frame decisions from one common accepted starting model. Match actual gameplay-frame budgets and report policy-decision and optimizer-work budgets separately. Keep architecture and reward fixed. Preserving the current temporal discount and GAE decay suggests gamma1 = 0.995^(1/4), approximately 0.99874765, and lambda1 = 0.95^(1/4), approximately 0.98725854. Preserve rollout duration in game time where practical; 256 decisions span up to 1,024 frames at repeat four but only 256 at repeat one. State the optimization and entropy-scaling choices before launch.

**What we expect to happen:** Finer control should help if important reactions fall between four-frame decision boundaries. Frequent sampling could offset that benefit. A policy trained for one-frame control may improve even if the frozen-policy diagnostic did not. Equal frame budgets will not automatically give equal decision counts, optimizer work, or wall time.

**What actually happened:** Not run. Record learning curves, action-change rates, Q1 and full-game outcomes, and improvement per unit of compute. Use matched training randomness across arms and multiple training pairs when advancing beyond screening.

**Why might it have happened?** Attribute results to the registered bundle of temporal and optimization choices, then isolate any promising interaction. A change in action repeat also changes the number of entropy-regularized choices per game second. Do not credit every difference to reaction speed.

## 6. Test memory if the traces support an information gap

**What we're doing:** First compare predictive information in current observations against observations plus position-derived center-dwell history. If the signal is useful, test one history-based policy intervention against a constant or shuffled-history control with matched capacity and initialization. Consider a recurrent policy only after this cheaper test. This is an explicit observation-contract change; do not silently feed private engine counters to the policy.

**What we expect to happen:** Relevant history should distinguish similar-looking situations with different near-future risks. A genuine behavioral benefit should improve the affected failures and Q1, rather than merely improve a predictor's offline fit.

**What actually happened:** Not run. Record history's predictive contribution and, separately, changes in closed-loop survival under the controlled intervention.

**Why might it have happened?** Improvement with real history but not the control supports a history limitation. No benefit would reduce its priority as the opening bottleneck. Improvements from both real and control inputs would suggest capacity, optimization, or another shared change. A future visual student would also need access to the required history.

## 7. Test interference and learning-progress curricula

**What we're doing:** On isolated learner copies, measure how a small opening-focused update changes both early- and late-game behavior; compare against a matched control update. Use gradient comparisons as supporting diagnostics. If interference or unproductive failure-focused practice is supported, compare uniform sampling with one capped learning-progress priority rule that retains a uniform floor. Change sampling only, keeping reward and architecture fixed.

**What we expect to happen:** Interference predicts opening-focused updates that improve early decisions while damaging later ones. Learning-progress prioritization should spend more effort on situations the learner is improving on, rather than repeatedly selecting failures with little progress. The historical hard-seed labels need not identify today's best learning opportunities.

**What actually happened:** New tests not run. Existing evidence: the static 75%-expected-hard-start recipe had lower Q1 than its matched uniform control in all three completed pairs. That result motivates testing a different selection rule; it does not establish interference or rule out curricula.

**Why might it have happened?** Immediate behavioral tradeoffs would support investigating shared-policy interference. If they are absent, curriculum effects could instead involve exposure, outdated labels, or optimization. Learning-progress priority must use training evidence, not final evaluation seeds. Validate any promising rule across matched training pairs.

## 8. Test objective alignment if mean gains leave the weak tail behind

**What we're doing:** If the preceding results support an objective mismatch, compare ordinary expected-reward PPO with one explicitly defined lower-tail survival objective or survival constraint. Keep this separate from changes to memory, sampling, or action repeat. Define the score/survival tradeoff and any constraint target before training; no target is assumed here.

**What we expect to happen:** An objective that directly values reliable survival may improve Q1 even when additional ordinary training does not. It may trade away score or high-end performance. Selecting checkpoints by Q1 alone does not make the training objective optimize Q1.

**What actually happened:** Not run. Record the complete tradeoff across Q1, score, Mean, Q4, Best, and milestones, together with training cost.

**Why might it have happened?** A reproducible tradeoff would help specify the behavior we actually want. Failure would direct attention back to information, control, or learnability rather than assuming another objective will solve the problem.

## How this becomes real iteration

Finish experiment 1, then run the cheap fixed-policy screen and repeated-seed traces in experiments 2–3. Use those results to refine the queued one-frame training comparison. Run counterfactual branches when they can answer an unresolved decision-quality question; building that tooling is not a mandatory delay before the one-frame comparison. Experiments 6–8 are conditional branches, not instructions to launch every idea. Before each run, write down both the leading prediction and an outcome that would count against it. Afterward, fill in measured results, explain the strongest surviving possibilities, and name the next test that separates them.

Use fresh reserved cohorts for new development comparisons and separate evidence for confirmation. Preserve the existing registration, source review, resource, seed-exclusion, exactly-once, and checkpoint-acceptance requirements. This plan prepares future work; it does not change the active campaign or open a confirmation set.

Sources: [newcomer guide and source map](../learning/reports/dodge-native-project-guide-20261028/REPORT.md), [completed six-model comparison](../learning/runs/v2/fullgame-priority-D4-last-three-evaluator-sonnet-20261028-r1/six-model-merge.json), [current campaign registration](../learning/runs/v2/uniform2-continuation600-luna-20261028-r2/registration-final.json), and [investigation methodology](investigation-methodology.md).
