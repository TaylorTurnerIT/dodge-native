# M2 math/raster implementation, revision 1

The two production modules are frozen for parent review and wrapper integration.
This directory records focused primitive verification, not workspace acceptance.

## Scope and provenance

Owned production paths:

- `crates/dodge-rl-env/src/geometry.rs`
- `crates/dodge-rl-env/src/raster.rs`

All other writes belong to this evidence directory. No Cargo manifest, `lib.rs`,
core draft, parent document, commit, or PR was created or changed by this task.
No subagent was launched. No changing core source was read or compiled.

`input-manifest.json` identifies the exact frozen core inputs and copied design
documents. The environment contract matched revision 2 SHA-256
`79e953f20487bb442888fe40cee5f43226ae2cfc7ef0b9ef0fc3a377db4e01aa`.
The frozen `fixed.rs`, `game.rs`, and `snapshot.rs` hashes were also checked
against `learning/.cache/v2-m1-review-r1/manifest.json` before implementation.

Source anchors in that frozen core:

- `game.rs:1055`: strict enemy/powerup and pattern collision inequalities.
- `fixed.rs:58` and `fixed.rs:71`: native floor and negative-half round behavior.
- `snapshot.rs:969`: enemy/powerup renderer footprint and enemy size clamp.
- `snapshot.rs:1081`: independently rounded rectangle coordinates and sizes.
- `snapshot.rs:1207`: main warning segment and shadow at `y+1`.

The parent supplied the M0 full-D2 audit result (1,000 episodes per policy,
maximum 15 enemies and 16 rectangles, no overflow, all 39 patterns). This task
did not repeat or validate that campaign. These primitives impose no entity cap;
the parent retains the specified 64 enemy-family plus 16 rectangle defaults.

## Public API

`geometry` exposes:

- `ONE_RAW`, `SLAB_HORIZON_FRAMES`.
- `RawInterval::from_raw_q16(i32, i32)` with `min_raw`, `max_raw`, `is_inverted`,
  `center_twice_raw`, `half_extent_twice_raw`, `strictly_overlaps`, `signed_gap`.
- `RawAabb::from_raw_q16(min_x, min_y, max_x, max_y)` and public `x`/`y`
  intervals, plus `strictly_overlaps`, `signed_gaps`, and `measures`.
- `RawBoxMeasures` with public `center_x_twice_raw`, `center_y_twice_raw`,
  `half_x_twice_raw`, `half_y_twice_raw` (`i64`, in half-raw units).
- `raw_to_pixels(i64) -> f64`, `half_raw_to_pixels(i64) -> f64`.
- `enemy_box(x, y, size)`, `powerup_box(x, y)`,
  `rectangle_box(x, y, width, height)`, and
  `player_box(x, y, size, PlayerBoxKind) -> RawAabb`. All scalar inputs are raw
  native Q16.16 `i32`; player kinds are `EnemyFamily`, `Powerup`, `Rectangle`.
- `RelativeVelocityRaw { x: f64, y: f64 }` and
  `slab_contact(entity, player, velocity) -> SlabContact`, with public `frames`,
  `contact_within_horizon`, and `strict_overlap_now` fields.
- `floor_raw_q16(i32) -> i64`, `round_raw_q16(i32) -> i64`.
- `PixelFootprint { min_x, min_y, max_x, max_y: i64 }` and
  `intersects_world()`, plus `enemy_footprint`, `powerup_footprint`, and
  `rectangle_footprint` using the same raw input signatures as their box helpers.
- `WarningSegment::from_raw_q16(x0, y0, x1, y1) -> Result<_, SegmentError>`;
  `main_footprint`, `shadow_footprint`, `intersects_world`.
  `SegmentError::NonAxisAligned` rejects rounded diagonal segments.

`raster` exposes:

- `PATCH_SIDE = 16`, `CHANNEL_COUNT = 5`, `CELL_RAW = 1 << 19`.
- `RasterChannel = [[f32; 16]; 16]` and
  `RasterChannels = [[[f32; 16]; 16]; 5]`, indexed `[channel][y][x]`.
- `Channel::{LethalNow, LethalSoon, Enemy, Powerup, Player}` in that exact order.
- `RasterFlags` with independent `lethal_now`, `lethal_soon`, `enemy`, `powerup`,
  and `player` booleans, plus `as_array()`.
- `RasterDiagnostics { inverted_boxes: u64, inverted_axes: u64 }`.
- `floor_cell(i64)`, `ceil_cell(i64)`, and
  `interval_patches(RawInterval) -> Option<PatchSpan { first, last: usize }>`.
- `AuxRaster::default()`, `paint_box(RawAabb, RasterFlags)`,
  `paint_warning(WarningSegment, RasterFlags)`, `channel(Channel)`, `channels()`,
  `into_channels()`, and `diagnostics()`.

## Wrapper integration

Declare `geometry` and `raster` as sibling crate-root modules; `raster` imports
`crate::geometry`. The parent owns that module registration and crate manifest.
Pass native fixed values via `.raw()`. Endpoint constructors wrap at the native
`i32` boundary and then widen; interval math stays in signed `i64`. Private
interval endpoints ensure all native endpoint differences and sums fit `i64`.

Compute measured center delta by subtracting consecutive
`center_*_twice_raw` fields, converting the difference to `f64`, and dividing by
two. Subtract the player velocity's raw Q16.16 value before calling
`slab_contact`. This preserves half-raw motion. The returned time is in raw
frames; divide by 120 for the normalized feature. Unknown history handling
belongs to the wrapper.

Evaluate footprint admission independently at reset and decision boundaries.
Keep admitted entity coordinates unchanged. The helper holds no sticky seen set.
Use the borrowed current-drawn-warning eligibility supplied by core, then check
each segment's `intersects_world`; handle `NonAxisAligned` as an explicit
contract error rather than silently discarding a warning. No timer or hidden
rectangle is an input to the warning primitives.

Create a fresh `AuxRaster` per observation. Paint admitted entities with their
literal collision boxes and caller-supplied phase/category flags. For the player
channel, use `player_box(..., PlayerBoxKind::Powerup)`. Paint eligible warning
segments with only `lethal_soon` enabled. The raster does not derive hazardous
phase from player overlap. It exposes diagnostics separately from neural data.

## Verification and retained logs

From the checkout root:

```sh
python3 learning/runs/v2/milestone2-math-r1/check.py test
python3 learning/runs/v2/milestone2-math-r1/check.py clippy
```

The test phase runs `rustfmt --check` on only the two owned modules and the
owned fixture harness, compiles the actual modules through `#[path]` with
`rustc --edition 2024 --test --deny warnings`, then runs tests sequentially.
The Clippy phase runs `clippy-driver --edition 2024 --test -W clippy::all
-D warnings` on the same harness. Neither phase reads a Cargo manifest or
compiles changing core source.

Initial results: **35 passed; 0 failed; 0 ignored**. Formatting, standalone
compilation, and standalone Clippy each exited zero. All five command attempts
are retained in `commands.jsonl`, with exact arguments, timestamps, input source
hashes, exit status, and separate complete logs. `04-fixtures.log` contains the
test names and result. `failure-ledger.json` records that no check failed and no
failure-driven source revision or retry occurred.

Coverage includes type offsets and strict edges; shrunk point players; zero and
negative explosions; literal width-one/zero/inverted rectangles; half-raw center
precision; native wrapping; widened signed gaps; stationary, parallel, corner,
tangent, disjoint, horizon and point slabs; negative floor and round ties;
partly offscreen admission; the offscreen control; powerup shadows; full-width
walls; half-open and point patch rules; warning main/shadow boundaries and
vertical/reversed segments; inverted counters; and independent overlapping
binary channels.

`source-manifest.json` identifies the exact final production and harness sources.
`frozen/` contains byte-for-byte copies of the production modules.
`evidence-manifest.json` hashes the retained source, inputs, commands, logs, and
artifacts. The manifest excludes itself to avoid a self-hash cycle.

## Limits

Slabs predict closed contact for constant relative center velocity and fixed
current extents. Contact at time zero is distinct from native strict collision.
Growth, shrink, acceleration, future phase, collision order, and later gameplay
changes can invalidate the prediction. Nonfinite velocity returns the 120-frame
miss sentinel while preserving the independently computed current-overlap flag.

Renderer footprints are conservative envelopes. Occlusion, outlines/circles,
palette aliases, HUD coverage, and camera-edge padding prevent a general pixel
observability claim. Warning support is explicitly axis-aligned; it does not
implement arbitrary Bresenham segments. Inverted collision intervals retain
their native strict-inequality behavior but intentionally paint no occupancy.
Diagnostic counters saturate at `u64::MAX`.

No runtime renderer comparison, whole-environment behavior, PyO3 integration,
workspace check, throughput, allocation measurement, or broad visibility proof
was performed. Those acceptance checks remain with the parent.
