use crate::EnvError;

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
    /// Record the observation-only gameplay trace (fyou, patterns, death context).
    /// Never changes simulation; reported only on ended episodes.
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
            trace: false,
        }
    }
}

impl EnvConfig {
    pub fn validate(&self) -> Result<(), EnvError> {
        if self.batch_size == 0 {
            return Err(EnvError::Config("batch_size must be positive"));
        }
        if !(1..=4).contains(&self.action_repeat) {
            return Err(EnvError::Config("action_repeat must be 1..=4"));
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
