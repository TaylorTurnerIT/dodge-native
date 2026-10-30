# M0 pre-headless baseline harness: review repair 2

This isolated worktree is `/Users/taylor/.t3/worktrees/dodge-native/t3-5d7162c0`,
branch `t3/repair-m0-harness`, at original HEAD
`d7ad95127ad7529c5217a51ae9dc5cfedd3f2365`. All original tracked files remain
unchanged. Only the example, its three modules, and this document are new source
files. No dependencies, gameplay, core API, or parent headless implementation are
changed or copied.

The five files were copied byte-for-byte from the read-only worktree
`/Users/taylor/.t3/worktrees/dodge-native/t3-a0ce7b5e`. Their hashes were verified
against that worktree's `target/v2-m0-pilot-r1/final-manifest.json` before edits.
`target/v2-m0-review-r2/copy-verification.json` records the check. The original
pilot and throughput results describe the old policy and remain historical.
No result transfers to this repair.

The parent specification, implementation plan, and source-audit decisions were
read from `/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/docs/`:
`SPEC_PRIVILEGED_VIT_RL.md`, `implementation-plan-v2.md`, and `v2-source-audit.md`.
Their hashes are retained in the repair receipts. That checkout is read-only.

## Episode and configuration contract

Each policy receives the paired fresh `u32` seeds `0xB0000000 + i`.
Every episode constructs `NativeGame::new` from its recorded `NativeConfig`.
There is no reset, retry, or state carryover. Startup presses X once, then holds
neutral until `Mode::Game`, bounded by 120 raw frames. Every successful startup
must take exactly 13 frames: X plus twelve neutral frames. It must preserve the
requested seed, difficulty, flags, theme, and zero initial highscores. A mismatch
fails the run. Startup frames are excluded from gameplay and survival counts.

Defaults are 1,000 episodes per policy, an 18,000-raw-gameplay-frame cap, action
repeat four, difficulty 2, patterns enabled, powerups enabled, theme 12/1, twelve
zero highscores, and a global 3,600-second budget. The policy order is random,
neutral, then AABB dodger. Seed base and theme are fixed.

The CLI accepts `--episodes 1..1000`, `--max-frames 1..18000`,
`--action-repeat 2..4`, `--difficulty 1|2|3`, `--patterns true|false`,
`--powerups true|false`, and `--max-seconds 1..3600`. `--output-dir NEW_DIR` is
required. Benchmark mode accepts the same configuration and global budget.
The manifest, every episode, and benchmark phases serialize the actual
configuration template used to construct native games; seeds are recorded
separately. Synthetic tests check all twelve configuration categories and their
startup counts, including D1 and D3. Those tests are not baseline campaigns.

Every gameplay raw frame calls the original full
`NativeGame::advance_frame(action.mask())`. The harness never calls `step`,
which drops intermediate rewards and events. It accumulates fixed-point score
deltas, legacy rewards, and all five frame events. Death stops action repeat
immediately, and takes precedence when it coincides with the episode cap.
A decision must begin in `Mode::Game`; no extra gameplay frame follows death.

Gameplay frames include the death frame. Survival counts only alive frames and
must equal the native survival-counter delta. Seconds use 60 Hz. The score-delta
sum must equal the final raw native score, including pickups on a lethal frame.
The separate diagnostic return is
`sum(score_delta) + 0.01 * alive_raw_frames - 5 * death`.

## Policy repair and prediction limits

Random uses an independent SplitMix64 generator initialized with
`u64(seed) XOR 0xD1B54A32D192ED03`, with rejection sampling over the nine native
actions. Neutral holds no direction. Neither inspects native RNG.

The dodger evaluates all nine held actions over twelve predicted raw frames.
Player motion uses native Q16.16 momentum, unnormalized diagonals, and clamps.
Current collision checks use strict inequalities and native type-specific boxes:

- Enemy, kamikaze, and explosion: `[x,x+s] × [y,y+s]`, player half-size `ps-1`.
- Powerup: `[x-4,x+4] × [y-4,y+4]`, player half-size `ps`.
- Pattern rectangle: `[x,x+w-1] × [y,y+h-1]`, player half-size `ps-2`.

A shrunk player's pattern box is a point. Signed per-axis gaps use
`max(entity_min-player_max, player_min-entity_max)`, retaining negative clearance
for a point strictly inside a box. Touching an edge is not strict overlap.
Zero-size explosions remain collision candidates. Narrow boxes, inverted native
bounds, and partly offscreen coordinates are retained without sorting or clipping.

Only pattern 23's exact type-1 rectangle `(-50,-50,0,0)` is excluded from policy
entities. That record controls spawns and has no visible spatial geometry.
Its presence cannot change either neutral behavior or a safe-powerup choice.
This is a narrow source-pinned exclusion, not a general visibility filter.
Occupancy receipts still count the native record and identify their raw scope.

A static rectangle is lethal now only at `sh == 2`; moving rectangles are lethal
in their current boxes. For static `0 < sh < 2`, a forecast requires a positive
`sh` delta from the immediately preceding observed raw frame in the same active
pattern and rectangle slot. The forecast is `(2-sh)/observed_sh_delta`.
Decreasing, flat, and first-sample `sh` produce no future-lethal forecast.
An inactive interval or changed active pattern resets history. Observation runs
after every raw frame inside action repeat. Policy decisions do not read queued
targets, `shown`, waits, scheduling timers, or native RNG to infer phase.

All lethal threats constrain predicted collision checks. A safe candidate has no
predicted collision and at least four pixels of clearance over the horizon.
When such candidates exist, the policy chooses the one ending closest to a
powerup. Otherwise it maximizes collision-free time, then final clearance from
the nearest current or imminent threat, then minimum clearance from all threats.
Native action order resolves ties; no threats or powerups gives neutral.

This is a current-velocity prediction approximation, not a future-death oracle.
Enemy translation uses `vx/vy * speed * freeze_rate * enemy.speed`; later score
changes, acceleration, bounces, births, removals, and pickups can invalidate it.
Enemy growth and explosion extent changes are approximated by holding current
extents fixed. A new zero-size explosion is therefore included now but its future
expansion is not predicted. Rectangle edge deltas use consecutive raw frames,
including width/height changes, then extrapolate linearly. First-sample edge
motion is zero. Future targets, phase changes, and freezes are not simulated.

## Receipts, deadlines, and failure behavior

Atomic directory creation rejects every existing destination, including empty
directories. Files also use exclusive creation. Existing runs are never replaced.
The JSON serializer escapes strings and rejects nonfinite numbers.

- `manifest.json` schema 2 records source/executable SHA256, HEAD, worktree,
  runtime toolchain, arguments, configuration, seeds, repeat, cap, and time budget.
  All original tracked files must match HEAD, including staged changes. Compiled
  harness text must match disk before a run starts.
- `episodes.jsonl` is flushed and synced after each complete or interrupted
  gameplay episode. It includes final state hash, counts, events, timing, and
  separate death, cap, and run-deadline flags. Interrupted episodes carry an
  error and `episode_status: interrupted`; they do not enter completed summaries.
- Each `scores` object records signed Q16.16 integer `final_score_raw_fixed`,
  floating-point `final_score_raw`, integer `final_score_display_ceil`, native
  zero-based highscore category slot, actual stored highscore in fixed-point and
  score units, and `new_highscore`. The stored category value is not reconstructed
  from final score: `die()` can save it before a later pickup on the same frame.
  A cap-truncated game need not have saved any highscore.
- `summary.json` labels `raw_score`, `display_score_ceil`, and `stored_highscore`
  separately. Each uses the same mean/min/p10/p25/median/p75/p90/max distribution
  schema. Raw survival frames and 60 Hz seconds use that schema too. Quantiles
  use nearest rank; an even median averages the central pair.
- `failure.json` retains the error, last policy/index, completed episodes,
  emitted JSONL records, elapsed time, and deadline status. Prior records and
  any interrupted gameplay record remain available. Startup failure has no
  completed gameplay record; failure metadata still identifies the attempted
  policy/index. Disk or serialization errors can leave an incomplete last line.

The global budget starts after CLI parsing and includes provenance, construction,
startup, and simulation. Checks run between native frames, decisions, episodes,
and run stages. On expiry, no new native frame starts; a running synchronous
call, policy computation, subprocess, or I/O operation can finish later. There
is no OS preemption guarantee and no automatic retry or resume.

Enemy-family occupancy includes explosions and powerups. Rectangle occupancy
includes every record of the active pattern, including charging, finished, and
hidden control entries; it never counts the inactive catalog. Counts are sampled
at the initial gameplay boundary and after each executed raw frame. Receipts
include maxima, overflow frames and excess records above 64/16, pattern IDs, and
per-ID frames. They do not establish within-call maxima or accepted capacities.

Benchmark mode still runs sequential single-thread and multithread phases with
fresh games, independent private random actions, and a 2,000-frame episode cap.
Seeds use `0xC0000000 + worker_id + episode_index * phase_threads` per phase.
It requires release mode, 1..50 requested seconds, and a physical-core-bounded
thread count. macOS physical-core discovery is the implemented platform path.
Phase receipts serialize the same native configuration, verify 13-frame startup,
and retain failed worker/phase data before returning an error. Simulation clocks
exclude startup; wall rates include startup and thread lifecycle. Summed worker
seconds are not parallel wall time. This repair runs no throughput benchmark.

## Validation and frozen production recipe

Repair evidence lives in `target/v2-m0-review-r2`. Required checks are original
core tests, all ten existing harness checks plus eight relevant additions,
formatting, workspace/all-target Clippy, and release build. Logs preserve failures
as well as the final checks. Synthetic tests cover deadline expiry inside action
repeat, interruption receipts, overwrite rejection, configuration/startup, score
representations, hidden control, charge direction, and strict degenerate geometry.

Only one correctness smoke is allowed: one episode per policy, cap 2,000, repeat
four, D1, patterns false, powerups false. It verifies nondefault CLI configuration
and JSON fields; it cannot qualify score, survival, capacity, or throughput.
Source and executable identities are frozen before that invocation. No old
30-episode pilot, long campaign, PPO, student work, or throughput run is repeated.

The production recipe below remains **unexecuted**. Parent free Beam review and
source freeze must precede its 3,000 total episodes. D3 evaluation and D1 curriculum
checks remain separate parent decisions; do not multiply this campaign by three.
Theme 12/1, zero highscores, and seed base `0xB0000000` are fixed by source.
Use a fresh output path if a failed or previous run already occupies this one.

```sh
cargo run --manifest-path /Users/taylor/.t3/worktrees/dodge-native/t3-5d7162c0/Cargo.toml --release --locked -p dodge-core --example m0_baseline -- --episodes 1000 --max-frames 18000 --action-repeat 4 --difficulty 2 --patterns true --powerups true --max-seconds 3600 --output-dir /Users/taylor/.t3/worktrees/dodge-native/t3-5d7162c0/target/v2-m0-baselines-r2
```

The bounded correctness smoke command is:

```sh
cargo run --manifest-path /Users/taylor/.t3/worktrees/dodge-native/t3-5d7162c0/Cargo.toml --release --locked -p dodge-core --example m0_baseline -- --episodes 1 --max-frames 2000 --action-repeat 4 --difficulty 1 --patterns false --powerups false --max-seconds 30 --output-dir /Users/taylor/.t3/worktrees/dodge-native/t3-5d7162c0/target/v2-m0-review-r2/smoke
```
