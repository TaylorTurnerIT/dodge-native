# Historical Opus teacher review, round 3

This read-only review interpreted the completed state-collection comparison. Opus ran no runtime probes. The [original task result](task-result.json) and [manifest](manifest.json) preserve its recommendation and source/checkpoint identities. The [current diagnosis](../../teacher-failure-diagnosis.md) records the parent audit and chosen experiment.

Opus proposed keeping the data and model fixed while increasing optimizer updates, with checkpoints at epochs 8, 16, 32, and 64. Final-model training recall supports this as a useful test: both teachers still miss many non-neutral action changes on their own training data.

The parent audit corrected these details before implementation:

- `classification_loss` in the old runner averages losses across changing weights during training. The quoted 0.767 and 0.651 are not final-model losses. The next runner must compute final cross-entropy directly.
- Regenerating the fixed dataset requires the original stationary `relative.pt` collector, not the new moving teacher. Exact state/label and tag hashes must match the prior comparison before optimization.
- Epoch 8 must reproduce model tensors, optimizer state, initialization, and minibatch order. A new checkpoint's complete file hash cannot match the old checkpoint when configuration and provenance differ.
- Training-label errors do not prove that more aggregation cannot help. The completed aggregation intervention already improved movement and survival. A fit-budget test asks whether more updates help under one fixed objective; it does not establish the only possible remedy.
- Similar episode action counts do not establish an effective independent sample size of six. Keep the ten frozen smoke seeds and report their per-seed outcomes without inferring independence from summaries.
- Oracle cost margins were not retained. Cost instrumentation is deferred so the first comparison can change only optimizer updates without modifying the frozen labeling-policy implementation. Small cost margins would not by themselves prove label noise.
- The 1,800-second budget and 6 GiB peak-RSS threshold are checked between operations. They are cooperative failure limits, not strict operating-system preemption or a reliable macOS `RLIMIT_RSS` guarantee.

The source audit found all scalar inputs read by the avoidance policy in the full privileged features. The actor must infer legacy visibility membership from geometry and camera/clip fields; availability does not prove exact policy reconstruction or learnability. Architecture changes, PPO, pool/patch changes, formal qualification, and student work remain deferred.
