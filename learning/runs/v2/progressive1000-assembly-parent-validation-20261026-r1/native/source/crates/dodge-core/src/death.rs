//! Ephemeral death-cause telemetry.
//!
//! The record is observation-only diagnostics. It is not part of `FullState`,
//! snapshot bytes, RNG, reward, or any policy feature, and it never influences
//! collision, removal, or lifecycle behavior.

/// Source collision that produced the first alive-to-dead transition.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DeathCause {
    /// Contact with an enemy of personality 0.
    NormalEnemy,
    /// Contact with an enemy of personality 1 (body, before it explodes).
    KamikazeEnemy,
    /// Contact with an explosion enemy of personality -1.
    KamikazeExplosion,
    /// Overlap with a pattern rectangle of a non-moving type while fully expanded.
    StaticPatternRect,
    /// Overlap with a pattern rectangle of moving type (lethal throughout).
    MovingPatternRect,
    /// Dead state whose collision was not observed: restored from a snapshot,
    /// or an enemy personality outside the known lethal set.
    Unknown,
}

impl DeathCause {
    pub const ALL: [Self; 6] = [
        Self::NormalEnemy,
        Self::KamikazeEnemy,
        Self::KamikazeExplosion,
        Self::StaticPatternRect,
        Self::MovingPatternRect,
        Self::Unknown,
    ];

    pub const fn index(self) -> usize {
        match self {
            Self::NormalEnemy => 0,
            Self::KamikazeEnemy => 1,
            Self::KamikazeExplosion => 2,
            Self::StaticPatternRect => 3,
            Self::MovingPatternRect => 4,
            Self::Unknown => 5,
        }
    }

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::NormalEnemy => "normal_enemy",
            Self::KamikazeEnemy => "kamikaze_enemy",
            Self::KamikazeExplosion => "kamikaze_explosion",
            Self::StaticPatternRect => "static_pattern_rect",
            Self::MovingPatternRect => "moving_pattern_rect",
            Self::Unknown => "unknown",
        }
    }

    pub(crate) const fn for_enemy_personality(personality: i8) -> Self {
        match personality {
            0 => Self::NormalEnemy,
            1 => Self::KamikazeEnemy,
            -1 => Self::KamikazeExplosion,
            _ => Self::Unknown,
        }
    }
}

/// First lethal cause plus counts of every lethal contact the legacy loop
/// processed in the same death frame.
///
/// `first` is the first contact in source order (enemies in list order, then
/// the active pattern's rectangles); it is the only claimed cause. The
/// source `die()` repeats for later same-frame lethal contacts, so
/// `observed_contacts` counts those calls per kind, including the first.
/// Later contacts are observations of what the legacy loop also touched, not
/// alternate proven causes.
///
/// Equality is deliberately constant so this diagnostic never changes
/// `NativeGame` equality (it is absent from snapshots, so a restored game
/// could not otherwise equal the original).
#[derive(Clone, Copy, Debug, Default)]
pub struct DeathDiagnostic {
    first: Option<DeathCause>,
    observed_contacts: [u16; 6],
}

impl PartialEq for DeathDiagnostic {
    fn eq(&self, _other: &Self) -> bool {
        true
    }
}

impl Eq for DeathDiagnostic {}

impl DeathDiagnostic {
    /// `None` while alive; the first lethal cause once dead.
    pub const fn cause(&self) -> Option<DeathCause> {
        self.first
    }

    /// Lethal contacts processed in the death frame, indexed by
    /// `DeathCause::index`. The first cause is included in its own count.
    pub const fn observed_contacts(&self) -> [u16; 6] {
        self.observed_contacts
    }

    pub(crate) fn record(&mut self, cause: DeathCause) {
        self.first.get_or_insert(cause);
        if let Some(count) = self.observed_contacts.get_mut(cause.index()) {
            *count = count.saturating_add(1);
        }
    }

    /// Snapshots carry no cause: a dead restore is unknown, an alive one empty.
    pub(crate) fn restored(dead: bool) -> Self {
        let mut value = Self::default();
        if dead {
            value.first = Some(DeathCause::Unknown);
        }
        value
    }
}
