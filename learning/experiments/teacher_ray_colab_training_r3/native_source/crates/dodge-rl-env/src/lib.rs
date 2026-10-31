//! Owned-batch Dodge environment with optional Python support and no window dependency.
mod config;
mod env;
mod features;
pub mod geometry;
// Unit-test environments contain Send-only raw observer closures. The normal
// library (including all-feature Clippy) and real extension compile this module.
#[cfg(all(feature = "python", not(test)))]
mod python;
pub mod raster;
mod seed;

pub use config::{EnvConfig, SeedMode};
pub use env::{BatchInfo, DeathInfo, EpisodeInfo, ResetBatch, StepBatch, VecDodgeEnv};
pub use features::{
    Diagnostics, ENEMY_SLOTS, ENTITY_DIM, ENTITY_SLOTS, GLOBAL_DIM, MOTION_VERSION, Observation,
    ObservationBatch, RECT_SLOTS,
};
pub use seed::{
    MANDATORY_SEED_RANGE, SEED_EXCLUSION_VERSION, SEED_STREAM_VERSION, SeedMetadata,
    normalize_seed_exclusions, training_seed, training_seed_with_exclusions,
};

/// A batch failure requires `reset_all`; ordinary validation errors do not mutate.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum EnvError {
    Config(&'static str),
    ActionShape {
        expected: usize,
        actual: usize,
    },
    ActionId {
        slot: usize,
        id: i64,
    },
    SlotIndex(usize),
    DuplicateReset(usize),
    SlotNotEnded(usize),
    SlotEnded(usize),
    PracticeShape {
        indices: usize,
        horizons: usize,
    },
    DuplicatePractice(usize),
    PracticeHorizon {
        slot: usize,
        horizon: u32,
    },
    PracticeFrame {
        slot: usize,
        expected: u32,
        actual: u32,
    },
    Poisoned,
    SeedExhausted {
        slot: usize,
        episode: u64,
    },
    CounterExhausted,
    Native(String),
    Contract(&'static str),
    RectangleOverflow(usize),
    BatchFailure(Vec<(usize, String)>),
}

impl std::fmt::Display for EnvError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for EnvError {}

impl From<dodge_core::CoreError> for EnvError {
    fn from(value: dodge_core::CoreError) -> Self {
        Self::Native(value.to_string())
    }
}

#[cfg(test)]
mod tests;

#[cfg(test)]
mod qualification_replay_tests;

#[cfg(test)]
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[cfg(test)]
mod seed_extension_tests;

#[cfg(test)]
mod death_tests;
