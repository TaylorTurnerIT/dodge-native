> Historical implementation and diagnostics: superseded by the user-supplied [v2.0 specification](SPEC_PRIVILEGED_VIT_RL.md). Retained for provenance; its objectives, feature contracts, architecture, and gates are not the current plan.

# Training a vision-only Dodge policy

Review date: October 23, 2026. Source revision: `d7ad95127ad7529c5217a51ae9dc5cfedd3f2365`.

Status: the user-supplied [architecture diagram and corrected contract](entity-transformer-architecture.md) supersede the original filtered-state MLP proposal. The primary teacher is now an omniscient entity transformer; the student is a visual ViT with action, latent, and spatial-attention distillation. Legacy MLP pilot results remain separate. Neither student has been trained on gameplay. Source findings below describe the pinned game revision.

## Recommendation

Train an entity-transformer teacher with privileged engine state, then distill its policy, latent representation, and spatial attention into an image-only ViT. Use DAgger to query the frozen teacher on states visited by the student. Deploy only the image policy.

The supplied [privileged-information discussion](Training-Vision-Models-Using-Privileged-Information.md) and later [architecture diagram](entity-transformer-architecture.md) define the intended teacher/student split. The diagram resolves the transformer backbones and all three required loss bridges. Game interfaces and evaluation details below adapt that architecture to the real codebase.

The game exposes both images and internal state without RAM scraping. The adapter and training pipeline are implemented. The immediate experimental gate is now a competent state teacher before collecting visual demonstrations. A compact ViT is the primary student candidate, with the CNN retained for comparison.

Target hardware: the local Mac first, as selected by the user. Use CPU simulation and teacher training initially; evaluate PyTorch MPS for the vision student. Keep training budgets provisional until the local throughput pilot.

## What the current code supports

- **Headless simulation and paired observations.** `NativeGame::advance_frame` returns a `FrameResult` containing reward, death, events, and a snapshot. The core has no Macroquad dependency. See [game.rs](../crates/dodge-core/src/game.rs#L63) and [the core manifest](../crates/dodge-core/Cargo.toml).
- **Privileged state.** `Snapshot::logical_state()` exposes `FullState`: player and enemy positions, velocities and sizes, patterns, spawn state, timers, camera, score, and RNG. This is enough to define a state teacher and training diagnostics. See [snapshot.rs](../crates/dodge-core/src/snapshot.rs#L51).
- **Pixels.** `Snapshot::pixels()` exposes a row-major 128×128 array of 16 palette indices. The viewer defines the palette and its RGB conversion. Palette indices are categorical colors, not grayscale intensities. See [snapshot.rs](../crates/dodge-core/src/snapshot.rs#L11) and [viewer/lib.rs](../crates/dodge-viewer/src/lib.rs#L105).
- **Nine movement actions.** Preserve `Action::ALL` order: neutral, left, right, up, down, up_left, up_right, down_left, down_right. Corresponding masks are `[0, 1, 2, 4, 8, 5, 6, 9, 10]`. X and O remain environment controls. See [action.rs](../crates/dodge-core/src/action.rs#L19).
- **Reproducibility tools.** Snapshots carry state/pixel hashes, core schema and cartridge provenance, plus a versioned wire encoding. Viewer replay checks frame and hash consistency. See [snapshot.rs](../crates/dodge-core/src/snapshot.rs#L420) and [viewer/lib.rs](../crates/dodge-viewer/src/lib.rs#L198).
- **Original game workspace.** The reviewed game revision contains `dodge-core`, `dodge-native-runner`, and `dodge-viewer`; its original README excluded training adapters, RL code, and datasets. The new `learning/` companion is separate from that workspace. Existing action comments do not establish that the original Python collector or DQN is present. See [Cargo.toml](../Cargo.toml) and [README.md](../README.md).

The first implementation uses `learning/` as an independently packaged companion inside this checkout, excluded from the normal game Cargo workspace. Its Rust/Python dependencies and virtual environment remain separate. This keeps the new adapter reviewable beside the core without importing the original RL project. Generated datasets/checkpoints remain outside version control. No older companion checkout was available at the two conventional local paths checked during the source review.

## Code-level issues the adapter must handle

### Episode startup and reset

New instances begin in Menu. Existing source tests show X startup reaches Game on native frame 13. Construct a fresh `NativeGame` for each episode seed and configuration; press X once, release it, and advance until `game_ready && mode == Game && !dead`, with a bounded startup timeout. Use the last returned snapshot as the initial observation. Exclude startup from agent rewards and episode length. See [startup tests](../crates/dodge-core/src/game.rs#L2230).

Do not assume `reset()` or the in-game retry is an independent fresh episode. `reset()` reuses the configured seed and leaves fields such as `has_played`, settings state, and highscores intact. Gameplay retry also preserves pattern counters and continues the RNG stream. Fresh construction avoids cross-episode state leakage. See [reset](../crates/dodge-core/src/game.rs#L239) and [restart_gameplay](../crates/dodge-core/src/game.rs#L721).

### Reward, action duration, and termination

The existing reward is `1` for a frame that began in Game and ended alive, otherwise `0`. It is not the displayed score. Use survival reward unchanged for the initial experiment, and log score separately. Death has no additional negative reward. See [reward calculation](../crates/dodge-core/src/game.rs#L460).

Start with action repeat `1`. `NativeGame::step(action, frames)` returns only the last frame's reward and events. Any later action-repeat wrapper must call `advance_frame` repeatedly, sum rewards, retain events, record actual elapsed frames, and stop on first death or at the remaining episode frame limit. Keep undiscounted reward sums for reporting. If training uses per-native-frame discount `gamma`, discount rewards within each repeat and use `gamma^elapsed_native_frames` for value bootstrapping. See [step](../crates/dodge-core/src/game.rs#L503).

Use `FrameResult.done` for death termination. Death does not require the mode to become Terminal. Reject agent steps after termination or truncation until reset. Keep a separate `truncated` flag for adapter time limits, and preserve the final observation for correct value bootstrapping. If death coincides with the time limit, termination takes precedence: set `terminated = true`, `truncated = false`, and do not bootstrap. See [result construction](../crates/dodge-core/src/game.rs#L1878) and [mark_dead](../crates/dodge-core/src/lifecycle.rs#L69).

### Observation timing and simulation fidelity

Use `FrameResult.snapshot` consistently for the observation and teacher features. The frame pipeline captures rendered pixels, applies draw-side changes, and constructs the returned snapshot. An extra player-trail mutation can occur after that capture on the startup transition. A later `game.snapshot()` is not a safe replacement for the returned observation. See [frame boundary](../crates/dodge-core/src/game.rs#L466).

Keep full frame execution during teacher training, including raster and draw-side work. Camera updates and some particle effects consume RNG. Skipping them changes future gameplay, even without opening a window. See [draw-side effects](../crates/dodge-core/src/game.rs#L1794) and [camera update](../crates/dodge-core/src/game.rs#L1852).

Player appearance comes from trails rather than a direct draw of `state.player`. Trails are added after capture, so visible position can lag current logical position. Exact velocities and hidden timers also cannot be read from a single image. Use image history and define capture timing before adding position or velocity supervision. See [render_game](../crates/dodge-core/src/snapshot.rs#L913) and [add_player_trail](../crates/dodge-core/src/game.rs#L1844).

Observation snapshots and resumable simulator checkpoints need distinct contracts. A checkpoint for continuation should come from live state after the call returns; do not substitute it for recorded pixels. The existing restore test covers an ordinary gameplay boundary, not every transition. Add a transition-boundary continuation check before relying on checkpoint-based dataset regeneration. See [restore test](../crates/dodge-core/src/game.rs#L2689).

### Existing executables

The CLI runner reads a full action schedule, executes it, buffers all frames, and writes JSON at the end. Its startup schedule forces 13 X frames and ignores the first command's supplied duration. Retain it for replay/debugging rather than launching it for each learner action. See [runner](../crates/dodge-native-runner/src/main.rs#L90) and [schedule expansion](../crates/dodge-native-runner/src/main.rs#L247).

The live viewer advances once per graphics loop; its elapsed-time 60 Hz accumulator applies to trace playback. Use native-frame counts as the training clock. Treat 60 frames per second as a nominal reporting convention, and measure real deployment timing separately. See [viewer loop](../crates/dodge-viewer/src/main.rs#L72).

## Proposed environment and data contracts

The implemented adapter follows this conceptual contract; constructor settings and literal Python signatures are documented in the companion README:

```text
reset(seed, config)
    -> pixels, privileged_state, train_only_state, info

step(action_id)
    -> pixels, privileged_state, train_only_state, reward_sum,
       terminated, truncated, info

student.act(pixel_history)
    -> action_id
```

`pixels` contains only the indexed image, converted through the exact RGB palette to grayscale for the ViT. `privileged_state` follows the entity-teacher schema; `train_only_state` preserves the filtered legacy baseline schema. `info` carries frame IDs, actual elapsed native frames, score, survival frames, events, hashes, and provenance. The deployed student receives only pixel history. Reset orchestration and termination handling belong to the host.

For each decision, record:

```text
episode_id, decision_id, observation_frame_id
image_t, teacher_distribution_t, teacher_latent_t, projected_teacher_attention_t, executed_action_t
reward_t, image_t_plus_1, terminated, truncated, elapsed_native_frames
```

Query the teacher on the state paired with `image_t` before executing the action. Do not label `image_t` with a policy decision taken after that action. Teacher queries must not advance or mutate the environment. Keep privileged features and diagnostic metadata in a separate training record; the student loader must select only images and teacher targets.

Store raw indexed frames once in bounded binary chunks and form history windows during loading. One million uncompressed indexed frames require about 15.3 GiB; RGB triples that cost. Avoid duplicated four-frame stacks or per-frame JSON snapshot hex in the training hot path. Start with a bounded pilot and measure compression, throughput, queue size, and disk use before expanding collection.

Record the game commit, cartridge hash, core schema, snapshot wire version, adapter/feature schema, action order, configuration, preprocessing, action repeat, seed manifests, trainer version, hyperparameters, and checkpoint hashes. At the reviewed revision, the core schema is `1` and snapshot wire version is `7`. Full snapshots should be sparse debugging/checkpoint artifacts, with their boundary recorded explicitly.

## Model and learning design

### Teacher: omniscient entity transformer

Use categorical PPO over the existing nine actions. Project typed engine entities to width 128, then learn threat attention and a 128-dimensional latent shared by policy/value heads. Player-query cross-attention avoids a quadratic matrix over the complete catalog. Entity features and padding masks preserve every record; exceeding the explicit capacity raises an error.

The versioned `privileged_state` projection includes all enemies, offscreen geometry, active/inactive patterns, queued targets and spawns, hidden timers, RNG, particles, settings, and render metadata. Actor and critic receive that privileged projection. Visibility controls only projection of attention targets onto student image patches, never teacher input selection.

The earlier filtered `train_only_state` projection and MLP remain explicit legacy baselines. They do not define the primary architecture. Full privileged access can produce decisions that an image history cannot reproduce; measure this gap rather than silently restricting the teacher. Privileged access alone does not establish an optimal policy.

Compare neutral and random policies with a simple state-based avoidance heuristic before PPO. Require the teacher to beat these baselines on validation seeds and survive complete active patterns before collecting a large imitation dataset. Use the quantitative teacher gate below. Train multiple seeds and retain failures; privileged access alone does not establish competence.

### Student: compact ViT, with a CNN comparison baseline

The user's preferred main student is a compact Vision Transformer (ViT). Keep the implemented CNN as a comparison baseline. No experiment has established which architecture learns or plays better here; the CNN was selected initially for low-cost iteration and its local spatial bias. Distillation does not require the student to have fewer parameters than the state teacher.

The diagram's default student uses four consecutive grayscale frames at native 128×128 resolution, shaped `[B, 4, 128, 128]`. Compute luminance from the exact RGB palette, normalize to `[0, 1]`, and repeat the first observation after reset. Never mix episodes. An 8×8 spatial grid has 64 tokens and requires 16×16-pixel patches. Literal 8×8 and 4×4-pixel patches remain comparison settings. The legacy CNN retains its four-frame RGB/12-channel input; preprocessing differs and must be accounted for in comparisons.

The ViT defaults to width 128, four heads, four pre-normalized blocks, MLP ratio 2, learned spatial positions, and learned attention pooling. It exposes latent and patch attention alongside nine categorical logits during training. The CNN baseline retains its original architecture. Synthetic gradient checks establish operation support, not gameplay quality; legacy ViT receipts describe an earlier RGB architecture.

Keep palette conversion identical in training and deployment. Its constants currently live in the viewer crate; share the palette through a small graphics-independent boundary or copy it into a versioned bridge with an exact-equivalence check. Do not add a Macroquad/window dependency to the learner solely to obtain RGB values.

Freeze the teacher and use all three loss bridges:

```text
L_distill = lambda_action * T^2 * KL(teacher_policy(T) || student_policy(T))
          + lambda_latent * MSE(normalize(z_student), normalize(z_teacher))
          + lambda_attn * KL(project(teacher_entity_attention) || student_patch_attention)
```

Detach all teacher targets. Begin with `T = 1` and each loss weight 1; record weights and ablations. Project entity attention by visible area overlap onto the patch grid, renormalize representable mass, and skip only attention loss for rows without a visible target. Keep valid-row counts. Preserve soft policy probabilities rather than only chosen actions.

Then use DAgger-style collection: let the student control training episodes, query the teacher on those visited states, add the image/teacher pairs, and retrain. Limit rounds and dataset size explicitly. Validation and test seeds must never enter this collection. This addresses drift away from teacher trajectories; offline action accuracy alone is insufficient.

If four frames prove inadequate, compare longer visual history or recurrent visual memory with episode-local resets. Latent and spatial-attention matching remain required parts of the primary architecture; controlled ablations measure their contribution.

Optional final stage: fine-tune the image actor using PPO with a privileged training-only critic. Export only the actor. This is a separate experiment because the critic can improve training without providing the deployed policy any additional observations.

### Corrections to the conceptual brief

- A privileged teacher need not be large, and its actions need not be optimal.
- Distillation cannot recover information absent from image history, including future RNG outcomes. Some teacher/student gap may be irreducible.
- Teacher supervision does not guarantee protection against shortcuts. Test theme, HUD, and timing dependence explicitly.
- Image conversion, history management, inference, and action dispatch all cost time. Measure latency before claiming real-time play.
- Measure each required loss bridge through controlled ablation. Hidden-state-dependent teacher representations may leave irreducible feature and policy errors.

## Local Mac target and initial budgets

The local hardware inventory reports a MacBook Pro (`Mac16,7`), Apple M4 Pro, 14 CPU cores (10 performance and 4 efficiency), 20 GPU cores, and 48 GB of memory. The host architecture is `arm64`. This inventory does not establish PyTorch MPS availability, operation support, or training speed. The 48 GB is shared system memory, not dedicated GPU memory.

- **Environment and teacher:** start on CPU with one environment. Benchmark 1, 4, and 8 CPU workers before selecting parallelism. Use spawned workers on macOS, limit each worker's numerical-library threads, and keep MPS work in the main learner process. Measure full-fidelity simulation throughput, bridge overhead, and memory rather than sizing workers from core count alone.
- **Student training:** start with the specified compact ViT and benchmark a bounded batch-size range before choosing throughput settings. Check PyTorch's MPS build/runtime availability, run finite-loss checks for all three bridges, and compare CPU/MPS. Record unsupported operations explicitly; do not hide them through automatic CPU fallback. CPU remains the supported development path.
- **Data:** retain the first collection pilot's limit of 10,000 native frames. Indexed images alone occupy about 156 MiB before compression and metadata. Start with a 2 GiB dataset cap, bounded prefetch queues, and at most 100,000 cached indexed frames. Stream later datasets and construct grayscale histories during batching. Stop collection cleanly at the storage cap.
- **Run budgets:** cap the first teacher smoke run at 100,000 native frames or 30 minutes, whichever comes first. Cap the first student fitting smoke run at 30 minutes. Evaluate these smoke runs on 10 dedicated smoke seeds, separate from validation and test. These are diagnostic budgets; they do not replace the teacher or student acceptance gates. Choose full training budgets after recording frames per second, optimizer throughput, peak memory, disk growth, and thermal behavior.
- **Local inference:** benchmark both CPU and MPS at batch size `1`. Warm up each backend, synchronize MPS timing, and measure conversion, history assembly, device transfers, inference, and action dispatch together. A small network may favor CPU even if MPS wins batched training. Use local end-to-end p50/p95 latency to choose the deployment backend.

Use a native arm64 Python environment and record Python, PyTorch, macOS, and backend versions with each run. Declare learner dependencies in the companion project's environment. CUDA and remote GPU training remain outside the initial implementation target. Reserve memory for the OS and other applications; use measured memory pressure to size caches and batches.

## Evaluation and acceptance gates

Freeze separate training, validation, and final test seed manifests before collecting data. Split entire episodes by seed, never adjacent frames. Seeds `0` and `1` generate equivalent RNG streams, so keep them in the same split or omit `0`; deduplicate any other detected equivalent streams. See [RNG initialization](../crates/dodge-core/src/rng.rs#L24).

Use difficulty `2`, patterns enabled, powerups enabled, and the default theme for the first benchmark, matching `NativeConfig::new`. A proposed initial episode cap is 18,000 agent-controlled native frames. Record cap hits as truncations rather than deaths; survival beyond the cap is censored. Freeze the cap before comparisons. Curriculum runs with disabled patterns or powerups must be reported separately and followed by the default benchmark.

Use 100 fixed validation seeds for selection and 100 distinct final test seeds after freezing the recipe. Compare at least three independent training runs for the final candidates. These counts are proposed budgets, not results. Keep final test data closed during iteration.

Report closed-loop mean, median, and tenth-percentile survival frames; mean displayed score; death and cap-hit rates; active-pattern encounters; and paired student/teacher survival ratios on the same initial seeds. Later trajectories can diverge with actions. Use paired confidence intervals over evaluation seeds and report between-run variation separately. Do not hide poor lower-tail performance behind a mean.

Provisional teacher gate: the paired 95% confidence interval for mean survival improvement over the best nonlearned baseline must have a positive lower bound, and at least 25 of the 100 validation episodes must survive one complete active pattern. Count completion when a valid active pattern ends naturally while the player remains alive, rather than counting `PatternActive` frames. Record pattern identity and exposure as well. See [pattern completion](../crates/dodge-core/src/game.rs#L1767). Freeze this gate before training; any later revision needs a recorded reason.

Compare neutral, random, heuristic, state teacher, direct pixel PPO, initial distilled student, and DAgger student. Match the direct-pixel baseline's actor, episode rules, and deployment inputs. Account separately for teacher-training frames, teacher queries, collection frames, student optimization, wall time, and peak memory. Report total training cost as well as student-only cost.

Provisional student target: at least 90% of teacher mean capped survival and 80% of teacher tenth-percentile capped survival, plus improvement over the best nonlearned baseline. Fix these thresholds before the first measured run; revise them only with a recorded reason. Report confidence intervals and raw values alongside ratios. If the teacher fails its baseline gate or a denominator is zero, the ratio is not a usable success claim. Distillation efficiency versus direct pixel PPO remains a separate measured outcome.

Run separate generalization evaluations across supported difficulties, patterns/powerups settings, and themes. Hold out some themes from training. Use an intentional HUD-mask ablation to measure score dependence. Do not call a failure under a changed configuration a default-benchmark result.

Verify the exported policy accepts only the image tensor and produces nine logits. For identical image history, changing privileged metadata must not change the action distribution. During fine-tuning, keep the privileged critic outside the actor's forward pass. Measure observation conversion, inference, and action-dispatch p50/p95 latency on the local Mac before choosing an action rate. Full training budgets remain provisional pending the local throughput pilot.

Deployment must pass the survival gates with its actual action repeat, image-history spacing, and delayed or dropped-frame behavior. Repeat-1 results do not qualify a slower control loop. Re-evaluate any cadence change and retrain if required before claiming deployment readiness.

## Implementation sequence

1. **Environment contract and baseline harness.** Add a companion learner package and an optional persistent Rust/Python bridge around `dodge-core`, pinned to this game revision. Start with one environment and one native frame per step. Implement fresh seeded startup, action validation, separate training state, reward/termination/truncation, frame history, and a bounded evaluation CLI. Add focused tests for seed replay, startup, action order, reward accumulation, mid-repeat death, time-limit bootstrapping, palette conversion, history reset, and observation/checkpoint boundaries. Gate: fixed-seed traces match direct core execution in state and pixel hashes.
2. **Throughput pilot and nonlearned baselines.** On the local Mac, measure full-fidelity frame execution with 1, 4, and 8 CPU workers, bridge overhead, CPU/MPS student performance, and dataset storage. Run a bounded collection pilot of at most 10,000 frames before choosing worker count or a large budget. Gate: deterministic replay, bounded memory/disk use, and reproducible neutral/random/heuristic results.
3. **Entity-transformer teacher.** Implement the unfiltered privileged projection, entity attention, and PPO. Log per-seed survival and pattern coverage. Gate: teacher clears validation baselines with reported uncertainty. Do not launch large student collection if it fails.
4. **Initial vision student.** Implement the preferred compact ViT, collect paired image/distribution data, fit it, and compare closed-loop play with the CNN baseline. Gate: image-only input audit passes, all nine actions remain correctly mapped, and survival improves over nonlearned baselines. Keep offline loss as a diagnostic.
5. **Student-visited collection and controlled alternatives.** Run bounded DAgger rounds. Compare direct pixel PPO, longer visual memory if needed, and optional asymmetric PPO fine-tuning. Gate: validation meets the frozen student target or failures have a concrete observability/teacher/data diagnosis.
6. **Final evaluation and deployment.** Freeze the recipe, run final held-out evaluation, export actor weights plus preprocessing/action manifests, and integrate in-process control or a persistent bridge. Keep menu/reset handling outside the model. Gate: held-out metrics, reproducible replay, input isolation, and measured deployment latency are recorded together.

The implemented learner uses an in-process PyO3/maturin extension and optional Python/PyTorch dependencies in its standalone companion. CPU smoke runs remain available; MPS has been exercised for the ViT. Record hardware/backend for each workload. Parallel environments and larger training budgets still require measured justification.

## Scope and verification of this review

The original documentation change preserved the supplied Markdown verbatim and added this plan. The authorized implementation adds the standalone learning companion and excludes it from the root game workspace. No core gameplay source or game dependency changed. Teacher training is implemented and piloted; a teacher that clears qualification, closed-loop student learning, and deployment benchmarking remain outstanding.

The initial review used source inspection, independent core and renderer reviews, and read-only hardware inventory. Its default toolchain probes failed because rustup attempted to write under sandbox-restricted `/Users/taylor/.rustup/tmp`. Implementation validation subsequently used the installed Rust 1.98.1 toolchain explicitly. Final companion checks pass 13 native tests, 32 Python tests, Clippy, and formatting. The earlier 56 game tests passed and their source remains unchanged. This qualifies the parent-recorded runs on Rust 1.98.1; the original game toolchain pin was not changed by the implementation.

The 323,625-parameter CNN passed bounded synthetic forward/backward checks on CPU and MPS with PyTorch 2.14.1 and Python 3.12.15. MPS required execution outside the sandbox; the sandboxed process reported it unavailable. These checks establish backend operation, not a trained policy or a deployment latency result.

A repeat-1 baseline pilot used seeds 42, 43, and 74 with a 1,000-frame cap and executed 4,313 agent frames in total. Mean capped survival was 187 frames for neutral, about 248.7 for random, and 1,000 for avoidance. All three avoidance episodes hit the cap; one survived a complete active pattern. These are smoke results on three seeds, not the 100-seed teacher acceptance gate. Machine-readable receipts are retained locally under `learning/runs/implementation-smoke/`, outside version control.

The copied attachment remains byte-identical and document links were checked locally. Free OpenCode reviewers run in full-access mode. Beam returned no findings on the initial snapshot. DeepSeek prompted per-pattern diagnostics, consistent current-result retrieval, stricter numeric validation, and an image-only accessor. Regressions are covered by focused tests, including a real native pattern completion. Its claim that transition-boundary restore lacked a test was unsupported by the existing test.

DeepSeek's follow-up verified its repaired snapshot and found no High/Medium regressions. Its remaining oversized-discount exception finding was reproduced and fixed with a range-check ordering change and positive/negative regression cases.

MiMo's moving-pattern lethality and worktree-provenance findings were validated and repaired. Feature schema `2` records the corrected lethality semantics. Provenance invalidation is covered by isolated Git/worktree fixtures, including metadata-only commits, dirty source transitions, packed refs, detached HEAD, and cached unchanged builds. Its proposed camera-bound change was rejected because it confused physical framebuffer coordinates with the canonical student image. All first-milestone reviews are complete and findings are reconciled; later repairs were validated by the parent and regression tests, rather than inheriting earlier snapshot verdicts. Those reviews cover the CNN scaffold and adapter; the second milestone has a separate review round.

### Second milestone evidence

The second milestone implemented the earlier RGB ViT, masked MLP state encoder/actor/critic, bounded PPO loop, checkpoint format, fixed seed manifest, shared evaluation deadlines, and qualification gate. At that milestone, 101 Python tests passed. A separate native audit found that semantic version matching alone could miss an incompatible binary rebuild; evaluation compares exact native extension, encoder, and wrapper hashes. Missing fingerprints allow diagnostics but cannot qualify a teacher.

MiMo exposed qualification using an arbitrary structurally valid checkpoint manifest, and DeepSeek exposed qualification of non-default curriculum configurations under the default benchmark label. Both formal entry points now pin the exact frozen four-split manifest and exact default configuration before episodes or calculations. Direct-report and saved-checkpoint regressions cover the repairs. Both actual pilots used the correct recipe and configuration. All second-milestone reviews are complete and reconciled; later code changes were validated by the parent and tests, without transferring the earlier snapshot's verdict.

The 10,000-frame and 100,000-frame runs used the same hyperparameters and training initialization, with no tuning between them. Each started fresh; their total training cost is 110,000 frames. The larger run collected exactly 100,000 frames, performed 391 updates and 6,252 optimizer steps, left no frames unoptimized, and completed in 45.64 seconds on CPU.

On the ten held-out smoke seeds `2000..2009`, with a 1,000-frame cap, mean survival after the larger run was 198 frames for the teacher, 188.5 for neutral, 260.9 for random, and 1,000 for avoidance. The teacher encountered no active pattern; four avoidance episodes completed a pattern. This is inadequate smoke performance. The formal 100-validation-seed gate was not run, final test seeds were unused, and no student demonstrations were collected. Source-bound checkpoints, progress logs, and comparison reports are retained in the local run directories described in [teacher usage](../learning/TEACHER.md).
