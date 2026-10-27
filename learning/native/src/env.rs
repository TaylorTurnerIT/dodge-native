//! Seeded episodes and action-duration semantics for native Dodge learning.

use std::fmt::{Display, Formatter};

use dodge_core::{
    Action, BUTTON_X_MASK, CoreError, FrameEvent, FrameResult, Mode, NativeConfig, NativeGame,
    PALETTE_SIZE,
};

const MAX_STARTUP_FRAMES: u32 = 64;

/// Configuration for independent native-game episodes.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct EnvironmentConfig {
    pub game: NativeConfig,
    pub max_episode_frames: u32,
    pub action_repeat: u32,
    /// Discount applied once per actual native frame, including repeated actions.
    pub discount: f32,
}

impl Default for EnvironmentConfig {
    fn default() -> Self {
        Self {
            game: NativeConfig::new(42),
            max_episode_frames: 18_000,
            action_repeat: 1,
            discount: 0.99,
        }
    }
}

impl EnvironmentConfig {
    fn validate(self) -> Result<(), EnvError> {
        if self.max_episode_frames == 0 {
            return Err(EnvError::InvalidConfig(
                "max_episode_frames must be positive",
            ));
        }
        if self.action_repeat == 0 {
            return Err(EnvError::InvalidConfig("action_repeat must be positive"));
        }
        if !self.discount.is_finite() || self.discount <= 0.0 || self.discount > 1.0 {
            return Err(EnvError::InvalidConfig(
                "discount must be finite and in (0, 1]",
            ));
        }
        if !(1..=3).contains(&self.game.difficulty) {
            return Err(EnvError::InvalidConfig("difficulty must be from 1 to 3"));
        }
        if usize::from(self.game.theme_background) >= PALETTE_SIZE
            || usize::from(self.game.theme_shadow) >= PALETTE_SIZE
        {
            return Err(EnvError::InvalidConfig(
                "theme colors must be valid palette indices",
            ));
        }
        Ok(())
    }
}

/// Errors at the environment boundary. Invalid calls do not advance the game.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum EnvError {
    InvalidConfig(&'static str),
    InvalidAction(usize),
    EpisodeFinished,
    StartupTimeout,
    Core(CoreError),
}

impl Display for EnvError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidConfig(message) => {
                write!(formatter, "invalid environment config: {message}")
            }
            Self::InvalidAction(action) => {
                write!(formatter, "action id must be from 0 to 8: {action}")
            }
            Self::EpisodeFinished => formatter.write_str("episode finished; reset before stepping"),
            Self::StartupTimeout => {
                formatter.write_str("game did not reach a live ready frame during startup")
            }
            Self::Core(error) => write!(formatter, "native game step failed: {error}"),
        }
    }
}

impl std::error::Error for EnvError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Core(error) => Some(error),
            _ => None,
        }
    }
}

impl From<CoreError> for EnvError {
    fn from(error: CoreError) -> Self {
        Self::Core(error)
    }
}

/// One decision interval, ending at the returned canonical observation.
#[derive(Clone, Debug)]
pub struct StepResult {
    pub frame: FrameResult,
    /// Undiscounted reward for reporting across every actual native frame.
    pub reward_sum: f32,
    /// Within-interval reward, discounted from the first executed frame.
    pub discounted_reward: f32,
    /// Zero after death, otherwise `discount` to the actual interval length.
    pub bootstrap_discount: f32,
    pub elapsed_native_frames: u32,
    pub episode_frames: u32,
    pub terminated: bool,
    pub truncated: bool,
    /// Ordered events from every frame, not only the last repeated frame.
    pub events: Vec<FrameEvent>,
}

/// Episode diagnostics for one cartridge pattern identity.
///
/// These identifiers and counts are evaluation metadata, not actor features.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PatternMetrics {
    pub id: u8,
    pub encounters: u32,
    pub exposure_frames: u32,
    pub completions: u32,
}

/// Owns one simulator; reset always constructs a fresh seeded native instance.
///
/// The current observation is the snapshot returned by frame execution. It is
/// deliberately separate from the simulator's later live checkpoint boundary.
#[derive(Clone, Debug)]
pub struct LearningEnv {
    config: EnvironmentConfig,
    game: NativeGame,
    current: FrameResult,
    episode_frames: u32,
    pattern_completions: u32,
    pattern_metrics: Vec<PatternMetrics>,
    terminated: bool,
    truncated: bool,
}

impl LearningEnv {
    pub fn new(config: EnvironmentConfig) -> Result<Self, EnvError> {
        config.validate()?;
        let (game, current) = start_game(config.game)?;
        Ok(Self {
            config,
            game,
            current,
            episode_frames: 0,
            pattern_completions: 0,
            pattern_metrics: Vec::new(),
            terminated: false,
            truncated: false,
        })
    }

    /// Start an independent episode without carrying mutable state from retry.
    pub fn reset(&mut self, seed: u32) -> Result<&FrameResult, EnvError> {
        let mut game_config = self.config.game;
        game_config.seed = seed;
        let (game, current) = start_game(game_config)?;
        self.config.game = game_config;
        self.game = game;
        self.current = current;
        self.episode_frames = 0;
        self.pattern_completions = 0;
        self.pattern_metrics.clear();
        self.terminated = false;
        self.truncated = false;
        Ok(&self.current)
    }

    pub fn current(&self) -> &FrameResult {
        &self.current
    }

    pub const fn config(&self) -> EnvironmentConfig {
        self.config
    }

    /// Agent-controlled frames only; startup frames are excluded.
    pub const fn elapsed_frames(&self) -> u32 {
        self.episode_frames
    }

    /// Active patterns that ended while alive during this independent episode.
    pub const fn pattern_completions(&self) -> u32 {
        self.pattern_completions
    }

    /// Per-pattern evaluation metadata, sorted by cartridge pattern identity.
    pub fn pattern_metrics(&self) -> &[PatternMetrics] {
        &self.pattern_metrics
    }

    pub const fn terminated(&self) -> bool {
        self.terminated
    }

    pub const fn truncated(&self) -> bool {
        self.truncated
    }

    pub fn step(&mut self, action_id: usize) -> Result<StepResult, EnvError> {
        let action = Action::ALL
            .get(action_id)
            .copied()
            .ok_or(EnvError::InvalidAction(action_id))?;
        if self.terminated || self.truncated {
            return Err(EnvError::EpisodeFinished);
        }

        let mut reward_sum = 0.0_f32;
        let mut discounted_reward = 0.0_f32;
        let mut bootstrap_discount = 1.0_f32;
        let mut elapsed_native_frames = 0_u32;
        let mut events = Vec::new();
        let remaining_frames = self.config.max_episode_frames - self.episode_frames;

        for _ in 0..self.config.action_repeat.min(remaining_frames) {
            let previous_pattern = active_pattern_id(&self.current);
            let frame = self.game.advance_frame(action.mask())?;
            self.record_patterns(previous_pattern, active_pattern_id(&frame), frame.done);
            let reward = frame.reward.to_f32();
            reward_sum += reward;
            discounted_reward += bootstrap_discount * reward;
            bootstrap_discount *= self.config.discount;
            elapsed_native_frames += 1;
            self.episode_frames += 1;
            events.extend(frame.events.iter().copied());
            self.terminated = frame.done;
            self.current = frame;
            if self.terminated {
                break;
            }
        }

        // A death exactly at the frame limit is a terminal transition. Only a
        // live time-limit transition bootstraps from its final observation.
        self.truncated = !self.terminated && self.episode_frames == self.config.max_episode_frames;
        if self.terminated {
            bootstrap_discount = 0.0;
        }

        Ok(StepResult {
            frame: self.current.clone(),
            reward_sum,
            discounted_reward,
            bootstrap_discount,
            elapsed_native_frames,
            episode_frames: self.episode_frames,
            terminated: self.terminated,
            truncated: self.truncated,
            events,
        })
    }

    fn record_patterns(&mut self, previous: Option<u8>, current: Option<u8>, done: bool) {
        if let Some(id) = current {
            let metric = self.pattern_metric_mut(id);
            if previous != current {
                metric.encounters += 1;
            }
            metric.exposure_frames += 1;
        }
        if let Some(id) = previous
            && current.is_none()
            && !done
        {
            self.pattern_completions += 1;
            self.pattern_metric_mut(id).completions += 1;
        }
    }

    fn pattern_metric_mut(&mut self, id: u8) -> &mut PatternMetrics {
        let index = match self
            .pattern_metrics
            .binary_search_by_key(&id, |metric| metric.id)
        {
            Ok(index) => index,
            Err(index) => {
                self.pattern_metrics.insert(
                    index,
                    PatternMetrics {
                        id,
                        encounters: 0,
                        exposure_frames: 0,
                        completions: 0,
                    },
                );
                index
            }
        };
        &mut self.pattern_metrics[index]
    }
}

fn active_pattern_id(frame: &FrameResult) -> Option<u8> {
    let state = frame.snapshot.logical_state();
    state
        .active_pattern
        .and_then(|index| state.patterns.get(index))
        .map(|pattern| pattern.id)
}

fn start_game(config: NativeConfig) -> Result<(NativeGame, FrameResult), EnvError> {
    let mut game = NativeGame::new(config);
    let mut current = game.advance_frame(BUTTON_X_MASK)?;
    for _ in 1..MAX_STARTUP_FRAMES {
        if current.game_ready && current.mode == Mode::Game && !current.dead {
            return Ok((game, current));
        }
        current = game.advance_frame(0)?;
    }
    if current.game_ready && current.mode == Mode::Game && !current.dead {
        Ok((game, current))
    } else {
        Err(EnvError::StartupTimeout)
    }
}

#[cfg(test)]
mod tests {
    use std::error::Error;

    use dodge_core::{
        Action, BUTTON_X_MASK, FrameResult, Mode, NativeConfig, NativeGame, PicoFixed,
    };

    use super::{EnvError, EnvironmentConfig, LearningEnv, PatternMetrics};

    type TestResult = Result<(), Box<dyn Error>>;

    fn start_direct(config: NativeConfig) -> Result<(NativeGame, FrameResult), Box<dyn Error>> {
        let mut game = NativeGame::new(config);
        let mut frame = game.advance_frame(BUTTON_X_MASK)?;
        for _ in 1..13 {
            frame = game.advance_frame(0)?;
        }
        assert_eq!(frame.mode, Mode::Game);
        assert!(frame.game_ready);
        Ok((game, frame))
    }

    fn neutral_death_frame() -> Result<u32, Box<dyn Error>> {
        let (mut game, _) = start_direct(NativeConfig::new(42))?;
        for frame in 1..=10_000 {
            if game.advance_frame(Action::Neutral.mask())?.done {
                return Ok(frame);
            }
        }
        Err("seed 42 neutral fixture did not terminate within 10000 agent frames".into())
    }

    #[test]
    fn startup_preserves_capture_boundary_and_live_continuation() -> TestResult {
        let mut env = LearningEnv::new(EnvironmentConfig::default())?;
        let (mut direct, frame) = start_direct(NativeConfig::new(42))?;
        assert_eq!(env.current(), &frame);
        assert_eq!(env.current().frame, 13);
        assert_eq!(env.elapsed_frames(), 0);
        assert_eq!(env.pattern_completions(), 0);
        assert_eq!(env.current().input_mask, 0);
        assert_eq!(env.current().previous_input_mask, 0);
        assert!(!env.terminated());
        assert!(!env.truncated());

        // Startup has one post-capture trail mutation. The observation must
        // remain at capture even though continuation uses the later live state.
        let checkpoint = env.game.snapshot();
        assert_ne!(env.current().snapshot.state_hash(), checkpoint.state_hash());
        assert_eq!(env.current().snapshot.pixel_hash(), checkpoint.pixel_hash());
        let mut restored = NativeGame::restore(&checkpoint)?;
        let result = env.step(2)?;
        let direct_frame = direct.advance_frame(Action::Right.mask())?;
        let restored_frame = restored.advance_frame(Action::Right.mask())?;
        assert_eq!(result.frame, direct_frame);
        assert_eq!(result.frame, restored_frame);
        Ok(())
    }

    #[test]
    fn fixed_seed_action_trace_matches_core_exactly() -> TestResult {
        let mut env = LearningEnv::new(EnvironmentConfig::default())?;
        let (mut direct, _) = start_direct(env.config().game)?;
        for action_id in [0, 1, 2, 3, 4, 5, 6, 7, 8, 8, 6, 4, 2, 0] {
            let result = env.step(action_id)?;
            let action = Action::ALL.get(action_id).ok_or("invalid fixture action")?;
            let expected = direct.advance_frame(action.mask())?;
            assert_eq!(result.frame, expected);
            assert_eq!(result.elapsed_native_frames, 1);
            assert_eq!(result.reward_sum, expected.reward.to_f32());
        }
        Ok(())
    }

    #[test]
    fn reset_reconstructs_fresh_seed_and_preserves_configuration() -> TestResult {
        let mut game = NativeConfig::new(9);
        game.difficulty = 1;
        game.patterns_enabled = false;
        game.powerups_enabled = false;
        game.theme_background = 3;
        game.theme_shadow = 1;
        game.highscores[0] = PicoFixed::from_int(123);
        let config = EnvironmentConfig {
            game,
            max_episode_frames: 12,
            action_repeat: 4,
            discount: 0.9,
        };
        let mut env = LearningEnv::new(config)?;
        for action in [1, 8, 3] {
            let _ = env.step(action)?;
        }
        assert!(env.truncated());
        env.pattern_completions = 7;
        env.record_patterns(None, Some(3), false);
        let first = env.reset(74)?.clone();
        assert_eq!(env.elapsed_frames(), 0);
        assert_eq!(env.pattern_completions(), 0);
        assert!(env.pattern_metrics().is_empty());
        assert!(!env.terminated());
        assert!(!env.truncated());
        let mut fresh_config = config;
        fresh_config.game.seed = 74;
        let fresh = LearningEnv::new(fresh_config)?;
        assert_eq!(env.config(), fresh_config);
        assert_eq!(&first, fresh.current());
        let _ = env.step(6)?;
        let second = env.reset(74)?.clone();
        assert_eq!(first, second);
        Ok(())
    }

    #[test]
    fn repeated_actions_accumulate_and_discount_every_reward() -> TestResult {
        let mut env = LearningEnv::new(EnvironmentConfig {
            action_repeat: 4,
            discount: 0.5,
            ..EnvironmentConfig::default()
        })?;
        let (mut direct, _) = start_direct(env.config().game)?;
        let mut expected = None;
        for _ in 0..4 {
            expected = Some(direct.advance_frame(Action::Neutral.mask())?);
        }
        let result = env.step(0)?;
        assert_eq!(Some(&result.frame), expected.as_ref());
        assert_eq!(result.reward_sum, 4.0);
        assert_eq!(result.discounted_reward, 1.875);
        assert_eq!(result.bootstrap_discount, 0.0625);
        assert_eq!(result.elapsed_native_frames, 4);
        assert_eq!(result.episode_frames, 4);
        assert!(!result.terminated);
        assert!(!result.truncated);
        Ok(())
    }

    #[test]
    fn time_limit_stops_inside_repeat_and_preserves_bootstrap() -> TestResult {
        let mut env = LearningEnv::new(EnvironmentConfig {
            max_episode_frames: 2,
            action_repeat: 4,
            discount: 0.5,
            ..EnvironmentConfig::default()
        })?;
        let result = env.step(0)?;
        assert_eq!(result.elapsed_native_frames, 2);
        assert_eq!(result.episode_frames, 2);
        assert_eq!(result.frame.frame, 15);
        assert_eq!(result.reward_sum, 2.0);
        assert_eq!(result.discounted_reward, 1.5);
        assert_eq!(result.bootstrap_discount, 0.25);
        assert!(!result.terminated);
        assert!(result.truncated);
        let final_observation = env.current().clone();
        assert_eq!(env.step(0).err(), Some(EnvError::EpisodeFinished));
        assert_eq!(env.current(), &final_observation);
        Ok(())
    }

    #[test]
    fn death_stops_inside_repeat_without_losing_prior_rewards_or_events() -> TestResult {
        let death_frame = neutral_death_frame()?;
        let mut env = LearningEnv::new(EnvironmentConfig {
            max_episode_frames: death_frame + 10,
            action_repeat: death_frame + 7,
            discount: 1.0,
            ..EnvironmentConfig::default()
        })?;
        let result = env.step(0)?;
        assert_eq!(result.elapsed_native_frames, death_frame);
        assert_eq!(result.reward_sum, (death_frame - 1) as f32);
        assert_eq!(result.discounted_reward, result.reward_sum);
        assert_eq!(result.bootstrap_discount, 0.0);
        assert!(result.terminated);
        assert!(!result.truncated);
        assert!(result.events.contains(&dodge_core::FrameEvent::EnemySpawn));
        assert!(result.events.contains(&dodge_core::FrameEvent::Death));
        assert_eq!(env.step(0).err(), Some(EnvError::EpisodeFinished));
        Ok(())
    }

    #[test]
    fn death_at_frame_cap_takes_precedence_over_truncation() -> TestResult {
        let death_frame = neutral_death_frame()?;
        let mut env = LearningEnv::new(EnvironmentConfig {
            max_episode_frames: death_frame,
            action_repeat: death_frame + 1,
            ..EnvironmentConfig::default()
        })?;
        let result = env.step(0)?;
        assert_eq!(result.episode_frames, death_frame);
        assert!(result.frame.done);
        assert!(result.terminated);
        assert!(!result.truncated);
        assert_eq!(result.bootstrap_discount, 0.0);
        Ok(())
    }

    #[test]
    fn pattern_metrics_count_identity_transitions_exposure_and_live_completion() -> TestResult {
        let mut env = LearningEnv::new(EnvironmentConfig::default())?;
        env.record_patterns(None, Some(7), false);
        env.record_patterns(Some(7), Some(7), false);
        env.record_patterns(Some(7), Some(2), false);
        env.record_patterns(Some(2), None, false);
        env.record_patterns(None, Some(7), false);
        env.record_patterns(Some(7), Some(7), true);
        env.record_patterns(Some(7), None, true);
        assert_eq!(env.pattern_completions(), 1);
        assert_eq!(
            env.pattern_metrics(),
            &[
                PatternMetrics {
                    id: 2,
                    encounters: 1,
                    exposure_frames: 1,
                    completions: 1
                },
                PatternMetrics {
                    id: 7,
                    encounters: 2,
                    exposure_frames: 4,
                    completions: 0
                },
            ]
        );
        Ok(())
    }

    #[test]
    fn invalid_action_does_not_advance_state() -> TestResult {
        let mut env = LearningEnv::new(EnvironmentConfig::default())?;
        let before = env.current().clone();
        assert_eq!(env.step(9).err(), Some(EnvError::InvalidAction(9)));
        assert_eq!(
            env.step(usize::MAX).err(),
            Some(EnvError::InvalidAction(usize::MAX))
        );
        assert_eq!(env.current(), &before);
        assert_eq!(env.elapsed_frames(), 0);
        Ok(())
    }

    #[test]
    fn invalid_configuration_is_rejected() {
        let default = EnvironmentConfig::default();
        let mut configs = vec![
            EnvironmentConfig {
                max_episode_frames: 0,
                ..default
            },
            EnvironmentConfig {
                action_repeat: 0,
                ..default
            },
        ];
        for discount in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, -1.0, 0.0, 1.01] {
            configs.push(EnvironmentConfig {
                discount,
                ..default
            });
        }
        for difficulty in [0, 4, u8::MAX] {
            let mut config = default;
            config.game.difficulty = difficulty;
            configs.push(config);
        }
        for color in [16, u8::MAX] {
            let mut background = default;
            background.game.theme_background = color;
            configs.push(background);
            let mut shadow = default;
            shadow.game.theme_shadow = color;
            configs.push(shadow);
        }
        for config in configs {
            assert!(matches!(
                LearningEnv::new(config),
                Err(EnvError::InvalidConfig(_))
            ));
        }
    }
}
