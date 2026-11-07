//! Find and explain the games that the learned planner loses.
//!
//! For each seed the planner plays until it dies (or reaches the frame cap). A short history
//! of game states is kept. After a death the study answers three questions:
//!
//! 1. When did the game become lost? The exact lookahead policy is started from each saved
//!    state. The last state from which lookahead survives `RECOVERY_FRAMES` more frames is
//!    the last point where the death could still have been avoided.
//! 2. What did the planner do there? Its chosen action is compared with lookahead's.
//! 3. Why? The model's imagined future for the chosen action is compared with what the
//!    engine does if that action is held. This sorts the death into a class.
//!
//! Lookahead is used only to judge. The learned planner never sees it.

use std::collections::VecDeque;
use std::sync::Mutex;
use std::sync::atomic::{AtomicU32, Ordering};

use dodge_core::{Action, NativeConfig, NativeGame};
use serde::Serialize;

use crate::{
    DangerConfig, HeatField, PLAYFIELD, PolicyKind, PrivateRng, compute_heat, decide, hnnplan,
    lookahead, rollout_action, start_game,
};

/// States kept before the death.
const HISTORY: usize = 150;
/// A state counts as recoverable if lookahead survives this many more frames from it.
const RECOVERY_FRAMES: u32 = 300;
/// Frames ahead at which the imagined enemy positions are compared with the engine's.
const ERROR_FRAMES: u32 = 12;

#[derive(Clone, Debug, Serialize)]
pub struct DeathCase {
    pub seed: u32,
    pub difficulty: u8,
    pub death_frame: u32,
    pub cause: &'static str,
    /// The game was already lost at the oldest saved state.
    pub lost_before_window: bool,
    /// Frames between the last recoverable state and the death.
    pub frames_before_death: u32,
    pub class: &'static str,
    pub planner_action: &'static str,
    pub lookahead_action: &'static str,
    /// Frame on which the model predicts a hit for the planner's action (`null` = none).
    pub predicted_hit: Option<u32>,
    /// Frame on which the engine kills the player if that action is held (`null` = none).
    pub engine_hit: Option<u32>,
    /// The model's cost for the planner's action and for lookahead's action.
    pub model_cost_planner: f64,
    pub model_cost_lookahead: f64,
    /// Engine hit frame if lookahead's action were held (`null` = none).
    pub engine_hit_lookahead: Option<u32>,
    pub enemies: usize,
    pub kamikaze_near: bool,
    pub blast_near: bool,
    pub nearest_gap: f64,
    pub wall_distance: f64,
    pub enemy_pair_gap: f64,
    /// Largest position error of any enemy after `ERROR_FRAMES` frames, in pixels (`null` = not comparable).
    pub model_error_px: Option<f64>,
    pub worst_error_kind: Option<&'static str>,
}

fn config_for(config: &DangerConfig, seed: u32) -> NativeConfig {
    NativeConfig {
        seed,
        difficulty: config.difficulty,
        patterns_enabled: config.patterns,
        powerups_enabled: config.powerups,
        ..NativeConfig::new(seed)
    }
}

/// Does exact lookahead survive `frames` more frames from this state?
fn survives(start: &NativeGame, config: &DangerConfig, frames: u32) -> Result<bool, String> {
    let mut game = start.clone();
    let mut previous = Action::Neutral;
    let mut goal = (PLAYFIELD / 2.0, PLAYFIELD / 2.0);
    let mut field: Option<HeatField> = None;
    for frame in 0..frames {
        if field.is_none() || frame % config.goal_every == 0 {
            let next = compute_heat(&game, config);
            goal = next.goal;
            field = Some(next);
        }
        let decision = lookahead(&game, goal, config, previous)?;
        previous = decision.action;
        let result = game
            .advance_frame_headless(decision.action.mask())
            .map_err(|error| format!("recovery frame {frame}: {error}"))?;
        if result.dead {
            return Ok(false);
        }
    }
    Ok(true)
}

fn kind_name(personality: i8) -> &'static str {
    match personality {
        0 => "normal",
        1 => "kamikaze",
        -1 => "blast",
        2 => "bomb",
        _ => "bonus",
    }
}

/// Engine position error after `ERROR_FRAMES` frames of holding `action`, against the
/// model's imagined positions. `None` when enemies were added or removed in between.
fn model_error(
    model: &hnnplan::PhysicsModel,
    game: &NativeGame,
    action: Action,
    index: usize,
    horizon: u32,
) -> Option<(f64, &'static str)> {
    let imagined = hnnplan::imagine(model, game, index, horizon, ERROR_FRAMES);
    let mut sim = game.clone();
    for _ in 0..ERROR_FRAMES {
        let result = sim.advance_frame_headless(action.mask()).ok()?;
        if result.dead {
            return None;
        }
    }
    let before: Vec<_> = game
        .enemies()
        .iter()
        .filter(|e| e.personality < 2)
        .collect();
    let after: Vec<_> = sim.enemies().iter().filter(|e| e.personality < 2).collect();
    if before.len() != after.len() || imagined.snapshot.len() != before.len() {
        return None;
    }
    let mut worst = (0.0_f64, "normal");
    for (predicted, truth) in imagined.snapshot.iter().zip(&after) {
        let error = (predicted[0] - truth.x.to_double()).hypot(predicted[1] - truth.y.to_double());
        if error > worst.0 {
            worst = (error, kind_name(truth.personality));
        }
    }
    Some(worst)
}

fn analyse(
    model: &hnnplan::PhysicsModel,
    game: &NativeGame,
    config: &DangerConfig,
    seed: u32,
    death_frame: u32,
    cause: &'static str,
    frames_before_death: u32,
    lost_before_window: bool,
) -> Result<DeathCase, String> {
    let horizon = config.horizon;
    let (planner_action, model_costs) = hnnplan::choose(model, game, horizon);
    let planner_index = Action::ALL
        .iter()
        .position(|a| *a == planner_action)
        .unwrap_or(0);

    // Lookahead's own pick from the same state, with the goal it would use.
    let heat = compute_heat(game, config);
    let teacher = lookahead(game, heat.goal, config, Action::Neutral)?;
    let teacher_index = Action::ALL
        .iter()
        .position(|a| *a == teacher.action)
        .unwrap_or(0);

    let predicted = hnnplan::imagine(model, game, planner_index, horizon, 0).first_hit;
    let engine = rollout_action(game, planner_action, horizon)?;
    let engine_hit = (engine.ttc <= horizon).then_some(engine.ttc);
    let teacher_engine = rollout_action(game, teacher.action, horizon)?;
    let engine_hit_lookahead = (teacher_engine.ttc <= horizon).then_some(teacher_engine.ttc);

    let class = if planner_action == teacher.action {
        "same-action"
    } else if engine_hit.is_none() {
        // Holding the action is safe for the whole horizon, so the loss comes later.
        "horizon-limited"
    } else if predicted.is_none() {
        "model-blind"
    } else {
        "chose-known-risk"
    };

    let player = game.player();
    let (px, py) = (player.x.to_double(), player.y.to_double());
    let lethal: Vec<_> = game
        .enemies()
        .iter()
        .filter(|e| e.personality < 2)
        .collect();
    let nearest_gap = lethal
        .iter()
        .map(|e| {
            crate::box_clearance(
                px,
                py,
                player.size.to_double(),
                e.x.to_double(),
                e.y.to_double(),
                e.size.to_double(),
            )
        })
        .fold(f64::INFINITY, f64::min);
    let mut pair_gap = f64::INFINITY;
    for (i, a) in lethal.iter().enumerate() {
        for b in lethal.iter().skip(i + 1) {
            pair_gap = pair_gap.min(crate::box_clearance(
                a.x.to_double(),
                a.y.to_double(),
                a.size.to_double(),
                b.x.to_double(),
                b.y.to_double(),
                b.size.to_double(),
            ));
        }
    }
    let error = model_error(model, game, planner_action, planner_index, horizon);

    Ok(DeathCase {
        seed,
        difficulty: config.difficulty,
        death_frame,
        cause,
        lost_before_window,
        frames_before_death,
        class,
        planner_action: planner_action.name(),
        lookahead_action: teacher.action.name(),
        predicted_hit: predicted,
        engine_hit,
        model_cost_planner: model_costs[planner_index],
        model_cost_lookahead: model_costs[teacher_index],
        engine_hit_lookahead,
        enemies: lethal.len(),
        kamikaze_near: lethal.iter().any(|e| e.personality == 1),
        blast_near: lethal.iter().any(|e| e.personality == -1),
        nearest_gap,
        wall_distance: px.min(py).min(PLAYFIELD - px).min(PLAYFIELD - py),
        enemy_pair_gap: pair_gap,
        model_error_px: error.map(|e| e.0),
        worst_error_kind: error.map(|e| e.1),
    })
}

/// Play one game with the planner. Returns a death case if it dies before the cap.
fn study_game(config: &DangerConfig, seed: u32) -> Result<Option<DeathCase>, String> {
    let model = hnnplan::installed().ok_or("no physics model installed (use --physics-model)")?;
    let mut game = NativeGame::new(config_for(config, seed));
    start_game(&mut game)?;
    let mut rng = PrivateRng::new(seed);
    let mut history: VecDeque<NativeGame> = VecDeque::with_capacity(HISTORY + 1);
    let mut frame = 0_u32;
    let goal = (PLAYFIELD / 2.0, PLAYFIELD / 2.0);
    loop {
        if frame >= config.max_frames {
            return Ok(None);
        }
        history.push_back(game.clone());
        if history.len() > HISTORY {
            history.pop_front();
        }
        let decision = decide(
            &game,
            goal,
            config,
            PolicyKind::Hnn,
            Action::Neutral,
            &mut rng,
        )?;
        let result = game
            .advance_frame_headless(decision.action.mask())
            .map_err(|error| format!("frame {frame}: {error}"))?;
        if result.dead {
            break;
        }
        frame += 1;
    }
    let cause = game
        .death_diagnostic()
        .cause()
        .map_or("unknown", |c| c.as_str());
    let death_frame = game.survival_frames();
    let states: Vec<NativeGame> = history.into_iter().collect();
    let last = states.len() - 1;

    // Find the last state from which lookahead can still survive.
    let mut lost_before_window = false;
    let recoverable = |index: usize| survives(&states[index], config, RECOVERY_FRAMES);
    let chosen = if !recoverable(0)? {
        lost_before_window = true;
        0
    } else if recoverable(last)? {
        last
    } else {
        // `low` is recoverable, `high` is not. Narrow to adjacent states.
        let (mut low, mut high) = (0, last);
        while high - low > 1 {
            let middle = (low + high) / 2;
            if recoverable(middle)? {
                low = middle;
            } else {
                high = middle;
            }
        }
        low
    };
    let frames_before_death = u32::try_from(last - chosen).unwrap_or(0) + 1;
    analyse(
        model,
        &states[chosen],
        config,
        seed,
        death_frame,
        cause,
        frames_before_death,
        lost_before_window,
    )
    .map(Some)
}

pub struct Study {
    pub games: u32,
    pub deaths: Vec<DeathCase>,
}

/// Play `seeds` games from `config.seed` on all cores and explain every death.
pub fn run(config: &DangerConfig, seeds: u32, threads: usize) -> Result<Study, String> {
    config.validate()?;
    let next = AtomicU32::new(0);
    let found: Mutex<Vec<DeathCase>> = Mutex::new(Vec::new());
    let failure: Mutex<Option<String>> = Mutex::new(None);
    std::thread::scope(|scope| {
        for _ in 0..threads.max(1) {
            scope.spawn(|| {
                loop {
                    let offset = next.fetch_add(1, Ordering::Relaxed);
                    if offset >= seeds {
                        return;
                    }
                    let seed = config.seed.wrapping_add(offset);
                    match study_game(config, seed) {
                        Ok(Some(case)) => {
                            if let Ok(mut list) = found.lock() {
                                list.push(case);
                            }
                        }
                        Ok(None) => {}
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
    let mut deaths = found.into_inner().map_err(|_| "poisoned".to_owned())?;
    deaths.sort_by_key(|case| case.seed);
    Ok(Study {
        games: seeds,
        deaths,
    })
}
