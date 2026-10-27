//! Optional learning companion for Dodge's deterministic native core.

pub mod env;
pub mod observation;
pub mod privileged;

#[cfg(feature = "python")]
mod python;

pub use env::{EnvError, EnvironmentConfig, LearningEnv, PatternMetrics, StepResult};
