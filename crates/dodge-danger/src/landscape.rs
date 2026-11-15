//! A hard-coded danger landscape, and a controller that rolls down it.
//!
//! The player is a damped particle with position `q` and momentum `p`. The
//! energy is `H(q, p) = ½‖p‖² + V(q)`, and the controller follows `-∇V`.
//!
//! `V` is a sum of terms, one per source of danger:
//!
//! * **Enemies.** Each enemy is a tube of Gaussians along its extrapolated
//!   path, `A · wₖ · exp(-|q - cₖ|² / 2σₖ²)` for a few future times `tₖ`, and
//!   the enemy contributes the strongest sample, not the sum. The tube is the
//!   teardrop of the road game: the ridge leans along the enemy's velocity and
//!   widens with time. Touching an enemy is fatal, so contact is the tallest
//!   feature of the landscape at any speed.
//! * **Patterns.** Lethal pattern rectangles raise a ridge that falls off with
//!   the distance to the rectangle.
//! * **Walls.** A ridge along the four edges.
//! * **Corners.** Fixed terms, hard-coded on purpose and not meant to be learned.
//! * **Tilt.** A weak linear slope. The four spawn corners are symmetric, so the
//!   gradient at the centre is exactly zero until the symmetry breaks; the tilt
//!   breaks it from frame 0.
//! * **Centre.** A fixed ridge. The game spawns extra enemies when the player
//!   stays in the centre box for 50 frames, so the centre is never a safe basin.
//!
//! Every enemy, pattern and wall term takes its shape from [`LandscapeParams`].
//! The numbers here are hand-set. They are the parameters a learned model would
//! replace: the structure stays, and the model fits `A`, `wₖ` and `σ` per kind.

use dodge_core::{Action, NativeGame};
use serde::Deserialize;

/// Future times, in frames, at which an enemy's tube is sampled.
pub const TUBE_FRAMES: [f64; 4] = [0.0, 12.0, 24.0, 36.0];

const ARENA_MIN: f64 = 2.0;
const ARENA_MAX: f64 = 125.0;
const PLAYFIELD: f64 = 128.0;

/// How one kind of enemy bends the landscape.
#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(default)]
pub struct EnemyShape {
    /// Peak height. A negative value makes the enemy attract the player.
    pub amplitude: f64,
    /// Weight of each tube sample, now to `TUBE_FRAMES[3]` frames ahead.
    pub tube_weights: [f64; 4],
    /// Scale on the contact radius (enemy half-size plus player size).
    pub body_scale: f64,
    /// Extra width in pixels per frame of lookahead.
    pub sigma_growth: f64,
}

impl Default for EnemyShape {
    fn default() -> Self {
        Self {
            amplitude: 3.0,
            tube_weights: [1.0, 0.8, 0.55, 0.35],
            body_scale: 1.0,
            sigma_growth: 0.08,
        }
    }
}

/// Every hand-set number in the landscape.
#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(default)]
pub struct LandscapeParams {
    /// Normal homing enemy.
    pub normal: EnemyShape,
    /// Kamikaze (personality 1).
    pub kamikaze: EnemyShape,
    /// Blast (personality -1).
    pub blast: EnemyShape,
    /// Explosive powerup (personality 2).
    pub bomb: EnemyShape,
    /// Freeze and shrink powerups (personality 3 and 4). Attractive by default.
    pub bonus: EnemyShape,
    pub pattern_lethal: f64,
    pub pattern_reach: f64,
    pub wall_amplitude: f64,
    pub wall_reach: f64,
    /// Hard-coded corner terms. Positive makes wells that pull the player in;
    /// negative makes bumps that push it away. The default is the best of three
    /// settings measured over 12 seeds, not a claim about the game.
    pub corner_amplitude: f64,
    pub corner_sigma: f64,
    /// Hard-coded ridge at the arena centre (the anti-camp spawner).
    pub center_amplitude: f64,
    pub center_sigma: f64,
    /// Symmetry-breaking slope in `V` per pixel along x and y.
    pub tilt_x: f64,
    pub tilt_y: f64,
    /// Below this gradient magnitude the controller stays still.
    pub deadband: f64,
}

impl Default for LandscapeParams {
    fn default() -> Self {
        Self {
            normal: EnemyShape::default(),
            kamikaze: EnemyShape {
                amplitude: 4.0,
                ..EnemyShape::default()
            },
            blast: EnemyShape {
                amplitude: 4.0,
                ..EnemyShape::default()
            },
            bomb: EnemyShape {
                amplitude: 1.5,
                ..EnemyShape::default()
            },
            bonus: EnemyShape {
                amplitude: -0.5,
                tube_weights: [1.0, 0.0, 0.0, 0.0],
                ..EnemyShape::default()
            },
            pattern_lethal: 3.0,
            pattern_reach: 5.0,
            wall_amplitude: 3.0,
            wall_reach: 10.0,
            corner_amplitude: -0.6,
            corner_sigma: 14.0,
            center_amplitude: 0.8,
            center_sigma: 12.0,
            tilt_x: 0.003,
            tilt_y: 0.002,
            deadband: 1e-3,
        }
    }
}

#[derive(Clone, Copy, Debug)]
struct Body {
    cx: f64,
    cy: f64,
    /// Velocity in pixels per frame, as the engine applies it.
    vx: f64,
    vy: f64,
    /// Contact radius: enemy half-size plus player size.
    radius: f64,
    kind: Kind,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Kind {
    Normal,
    Kamikaze,
    Blast,
    Bomb,
    Bonus,
}

#[derive(Clone, Copy, Debug)]
struct Rect {
    x: f64,
    y: f64,
    w: f64,
    h: f64,
}

/// The state the landscape reads, built once per decision.
#[derive(Clone, Debug)]
pub struct LandscapeState {
    px: f64,
    py: f64,
    bodies: Vec<Body>,
    rects: Vec<Rect>,
}

/// Read the landscape's inputs from the engine.
pub fn read_state(game: &NativeGame) -> LandscapeState {
    let view = game.privileged_view();
    let player = game.player();
    let step = view.speed.to_double() * view.freeze_rate.to_double();
    let player_size = player.size.to_double();

    let bodies = game
        .enemies()
        .iter()
        .map(|enemy| {
            let size = enemy.size.to_double();
            let rate = step * enemy.speed.to_double();
            let kind = match enemy.personality {
                1 => Kind::Kamikaze,
                -1 => Kind::Blast,
                2 => Kind::Bomb,
                3 | 4 => Kind::Bonus,
                _ => Kind::Normal,
            };
            Body {
                cx: enemy.x.to_double() + size / 2.0,
                cy: enemy.y.to_double() + size / 2.0,
                vx: enemy.vx.to_double() * rate,
                vy: enemy.vy.to_double() * rate,
                radius: size / 2.0 + player_size,
                kind,
            }
        })
        .collect();

    let mut rects = Vec::new();
    if let Some(pattern) = view.active_pattern {
        let lethal_pattern = pattern.pattern_type == 1;
        for rect in pattern.rects {
            if lethal_pattern || rect.sh.to_double() == 2.0 {
                rects.push(Rect {
                    x: rect.x.to_double(),
                    y: rect.y.to_double(),
                    w: rect.width.to_double(),
                    h: rect.height.to_double(),
                });
            }
        }
    }

    LandscapeState {
        px: player.x.to_double(),
        py: player.y.to_double(),
        bodies,
        rects,
    }
}

fn shape_for(kind: Kind, params: &LandscapeParams) -> &EnemyShape {
    match kind {
        Kind::Normal => &params.normal,
        Kind::Kamikaze => &params.kamikaze,
        Kind::Blast => &params.blast,
        Kind::Bomb => &params.bomb,
        Kind::Bonus => &params.bonus,
    }
}

/// The potential `V` at `(x, y)`.
pub fn potential(state: &LandscapeState, params: &LandscapeParams, x: f64, y: f64) -> f64 {
    let mut total = 0.0;

    for body in &state.bodies {
        let shape = shape_for(body.kind, params);
        // The strongest sample along the tube, not the sum. A sum would pile
        // every sample onto a slow enemy's body and spread the same weight thinly
        // along a fast one, so touching a fast enemy would look cheap.
        let mut strongest = 0.0_f64;
        for (time, weight) in TUBE_FRAMES.iter().zip(shape.tube_weights) {
            if weight == 0.0 {
                continue;
            }
            let sigma = (shape.body_scale * body.radius + shape.sigma_growth * time).max(0.5);
            let dx = x - (body.cx + body.vx * time);
            let dy = y - (body.cy + body.vy * time);
            let value =
                shape.amplitude * weight * (-(dx * dx + dy * dy) / (2.0 * sigma * sigma)).exp();
            if value.abs() > strongest.abs() {
                strongest = value;
            }
        }
        total += strongest;
    }

    for rect in &state.rects {
        let gap_x = (rect.x - x).max(x - (rect.x + rect.w)).max(0.0);
        let gap_y = (rect.y - y).max(y - (rect.y + rect.h)).max(0.0);
        let gap = gap_x.hypot(gap_y);
        total += params.pattern_lethal * (-gap / params.pattern_reach.max(1e-6)).exp();
    }

    let to_wall = (x - ARENA_MIN)
        .min(ARENA_MAX - x)
        .min((y - ARENA_MIN).min(ARENA_MAX - y))
        .max(0.0);
    total += params.wall_amplitude * (-to_wall / params.wall_reach.max(1e-6)).exp();

    for corner_x in [ARENA_MIN, ARENA_MAX] {
        for corner_y in [ARENA_MIN, ARENA_MAX] {
            let dx = x - corner_x;
            let dy = y - corner_y;
            let sigma = params.corner_sigma.max(1e-6);
            total -= params.corner_amplitude * (-(dx * dx + dy * dy) / (2.0 * sigma * sigma)).exp();
        }
    }
    let dx = x - PLAYFIELD / 2.0;
    let dy = y - PLAYFIELD / 2.0;
    let sigma = params.center_sigma.max(1e-6);
    total += params.center_amplitude * (-(dx * dx + dy * dy) / (2.0 * sigma * sigma)).exp();
    total += params.tilt_x * dx + params.tilt_y * dy;
    total
}

/// `∇V` at `(x, y)` by central differences.
pub fn gradient(state: &LandscapeState, params: &LandscapeParams, x: f64, y: f64) -> (f64, f64) {
    const H: f64 = 0.75;
    let gx = (potential(state, params, x + H, y) - potential(state, params, x - H, y)) / (2.0 * H);
    let gy = (potential(state, params, x, y + H) - potential(state, params, x, y - H)) / (2.0 * H);
    (gx, gy)
}

fn direction(action: Action) -> (f64, f64) {
    let (dx, dy): (f64, f64) = match action {
        Action::Neutral => (0.0, 0.0),
        Action::Left => (-1.0, 0.0),
        Action::Right => (1.0, 0.0),
        Action::Up => (0.0, -1.0),
        Action::Down => (0.0, 1.0),
        Action::UpLeft => (-1.0, -1.0),
        Action::UpRight => (1.0, -1.0),
        Action::DownLeft => (-1.0, 1.0),
        Action::DownRight => (1.0, 1.0),
    };
    let length = dx.hypot(dy);
    if length == 0.0 {
        (0.0, 0.0)
    } else {
        (dx / length, dy / length)
    }
}

/// What the controller decided and why.
#[derive(Clone, Copy, Debug)]
pub struct Choice {
    pub action: Action,
    /// `∇V · d` for each action in `Action::ALL` order. Lower is better.
    pub costs: [f64; 9],
    pub gradient: (f64, f64),
}

/// Follow `-∇V`: take the action whose direction is most downhill.
pub fn choose(state: &LandscapeState, params: &LandscapeParams) -> Choice {
    let gradient = gradient(state, params, state.px, state.py);
    let mut costs = [0.0; 9];
    for (slot, action) in costs.iter_mut().zip(Action::ALL) {
        let (dx, dy) = direction(action);
        *slot = gradient.0 * dx + gradient.1 * dy;
    }
    let mut action = Action::Neutral;
    if gradient.0.hypot(gradient.1) > params.deadband {
        let mut best = f64::INFINITY;
        for (candidate, &cost) in Action::ALL.iter().copied().zip(&costs) {
            if cost < best {
                best = cost;
                action = candidate;
            }
        }
    }
    Choice {
        action,
        costs,
        gradient,
    }
}

/// Convenience wrapper for the policy.
pub fn choose_for_game(game: &NativeGame, params: &LandscapeParams) -> Choice {
    choose(&read_state(game), params)
}

/// The landscape sampled on a grid, as `(danger in 0..=1, argmin cell)`.
/// Danger is `V` clamped to `0..=V_REF` and scaled, so wells show as safe.
pub const V_REF: f64 = 4.0;

pub fn sample_grid(
    game: &NativeGame,
    params: &LandscapeParams,
    width: usize,
    height: usize,
) -> (Vec<f32>, (f64, f64), f64) {
    let state = read_state(game);
    let mut danger = Vec::with_capacity(width * height);
    let mut best = (PLAYFIELD / 2.0, PLAYFIELD / 2.0);
    let mut best_value = f64::INFINITY;
    for row in 0..height {
        for column in 0..width {
            let x = (column as f64 + 0.5) * PLAYFIELD / width as f64;
            let y = (row as f64 + 0.5) * PLAYFIELD / height as f64;
            let value = potential(&state, params, x, y);
            danger.push((value / V_REF).clamp(0.0, 1.0) as f32);
            if (8.0..=PLAYFIELD - 8.0).contains(&x)
                && (8.0..=PLAYFIELD - 8.0).contains(&y)
                && value < best_value
            {
                best_value = value;
                best = (x, y);
            }
        }
    }
    (danger, best, best_value)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Only the enemy terms: no walls, corners, centre or tilt.
    fn flat() -> LandscapeParams {
        LandscapeParams {
            wall_amplitude: 0.0,
            corner_amplitude: 0.0,
            center_amplitude: 0.0,
            tilt_x: 0.0,
            tilt_y: 0.0,
            ..LandscapeParams::default()
        }
    }

    fn one_enemy(vx: f64) -> LandscapeState {
        LandscapeState {
            px: 70.0,
            py: 64.0,
            bodies: vec![Body {
                cx: 64.0,
                cy: 64.0,
                vx,
                vy: 0.0,
                radius: 5.0,
                kind: Kind::Normal,
            }],
            rects: Vec::new(),
        }
    }

    #[test]
    fn enemy_ridge_is_highest_at_the_enemy() {
        let params = LandscapeParams::default();
        let state = one_enemy(0.0);
        let at = potential(&state, &params, 64.0, 64.0);
        let away = potential(&state, &params, 90.0, 64.0);
        assert!(at > away);
    }

    #[test]
    fn controller_moves_away_from_a_close_enemy() {
        let params = flat();
        // Enemy is to the left of the player, so downhill is to the right.
        let choice = choose(&one_enemy(0.0), &params);
        assert_eq!(choice.action, Action::Right);
    }

    #[test]
    fn touching_an_enemy_costs_the_same_at_any_speed() {
        // A slow enemy must not look more dangerous than a fast one at the
        // moment of contact. Contact is fatal either way.
        let params = flat();
        let at_body = |vx: f64| potential(&one_enemy(vx), &params, 64.0, 64.0);
        let slow = at_body(0.0);
        let fast = at_body(0.9);
        assert!(
            (slow - fast).abs() < 1e-9,
            "slow {slow:.3} vs fast {fast:.3} at the enemy body"
        );
    }

    #[test]
    fn contact_with_an_enemy_outranks_the_walls() {
        let params = LandscapeParams::default();
        let state = one_enemy(0.9);
        let contact = potential(&state, &params, 64.0, 64.0)
            - potential(
                &LandscapeState {
                    bodies: Vec::new(),
                    ..state.clone()
                },
                &params,
                64.0,
                64.0,
            );
        let wall_only = LandscapeState {
            bodies: Vec::new(),
            ..state
        };
        let edge =
            potential(&wall_only, &params, 2.0, 64.0) - potential(&wall_only, &params, 64.0, 64.0);
        assert!(
            contact > edge,
            "contact {contact:.2} must exceed the wall ridge {edge:.2}"
        );
    }

    #[test]
    fn tube_leans_along_enemy_velocity() {
        let params = flat();
        let moving = one_enemy(0.5);
        let still = one_enemy(0.0);
        // Ahead of a rightward enemy (x = 78) is more dangerous than behind it (x = 50).
        assert!(potential(&moving, &params, 78.0, 64.0) > potential(&moving, &params, 50.0, 64.0));
        assert!(potential(&moving, &params, 78.0, 64.0) > potential(&still, &params, 78.0, 64.0));
    }

    #[test]
    fn centre_is_a_ridge_not_a_basin() {
        let params = LandscapeParams {
            center_amplitude: 1.0,
            ..flat()
        };
        let empty = LandscapeState {
            px: 64.0,
            py: 64.0,
            bodies: Vec::new(),
            rects: Vec::new(),
        };
        assert!(potential(&empty, &params, 64.0, 64.0) > potential(&empty, &params, 90.0, 64.0));
    }

    #[test]
    fn corner_well_is_lower_than_open_floor() {
        let params = LandscapeParams {
            corner_amplitude: 0.8,
            ..flat()
        };
        let empty = LandscapeState {
            px: 64.0,
            py: 64.0,
            bodies: Vec::new(),
            rects: Vec::new(),
        };
        assert!(potential(&empty, &params, 6.0, 6.0) < potential(&empty, &params, 64.0, 64.0));
    }
}
