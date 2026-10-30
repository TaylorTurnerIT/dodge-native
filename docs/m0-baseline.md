# M0 pre-headless baseline and profiling harness

The harness is implemented in `crates/dodge-core/examples/m0_baseline.rs` with
three supporting modules under `examples/m0/`. It adds no dependencies and changes
no tracked engine, game, snapshot, state, cartridge, or workspace configuration.
Its source guard requires HEAD `d7ad95127ad7529c5217a51ae9dc5cfedd3f2365` and
unchanged engine inputs. This worktree remains the pre-headless measurement source;
the parent's M1 checkout is never used for builds or simulation.

Authority was read from these parent files, without editing them:

- `/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/docs/SPEC_PRIVILEGED_VIT_RL.md`
- `/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/docs/implementation-plan-v2.md`

Their hashes, original tracked-file hashes, toolchain identity, and authorization
bounds are retained in `target/v2-m0-pilot-r1/preflight.json`.

## Episode contract

Each policy receives the same frozen stream `0xB0000000 + i`. The proposed long
campaign uses `i = 0..999`, separately for all three policies. Every episode
constructs a fresh `NativeGame` with difficulty 2, patterns and powerups enabled,
theme background/shadow 12/1, and twelve zero initial highscores. Startup presses
X once and advances neutral frames until `Mode::Game`. There is no reset, retry,
or state carryover. A failed startup stops the run.

Default action repeat is four. The harness calls the original full
`NativeGame::advance_frame` on **every** raw frame; it never calls `step`.
It accumulates score deltas, legacy native rewards, and all five frame-event
counts, then stops immediately on death or the raw-frame cap, including inside
an action repeat. Death takes precedence if death and cap coincide.

Startup frames are excluded from gameplay and survival counts. Gameplay native
frames include the death frame; survival counts only alive frames, checked against
the native survival-counter delta. Seconds use 60 Hz. Final native game score is
reported directly and checked against the sum of every executed frame's score
delta. The separate diagnostic objective return is
`sum(score_delta) + 0.01 * alive_raw_frames - 5 * death`; policies do not optimize
an artificial center, wall, or action-jitter reward.

The proposed long cap is **18,000 raw gameplay frames**, provisionally. Parent
review must choose or accept that cap before the long campaign. This implementation
does not establish the 1,000-episode distributions, final entity capacities, or a
teacher score gate.

## Policies and geometry

- **Random:** private SplitMix64, initialized with
  `u64(seed) XOR 0xD1B54A32D192ED03`, using rejection sampling over the nine
  `Action::ALL` actions. It never reads or advances native RNG.
- **Neutral:** holds `Action::Neutral` throughout gameplay.
- **Nearest lethal AABB dodger:** evaluates all nine held actions over a 12-frame
  horizon, executes the chosen action for at most four frames, then replans.
  Player prediction uses the source's Q16.16 friction, acceleration, and [2, 125]
  clamps, including retained momentum at walls and unnormalized diagonals.
  Candidate checks use collision-before-motion order and strict inequalities.

Current collision boxes follow the native source:

- Normal, kamikaze, and explosion entries use `[x, x+s] × [y, y+s]` against
  player half-size `ps-1`.
- Powerups use `[x-4, x+4] × [y-4, y+4]` against player half-size `ps`.
- Pattern rectangles use `[x, x+w-1] × [y, y+h-1]` against player half-size
  `ps-2`. This retains strict point-in-box behavior when shrink makes `ps-2=0`.
- A static rectangle is lethal now only at native `sh == 2`. Visible charging
  rectangles with `0 < sh < 2` are forecast to become lethal at
  `(2-sh)/(0.02*freeze_rate)` frames. Moving rectangles are lethal throughout
  their current boxes, including while charging.

The nearest currently lethal box is selected by signed AABB clearance. If none
exists, a charging box expected to become lethal within the horizon can be used.
All lethal boxes constrain candidate collision checks. When a powerup exists and
some candidate remains collision-free with at least four pixels of clearance
throughout the horizon, the policy chooses the safe candidate ending closest to
any powerup. Otherwise it maximizes predicted time without collision, then
end-of-horizon clearance from the nearest threat, then minimum clearance from all
threats. Exact ties retain the first action in native action order. No threats or
powerups therefore produce neutral input. Native center anti-camping, corner
spawns, momentum, and walls remain part of the environment.

This is a scripted heuristic, not an exact future collision controller. Enemy
velocity is extrapolated from current `vx/vy * speed * freeze_rate * enemy.speed`;
future acceleration, bounces, collisions, births, removals, powerup effects, and
size changes are not simulated. Explosion bounds are exact now but held fixed
over the prediction horizon. Rectangle edge displacements are measured between
consecutive raw frames within the same active pattern, including changing width
and height; the first observed frame has zero inferred displacement. Smooth
motion, future target transitions, and future freezes can invalidate that linear
forecast. Charging forecasts assume increasing charge and can conservatively
misclassify a retreating static rectangle. No queued targets, RNG state,
scheduling timers, or anti-camping counters influence decisions.

## Outputs and bounds

`--episodes` accepts 1..1000 per policy, `--max-frames` accepts 1..18000, and
`--action-repeat` accepts 2..4. `--output-dir` is required. Atomic directory
creation rejects any existing destination, even an empty directory. Output files
also use exclusive creation. Errors retain partial receipts without retrying.

The fixed-schema standard-library JSON serializer escapes strings and rejects
nonfinite numbers. Baseline output contains:

- `manifest.json`: source and executable SHA256 hashes, HEAD, runtime toolchain,
  worktree, exact arguments, configuration, RNG recipes, and all episode seeds.
  Embedded harness text must match disk before a measurement can start.
- `episodes.jsonl`: one flushed record per episode with score, raw/alive/native
  frame counts, 60 Hz survival seconds, decisions, startup and gameplay timings,
  accumulated events/rewards, death versus cap, entity maxima, coverage, and
  capacity-overflow observations.
- `summary.json`: mean, median, nearest-rank p90, and maximum score, survival,
  and per-episode entity maxima; aggregate frame/decision/overflow counts and
  observed pattern IDs. An even-sized median averages the central pair.

Enemy-family occupancy counts every live entry in `enemies`, including powerups
and explosions. Active rectangle occupancy counts only `active_pattern.rects`,
never the inactive catalog. It includes charging and finished rectangle entries
while the native pattern remains active, matching the native collision loop's
scope. Occupancy is sampled at the initial gameplay boundary and after every
raw gameplay frame. Overflow frame and excess-record counts use only executed
gameplay frames and thresholds 64/16. Pattern coverage records active pattern IDs
and per-ID raw-frame counts. These are frame-boundary observations, not maxima
inside a single engine method call.

## Full-frame benchmark

Benchmark mode is separate from baseline mode. It requires a release build and
accepts a total requested duration of 1..50 seconds. It runs one single-thread
phase followed by one multithread phase, with independent fresh game instances
on OS worker threads. Thread limits use the minimum of macOS physical CPU count
and Rust available parallelism. Other platforms currently fail physical-core
discovery rather than treating logical CPUs as physical CPUs.

Both phases use private random nine-action input, the same repeat contract,
fresh startup on death, and a 2,000-raw-frame benchmark episode cap. Their seeds
are explicit in each worker receipt and follow
`0xC0000000 + worker_id + episode_index * phase_threads`. Benchmark seeds and
short benchmark episodes are separate from the paired score-baseline campaign.

Compilation and provenance capture finish before benchmark timing. Per-worker
simulation clocks exclude construction/startup and include action RNG, the full
frame method, and destruction of returned results. Wall rates include startups,
scheduling, and thread lifecycle. Summed worker simulation seconds are reported
as worker time, never as parallel wall time. Reports distinguish raw gameplay
frames, startup native frames, and decision steps. Each raw call checks a wall
deadline; an in-flight call or startup can finish just after that deadline.

## Executed checks and bounded evidence

Only one pilot and one throughput benchmark were executed. Source was frozen
before both in `target/v2-m0-pilot-r1/experiment-plan.json` and
`preheadless-source.tar.gz`. All logs and initial failed lint output are retained
in that companion directory. No source changed after those measurements.

- Original core: `cargo test --locked -p dodge-core`, 44 passed; zero doctests.
- Harness: `cargo test --locked -p dodge-core --example m0_baseline`, 10 passed.
  Tests cover raw-frame aggregation, death/cap breaks, private seeding and all
  action masks, strict typed geometry, active-only counts, overflow accounting,
  charging/moving rectangles, safe powerup seeking, momentum/clamps, CLI bounds,
  JSON escaping/nonfinite rejection, and quantiles.
- `cargo fmt --all -- --check`: passed.
- `cargo clippy --locked --workspace --all-targets`: passed. An earlier
  collapsible-if error in the new example was fixed before source freeze.
- `cargo build --locked --release -p dodge-core --example m0_baseline`: passed.

The pilot used ten paired seeds per policy, cap 2,000, repeat four. Every startup
used 13 excluded native frames. Results are diagnostic and cap-censored:

- Random: score mean/median/p90 **0.30 / 0 / 0**; alive frames
  **208.4 / 176.5 / 261**; 10 deaths, zero cap truncations.
- Neutral: score **0.20 / 0 / 1**; alive frames **187.6 / 187 / 190**;
  10 deaths, zero cap truncations.
- Dodger: score **22.90 / 22.75 / 25.5**; alive frames
  **1886.5 / 2000 / 2000**; two deaths, eight cap truncations.

The pilot observed at most 15 live enemy-family entries and 16 active rectangles,
with zero overflow frames at 64/16. Across policies it observed pattern IDs
1, 2, 5, 9, 10, 18, 21, 27, 28, 31. This short coverage cannot establish capacity
safety; eight capped dodger episodes also limit survival comparisons.

The release benchmark requested six seconds and measured 6.000322 seconds of
benchmark wall time, or 6.328725 seconds including invocation/provenance overhead.
The host exposed 14 physical CPUs and available parallelism 14. Sequential phases:

- One worker: 117,912 gameplay raw frames, 5,941 startup frames, 29,660 decisions;
  3.000061 wall seconds, 2.781033 simulation worker seconds;
  **39,303.20 gameplay frames/s** and **9,886.47 decisions/s** by wall time.
- Four workers: 405,975 gameplay raw frames, 20,735 startup frames, 102,108 decisions;
  3.000244 wall seconds, 11.167394 summed simulation worker seconds;
  **135,313.99 gameplay frames/s** and **34,033.23 decisions/s** by wall time.

These measure the existing full-frame random-input path on this host. They do
not measure headless stepping, heuristic-policy throughput, training, or future
hardware performance. Raw receipts contain worker seeds, startup timing, and
both wall-time and simulation-worker-time rates.

## Next long campaign: parent review required

The following command proposes the frozen 1,000-seed, 18,000-frame recipe. It has
**not** been executed. Parent review must approve the harness and choose the
empirical cap first. Use a new destination; this command cannot replace an old run.

```sh
cargo run --manifest-path /Users/taylor/.t3/worktrees/dodge-native/t3-a0ce7b5e/Cargo.toml --release --locked -p dodge-core --example m0_baseline -- --episodes 1000 --max-frames 18000 --action-repeat 4 --output-dir /Users/taylor/.t3/worktrees/dodge-native/t3-a0ce7b5e/target/v2-m0-baselines-r1
```

No commits, PRs, publication, merge, training, dependency changes, or changes to
another checkout were made.
