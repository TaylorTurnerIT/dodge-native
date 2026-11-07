//! Plan by rolling a learned enemy model forward, in place of the engine.
//!
//! The enemy model is a port-Hamiltonian system learned from trajectories only
//! (`hnn/physics.py`): `H = 1/2 |p|^2 + U(q_enemy - q_player, kind)`, with a learned damping.
//! The player moves by its own known motion rule. For each of the nine actions the planner
//! rolls the player and every enemy forward `horizon` frames, then scores the rollout with the
//! same collision, clearance and wall terms that the lookahead policy uses.
//!
//! What it assumes without learning it: an enemy has its full size of 3 px, the clock rate
//! stays what it is now, wall bounces do not happen (no enemy was seen to bounce), and
//! enemies do not collide with each other.

use std::sync::OnceLock;

use dodge_core::{Action, NativeGame};
use serde::Deserialize;

use crate::box_clearance;

/// Enemies grow to this size. The model sees the current size, which can be smaller.
const ADULT_SIZE: f64 = 3.0;
/// Pull toward the middle of the arena, scored at the end of a rollout.
const GOAL_WEIGHT: f64 = 0.3;

#[derive(Clone, Debug, Deserialize)]
struct Layer {
    weights: Vec<Vec<f64>>,
    bias: Vec<f64>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct PhysicsModel {
    layers: Vec<Layer>,
    gamma: f64,
}

impl PhysicsModel {
    pub fn from_json(text: &str) -> Result<Self, String> {
        serde_json::from_str(text)
            .map_err(|error| format!("could not parse physics model: {error}"))
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
}

fn read_bodies(game: &NativeGame) -> Vec<Body> {
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

fn hits(px: f64, py: f64, size: f64, body: &Body) -> bool {
    px + size - 1.0 > body.x
        && py + size - 1.0 > body.y
        && px - size + 1.0 < body.x + body.size
        && py - size + 1.0 < body.y + body.size
}

fn wall_penalty(x: f64, y: f64) -> f64 {
    (8.0 - x).max(0.0) + (x - 120.0).max(0.0) + (8.0 - y).max(0.0) + (y - 120.0).max(0.0)
}

/// Cost of playing `direction` for `horizon` frames, with the learned enemy model.
fn rollout(
    model: &PhysicsModel,
    game: &NativeGame,
    bodies: &[Body],
    direction: (f64, f64),
    horizon: u32,
) -> f64 {
    let player = game.player();
    let size = player.size.to_double();
    let (mut px, mut py) = (player.x.to_double(), player.y.to_double());
    let (mut pvx, mut pvy) = (player.vx.to_double(), player.vy.to_double());
    let mut enemies = bodies.to_vec();
    let mut cost = 0.0;
    let mut clearance = f64::INFINITY;

    for frame in 1..=horizon {
        // The engine checks for a hit first, then moves the player, then moves the enemies.
        if enemies.iter().any(|body| hits(px, py, size, body)) {
            cost += 5_000.0 - 50.0 * f64::from(frame);
            clearance = 0.0;
            break;
        }
        pvx = 0.8 * pvx + 0.5 * direction.0;
        pvy = 0.8 * pvy + 0.5 * direction.1;
        px = (px + pvx).clamp(2.0, 125.0);
        py = (py + pvy).clamp(2.0, 125.0);
        let mut gap = f64::INFINITY;
        for body in &mut enemies {
            if body.moves {
                let (fx, fy) = model.force(body.x - px, body.y - py, body.kind);
                body.vx += fx - model.gamma * body.vx;
                body.vy += fy - model.gamma * body.vy;
                body.x += body.rate * body.vx;
                body.y += body.rate * body.vy;
            }
            gap = gap.min(box_clearance(px, py, size, body.x, body.y, body.size));
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
    cost
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
                let (fx, fy) = model.force(body.x - px, body.y - py, body.kind);
                body.vx += fx - model.gamma * body.vx;
                body.vy += fy - model.gamma * body.vy;
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
        costs[index] = rollout(model, game, &bodies, *direction, horizon);
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
