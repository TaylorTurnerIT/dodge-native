//! The VelocityFlow observation from LaunchSpark/DodgeAI (`dodge/observe.py`),
//! encoded natively so a training step never walks entities in Python.
//!
//! Layout, in order:
//!     0..3        px, py, dpx, dpy  -- position normalised, velocity scaled
//!     4..1027     categorical cell values, normalised by CELL_TYPES
//!     1028..2051  vx of whatever occupies each cell
//!     2052..3075  vy of the same
//!
//! Every rule here mirrors the Python encoder line for line; the parity test
//! on the Python side compares the two on live games.
//!
//! Ported from TaylorTurnerIT/dodge-ai-3 velocity-flow
//! `native/crates/dodge-batch/src/velocity.rs`. The only changes are the
//! names (`VELOCITY_FLOW_*`, `encode_velocity_flow`) and reading the global
//! speed and freeze rate through `privileged_view()`, the upstream core's
//! accessor for them.

use dodge_core::NativeGame;

pub const GRID_SIZE: usize = 32;
pub const CELL_COUNT: usize = GRID_SIZE * GRID_SIZE;
pub const PLAYER_VALUES: usize = 4;
pub const VELOCITY_FLOW_SIZE: usize = PLAYER_VALUES + 3 * CELL_COUNT;
/// Bump whenever any value's meaning, order or count changes. Checkpoints
/// trained on one encoding play worse, silently, on another.
pub const VELOCITY_FLOW_VERSION: &str = "velocity_flow_3076_v1";

const CELL_SIZE: f64 = 4.0;
const CELL_TYPES: f32 = 8.0;
pub(crate) const VELOCITY_SCALE: f32 = 4.0;
// How long the cart draws a side-entering pattern's warning lines.
const WARNING_FRAMES: f64 = 125.0;

const ENEMY_NORMAL: u8 = 1;
const ENEMY_KAMIKAZE: u8 = 2;
const ENEMY_BLAST: u8 = 3;
const PICKUP_EXPLODE: u8 = 4;
const PICKUP_FREEZE: u8 = 5;
const PICKUP_SHRINK: u8 = 6;
const HAZARD_WARNING: u8 = 7;
const HAZARD_LETHAL: u8 = 8;

/// Which entity keeps a contested cell, ranked by how much it matters to
/// staying alive (`PAINT_PRIORITY` in observe.py).
const fn paint_priority(value: u8) -> u8 {
    match value {
        HAZARD_LETHAL => 6,
        ENEMY_BLAST => 5,
        ENEMY_KAMIKAZE => 4,
        ENEMY_NORMAL => 3,
        HAZARD_WARNING => 2,
        _ => 1,
    }
}

const fn enemy_cell(personality: i8) -> u8 {
    match personality {
        1 => ENEMY_KAMIKAZE,
        -1 => ENEMY_BLAST,
        2 => PICKUP_EXPLODE,
        3 => PICKUP_FREEZE,
        4 => PICKUP_SHRINK,
        _ => ENEMY_NORMAL,
    }
}

#[derive(Clone, Copy, Default)]
struct Cell {
    value: u8,
    rank: u8,
    vx: f32,
    vy: f32,
}

struct Grid {
    cells: [Cell; CELL_COUNT],
}

impl Grid {
    fn new() -> Self {
        Self {
            cells: [Cell::default(); CELL_COUNT],
        }
    }

    /// Paint every 4px cell touched by an axis-aligned rectangle.
    fn paint(&mut self, x: f64, y: f64, width: f64, height: f64, value: u8, velocity: (f64, f64)) {
        if width <= 0.0 || height <= 0.0 {
            return;
        }
        let last = GRID_SIZE as i64 - 1;
        let left = ((x / CELL_SIZE).floor() as i64).max(0);
        let top = ((y / CELL_SIZE).floor() as i64).max(0);
        let right = (((x + width - 1e-9) / CELL_SIZE).floor() as i64).min(last);
        let bottom = (((y + height - 1e-9) / CELL_SIZE).floor() as i64).min(last);
        if left > right || top > bottom {
            return;
        }
        let rank = paint_priority(value);
        let rows = self
            .cells
            .chunks_mut(GRID_SIZE)
            .skip(top as usize)
            .take((bottom - top + 1) as usize);
        for row in rows {
            for cell in row
                .iter_mut()
                .skip(left as usize)
                .take((right - left + 1) as usize)
            {
                if cell.rank < rank {
                    // The winner of the cell supplies its velocity too.
                    *cell = Cell {
                        value,
                        rank,
                        vx: velocity.0 as f32,
                        vy: velocity.1 as f32,
                    };
                }
            }
        }
    }
}

/// Write one game's observation into `out`, which must hold
/// `VELOCITY_FLOW_SIZE` values.
pub fn encode_velocity_flow(game: &NativeGame, out: &mut [f32]) {
    debug_assert_eq!(out.len(), VELOCITY_FLOW_SIZE);
    let player = game.player();
    let speed_scale = f64::from(VELOCITY_SCALE);
    let player_values = [
        (player.x.to_double() / 127.0).clamp(0.0, 1.0) as f32,
        (player.y.to_double() / 127.0).clamp(0.0, 1.0) as f32,
        (player.vx.to_double() / speed_scale).clamp(-1.0, 1.0) as f32,
        (player.vy.to_double() / speed_scale).clamp(-1.0, 1.0) as f32,
    ];
    for (slot, value) in out.iter_mut().zip(player_values) {
        *slot = value;
    }

    let mut grid = Grid::new();
    let view = game.privileged_view();
    let freeze = view.freeze_rate.to_double();
    // Enemies move by vx * spd * frz * e.spd, so velocities are real pixels.
    let step = view.speed.to_double() * freeze;
    for enemy in game.enemies() {
        let value = enemy_cell(enemy.personality);
        let own = step * enemy.speed.to_double();
        let velocity = (enemy.vx.to_double() * own, enemy.vy.to_double() * own);
        let x = enemy.x.to_double();
        let y = enemy.y.to_double();
        if enemy.personality >= 2 {
            grid.paint(x - 4.0, y - 4.0, 8.0, 8.0, value, velocity);
        } else {
            let size = enemy.size.to_double();
            grid.paint(x, y, size, size, value, velocity);
        }
    }

    let pattern = game
        .active_pattern_index()
        .and_then(|index| game.patterns().get(index));
    if let Some(pattern) = pattern {
        let lethal_pattern = pattern.pattern_type == 1;
        let telegraphed = pattern.timer.to_double() < WARNING_FRAMES;
        for rect in &pattern.rects {
            let lethal = lethal_pattern || rect.sh.to_double() == 2.0;
            let value = if lethal {
                HAZARD_LETHAL
            } else {
                HAZARD_WARNING
            };
            let rate = rect.speed.to_double();
            let velocity = (
                rect.dx.to_double() * rate * freeze,
                rect.dy.to_double() * rate * freeze,
            );
            grid.paint(
                rect.x.to_double(),
                rect.y.to_double(),
                rect.width.to_double(),
                rect.height.to_double(),
                value,
                velocity,
            );
            if telegraphed {
                for line in &rect.warnings {
                    let (x1, y1) = (line.x0.to_double(), line.y0.to_double());
                    let (x2, y2) = (line.x1.to_double(), line.y1.to_double());
                    grid.paint(
                        x1.min(x2),
                        y1.min(y2),
                        (x2 - x1).abs().max(1.0),
                        (y2 - y1).abs().max(1.0),
                        HAZARD_WARNING,
                        velocity,
                    );
                }
            }
        }
    }

    // Cells drive each zip so a finished plane never pulls a slot from the
    // next one.
    let mut planes = out.iter_mut().skip(PLAYER_VALUES);
    for (cell, slot) in grid.cells.iter().zip(planes.by_ref()) {
        *slot = f32::from(cell.value) / CELL_TYPES;
    }
    for (cell, slot) in grid.cells.iter().zip(planes.by_ref()) {
        *slot = (cell.vx / VELOCITY_SCALE).clamp(-1.0, 1.0);
    }
    for (cell, slot) in grid.cells.iter().zip(planes) {
        *slot = (cell.vy / VELOCITY_SCALE).clamp(-1.0, 1.0);
    }
}
