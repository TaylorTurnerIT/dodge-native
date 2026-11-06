//! Per-slot game counters as columns, so a trainer can compute its own reward
//! and episode bookkeeping without a dict per slot. Diagnostic only: none of
//! these values is part of an observation.
//!
//! The names, dtypes and meanings are those of `observe_velocity` in
//! TaylorTurnerIT/dodge-ai-3 velocity-flow (`VelocityLane` and `Telemetry`),
//! which LaunchSpark/DodgeAI reads today.

use dodge_core::{DeathCause, NativeGame};

/// `death_cause` codes, as LaunchSpark/DodgeAI numbers them.
pub const DEATH_NONE: u8 = 0;
pub const DEATH_NORMAL_ENEMY: u8 = 1;
pub const DEATH_KAMIKAZE_ENEMY: u8 = 2;
pub const DEATH_KAMIKAZE_EXPLOSION: u8 = 3;
pub const DEATH_STATIC_PATTERN_RECT: u8 = 4;
pub const DEATH_MOVING_PATTERN_RECT: u8 = 5;

/// DodgeAI's code for a cause of death. An unobserved cause is 0, as alive.
pub const fn death_cause_code(cause: Option<DeathCause>) -> u8 {
    match cause {
        None | Some(DeathCause::Unknown) => DEATH_NONE,
        Some(DeathCause::NormalEnemy) => DEATH_NORMAL_ENEMY,
        Some(DeathCause::KamikazeEnemy) => DEATH_KAMIKAZE_ENEMY,
        Some(DeathCause::KamikazeExplosion) => DEATH_KAMIKAZE_EXPLOSION,
        Some(DeathCause::StaticPatternRect) => DEATH_STATIC_PATTERN_RECT,
        Some(DeathCause::MovingPatternRect) => DEATH_MOVING_PATTERN_RECT,
    }
}

/// One slot's counters, read from its game.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct LaneCounters {
    pub score: f64,
    pub player_x: f64,
    pub player_y: f64,
    /// Enemies resolved through `is_dying`, which the cartridge scores at half.
    pub uncontrolled_kills: u32,
    pub survival_frames: u32,
    pub dead: bool,
    pub pattern_active: bool,
    /// Identifier of the active pattern, -1 for none.
    pub pattern_id: i16,
    /// See `death_cause_code`; 0 while alive.
    pub death_cause: u8,
    /// Identifier of the pattern active at the death, -1 for none.
    pub death_pattern: i16,
    pub fyou_triggers: u32,
    /// Lethal contacts absorbed by training lives.
    pub lives_spent: u32,
    /// Explode, freeze and shrink pickups collected.
    pub pickups: [u32; 3],
}

impl LaneCounters {
    pub fn read(game: &NativeGame) -> Self {
        let player = game.player();
        let telemetry = game.telemetry();
        Self {
            score: game.score().to_double(),
            player_x: player.x.to_double(),
            player_y: player.y.to_double(),
            uncontrolled_kills: game.uncontrolled_kills(),
            survival_frames: game.survival_frames(),
            dead: game.lifecycle().dead,
            pattern_active: game.active_pattern_index().is_some(),
            pattern_id: game.active_pattern_id(),
            death_cause: death_cause_code(game.death_diagnostic().cause()),
            death_pattern: telemetry.death_pattern,
            fyou_triggers: telemetry.fyou_triggers,
            lives_spent: telemetry.lives_spent,
            pickups: telemetry.pickups,
        }
    }
}

/// Counters for a batch of slots, one column per field, rows in `indices`
/// order. `pickups` is row-major B x 3.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct CounterBatch {
    pub indices: Vec<usize>,
    pub score: Vec<f64>,
    pub player_x: Vec<f64>,
    pub player_y: Vec<f64>,
    pub uncontrolled_kills: Vec<u32>,
    pub survival_frames: Vec<u32>,
    pub dead: Vec<bool>,
    pub pattern_active: Vec<bool>,
    pub pattern_id: Vec<i16>,
    pub death_cause: Vec<u8>,
    pub death_pattern: Vec<i16>,
    pub fyou_triggers: Vec<u32>,
    pub lives_spent: Vec<u32>,
    pub pickups: Vec<u32>,
}

impl CounterBatch {
    pub(crate) fn collect<'a>(
        indices: Vec<usize>,
        games: impl Iterator<Item = &'a NativeGame>,
    ) -> Self {
        let mut batch = Self {
            indices,
            ..Self::default()
        };
        for game in games {
            batch.push(LaneCounters::read(game));
        }
        batch
    }

    fn push(&mut self, row: LaneCounters) {
        self.score.push(row.score);
        self.player_x.push(row.player_x);
        self.player_y.push(row.player_y);
        self.uncontrolled_kills.push(row.uncontrolled_kills);
        self.survival_frames.push(row.survival_frames);
        self.dead.push(row.dead);
        self.pattern_active.push(row.pattern_active);
        self.pattern_id.push(row.pattern_id);
        self.death_cause.push(row.death_cause);
        self.death_pattern.push(row.death_pattern);
        self.fyou_triggers.push(row.fyou_triggers);
        self.lives_spent.push(row.lives_spent);
        self.pickups.extend_from_slice(&row.pickups);
    }

    pub fn batch_size(&self) -> usize {
        self.indices.len()
    }

    /// Row `row` as a struct, for tests and diagnostics.
    pub fn row(&self, row: usize) -> Option<LaneCounters> {
        let pickups = self.pickups.get(row * 3..row * 3 + 3)?;
        Some(LaneCounters {
            score: *self.score.get(row)?,
            player_x: *self.player_x.get(row)?,
            player_y: *self.player_y.get(row)?,
            uncontrolled_kills: *self.uncontrolled_kills.get(row)?,
            survival_frames: *self.survival_frames.get(row)?,
            dead: *self.dead.get(row)?,
            pattern_active: *self.pattern_active.get(row)?,
            pattern_id: *self.pattern_id.get(row)?,
            death_cause: *self.death_cause.get(row)?,
            death_pattern: *self.death_pattern.get(row)?,
            fyou_triggers: *self.fyou_triggers.get(row)?,
            lives_spent: *self.lives_spent.get(row)?,
            pickups: [*pickups.first()?, *pickups.get(1)?, *pickups.get(2)?],
        })
    }
}
