use dodge_core::{PicoFixed, TrainingOptions};

use crate::EnvError;

/// What a step returns as the policy's observation.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum ObservationKind {
    /// The global and per-entity features, with optional pixels and targets.
    #[default]
    Entity,
    /// LaunchSpark/DodgeAI's VelocityFlow grid (`VELOCITY_FLOW_SIZE` values).
    /// No entity motion history is kept.
    VelocityFlow,
}

/// Which slots a step reports `EpisodeInfo` for. Building a Python dict per
/// slot on every step is a large share of a step's cost at large batches.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum StepInfo {
    /// Every slot, every step.
    #[default]
    All,
    /// Only slots that terminated or were truncated on this step.
    Ended,
    /// None; `episode_info()` still reads any slot.
    None,
}

/// Opt-in training variations of the cartridge game. The default is the
/// cartridge itself (`TrainingOptions::CARTRIDGE`).
///
/// The spawn rate is kept as an integer percent so `EnvConfig` stays `Eq`; it
/// is converted exactly as LaunchSpark/DodgeAI's batch binding converts it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TrainingConfig {
    pub normal_enemies: bool,
    pub kamikaze_enemies: bool,
    /// Multiplier on the enemy spawn and between-pattern timers, in percent,
    /// `50..=150`.
    pub spawn_rate_percent: u32,
    /// Lethal contacts absorbed per game.
    pub lives: u8,
}

impl Default for TrainingConfig {
    fn default() -> Self {
        Self {
            normal_enemies: true,
            kamikaze_enemies: true,
            spawn_rate_percent: 100,
            lives: 0,
        }
    }
}

impl TrainingConfig {
    /// The core options these settings select.
    pub fn options(&self) -> TrainingOptions {
        TrainingOptions {
            normal_enemies: self.normal_enemies,
            kamikaze_enemies: self.kamikaze_enemies,
            spawn_rate: PicoFixed::from_f32(self.spawn_rate_percent as f32 / 100.0),
            lives: self.lives,
        }
    }
}

/// Evaluation lists are explicit, per stable slot, then episode. Exhaustion is
/// an error; evaluation seeds are never drawn from the training stream.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SeedMode {
    Training { run_seed: u64 },
    Evaluation { seeds_by_slot: Vec<Vec<u32>> },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EnvConfig {
    pub batch_size: usize,
    pub action_repeat: u8,
    pub difficulty: u8,
    pub patterns_enabled: bool,
    pub powerups_enabled: bool,
    /// Raw gameplay frames, excluding startup. Zero is invalid.
    pub raw_frame_cap: u32,
    pub num_threads: usize,
    pub chunk_size: usize,
    pub render_pixels: bool,
    pub auxiliary_targets: bool,
    pub seed_mode: SeedMode,
    /// Additional inclusive training exclusions. The mandatory B range remains.
    pub excluded_seed_ranges: Vec<(u32, u32)>,
    /// Fresh construction starts at these per-slot episode indices.
    pub initial_episode_indices: Option<Vec<u64>>,
    /// Enemy toggles, spawn rate and lives. Default: the cartridge game.
    pub training: TrainingConfig,
    /// Default: the entity observation.
    pub observation: ObservationKind,
    /// Default: info for every slot.
    pub step_info: StepInfo,
    /// Also return `CRITIC_FEATURE_COUNT` privileged values per slot for a
    /// value head. VelocityFlow only; default off.
    pub critic_features: bool,
    /// Record Taylor Turner's gameplay trace for games started from now on.
    /// Read-only: it never changes a game. Default off.
    pub trace: bool,
}

impl Default for EnvConfig {
    fn default() -> Self {
        Self {
            batch_size: 1,
            action_repeat: 4,
            difficulty: 2,
            patterns_enabled: true,
            powerups_enabled: true,
            raw_frame_cap: 18_000,
            num_threads: 1,
            chunk_size: 8,
            render_pixels: false,
            auxiliary_targets: false,
            seed_mode: SeedMode::Training { run_seed: 0 },
            excluded_seed_ranges: Vec::new(),
            initial_episode_indices: None,
            training: TrainingConfig::default(),
            observation: ObservationKind::Entity,
            step_info: StepInfo::All,
            critic_features: false,
            trace: false,
        }
    }
}

impl EnvConfig {
    pub fn validate(&self) -> Result<(), EnvError> {
        if self.batch_size == 0 {
            return Err(EnvError::Config("batch_size must be positive"));
        }
        // Entity motion history is observed on every raw frame, not per
        // decision, so any repeat from a single frame upward is sound.
        if !(1..=5).contains(&self.action_repeat) {
            return Err(EnvError::Config("action_repeat must be 1..=5"));
        }
        if !(1..=3).contains(&self.difficulty) {
            return Err(EnvError::Config("difficulty must be 1..=3"));
        }
        if self.raw_frame_cap == 0 {
            return Err(EnvError::Config("raw_frame_cap must be positive"));
        }
        if self.num_threads == 0 || self.chunk_size == 0 {
            return Err(EnvError::Config("thread and chunk counts must be positive"));
        }
        if let SeedMode::Evaluation { seeds_by_slot } = &self.seed_mode
            && (seeds_by_slot.len() != self.batch_size || seeds_by_slot.iter().any(Vec::is_empty))
        {
            return Err(EnvError::Config(
                "evaluation needs a nonempty seed list per slot",
            ));
        }
        if self.observation != ObservationKind::Entity
            && (self.render_pixels || self.auxiliary_targets)
        {
            return Err(EnvError::Config(
                "render_pixels and auxiliary_targets need the entity observation",
            ));
        }
        if self.critic_features && self.observation != ObservationKind::VelocityFlow {
            return Err(EnvError::Config(
                "critic_features needs the velocity_flow observation",
            ));
        }
        if !(50..=150).contains(&self.training.spawn_rate_percent) {
            return Err(EnvError::Config(
                "spawn_rate_percent must be between 50 and 150",
            ));
        }
        crate::seed::normalize_seed_exclusions(&self.excluded_seed_ranges)?;
        if let Some(indices) = &self.initial_episode_indices
            && indices.len() != self.batch_size
        {
            return Err(EnvError::Config(
                "initial_episode_indices must have batch_size entries",
            ));
        }
        Ok(())
    }
}
