//! Hand-coded danger Hamiltonian prototype for Dodge.
//!
//! The potential is `V(q) = V_goal(q) + V_danger(q)`. `V_danger` is built from
//! a lookahead: each enemy is rolled forward under the game's homing rule, and
//! the field records the first frame at which a stationary player at a cell
//! would be hit. The policy is a receding-horizon search over the nine actions
//! using exact `NativeGame` clones and `advance_frame_headless`.
//!
//! This is not a trained HNN. It is a deterministic ground-truth generator and
//! a visual probe for the next step: fitting a residual danger potential.

pub mod deaths;
pub mod hnnplan;
pub mod landscape;
pub mod learned;
pub mod observe;

use dodge_core::{Action, BUTTON_X_MASK, EnemyState, Mode, NativeConfig, NativeGame, PlayerState};
pub use landscape::LandscapeParams;
use serde::Serialize;

pub const FPS: u32 = 60;
pub const START_FRAMES: u32 = 13;
pub const PLAYFIELD: f64 = 128.0;

// Mirrors the constants in `crates/dodge-core/src/game.rs`.
const ENEMY_FRICTION: f64 = 64_880.0 / 65_536.0;
const ENEMY_ACCELERATION: f64 = 655.0 / 65_536.0;
const ENEMY_SPEED_STEP: f64 = 655.0 / 65_536.0;
const KAMIKAZE_RADIUS: f64 = 25.0;

const GOAL_MARGIN: f64 = 8.0;
const GOAL_MIN_DISTANCE: f64 = 16.0;
const GOAL_MIN_PENALTY: f64 = 8.0;
const CORNER_PENALTY: f64 = 12.0;

/// The hard-coded policies available in the prototype.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PolicyKind {
    /// Exact native-engine rollouts, scored by collision time, clearance, and goal progress.
    Lookahead,
    /// Gradient descent on a hard-coded danger landscape (`landscape.rs`).
    Landscape,
    /// Myopic repulsion from current enemy boxes plus a goal attraction.
    Potential,
    /// Run directly away from the nearest enemy.
    Flee,
    /// Uniform random action from a private RNG.
    Random,
    /// Do nothing.
    Neutral,
    /// Gradient descent on a learned potential (`learned.rs`). Needs `--model`.
    Learned,
    /// Lookahead through a learned Hamiltonian enemy model (`hnnplan.rs`). Needs `--physics-model`.
    Hnn,
}

impl PolicyKind {
    pub const ALL: [Self; 6] = [
        Self::Lookahead,
        Self::Landscape,
        Self::Potential,
        Self::Flee,
        Self::Random,
        Self::Neutral,
    ];

    pub const COMPARE: [Self; 5] = [
        Self::Lookahead,
        Self::Landscape,
        Self::Potential,
        Self::Flee,
        Self::Random,
    ];

    pub const fn name(self) -> &'static str {
        match self {
            Self::Lookahead => "lookahead",
            Self::Landscape => "landscape",
            Self::Potential => "potential",
            Self::Flee => "flee",
            Self::Random => "random",
            Self::Neutral => "neutral",
            Self::Learned => "learned",
            Self::Hnn => "hnn",
        }
    }

    pub fn from_name(name: &str) -> Option<Self> {
        match name {
            "lookahead" => Some(Self::Lookahead),
            "landscape" => Some(Self::Landscape),
            "potential" => Some(Self::Potential),
            "flee" => Some(Self::Flee),
            "random" => Some(Self::Random),
            "neutral" => Some(Self::Neutral),
            "learned" => Some(Self::Learned),
            "hnn" => Some(Self::Hnn),
            _ => None,
        }
    }
}

/// Settings for one trace or benchmark run.
#[derive(Clone, Copy, Debug)]
pub struct DangerConfig {
    pub seed: u32,
    pub difficulty: u8,
    pub max_frames: u32,
    pub horizon: u32,
    pub grid: usize,
    pub goal_every: u32,
    pub heat_every: u32,
    pub patterns: bool,
    pub powerups: bool,
    /// Per-frame chance of starting a burst of random actions that replaces the
    /// policy's action. The recorded label stays the policy's own choice. Zero by default.
    pub epsilon: f64,
    /// Play the installed learned model's action while the policy still labels the frame.
    pub drive_model: bool,
    /// Record each enemy's raw velocity and clock rate (for learning the physics).
    pub physics: bool,
    /// Hand-set shape of every term in the danger landscape.
    pub landscape: LandscapeParams,
}

impl Default for DangerConfig {
    fn default() -> Self {
        Self {
            seed: 42,
            difficulty: 2,
            max_frames: 2_400,
            horizon: 36,
            grid: 40,
            goal_every: 8,
            heat_every: 10,
            patterns: false,
            powerups: false,
            epsilon: 0.0,
            drive_model: false,
            physics: false,
            landscape: LandscapeParams::default(),
        }
    }
}

impl DangerConfig {
    pub fn validate(&self) -> Result<(), String> {
        if self.difficulty == 0 || self.difficulty > 3 {
            return Err("difficulty must be 1, 2, or 3".to_owned());
        }
        if !(0.0..=1.0).contains(&self.epsilon) {
            return Err("epsilon must be from 0 to 1".to_owned());
        }
        if self.max_frames == 0 {
            return Err("max_frames must be greater than zero".to_owned());
        }
        if self.horizon == 0 || self.horizon > 120 {
            return Err("horizon must be from 1 to 120".to_owned());
        }
        if self.grid < 8 || self.grid > 96 {
            return Err("grid must be from 8 to 96".to_owned());
        }
        if self.goal_every == 0 {
            return Err("goal_every must be greater than zero".to_owned());
        }
        if self.heat_every == 0 {
            return Err("heat_every must be greater than zero".to_owned());
        }
        Ok(())
    }
}

/// A sampled danger field over the playfield.
#[derive(Clone, Debug)]
pub struct HeatField {
    pub width: usize,
    pub height: usize,
    /// First collision frame for a stationary player at each cell, capped at the horizon.
    pub arrival: Vec<f32>,
    /// Safest reachable cell by lookahead arrival time, with corner and distance penalties.
    pub goal: (f64, f64),
    /// Score of the chosen goal cell before hysteresis.
    pub goal_score: f64,
}

impl HeatField {
    pub fn record(&self, horizon: u32) -> HeatRecord {
        HeatRecord {
            w: self.width,
            h: self.height,
            a: self
                .arrival
                .iter()
                .map(|value| quantize(*value, horizon))
                .collect(),
        }
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct HeatRecord {
    pub w: usize,
    pub h: usize,
    /// Arrival time quantized to 0..=255 over 0..=horizon frames.
    pub a: Vec<u8>,
}

#[derive(Clone, Debug, Serialize)]
pub struct FrameRecord {
    /// Player x, y, vx, vy, size.
    pub p: [f32; 5],
    /// Enemy x, y, vx, vy, size, personality. `vx` and `vy` are pixels per frame,
    /// after game speed, freeze and the enemy's own speed.
    pub e: Vec<[f32; 6]>,
    /// Per enemy, when `physics` is on: x, y, raw vx, raw vy, size, personality, rate.
    /// `rate` is game speed x freeze x the enemy's own speed. An enemy moves by
    /// `raw velocity x rate` each frame.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub ph: Vec<[f32; 7]>,
    /// With `ph`: for each pattern rectangle, its warning progress (0 to 2; the rectangle is
    /// lethal once it reaches 2, or always for moving patterns) and 1 if the pattern moves.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub rs: Vec<[f32; 2]>,
    /// With `ph`: 1 for each enemy the engine has marked as dying (it is removed shortly after).
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub dy: Vec<u8>,
    /// Active pattern rectangles: x, y, width, height, lethal (1.0) or harmless (0.0).
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub r: Vec<[f32; 5]>,
    /// The policy's chosen action. In a perturbed run this is the label.
    pub a: &'static str,
    /// The action that was played, when a random burst replaced the policy's choice.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub x: Option<&'static str>,
    /// Current goal.
    pub g: [f32; 2],
    /// First collision frame in the chosen action's lookahead rollout. `horizon + 1` means none.
    pub t: f32,
    /// Minimum player-enemy AABB gap in that rollout.
    pub c: f32,
    /// Heat map sampled on this frame, when scheduled.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub h: Option<HeatRecord>,
    /// Player positions along the chosen action's rollout, every two frames.
    pub path: Vec<[f32; 2]>,
    /// Nine lookahead costs in `Action::ALL` order, when the policy computes them.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub costs: Option<Vec<f32>>,
}

#[derive(Clone, Debug, Serialize)]
pub struct TraceMeta {
    pub seed: u32,
    pub difficulty: u8,
    pub policy: &'static str,
    pub horizon: u32,
    pub grid: usize,
    pub goal_every: u32,
    pub heat_every: u32,
    pub max_frames: u32,
    pub fps: u32,
    pub patterns: bool,
    pub powerups: bool,
    pub playfield: f32,
    /// What the heat map shows: `arrival` (frames to hit) or `potential` (landscape V).
    pub field: &'static str,
}

#[derive(Clone, Debug, Serialize)]
pub struct TraceResult {
    pub survival_frames: u32,
    pub dead: bool,
    pub score: f32,
    pub captured_frames: u32,
}

#[derive(Clone, Debug, Serialize)]
pub struct Trace {
    pub meta: TraceMeta,
    pub frames: Vec<FrameRecord>,
    pub result: TraceResult,
}

#[derive(Clone, Debug)]
pub struct Episode {
    pub survival_frames: u32,
    pub dead: bool,
    pub score: f32,
    pub trace: Option<Trace>,
}

#[derive(Clone, Debug, Serialize)]
pub struct CompareRow {
    pub policy: &'static str,
    pub seeds: Vec<u32>,
    pub mean_survival: f64,
    pub min_survival: u32,
    pub max_survival: u32,
    pub censored: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct CompareOutput {
    pub seed: u32,
    pub difficulty: u8,
    pub max_frames: u32,
    pub rows: Vec<CompareRow>,
}

/// Run one episode with the configured frame cap. The game is advanced with
/// `advance_frame_headless`, so the trace contains gameplay state but no pixels.
pub fn run_episode(
    config: &DangerConfig,
    policy: PolicyKind,
    capture: bool,
) -> Result<Episode, String> {
    config.validate()?;
    let mut frames = Vec::new();
    let end = if capture {
        let mut sink = |record: FrameRecord| -> Result<(), String> {
            frames.push(record);
            Ok(())
        };
        drive(config, policy, Some(config.max_frames), Some(&mut sink))?
    } else {
        drive(config, policy, Some(config.max_frames), None)?
    };

    let captured_frames = frames.len() as u32;
    let trace = if capture {
        Some(Trace {
            meta: trace_meta(config, policy),
            frames,
            result: TraceResult {
                survival_frames: end.survival_frames,
                dead: end.dead,
                score: end.score,
                captured_frames,
            },
        })
    } else {
        None
    };

    Ok(Episode {
        survival_frames: end.survival_frames,
        dead: end.dead,
        score: end.score,
        trace,
    })
}

/// Run one episode with no frame limit, handing each frame to `sink` as it is
/// produced. The run ends when the player dies or when `sink` returns an error.
/// A policy that never dies makes this run forever, so the caller must stop
/// pulling frames when it wants to stop.
pub fn stream_episode(
    config: &DangerConfig,
    policy: PolicyKind,
    limit: Option<u32>,
    sink: &mut dyn FnMut(FrameRecord) -> Result<(), String>,
) -> Result<TraceResult, String> {
    config.validate()?;
    let end = drive(config, policy, limit, Some(sink))?;
    Ok(TraceResult {
        survival_frames: end.survival_frames,
        dead: end.dead,
        score: end.score,
        captured_frames: end.frames_run,
    })
}

/// The metadata record for a run. `max_frames` is the cap that a recorded run
/// uses; a streamed run has no cap and ignores it.
pub fn trace_meta(config: &DangerConfig, policy: PolicyKind) -> TraceMeta {
    TraceMeta {
        seed: config.seed,
        difficulty: config.difficulty,
        policy: policy.name(),
        horizon: config.horizon,
        grid: config.grid,
        goal_every: config.goal_every,
        heat_every: config.heat_every,
        max_frames: config.max_frames,
        fps: FPS,
        patterns: config.patterns,
        powerups: config.powerups,
        playfield: PLAYFIELD as f32,
        field: if policy == PolicyKind::Landscape {
            "potential"
        } else if policy == PolicyKind::Hnn {
            "hnn-arrival"
        } else {
            "arrival"
        },
    }
}

struct DriveEnd {
    survival_frames: u32,
    dead: bool,
    score: f32,
    frames_run: u32,
}

/// The shared run loop. `limit` is a frame cap, or `None` to run until death.
fn drive(
    config: &DangerConfig,
    policy: PolicyKind,
    limit: Option<u32>,
    mut on_frame: Option<&mut dyn FnMut(FrameRecord) -> Result<(), String>>,
) -> Result<DriveEnd, String> {
    let native_config = NativeConfig {
        seed: config.seed,
        difficulty: config.difficulty,
        patterns_enabled: config.patterns,
        powerups_enabled: config.powerups,
        ..NativeConfig::new(config.seed)
    };
    let mut game = NativeGame::new(native_config);
    start_game(&mut game)?;

    let mut rng = PrivateRng::new(config.seed);
    let mut previous = Action::Neutral;
    let mut goal = (PLAYFIELD / 2.0, PLAYFIELD / 2.0);
    let mut field: Option<HeatField> = None;
    let mut frame: u32 = 0;
    let mut frames_run: u32 = 0;
    let mut rect_memory = hnnplan::RectSnapshot::new();
    observe::reset();
    let mut burst_left: u32 = 0;
    let mut burst_action = Action::Neutral;

    loop {
        if limit.is_some_and(|cap| frame >= cap) {
            break;
        }
        if policy == PolicyKind::Hnn {
            observe::feed(&game);
        }
        if field.is_none() || frame % config.goal_every == 0 {
            let mut next = if policy == PolicyKind::Landscape {
                landscape_heat(&game, config)
            } else if policy == PolicyKind::Hnn
                && let Some(model) = hnnplan::installed()
            {
                // The field the learned model predicts, not the engine's exact one.
                HeatField {
                    width: config.grid,
                    height: config.grid,
                    arrival: hnnplan::arrival_field(model, &game, config.grid, config.horizon),
                    goal: (PLAYFIELD / 2.0, PLAYFIELD / 2.0),
                    goal_score: 0.0,
                }
            } else {
                compute_heat(&game, config)
            };
            if let Some(previous) = &field {
                let jump = (next.goal.0 - previous.goal.0).hypot(next.goal.1 - previous.goal.1);
                if jump < 8.0 && next.goal_score <= previous.goal_score + 1.0 {
                    next.goal = previous.goal;
                }
            }
            goal = next.goal;
            field = Some(next);
        }

        if policy == PolicyKind::Hnn {
            hnnplan::set_history(rect_memory.clone());
        }
        let decision = decide(&game, goal, config, policy, previous, &mut rng)?;
        if policy == PolicyKind::Hnn {
            rect_memory = hnnplan::rect_snapshot(&game);
        }
        let mut played = decision.action;
        if config.drive_model
            && let Some(model) = learned::installed()
        {
            played = model.choose(&learned::Observation::from_game(&game)).0;
        }
        if config.epsilon > 0.0 {
            if burst_left == 0 {
                let draw = (rng.next_u64() >> 11) as f64 / (1u64 << 53) as f64;
                if draw < config.epsilon {
                    burst_left = 6 + (rng.next_u64() % 9) as u32;
                    burst_action = rng.action();
                }
            }
            if burst_left > 0 {
                burst_left -= 1;
                played = burst_action;
            }
        }

        if let Some(sink) = on_frame.as_mut() {
            let heat = if frame % config.heat_every == 0 {
                field.as_ref().map(|value| value.record(config.horizon))
            } else {
                None
            };
            sink(FrameRecord::new(
                &game,
                &decision,
                goal,
                heat,
                played,
                config.physics,
            ))?;
            frames_run += 1;
        }

        previous = played;
        let result = game
            .advance_frame_headless(played.mask())
            .map_err(|error| format!("frame {frame}: {error}"))?;
        if result.dead {
            break;
        }
        frame = frame.saturating_add(1);
    }

    Ok(DriveEnd {
        survival_frames: game.survival_frames(),
        dead: game.lifecycle().dead,
        score: game.score().to_f32(),
        frames_run,
    })
}

/// Play `seeds` consecutive games with one policy on `threads` threads.
/// Returns `(seed, survival frames, died)` sorted by seed.
pub fn survival_parallel(
    config: &DangerConfig,
    policy: PolicyKind,
    seeds: u32,
    threads: usize,
) -> Result<Vec<(u32, u32, bool)>, String> {
    use std::sync::Mutex;
    use std::sync::atomic::{AtomicU32, Ordering};
    config.validate()?;
    let next = AtomicU32::new(0);
    let results: Mutex<Vec<(u32, u32, bool)>> = Mutex::new(Vec::new());
    let failure: Mutex<Option<String>> = Mutex::new(None);
    std::thread::scope(|scope| {
        for _ in 0..threads.max(1) {
            scope.spawn(|| {
                loop {
                    let offset = next.fetch_add(1, Ordering::Relaxed);
                    if offset >= seeds {
                        return;
                    }
                    let mut local = *config;
                    local.seed = config.seed.wrapping_add(offset);
                    match run_episode(&local, policy, false) {
                        Ok(episode) => {
                            if let Ok(mut list) = results.lock() {
                                list.push((local.seed, episode.survival_frames, episode.dead));
                            }
                        }
                        Err(error) => {
                            if let Ok(mut slot) = failure.lock() {
                                slot.get_or_insert(error);
                            }
                            return;
                        }
                    }
                }
            });
        }
    });
    if let Ok(slot) = failure.lock()
        && let Some(error) = slot.clone()
    {
        return Err(error);
    }
    let mut list = results.into_inner().map_err(|_| "poisoned".to_owned())?;
    list.sort_unstable();
    Ok(list)
}

/// Compare the non-neutral policies over a seed range. Each seed is a fresh game.
pub fn compare(config: &DangerConfig, seeds: u32) -> Result<CompareOutput, String> {
    config.validate()?;
    if seeds == 0 {
        return Err("seeds must be greater than zero".to_owned());
    }
    let mut rows = Vec::new();
    let mut policies = PolicyKind::COMPARE.to_vec();
    if learned::installed().is_some() {
        policies.push(PolicyKind::Learned);
    }
    if hnnplan::installed().is_some() {
        policies.push(PolicyKind::Hnn);
    }
    for policy in policies {
        let mut values = Vec::new();
        let mut seed_list = Vec::new();
        for offset in 0..seeds {
            let seed = config.seed.wrapping_add(offset);
            let mut local = *config;
            local.seed = seed;
            seed_list.push(seed);
            let episode = run_episode(&local, policy, false)?;
            values.push(episode.survival_frames);
        }
        let total: u64 = values.iter().map(|value| u64::from(*value)).sum();
        let mean = total as f64 / values.len() as f64;
        let min = values.iter().copied().min().unwrap_or(0);
        let max = values.iter().copied().max().unwrap_or(0);
        let censored = values.iter().any(|value| *value >= config.max_frames);
        rows.push(CompareRow {
            policy: policy.name(),
            seeds: seed_list,
            mean_survival: mean,
            min_survival: min,
            max_survival: max,
            censored,
        });
    }
    Ok(CompareOutput {
        seed: config.seed,
        difficulty: config.difficulty,
        max_frames: config.max_frames,
        rows,
    })
}

/// Advance the cartridge through its 13-frame X hold until gameplay starts.
pub fn start_game(game: &mut NativeGame) -> Result<(), String> {
    for _ in 0..START_FRAMES {
        game.advance_frame_headless(BUTTON_X_MASK)
            .map_err(|error| format!("start frame: {error}"))?;
    }
    let mode = game.lifecycle().mode;
    if mode != Mode::Game {
        return Err(format!("start sequence ended in mode {mode:?}"));
    }
    Ok(())
}

/// The landscape as a heat map. The page draws `1 - arrival / horizon` as danger,
/// so a cell's value is stored as `horizon * (1 - danger)`.
fn landscape_heat(game: &NativeGame, config: &DangerConfig) -> HeatField {
    let (danger, goal, best_value) =
        landscape::sample_grid(game, &config.landscape, config.grid, config.grid);
    let horizon = config.horizon as f32;
    HeatField {
        width: config.grid,
        height: config.grid,
        arrival: danger.iter().map(|value| horizon * (1.0 - value)).collect(),
        goal,
        goal_score: -best_value,
    }
}

/// Compute the danger field and the safest goal cell.
pub fn compute_heat(game: &NativeGame, config: &DangerConfig) -> HeatField {
    let width = config.grid;
    let height = config.grid;
    let player = game.player();
    let enemies = game.enemies();
    let snapshot = game.snapshot();
    let state = snapshot.logical_state();
    let speed = state.speed.to_double();
    let freeze = state.freeze_rate.to_double();

    let mut arrival = vec![config.horizon as f32; width.saturating_mul(height)];
    let mut goal = (PLAYFIELD / 2.0, PLAYFIELD / 2.0);

    if enemies.is_empty() {
        return HeatField {
            width,
            height,
            arrival,
            goal,
            goal_score: 0.0,
        };
    }

    let mut best_score = f64::NEG_INFINITY;
    for gy in 0..height {
        for gx in 0..width {
            let cx = (gx as f64 + 0.5) * PLAYFIELD / width as f64;
            let cy = (gy as f64 + 0.5) * PLAYFIELD / height as f64;
            let value = arrival_time(enemies, &player, cx, cy, config.horizon, speed, freeze);
            let index = gy.saturating_mul(width).saturating_add(gx);
            if let Some(slot) = arrival.get_mut(index) {
                *slot = value;
            }
            if cx >= GOAL_MARGIN
                && cx <= PLAYFIELD - GOAL_MARGIN
                && cy >= GOAL_MARGIN
                && cy <= PLAYFIELD - GOAL_MARGIN
            {
                let score = goal_score(value, cx, cy, &player);
                if score > best_score {
                    best_score = score;
                    goal = (cx, cy);
                }
            }
        }
    }

    HeatField {
        width,
        height,
        arrival,
        goal,
        goal_score: best_score,
    }
}

/// Engine frame on which a player who stays at its current position dies.
///
/// Frame 1 is the next `advance_frame_headless` call. Returns `horizon` when no
/// collision happens before it; a hit exactly on `horizon` is the same value. Used to
/// check the float predictor against exact neutral rollouts.
pub fn predict_player_arrival(game: &NativeGame, horizon: u32) -> f32 {
    let player = game.player();
    let snapshot = game.snapshot();
    let state = snapshot.logical_state();
    arrival_time(
        game.enemies(),
        &player,
        player.x.to_double(),
        player.y.to_double(),
        horizon,
        state.speed.to_double(),
        state.freeze_rate.to_double(),
    )
}

/// Engine frame of the first hit for a player standing still at `(px, py)`.
fn arrival_time(
    enemies: &[EnemyState],
    player: &PlayerState,
    px: f64,
    py: f64,
    horizon: u32,
    speed: f64,
    freeze: f64,
) -> f32 {
    let mut predicted: Vec<SimEnemy> = enemies
        .iter()
        .filter(|enemy| enemy.personality >= 0)
        .map(SimEnemy::from)
        .collect();
    if predicted.is_empty() {
        return horizon as f32;
    }
    let player_size = player.size.to_double();
    // The engine checks collisions at the start of a frame, before enemies move.
    // A hit after `k` enemy updates therefore registers on engine frame `k + 1`.
    for frame in 0..horizon {
        if predicted
            .iter()
            .any(|enemy| enemy.overlaps(px, py, player_size))
        {
            return (frame + 1) as f32;
        }
        for enemy in &mut predicted {
            enemy.step(px, py, speed, freeze);
        }
    }
    horizon as f32
}

fn goal_score(arrival: f32, cx: f64, cy: f64, player: &PlayerState) -> f64 {
    let px = player.x.to_double();
    let py = player.y.to_double();
    let distance = (cx - px).hypot(cy - py);
    let mut score = f64::from(arrival);
    if distance < GOAL_MIN_DISTANCE {
        score -= GOAL_MIN_PENALTY;
    }
    // If two cells are equally safe, prefer the one that gives the player
    // somewhere to go rather than a goal under the bumper.
    score += 0.02 * distance;

    for (corner_x, corner_y) in [
        (0.0, 0.0),
        (PLAYFIELD, 0.0),
        (0.0, PLAYFIELD),
        (PLAYFIELD, PLAYFIELD),
    ] {
        let corner_distance = (cx - corner_x).hypot(cy - corner_y);
        score -= CORNER_PENALTY * (-corner_distance / 8.0).exp();
    }

    let center = PLAYFIELD / 2.0;
    let center_distance = (cx - center).hypot(cy - center);
    score += 0.002 * (center - center_distance);
    score
}

#[derive(Clone, Copy, Debug)]
struct SimEnemy {
    x: f64,
    y: f64,
    vx: f64,
    vy: f64,
    size: f64,
    max_size: f64,
    personality: i8,
    speed: f64,
    inside: bool,
}

impl From<&EnemyState> for SimEnemy {
    fn from(enemy: &EnemyState) -> Self {
        Self {
            x: enemy.x.to_double(),
            y: enemy.y.to_double(),
            vx: enemy.vx.to_double(),
            vy: enemy.vy.to_double(),
            size: enemy.size.to_double(),
            max_size: enemy.max_size.to_double(),
            personality: enemy.personality,
            speed: enemy.speed.to_double(),
            inside: enemy.inside,
        }
    }
}

impl SimEnemy {
    /// One frame of the cartridge's `updateenemies` path, without enemy-enemy
    /// collisions or patterns. The player is a fixed homing target.
    fn step(&mut self, px: f64, py: f64, game_speed: f64, freeze: f64) {
        let mut vx = self.vx * ENEMY_FRICTION;
        let mut vy = self.vy * ENEMY_FRICTION;
        let source_size = self.size;
        let mut size = self.size;
        if size < self.max_size && self.personality != -1 {
            size += freeze;
        }
        if self.personality >= 2 {
            size = 4.0;
        }
        let inside = self.inside || (1.0..=128.0).contains(&self.x);

        if self.personality >= 0 {
            if self.x < px {
                vx += ENEMY_ACCELERATION;
            } else if self.x > px {
                vx -= ENEMY_ACCELERATION;
            }
            if self.y < py {
                vy += ENEMY_ACCELERATION;
            } else if self.y > py {
                vy -= ENEMY_ACCELERATION;
            }
        }

        if inside && self.personality != -1 {
            if self.y >= 129.0 - source_size {
                vy = -vy.abs();
            } else if self.y <= -2.0 {
                vy = vy.abs();
            }
            if self.x >= 129.0 - source_size {
                vx = -vx.abs();
            } else if self.x <= -2.0 {
                vx = vx.abs();
            }
        }

        let mut speed = self.speed;
        if self.personality == 1 {
            let distance = (self.x - px).hypot(self.y - py);
            if distance <= KAMIKAZE_RADIUS {
                speed -= ENEMY_SPEED_STEP;
            } else if speed < 1.0 {
                speed += ENEMY_SPEED_STEP;
            } else {
                speed = 1.0;
            }
        }

        self.x += vx * game_speed * freeze * speed;
        self.y += vy * game_speed * freeze * speed;
        self.vx = vx;
        self.vy = vy;
        self.size = size;
        self.speed = speed;
        self.inside = inside;
    }

    fn overlaps(&self, px: f64, py: f64, player_size: f64) -> bool {
        px + player_size - 1.0 > self.x
            && py + player_size - 1.0 > self.y
            && px - player_size + 1.0 < self.x + self.size
            && py - player_size + 1.0 < self.y + self.size
    }
}

#[derive(Clone, Debug)]
struct Decision {
    action: Action,
    ttc: u32,
    clearance: f64,
    path: Vec<(f64, f64)>,
    costs: Option<[f64; 9]>,
}

impl FrameRecord {
    fn new(
        game: &NativeGame,
        decision: &Decision,
        goal: (f64, f64),
        heat: Option<HeatRecord>,
        played: Action,
        physics: bool,
    ) -> Self {
        let player = game.player();
        let view = game.privileged_view();
        let step = view.speed.to_double() * view.freeze_rate.to_double();
        let mut rects = Vec::new();
        if let Some(pattern) = view.active_pattern {
            let lethal_pattern = pattern.pattern_type == 1;
            for rect in pattern.rects {
                let lethal = lethal_pattern || rect.sh.to_double() == 2.0;
                rects.push([
                    rect.x.to_f32(),
                    rect.y.to_f32(),
                    rect.width.to_f32(),
                    rect.height.to_f32(),
                    if lethal { 1.0 } else { 0.0 },
                ]);
            }
        }
        Self {
            p: [
                player.x.to_f32(),
                player.y.to_f32(),
                player.vx.to_f32(),
                player.vy.to_f32(),
                player.size.to_f32(),
            ],
            e: game
                .enemies()
                .iter()
                .map(|enemy| {
                    let rate = step * enemy.speed.to_double();
                    [
                        enemy.x.to_f32(),
                        enemy.y.to_f32(),
                        (enemy.vx.to_double() * rate) as f32,
                        (enemy.vy.to_double() * rate) as f32,
                        enemy.size.to_f32(),
                        f32::from(enemy.personality),
                    ]
                })
                .collect(),
            r: rects,
            ph: if physics {
                game.enemies()
                    .iter()
                    .map(|enemy| {
                        [
                            enemy.x.to_f32(),
                            enemy.y.to_f32(),
                            enemy.vx.to_f32(),
                            enemy.vy.to_f32(),
                            enemy.size.to_f32(),
                            f32::from(enemy.personality),
                            (step * enemy.speed.to_double()) as f32,
                        ]
                    })
                    .collect()
            } else {
                Vec::new()
            },
            rs: if physics {
                view.active_pattern
                    .map(|pattern| {
                        pattern
                            .rects
                            .iter()
                            .map(|rect| {
                                [
                                    rect.sh.to_f32(),
                                    if pattern.pattern_type == 1 { 1.0 } else { 0.0 },
                                ]
                            })
                            .collect()
                    })
                    .unwrap_or_default()
            } else {
                Vec::new()
            },
            dy: if physics {
                game.enemies()
                    .iter()
                    .map(|enemy| u8::from(enemy.is_dying))
                    .collect()
            } else {
                Vec::new()
            },
            a: decision.action.name(),
            x: (played != decision.action).then(|| played.name()),
            g: [goal.0 as f32, goal.1 as f32],
            t: decision.ttc as f32,
            c: if decision.clearance.is_finite() {
                decision.clearance as f32
            } else {
                999.0
            },
            h: heat,
            path: decision
                .path
                .iter()
                .map(|(x, y)| [*x as f32, *y as f32])
                .collect(),
            costs: decision
                .costs
                .map(|values| values.iter().map(|value| *value as f32).collect()),
        }
    }
}

fn decide(
    game: &NativeGame,
    goal: (f64, f64),
    config: &DangerConfig,
    policy: PolicyKind,
    previous: Action,
    rng: &mut PrivateRng,
) -> Result<Decision, String> {
    match policy {
        PolicyKind::Lookahead => lookahead(game, goal, config, previous),
        PolicyKind::Landscape => {
            let choice = landscape::choose_for_game(game, &config.landscape);
            let rollout = rollout_action(game, choice.action, config.horizon)?;
            Ok(Decision {
                action: choice.action,
                ttc: rollout.ttc,
                clearance: rollout.clearance,
                path: rollout.path,
                costs: Some(choice.costs),
            })
        }
        PolicyKind::Learned => {
            let model = learned::installed().ok_or("no learned model installed (use --model)")?;
            let (action, logits) = model.choose(&learned::Observation::from_game(game));
            let rollout = rollout_action(game, action, config.horizon)?;
            Ok(Decision {
                action,
                ttc: rollout.ttc,
                clearance: rollout.clearance,
                path: rollout.path,
                costs: Some(logits.map(|logit| -logit)),
            })
        }
        PolicyKind::Hnn => {
            let model =
                hnnplan::installed().ok_or("no physics model installed (use --physics-model)")?;
            let (action, costs) = hnnplan::choose(model, game, config.horizon);
            let rollout = rollout_action(game, action, config.horizon)?;
            Ok(Decision {
                action,
                ttc: rollout.ttc,
                clearance: rollout.clearance,
                path: rollout.path,
                costs: Some(costs),
            })
        }
        PolicyKind::Potential => {
            let action = potential_action(game, goal, previous);
            let rollout = rollout_action(game, action, config.horizon)?;
            Ok(Decision {
                action,
                ttc: rollout.ttc,
                clearance: rollout.clearance,
                path: rollout.path,
                costs: None,
            })
        }
        PolicyKind::Flee => {
            let action = flee_action(game, goal, previous);
            let rollout = rollout_action(game, action, config.horizon)?;
            Ok(Decision {
                action,
                ttc: rollout.ttc,
                clearance: rollout.clearance,
                path: rollout.path,
                costs: None,
            })
        }
        PolicyKind::Random => {
            let action = rng.action();
            let rollout = rollout_action(game, action, config.horizon)?;
            Ok(Decision {
                action,
                ttc: rollout.ttc,
                clearance: rollout.clearance,
                path: rollout.path,
                costs: None,
            })
        }
        PolicyKind::Neutral => {
            let rollout = rollout_action(game, Action::Neutral, config.horizon)?;
            Ok(Decision {
                action: Action::Neutral,
                ttc: rollout.ttc,
                clearance: rollout.clearance,
                path: rollout.path,
                costs: None,
            })
        }
    }
}

fn lookahead(
    game: &NativeGame,
    goal: (f64, f64),
    config: &DangerConfig,
    previous: Action,
) -> Result<Decision, String> {
    let start = game.player();
    let start_clearance = min_clearance(game);
    let mut best_action = Action::Neutral;
    let mut best_cost = f64::INFINITY;
    let mut best_ttc = config.horizon + 1;
    let mut best_clearance = start_clearance;
    let mut best_path = vec![(start.x.to_double(), start.y.to_double())];
    let mut costs = [f64::INFINITY; 9];

    for (index, action) in Action::ALL.iter().copied().enumerate() {
        let mut sim = game.clone();
        let mut cost = 0.0;
        let mut ttc = config.horizon + 1;
        let mut clearance = start_clearance;
        let mut path = vec![(start.x.to_double(), start.y.to_double())];

        for frame in 1..=config.horizon {
            let result = sim
                .advance_frame_headless(action.mask())
                .map_err(|error| format!("lookahead frame {frame}: {error}"))?;
            if frame == 1 || frame % 2 == 0 {
                let player = sim.player();
                path.push((player.x.to_double(), player.y.to_double()));
            }
            if result.dead {
                ttc = frame;
                cost += 5_000.0 - 50.0 * f64::from(frame);
                break;
            }
            let gap = min_clearance(&sim);
            if gap < clearance {
                clearance = gap;
            }
            cost += 12.0 / (gap + 1.0).powi(2);
            cost += 0.05 * wall_penalty(&sim.player());
        }

        let player = sim.player();
        cost += 3.0 * (player.x.to_double() - goal.0).hypot(player.y.to_double() - goal.1);
        cost += 8.0 * (-clearance / 3.0).exp();
        if action != previous {
            cost += 0.15;
        }
        if action == Action::Neutral {
            cost += 0.25;
        }
        if let Some(slot) = costs.get_mut(index) {
            *slot = cost;
        }
        if cost < best_cost {
            best_cost = cost;
            best_action = action;
            best_ttc = ttc;
            best_clearance = clearance;
            best_path = path;
        }
    }

    Ok(Decision {
        action: best_action,
        ttc: best_ttc,
        clearance: best_clearance,
        path: best_path,
        costs: Some(costs),
    })
}

#[derive(Clone, Debug)]
struct Rollout {
    ttc: u32,
    clearance: f64,
    path: Vec<(f64, f64)>,
}

fn rollout_action(game: &NativeGame, action: Action, horizon: u32) -> Result<Rollout, String> {
    let start = game.player();
    let mut sim = game.clone();
    let mut ttc = horizon + 1;
    let mut clearance = min_clearance(game);
    let mut path = vec![(start.x.to_double(), start.y.to_double())];
    for frame in 1..=horizon {
        let result = sim
            .advance_frame_headless(action.mask())
            .map_err(|error| format!("rollout frame {frame}: {error}"))?;
        if frame == 1 || frame % 2 == 0 {
            let player = sim.player();
            path.push((player.x.to_double(), player.y.to_double()));
        }
        if result.dead {
            ttc = frame;
            break;
        }
        let gap = min_clearance(&sim);
        if gap < clearance {
            clearance = gap;
        }
    }
    Ok(Rollout {
        ttc,
        clearance,
        path,
    })
}

fn potential_action(game: &NativeGame, goal: (f64, f64), previous: Action) -> Action {
    let player = game.player();
    let px = player.x.to_double();
    let py = player.y.to_double();
    let mut force_x = 0.0;
    let mut force_y = 0.0;

    let goal_dx = goal.0 - px;
    let goal_dy = goal.1 - py;
    let goal_distance = goal_dx.hypot(goal_dy);
    if goal_distance > 0.001 {
        force_x += goal_dx / goal_distance * 1.5;
        force_y += goal_dy / goal_distance * 1.5;
    }

    for enemy in game.enemies() {
        let gap = clearance(&player, enemy).max(0.25);
        let ex = enemy.x.to_double() + enemy.size.to_double() * 0.5;
        let ey = enemy.y.to_double() + enemy.size.to_double() * 0.5;
        let dx = px - ex;
        let dy = py - ey;
        let distance = dx.hypot(dy).max(0.001);
        let weight = 40.0 / (gap + 1.0).powi(2);
        force_x += dx / distance * weight;
        force_y += dy / distance * weight;
    }

    force_x += wall_force(px);
    force_y += wall_force(py);
    choose_direction(force_x, force_y, previous)
}

fn flee_action(game: &NativeGame, goal: (f64, f64), previous: Action) -> Action {
    let player = game.player();
    let nearest = game
        .enemies()
        .iter()
        .min_by(|left, right| clearance(&player, left).total_cmp(&clearance(&player, right)));
    if let Some(enemy) = nearest {
        let ex = enemy.x.to_double() + enemy.size.to_double() * 0.5;
        let ey = enemy.y.to_double() + enemy.size.to_double() * 0.5;
        let dx = player.x.to_double() - ex;
        let dy = player.y.to_double() - ey;
        if dx.hypot(dy) > 0.001 {
            return choose_direction(dx, dy, previous);
        }
    }
    potential_action(game, goal, previous)
}

fn choose_direction(force_x: f64, force_y: f64, previous: Action) -> Action {
    let length = force_x.hypot(force_y);
    if length < 1e-6 {
        return Action::Neutral;
    }
    let ux = force_x / length;
    let uy = force_y / length;
    let mut best = Action::Neutral;
    let mut best_score = f64::NEG_INFINITY;
    for action in Action::ALL {
        let (ax, ay) = action_vector(action);
        let mut score = ux * ax + uy * ay;
        if action == previous {
            score += 0.02;
        }
        if score > best_score {
            best_score = score;
            best = action;
        }
    }
    best
}

fn action_vector(action: Action) -> (f64, f64) {
    match action {
        Action::Neutral => (0.0, 0.0),
        Action::Left => (-1.0, 0.0),
        Action::Right => (1.0, 0.0),
        Action::Up => (0.0, -1.0),
        Action::Down => (0.0, 1.0),
        Action::UpLeft => (-1.0, -1.0),
        Action::UpRight => (1.0, -1.0),
        Action::DownLeft => (-1.0, 1.0),
        Action::DownRight => (1.0, 1.0),
    }
}

fn wall_force(value: f64) -> f64 {
    if value < 8.0 {
        (8.0 - value) * 2.0
    } else if value > 120.0 {
        -(value - 120.0) * 2.0
    } else {
        0.0
    }
}

fn wall_penalty(player: &PlayerState) -> f64 {
    let x = player.x.to_double();
    let y = player.y.to_double();
    (8.0 - x).max(0.0) + (x - 120.0).max(0.0) + (8.0 - y).max(0.0) + (y - 120.0).max(0.0)
}

fn min_clearance(game: &NativeGame) -> f64 {
    let player = game.player();
    game.enemies()
        .iter()
        .map(|enemy| clearance(&player, enemy))
        .fold(f64::INFINITY, f64::min)
}

fn clearance(player: &PlayerState, enemy: &EnemyState) -> f64 {
    box_clearance(
        player.x.to_double(),
        player.y.to_double(),
        player.size.to_double(),
        enemy.x.to_double(),
        enemy.y.to_double(),
        enemy.size.to_double(),
    )
}

fn box_clearance(px: f64, py: f64, player_size: f64, ex: f64, ey: f64, enemy_size: f64) -> f64 {
    let player_left = px - player_size + 1.0;
    let player_right = px + player_size - 1.0;
    let player_top = py - player_size + 1.0;
    let player_bottom = py + player_size - 1.0;
    let enemy_left = ex;
    let enemy_right = ex + enemy_size;
    let enemy_top = ey;
    let enemy_bottom = ey + enemy_size;

    let gap_x = (enemy_left - player_right)
        .max(player_left - enemy_right)
        .max(0.0);
    let gap_y = (enemy_top - player_bottom)
        .max(player_top - enemy_bottom)
        .max(0.0);
    gap_x.hypot(gap_y)
}

fn quantize(value: f32, horizon: u32) -> u8 {
    let normalized = (value / horizon.max(1) as f32).clamp(0.0, 1.0);
    (normalized * 255.0).round() as u8
}

#[derive(Clone, Debug)]
struct PrivateRng(u64);

impl PrivateRng {
    fn new(seed: u32) -> Self {
        Self(u64::from(seed).wrapping_add(0x9E37_79B9_7F4A_7C15))
    }

    fn next_u64(&mut self) -> u64 {
        self.0 = self
            .0
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        self.0
    }

    fn action(&mut self) -> Action {
        let index = (self.next_u64() % 9) as usize;
        Action::ALL.get(index).copied().unwrap_or(Action::Neutral)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn start_sequence_reaches_game() {
        let mut game = NativeGame::new(NativeConfig::new(7));
        start_game(&mut game).expect("start sequence");
        assert_eq!(game.lifecycle().mode, Mode::Game);
        assert!(game.lifecycle().game_ready);
    }

    #[test]
    fn empty_field_puts_goal_at_center() {
        let game = NativeGame::new(NativeConfig::new(7));
        let field = compute_heat(&game, &DangerConfig::default());
        assert_eq!(field.goal, (64.0, 64.0));
        assert!(field.arrival.iter().all(|value| *value == 36.0));
    }

    #[test]
    fn short_lookahead_episode_produces_trace() {
        let config = DangerConfig {
            max_frames: 40,
            grid: 16,
            horizon: 12,
            goal_every: 4,
            heat_every: 8,
            ..DangerConfig::default()
        };
        let episode = run_episode(&config, PolicyKind::Lookahead, true).expect("episode");
        let trace = episode.trace.expect("trace");
        assert_eq!(trace.result.captured_frames, 40);
        assert!(trace.frames.iter().any(|frame| frame.h.is_some()));
    }
}

/// Worker threads for parallel runs. `DODGE_THREADS` sets it; otherwise all cores but four are
/// used, so the machine stays usable for the person running the jobs.
pub fn worker_threads() -> usize {
    if let Some(n) = std::env::var("DODGE_THREADS")
        .ok()
        .and_then(|v| v.parse::<usize>().ok())
    {
        return n.max(1);
    }
    std::thread::available_parallelism()
        .map_or(4, usize::from)
        .saturating_sub(4)
        .max(1)
}
