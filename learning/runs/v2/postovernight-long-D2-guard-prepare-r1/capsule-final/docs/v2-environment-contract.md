# M2 environment contract, revision 2

This is an implementation design derived from [v2](SPEC_PRIVILEGED_VIT_RL.md), the [source audit](v2-source-audit.md), and the read-only Opus review retained in `learning/runs/v2-orchestration/m2_contract_opus_r1-result.json`. Parent source reconciliation is in progress; Milestone 0 capacity measurements remain pending. It does not claim an existing vectorized API or authorize training past the foundation gates.

## Observation layout

| Buffer | Shape and type |
| --- | --- |
| `global_feats` | `float32[B, 1, 14]` |
| `entity_feats` | `float32[B, 80, 16]`, initially 64 enemy-family and 16 rectangle slots |
| `entity_types` | `int64[B, 80]`, types 1–8; padding type 0 |
| `entity_mask` | `bool[B, 80]`, true for valid entities |
| Optional pixels | Owned `uint8[B, 4, 128, 128]`, palette indices 0–15 |
| Optional auxiliary targets | `float32[B, 5, 16, 16]`, independent binary semantic channels |

Global order is `px, py, pvx, pvy, psize, freeze_rate, speed, enemy_est, score, visible_pattern_active, left, right, top, bottom`, using the supplied normalizations. Entity order is `cx, cy, hx, hy, relative_cx, relative_cy, dx, dy, dhx, dhy, gap_x, gap_y, slab_tto, until_lethal, beneficial, lethal_now`. Do not append diagnostic counters, IDs, seeds, or hidden state to these arrays.

`lethal_now` describes an entity's current hazardous phase, not whether it already overlaps the player. Static rectangles require the native fully charged value. Fading rectangles predict no new lethal phase. Signed gaps use `max(entity_min - player_max, player_min - entity_max)` on literal type-specific collision endpoints. Contact time zero and current strict overlap are distinct.

## Observation-only core additions

1. Expose `NativeGame::drawn_warning_lines()` as a borrowed iterator of scene warning lines. Share `rect_warnings_drawn(pattern, rect)` with the renderer: `pattern.timer < 125 && !(pattern.pattern_type == 0 && rect.sh < 2)`. It exposes no timer. The predicate describes the game scene; the wrapper separately handles mode/death, where the renderer substitutes Game Over. Keep stale stored lines when the renderer still draws them.
2. Provide stable enemy birth serials through `NativeGame::enemy_serials()`, parallel to `enemies()`. A private `EnemyRows` newtype owns both vectors and all insertion/removal/clear operations, with no mutable-vector escape. The current source uses order-preserving removal, so serial order remains increasing and the wrapper can merge-match consecutive frames. In-place updates preserve identity. Clear retains the birth counter; restore reassigns serials and the wrapper clears history. Define metadata exhaustion explicitly: preserve gameplay, invalidate the ML identity accessor, and fail closed in the wrapper. Never wrap/reuse IDs, panic, or omit a gameplay insertion to preserve metadata.

Neither addition changes `EnemyState`, `FullState`, snapshot wire data, the reviewed `PrivilegedView` fields, RNG consumption, or gameplay decisions. Previous geometry belongs in the wrapper, avoiding extra per-frame geometry copies in the legacy path. Serial values never enter neural inputs. Restored/new records invalidate history and use logged unknown deltas until observed. Existing matched rows must receive measured growth; filling all growth slots with zero is not a completed implementation. Validate metadata under rendered and headless stepping separately from logical-state parity, and measure overhead. `NativeGame` structural equality can include observation metadata; use live full state or canonical bytes to establish logical equality after restore.

Enemy and rectangle geometry history is updated after every executed raw frame. Rectangle history clears at no-active-pattern, reset, and restore boundaries; indices are stable within an activation. Current source exposes a no-active-pattern interval before later activation. Future target lists, waits, `shown`, and hidden size/lifetime fields must not supply missing history. In particular, `shown` can change one raw frame before visible fading begins.

Version motion as `measured_center_delta_v1`: delta is current minus immediately preceding raw-frame geometry at the final executed frame, not a K-frame average. Enemy/kamikaze/explosion centers are `x + size/2`; half-extents are `size/2`. Powerups use center `(x,y)` and fixed half-extents four, so their internal first-update size change produces no fake growth. Keep literal signed geometry for negative explosion sizes; never sort endpoints, take absolute values, or clamp collision extents. Unknown/history-valid flags and counts stay outside the 16 neural scalars. The supplied analytic formula remains a current estimate; growth and later speed changes mean it is not exact historical center displacement.

For static rectangles, `sh == 2` is lethal now. A positive observed `sh` delta forecasts time to full charge. Negative, flat, or unknown deltas below two yield `until_lethal = 1.0`; no history is not evidence of charging. Report unknown-phase counts. Moving rectangles are hazardous at their current literal collision boxes regardless of `sh`.

## Conservative entity admission, version 1

Evaluate admission at reset observations and decision ends, using the current world-coordinate renderer footprint against inclusive window `[0,127]²`. Keep partly offscreen coordinates without clipping. Do not retain wholly offscreen rows through a sticky seen set in this initial version. Raw-frame geometry history and decision-boundary admission are separate.

- Enemy/kamikaze/explosion: `fx=floor(x)`, `fy=floor(y)`, `s=max(floor(size),0)`; conservative footprint `[fx,fx+s] × [fy,fy+s+1]`, including the shadow row.
- Powerup: conservative circle bounding footprint `[fx-4,fx+4] × [fy-4,fy+5]`.
- Rectangle: renderer-rounded `rx,ry,rw,rh`; conservative footprint `[min(rx,rx+rw),max(rx,rx+rw)] × [min(ry,ry+rh),max(ry,ry+rh)+1]`. Renderer normalization applies only to visual admission; collision endpoints stay literal. This is an envelope of charging corner/outline pixels, not a claim every enclosed pixel is drawn.
- Warning: currently drawn rounded line segment and its shadow at `y+1`. Intersect actual segment footprints, not their enclosing rectangle.

An enemy-family or rectangle row is admitted only when its own conservative footprint intersects the window. This excludes pattern 23's invisible offscreen control without consulting its catalog ID. Zero-size explosions still have a body pixel and a shadow pixel and remain admissible. The enemy renderer clamps the integer visual size to zero before drawing, including for negative-size explosions; collision endpoints remain signed. Warnings set the visible-pattern flag and auxiliary target; they do not disclose an offscreen rectangle's full hidden box. Derive `visible_pattern_active` from admitted rectangles or onscreen drawn warnings. No inactive catalog, pattern ID, or raw active-pattern flag enters the neural tensors.

This is a conservative geometric policy, not proof of pixel observability. Occlusion, circle/outline envelopes, palette aliases, HUD coverage, camera-edge padding, subpixel precision, raw-frame kinematics, and short-history limits remain. Validate single-entity renderer fixtures and negative/over-127 coordinates for admitted boxes. Longer offscreen tracking and warning-announced box admission are later ablations requiring a separately versioned inference rule. Parent reconciliation retains the enemy size clamp after inspecting `render_game`; a secondary review's proposal to reverse negative enemy visual endpoints missed that caller-side clamp and is rejected.

Apply caps after admission. Initially retain 64 enemy-family rows, ordered by `(slab_tto, birth_serial)` for deterministic overflow ties, and log dropped rows. More than 16 admitted rectangles is a contract error, never silent truncation. Retain literal inverted collision intervals as diagnostic/feature geometry, count them, and rasterize no occupancy for their inverted axes. Final capacity acceptance waits for M0 evidence.

## Episodes, reward, and data ownership

- Validate all action IDs and shapes before mutating any slot. Map IDs through the nine existing actions; O/X masks belong only to startup.
- Step up to K=4 raw frames per active slot. Sum raw fixed-point score changes, including death-frame score, add `0.01` only for alive frames, and subtract 5 once on death.
- Use the M0 cap of 18,000 raw gameplay frames, excluding the 13 startup frames; cap changes need a new recorded configuration. Death on the cap frame yields `terminated=true, truncated=false`. Reject unexpected negative score deltas; retry is not an environment action.
- Return separate `terminated`, `truncated`, actual elapsed frames, score, and final observations. An alive time-limit truncation bootstraps; death does not.
- Begin with explicit `reset_done(indices)`. Reject stepping if any slot has ended, before mutating any slot. Require reset indices to be unique, in range, and all ended; validate the whole request first. Reconstruct fresh games, refill all four pixel slots, and return an independently owned subset aligned to the requested index order.
- Rendering a dead state includes Game Over. Skip that pixel push, retain actual terminal privileged features, and mark pixel/state pairing invalid. Do not substitute reset pixels for the terminal state's features. Alive truncations keep valid current pixels and state.
- Copy validated actions into Rust-owned storage before releasing the GIL. Use stable environment slots with Rayon chunks and a persistent pool. Return independently owned NumPy arrays, not views of buffers overwritten by the next step.
- If a native/feature error occurs after parallel stepping begins, poison the batch and require `reset_all`; partial `reset_done` cannot clear poison. Do not claim transactional rollback. Rectangle overflow is an expected validation failure; retain other errors rather than assuming none can occur.

Episode seed ownership is stable by run, environment slot, and episode index, independent of thread scheduling. Use a versioned deterministic hash to `u32`; reject `0xB0000000..0xB00003E7` by deterministic counter rehash. Log the stream definition, batch size, thread/chunk configuration, and actual seeds. Changing batch size changes assignment of episodes to slots. Explicit evaluation seeds are a separate logged mode, never generated training seeds.

## Canonical raster targets

Map world coordinates directly onto canonical 8-pixel patches. Canonical projection already reverses camera translation; do not apply it again. Use literal collision boxes for semantic targets, distinct from inclusive visual footprints. The player channel uses the widest type-specific player box, `p ± player.size` (the powerup box).

Compute patch bounds in signed `i64` Q16.16 units; one cell is `1 << 19`. Define `floor_cell(raw) = raw >> 19` and `ceil_cell(raw) = -((-raw) >> 19)`. A positive interval `[emin,emax)` covers `floor_cell(emin)..=ceil_cell(emax)-1`. A degenerate interval covers only `floor_cell(emin)`, so `(8,8)` maps to patch `(1,1)`. An inverted interval covers nothing and increments a contract counter. Clip selected patch indices to `0..15`, not the stored entity geometry.

Warnings are visual segments with rounded inclusive pixel endpoints. Rasterize the main segment and the shadow segment at `y+1`; do not fill their enclosing rectangle. Keep the five channels independent. The `lethal_soon` channel includes observed charging static rectangles and currently drawn warnings; an unknown/fading rectangle is not labeled as predicted future lethal from a hidden phase field.

## Acceptance order

1. Add and review the two observational interfaces while preserving legacy fingerprints, wire data, and state/RNG parity. Test serial invariants through append/remove/clear, explode-chain appends, dying pairs, lifetime expiry, corner spawns, restart, and restore; include an index-matching regression. Recheck the existing 100×2,000 parity and targeted pattern/mechanic coverage on the changed source, rather than transferring old receipts.
2. Implement pure Rust features, reward, seed/reset logic, overflow behavior, and terminal/truncation handling.
3. Add `crates/dodge-rl-env` with its own lint table, a core-only dependency, GIL release, and owned arrays. Keep PyO3-specific unsafe allowances out of `dodge-core`.
4. Test strict edges, point players, zero explosions, charging/fading, warning visibility, pattern 23, overflow, death plus pickup, ragged K steps, reset history, hidden-state invariance with phenotype/history held fixed, and array independence.
5. Reuse the frozen Milestone 0 heuristic without semantic duplication to cross-check full and vectorized episodes. Validation-only snapshots can be used; exclude their cost from production throughput.
6. Check trajectories across thread/chunk configurations; run the required 100,000-step post-warmup memory check and actual headless/rendered benchmarks with retained samples.
7. Freeze/review source and contract manifests before curriculum PPO. Snapshot recovery and student work remain deferred.
