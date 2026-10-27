# `SPEC_PRIVILEGED_VIT_RL.md` (v2.0 — Source-Verified Specification)

## 1. Executive Summary & Architectural Overview

### 1.1 Goal
Train a superhuman **visual-only agent** for `dodge-native` (`d7ad951`, a deterministic Rust port of the PICO-8 game `dodge.p8`) that plays purely from stacked $128 \times 128$ palette-indexed frames while maximizing **game score** (the true highscore metric) alongside survival.

### 1.2 Two-Stage Privileged-to-Visual Architecture

1. **Stage 1 — Privileged Entity-Transformer Teacher (PPO):**
  - Operates on a newly added **headless stepping path** in `dodge-core` that bypasses framebuffer rendering and `FullState` snapshot clones while strictly preserving RNG parity (`apply_draw_side_effects`).
  - Models the game as a set of **Typed Box Entities** (`Global/Player`, `Enemy`, `Kamikaze`, `Explosion`, `Powerup-{Explode, Freeze, Shrink}`, `Static-Rect`, `Moving-Rect`) using exact axis-aligned bounding box (AABB) Minkowski gaps and slab time-to-overlap—**strictly excluding clairvoyant hidden timers** (`pattern_timer`, `enemy_timer`, RNG state) so the Teacher only uses facts inferable from a short visual history.
  - Trains via a built-in curriculum (`difficulty` $1 \to 3$, `patterns_enabled`, `powerups_enabled`) optimizing **$\Delta\text{score}$** plus a small survival term.
2. **Stage 2 — Visual ViT Student (DAgger + Multi-Channel Box Rasterization):**
  - Operates strictly on 4 action-repeat-spaced $128 \times 128$ frames of categorical PICO-8 palette indices (`0..15`) embedded via `nn.Embedding(16, C)`.
  - Trains first with a clean baseline of **Action-KL DAgger**, then adds dense **16×16 Rasterized Spatial Auxiliary Targets** (`lethal_now`, `lethal_soon`, `enemy`, `powerup`, `player` per-patch BCE head) computed directly from exact entity boxes—avoiding point-splat distortion on $127\text{px}$ pattern walls.
  - Evaluates **Latent Alignment ($L_{\text{latent}}$)** and **Custom-Layer Attention Transfer ($L_{\text{attn}}$)** as controlled ablations, followed by optional Stage 2.5 Asymmetric PPO fine-tuning (Visual Student Actor + Privileged Teacher Critic).

## 2. Verified Engine Mechanics & Constraints (`dodge-core`)
All implementation work in Rust and Python must obey these exact source-verified mechanics:

| Domain | Source-Verified Behavior | Architectural Consequence |
| --- | --- | --- |
| **Timebase** | `_update60` (60 FPS). | Use **Action Repeat $K \in [2, 4]$** (default $K=4 \implies 15\text{ Hz}$ decisions). Space the Student's 4-frame stack by $K$ (covering $16$ raw frames $\approx 267\text{ ms}$) so velocity is visually observable. Set $\gamma = 0.995$ per *decision step* ($\approx 800$ raw frames / $13.3\text{s}$ horizon). |
| **Player Physics** | Momentum: $v \leftarrow 0.8v \pm 0.5$ per held axis (`PLAYER_FRICTION`, `PLAYER_SPEED`). Terminal speed: $2.5\text{ px/frame}$ cardinal, $\approx 3.5\text{ px/frame}$ diagonal (unnormalized). Time constant $\approx 5$ frames. Clamped to $[2, 125]$. | No artificial action-jitter penalty needed; momentum + action repeat naturally smooth motion. |
| **Action Space** | 9 actions in `action.rs` locked by `action_order_and_masks_match_training_contract`. `O` and `X` only act on menu/retry screens. | Policy outputs logits over the **9 directional/button actions** (or masks `O`/`X` during `Mode::Game`). |
| **True Objective & Score** | Score does **not** rise with time. $+0.5$ when an enemy dies (two enemies collide or crushed by a pattern). $+1.0$ for freeze/shrink powerup. $+1.0$ per enemy cleared by explode powerup. Every score increment calls `apply_difficulty` (`spd` $\to 3$, `est` $\to 0.22\text{s}$, tighter bounce caps). | **Never reward survival alone** (a survival-only agent avoids scoring to keep difficulty low). Reward must center on $\Delta\text{score}$. |
| **Built-in Anti-Camping** | Staying inside the central $8 \times 8$ box for $>50$ frames triggers `update_fyou` (spawns 4 enemies). New enemies spawn at `nearest_corner` to the player. | **Do not add artificial center-bias or wall penalties.** Let the agent learn the native mechanics. |
| **Rendering Location** | Rendering lives in `dodge-core/src/snapshot.rs` (`render_full_state_into`). `dodge-viewer` is just a `macroquad` window + PGM/PPM export + `PICO8_PALETTE`. | `dodge-rl-env` must only depend on `dodge-core`. Do not link `dodge-viewer` (avoids pulling in `macroquad`/X11/GL). |
| **Current Step Cost** | `advance_frame` renders the $128 \times 128$ screen and builds a `Snapshot` ($\sim 3$ `FullState` deep clones including nested pattern `Vec`s + multiple $16\text{ KB}$ framebuffer copies) every frame. `step(action, frames)` drops intermediate `FrameResult` rewards/events. | Must add `advance_frame_headless(mask)` and `render_into(&mut [u8; 16384])` in `dodge-core`, and manually accumulate rewards/events across action-repeat frames. |
| **RNG & Reset Parity** | `reset()` reseeds from private `config.seed` (replaying the identical run). `restart_gameplay` leaks pattern counters across runs. Camera shake (2 RNG calls) and `apply_draw_side_effects` (trail particles) consume RNG every frame. | Start each episode via `NativeGame::new(NativeConfig::new(random_seed))` + internal start sequence (`X` press + $\sim 13$ neutral frames until `Mode::Game`). Headless stepping **must** execute `apply_draw_side_effects`. |
| **Workspace Lints** | Root `Cargo.toml` & `.cargo/config.toml`: `unsafe_code = "forbid"`, `unwrap_used = "deny"`, `expect_used = "deny"`, `panic = "deny"`, `indexing_slicing = "deny"`, `-Dwarnings`. | `dodge-core` additions must strictly obey all lints. `crates/dodge-rl-env` must define its own `[lints]` table (not `workspace = true`) because PyO3 macros emit code that conflicts with `unsafe_code = "forbid"`. |

## 3. Typed Entity & AABB Geometry Specification
All entities in `dodge-native` use **Axis-Aligned Bounding Boxes (AABBs)** with type-specific hit offsets (`game.rs::collision_check`), and coordinates routinely travel off-screen (e.g., $-50, 131, 144$).

### 3.1 Entity Categories & Hitbox Rules
Let player position be $(p_x, p_y)$ and player size be $p_s$ (normally $4$, or $2$ during active shrink powerup for $\sim 600$ frames).

| `type_id` | Entity Category | Source Representation | Player Hitbox Used | Entity Box $[x_{\min}, x_{\max}] \times [y_{\min}, y_{\max}]$ | `beneficial` | `lethal_now` |
| --- | --- | --- | --- | --- | --- | --- |
| `0` | **Global / Player Token** | Player state + global scalars | $[p_x - p_s, p_x + p_s]$ | Self | `0.0` | `0.0` |
| `1` | **Normal Enemy** (`personality == 0`) | Top-left $(x, y)$, side $s \in [1, \text{max\_size} \in \{3..6\}]$ | $p \pm (p_s - 1)$ | $[x, x+s] \times [y, y+s]$ | `0.0` | `1.0` |
| `2` | **Kamikaze Enemy** (`personality == 1`) | Top-left $(x, y)$, side $s$; slows within $25\text{px}$ of player, spawns explosion on death | $p \pm (p_s - 1)$ | $[x, x+s] \times [y, y+s]$ | `0.0` | `1.0` |
| `3` | **Kamikaze Explosion** (`personality == -1`) | Centered at death pos, grows to $30\text{px}$ then shrinks (`life = 60` frames) | $p \pm (p_s - 1)$ | $[x, x+s] \times [y, y+s]$ | `0.0` | `1.0` |
| `4` | **Powerup: Explode** (`personality == 2`) | Center $(x, y)$, fixed $\pm 4$ box (trail colors `{8,9,10}`) | $p \pm p_s$ | $[x-4, x+4] \times [y-4, y+4]$ | `1.0` | `0.0` |
| `5` | **Powerup: Freeze** (`personality == 3`) | Center $(x, y)$, fixed $\pm 4$ box (trail `{1,13,7}`); sets `freeze_rate = 0.4` for $420$ frames | $p \pm p_s$ | $[x-4, x+4] \times [y-4, y+4]$ | `1.0` | `0.0` |
| `6` | **Powerup: Shrink** (`personality == 4`) | Center $(x, y)$, fixed $\pm 4$ box (trail `{7}`); sets player `size = 2` for $\sim 600$ frames | $p \pm p_s$ | $[x-4, x+4] \times [y-4, y+4]$ | `1.0` | `0.0` |
| `7` | **Static Pattern Rect** (`pattern_type == 0`) | Top-left $(x, y)$, $(w, h)$ up to $127\text{px}$; charges `sh` $0 \to 2$ at $0.02 \cdot \text{freeze\_rate}$/frame ($\sim 100$ frames), holds $510$ frames | $p \pm (p_s - 2)$ | $[x, x+w-1] \times [y, y+h-1]$ | `0.0` | `1.0` if `sh >= 2.0` else `0.0` |
| `8` | **Moving Pattern Rect** (`pattern_type == 1`) | Top-left $(x, y)$, $(w, h)$; starts off-screen, moves at $0.7\text{px/frame}$ or smooth exponential (`pattern 17`) | $p \pm (p_s - 2)$ | $[x, x+w-1] \times [y, y+h-1]$ | `0.0` | `1.0` |

### 3.2 Privileged (But Non-Clairvoyant) Token Features
**Strict Non-Clairvoyance Rule:** Do **not** include `pattern_timer`, `pattern_delay_frames`, `enemy_timer`, `fyou` internal counter, or `rng` state. Everything exposed to the Teacher must be visually observable or inferable from short frame history.

#### Token 0: Global & Player Token (`GLOBAL_FEAT_DIM = 14`)

1. `px_norm`, `py_norm`: $(p_x - 64.0) / 64.0$, $(p_y - 64.0) / 64.0$
2. `pvx_norm`, `pvy_norm`: $v_x / 2.5$, $v_y / 2.5$
3. `psize_norm`: $p_s / 4.0$ (`1.0` normal, `0.5` shrunk)
4. `freeze_rate`: `0.4` when frozen, `1.0` normal
5. `game_speed_norm`: `game.speed / 3.0` (visually observable via score / enemy speed)
6. `enemy_est_norm`: `enemy_est / 2.0` (difficulty spawn interval, tied deterministically to score)
7. `score_norm`: $\tanh(\text{score} / 50.0)$ (score is drawn in top-left 8 rows)
8. `pattern_active_flag`: `1.0` if an active pattern is visibly charging/moving, else `0.0`
9. `dist_left`, `dist_right`, `dist_top`, `dist_bottom`: Distance to the $[2, 125]$ player clamp walls divided by $123.0$.

#### Tokens $1 \dots (M_{\text{enemies}} + M_{\text{rects}})$: Entity Tokens (`ENTITY_FEAT_DIM = 16` + `type_id: u8`)
Separate buffers with explicit caps: `MAX_ENEMIES = 64` (verify in Milestone 0; if active count $> 64$, sort by `slab_tto` ascending, keep the 64 closest-in-time, and increment `overflow_counter`) and `MAX_RECTS = 16`.
For each active entity (enemy/explosion/powerup or pattern rect):

1. `cx_norm`, `cy_norm`: Box center squashed via $(c - 64.0) / 128.0$ (handles off-screen coordinates in $[-64, 192]$ cleanly without clipping).
2. `hx_norm`, `hy_norm`: Box half-extents $(w/2) / 64.0$, $(h/2) / 64.0$.
3. `rel_cx_norm`, `rel_cy_norm`: $(c_x - p_x) / 128.0$, $(c_y - p_y) / 128.0$.
4. `dx_frame`, `dy_frame`: True per-frame displacement divided by $4.0$:
  - **For enemies (`type_id` 1, 2):** Use the exact analytic formula $dx = v_x \cdot \text{game.speed} \cdot \text{freeze\_rate} \cdot \text{enemy.speed}$ (do **not** difference across frames because `Vec` swap/remove shifts indices).
  - **For pattern rects (`type_id` 7, 8):** Difference box center across consecutive frames (rect indices are stable within an active pattern) or compute directly from the active `Move` target.
5. `dw_frame`, `dh_frame`: Per-frame half-extent growth rate (captures growing `EnemyState` $1 \to \text{max\_size}$, growing/shrinking kamikaze explosions, and Pattern 17 smooth rect resizing).
6. `minkowski_gap_x`, `minkowski_gap_y`: Signed per-axis clearance between the player's type-specific hitbox $[p_{x,\min}, p_{x,\max}]$ and the entity box $[e_{x,\min}, e_{x,\max}]$ divided by $64.0$ (negative values mean currently overlapping on that axis).
7. `slab_tto_norm`: **2D Slab Time-To-Overlap** on the Minkowski-expanded box under constant relative per-frame velocity $(dx - p_{vx}, dy - p_{vy})$, clamped to $[0, 120]$ frames and divided by $120.0$.
  - Let $[t_{x,\text{enter}}, t_{x,\text{exit}}]$ and $[t_{y,\text{enter}}, t_{y,\text{exit}}]$ be the ray-slab intersection intervals along $X$ and $Y$.
  - Let $t_{\text{enter}} = \max(0.0, t_{x,\text{enter}}, t_{y,\text{enter}})$ and $t_{\text{exit}} = \min(t_{x,\text{exit}}, t_{y,\text{exit}})$.
  - If $t_{\text{enter}} \le t_{\text{exit}}$, then $\text{slab\_tto} = \min(120.0, t_{\text{enter}})$; else $120.0$.
8. `frames_until_lethal_norm`:
  - For static rects (`type_id == 7`) with $\text{sh} < 2.0$: $\min\left(120.0, \frac{2.0 - \text{sh}}{0.02 \cdot \text{freeze\_rate}}\right) / 120.0$.
  - For all currently lethal entities: `0.0`. For powerups: `1.0`.
9. `beneficial_flag`: `1.0` for powerups (`type_id` 4, 5, 6), `0.0` otherwise.
10. `lethal_now_flag`: `1.0` if touching this entity on this frame kills the player, `0.0` otherwise.

## 4. Engine Instrumentation & PyO3 Binding (`crates/dodge-core` & `crates/dodge-rl-env`)

### 4.1 Required Additions to `crates/dodge-core`
All changes in `dodge-core` must compile cleanly under `unsafe_code = "forbid"`, `unwrap_used = "deny"`, `expect_used = "deny"`, `panic = "deny"`, `indexing_slicing = "deny"`, and `-Dwarnings`.

1. **Move/Expose `PICO8_PALETTE` in `dodge-core`** (or copy the 16-entry RGB constant into `dodge-rl-env`) so `dodge-viewer` is never linked.
2. **Add `advance_frame_headless(&mut self, mask: u8) -> HeadlessResult`:**
  - Runs `update_active_pattern`, `update_player`, enemy/powerup updates, `update_fyou`, `update_camera`, and **must call `apply_draw_side_effects`** so trail particle RNG consumption remains bit-identical to `advance_frame`.
  - Skips `render_current_frame`, `Snapshot::from_game` (`FullState` clones), and `FrameResult` heap allocations.
  - Returns lightweight `HeadlessResult { reward: f32, score_delta: f32, score: f32, dead: bool, mode: Mode }`.
3. **Add `render_into(&mut self, out_buf: &mut [u8; 16384])`:**
  - Renders the post-remap $128 \times 128$ palette-indexed screen (`0..15`) on demand directly into a caller-supplied buffer.
  - **Boundary Rule:** Extract privileged features and call `render_into` at the exact same post-`apply_draw_side_effects` frame boundary.
4. **Add `PrivilegedView<'a>` Borrowed Accessor (`pub fn privileged_view(&'a self) -> PrivilegedView<'a>`):**
  - Exposes zero-copy borrowed references to player coordinates/velocity/size, `freeze_rate`, `speed`, `enemy_est`, `score`, `enemies: &[EnemyState]`, and active pattern rects (`pattern_type`, `sh`, rect slices) without calling `snapshot()`.

### 4.2 Vectorized Environment Crate (`crates/dodge-rl-env`)
Create a new crate `crates/dodge-rl-env` with its own `[lints]` section in `Cargo.toml` (`unsafe_code = "allow"` for PyO3 macro compatibility; keep `clippy::all = "warn"`).

- **Episode Initialization & Reset Contract:**
  - Maintain a per-worker master PRNG in `VecDodgeEnv`. On episode reset for env $i$, sample a fresh `u64` seed, construct `NativeGame::new(NativeConfig { seed, difficulty, patterns_enabled, powerups_enabled, .. })` (pinning the default theme `12/1`), and immediately step through the start sequence (`X` button press followed by neutral frames until `mode == Mode::Game`) before returning the initial observation.
  - Never call `game.reset()` or use in-game retry.
  - On `dead == true`, terminate the episode immediately and do **not** emit the Game Over screen into the Student's frame stack.
- **Action Repeat & Reward Aggregation:**
  - Step each environment for $K$ frames (default $K=4$) using `advance_frame_headless(action_mask)` (breaking early if `dead == true`).
  - Accumulate across the $k = 1 \dots K'$ frames actually stepped:$R_{\text{step}} = \sum_{k=1}^{K'} \left( \Delta\text{score}_k + c_{\text{surv}} \right) - 5.0 \cdot \mathbb{I}[\text{dead}]$where $c_{\text{surv}} = 0.01$ per alive frame ($\implies +0.04$ per 4-frame decision step), while a single enemy collision kill gives $+0.50$ and a powerup gives $+1.00$.
- **Student Frame Stack Spacing:**
  - When `render_pixels = true`, render 1 frame at the end of each $K$-frame decision step and push it into a 4-slot ring buffer per environment (`[B, 4, 128, 128]` `uint8` values in `0..15`). Thus, the 4 frames are spaced by $K$ raw frames ($4K = 16$ frames total span).
  - On episode start, fill all 4 slots with the initial `Mode::Game` frame.
- **Rayon Chunking & GIL Release:**
  - Wrap `step()` in `py.allow_threads(|| ...)`.
  - Because a single headless step takes only a few microseconds, use `envs.par_chunks_mut(chunk_size)` (e.g., `chunk_size = 8` or `16` envs per task) and run the entire $K$-frame loop + featurization inside the chunk to avoid Rayon fork/join overhead.
- **Snapshot Death-Recovery Buffer (Bonus Curriculum Accelerator):**
  - Maintain a small ring buffer of `Snapshot`s every 60 frames per env. Allow Python to sample a saved `Snapshot` from 60–120 frames before a death via `NativeGame::restore` to practice hard pattern survival scenarios.

## 5. Neural Architectures & Training Pipeline (`python/dodge_rl/`)

### 5.1 Stage 1: `OmniscientEntityTeacher` (`models/teacher.py`)

- **Inputs:**
  - `global_feats`: `[B, 1, 14]`
  - `entity_feats`: `[B, M, 16]` where $M = \text{MAX\_ENEMIES} + \text{MAX\_RECTS} = 64 + 16 = 80$
  - `entity_types`: `[B, M]` (`int64` in `1..8`)
  - `entity_mask`: `[B, M]` (`bool`, `True` = valid entity, `False` = padding)
- **Token Embedding (`d_model = 128`):**
  - Token `0`: `Linear(14, 128) + TypeEmbedding(0)`
  - Tokens `1..M`: `MLP(16 -> 128 -> 128) + TypeEmbedding(entity_types)`
- **Custom Pre-Norm Transformer Encoder (`2` Layers, `4` Heads):**
  - **Important:** Do **not** use stock `nn.TransformerEncoderLayer` (which calls `MultiheadAttention` with `need_weights=False` and triggers fused SDPA kernels that return `None` for attention weights).
  - Implement `CustomTransformerLayer` that explicitly calls `self.mha(x, x, x, key_padding_mask=pad_mask, need_weights=True, average_attn_weights=True)` so attention weights are always extractable for visualization and Stage 2 ablations.
  - Token `0` (`Global/Player`) is never masked in `pad_mask`, preventing `NaN`s when 0 entities are on screen.
- **Outputs:**
  - Slice Token `0`: $z_{\text{teacher}} \in \mathbb{R}^{B \times 128}$.
  - `actor_head`: `Linear(128, 128) -> GELU -> Linear(128, 9)`
  - `critic_head`: `Linear(128, 128) -> GELU -> Linear(128, 1)`

### 5.2 Stage 2: `VisualViTStudent` (`models/student.py`)

- **Categorical Palette Input Embedding:**
  - Input tensor: `frames_idx` of shape `[B, 4, 128, 128]` (`uint8` indices in `0..15`).
  - Pass through `self.palette_embed = nn.Embedding(16, 8)` $\rightarrow$ `[B, 4, 128, 128, 8]`, permute and reshape to `[B, 32, 128, 128]`. This cleanly separates identical-luminance colors and preserves the trail color signatures (`{8,9,10}` vs `{1,13,7}` vs `{7}`) that distinguish Explode, Freeze, and Shrink powerups.
- **Conv Patch Stem ($128 \times 128 \to 16 \times 16$ Grid of $8 \times 8$ Patches):**
  1. `Conv2d(32, 64, kernel_size=4, stride=4) + GroupNorm(8, 64) + GELU` ($128 \to 32$)
  2. `Conv2d(64, 128, kernel_size=2, stride=2) + GroupNorm(8, 128) + GELU` ($32 \to 16$)
  - Flatten spatial grid $(16, 16)$ into `256` visual patch tokens of dimension `d_model = 128`: $E_{\text{patches}} \in \mathbb{R}^{B \times 256 \times 128}$.
- **ViT Backbone:**
  - Add learnable 2D positional embedding `pos_embed` `(1, 256, 128)` and prepend `[CLS_student]` `(1, 1, 128)` $\rightarrow$ shape `[B, 257, 128]`.
  - Pass through `3` `CustomTransformerLayer` blocks (`d_model = 128`, `nhead = 4`, `ffn_dim = 256`).
- **Output Heads:**
  1. **Actor Head (`9` actions):** Takes $z_{\text{student}} = \text{out}[:, 0, :] \in \mathbb{R}^{B \times 128}$. Initialized from the trained Teacher's `actor_head` weights, but **kept unfrozen** for end-to-end fine-tuning.
  2. **Dense Spatial Auxiliary Head (`5` channels per patch):** A lightweight linear projection on the 256 patch tokens `Linear(128, 5)` outputting logits of shape `[B, 5, 16, 16]`.

### 5.3 Multi-Channel Box Rasterization Targets (Replacing Point Gaussian Splats)
Because pattern walls can be $127 \times 32$ pixels wide, point-based Gaussian splats misrepresent their spatial footprint. Instead, in `crates/dodge-rl-env` (or vectorized PyTorch), rasterize the exact entity AABBs onto the $16 \times 16$ patch grid (each cell $(u, v)$ covers $[8u, 8u+8) \times [8v, 8v+8)$ in screen space) to produce binary target masks $Y_{\text{aux}} \in \{0, 1\}^{B \times 5 \times 16 \times 16}$:

- **Channel 0 (`lethal_now`):** `1.0` if any currently lethal AABB (Enemy, Kamikaze, Explosion, Moving Rect, or Static Rect with $\text{sh} == 2$) overlaps patch $(u, v)$.
- **Channel 1 (`lethal_soon`):** `1.0` if any charging Static Rect ($0 < \text{sh} < 2$) or warning line overlaps patch $(u, v)$.
- **Channel 2 (`enemy_body`):** `1.0` if any Normal or Kamikaze enemy overlaps patch $(u, v)$ (helps the Student identify enemy-enemy collision opportunities for $+0.5$ score).
- **Channel 3 (`powerup`):** `1.0` if any Powerup AABB overlaps patch $(u, v)$.
- **Channel 4 (`player`):** `1.0` if the Player AABB overlaps patch $(u, v)$.

### 5.4 Staged Distillation & Ablation Protocol
To ensure every loss term pulls its weight:

1. **Stage 2A (Baseline DAgger):** Train Student with pure Action KL loss:$L_{\text{action}} = D_{\text{KL}}\left(\pi_{\text{teacher}}(\cdot \mid s_{\text{priv}}) \;\parallel\; \pi_{\text{student}}(\cdot \mid o_{\text{vis}})\right)$
2. **Stage 2B (+ Dense Box Rasterization Auxiliary Loss):** Add per-patch binary cross-entropy over the 5 semantic occupancy maps:$L_{\text{total}} = L_{\text{action}} + \lambda_{\text{aux}} \text{BCEWithLogits}( \hat{Y}_{\text{aux}}, Y_{\text{aux}} )$
3. **Stage 2C (Controlled Ablations):** Test adding:
  - **Latent Alignment:** $L_{\text{latent}} = \| z_{\text{student}} - \text{sg}(z_{\text{teacher}}) \|_2^2$
  - **Attention Transfer:** Project Teacher entity attention $\alpha_{\text{teacher}, i}$ across all patches overlapped by Entity $i$'s AABB (normalized to sum to 1) and minimize $D_{\text{KL}}(M_{\text{box\_attn}} \parallel \alpha_{\text{student}})$.
  - *Gate:* Only retain $L_{\text{latent}}$ or $L_{\text{attn}}$ in the final config if they measurably improve pure-visual score or survival over Stage 2B.
4. **Stage 2.5 (Asymmetric PPO Fine-Tuning):** If a distillation gap remains, run on-policy PPO where the Visual Student is the Actor $\pi_\theta(a \mid o_{\text{vis}})$ and the frozen/fine-tuned Privileged Teacher Critic $V_\phi(s_{\text{priv}})$ supplies low-variance GAE advantages.

## 6. Revised 7-Milestone Execution Plan

### Milestone 0: Environment Setup, Baselines & Engine Profiling

1. Update `devenv.nix` (or configure a `uv` virtual environment inside the `devenv` shell with `LD_LIBRARY_PATH` / CUDA wheel support for NixOS) to provide Python 3.11+, `maturin`, `pytest`, `numpy`, and `torch`.
2. Benchmark the existing `NativeGame::advance_frame` SPS (single-threaded and multi-threaded).
3. Run 1,000 episodes each of three baseline policies at `difficulty = 2`, `patterns_enabled = true`, `powerups_enabled = true`:
  - **Random Policy**
  - **Stand-Still Policy**
  - **Scripted Heuristic Dodger** (moves away from nearest lethal AABB, moves toward powerups when safe)
4. Record mean/median/p90 **Game Score**, **Survival Frames (at 60 Hz)**, **Max Simultaneous Enemies**, and **Max Simultaneous Pattern Rects**. Use these empirical numbers to lock `MAX_ENEMIES` and set the Teacher's target score gate.

### Milestone 1: `dodge-core` Headless Path, Accessors & Parity Tests

1. Implement `advance_frame_headless`, `render_into`, and `PrivilegedView` in `crates/dodge-core`.
2. Write the **Headless Equivalence Test**: across $100$ seeds $\times 2,000$ random-action frames, assert that `full_state()` after `advance_frame_headless` is bit-for-bit identical to `advance_frame` (ignoring `physical_screen`).
3. Verify all existing parity tests (`v1xx_*`) pass and `cargo clippy --workspace --all-targets` exits with 0 warnings.
4. Benchmark `advance_frame_headless` vs `advance_frame` and record the speedup.

### Milestone 2: `crates/dodge-rl-env` Vectorized PyO3 Binding

1. Create `crates/dodge-rl-env` (linking **only** `dodge-core`, with its own `[lints]` table).
2. Implement `VecDodgeEnv` with per-episode seeded `NativeGame::new`, internal start-sequence fast-forwarding (`X` press + neutral until `Mode::Game`), action repeat $K=4$ with summed $\Delta\text{score}$ and survival rewards, AABB Minkowski/slab featurization, 5-channel $16 \times 16$ box rasterization targets, and optional 4-frame $K$-spaced pixel stacks.
3. Write Python tests verifying shapes, non-clairvoyance, off-screen coordinate handling (no $[0, 128]$ assertions), and zero memory leaks over 100k steps.
4. Benchmark multi-threaded Rayon chunked throughput (headless SPS and rendered SPS).

### Milestone 3: Stage 1 — Privileged Entity-Transformer Teacher (PPO)

1. Implement `OmniscientEntityTeacher` with `CustomTransformerLayer` in `python/dodge_rl/models/teacher.py`.
2. Train via PPO (`gamma = 0.995` at $K=4$) using the built-in curriculum:
  - **Phase A:** `difficulty = 1, patterns = false, powerups = true` (learn movement, enemy-collision baiting, and powerup collection).
  - **Phase B:** `difficulty = 2, patterns = true, powerups = true` (learn static rect `frames_until_lethal` and moving walls).
  - **Phase C:** `difficulty = 3, patterns = true, powerups = true` (full chaos + optional `Snapshot::restore` hard-state replays).
3. **Gate:** Teacher must beat the Milestone 0 Scripted Heuristic Dodger's mean **Score** and **Survival Time** by a clear margin (e.g., $\ge 2\times$ mean score) at Difficulty 2 and 3.

### Milestone 4: Stage 2A & 2B — Visual Student (DAgger + Box Rasterization)

1. Implement `VisualViTStudent` (with `nn.Embedding(16, 8)` palette embedding and $K$-spaced 4-frame Conv stem) in `python/dodge_rl/models/student.py`.
2. Train Stage 2A (Action-KL DAgger with $\beta$ annealed $1.0 \to 0.0$) and evaluate pure-visual score and survival.
3. Train Stage 2B (Action-KL + 5-channel $16 \times 16$ Box Rasterization BCE head) and measure the improvement in pure-visual score and survival.

### Milestone 5: Stage 2C & 2.5 — Ablations & Asymmetric PPO Fine-Tuning

1. Run controlled ablations adding $L_{\text{latent}}$ (MSE on `[CLS]`) and $L_{\text{attn}}$ (AABB-projected Teacher attention KL). Retain only terms that improve pure-visual evaluation score.
2. If the Student trails the Teacher by $>10\%$ in mean score, run Stage 2.5 Asymmetric PPO (Visual Student Actor + Privileged Teacher Critic) to close the gap.

### Milestone 6: Visual Evaluation & Diagnostics (`eval_visual.py`)

1. Build `python/dodge_rl/eval_visual.py` to output quantitative metrics (mean/median/max Score and Survival Seconds across difficulties) and render a 60 FPS diagnostic video showing:
  - **Panel 1:** Live $128 \times 128$ PICO-8 game frame (mapped via `PICO8_PALETTE`).
  - **Panel 2:** The Student's predicted $16 \times 16$ semantic occupancy probabilities (`lethal_now`, `lethal_soon`, `powerup`).
  - **Panel 3:** The Student ViT's `[CLS]` spatial attention heatmap over the $16 \times 16$ grid.
