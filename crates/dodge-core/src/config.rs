use crate::PicoFixed;

/// Opt-in training controls layered over the cartridge's rules. The default,
/// `TrainingOptions::CARTRIDGE`, reproduces the cartridge exactly.
///
/// Snapshots do not carry these options: `NativeGame::restore` always rebuilds
/// a cartridge game.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct TrainingOptions {
    /// Allow personality-0 enemies, including the anti-camping wave.
    pub normal_enemies: bool,
    /// Allow kamikaze enemies and therefore their explosions.
    pub kamikaze_enemies: bool,
    /// Multiplier on both the enemy spawn timer and the between-pattern timer.
    pub spawn_rate: PicoFixed,
    /// Lethal collisions absorbed per game. An absorbed enemy hit removes the
    /// enemy as usual; an absorbed pattern hit restarts the active pattern
    /// from the state it started in.
    pub lives: u8,
}

impl TrainingOptions {
    pub const CARTRIDGE: Self = Self {
        normal_enemies: true,
        kamikaze_enemies: true,
        spawn_rate: PicoFixed::ONE,
        lives: 0,
    };
}

impl Default for TrainingOptions {
    fn default() -> Self {
        Self::CARTRIDGE
    }
}

/// Persistent settings and cartridge data supplied to a native game instance.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct NativeConfig {
    pub seed: u32,
    pub difficulty: u8,
    pub patterns_enabled: bool,
    pub powerups_enabled: bool,
    pub theme_background: u8,
    pub theme_shadow: u8,
    pub highscores: [PicoFixed; 12],
    pub training: TrainingOptions,
}

impl NativeConfig {
    pub const fn new(seed: u32) -> Self {
        Self {
            seed,
            difficulty: 2,
            patterns_enabled: true,
            powerups_enabled: true,
            theme_background: 12,
            theme_shadow: 1,
            highscores: [PicoFixed::ZERO; 12],
            training: TrainingOptions::CARTRIDGE,
        }
    }
}

impl Default for NativeConfig {
    fn default() -> Self {
        Self::new(42)
    }
}
