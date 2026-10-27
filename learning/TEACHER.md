> Historical implementation and diagnostics: superseded by the user-supplied [v2.0 specification](../docs/SPEC_PRIVILEGED_VIT_RL.md). Retained for provenance; its objectives, feature contracts, architecture, and gates are not the current plan.

# Entity-transformer teacher and ViT student

The primary architecture is the user-supplied [entity-transformer teacher and visual ViT student](../docs/entity-transformer-architecture.md). The teacher consumes privileged engine records and trains with PPO. The student consumes images only and receives action, latent, and spatial-attention supervision. The earlier MLP and CNN remain explicit baselines. A successful optimization diagnostic does not establish game-playing quality.

## ViT input and architecture

`ViTPolicy(ViTConfig())` accepts only a floating-point tensor shaped `[batch, 4, 128, 128]`. It consumes the four most recent grayscale frames, oldest first, normalized to `[0, 1]`. Use `PixelHistory.gray_chw()` for palette-derived luminance. The legacy CNN retains `PixelHistory.rgb_chw()` and 12 channels.

The transformer fuses time into channels before patch embedding. Default 16×16-pixel patches produce the diagram's 8×8 spatial grid and 64 tokens. Patch sizes 8 and 4 produce 256 and 1,024 tokens. The model uses learned spatial positions, four pre-normalized blocks, learned attention pooling, and nine action logits. Default width is 128 with four heads and MLP ratio 2; the model has 670,857 parameters. `distillation_outputs(images)` adds the 128-dimensional latent and 64 patch weights without accepting privileged inputs.

```sh
.venv/bin/python -m dodge_learning.smoke --architecture vit --device cpu --patch-size 16 --steps 1 --batch-size 1
.venv/bin/python -m dodge_learning.smoke --architecture vit --device mps --patch-size 4 --steps 1 --batch-size 1
.venv/bin/python -m dodge_learning.smoke --architecture cnn --device cpu --steps 1 --batch-size 1
```

These are bounded synthetic gradient checks. The corrected model and all three loss bridges passed a synthetic MPS forward/backward check. Earlier RGB ViT receipts describe a different input contract. Neither check measures gameplay quality or deployment latency.

## Teacher feature contract

`EntityActorCritic` uses privileged schema `1`: 64 global features and 32-feature typed entities. It retains offscreen enemies, inactive patterns, hidden timers, queued targets, spawns, RNG, and the other engine records described in the architecture contract. Entity projection, two player-query attention blocks, a 128-dimensional latent, and policy/value heads contain 430,474 parameters. The teacher has no image branch.

`encode_entities` returns immutable features; `batch_entities` pads without dropping records. Attention masks preserve all valid entities, and nonplayer order does not affect the policy. The 8,192-token capacity raises an error on overflow. Spatial flags affect only the attention-target projection, not teacher information access.

The earlier `teacher.StateActorCritic` is the filtered MLP baseline, using native feature schema `2` and legacy encoder schema `1`. It remains available through `--architecture legacy_mlp`; its pilots are not results for the entity transformer.

`distillation.distillation_losses` implements action KL, normalized-latent MSE, and projected spatial-attention KL. All teacher targets are detached. All three weights default to 1. The spatial projector clips half-open entity bounds to the captured image, distributes mass by patch overlap, renormalizes visible mass, and reports how many rows have valid targets. Rows with no visible target skip only the attention term.

## Seed splits

`seeds.seed_manifest()` freezes these distinct RNG streams:

- Training: `1000..1099`.
- Smoke evaluation: `2000..2009`.
- Validation: `3000..3099`.
- Final test: `4000..4099`, reserved for a frozen recipe.

The manifest and its SHA-256 are saved with every training run and checkpoint. Validation rejects cross-split overlap, duplicate streams, and the equivalent `0`/`1` RNG streams. The teacher evaluation CLI exposes only smoke and validation splits.

## Run a bounded teacher experiment

From `learning`, after installing `.[models]`:

```sh
.venv/bin/python -m dodge_learning.teacher_run train \
  --output-dir runs/my-teacher \
  --architecture entity_transformer \
  --frames 100000 --max-seconds 1800 \
  --evaluate-smoke --smoke-frames 1000 --evaluation-seconds 300
```

Use a new output directory for each run. The CLI never replaces an existing run. Its initial limit is 100,000 training frames and 30 minutes per run. Training uses one CPU environment, action repeat `1`, and one PyTorch thread. Default rollout length is 256 with four PPO epochs and minibatches of 64. Hyperparameters and actual frame/update counts are recorded.

Current teacher training uses reward scale `0.01` for GAE and value targets; native reward validation, episode returns, and survival evaluation remain in raw native frames. `--reward-scale 1` is an explicit unscaled comparison. The actor head starts near a uniform policy through small-gain orthogonal initialization. The CLI exposes discount, GAE lambda, value/entropy coefficients, gradient clipping, CPU threads, and entity-model dimensions. These settings are recorded with the model configuration.

`--warm-start PATH` imports matching entity-transformer weights into a fresh run. It requires the current source fingerprints, native game configuration, frozen seed manifest, training seed order, and declared model dimensions. It records the parent checkpoint hash and restarts optimizer, rollouts, private RNGs, and training seed order. This is weights-only continuation, not exact resume; neither frame counts nor qualification transfer to the new run. Parent receipts preserve cumulative experiment cost.

PPO stores the value of each transition's actual final observation. Death removes bootstrap value. Time-limit truncation keeps that value but cuts the advantage trace before reset. Rollout boundaries bootstrap without becoming episode boundaries. The frame limit permits a final partial rollout update while time remains. The wall-time limit stops additional collection and optimizer steps; any collected samples left unoptimized are reported. Individual simulator or PyTorch operations are not preempted mid-call.

The output directory contains `config.json`, `seeds.json`, `source.json`, `progress.jsonl`, `teacher.pt`, and `run.json`. Optional comparison results go to `smoke-evaluation.json`. Failures retain a `failure.json` receipt. Source manifests include learner source hashes and the native extension's SHA-256. No image dataset is written by this command.

Checkpoints publish atomically without overwriting an existing destination. Entity teachers use format `2`, kind `dodge_entity_transformer_teacher`, and an explicit privileged schema. Legacy MLPs retain format `1`, kind `dodge_state_teacher`. Loading uses PyTorch's weights-only reader and validates architecture, schemas, action order, model shapes/dtypes, finite weights, and seed membership. Optimizer state is retained, but exact resume is not implemented: checkpoints do not include complete rollout and RNG state. The CLI starts fresh runs.

## Evaluation and the collection gate

```sh
.venv/bin/python -m dodge_learning.teacher_run evaluate \
  --checkpoint runs/my-teacher/teacher.pt \
  --output runs/my-teacher/validation.json \
  --split validation --max-frames 18000 --qualify --max-seconds 1800
```

Evaluation compares the greedy teacher with neutral, random, and avoidance policies on the same initial seeds. A shared wall-time budget covers checkpoint loading and every policy. Native configuration and semantic provenance must match. Recorded native-binary, encoder, and wrapper hashes must match the running implementation; absent fingerprints permit diagnostics only. Reports record runtime versions and source identity.

Qualification requires the exact frozen four-split seed manifest, difficulty `2`, patterns and powerups enabled, theme background/shadow `12/1`, all 100 validation episodes at the 18,000-frame cap, all three baselines, matching source identity, and both of these conditions:

1. The lower bound of a paired 95% bootstrap interval for mean capped-survival improvement over the best baseline is positive.
2. At least 25 teacher episodes survive a complete active pattern.

The bootstrap uses a private fixed RNG and 2,000 resamples. Smoke results never authorize student collection. A timeout produces no passing qualification. Direct calls that supply reports are statistical helpers, not a substitute for runtime evidence.

Structurally valid custom manifests can be loaded for diagnostics, but cannot qualify under the frozen protocol. Both formal entry points compare the complete manifest hash with `seed_manifest()` before episodes or qualification calculations. Replacing validation seeds with another disjoint set requires a separately versioned experiment, rather than changing the embedded checkpoint manifest.

Curriculum configurations can also be evaluated diagnostically, but cannot qualify as the default benchmark. Both formal entry points enforce the exact configuration values and types before episodes or qualification calculations. Matching the teacher and baselines to the same non-default configuration is insufficient.

The current work is teacher-only, as requested. Student fitting, student DAgger, and deployment remain deferred until there is a capable teacher. Teacher imitation experiments may use avoidance-labelled states visited by a frozen teacher; these do not collect visual student data or transfer qualification. Student collection stays blocked until a teacher clears the full gate. Training costs include teacher frames, optimization, and evaluation; historical synthetic student checks remain separate evidence.

## Legacy MLP pilots

The 10,000-frame and 100,000-frame pilots used unchanged hyperparameters and fresh starts from the same training seed. Total training collection was 110,000 frames. The larger run finished all requested frames and 6,252 optimizer steps in about 46 seconds, with finite weights and no unoptimized samples.

Its ten-seed smoke evaluation, capped at 1,000 frames, averaged 198 survival frames. Neutral averaged 188.5, random 260.9, and avoidance 1,000. The teacher never reached an active pattern; four avoidance episodes completed one. The teacher is therefore not qualified, and no visual training dataset was collected. The formal validation gate and reserved final test split were not exercised.

Local artifacts are in `runs/teacher-pilot-10000/` and `runs/teacher-pilot-100000/`; earlier RGB ViT diagnostics and test logs are in `runs/milestone2-smoke/`. These timings describe bounded diagnostics on the local Mac, not isolated performance benchmarks. MiMo's seed-substitution finding and DeepSeek's default-configuration finding were reproduced and fixed. Both pilots used the required seed recipe and configuration, so their results remain unaffected. At that milestone, all requested reviews were reconciled and 101 Python tests passed. Those verdicts do not transfer to the corrected architecture.

## Corrected-architecture diagnostics

The default entity teacher completed a separate 1,000-frame CPU pilot with one PPO epoch, 64-step rollouts, and minibatches of 16. All samples were optimized in 63 optimizer steps, taking about 12.4 seconds. This was a pipeline pilot, not a controlled speed benchmark or a competent teacher. Its ten-seed smoke evaluation at a 256-frame cap averaged 107.8 survival frames, versus 188.5 neutral, 234.7 random, and 256 avoidance. No teacher qualification or student collection followed.

To check the assembled architecture on a paired native image/state without fitting either model:

```sh
.venv/bin/python -m dodge_learning.architecture_smoke --device cpu --max-frames 128
.venv/bin/python -m dodge_learning.architecture_smoke --device mps --max-frames 128
```

Both backends passed on the same training-seed frame, retaining 593 privileged records and producing finite student gradients through all three bridges. Teacher gradients were absent. The command performs one backward pass, zero optimizer steps, and writes no checkpoint or dataset. Receipts are in `runs/entity-architecture-validation/`; the independent teacher pilot is in `runs/entity-teacher-pilot-1000/`.

## Teacher-first training experiments

The current phase defers all student work. A 10,000-frame transformer PPO run used near-uniform actor initialization, reward scale 0.01, gamma 0.995, 256-step rollouts, four epochs, and minibatches of 64. It completed all frames in about 122 seconds with no unoptimized samples. Its last value MSE was about 0.0031 and gradient norm about 2.81, substantially below the earlier raw-return pilot. Those numerical diagnostics do not establish gameplay improvement.

On ten held-out smoke seeds at a 1,000-frame cap, mean survival remained 107.8 frames. Neutral reached 188.5, random 260.9, and avoidance 1,000; avoidance completed a pattern in four episodes. The learned teacher completed none. Its greedy policy continued favoring one direction across different states. The checkpoint remains unqualified; no formal validation or student collection followed. Receipts are in `runs/entity-teacher-scaled-10000/`.

The following teacher-only experiments warmed up the same full-state transformer from avoidance-action labels on training seeds, then used PPO for further learning. Heuristic warmup is reported separately from PPO training and from teacher qualification. Matching a heuristic does not satisfy the requirement to outperform it.

Two 10,000-frame warmups used identical avoidance-controlled trajectories and labels. They kept at most 2,048 privileged records in replay, trained each new frame once in the first epoch, and sampled replay in the remaining three epochs. The first used ordinary cross-entropy. The second used capped square-root inverse-frequency class weights to reduce dominance of neutral labels. Each took about two minutes. These runs stored teacher checkpoints and metrics, not image datasets.

Both warmed teachers averaged 188.5 survival frames on the same ten smoke seeds, matching the neutral baseline. The weighted model improved several movement-action recalls on a separate 250-state diagnostic from two heuristic-controlled smoke trajectories, but that did not improve closed-loop survival. Warmup-controller pattern completions describe the avoidance controller, not the learned policy. Neither model is qualified.

A separate 100,000-frame PPO continuation used the weighted checkpoint, learning rate `0.0001`, reward scale `0.01`, and gamma `0.995`, with a 30-minute training cap. It completed in about 1,239 seconds, with 6,252 optimizer steps and no unoptimized frames. Held-out mean survival reached only 196.9 frames; no teacher episode reached an active pattern. Formal qualification was skipped. The unchanged-code Python suite passed 152 tests. Evidence and review responses are in `runs/teacher-training-improvements/`.

The subsequent [representation diagnosis](../docs/teacher-failure-diagnosis.md) found severe hazard insensitivity and constant-left behavior. A four-arm fixed-data comparison retained all privileged inputs and compared the original representation, finite attention priority, relative geometry with smaller kind embeddings, and both changes. All arms used 5,000 training examples, 1,000 smoke examples, eight epochs, 632 updates, and 40,000 sample visits. Relative geometry raised held-out balanced accuracy from 37.86% to 46.14%, but both evaluated teachers still averaged 188.5 survival frames, matching neutral. The finite priority alone did not materially improve classification. Receipts are in `runs/teacher-representation-ablation-r1/`.

Opus's second investigation traced this failure to missed movement initiation on the tested smoke trajectories. Both models remained neutral through three complete greedy episodes and missed all 48 sampled non-neutral labels near rest, defined by both native velocity magnitudes below `0.05`. Improved classification came mainly from continuing movement. Rare training examples, distribution shift, velocity shortcuts, and representation limits remain hypotheses. Historical online training accuracy is not final-model training fit.

The next bounded comparison added either 2,500 expert-state examples or 2,500 avoidance-labelled frozen-teacher states to the same original 5,000 examples. It held model configuration, initialization, sample count, optimizer, and updates fixed. Different episode lengths required different collection cadences, and some learned-path examples repeated the base dataset. Receipts report those differences and final-model recall by onset, continuation, exact rest, and near rest. First-movement timing and survival test whether improved imitation affects play. This is a diagnostic of the collection strategy, not a pure test of one causal mechanism.

No further PPO, student work, or pool/patch changes accompany that comparison. Separate threat/context attention and critic detachment remain untested follow-ups.

Run the bounded comparison from `learning`:

```sh
.venv/bin/python -m dodge_learning.teacher_onset_ablation \
  --output-dir runs/teacher-onset-ablation-r1 \
  --collector-checkpoint runs/teacher-representation-ablation-r1/relative.pt \
  --epochs 8 --max-seconds 1200 --arm-seconds 300
```

The frozen collector supplies visited states and pretraining predictions only; neither fitted arm imports its weights or optimizer. Inference requires matching runtime model/encoder/wrapper/native fingerprints, the frozen seed recipe, and matching labeling-policy and seed sources. Historical training-command changes do not alter inference. Actual PPO warm starts retain their stricter training-source checks, including this experiment's module and shared representation helpers for onset checkpoints.

The runner verifies that the reproduced base dataset matches the original collector checkpoint's training-data hash before fitting. Default budgets give each fresh arm 7,500 examples, eight epochs, 944 optimizer steps, and 60,000 sample visits. Dataset estimates are capped at 2 GiB; process RSS is measured separately. All ten smoke seeds are diagnostic. Source changes, incomplete collections, and exhausted budgets retain failure receipts instead of yielding a valid matched comparison.

The first run completed once in 499.70 seconds with matching initialization and minibatch order. Learned-state relabelling raised mean smoke survival to 253.8 frames, versus 188.5 for the control and neutral, 260.9 random, and 1,000 avoidance. It moved on all ten smoke seeds; six survived longer and four still died at neutral's timing. Both teachers completed zero patterns. The teacher remains unqualified.

On the unchanged original training set, the learned-state arm recognized 18/19 non-neutral exact-rest examples, compared with 0/19 for the control. Held-out exact-rest recall was 2/2 versus 0/2, but broader smoke accuracy fell from 78.8% to 74.2% and non-neutral onset recall from 24/142 to 20/142. The learned extras retained 1,089 exact base-input overlaps. These results support the collection intervention while leaving continued avoidance and generalization unresolved. Receipts are in `runs/teacher-onset-ablation-r1/`.

## Fixed-data optimization budget

The next diagnostic varies only optimizer updates on the reproduced relabelled dataset. It uses one fresh model and one continuous Adam trajectory, with evaluations at epochs 8, 16, 32, and 64. The original stationary teacher generates the same examples; the moving teacher's epoch-8 checkpoint supplies exact reference tensors and optimizer state. Neither checkpoint initializes the new model.

```sh
.venv/bin/python -m dodge_learning.teacher_fit_budget \
  --output-dir runs/teacher-fit-budget-r1 \
  --collector-checkpoint runs/teacher-representation-ablation-r1/relative.pt \
  --reference-checkpoint runs/teacher-onset-ablation-r1/learned_state_relabel.pt \
  --max-seconds 1800
```

Before fitting, state/label and onset-tag hashes must reproduce the fixed 7,500 training examples and 1,000 smoke examples. Epoch 8 must reproduce the old model tensors, optimizer values, initialization hash, cumulative minibatch-order hash, and update counts before any additional updates. Snapshot evaluation preserves model weights, optimizer, training mode, and private RNG sequence. Complete checkpoint file hashes can differ because the new provenance and configuration differ.

Each snapshot reports final-model cross-entropy separately from accumulated online loss, subset recall on training/original-base/smoke examples, and greedy smoke behavior. Gameplay includes reward-based survival, first movement, action counts, longest consecutive movement runs, and agreement with avoidance on visited-path action changes and continuations. Action-sequence hashes describe exact action repetition; they do not establish statistical independence or full trajectory equivalence.

The fixed recipe remains seed 7, width 128, depth 2, four heads, relative geometry, kind scale 0.02, Adam at `3e-4`, minibatches of 64, and one CPU thread. A complete 64-epoch run performs 7,552 updates and 480,000 sample visits. Early stopping is evaluated only at checkpoints and requires final training accuracy at least 99%, non-neutral onset recall at least 90%, and non-neutral continuation recall at least 95%.

One invocation has a shared 1,800-second budget, a 2 GiB dataset estimate cap, and a 6 GiB observed peak-RSS threshold. Checks occur between operations; individual native/Torch calls are not preempted. Failures retain partial checkpoints and receipts rather than retrying or relaxing limits. The old onset runner keeps its separate 1,200-second total and 300-second arm limits. No PPO, cost-margin instrumentation, architecture change, pool/patch change, formal validation, final test, or student work accompanies this diagnostic.
