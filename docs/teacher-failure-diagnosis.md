> Historical implementation and diagnostics: superseded by the user-supplied [v2.0 specification](SPEC_PRIVILEGED_VIT_RL.md). Retained for provenance; its objectives, feature contracts, architecture, and gates are not the current plan.

# Teacher representation diagnosis

The reusable procedure behind this investigation is recorded in [Investigating models that fail to learn](investigation-methodology.md), with [archived original probes](investigations/opus-teacher-diagnosis-2026-10-24/README.md).

The 100,000-frame warm PPO run completed, but the teacher remains unqualified. Mean capped survival on ten smoke seeds was 196.9 native frames, compared with 188.5 for neutral, 260.9 for random, and the 1,000-frame cap for avoidance. The teacher encountered no active pattern. Student work remains deferred.

## What the probes establish

Opus 5.5 inspected the implementation and ran read-only representation probes. Independent native traces agree with its main observation: the trained policy responds weakly to enemy geometry.

- On train seed 1000 and smoke seed 2000, the greedy policy selected left on every decision, reached the left boundary by frame 30, and died around frame 196.
- Near death, total attention on spatial records was about 0.27%. Inactive rectangles, queued spawns, and queued targets held most of the attention.
- In Opus's tested counterfactual states, moving an enemy eight pixels from the player changed the warm PPO action distribution by at most about 0.0013 in total variation. The weighted bootstrap checkpoint was also insensitive, before PPO.
- The bootstrap checkpoint did respond to player position. That response became much weaker after PPO. This establishes lost conditioning, but does not establish that critic gradients caused it.
- Enemy positions and velocities affect the avoidance labels. Poor imitation is therefore not explained solely by the frequency of neutral actions.

The implementation mixed hundreds of inactive catalog and metadata records into the same attention pool as a handful of current hazards. Large kind embeddings further outweighed the varying geometric features at initialization. These choices were added during implementation; the supplied diagram depicts focused attention over engine entities. The observed attention and counterfactual results support a conditioning problem in this implementation. They do not prove that the architecture is incapable of representing a useful policy given arbitrary training.

## Independent synthetic control

A small diagnostic preserved the full native catalog and added one synthetic enemy. It used 16 balanced geometry cases, with two examples for each movement label. The existing checkpoint and a fresh default model after 300 optimization steps both achieved 12.5% accuracy. A finite enemy-attention multiplier of 512 retained all attention keys and reached 62.5% under the same diagnostic budget. Smaller kind embeddings alone, projection normalization alone, and a multiplier of 64 did not improve beyond chance in that probe.

These counterfactuals were constructed for diagnosis; they are not simulator trajectories. The result supports a targeted conditioning experiment, not a gameplay or qualification claim.

## Completed representation comparison

The four-arm comparison used one fixed set of 5,000 training-only avoidance labels and 1,000 smoke examples:

1. Existing full-catalog model.
2. A finite prior favoring current physical entities, retaining all metadata keys.
3. Player-relative geometry with smaller kind embeddings, retaining all records.
4. Both representation changes.

All arms shared initialization seed 7, examples, minibatch order, Adam at `3e-4`, eight epochs, 632 updates, and 40,000 optimized samples. Baseline balanced accuracy was 37.86%; relative geometry with smaller kind embeddings reached 46.14%. The finite attention prior alone reached 37.95%. Relative geometry increased the maximum tested enemy-counterfactual TV from 0.0062 to 0.1652. These are diagnostic responses, not correctness measures.

Neither evaluated model improved gameplay: baseline and relative teachers both averaged 188.5 frames across ten smoke seeds, exactly matching neutral. No teacher episode completed a pattern. Receipts remain in `learning/runs/teacher-representation-ablation-r1/`.

The counterfactual diagnostic used the first 40 eligible smoke records, all from the beginning of seed 2000, and modified the first normal enemy. It did not sample the state distribution broadly. Its exploratory accuracy/TV thresholds are not qualification requirements.

Opus suggested separating threat attention from metadata context and testing a detached or separate critic. Those remain follow-up experiments. Value coupling is a plausible cause of lost conditioning, not a confirmed implementation defect. The default-path PPO math audit found no error in GAE, clipping, transition alignment, action mapping, or reward units that explains this run. Insufficient training, capacity, class imbalance, and covariate shift remain possible contributors.

## Round 2: inspect decisions that begin movement

Opus revisited its diagnosis after the representation changes improved classification and sensitivity without improving survival. The [round-2 archive](investigations/opus-teacher-diagnosis-2026-10-24-round2/README.md) preserves the original scripts and results.

Both greedy teachers selected neutral on every frame of smoke seeds 2000–2002 and died at frames 191, 188, and 191. On those teacher-visited states, avoidance requested movement for 36, 18, and 43 frames before death. This is a persistent missed response, rather than a single-frame timing error.

On avoidance-controlled seeds 2000–2004, both models missed all 48 non-neutral labels where both player velocity components had magnitude below `0.05`. This is a **near-rest** subset, not an exact-zero subset. The first avoidance movement in each episode occurred at frames 147–170 with player state exactly `(64, 64, 0, 0)`. The relative model's gains came mainly from continuing movement; recall on action changes remained low. Player velocity may provide a shortcut, but the probes do not establish that it caused the failure.

The observed defect is failure to initiate avoidance on these sampled trajectories. Rare onset examples and divergence from expert trajectories are plausible causes. The original training set's onset counts and the final model's fit must be measured before treating either explanation as established. In particular, the prior `training_accuracy` field averages predictions made throughout optimization; it is not final-model training accuracy and cannot establish underfitting.

## Completed state-collection comparison

Before more PPO or architecture changes, the next comparison fitted two fresh relative-geometry teachers:

1. **Control:** the original 5,000 expert-state examples plus 2,500 additional expert-state examples.
2. **Learned-state collection:** the same original 5,000 examples plus 2,500 states visited by the frozen relative teacher, labelled by avoidance.

Use the same initialization, optimizer, number of examples, minibatch order, and updates. First evaluate the existing relative teacher on the training examples, reporting final-model recall on action changes, non-neutral continuation, exact rest, and near rest. Compute action-change tags against the previous native frame's label, not the previous retained sample.

The control adds frames `5, 25, ..., 485` from each training seed. Learned episodes can end near frame 190, so their collection cannot use that full cadence. Select 25 distinct, evenly spaced rows from five-frame candidates in each learned episode, with no padding. Record selected frames and overlap with the original dataset: distinct rows can repeat original states before expert and learned paths diverge.

This comparison tests a collection strategy as a bundle. State distribution, temporal density, episode horizon, action frequencies, and repetition can all differ. Improvement would support this intervention, without isolating rare labels from covariate shift. One initialization and a negative result cannot rule out data-based correction.

Final-model training and smoke recall were measured by subset, followed by first-movement timing and greedy survival on all ten smoke seeds. The original 5,000-example hash matched exactly. Both arms completed eight epochs, 944 updates, and 60,000 sample visits with identical initialization weights and minibatch order. The campaign ran once, taking 499.70 seconds; each full arm took about 179 seconds. All learner/native source identities and checkpoint hashes matched the frozen implementation.

The frozen collector's final fit was 84.78% on its original training examples. It missed all 19 exact-rest and all 36 near-rest non-neutral labels in that dataset. These counts replace the earlier extrapolation from smoke. Its non-neutral onset recall was 173/650; it was not incapable of every action change, but failed on this movement-initiation subset.

The learned-state arm began moving on all ten smoke seeds; the extra-expert control remained neutral throughout. Mean reward-based survival was **253.8 versus 188.5 frames**. Six paired episodes improved; four stayed at the neutral survival time despite four to six non-neutral actions. Random averaged 260.9 and avoidance reached the 1,000-frame cap. Neither teacher completed a pattern; avoidance completed four. Executed native frames include the terminal death frame; reward-based survival excludes it, matching earlier evaluations.

On the unchanged original training examples, exact-rest non-neutral recall rose from the control's 0/19 to 18/19. The smoke dataset contained only two such examples: the learned-state arm got both right, the control neither. Near-rest smoke recall was 2/11 versus 0/11. Broader imitation regressed: smoke accuracy was 74.2% versus 78.8%, and non-neutral onset recall was 20/142 versus 24/142. Beginning movement therefore does not establish reliable continuing avoidance.

The learned-state extras included 1,089 exact state-and-label overlaps with the base; the control extras included none. The intervention changed temporal density, horizon, label proportions, and visited states together. It supports this data-collection correction as useful under the tested budget, without isolating rare examples from distribution shift or proving that representation limits are resolved.

All artifacts remain under `learning/runs/teacher-onset-ablation-r1/`, including the run, pretraining and final fit reports, source manifests, checkpoints, first-action timings, overlap receipts, and post-run verification. Dataset estimates totaled about 1.06 GB; separate peak process RSS was about 3.40 GB. Student work, PPO, and pool/patch changes remain deferred; formal validation and the reserved final test split remain untouched. The next diagnosis should inspect why the responding policy fails after its first move before choosing another bounded teacher experiment.

## Next controlled experiment: optimizer updates on fixed data

The [third Opus review](investigations/opus-teacher-diagnosis-2026-10-24-round3/README.md) recommends measuring whether more optimization improves the existing collection result. Final-model training recall remains poor on non-neutral action changes: 276/932 for the control and 250/699 for the relabelled teacher. This establishes training-label errors, without identifying optimization budget, label boundaries, or representation as the cause. The historical classification-loss field is an online average and cannot establish final loss or a plateau.

Regenerate exactly the relabelled teacher's 7,500-example dataset using the original stationary collector. Require the prior state/label hash and tag hash before fitting. Keep architecture, labels, initialization, optimizer, learning rate, batch size, and private RNG sequence fixed. Train one fresh optimizer trajectory for up to 64 epochs, with checkpoints and evaluations at epochs 8, 16, 32, and 64. At epoch 8, require exact model tensors, optimizer state, initial weights, and cumulative minibatch order to reproduce the previous result before proceeding.

At each checkpoint, compute final-model cross-entropy and recall on the fixed training, original-base, and smoke examples. Evaluate greedy smoke survival, first-action timing, action counts, consecutive direction runs, and agreement with avoidance on visited-path action changes and continuations. Keep the ten frozen smoke seeds and report per-seed outcomes; no formal validation or final test evaluation follows.

The campaign permits one invocation with a 1,800-second shared budget, a 2 GiB estimated-dataset cap, and a 6 GiB observed peak-RSS threshold checked between operations. Preserve partial checkpoints and receipts on failure. Early stopping requires final training accuracy at least 99%, non-neutral onset recall at least 90%, and non-neutral continuation recall at least 95%, measured at a checkpoint. These are exploratory fit criteria, not teacher qualification.

The parent source audit found all scalar avoidance inputs represented in privileged features: player/enemy geometry and velocity, personality, speed and freeze rate, rectangle motion and extent, and warning endpoints. Visibility filtering still requires inference from feature context; this audit does not prove learnability. Cost-margin instrumentation is deferred to preserve the fixed labeling-policy source and keep the first fit comparison narrow.

Improved training fit with better smoke behavior supports a larger optimization budget for this recipe. Improved training fit without better behavior motivates investigation of generalization or visited-state coverage. Failure to fit after more updates leaves representation and optimization unresolved; it does not prove label noise or rule out aggregation. No student, PPO, or pooling change is part of this test.

## Evidence

Local, ignored artifacts under `learning/runs/teacher-failure-diagnosis/` include the full Opus task result, probe scripts, raw JSON measurements, native failure traces, and the synthetic geometry probe. The failed campaign remains in `learning/runs/entity-teacher-warm-ppo-100000/`. These artifacts preserve the old checkpoints and source identities; their validation results do not transfer to a changed model.
