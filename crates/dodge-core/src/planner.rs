//! Diagnostic action values from branching native-game continuations.
//!
//! This planner reads full native state and is an oracle diagnostic. It is not
//! suitable as a policy input or a training-label source.

use crate::m0_policy::{Policy, PolicyKind};
use crate::{Action, CoreError, NativeGame};
use crate::{ValueModel, value_features};

const FAIR_M0_SCENARIO_COUNT: usize = 4;
/// Maximum leaf horizon for the M0 continuation search.
pub const MAX_M0_ROLLOUT_FRAMES: u32 = 192;
/// Maximum branch-frame work per planner call, before scenario count.
pub const DEFAULT_M0_SEARCH_BUDGET: u32 = 9 * 192 * 4;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum FutureMode {
    /// Every branch continues from the exact RNG state at the decision point.
    KnownSeed,
    /// Every counterfactual gets the same explicit future RNG seeds.
    FairResampled(Vec<u32>),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SearchConfig {
    /// Number of action segments in each continuation. Depth is capped at two
    /// because exhaustive branching grows as 9 to the depth.
    pub depth: u8,
    /// Frames to hold each action segment.
    pub frames_per_step: u32,
}

impl SearchConfig {
    pub const fn new(depth: u8, frames_per_step: u32) -> Self {
        Self {
            depth,
            frames_per_step,
        }
    }
}

/// Frame-equivalent return for each action in [`Action::ALL`] order.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ActionValues {
    pub values: [f64; 9],
    /// Separate bounded M0 preference among actions with equal survival value.
    pub m0_safety_tiebreak: [f64; 9],
}

impl ActionValues {
    /// Select a maximum value. Exact ties use the supplied M0 safety choice.
    pub fn best_action(self, m0_action: Action) -> Action {
        let best = self
            .values
            .iter()
            .copied()
            .fold(f64::NEG_INFINITY, f64::max);
        if self.for_action(m0_action) == best {
            return m0_action;
        }
        let best_tiebreak = self
            .values
            .iter()
            .zip(self.m0_safety_tiebreak)
            .filter(|(value, _)| **value == best)
            .map(|(_, rank)| rank)
            .fold(f64::NEG_INFINITY, f64::max);
        Action::ALL
            .iter()
            .copied()
            .find(|action| {
                self.for_action(*action) == best
                    && self.m0_safety_tiebreak[action_index(*action)] == best_tiebreak
            })
            .unwrap_or(m0_action)
    }
}

fn action_index(action: Action) -> usize {
    Action::ALL
        .iter()
        .position(|candidate| *candidate == action)
        .unwrap_or(0)
}

/// Evaluate each root action, then continue each resampled future with the
/// causal M0 controller. The caller supplies M0 history observed on every real
/// frame up to the current decision. Each future gets its own cloned history.
pub fn plan_action_values_m0(
    game: &NativeGame,
    root_frames: u32,
    rollout_frames: u32,
    mode: &FutureMode,
    observed_policy: &Policy,
) -> Result<ActionValues, CoreError> {
    plan_action_values_m0_with_budget(
        game,
        root_frames,
        rollout_frames,
        DEFAULT_M0_SEARCH_BUDGET,
        mode,
        observed_policy,
    )
}

/// M0 feedback continuation with an explicit frame-equivalent search budget.
pub fn plan_action_values_m0_with_budget(
    game: &NativeGame,
    root_frames: u32,
    rollout_frames: u32,
    search_budget: u32,
    mode: &FutureMode,
    observed_policy: &Policy,
) -> Result<ActionValues, CoreError> {
    if root_frames == 0 || root_frames > 120 {
        return Err(CoreError::InvalidFrameCount(root_frames));
    }
    if rollout_frames > MAX_M0_ROLLOUT_FRAMES
        || root_frames.saturating_add(rollout_frames) > MAX_M0_ROLLOUT_FRAMES
    {
        return Err(CoreError::InvalidFrameCount(rollout_frames));
    }
    if !matches!(observed_policy.kind(), PolicyKind::AabbDodger) {
        return Err(CoreError::InvalidPlannerPolicy);
    }
    let scenarios: Vec<Option<u32>> = match mode {
        FutureMode::KnownSeed => vec![None],
        FutureMode::FairResampled(seeds) if seeds.len() == FAIR_M0_SCENARIO_COUNT => {
            let mut sorted = seeds.clone();
            sorted.sort_unstable();
            sorted.into_iter().map(Some).collect()
        }
        FutureMode::FairResampled(seeds) => {
            return Err(CoreError::InvalidFutureSeedCount(seeds.len()));
        }
    };
    let required_budget = 9_u32
        .saturating_mul(root_frames.saturating_add(rollout_frames))
        .saturating_mul(scenarios.len() as u32);
    if search_budget == 0 || required_budget > search_budget {
        return Err(CoreError::InvalidPlannerBudget {
            required: required_budget,
            budget: search_budget,
        });
    }

    let mut values = [0.0; 9];
    let mut tiebreaks = [0.0; 9];
    for (action_index, action) in Action::ALL.iter().copied().enumerate() {
        let mut total = 0.0;
        let mut m0_preferred = 0_u32;
        for seed in &scenarios {
            let mut branch = game.clone();
            if let Some(seed) = seed {
                branch.reseed_rng_for_planner(*seed);
            }
            let mut policy = observed_policy.clone();
            let mut alive = 0_u32;
            for frame in 0..root_frames.saturating_add(rollout_frames) {
                let chosen = if frame < root_frames {
                    action
                } else {
                    policy.action(branch.snapshot().logical_state())
                };
                let result = branch.advance_frame(chosen.mask())?;
                policy.observe(branch.snapshot().logical_state());
                if result.reward.to_f32() > 0.0 {
                    alive += 1;
                }
                if result.done {
                    break;
                }
            }
            // Return expected capped survival only. M0 supplies a separate
            // safety and clearance choice when action values tie.
            total += f64::from(alive);
            if policy.action(branch.snapshot().logical_state()) == action {
                m0_preferred += 1;
            }
        }
        values[action_index] = total / scenarios.len() as f64;
        tiebreaks[action_index] = f64::from(m0_preferred) / scenarios.len() as f64;
    }
    Ok(ActionValues {
        values,
        m0_safety_tiebreak: tiebreaks,
    })
}

impl ActionValues {
    pub fn for_action(self, action: Action) -> f64 {
        Action::ALL
            .iter()
            .position(|candidate| *candidate == action)
            .and_then(|index| self.values.get(index).copied())
            .unwrap_or(0.0)
    }
}

/// Search all action sequences to `depth`, then return the best continuation
/// value for each first action. Each leaf scores alive frames plus 0.001 times
/// score change, less 1000 frame equivalents on death. Branches clone the
/// source at every decision boundary. The source game is never advanced.
pub fn plan_action_values(
    game: &NativeGame,
    config: SearchConfig,
    mode: &FutureMode,
) -> Result<ActionValues, CoreError> {
    plan_action_values_internal(game, config, mode, None)
}

/// Search with a learned future-survival estimate at depth-limited leaves.
/// Terminal branches keep the exact terminal score and do not query the model.
pub fn plan_action_values_with_value(
    game: &NativeGame,
    config: SearchConfig,
    mode: &FutureMode,
    model: &ValueModel,
) -> Result<ActionValues, CoreError> {
    plan_action_values_internal(game, config, mode, Some(model))
}

fn plan_action_values_internal(
    game: &NativeGame,
    config: SearchConfig,
    mode: &FutureMode,
    model: Option<&ValueModel>,
) -> Result<ActionValues, CoreError> {
    if config.depth == 0 {
        return Err(CoreError::InvalidSearchDepth(config.depth));
    }
    if config.depth > 2 {
        return Err(CoreError::InvalidSearchDepth(config.depth));
    }
    if config.frames_per_step == 0 {
        return Err(CoreError::InvalidFrameCount(0));
    }
    if config.frames_per_step > 120 {
        return Err(CoreError::InvalidFrameCount(config.frames_per_step));
    }
    let mut values = [0.0; 9];
    match mode {
        FutureMode::KnownSeed => {
            for (index, first) in Action::ALL.iter().copied().enumerate() {
                values[index] = best_continuation(game, first, config, 1, model)?;
            }
        }
        FutureMode::FairResampled(seeds) if !seeds.is_empty() => {
            if seeds.len() > 16 {
                return Err(CoreError::InvalidFutureSeedCount(seeds.len()));
            }
            let mut paired_seeds = seeds.clone();
            paired_seeds.sort_unstable();
            // Keep each hypothetical decision common across the paired RNG
            // scenarios. Optimizing each seed separately would reveal its future.
            let roots: Vec<_> = paired_seeds
                .iter()
                .map(|seed| {
                    let mut root = game.clone();
                    root.reseed_rng_for_planner(*seed);
                    (root, false)
                })
                .collect();
            for (index, first) in Action::ALL.iter().copied().enumerate() {
                values[index] = best_continuation_fair(&roots, first, config, 1, model)?;
            }
        }
        FutureMode::FairResampled(_) => return Err(CoreError::InvalidFrameCount(0)),
    }
    Ok(ActionValues {
        values,
        m0_safety_tiebreak: [0.0; 9],
    })
}

fn best_continuation_fair(
    games: &[(NativeGame, bool)],
    action: Action,
    config: SearchConfig,
    level: u8,
    model: Option<&ValueModel>,
) -> Result<f64, CoreError> {
    let mut branches = Vec::with_capacity(games.len());
    let mut total = 0.0;
    for (game, already_dead) in games {
        if *already_dead {
            branches.push((game.clone(), true));
            continue;
        }
        let mut branch = game.clone();
        let mut alive = 0_u32;
        let mut score_delta = 0.0;
        let mut dead = false;
        for _ in 0..config.frames_per_step {
            let score_before = branch.score();
            let result = branch.advance_frame(action.mask())?;
            if result.reward.to_f32() > 0.0 {
                alive += 1;
            }
            score_delta += f64::from(branch.score().sub(score_before).to_f32());
            if result.done {
                dead = true;
                break;
            }
        }
        total += f64::from(alive) + score_delta * 0.001 - if dead { 1000.0 } else { 0.0 };
        if !dead
            && level >= config.depth
            && let Some(model) = model
        {
            total += model.predict(value_features(&branch));
        }
        branches.push((branch, dead));
    }
    let immediate = total / games.len() as f64;
    if level >= config.depth || branches.iter().all(|(_, dead)| *dead) {
        return Ok(immediate);
    }
    let mut continuation = f64::NEG_INFINITY;
    for next in Action::ALL {
        continuation = continuation.max(best_continuation_fair(
            &branches,
            next,
            config,
            level + 1,
            model,
        )?);
    }
    Ok(immediate + continuation)
}

fn best_continuation(
    game: &NativeGame,
    first_action: Action,
    config: SearchConfig,
    level: u8,
    model: Option<&ValueModel>,
) -> Result<f64, CoreError> {
    let mut branch = game.clone();
    let mut alive = 0_u32;
    let mut score_delta = 0.0;
    let mut dead = false;
    for _ in 0..config.frames_per_step {
        let score_before = branch.score();
        let result = branch.advance_frame(first_action.mask())?;
        if result.reward.to_f32() > 0.0 {
            alive += 1;
        }
        score_delta += f64::from(branch.score().sub(score_before).to_f32());
        if result.done {
            dead = true;
            break;
        }
    }
    let immediate = f64::from(alive) + score_delta * 0.001 - if dead { 1000.0 } else { 0.0 };
    if dead {
        return Ok(immediate);
    }
    if level >= config.depth {
        return Ok(immediate + model.map_or(0.0, |m| m.predict(value_features(&branch))));
    }
    let mut continuation = f64::NEG_INFINITY;
    for action in Action::ALL {
        continuation = continuation.max(best_continuation(
            &branch,
            action,
            config,
            level + 1,
            model,
        )?);
    }
    Ok(immediate + continuation)
}

#[cfg(test)]
mod tests {
    use super::{FutureMode, SearchConfig, plan_action_values, plan_action_values_m0};
    use crate::{Action, BUTTON_X_MASK, NativeConfig, NativeGame};

    fn active_game() -> Result<NativeGame, crate::CoreError> {
        let mut game = NativeGame::new(NativeConfig::new(42));
        game.advance_frame(BUTTON_X_MASK)?;
        for _ in 0..120 {
            if game.advance_frame(0)?.done {
                return Ok(game);
            }
        }
        Ok(game)
    }

    #[test]
    fn depth_two_returns_all_nine_values_and_does_not_mutate_source() -> Result<(), crate::CoreError>
    {
        let game = active_game()?;
        let rng = game.rng_checkpoint();
        let snapshot = game.snapshot().canonical_bytes();
        let values = plan_action_values(&game, SearchConfig::new(2, 3), &FutureMode::KnownSeed)?;
        assert_eq!(values.values.len(), Action::ALL.len());
        assert!(values.values.iter().all(|value| value.is_finite()));
        assert_eq!(game.rng_checkpoint(), rng);
        assert_eq!(game.snapshot().canonical_bytes(), snapshot);
        Ok(())
    }

    #[test]
    fn fair_values_are_seed_order_independent_and_repeatable() -> Result<(), crate::CoreError> {
        let game = active_game()?;
        let rng = game.rng_checkpoint();
        let snapshot = game.snapshot().canonical_bytes();
        let config = SearchConfig::new(2, 4);
        let forward = plan_action_values(&game, config, &FutureMode::FairResampled(vec![17, 29]))?;
        let reverse = plan_action_values(&game, config, &FutureMode::FairResampled(vec![29, 17]))?;
        assert_eq!(forward, reverse);
        assert_eq!(
            forward,
            plan_action_values(&game, config, &FutureMode::FairResampled(vec![17, 29]))?
        );
        assert_eq!(game.rng_checkpoint(), rng);
        assert_eq!(game.snapshot().canonical_bytes(), snapshot);
        Ok(())
    }

    #[test]
    fn known_seed_values_repeat() -> Result<(), crate::CoreError> {
        let game = active_game()?;
        let config = SearchConfig::new(2, 4);
        assert_eq!(
            plan_action_values(&game, config, &FutureMode::KnownSeed)?,
            plan_action_values(&game, config, &FutureMode::KnownSeed)?
        );
        Ok(())
    }

    #[test]
    fn extended_causal_horizon_discriminates_action_values() -> Result<(), crate::CoreError> {
        let mut game = active_game()?;
        let mut history =
            crate::m0_policy::Policy::new(crate::m0_policy::PolicyKind::AabbDodger, 42);
        let mut action = Action::Neutral;
        let mut discriminated = false;
        for frame in 0..900 {
            history.observe(game.snapshot().logical_state());
            if frame % 60 == 0 {
                let values = crate::plan_action_values_m0_with_budget(
                    &game,
                    4,
                    92,
                    9 * 96,
                    &FutureMode::KnownSeed,
                    &history,
                )?;
                assert_eq!(values.values.len(), Action::ALL.len());
                assert!(values.values.iter().all(|value| value.is_finite()));
                discriminated |= values.values.iter().any(|value| *value != values.values[0])
                    || values
                        .m0_safety_tiebreak
                        .iter()
                        .any(|value| *value != values.m0_safety_tiebreak[0]);
                action = values.best_action(history.action(game.snapshot().logical_state()));
                if discriminated {
                    break;
                }
            } else if frame % 4 == 0 {
                action = history.action(game.snapshot().logical_state());
            }
            if game.advance_frame(action.mask())?.done {
                break;
            }
        }
        assert!(
            discriminated,
            "fixture trajectory had no action-value separation"
        );
        Ok(())
    }

    #[test]
    fn exact_value_ties_prefer_the_m0_safety_choice() {
        let mut values = super::ActionValues {
            values: [52.0; 9],
            m0_safety_tiebreak: [0.0; 9],
        };
        values.m0_safety_tiebreak[2] = 1.0;
        assert_eq!(values.best_action(Action::UpLeft), Action::UpLeft);
        assert_eq!(values.best_action(Action::Neutral), Action::Neutral);
    }

    #[test]
    fn leaf_m0_preference_breaks_ties_when_current_m0_action_is_not_available() {
        let mut values = super::ActionValues {
            values: [0.0; 9],
            m0_safety_tiebreak: [0.0; 9],
        };
        values.values[Action::Right as usize] = 1.0;
        values.values[Action::Left as usize] = 1.0;
        values.m0_safety_tiebreak[Action::Left as usize] = 0.75;
        assert_eq!(values.best_action(Action::UpLeft), Action::Left);
    }

    #[test]
    fn rejects_search_work_above_explicit_budget() -> Result<(), crate::CoreError> {
        let game = active_game()?;
        let mut history =
            crate::m0_policy::Policy::new(crate::m0_policy::PolicyKind::AabbDodger, 42);
        history.observe(game.snapshot().logical_state());
        assert_eq!(
            crate::plan_action_values_m0_with_budget(
                &game,
                4,
                92,
                9 * 95,
                &FutureMode::KnownSeed,
                &history,
            ),
            Err(crate::CoreError::InvalidPlannerBudget {
                required: 9 * 96,
                budget: 9 * 95
            })
        );
        Ok(())
    }

    #[test]
    fn rejects_search_depth_above_budgeted_limit() -> Result<(), crate::CoreError> {
        let game = active_game()?;
        assert_eq!(
            plan_action_values(&game, SearchConfig::new(3, 1), &FutureMode::KnownSeed),
            Err(crate::CoreError::InvalidSearchDepth(3))
        );
        Ok(())
    }

    #[test]
    fn learned_leaf_search_is_repeatable_and_does_not_leak_rng() -> Result<(), crate::CoreError> {
        let game = active_game()?;
        let rng = game.rng_checkpoint();
        let snapshot = game.snapshot().canonical_bytes();
        let model = crate::ValueModel {
            mean: [0.0; crate::FEATURE_COUNT],
            scale: [1.0; crate::FEATURE_COUNT],
            w1: [[0.0; crate::FEATURE_COUNT]; 32],
            b1: [0.0; 32],
            w2: [[0.0; 32]; 16],
            b2: [0.0; 16],
            w3: [0.0; 16],
            b3: 7.0,
        };
        let config = SearchConfig::new(2, 3);
        let mode = FutureMode::FairResampled(vec![17, 29]);
        let result = crate::plan_action_values_with_value(&game, config, &mode, &model)?;
        assert!(result.values.iter().all(|value| value.is_finite()));
        assert_eq!(
            result,
            crate::plan_action_values_with_value(&game, config, &mode, &model)?
        );
        assert_eq!(rng, game.rng_checkpoint());
        assert_eq!(snapshot, game.snapshot().canonical_bytes());
        Ok(())
    }

    #[test]
    fn fair_m0_values_ignore_the_episode_future_rng() -> Result<(), crate::CoreError> {
        let game = active_game()?;
        let mut reseeded_episode = game.clone();
        reseeded_episode.reseed_rng_for_planner(0xBAD5_EED);
        let mut history =
            crate::m0_policy::Policy::new(crate::m0_policy::PolicyKind::AabbDodger, 42);
        history.observe(game.snapshot().logical_state());
        let futures = FutureMode::FairResampled(vec![17, 29, 43, 61]);
        let config = (1, 3);
        let original = plan_action_values_m0(&game, config.0, config.1, &futures, &history)?;
        let changed =
            plan_action_values_m0(&reseeded_episode, config.0, config.1, &futures, &history)?;
        assert_eq!(original, changed);
        Ok(())
    }
}
