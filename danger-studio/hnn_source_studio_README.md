# HNN Road Game (marimo)

Run: `uv run marimo run studio/app.py` (or `uv run marimo edit studio/app.py`).

The marimo page owns the scenario and kernel choice. The embedded panel owns playback,
the live kernel sliders, the 3D camera and the goal editor.

## Moving goals

- Drag any dashed ring on the 2D map to move that driver's destination. The 3D goal pit
  and the agent's urgency vector update in the same frame.
- Type exact coordinates in the `X` / `Y` fields under the map.
- **Reset goals** restores the scenario's original destinations. **Reset run** restarts
  the cars but keeps the goals you moved.
- **Loop goals** is off by default so a moved goal is not flipped automatically when the
  cars arrive.

## Styling

Styling is NASA JPL's [Stellar](https://github.com/nasa-jpl/stellar) design system
(MIT, pinned 1.1.18), vendored in `vendor/stellar/`. `build_css.sh` rebuilds `studio.css`
from it plus `custom.css`. Three.js r128 is vendored in `vendor/three.min.js` and inlined
into the iframe at run time, so the page works offline.

## Dodge danger field (Part II)

The second section of the page shows the `dodge-native` engine under a hard-coded danger
field. It has two modes.

- **Live, no frame cap** (default). The page starts a `dodge-danger --stream` process and
  pulls frames from it as it plays. The run goes on until the player dies. The
  `lookahead` policy did not die in any setting I tried (difficulty 1 to 3, patterns and
  powerups on or off, up to 30,000 frames), so a live run can go on indefinitely.
  Pause stops the pulling. The page keeps a rolling window of the last 3,600 to 7,200
  frames, so memory stays flat. **Restart run** starts a new run.
- **Recorded, capped.** The binary runs once with a frame limit and the page plays back the
  trace. Use it to scrub through a fixed run.

`app.py` runs `dodge-native/target/release/dodge-danger`. If the binary is missing, `app.py`
builds it with `cargo` (it looks in `~/.cargo/bin`).

Live mode uses `relay.py`, a small HTTP server on `127.0.0.1` that `app.py` starts inside the
notebook process. The browser must run on the same machine as marimo. Every request needs a
random token, run settings are checked against an allow-list, at most 4 runs live at once,
and idle runs stop after 90 seconds.

- The heat map is the arrival field: the engine frame at which a homing enemy would hit a
  player who stays at that cell.
- The goal is the safest cell by that field, with corner and distance penalties.
- The `lookahead` policy clones the exact engine and scores all nine actions.
- The `landscape` policy does gradient descent on a hard-coded potential `V(q)` and plans
  nothing. `V` is a sum of terms: a tube of Gaussians along each enemy's velocity,
  lethal pattern rectangles, a wall ridge, fixed corner terms, a centre ridge (the game's
  anti-camp spawner) and a weak tilt that breaks the spawn symmetry. Every shape is a
  number in `LandscapeParams` (`dodge-native/crates/dodge-danger/src/landscape.rs`). Override
  them with `dodge-danger --params file.json`. These are the numbers a model would learn.
- The float predictor is checked against engine rollouts with
  `cargo run --release -p dodge-danger --example validate_field` (in `dodge-native/`).
