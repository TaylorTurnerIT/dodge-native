> Historical implementation and diagnostics: superseded by the user-supplied [v2.0 specification](../docs/SPEC_PRIVILEGED_VIT_RL.md). Retained for provenance; its objectives, feature contracts, architecture, and gates are not the current plan.

# Dodge learning companion

This optional package provides a persistent native environment, image preprocessing, baseline evaluation, a visual ViT student, and an omniscient entity-transformer PPO teacher. Action, latent, and spatial-attention losses implement the user-supplied [architecture](../docs/entity-transformer-architecture.md). The companion is excluded from the root Cargo workspace. The playable game keeps its existing dependencies and commands.

The companion lives in this checkout so the adapter and core can be reviewed together. It has a separate Rust workspace, Cargo lockfile, Python package, and virtual environment. Generated models, datasets, build outputs, and run receipts stay outside version control. The conceptual brief and full training design are in [docs](../docs/vision-model-training-plan.md).

## Local Mac setup

Use native arm64 Python 3.11 or newer. The companion pins Rust 1.98.1 independently of the game's toolchain. The first target is the local M4 Pro Mac; CPU support is required, while MPS is optional and checked at runtime.

From the repository root:

```sh
cd learning
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e .
```

Install the optional CNN dependencies when needed:

```sh
uv pip install --python .venv/bin/python -e '.[models]'
```

Builds use the local `dodge-core` source through PyO3/maturin. Reinstall the editable package after changing Rust code; Python source changes load directly. Importing `dodge_learning` does not load PyTorch or create a window. The baseline package has no runtime Python dependencies beyond the compiled extension.

## Environment

```python
from dodge_learning import NativeEnvironment
from dodge_learning.pixels import PixelHistory

with NativeEnvironment(seed=42, max_episode_frames=18_000) as env:
    observation = env.reset()
    history = PixelHistory(4)
    history.reset(env.student_observation(), observation["info"]["frame"])
    while not (observation["info"]["terminated"] or observation["info"]["truncated"]):
        observation = env.step(0)  # Neutral baseline; action IDs are 0 through 8.
        history.append(env.student_observation(), observation["info"]["frame"])
```

Each result contains:

- `pixels`: immutable 16,384-byte indexed image from the returned canonical core snapshot.
- `privileged_state`: schema-1 unfiltered structured engine records for the entity transformer, including offscreen entities, inactive patterns, queued targets, timers, RNG, and render state. Spatial flags select attention-target geometry only.
- `train_only_state`: a versioned actor projection containing the player, current visible hazards and pattern geometry, warnings, and current dynamics. It excludes seed, RNG, future targets, inactive patterns, score, hashes, and highscores. Coordinates use canonical game pixels. Exact state can still lead visible player trails; this projection is privileged.
- `info`: frame counts, termination flags, displayed and raw score, pattern identity/encounter/exposure/completion counters, events, hashes, seed, and build/configuration provenance. These diagnostics must never enter an image policy.
- `reward_sum`: undiscounted survival reward over actual executed native frames.
- `discounted_reward`: per-native-frame discounted reward within that decision interval.
- `bootstrap_discount`: `discount**elapsed_native_frames` while alive, including time-limit truncation; zero after death.

Teacher feature schema `2` corrects rectangle `solid` to mean player-lethal collision status: moving patterns are lethal throughout expansion, while static patterns require full expansion. The bridge records the schema version in provenance.

The constructor accepts seed, episode frame cap, action repeat, discount, difficulty, pattern/powerup switches, and palette theme indices. Reset constructs a fresh seeded game, starts it with X, releases X, and returns the ready frame. Startup does not count toward agent rewards or the frame cap. Death takes precedence when it coincides with the cap. After either terminal flag, call `reset` before another action.

`student_observation()` returns immutable indexed pixels directly from the native core without constructing privileged Python records. Use it to build the student's image history. The explicit training API still returns privileged features for the teacher and state baselines; the model itself accepts only an image tensor. This API boundary does not isolate arbitrary Python code that deliberately reads training state.

`current()` returns a fresh copy of the latest successful reset/step result, including that transition's rewards, elapsed frames, events, and bootstrap discount. Invalid actions, invalid resets, and steps after episode completion preserve the current result. Numeric settings and seeds reject booleans and invalid ranges with `ValueError`; the pattern/powerup switches require actual booleans.

Action IDs are neutral, left, right, up, down, up_left, up_right, down_left, down_right. Masks are `[0, 1, 2, 4, 8, 5, 6, 9, 10]`. X/O and menu handling stay outside the movement policy.

Use repeat `1` for the first experiment. The native adapter supports longer repeats and stops them at death or the episode cap, but returns only the final image for that interval. `PixelHistory` with frame IDs requires consecutive native frames and rejects skipped frames. Longer repeats therefore need a separately specified observation-history policy and fresh evaluation. The baseline CLI intentionally uses repeat `1`.

## Baselines and model diagnostic

Run bounded baseline evaluation without storing image datasets:

```sh
.venv/bin/python -m dodge_learning.evaluate --policy neutral --seeds 42,43 --max-frames 1000
.venv/bin/python -m dodge_learning.evaluate --policy random --seeds 42,43 --max-frames 1000
.venv/bin/python -m dodge_learning.evaluate --policy avoidance --seeds 42,43 --max-frames 1000
```

Use `--output PATH` to retain JSON. Parent directories must already exist. Each report includes per-seed outcomes and capped-survival summaries. The evaluator deduplicates seed `0`/`1` RNG aliases, limits seed count to 1,000 and episode length to 18,000 frames, and preserves death versus truncation. Timings include startup, the bridge, diagnostics, and policy work; they are not isolated native-engine or deployment benchmarks.

Each episode's `pattern_metrics` records cartridge pattern ID, encounters, exposed native frames, and live completions. Summary metrics aggregate by ID and in total. The encounter frame counts as exposure; a completion frame with no active pattern does not. Exposure is counted within every repeated native step. Missing metrics stay `null`, rather than becoming measured zeros. A completion count alone does not establish broad pattern coverage.

The avoidance baseline uses privileged current-state features and approximate short-horizon clearance. It is neither a learned teacher nor an optimal controller. Random actions use a private RNG. No baseline reads future pattern state or simulator RNG.

After installing the models extra, run a bounded synthetic optimization diagnostic:

```sh
.venv/bin/python -m dodge_learning.smoke --device cpu --steps 1 --batch-size 2
.venv/bin/python -m dodge_learning.smoke --device mps --steps 1 --batch-size 2
```

An explicit MPS request fails if unavailable or if automatic MPS-to-CPU fallback is enabled. The diagnostic reports finite loss, gradients, parameter count, and backend facts. It runs at most ten steps with batch size at most 64. It uses synthetic inputs and targets; it does not train a game-playing policy, measure teacher quality, save weights, or qualify deployment latency.

`VisionPolicy` consumes only floating-point image tensors shaped `[batch, 12, 128, 128]`. Feed `PixelHistory.rgb_chw()` in oldest-frame-first order, with each frame's RGB channels adjacent, reshaped to that tensor shape. `distillation_loss(student_logits, teacher_logits, temperature=1.0)` computes detached teacher-to-student KL. Teacher gradients never flow through this loss. The state PPO teacher and checkpoint pipeline are now implemented. A visual dataset collector, DAgger, and deployment controller remain future milestones.

The primary student is `ViTPolicy`. It consumes `[B, 4, 128, 128]` grayscale history from `PixelHistory.gray_chw()`, with default 16-pixel patches producing 64 tokens. Patch sizes 8 and 4 remain comparisons. Its learned patch attention pools the policy latent and receives spatial supervision. The RGB CNN remains a baseline with a different preprocessing contract. See [teacher and ViT usage](TEACHER.md) for commands, seed splits, checkpoint provenance, and qualification.

## Checks

From `learning`:

```sh
cargo test --manifest-path native/Cargo.toml --locked
cargo clippy --manifest-path native/Cargo.toml --locked --all-targets --features python -- -D warnings
cargo fmt --manifest-path native/Cargo.toml -- --check
.venv/bin/python -m unittest discover -s tests -v
```

Native tests compare the adapter with direct core execution, including canonical startup versus live continuation, all action IDs, fresh resets, accumulated rewards/events, native-frame discounts, mid-repeat death/caps, and death-at-cap precedence. Python tests cover the installed bridge, JSON reports, palette equivalence, history isolation, baseline bounds, CNN gradients, and teacher-gradient isolation. Model tests skip in a baseline-only installation; native integration tests skip when the extension is not built.

Large training runs remain gated on a measured teacher that beats the nonlearned baselines. Local full-fidelity throughput, worker counts, CPU/MPS performance, and memory budgets still require the pilot described in the design.

## Historical validation and reviews

The first milestone passed 13 native tests and 32 Python tests using Rust 1.98.1 and Python 3.12.15. Companion Clippy and formatting passed. The earlier 56 original game tests passed with the same toolchain; their source remains unchanged. The untrained 323,625-parameter CNN completed finite synthetic forward/backward checks on CPU and MPS with PyTorch 2.14.1 before these adapter repairs; the model code is unchanged. The MPS check required access outside the agent sandbox. Local smoke receipts are in `runs/implementation-smoke/`, with repair diagnostics in `runs/review-repairs/`; their timings are diagnostics rather than deployment benchmarks.

Beam returned no findings on the initial frozen implementation. DeepSeek identified missing pattern diagnostics and inconsistent `current()`/numeric-input behavior; these were repaired with regression tests. Its student-input concern prompted the direct pixels-only accessor; no automatic metadata leak through the tensor-only model was demonstrated. Its claimed missing transition-boundary restore test was already covered.

DeepSeek's follow-up verified its repaired snapshot and found no High/Medium regressions. Its remaining oversized-discount exception issue was reproduced and fixed with a range-check ordering change and positive/negative regression cases.

MiMo identified an incorrect moving-pattern lethality flag and stale build provenance in linked worktrees. Both were fixed and tested. Build invalidation now watches resolved Git HEAD, index, packed refs, and the current symbolic branch, plus game source inputs. Isolated fixture tests cover unchanged cached builds, empty commits, dirty-to-committed source transitions, packed refs, detached HEAD, and non-Git exports without changing this repository's history.

MiMo's camera-bound finding was rejected: it described the physical framebuffer, while the student receives the canonical `pget` projection. That projection preserves the world-coordinate bounds used by the existing filter. All requested review tasks have finished and their findings have been reconciled. Review verdicts apply to their recorded snapshots; later repairs were checked by the parent and the listed regression tests.

The second milestone adds PPO/ViT/encoder/checkpoint/gate tests; 101 Python tests pass. A native audit prompted exact native-binary, encoder, and wrapper fingerprint checks before checkpoint evaluation. MiMo found that replacement seed manifests could bypass the frozen recipe, and DeepSeek found that curriculum configurations could qualify under the default benchmark label. Both formal paths now pin the complete seed recipe and exact default configuration, with direct-report and saved-checkpoint regressions. The existing pilots used the correct recipe and configuration. Both second-milestone reviews are complete; later fixes were checked by the parent and tests.

Two legacy MLP pilots used 10,000 and 100,000 training frames. The 100,000-frame run completed in about 46 seconds on CPU. On ten held-out smoke seeds capped at 1,000 frames, its mean survival was 198 frames; random reached 260.9, and avoidance hit the cap on every seed. The MLP encountered no active patterns. These results do not measure the corrected entity transformer. Formal qualification was not run, and large student collection remains blocked. Legacy receipts remain under `runs/teacher-pilot-10000/`, `runs/teacher-pilot-100000/`, and `runs/milestone2-smoke/`.

## Architecture correction

At the entity-transformer/ViT correction milestone, 134 Python tests, 19 native tests, Clippy, and rustfmt passed. Paired native-frame diagnostics passed on CPU and MPS with all three losses, finite student gradients, no teacher gradients, and zero student optimizer steps. The entity teacher's separate 1,000-frame PPO pilot was not qualified. See [diagnostics](TEACHER.md#corrected-architecture-diagnostics) and `runs/entity-architecture-validation/` for that evidence.

Current work is teacher-only. PPO stabilization, caching, teacher controls, strict weights-only continuation, and bounded heuristic warmup bring the Python suite to 152 tests. Neither the 10,000-frame PPO run nor the two 10,000-frame warmups produced a capable teacher. A 100,000-frame PPO continuation uses the weighted warmup checkpoint under an explicit time cap. Beam's Boolean-flag and training-source checks were reproduced and fixed. Stalled broad reviews were cancelled; a focused MiMo teacher review is pending. Student work remains deferred. See [teacher-first experiments](TEACHER.md#teacher-first-training-experiments).
