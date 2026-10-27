# Privileged teacher and visual ViT implementation plan

## Authority and scope

The user's intended plan is the final, revised v2.0 specification in the [supplied six-turn conversation](Branch-DQN-vs-PPO-Explained-Google-Gemini.md), extracted as [SPEC_PRIVILEGED_VIT_RL.md](SPEC_PRIVILEGED_VIT_RL.md). The [raw export](Branch-DQN-vs-PPO-Explained-Google-Gemini.json) is preserved byte-for-byte with SHA256 `53a6c21657c59db35c80137519a186cd5b850ccad7b76666fa3407de43182c65`.

This replaces the earlier conceptual brief, diagram interpretation, and implementation plan. Existing `learning/` checkpoints and tests remain historical diagnostics. Survival-only rewards, clairvoyant full-catalog observations, heuristic-imitation teacher training, player-query-only attention, grayscale inputs, and always-enabled distillation bridges do not satisfy v2. Their results do not qualify a new teacher.

Execution remains local Mac first. The user authorized proceeding without further confirmation and continuing overnight. Teacher training waits for the engine and vectorized environment milestones. Student implementation and training wait for a capable teacher.

## Required direction

- Train a typed entity transformer with two full self-attention layers, width 128, four heads, and two-layer actor/critic heads. Input contracts are 14 global scalars and 16 entity scalars plus a type ID. Initial capacities are 64 enemy-family records and 16 active rectangles, subject to measured overflow evidence.
- Expose a non-clairvoyant feature allowlist. Exclude RNG, scheduling timers, inactive pattern catalogs, queued future targets, and the internal anti-camping counter. Use type-correct AABBs, motion/growth, signed gaps, slab overlap time, and current visible charging state.
- Train with on-policy PPO and the difficulty/pattern curriculum. Reward is accumulated score delta plus `0.01` per alive raw frame, minus `5` once on death. Score and survival both matter; the scripted policy is an evaluation baseline.
- Use action repeat `K=4` by default, aggregating all executed frames. Build the headless path and borrowed accessors before vectorizing. Preserve RNG and legacy runtime behavior.
- Later, use categorical palette embeddings, four K-spaced frames, an 8-pixel convolutional patch stem, and 256 visual tokens. Begin with action-KL DAgger, add five-channel AABB occupancy targets, and retain latent/attention transfer only after controlled ablations.

## Milestones and acceptance evidence

| Milestone | Work | Required evidence |
| --- | --- | --- |
| 0 | Profile the existing engine; define reproducible random, neutral, and safe-powerup-seeking AABB baselines | Full source identity, measured single/multithread throughput; 1,000 episodes per policy with score/survival distributions, truncation counts, and active entity maxima |
| 1 | Shared deterministic stepping, `advance_frame_headless`, on-demand rendering, borrowed `PrivilegedView` | 100 seeds × 2,000 frames of live logical-state/RNG equivalence, targeted mechanics fixtures, unchanged legacy parity, Rust tests/format/Clippy, measured speedup |
| 2 | `crates/dodge-rl-env`, fresh-seed resets, K-frame aggregation, allowlisted AABB/slab features, Rayon/GIL release | Shape, geometry, hidden-state exclusion, episode boundaries, memory behavior, and headless/rendered throughput checks |
| 3 | Teacher full self-attention and curriculum PPO | Reproducible raw score/survival reports; clear improvement over the Milestone 0 heuristic at difficulties 2 and 3; gate fixed from measured baselines |
| 4 | Visual student and staged DAgger/occupancy supervision | Pure-visual score/survival evaluation after the teacher gate |
| 5 | Latent/attention ablations and optional asymmetric PPO | Retain changes only when visual performance improves |
| 6 | Visual diagnostics and deployment measurements | Quantitative score/survival reports and explicit inference timing |

The example two-times-score gate and throughput figures in the conversation are targets, not measurements. Baseline episode limits and seeds must be fixed and logged before the long baseline campaign. The previous survival-only/25-pattern qualification rule is historical and will not govern v2.

## Source corrections resolved before implementation

1. `NativeConfig.seed` is `u32`; use reproducible fresh `u32` episode streams and log them. Do not narrow arbitrary `u64` values silently.
2. Four samples separated by K have `3K` raw frames between the oldest and newest image. At `K=4`, that is 12 frames or 200 ms. Four complete decision intervals are 16 frames.
3. The existing frame API renders before draw-side effects and returns those cached pixels with later logical state. Preserve that legacy capture contract. The new `render_into` contract renders the current post-method state, after draw-side effects, input finalization, and transition-only trail insertion. Pair new features with that same state. The two pixel boundaries are intentionally different and must be tested.
4. Headless state parity compares live full state after each stepping method, excluding only `physical_screen`. Compare RNG checkpoints, input, particles, lifecycle, and all pattern state. Do not compare only the returned transition snapshot.
5. The survival bonus applies only to alive frames, including early termination within action repeat. Accumulate score changes on every executed frame and apply the death penalty once.
6. Native collision uses strict inequalities and type-specific offsets. Keep collision, inclusive raster extents, and half-open patch coverage conventions explicit. Slab overlap and charging-time features are approximations to future dynamics, not an exact collision oracle.
7. The 14- and 16-scalar lists in v2 are internally consistent. Preserve their dimensions.
8. Headless stepping can still allocate particles and clone active pattern state. A borrowed renderer may use fixed stack scratch and a canonical framebuffer copy. Measure throughput and allocations before claiming zero-copy or zero-allocation execution.

## Review and overnight execution

The [source-audit decisions](v2-source-audit.md) record additional score-accounting, charging/fading, visibility, seed ownership, and evaluation issues to resolve before vectorization and PPO. They qualify reviewer proposals where the original source supports a narrower claim.

Implement in bounded, reviewable changes. Run relevant checks, freeze source snapshots for free OpenCode adversarial review, and reconcile findings before long experiments. Use Opus for substantive design/diagnosis when useful, with parent validation against source. Parallel read-only review is allowed; avoid concurrent source mutation and benchmark/training in a shared checkout.

Preserve old artifacts and failed runs. Use isolated worktrees for a pre-change baseline harness so headless implementation cannot change the measured baseline source. No previous test count, source verdict, checkpoint score, or benchmark timing transfers to the new implementation.
