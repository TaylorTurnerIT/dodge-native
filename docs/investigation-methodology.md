# Investigating models that fail to learn

Record the method used in the Opus 5.5 teacher investigation as a reusable pattern: inspect behavior, compare stages on matched inputs, perturb the information the task requires, and choose the smallest experiment that could disprove the diagnosis. Establish that useful information affects decisions before spending more on training.

This guide describes observable tools, measurements, and experiments. The project-specific findings are in [Teacher representation diagnosis](teacher-failure-diagnosis.md). The [historical probe archive](investigations/opus-teacher-diagnosis-2026-10-24/README.md) preserves the original scripts, raw measurements, and hashes.

## Repeatable procedure

### 1. State the behavioral failure and the intended contract

Write down what the system should do, what information it receives, and what it actually does. Compare the supplied architecture with the executed code, including preprocessing, feature units, entity counts, masks, output heads, action mapping, and observation/label timing.

Start with a concrete failure trace. In this case, aggregate survival looked slightly better than neutral, but the policy selected left on every decision in two traced episodes. That observation made a collapsed policy a useful hypothesis. Passing tests and finite loss established neither useful behavior nor correct learning.

Save the checkpoint hash, source identity, runtime, configuration, seeds, controller, sampling cadence, and actual resource use. Use the project's environment; Opus corrected an initial system-Python import failure by using `learning/.venv/bin/python`.

### 2. Compare learning stages on identical observations

Load fresh initialization, the intermediate supervised checkpoint, and the later RL checkpoint. Run all models on the same retained observations. Keep evaluation mode and preprocessing consistent.

This comparison separates changes in the model from differences in the states each policy visits. Then trace each policy in closed-loop play separately: matched-input sensitivity and behavior under policy control answer different questions.

Opus used 40 observations sampled every 15 frames from one avoidance-controlled trajectory, seed 2000, with a 600-frame cap. It compared action distributions, argmax actions, latent variation, and attention statistics across all three models. That localized enemy insensitivity to a stage before PPO and showed that player-position conditioning weakened after PPO.

### 3. Inspect input composition and representation scale

Count relevant objects and nuisance/context records. Measure the norms of identity embeddings, feature projections, and their variation across examples. Inspect the exact fields included in each statistic.

The Dodge model processed roughly 590 tokens while only six represented enemies in the sampled state. Kind embeddings had norms around 11; varying projected features were much smaller. This suggested a way for identity and catalog context to dominate geometry.

Magnitude comparisons suggest a conditioning problem. They do not prove that the network cannot represent a useful solution. Opus's projected-feature variation statistic covered all 32 fields within a kind; it did not isolate position and velocity alone.

### 4. Measure routing and local sensitivity

Use several measurements that fail in different ways:

| Measurement | Question | Evidence to retain |
| --- | --- | --- |
| Output variation across matched states | Does behavior depend on the state? | Probability vectors, argmax counts, standard deviations |
| Latent variation relative to latent norm | Does the representation vary across states? | Exact formula and sampled states |
| Attention entropy versus `log(N)` | Is attention close to uniform over valid records? | Valid-token counts, masks, entropy, reference value |
| Attention mass by semantic group | Which groups receive routing weight? | Group sizes, total mass, and per-token mass |
| Input gradients for a declared scalar output | Which inputs locally affect that scalar? | Scalar definition, gradient aggregation, units, group sizes |

Opus differentiated `std(logits)` with respect to input features and summed absolute gradients by entity kind. This is a scalar sensitivity proxy, not a full action-probability Jacobian or a geometric-only gradient norm. Group totals also depend on token counts and feature scaling.

Attention alone is not causal evidence. Residual paths, value projections, and later layers can change what attention weights mean. Treat agreement between routing statistics, gradients, finite interventions, and actual behavior as stronger evidence than any single metric.

### 5. Intervene on one semantic input group

Hold the model and reference observation fixed. Construct controlled variants such as moving an enemy toward the player, moving the player toward a boundary, or removing a context group for diagnosis. Compare complete output distributions, not only their winning actions.

For categorical policies, total variation is:

```text
TV(reference, intervention) = 0.5 * sum(abs(p_reference - p_intervention))
```

Record the object selected, the changed fields, the reference output, and the modified output. Recompute coupled fields such as bounds, masks, relative features, and counts when those fields affect the tested path. State explicitly when a counterfactual is synthetic rather than a simulator-executed state.

Opus changed the first enemy record in one middle observation, despite a script comment mentioning the nearest enemy. It also moved the player and removed selected token groups. Bringing an enemy nearby barely changed either trained policy's probabilities. Player-position changes affected the supervised model much more than the PPO model.

Removing records also changes sequence length and attention normalization. Use removal to identify a promising hypothesis; use matched controls and retraining ablations to test its mechanism. A large response to a perturbation can still be wrong behavior, while an unchanged argmax can still be correct if the original action remains safe.

### 6. Verify that the objective requires the allegedly ignored information

Apply the same intervention to the labeling rule, reference controller, or task outcome. If target decisions do not depend on that information, insensitivity may be reasonable.

Opus queried avoidance labels with and without enemies on the same 5,000 visited states across seeds 2000–2004. About 75% of all labels changed, including about 91% of non-neutral labels. This established that enemy information mattered to the imitation objective. It did not establish that the heuristic was optimal.

Also report class frequencies, a majority-class baseline, per-class recall, and confusion. Accuracy on replay-weighted optimization batches cannot be compared directly with frequencies from a differently sampled collection population.

### 7. Separate observations from causal explanations

Use three categories in the investigation record:

- **Observed:** the intervention produced a measured response; a checkpoint lost state variation; a policy repeatedly chose one action.
- **Supported explanation:** several independent measurements point toward a mechanism, such as poor geometric conditioning.
- **Unresolved:** a proposed cause still needs a discriminating experiment, such as critic gradients destroying actor features.

Identify where the symptom first appears. Enemy insensitivity before PPO means a PPO-only explanation is incomplete. It does not universally rule out insufficient training, capacity, imbalance, or covariate shift. Likewise, a small value loss does not validate the whole actor/critic learning process.

For each leading explanation, record a predicted result and a result that would count against it. Avoid turning a confident reviewer summary into stronger evidence than its measurements support.

### 8. Run the cheapest controlled experiment before another long campaign

Use a fixed dataset and matched initialization, minibatch order, optimizer, and update budget. A small balanced overfit problem can test whether a model can acquire the proposed distinction within a bounded budget. A fixed real-data fit can test whether the improvement survives outside the synthetic construction.

The subsequent Dodge experiments compared a baseline, finite attention priority, relative geometry with smaller kind embeddings, and their combination. All retained the full privileged state. The native death traces, synthetic overfit runs, and four-arm implementation were independent parent-team work following Opus's diagnosis; Opus itself ran two read-only probe scripts, not those training experiments.

Interpret bundled changes as a bundle. Relative geometry plus smaller embeddings does not isolate the contribution of each component. If time limits produce different update counts, report that mismatch instead of claiming a controlled causal comparison.

Set advancement criteria before the experiment, then verify task behavior. The proposed 90% label accuracy and TV 0.2 thresholds were exploratory gates for this investigation, not universal constants or teacher qualification. Closed-loop survival, coverage, held-out evaluation, and the frozen acceptance protocol remain separate evidence.

### 9. Revise the diagnosis when a proxy improves but behavior does not

The [second Opus investigation](investigations/opus-teacher-diagnosis-2026-10-24-round2/README.md) followed this pattern: relative geometry improved held-out recall and enemy sensitivity, yet survival stayed identical to neutral. Instead of treating the proxy improvement as progress in play, Opus traced model-controlled states and asked the reference controller what action was needed there.

Separate decisions that begin a response from those that continue it. In this game, action changes and movement from rest were much harder than continued movement. Overall accuracy concealed this distinction. Query the label on every native frame so action-change tags do not depend on dataset sampling cadence. Report subset definitions, thresholds, counts, correct counts, and recall together.

Count the relevant examples in the actual training set. Measure the final model on those examples; an accuracy averaged across changing weights during optimization is not a final fit check. Compare expert-visited and model-visited states to test distribution shift, while preserving the original trajectories and controller checkpoint.

When collecting additional model-visited examples, match sample and update budgets to an expert-state control. Report temporal cadence, horizon, class proportions, and overlap with original examples. A collection intervention can change all of these; its result does not isolate one mechanism. Check first-response timing alongside actual task performance so premature movement is not mistaken for useful reaction.

Keep the first diagnosis and its raw measurements. Record which causal claims weakened, which observations survived, and which new test could distinguish the remaining explanations. A corrected interpretation is part of the investigation record.

The ensuing collection comparison taught movement initiation and improved survival on six of ten smoke seeds, while lowering aggregate expert-state classification accuracy. This demonstrates why a useful diagnostic subset must still be checked against actual task behavior. Moving at least once did not suffice: four episodes took a few movement actions yet died at the neutral policy's timing. After a partial repair, examine the behavior following the repaired decision and the distribution of gains across episodes before declaring the bottleneck resolved.

Trace each metric back to its aggregation window. A field called training accuracy or classification loss may average predictions from many different model states during optimization. Evaluate the final model explicitly before claiming training fit or a loss plateau. A longer-fit comparison should preserve the exact data and reproduce its earlier checkpoint's weights, optimizer, and update order before interpreting later checkpoints. Matching whole checkpoint files is inappropriate when their metadata changes.

## Minimum investigation record

Preserve a short, self-contained record with these fields:

```text
Behavioral failure and acceptance criterion:
Artifact/source/runtime/configuration identities:
Models or pipeline stages compared:
Observation provenance, controller, seeds, and sample counts:
Intervention, selected object, and coupled fields changed:
Metric definitions and raw measurements:
Observed facts:
Leading explanation and competing explanations:
Smallest experiment that could disprove the explanation:
Matched controls, update/resource budgets, and advancement gate:
Result, uncertainty, and next decision:
Evidence/script locations and hashes:
```

Archive raw scripts and measurements outside disposable run folders when they are intended for long-term reference. Preserve originals and label their limitations; write improved reusable tooling separately rather than silently changing historical probes.

For other pipelines, substitute revisions or processing stages for checkpoints, semantic input groups for entity types, and observable outputs for policy probabilities. The transferable pattern is matched comparisons, controlled interventions, target-dependence checks, and evidence-ranked explanations—not the particular attention multiplier or numerical thresholds used here.
