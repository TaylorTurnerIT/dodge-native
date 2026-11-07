//! Plan by rolling a learned enemy model forward, in place of the engine.
//!
//! The enemy model is a port-Hamiltonian system learned from trajectories only
//! (`hnn/physics.py`): `H = 1/2 |p|^2 + U(q_enemy - q_player, kind)`, with a learned damping.
//! The player moves by its own known motion rule. For each of the nine actions the planner
//! rolls the player and every enemy forward `horizon` frames, then scores the rollout with the
//! same collision, clearance and wall terms that the lookahead policy uses.
//!
//! What it assumes without learning it: an enemy has its full size of 3 px, the clock rate
//! stays what it is now, an enemy bounces off the arena edge (sign flip at -2 and 129 - size, as
//! seen in replays), and what else it learns is in the event layer.

use std::sync::OnceLock;

use dodge_core::{Action, NativeGame};
use serde::Deserialize;

use crate::box_clearance;

/// Enemies grow to this size. The model sees the current size, which can be smaller.
const ADULT_SIZE: f64 = 3.0;
/// Pull toward the middle of the arena, scored at the end of a rollout.
const GOAL_WEIGHT: f64 = 0.3;

/// QUICK CHECK ONLY (not part of the learned model): extra cost for being close to a
/// kamikaze, whose death turns into an explosion. Read from `HNN_KAMIKAZE_MARGIN`
/// (cost units, default 0 = off) and `HNN_KAMIKAZE_RADIUS` (pixels, default 20).
fn kamikaze_margin() -> (f64, f64) {
    static VALUE: OnceLock<(f64, f64)> = OnceLock::new();
    *VALUE.get_or_init(|| {
        let read = |name: &str, default: f64| {
            std::env::var(name)
                .ok()
                .and_then(|text| text.parse().ok())
                .unwrap_or(default)
        };
        (
            read("HNN_KAMIKAZE_MARGIN", 0.0),
            read("HNN_KAMIKAZE_RADIUS", 20.0),
        )
    })
}

#[derive(Clone, Debug, Deserialize)]
struct Layer {
    weights: Vec<Vec<f64>>,
    bias: Vec<f64>,
}

/// Learned pair-collision classifier (`hnn/events.py`).
#[derive(Clone, Debug, Deserialize)]
struct Collision {
    near: f64,
    layers: Vec<Layer>,
}

/// Explosion size law measured from observed explosions: grows by `rate` per frame
/// from `start` to `peak`, then shrinks at the same rate.
#[derive(Clone, Copy, Debug, Deserialize)]
struct Blast {
    start: f64,
    rate: f64,
    peak: f64,
}

#[derive(Clone, Debug, Deserialize)]
pub struct PhysicsModel {
    layers: Vec<Layer>,
    gamma: f64,
    #[serde(default)]
    collision: Option<Collision>,
    #[serde(default)]
    blast: Option<Blast>,
    #[serde(default)]
    rect: Option<RectLaw>,
    #[serde(default)]
    crush: Option<Crush>,
    #[serde(default)]
    spawn: Option<Spawn>,
    /// Post-bounce enemy speed against game speed, per difficulty (`hnn/bounce_curve.py`).
    #[serde(default)]
    bounce_curve: std::collections::HashMap<String, BounceCurve>,
    /// The learned force sampled on a grid, built once on load. See `ForceTable`.
    #[serde(skip)]
    table: Option<ForceTable>,
}

/// The learned force `-dU/d(offset)` tabulated over enemy-to-player offsets, for fast lookup.
/// The network is smooth at the scale of the grid (0.5 px), so bilinear interpolation
/// reproduces it closely (see the `table_matches_the_network` test). Beyond the grid the
/// edge value is used.
#[derive(Clone, Debug)]
struct ForceTable {
    /// `[kind][row * side + column]` of `(fx, fy)`; row = y offset, column = x offset.
    values: Vec<Vec<[f32; 2]>>,
}

const TABLE_RANGE: f64 = 132.0;
const TABLE_STEP: f64 = 0.5;
const TABLE_KINDS: usize = 2;

fn table_side() -> usize {
    (2.0 * TABLE_RANGE / TABLE_STEP) as usize + 1
}

/// Post-bounce speed as a function of the game speed, measured from observed bounces.
/// Each list holds `[game speed, bounce speed]` points in rising order.
#[derive(Clone, Debug, Deserialize)]
struct BounceCurve {
    #[serde(rename = "static")]
    fixed: Vec<[f64; 2]>,
    moving: Vec<[f64; 2]>,
}

fn curve_at(points: &[[f64; 2]], x: f64) -> Option<f64> {
    let first = points.first()?;
    let last = points.last()?;
    if x <= first[0] {
        return Some(first[1]);
    }
    if x >= last[0] {
        return Some(last[1]);
    }
    points.windows(2).find(|w| x <= w[1][0]).map(|w| {
        let t = (x - w[0][0]) / (w[1][0] - w[0][0]).max(1e-9);
        w[0][1] + t * (w[1][1] - w[0][1])
    })
}

impl PhysicsModel {
    /// Bounce speeds (static rectangle, moving rectangle) for the game as it stands now.
    fn bounce_speeds(&self, game: &NativeGame, law: &RectLaw) -> (f64, f64) {
        let speed = if crate::observe::enabled() {
            return (law.bounce_static, law.bounce_moving);
        } else {
            game.privileged_view().speed.to_double()
        };
        match self.bounce_curve.get(&game.difficulty().to_string()) {
            Some(curve) => (
                curve_at(&curve.fixed, speed).unwrap_or(law.bounce_static),
                curve_at(&curve.moving, speed).unwrap_or(law.bounce_moving),
            ),
            None => (law.bounce_static, law.bounce_moving),
        }
    }
}

/// Pattern-rectangle law measured from observed frames (`hnn/events.py`): a static rectangle's
/// warning progress rises by `sh_step` per frame and it is lethal once progress reaches `lethal_at`.
#[derive(Clone, Copy, Debug, Deserialize)]
struct RectLaw {
    sh_step: f64,
    lethal_at: f64,
    /// Speed an enemy leaves a full-progress rectangle at, measured per rectangle type
    /// (`hnn/bounce.py`). Zero turns the bounce off.
    #[serde(default)]
    bounce_static: f64,
    #[serde(default)]
    bounce_moving: f64,
}

/// Where new enemies appear and how often (`hnn/spawns.py`, measured from observed frames).
#[derive(Clone, Debug, Deserialize)]
struct Spawn {
    points: Vec<SpawnPoint>,
    /// A player closer than this to a spawn point is in the way of a new enemy.
    radius: f64,
}

#[derive(Clone, Debug, Deserialize)]
struct SpawnPoint {
    x: f64,
    y: f64,
    /// Births per frame at any time.
    rate_default: f64,
    /// Births per frame while this many pattern rectangles are active.
    rate_by_rects: std::collections::HashMap<String, f64>,
}

/// Learned classifier for "a moving rectangle destroys an enemy it overlaps" (`hnn/crush.py`).
#[derive(Clone, Debug, Deserialize)]
struct Crush {
    mean: Vec<f64>,
    std: Vec<f64>,
    layers: Vec<Layer>,
}

/// Probability above which a moving rectangle is taken to destroy an overlapping enemy.
/// Read from `HNN_CRUSH_THRESHOLD` (default 0.5).
fn crush_threshold() -> f64 {
    static VALUE: OnceLock<f64> = OnceLock::new();
    *VALUE.get_or_init(|| {
        std::env::var("HNN_CRUSH_THRESHOLD")
            .ok()
            .and_then(|t| t.parse().ok())
            .unwrap_or(0.5)
    })
}

/// A pattern rectangle as the planner sees it: `x, y, width, height, progress, moving`.
pub type RectSnapshot = Vec<[f64; 6]>;

/// The active pattern's rectangles in the current frame.
pub fn rect_snapshot(game: &NativeGame) -> RectSnapshot {
    let view = game.privileged_view();
    let Some(pattern) = view.active_pattern else {
        return Vec::new();
    };
    let moving = if pattern.pattern_type == 1 { 1.0 } else { 0.0 };
    pattern
        .rects
        .iter()
        .map(|rect| {
            [
                rect.x.to_double(),
                rect.y.to_double(),
                rect.width.to_double(),
                rect.height.to_double(),
                rect.sh.to_double(),
                moving,
            ]
        })
        .collect()
}

thread_local! {
    /// The previous frame's rectangles. The planner needs one frame of history to see how
    /// a rectangle is moving, because rectangle velocity is not part of what a player sees.
    static HISTORY: std::cell::RefCell<RectSnapshot> = const { std::cell::RefCell::new(Vec::new()) };
}

/// Tell the planner what the rectangles looked like one frame ago.
pub fn set_history(previous: RectSnapshot) {
    HISTORY.with(|slot| *slot.borrow_mut() = previous);
}

#[derive(Clone, Copy, Debug)]
struct RectBody {
    x: f64,
    y: f64,
    w: f64,
    h: f64,
    vx: f64,
    vy: f64,
    vw: f64,
    vh: f64,
    progress: f64,
    /// +1 rising, -1 falling, 0 steady (from the change since the previous frame).
    trend: f64,
    moving: bool,
}

fn read_rects(game: &NativeGame) -> Vec<RectBody> {
    let current = rect_snapshot(game);
    HISTORY.with(|slot| {
        let previous = slot.borrow();
        let known = previous.len() == current.len();
        current
            .iter()
            .enumerate()
            .map(|(index, now)| {
                let before = if known { previous[index] } else { *now };
                let change = now[4] - before[4];
                RectBody {
                    x: now[0],
                    y: now[1],
                    w: now[2],
                    h: now[3],
                    vx: now[0] - before[0],
                    vy: now[1] - before[1],
                    vw: now[2] - before[2],
                    vh: now[3] - before[3],
                    progress: now[4],
                    trend: if change > 1e-3 {
                        1.0
                    } else if change < -1e-3 {
                        -1.0
                    } else {
                        0.0
                    },
                    moving: now[5] > 0.5,
                }
            })
            .collect()
    })
}

/// An enemy about to enter a full-progress rectangle is pushed out along the axis it overlaps
/// least, at the measured bounce speed (249 of 251 observed velocity changes pointed away).
fn bounce_off(body: &mut Body, rect: &RectBody, law: &RectLaw, speeds: (f64, f64)) {
    let speed = if rect.moving { speeds.1 } else { speeds.0 };
    if speed <= 0.0 || rect.progress < law.lethal_at - 1e-6 {
        return;
    }
    let inside = body.x + body.vx < rect.x + rect.w
        && body.x + body.size > rect.x
        && body.y + body.size > rect.y
        && body.y + body.vy < rect.y + rect.h;
    if !inside {
        return;
    }
    // Each axis along which the enemy's box sticks out past the rectangle is pushed away at the
    // bounce speed. Observed bounces change both axes in about 64% of cases.
    if body.x + body.vx < rect.x {
        body.vx = -speed;
    } else if body.x + body.vx + body.size > rect.x + rect.w {
        body.vx = speed;
    }
    if body.y + body.vy < rect.y {
        body.vy = -speed;
    } else if body.y + body.vy + body.size > rect.y + rect.h {
        body.vy = speed;
    }
}

fn rect_lethal(rect: &RectBody, law: &RectLaw) -> bool {
    rect.moving || rect.progress >= law.lethal_at - 1e-6
}

/// The game's visible hit rule for a rectangle (player box against rectangle box).
fn rect_hits(px: f64, py: f64, size: f64, rect: &RectBody) -> bool {
    px - 2.0 + size > rect.x
        && py - 2.0 + size > rect.y
        && px + 2.0 - size < rect.x + rect.w - 1.0
        && py + 2.0 - size < rect.y + rect.h - 1.0
}

fn rect_gap(px: f64, py: f64, size: f64, rect: &RectBody) -> f64 {
    let gap_x = (rect.x - (px + size - 1.0))
        .max((px - size + 1.0) - (rect.x + rect.w))
        .max(0.0);
    let gap_y = (rect.y - (py + size - 1.0))
        .max((py - size + 1.0) - (rect.y + rect.h))
        .max(0.0);
    gap_x.hypot(gap_y)
}

/// Probability above which two enemies are treated as colliding. Read from
/// `HNN_COLLISION_THRESHOLD` (default 0.3: a missed collision costs more than a false one).
fn collision_threshold() -> f64 {
    static VALUE: OnceLock<f64> = OnceLock::new();
    *VALUE.get_or_init(|| {
        std::env::var("HNN_COLLISION_THRESHOLD")
            .ok()
            .and_then(|t| t.parse().ok())
            .unwrap_or(0.3)
    })
}

fn mlp_forward(layers: &[Layer], input: &[f64]) -> f64 {
    let mut current = input.to_vec();
    let last = layers.len().saturating_sub(1);
    for (index, layer) in layers.iter().enumerate() {
        let mut next = Vec::with_capacity(layer.bias.len());
        for (row, bias) in layer.weights.iter().zip(&layer.bias) {
            let mut sum = *bias;
            for (weight, value) in row.iter().zip(&current) {
                sum += weight * value;
            }
            next.push(if index == last { sum } else { sum.tanh() });
        }
        current = next;
    }
    current.first().copied().unwrap_or(0.0)
}

impl PhysicsModel {
    pub fn from_json(text: &str) -> Result<Self, String> {
        let mut model: Self = serde_json::from_str(text)
            .map_err(|error| format!("could not parse physics model: {error}"))?;
        model.table = Some(model.build_table());
        Ok(model)
    }

    /// Sample the network's force on the grid, on all cores.
    fn build_table(&self) -> ForceTable {
        let side = table_side();
        let threads = crate::worker_threads();
        let mut values = Vec::with_capacity(TABLE_KINDS);
        for kind in 0..TABLE_KINDS {
            let mut grid = vec![[0.0_f32; 2]; side * side];
            let chunk = side.div_ceil(threads).max(1);
            std::thread::scope(|scope| {
                for (index, rows) in grid.chunks_mut(chunk * side).enumerate() {
                    scope.spawn(move || {
                        for (local, cell) in rows.iter_mut().enumerate() {
                            let row = index * chunk + local / side;
                            let column = local % side;
                            let dy = row as f64 * TABLE_STEP - TABLE_RANGE;
                            let dx = column as f64 * TABLE_STEP - TABLE_RANGE;
                            let (fx, fy) = self.force(dx, dy, kind);
                            *cell = [fx as f32, fy as f32];
                        }
                    });
                }
            });
            values.push(grid);
        }
        ForceTable { values }
    }

    /// The force from the table (bilinear). Falls back to the network if there is no table.
    #[inline]
    fn force_fast(&self, dx: f64, dy: f64, kind: usize) -> (f64, f64) {
        let Some(table) = &self.table else {
            return self.force(dx, dy, kind);
        };
        let side = table_side();
        let grid = &table.values[kind.min(TABLE_KINDS - 1)];
        let limit = (side - 1) as f64 - 1e-9;
        let fx = ((dx.clamp(-TABLE_RANGE, TABLE_RANGE) + TABLE_RANGE) / TABLE_STEP).min(limit);
        let fy = ((dy.clamp(-TABLE_RANGE, TABLE_RANGE) + TABLE_RANGE) / TABLE_STEP).min(limit);
        let (cx, cy) = (fx as usize, fy as usize);
        let (tx, ty) = (fx - cx as f64, fy - cy as f64);
        let at = |row: usize, column: usize| grid[row * side + column];
        let (a, b, c, d) = (
            at(cy, cx),
            at(cy, cx + 1),
            at(cy + 1, cx),
            at(cy + 1, cx + 1),
        );
        let mix = |i: usize| {
            let top = f64::from(a[i]) * (1.0 - tx) + f64::from(b[i]) * tx;
            let bottom = f64::from(c[i]) * (1.0 - tx) + f64::from(d[i]) * tx;
            top * (1.0 - ty) + bottom * ty
        };
        (mix(0), mix(1))
    }

    /// Force on an enemy at `(dx, dy)` from the player: `-dU/d(offset)`.
    fn force(&self, dx: f64, dy: f64, kind: usize) -> (f64, f64) {
        let mut input = vec![0.0; 7];
        input[0] = dx / 64.0;
        input[1] = dy / 64.0;
        input[2 + kind.min(4)] = 1.0;
        let mut activations: Vec<Vec<f64>> = vec![input];
        let last = self.layers.len().saturating_sub(1);
        for (index, layer) in self.layers.iter().enumerate() {
            let previous = &activations[index];
            let mut next = Vec::with_capacity(layer.bias.len());
            for (row, bias) in layer.weights.iter().zip(&layer.bias) {
                let mut sum = *bias;
                for (weight, value) in row.iter().zip(previous) {
                    sum += weight * value;
                }
                next.push(if index == last { sum } else { sum.tanh() });
            }
            activations.push(next);
        }
        // Back-propagate d(output)/d(input).
        let mut gradient = vec![1.0];
        for index in (0..self.layers.len()).rev() {
            if index != last {
                for (value, activation) in gradient.iter_mut().zip(&activations[index + 1]) {
                    *value *= 1.0 - activation * activation;
                }
            }
            let layer = &self.layers[index];
            let width = activations[index].len();
            let mut previous = vec![0.0; width];
            for (row, upstream) in layer.weights.iter().zip(&gradient) {
                for (slot, weight) in previous.iter_mut().zip(row) {
                    *slot += weight * upstream;
                }
            }
            gradient = previous;
        }
        (-gradient[0] / 64.0, -gradient[1] / 64.0)
    }
}

#[derive(Clone, Copy, Debug)]
struct Body {
    x: f64,
    y: f64,
    vx: f64,
    vy: f64,
    size: f64,
    kind: usize,
    rate: f64,
    moves: bool,
    /// An explosion: fixed centre, size follows the learned law.
    blast: bool,
    growing: bool,
    /// Marked for removal; a predicted pair collision may remain for one extra frame.
    dying: bool,
    /// Collision predictions use a one-frame-ahead feature; keep the body for that frame.
    collision_delay: bool,
    /// Has been seen between x = 1 and x = 128. Only such enemies bounce off the arena edge.
    inside: bool,
}

/// QUICK CHECK ONLY: perception noise. `HNN_NOISE_PX` (pixels, default 0 = off) is the standard
/// deviation of an independent error on every enemy position on every frame. Velocity gets
/// `sigma * HNN_NOISE_VEL / rate`; the default factor sqrt(2) is a two-frame difference, and
/// a five-frame linear fit gives about 0.35. A factor of 0 leaves velocity exact.
fn noise_sigma() -> f64 {
    static VALUE: OnceLock<f64> = OnceLock::new();
    *VALUE.get_or_init(|| {
        std::env::var("HNN_NOISE_PX")
            .ok()
            .and_then(|t| t.parse().ok())
            .unwrap_or(0.0)
    })
}

fn gaussian() -> f64 {
    use std::cell::Cell;
    thread_local!(static STATE: Cell<u64> = const { Cell::new(0x2545_F491_4F6C_DD1D) });
    STATE.with(|state| {
        let mut sum = 0.0;
        for _ in 0..12 {
            let mut x = state.get();
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            state.set(x);
            sum += (x >> 11) as f64 / (1u64 << 53) as f64;
        }
        sum - 6.0
    })
}

fn read_bodies(game: &NativeGame) -> Vec<Body> {
    let mut bodies = if crate::observe::enabled() {
        read_observed_bodies()
    } else {
        read_exact_bodies(game)
    };
    let sigma = noise_sigma();
    if sigma > 0.0 {
        for body in bodies.iter_mut().filter(|body| body.moves) {
            body.x += sigma * gaussian();
            body.y += sigma * gaussian();
            let factor = std::env::var("HNN_NOISE_VEL")
                .ok()
                .and_then(|text| text.parse::<f64>().ok())
                .unwrap_or(std::f64::consts::SQRT_2);
            let velocity_sigma = sigma * factor / body.rate.abs().max(0.2);
            body.vx += velocity_sigma * gaussian();
            body.vy += velocity_sigma * gaussian();
        }
    }
    bodies
}

fn read_observed_bodies() -> Vec<Body> {
    crate::observe::tracks()
        .into_iter()
        .filter_map(|track| {
            let sample = *track.samples.back()?;
            let (vx, vy) = track.velocity();
            let moves = sample.kind >= 0;
            Some(Body {
                x: sample.x,
                y: sample.y,
                vx,
                vy,
                size: if moves {
                    sample.size.max(ADULT_SIZE)
                } else {
                    sample.size
                },
                kind: usize::from(sample.kind == 1),
                rate: 1.0,
                moves,
                blast: sample.kind == -1,
                growing: track.growing(),
                dying: false,
                collision_delay: false,
                inside: track.inside,
            })
        })
        .collect()
}

fn read_exact_bodies(game: &NativeGame) -> Vec<Body> {
    let view = game.privileged_view();
    let step = view.speed.to_double() * view.freeze_rate.to_double();
    game.enemies()
        .iter()
        // Bonus and bomb pickups are not threats.
        .filter(|enemy| enemy.personality < 2)
        .map(|enemy| {
            let moves = enemy.personality >= 0;
            Body {
                x: enemy.x.to_double(),
                y: enemy.y.to_double(),
                vx: enemy.vx.to_double(),
                vy: enemy.vy.to_double(),
                size: if moves {
                    enemy.size.to_double().max(ADULT_SIZE)
                } else {
                    enemy.size.to_double()
                },
                kind: usize::from(enemy.personality == 1),
                rate: step * enemy.speed.to_double(),
                moves,
                blast: enemy.personality == -1,
                growing: enemy.isizing,
                dying: enemy.is_dying,
                collision_delay: false,
                inside: enemy.inside,
            }
        })
        .collect()
}

const DIRECTIONS: [(f64, f64); 9] = [
    (0.0, 0.0),
    (-1.0, 0.0),
    (1.0, 0.0),
    (0.0, -1.0),
    (0.0, 1.0),
    (-1.0, -1.0),
    (1.0, -1.0),
    (-1.0, 1.0),
    (1.0, 1.0),
];

/// Features of an enemy pair; must match `pair_features` in `hnn/events.py`.
fn pair_features(a: &Body, b: &Body) -> [f64; 10] {
    let mut f = [0.0; 10];
    for (slot, step) in [0.0, 1.0].iter().enumerate() {
        let (ax, ay) = (a.x + a.vx * a.rate * step, a.y + a.vy * a.rate * step);
        let (bx, by) = (b.x + b.vx * b.rate * step, b.y + b.vy * b.rate * step);
        let ox = (ax + a.size).min(bx + b.size) - ax.max(bx);
        let oy = (ay + a.size).min(by + b.size) - ay.max(by);
        f[slot * 3] = ox / 4.0;
        f[slot * 3 + 1] = oy / 4.0;
        f[slot * 3 + 2] = ox.min(oy) / 4.0;
    }
    f[6] = a.size / 4.0;
    f[7] = b.size / 4.0;
    f[8] = a.kind as f64;
    f[9] = b.kind as f64;
    f
}

/// Apply the learned event layer for one frame: remove enemies that were marked dying
/// (a kamikaze leaves an explosion), mark new colliding pairs, and grow or shrink explosions.
fn apply_events(model: &PhysicsModel, enemies: &mut Vec<Body>) {
    let (Some(collision), Some(blast)) = (&model.collision, &model.blast) else {
        return;
    };
    // Explosions follow the size law around a fixed centre.
    for body in enemies.iter_mut().filter(|body| body.blast) {
        let centre = (body.x + body.size / 2.0, body.y + body.size / 2.0);
        if body.growing {
            body.size += blast.rate;
            if body.size >= blast.peak {
                body.growing = false;
            }
        } else {
            body.size -= blast.rate;
        }
        body.x = centre.0 - body.size / 2.0;
        body.y = centre.1 - body.size / 2.0;
    }
    enemies.retain(|body| !body.blast || body.size > 0.0);

    // Enemies marked on the previous frame leave now.
    let mut born = Vec::new();
    enemies.retain_mut(|body| {
        if body.dying && !body.blast {
            if body.collision_delay {
                body.collision_delay = false;
                return true;
            }
            if body.kind == 1 {
                born.push(Body {
                    x: body.x + body.size / 2.0 - blast.start / 2.0,
                    y: body.y + body.size / 2.0 - blast.start / 2.0,
                    vx: 0.0,
                    vy: 0.0,
                    size: blast.start,
                    kind: 0,
                    rate: 1.0,
                    moves: false,
                    blast: true,
                    growing: true,
                    dying: false,
                    collision_delay: false,
                    inside: true,
                });
            }
            false
        } else {
            true
        }
    });
    enemies.extend(born);

    // New collisions among enemies that are inside the arena.
    let threshold = collision_threshold();
    let count = enemies.len();
    let mut marks = Vec::new();
    for i in 0..count {
        for j in (i + 1)..count {
            let (a, b) = (&enemies[i], &enemies[j]);
            if a.blast || b.blast || a.dying || b.dying || !a.moves || !b.moves {
                continue;
            }
            if !(1.0..=128.0).contains(&a.x) || !(1.0..=128.0).contains(&b.x) {
                continue;
            }
            if (a.x - b.x).hypot(a.y - b.y) > collision.near {
                continue;
            }
            let logit = mlp_forward(&collision.layers, &pair_features(a, b));
            if 1.0 / (1.0 + (-logit).exp()) > threshold {
                marks.push((i, j));
            }
        }
    }
    for (i, j) in marks {
        enemies[i].dying = true;
        enemies[j].dying = true;
        enemies[i].collision_delay = true;
        enemies[j].collision_delay = true;
    }
}

fn hits(px: f64, py: f64, size: f64, body: &Body) -> bool {
    px + size - 1.0 > body.x
        && py + size - 1.0 > body.y
        && px - size + 1.0 < body.x + body.size
        && py - size + 1.0 < body.y + body.size
}

fn wall_penalty(x: f64, y: f64) -> f64 {
    (8.0 - x).max(0.0) + (x - 120.0).max(0.0) + (8.0 - y).max(0.0) + (y - 120.0).max(0.0)
}

/// What one imagined rollout produced.
#[derive(Clone, Debug)]
pub struct Rollout {
    pub cost: f64,
    /// First frame on which the model predicts a hit, if any.
    pub first_hit: Option<u32>,
    /// Enemy `x, y, size` after `snapshot_at` frames, in the engine's enemy order.
    pub snapshot: Vec<[f64; 3]>,
}

/// Roll the player and enemies forward while playing `direction`, and score the result.
fn rollout(
    model: &PhysicsModel,
    game: &NativeGame,
    bodies: &[Body],
    direction: (f64, f64),
    horizon: u32,
    snapshot_at: u32,
) -> Rollout {
    let player = game.player();
    let size = player.size.to_double();
    let (mut px, mut py) = (player.x.to_double(), player.y.to_double());
    let (mut pvx, mut pvy) = (player.vx.to_double(), player.vy.to_double());
    let mut enemies = bodies.to_vec();
    let mut rects = read_rects(game);
    let law = model.rect;
    let speeds = law.map_or((0.0, 0.0), |law| model.bounce_speeds(game, &law));
    let rect_count = rects.len();
    let mut cost = 0.0;
    let mut clearance = f64::INFINITY;
    let mut first_hit = None;
    let mut snapshot = Vec::new();

    for frame in 1..=horizon {
        // The engine checks for a hit first, then moves the player, then moves the enemies.
        let rect_hit = law.is_some_and(|law| {
            rects
                .iter()
                .any(|rect| rect_lethal(rect, &law) && rect_hits(px, py, size, rect))
        });
        if rect_hit || enemies.iter().any(|body| hits(px, py, size, body)) {
            cost += 5_000.0 - 50.0 * f64::from(frame);
            clearance = 0.0;
            first_hit = Some(frame);
            break;
        }
        pvx = 0.8 * pvx + 0.5 * direction.0;
        pvy = 0.8 * pvy + 0.5 * direction.1;
        px = (px + pvx).clamp(2.0, 125.0);
        py = (py + pvy).clamp(2.0, 125.0);
        // Expected cost of standing where a new enemy is likely to appear.
        if let Some(spawn) = &model.spawn {
            for point in &spawn.points {
                if (px - point.x).hypot(py - point.y) < spawn.radius {
                    let rate = point.rate_default
                        + point
                            .rate_by_rects
                            .get(&rect_count.to_string())
                            .copied()
                            .unwrap_or(0.0);
                    cost += rate * (5_000.0 - 50.0 * f64::from(frame));
                }
            }
        }
        let mut gap = f64::INFINITY;
        let (margin, radius) = kamikaze_margin();
        for body in &mut enemies {
            if margin > 0.0 && body.kind == 1 && body.moves {
                let distance = (px - body.x - body.size / 2.0).hypot(py - body.y - body.size / 2.0);
                if distance < radius {
                    cost += margin * (radius - distance) / radius;
                }
            }
            if body.moves {
                let (fx, fy) = model.force_fast(body.x - px, body.y - py, body.kind);
                body.vx += fx - model.gamma * body.vx;
                body.vy += fy - model.gamma * body.vy;
                if let Some(law) = &law {
                    for rect in &rects {
                        bounce_off(body, rect, law, speeds);
                    }
                }
                // Arena edge: an enemy that has entered turns around at the edge. The test uses
                // the position before this frame's move. Speed is kept; only the sign flips.
                if body.inside {
                    if body.y >= 129.0 - body.size {
                        body.vy = -body.vy.abs();
                    } else if body.y <= -2.0 {
                        body.vy = body.vy.abs();
                    }
                    if body.x >= 129.0 - body.size {
                        body.vx = -body.vx.abs();
                    } else if body.x <= -2.0 {
                        body.vx = body.vx.abs();
                    }
                }
                body.x += body.rate * body.vx;
                body.y += body.rate * body.vy;
                body.inside |= (1.0..=128.0).contains(&body.x);
            } else if body.blast {
                // An explosion can be pushed. It keeps the velocity it has, losing the
                // same fraction to friction as an enemy does (seen in the data: 0.99 per frame).
                body.vx -= model.gamma * body.vx;
                body.vy -= model.gamma * body.vy;
                // Lethal rectangles push explosions away like any other enemy (seen in replays).
                if let Some(law) = &law {
                    for rect in &rects {
                        bounce_off(body, rect, law, speeds);
                    }
                }
                body.x += body.rate * body.vx;
                body.y += body.rate * body.vy;
            }
            gap = gap.min(box_clearance(px, py, size, body.x, body.y, body.size));
        }
        apply_events(model, &mut enemies);
        if let Some(law) = law {
            for rect in &mut rects {
                rect.x += rect.vx;
                rect.y += rect.vy;
                rect.w = (rect.w + rect.vw).max(0.0);
                rect.h = (rect.h + rect.vh).max(0.0);
                if let (true, Some(crush)) = (rect.moving, &model.crush) {
                    for body in enemies.iter_mut().filter(|body| !body.blast && !body.dying) {
                        let (ox, oy) = (
                            (body.x + body.size).min(rect.x + rect.w) - body.x.max(rect.x),
                            (body.y + body.size).min(rect.y + rect.h) - body.y.max(rect.y),
                        );
                        if ox <= 0.0 || oy <= 0.0 || !body.moves {
                            continue;
                        }
                        let wall = body
                            .x
                            .min(body.y)
                            .min(128.0 - body.x - body.size)
                            .min(128.0 - body.y - body.size);
                        let input = [
                            ox / 4.0,
                            oy / 4.0,
                            ox.min(oy) / 4.0,
                            rect.vx,
                            rect.vy,
                            rect.vw,
                            rect.vh,
                            rect.w / 64.0,
                            rect.h / 64.0,
                            body.size / 4.0,
                            body.kind as f64,
                            body.vx * body.rate,
                            body.vy * body.rate,
                            wall / 16.0,
                        ];
                        let scaled: Vec<f64> = input
                            .iter()
                            .zip(crush.mean.iter().zip(&crush.std))
                            .map(|(value, (mean, std))| (value - mean) / std)
                            .collect();
                        let logit = mlp_forward(&crush.layers, &scaled);
                        if 1.0 / (1.0 + (-logit).exp()) > crush_threshold() {
                            body.dying = true;
                        }
                    }
                }
                let was_lethal = rect_lethal(rect, &law);
                rect.progress =
                    (rect.progress + rect.trend * law.sh_step).clamp(0.0, law.lethal_at);
                if rect_lethal(rect, &law) {
                    gap = gap.min(rect_gap(px, py, size, rect));
                    // Measured from data: when a static rectangle turns lethal, 46 of 47
                    // enemies inside it were flagged dying on the next frame.
                    if !was_lethal && !rect.moving {
                        for body in enemies.iter_mut().filter(|body| !body.blast) {
                            if body.x + body.size > rect.x
                                && body.y + body.size > rect.y
                                && body.x < rect.x + rect.w
                                && body.y < rect.y + rect.h
                            {
                                body.dying = true;
                            }
                        }
                    }
                }
            }
        }
        if frame == snapshot_at {
            snapshot = enemies
                .iter()
                .map(|body| [body.x, body.y, body.size])
                .collect();
        }
        clearance = clearance.min(gap);
        if gap.is_finite() {
            cost += 12.0 / (gap + 1.0).powi(2);
        }
        cost += 0.05 * wall_penalty(px, py);
    }
    cost += GOAL_WEIGHT * (px - 64.0).hypot(py - 64.0);
    if clearance.is_finite() {
        cost += 8.0 * (-clearance / 3.0).exp();
    }
    Rollout {
        cost,
        first_hit,
        snapshot,
    }
}

/// One imagined rollout for action number `index` (`Action::ALL` order). For diagnostics.
pub fn imagine(
    model: &PhysicsModel,
    game: &NativeGame,
    index: usize,
    horizon: u32,
    snapshot_at: u32,
) -> Rollout {
    let direction = DIRECTIONS.get(index).copied().unwrap_or((0.0, 0.0));
    rollout(
        model,
        game,
        &read_bodies(game),
        direction,
        horizon,
        snapshot_at,
    )
}

/// First frame on which a player standing still at `(px, py)` is hit, from learned rollouts.
/// Returns `horizon` when nothing arrives in time. Same frame numbering as the exact field.
fn arrival_at(
    model: &PhysicsModel,
    bodies: &[Body],
    px: f64,
    py: f64,
    size: f64,
    horizon: u32,
) -> f32 {
    let mut enemies: Vec<Body> = bodies.to_vec();
    for frame in 0..horizon {
        if enemies.iter().any(|body| hits(px, py, size, body)) {
            return (frame + 1) as f32;
        }
        for body in &mut enemies {
            if body.moves {
                let (fx, fy) = model.force_fast(body.x - px, body.y - py, body.kind);
                body.vx += fx - model.gamma * body.vx;
                body.vy += fy - model.gamma * body.vy;
                body.x += body.rate * body.vx;
                body.y += body.rate * body.vy;
            } else if body.blast {
                // An explosion can be pushed. It keeps the velocity it has, losing the
                // same fraction to friction as an enemy does (seen in the data: 0.99 per frame).
                body.vx -= model.gamma * body.vx;
                body.vy -= model.gamma * body.vy;
                body.x += body.rate * body.vx;
                body.y += body.rate * body.vy;
            }
        }
    }
    horizon as f32
}

/// The arrival-time field that the learned model predicts, on a `grid` x `grid` lattice.
/// Row-major, like the exact field.
pub fn arrival_field(
    model: &PhysicsModel,
    game: &NativeGame,
    grid: usize,
    horizon: u32,
) -> Vec<f32> {
    let bodies = read_bodies(game);
    let size = game.player().size.to_double();
    let mut field = Vec::with_capacity(grid * grid);
    for row in 0..grid {
        for column in 0..grid {
            let x = (column as f64 + 0.5) * 128.0 / grid as f64;
            let y = (row as f64 + 0.5) * 128.0 / grid as f64;
            field.push(arrival_at(model, &bodies, x, y, size, horizon));
        }
    }
    field
}

/// The action with the lowest rollout cost, and all nine costs.
pub fn choose(model: &PhysicsModel, game: &NativeGame, horizon: u32) -> (Action, [f64; 9]) {
    let bodies = read_bodies(game);
    let mut costs = [0.0; 9];
    let mut best = 0;
    for (index, direction) in DIRECTIONS.iter().enumerate() {
        costs[index] = rollout(model, game, &bodies, *direction, horizon, 0).cost;
        if index == 0 {
            costs[index] += 0.25;
        }
        if costs[index] < costs[best] {
            best = index;
        }
    }
    let action = Action::ALL.get(best).copied().unwrap_or(Action::Neutral);
    (action, costs)
}

static MODEL: OnceLock<PhysicsModel> = OnceLock::new();

pub fn install(model: PhysicsModel) -> Result<(), String> {
    MODEL
        .set(model)
        .map_err(|_| "a physics model is already installed".to_owned())
}

pub fn installed() -> Option<&'static PhysicsModel> {
    MODEL.get()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A small fixed network, so the test does not need a trained file.
    fn model() -> PhysicsModel {
        let layer = |inputs: usize, outputs: usize, seed: f64| Layer {
            weights: (0..outputs)
                .map(|row| {
                    (0..inputs)
                        .map(|col| ((row * 7 + col * 3) as f64 * 0.37 + seed).sin() * 0.4)
                        .collect()
                })
                .collect(),
            bias: (0..outputs)
                .map(|row| (row as f64 * 0.11 + seed).cos() * 0.1)
                .collect(),
        };
        let mut model = PhysicsModel {
            layers: vec![layer(7, 12, 0.1), layer(12, 12, 0.7), layer(12, 1, 1.3)],
            gamma: 0.01,
            collision: None,
            blast: None,
            rect: None,
            crush: None,
            spawn: None,
            bounce_curve: std::collections::HashMap::new(),
            table: None,
        };
        model.table = Some(model.build_table());
        model
    }

    #[test]
    fn table_matches_the_network() {
        let model = model();
        let mut worst = 0.0_f64;
        for step in 0..400 {
            let dx = -120.0 + f64::from(step) * 0.6137;
            let dy = 95.0 - f64::from(step) * 0.5311;
            for kind in 0..2 {
                let exact = model.force(dx, dy, kind);
                let fast = model.force_fast(dx, dy, kind);
                worst = worst
                    .max((exact.0 - fast.0).abs())
                    .max((exact.1 - fast.1).abs());
            }
        }
        assert!(worst < 2e-4, "table differs from the network by {worst}");
    }
}
