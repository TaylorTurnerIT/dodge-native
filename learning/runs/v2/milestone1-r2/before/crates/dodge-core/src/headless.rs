use crate::{EnemyState, Mode, PatternRect, PicoFixed, PlayerState};

/// One completed simulation frame without a snapshot or framebuffer.
///
/// `reward` preserves the legacy fixed-point survival reward: one for an alive
/// frame whose previous mode was `Game`, zero otherwise. It is not the v2 RL
/// objective. A wrapper must accumulate score deltas and apply its own alive
/// bonus and one-time death penalty across the frames it actually executes.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct HeadlessResult {
    pub frame: u32,
    pub mode: Mode,
    pub input_mask: u8,
    pub previous_input_mask: u8,
    pub game_ready: bool,
    pub started: bool,
    pub dead: bool,
    pub done: bool,
    pub reward: PicoFixed,
    /// Actual score change, including a negative reset delta on legacy retry.
    pub score_delta: PicoFixed,
    pub score: PicoFixed,
}

/// Borrowed active rectangle geometry and current charging state (`rect.sh`).
///
/// This raw Rust view is not a policy tensor contract. `PatternRect` also holds
/// engine bookkeeping and future targets; consumers must use an explicit
/// feature allowlist and must not encode those hidden fields. No pattern timer
/// or inactive pattern catalog is provided here.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ActivePatternView<'a> {
    pub pattern_type: u8,
    pub rects: &'a [PatternRect],
}

/// Borrowed current state at the post-method boundary used by `render_into`.
///
/// These references avoid snapshot clones. The raw entity/rectangle types are
/// engine data, not permission to serialize every field into an observation.
/// Policy featurization must explicitly select its 14 global and 16 entity
/// scalars, excluding schedules, future targets, and other hidden bookkeeping.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PrivilegedView<'a> {
    pub player: &'a PlayerState,
    pub enemies: &'a [EnemyState],
    pub freeze_rate: PicoFixed,
    pub speed: PicoFixed,
    pub enemy_est: PicoFixed,
    pub score: PicoFixed,
    pub active_pattern: Option<ActivePatternView<'a>>,
    pub difficulty: u8,
    pub patterns_enabled: bool,
    pub powerups_enabled: bool,
}
