//! Ephemeral gameplay trace for death analysis.
//!
//! Like `DeathDiagnostic`, the trace is observation-only. It is disabled by
//! default, is not part of `FullState`, snapshot bytes, RNG, reward, or any
//! policy feature, and never influences collision, spawning, or lifecycle
//! behavior. It records when `update_fyou` fires, which enemies it spawned,
//! which patterns ran and when, and the situation at the first lethal contact.
//!
//! Frames are 1-based gameplay frames: the Nth call of the in-game update. The
//! 13 startup frames before `Mode::Game` are not counted, so a death frame
//! equals the environment's `fatal_gameplay_frame`.

use crate::{DeathCause, EnemySerial};

/// One `update_fyou` firing.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct FyouTrigger {
    pub frame: u32,
    /// Corner enemies spawned by this trigger (`spawns.len()` at the time).
    pub spawned: u8,
}

/// One pattern encounter, from selection to completion.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PatternSpan {
    pub id: u8,
    pub pattern_type: u8,
    pub start_frame: u32,
    /// `None` while the pattern was still active when the trace was read.
    pub end_frame: Option<u32>,
}

/// The enemy whose contact started the death.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct KillerEnemy {
    pub personality: i8,
    /// `None` when identity metadata was exhausted and attribution is unknown.
    pub fyou_spawned: Option<bool>,
    /// Frames between the enemy's birth and the fatal frame, when known.
    pub age_frames: Option<u32>,
}

/// Pattern active at the first lethal contact.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ActivePatternAtDeath {
    pub id: u8,
    pub pattern_type: u8,
    pub variants: Vec<u8>,
    pub start_frame: u32,
    pub frames_since_start: u32,
}

/// Situation at the first lethal contact in source order.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DeathContext {
    pub cause: DeathCause,
    pub frame: u32,
    pub killer: Option<KillerEnemy>,
    /// Enemies on the field excluding the killer, by personality:
    /// `[normal, kamikaze, explosion, powerup]`.
    pub enemies_alive: [u16; 4],
    /// Of the enemies counted in `enemies_alive`, those spawned by fyou.
    /// `None` when identity metadata was exhausted.
    pub fyou_enemies_alive: Option<u16>,
    pub player_x_raw: i32,
    pub player_y_raw: i32,
    pub player_vx_raw: i32,
    pub player_vy_raw: i32,
    pub player_size_raw: i32,
    /// Consecutive frames, including this one, the player had been in the
    /// central box evaluated by `update_fyou`, whether or not fyou was enabled.
    pub center_dwell_frames: u32,
    /// The game's own fyou timer and enable flag at death.
    pub fyou_timer: u32,
    pub fyou_enabled: bool,
    pub active_pattern: Option<ActivePatternAtDeath>,
    /// Frame the most recent pattern ended, if any.
    pub last_pattern_end_frame: Option<u32>,
    pub freeze_active: bool,
}

/// Recorder owned by `NativeGame`. Equality is deliberately constant so the
/// diagnostic never changes `NativeGame` equality (it is absent from snapshots).
#[derive(Clone, Debug, Default)]
pub struct RunTrace {
    enabled: bool,
    frame: u32,
    dwell: u32,
    triggers: Vec<FyouTrigger>,
    patterns: Vec<PatternSpan>,
    /// Ascending birth ordinals of fyou-spawned enemies.
    fyou_births: Vec<u64>,
    /// `birth_frames[i]` is the frame of birth ordinal `birth_base + i`.
    birth_base: u64,
    birth_frames: Vec<u32>,
    identity_lost: bool,
    death: Option<DeathContext>,
}

impl PartialEq for RunTrace {
    fn eq(&self, _other: &Self) -> bool {
        true
    }
}

impl Eq for RunTrace {}

impl RunTrace {
    /// Start a fresh recording. `next_birth` is the next enemy birth ordinal,
    /// or `None` when enemy identity metadata is already exhausted.
    pub(crate) fn begin(enabled: bool, next_birth: Option<u64>) -> Self {
        Self {
            enabled,
            birth_base: next_birth.unwrap_or(0),
            identity_lost: next_birth.is_none(),
            ..Self::default()
        }
    }

    pub const fn enabled(&self) -> bool {
        self.enabled
    }

    /// Gameplay frames elapsed since the recording began.
    pub const fn frame(&self) -> u32 {
        self.frame
    }

    pub fn fyou_triggers(&self) -> &[FyouTrigger] {
        &self.triggers
    }

    pub fn patterns(&self) -> &[PatternSpan] {
        &self.patterns
    }

    pub fn death(&self) -> Option<&DeathContext> {
        self.death.as_ref()
    }

    pub const fn center_dwell_frames(&self) -> u32 {
        self.dwell
    }

    pub(crate) fn begin_frame(&mut self, in_center: bool) {
        if !self.enabled {
            return;
        }
        self.frame = self.frame.saturating_add(1);
        self.dwell = if in_center {
            self.dwell.saturating_add(1)
        } else {
            0
        };
    }

    /// Record births visible at the end of a frame. `serials` is strictly
    /// increasing, so the last entry is the newest birth.
    pub(crate) fn end_frame(&mut self, serials: Option<&[EnemySerial]>) {
        if !self.enabled || self.identity_lost {
            return;
        }
        let Some(newest) = serials.and_then(<[EnemySerial]>::last).map(|s| s.birth()) else {
            if serials.is_none() {
                self.identity_lost = true;
            }
            return;
        };
        let recorded = self.birth_base + self.birth_frames.len() as u64;
        if newest >= recorded {
            let missing = usize::try_from(newest - recorded + 1).unwrap_or(0);
            self.birth_frames
                .extend(std::iter::repeat_n(self.frame, missing));
        }
    }

    pub(crate) fn record_fyou(&mut self, spawned: usize, new_serials: Option<&[EnemySerial]>) {
        if !self.enabled {
            return;
        }
        self.triggers.push(FyouTrigger {
            frame: self.frame,
            spawned: u8::try_from(spawned).unwrap_or(u8::MAX),
        });
        match new_serials {
            Some(serials) => self.fyou_births.extend(serials.iter().map(|s| s.birth())),
            None => self.identity_lost = true,
        }
    }

    pub(crate) fn pattern_start(&mut self, id: u8, pattern_type: u8) {
        if self.enabled {
            self.patterns.push(PatternSpan {
                id,
                pattern_type,
                start_frame: self.frame,
                end_frame: None,
            });
        }
    }

    pub(crate) fn pattern_end(&mut self) {
        if !self.enabled {
            return;
        }
        let frame = self.frame;
        if let Some(span) = self.patterns.last_mut().filter(|s| s.end_frame.is_none()) {
            span.end_frame = Some(frame);
        }
    }

    pub(crate) fn is_fyou_birth(&self, serial: EnemySerial) -> Option<bool> {
        (!self.identity_lost).then(|| self.fyou_births.binary_search(&serial.birth()).is_ok())
    }

    pub(crate) fn birth_frame(&self, serial: EnemySerial) -> Option<u32> {
        let index = serial.birth().checked_sub(self.birth_base)?;
        self.birth_frames
            .get(usize::try_from(index).ok()?)
            .copied()
            .filter(|_| !self.identity_lost)
    }

    pub(crate) fn needs_death_context(&self) -> bool {
        self.enabled && self.death.is_none()
    }

    pub(crate) fn set_death(&mut self, context: DeathContext) {
        self.death.get_or_insert(context);
    }

    pub(crate) fn last_pattern_end(&self) -> Option<u32> {
        self.patterns.iter().rev().find_map(|s| s.end_frame)
    }

    pub(crate) fn active_span(&self) -> Option<&PatternSpan> {
        self.patterns.last().filter(|s| s.end_frame.is_none())
    }
}
