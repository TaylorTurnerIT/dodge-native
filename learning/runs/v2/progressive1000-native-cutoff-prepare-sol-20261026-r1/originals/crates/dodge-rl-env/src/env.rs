use dodge_core::{
    Action, BUTTON_X_MASK, DeathCause, FRAMEBUFFER_SIZE, Mode, NativeConfig, NativeGame,
};
use rayon::prelude::*;

use crate::features::{History, Observation, ObservationBatch};
use crate::seed::{SEED_EXCLUSION_VERSION, SeedMetadata, normalize_seed_exclusions, seed_for};
use crate::{EnvConfig, EnvError, MOTION_VERSION, SEED_STREAM_VERSION};

const STARTUP_LIMIT: u32 = 64;
const PINNED_STARTUP_FRAMES: u32 = 13;

#[cfg(test)]
type RawObserver = Box<dyn FnMut(&NativeGame) + Send>;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BatchInfo {
    pub config: EnvConfig,
    pub seed_stream_version: &'static str,
    pub motion_version: &'static str,
    pub seed_exclusion_version: &'static str,
    pub effective_excluded_seed_ranges: Vec<(u32, u32)>,
    pub initial_episode_indices: Vec<u64>,
    pub theme_background_shadow: [u8; 2],
    pub initial_highscores_raw_fixed: [i32; 12],
}

/// Diagnostic cause of a terminated episode. Never part of observations.
///
/// `cause` is the first lethal collision in legacy source order on the fatal
/// frame. `observed_lethal_contacts` counts every lethal `die()` the legacy
/// loop processed on that same frame, indexed by `DeathCause::index` (the
/// first cause included). Extra entries record contacts the loop also
/// reached; they are not alternate proven causes. Termination, the single
/// -5 penalty and `fatal_gameplay_frame` come from the first dead frame only.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DeathInfo {
    pub cause: DeathCause,
    /// 1-based gameplay frame (startup excluded) in which the player died.
    pub fatal_gameplay_frame: u32,
    pub observed_lethal_contacts: [u16; 6],
}

#[derive(Clone, Debug, PartialEq)]
pub struct EpisodeInfo {
    pub seed: SeedMetadata,
    pub startup_frames: u32,
    pub gameplay_frames: u32,
    pub alive_frames: u32,
    pub score_raw_fixed: i32,
    pub score: f64,
    pub score_delta_sum_raw_fixed: i64,
    /// Computed from exact cumulative score/counts, not summed f32 rewards.
    pub objective_return: f64,
    pub terminated: bool,
    pub truncated: bool,
    pub bootstrap: bool,
    /// `Some` only for terminated episodes; live and cap-truncated are `None`.
    pub death: Option<DeathInfo>,
    pub diagnostics: crate::Diagnostics,
}

#[derive(Clone, Debug, PartialEq)]
pub struct StepBatch {
    pub observations: ObservationBatch,
    pub rewards: Vec<f32>,
    pub score_delta_raw_fixed: Vec<i64>,
    pub alive_raw_frames: Vec<u32>,
    pub elapsed_raw_frames: Vec<u32>,
    pub terminated: Vec<bool>,
    pub truncated: Vec<bool>,
    pub info: Vec<EpisodeInfo>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ResetBatch {
    pub observations: ObservationBatch,
    pub info: Vec<EpisodeInfo>,
}

struct Slot {
    game: NativeGame,
    seed: SeedMetadata,
    history: History,
    observation: Option<Observation>,
    pixel_stack: Option<Vec<u8>>,
    startup_frames: u32,
    gameplay_frames: u32,
    alive_frames: u32,
    score_delta_sum_raw_fixed: i64,
    terminated: bool,
    truncated: bool,
    death: Option<DeathInfo>,
    #[cfg(test)]
    raw_observer: Option<RawObserver>,
    #[cfg(test)]
    injected_error: Option<EnvError>,
}

#[derive(Clone, Copy)]
struct StepCounts {
    elapsed: u32,
    alive: u32,
    score: i64,
}

impl Slot {
    fn unstarted(config: &EnvConfig, seed: SeedMetadata) -> Self {
        let mut native = NativeConfig::new(seed.actual_seed);
        native.difficulty = config.difficulty;
        native.patterns_enabled = config.patterns_enabled;
        native.powerups_enabled = config.powerups_enabled;
        Self {
            game: NativeGame::new(native),
            seed,
            history: History::default(),
            observation: None,
            pixel_stack: config.render_pixels.then(|| vec![0; 4 * FRAMEBUFFER_SIZE]),
            startup_frames: 0,
            gameplay_frames: 0,
            alive_frames: 0,
            score_delta_sum_raw_fixed: 0,
            terminated: false,
            truncated: false,
            death: None,
            #[cfg(test)]
            raw_observer: None,
            #[cfg(test)]
            injected_error: None,
        }
    }

    fn start(&mut self, config: &EnvConfig) -> Result<(), EnvError> {
        for frame in 0..STARTUP_LIMIT {
            let result =
                self.game
                    .advance_frame_headless(if frame == 0 { BUTTON_X_MASK } else { 0 })?;
            self.startup_frames += 1;
            if result.mode == Mode::Game && !result.dead {
                if self.startup_frames != PINNED_STARTUP_FRAMES {
                    return Err(EnvError::Contract(
                        "startup frame count differs from accepted pin (13)",
                    ));
                }
                self.history
                    .observe_raw(self.game.privileged_view(), self.game.enemy_serials())?;
                self.update_observation(config, true)?;
                return Ok(());
            }
            if result.dead {
                return Err(EnvError::Contract("death during startup"));
            }
        }
        Err(EnvError::Contract(
            "bounded startup did not reach alive Game",
        ))
    }

    fn update_observation(&mut self, config: &EnvConfig, initial: bool) -> Result<(), EnvError> {
        let lifecycle = self.game.lifecycle();
        let warnings = self
            .game
            .drawn_warning_lines()
            .filter(|_| lifecycle.mode == Mode::Game && !lifecycle.dead);
        let mut observation = self.history.observation(
            self.game.privileged_view(),
            warnings,
            config.auxiliary_targets,
        )?;
        if let Some(stack) = &mut self.pixel_stack {
            if !lifecycle.dead {
                let mut frame = [0; FRAMEBUFFER_SIZE];
                self.game.render_into(&mut frame);
                if frame.iter().any(|v| *v > 15) {
                    return Err(EnvError::Contract("palette index outside 0..15"));
                }
                if initial {
                    for slot in stack.chunks_exact_mut(FRAMEBUFFER_SIZE) {
                        slot.copy_from_slice(&frame);
                    }
                } else {
                    stack.copy_within(FRAMEBUFFER_SIZE.., 0);
                    stack[3 * FRAMEBUFFER_SIZE..].copy_from_slice(&frame);
                }
                observation.pixel_valid = true;
            }
            observation.pixels = Some(stack.clone());
            observation.pixel_aux_pair_valid =
                observation.pixel_valid && observation.auxiliary.is_some();
        }
        self.observation = Some(observation);
        Ok(())
    }

    fn advance(&mut self, action: Action, config: &EnvConfig) -> Result<StepCounts, EnvError> {
        let mut counts = StepCounts {
            elapsed: 0,
            alive: 0,
            score: 0,
        };
        for _ in 0..config.action_repeat {
            let before = self.game.score().raw();
            let result = self.game.advance_frame_headless(action.mask())?;
            self.gameplay_frames += 1;
            counts.elapsed += 1;
            // Compare native fixed values exactly. Float reward tolerances do
            // not apply to this accounting identity, including death pickups.
            let delta = i64::from(result.score.raw()) - i64::from(before);
            if delta < 0 || delta != i64::from(result.score_delta.raw()) {
                return Err(EnvError::Contract(
                    "negative or inconsistent fixed score delta",
                ));
            }
            counts.score += delta;
            self.score_delta_sum_raw_fixed += delta;
            if !result.dead {
                self.alive_frames += 1;
                counts.alive += 1;
            }
            self.terminated = result.dead;
            if result.dead && self.death.is_none() {
                self.death = Some(self.death_info());
            }
            self.truncated = !result.dead && self.gameplay_frames >= config.raw_frame_cap;
            self.history
                .observe_raw(self.game.privileged_view(), self.game.enemy_serials())?;
            #[cfg(test)]
            if let Some(observer) = &mut self.raw_observer {
                observer(&self.game);
            }
            #[cfg(test)]
            if let Some(error) = self.injected_error.take() {
                return Err(error);
            }
            if result.mode != Mode::Game {
                return Err(EnvError::Contract("gameplay left Mode::Game"));
            }
            if self.terminated || self.truncated {
                break;
            }
        }
        self.update_observation(config, false)?;
        Ok(counts)
    }

    /// Captured at the first dead frame; the slot ends there, so the record
    /// is never overwritten. A dead game without a recorded cause is `Unknown`.
    fn death_info(&self) -> DeathInfo {
        let diagnostic = self.game.death_diagnostic();
        DeathInfo {
            cause: diagnostic.cause().unwrap_or(DeathCause::Unknown),
            fatal_gameplay_frame: self.gameplay_frames,
            observed_lethal_contacts: diagnostic.observed_contacts(),
        }
    }

    fn info(&self) -> EpisodeInfo {
        let score_raw_fixed = self.game.score().raw();
        let score = f64::from(score_raw_fixed) / 65536.0;
        let cumulative = self.history.cumulative_diagnostics();
        let mut diagnostics = self
            .observation
            .as_ref()
            .map_or(crate::Diagnostics::default(), |o| o.diagnostics);
        diagnostics.raw_history_samples = cumulative.raw_history_samples;
        diagnostics.unknown_enemy_samples = cumulative.unknown_enemy_samples;
        diagnostics.unknown_rectangle_samples = cumulative.unknown_rectangle_samples;
        diagnostics.unknown_phase_samples = cumulative.unknown_phase_samples;
        diagnostics.dropped_enemy_total = cumulative.dropped_enemy_total;
        EpisodeInfo {
            seed: self.seed,
            startup_frames: self.startup_frames,
            gameplay_frames: self.gameplay_frames,
            alive_frames: self.alive_frames,
            score_raw_fixed,
            score,
            score_delta_sum_raw_fixed: self.score_delta_sum_raw_fixed,
            objective_return: self.score_delta_sum_raw_fixed as f64 / 65536.0
                + f64::from(self.alive_frames) / 100.0
                - if self.terminated { 5.0 } else { 0.0 },
            terminated: self.terminated,
            truncated: self.truncated,
            bootstrap: !self.terminated,
            death: self.death,
            diagnostics,
        }
    }
}

/// Persistent pool and stable simulation slots. Parallel failures retain all
/// partially advanced games and poison the whole batch; no rollback is claimed.
/// The initial construction performs the first fresh reset. `observations()`
/// returns its owned initial arrays without consuming another episode seed.
pub struct VecDodgeEnv {
    config: EnvConfig,
    pool: rayon::ThreadPool,
    excluded_seed_ranges: Vec<(u32, u32)>,
    slots: Vec<Slot>,
    poisoned: bool,
    last_failures: Vec<(usize, String)>,
}

impl VecDodgeEnv {
    pub fn new(config: EnvConfig) -> Result<Self, EnvError> {
        config.validate()?;
        let excluded_seed_ranges = normalize_seed_exclusions(&config.excluded_seed_ranges)?;
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(config.num_threads)
            .build()
            .map_err(|e| EnvError::Native(e.to_string()))?;
        let seeds = (0..config.batch_size)
            .map(|i| {
                let episode = config.initial_episode_indices.as_ref().map_or(0, |v| v[i]);
                seed_for(&config.seed_mode, i, episode, &excluded_seed_ranges)
            })
            .collect::<Result<Vec<_>, _>>()?;
        let mut slots = Vec::with_capacity(config.batch_size);
        for seed in seeds {
            let mut slot = Slot::unstarted(&config, seed);
            slot.start(&config)?;
            slots.push(slot);
        }
        Ok(Self {
            config,
            pool,
            excluded_seed_ranges,
            slots,
            poisoned: false,
            last_failures: Vec::new(),
        })
    }

    pub fn batch_info(&self) -> BatchInfo {
        BatchInfo {
            config: self.config.clone(),
            seed_stream_version: SEED_STREAM_VERSION,
            motion_version: MOTION_VERSION,
            seed_exclusion_version: SEED_EXCLUSION_VERSION,
            effective_excluded_seed_ranges: self.excluded_seed_ranges.clone(),
            initial_episode_indices: self
                .config
                .initial_episode_indices
                .clone()
                .unwrap_or_else(|| vec![0; self.config.batch_size]),
            theme_background_shadow: [12, 1],
            initial_highscores_raw_fixed: [0; 12],
        }
    }
    pub fn is_poisoned(&self) -> bool {
        self.poisoned
    }
    pub fn last_failures(&self) -> &[(usize, String)] {
        &self.last_failures
    }
    /// Available after failure for partial-state diagnostics, never neural input.
    pub fn episode_info(&self) -> Vec<EpisodeInfo> {
        self.slots.iter().map(Slot::info).collect()
    }

    pub fn observations(&self) -> Result<ObservationBatch, EnvError> {
        if self.poisoned {
            return Err(EnvError::Poisoned);
        }
        self.observation_subset((0..self.slots.len()).collect())
    }

    fn observation_subset(&self, indices: Vec<usize>) -> Result<ObservationBatch, EnvError> {
        let rows = indices
            .iter()
            .map(|i| {
                self.slots[*i]
                    .observation
                    .as_ref()
                    .ok_or(EnvError::Contract("slot has no completed observation"))
            })
            .collect::<Result<Vec<_>, _>>()?;
        Ok(ObservationBatch::collect(
            indices,
            rows.into_iter(),
            self.config.render_pixels,
            self.config.auxiliary_targets,
        ))
    }

    pub fn step(&mut self, action_ids: &[i64]) -> Result<StepBatch, EnvError> {
        if self.poisoned {
            return Err(EnvError::Poisoned);
        }
        if action_ids.len() != self.slots.len() {
            return Err(EnvError::ActionShape {
                expected: self.slots.len(),
                actual: action_ids.len(),
            });
        }
        // Complete validation and copy into owned Rust storage before any slot
        // can mutate. A later Python binding can release the GIL after this.
        let actions = action_ids
            .iter()
            .enumerate()
            .map(|(slot, &id)| {
                usize::try_from(id)
                    .ok()
                    .and_then(|i| Action::ALL.get(i))
                    .copied()
                    .ok_or(EnvError::ActionId { slot, id })
            })
            .collect::<Result<Vec<_>, _>>()?;
        for (index, slot) in self.slots.iter().enumerate() {
            if slot.terminated || slot.truncated {
                return Err(EnvError::SlotEnded(index));
            }
            if slot.game.lifecycle().mode != Mode::Game || slot.game.lifecycle().dead {
                return Err(EnvError::Contract("step requires alive Mode::Game"));
            }
        }
        let config = &self.config;
        let results = self.pool.install(|| {
            self.slots
                .par_chunks_mut(config.chunk_size)
                .enumerate()
                .map(|(chunk, slots)| {
                    slots
                        .iter_mut()
                        .enumerate()
                        .map(|(offset, slot)| {
                            let index = chunk * config.chunk_size + offset;
                            (index, slot.advance(actions[index], config))
                        })
                        .collect::<Vec<_>>()
                })
                .collect::<Vec<_>>()
        });
        let mut counts = Vec::with_capacity(self.slots.len());
        let mut failures = Vec::new();
        for (index, result) in results.into_iter().flatten() {
            match result {
                Ok(value) => counts.push(value),
                Err(error) => failures.push((index, error.to_string())),
            }
        }
        if !failures.is_empty() {
            return Err(self.poison(failures));
        }
        let info = self.episode_info();
        Ok(StepBatch {
            observations: self.observations()?,
            rewards: counts
                .iter()
                .zip(&info)
                .map(|(c, i)| {
                    (c.score as f64 / 65536.0 + f64::from(c.alive) / 100.0
                        - if i.terminated { 5.0 } else { 0.0 }) as f32
                })
                .collect(),
            score_delta_raw_fixed: counts.iter().map(|c| c.score).collect(),
            alive_raw_frames: counts.iter().map(|c| c.alive).collect(),
            elapsed_raw_frames: counts.iter().map(|c| c.elapsed).collect(),
            terminated: info.iter().map(|i| i.terminated).collect(),
            truncated: info.iter().map(|i| i.truncated).collect(),
            info,
        })
    }

    fn poison(&mut self, failures: Vec<(usize, String)>) -> EnvError {
        self.poisoned = true;
        self.last_failures = failures.clone();
        EnvError::BatchFailure(failures)
    }

    /// Only `reset_all` can recover a poisoned batch. Every requested seed is
    /// validated first. Once mutation starts, failed fresh episodes are consumed
    /// and retained; a later explicit reset advances their episode counters.
    pub fn reset_done(&mut self, indices: &[usize]) -> Result<ResetBatch, EnvError> {
        if self.poisoned {
            return Err(EnvError::Poisoned);
        }
        let mut unique = std::collections::BTreeSet::new();
        for &index in indices {
            let slot = self.slots.get(index).ok_or(EnvError::SlotIndex(index))?;
            if !unique.insert(index) {
                return Err(EnvError::DuplicateReset(index));
            }
            if !slot.terminated && !slot.truncated {
                return Err(EnvError::SlotNotEnded(index));
            }
        }
        self.reset_indices(indices, false)
    }

    pub fn reset_all(&mut self) -> Result<ResetBatch, EnvError> {
        let indices: Vec<_> = (0..self.slots.len()).collect();
        self.reset_indices(&indices, true)
    }

    fn reset_indices(&mut self, indices: &[usize], all: bool) -> Result<ResetBatch, EnvError> {
        let seeds = indices
            .iter()
            .map(|&index| {
                let episode = self.slots[index]
                    .seed
                    .episode
                    .checked_add(1)
                    .ok_or(EnvError::CounterExhausted)?;
                seed_for(
                    &self.config.seed_mode,
                    index,
                    episode,
                    &self.excluded_seed_ranges,
                )
            })
            .collect::<Result<Vec<_>, _>>()?;
        for (&index, seed) in indices.iter().zip(seeds) {
            self.slots[index] = Slot::unstarted(&self.config, seed);
            if let Err(error) = self.slots[index].start(&self.config) {
                return Err(self.poison(vec![(index, error.to_string())]));
            }
        }
        if all {
            self.poisoned = false;
            self.last_failures.clear();
        }
        Ok(ResetBatch {
            observations: self.observation_subset(indices.to_vec())?,
            info: indices.iter().map(|i| self.slots[*i].info()).collect(),
        })
    }
}

#[cfg(test)]
impl VecDodgeEnv {
    pub(crate) fn test_game(&self, slot: usize) -> &NativeGame {
        &self.slots[slot].game
    }
    pub(crate) fn test_restore(
        &mut self,
        slot: usize,
        snapshot: &dodge_core::Snapshot,
    ) -> Result<(), EnvError> {
        let target = &mut self.slots[slot];
        target.game = NativeGame::restore(snapshot)?;
        target.history = History::default();
        target
            .history
            .observe_raw(target.game.privileged_view(), target.game.enemy_serials())?;
        target.terminated = target.game.lifecycle().dead;
        target.truncated = false;
        target.death = target.game.lifecycle().dead.then(|| target.death_info());
        target.update_observation(&self.config, true)
    }
    pub(crate) fn test_observer(
        &mut self,
        slot: usize,
        observer: Box<dyn FnMut(&NativeGame) + Send>,
    ) {
        self.slots[slot].raw_observer = Some(observer);
    }
    pub(crate) fn test_inject_error(&mut self, slot: usize, error: EnvError) {
        self.slots[slot].injected_error = Some(error);
    }
}
