//! Critic-only features: game state the actor never sees, packed into one
//! fixed-size vector per lane so a value head can read what the policy cannot.
//!
//! Layout, in `CRITIC_GROUPS` order:
//!     clock            12   run progress and where the difficulty curve is
//!     timers           10   countdowns to the next pattern and enemy, power-ups
//!     active_pattern   42   which pattern runs and how far along it is
//!     next_pattern     78   the pattern odds, and what the RNG would pick now
//!     next_enemy        9   the size class and personality the RNG would roll
//!     nearest_enemies 144   the 8 nearest enemies, 18 values each
//!
//! Every value is finite and in [-1, 1]. Nothing here advances the game.
//!
//! Ported from TaylorTurnerIT/dodge-ai-3 velocity-flow
//! `native/crates/dodge-batch/src/critic.rs`. The only changes are reading
//! the global speed, enemy estimate and freeze rate through
//! `privileged_view()`, the upstream core's accessor for them, and starting
//! and stepping test games through the headless frame API.

use std::sync::OnceLock;

use dodge_core::{NativeGame, PicoFixed};

use crate::velocity_flow::VELOCITY_SCALE;

/// Bump whenever any feature's meaning, order or count changes.
pub const CRITIC_FEATURE_VERSION: u32 = 1;
pub const CRITIC_FEATURE_COUNT: usize = 295;
/// Group name, start and stop (exclusive) into the feature vector.
pub const CRITIC_GROUPS: [(&str, usize, usize); 6] = [
    ("clock", 0, 12),
    ("timers", 12, 22),
    ("active_pattern", 22, 64),
    ("next_pattern", 64, 142),
    ("next_enemy", 142, 151),
    ("nearest_enemies", 151, CRITIC_FEATURE_COUNT),
];

const PATTERN_COUNT: usize = 39;
const NEAREST_ENEMIES: usize = 8;
const ENEMY_VALUES: usize = 18;

/// Run length the survival clock is scaled by (five minutes at 60 fps).
const SURVIVAL_SCALE: f64 = 18_000.0;
/// Frames between patterns, and the longest an active pattern is timed over.
const PATTERN_FRAMES: f64 = 600.0;
/// Largest enemy max size (`enemy_max_size_from_roll`).
const SIZE_SCALE: f64 = 6.0;
/// The player's rest size.
const PLAYER_SIZE: f64 = 4.0;
/// `freeze_timer` runs 0..=480 before the freeze ends.
const FREEZE_FRAMES: f64 = 480.0;
/// `size_timer` passes 600 before a shrunken player regrows.
const SIZE_FRAMES: f64 = 600.0;
/// `friendly_timer` fires its corner enemies once it passes 50.
const FRIENDLY_FRAMES: f64 = 50.0;
/// Pixel distance an enemy offset is scaled by (half the board).
const DISTANCE_SCALE: f64 = 64.0;
/// Life a timed enemy starts with.
const LIFE_START: f64 = 60.0;

/// The score that unlocks the last pattern: the largest `mins` in the catalogue.
fn score_scale(game: &NativeGame) -> f64 {
    static SCALE: OnceLock<f64> = OnceLock::new();
    *SCALE.get_or_init(|| {
        game.patterns()
            .iter()
            .map(|pattern| pattern.mins.to_double())
            .fold(1.0, f64::max)
    })
}

fn unit(value: f64) -> f32 {
    if value.is_finite() {
        value.clamp(-1.0, 1.0) as f32
    } else {
        0.0
    }
}

/// `value / scale`, clamped to [-1, 1]; 0 for a non-positive scale.
fn ratio(value: f64, scale: f64) -> f32 {
    if scale > 0.0 {
        unit(value / scale)
    } else {
        0.0
    }
}

fn flag(value: bool) -> f32 {
    f32::from(u8::from(value))
}

/// A write cursor over the feature vector, so each group reads in table order.
struct Writer<'a> {
    out: &'a mut [f32],
    at: usize,
}

impl Writer<'_> {
    fn push(&mut self, value: f32) {
        if let Some(slot) = self.out.get_mut(self.at) {
            *slot = value;
        }
        self.at += 1;
    }

    /// Leave `count` slots at zero.
    fn skip(&mut self, count: usize) {
        self.at += count;
    }

    fn one_hot(&mut self, width: usize, hot: Option<usize>) {
        for slot in 0..width {
            self.push(flag(hot == Some(slot)));
        }
    }
}

/// Write one game's critic features into `out`, which must hold
/// `CRITIC_FEATURE_COUNT` values.
pub fn encode_critic_features(game: &NativeGame, out: &mut [f32]) {
    debug_assert_eq!(out.len(), CRITIC_FEATURE_COUNT);
    out.fill(0.0);
    let mut w = Writer { out, at: 0 };
    clock(game, &mut w);
    timers(game, &mut w);
    active_pattern(game, &mut w);
    next_pattern(game, &mut w);
    next_enemy(game, &mut w);
    nearest_enemies(game, &mut w);
    debug_assert_eq!(w.at, CRITIC_FEATURE_COUNT);
}

fn clock(game: &NativeGame, w: &mut Writer) {
    let view = game.privileged_view();
    w.push(ratio(f64::from(game.survival_frames()), SURVIVAL_SCALE));
    w.push(ratio(game.score().to_double(), score_scale(game)));
    // Speed climbs to its target; the others fall to theirs, so those are
    // read as target over value. Either way 1 means fully ramped.
    let [speed_target, est_target, static_target, moving_target] = game.difficulty_targets();
    w.push(ratio(view.speed.to_double(), speed_target.to_double()));
    w.push(ratio(est_target.to_double(), view.enemy_est.to_double()));
    w.push(ratio(
        static_target.to_double(),
        game.bounce_cap_static().to_double(),
    ));
    w.push(ratio(
        moving_target.to_double(),
        game.bounce_cap_moving().to_double(),
    ));
    w.push(ratio(game.enemy_max_size().to_double(), SIZE_SCALE));
    let stats = game.enemy_stats().map(|weight| weight.to_double().max(0.0));
    let total: f64 = stats.iter().sum();
    for weight in stats {
        w.push(ratio(weight, total));
    }
}

fn timers(game: &NativeGame, w: &mut Writer) {
    let countdown = ratio(
        game.pattern_countdown_frames().unwrap_or(0.0),
        PATTERN_FRAMES,
    );
    w.push(countdown.max(0.0));
    w.push(flag(game.active_pattern_index().is_some()));
    let threshold = game.spawn_threshold().to_double();
    let spawn = if threshold > 0.0 {
        1.0 - game.enemy_timer().to_double() / threshold
    } else {
        0.0
    };
    w.push(unit(spawn).max(0.0));
    w.push(flag(game.freeze_active()));
    w.push(ratio(f64::from(game.freeze_timer()), FREEZE_FRAMES).max(0.0));
    w.push(ratio(game.size_timer().to_double(), SIZE_FRAMES).max(0.0));
    w.push(unit(game.privileged_view().freeze_rate.to_double()).max(0.0));
    w.push(ratio(game.player().size.to_double(), PLAYER_SIZE));
    w.push(ratio(f64::from(game.friendly_timer()), FRIENDLY_FRAMES));
    w.push(flag(game.friendly_enabled()));
}

fn active_pattern(game: &NativeGame, w: &mut Writer) {
    let active = game
        .active_pattern_index()
        .and_then(|index| game.patterns().get(index).map(|pattern| (index, pattern)));
    w.one_hot(PATTERN_COUNT, active.map(|(index, _)| index));
    let Some((_, pattern)) = active else {
        w.skip(3);
        return;
    };
    let rects = pattern.rects.len() as f64;
    let finished = pattern.rects.iter().filter(|rect| rect.finished).count();
    let lethal = pattern
        .rects
        .iter()
        .filter(|rect| rect.sh == PicoFixed::from_int(2) && rect.shown && !rect.finished)
        .count();
    w.push(ratio(finished as f64, rects));
    w.push(ratio(lethal as f64, rects));
    w.push(ratio(pattern.timer.to_double(), PATTERN_FRAMES).max(0.0));
}

fn next_pattern(game: &NativeGame, w: &mut Writer) {
    let weighted = game.pattern_weights();
    let mut counts = [0_usize; PATTERN_COUNT];
    for index in &weighted {
        if let Some(count) = counts.get_mut(*index) {
            *count += 1;
        }
    }
    for count in counts {
        w.push(ratio(count as f64, weighted.len() as f64));
    }
    let pick = if game.active_pattern_index().is_some() {
        None
    } else {
        game.preview_pattern_pick()
    };
    w.one_hot(PATTERN_COUNT, pick);
}

fn next_enemy(game: &NativeGame, w: &mut Writer) {
    let (max_size, personality) = game.preview_enemy_roll();
    let size = max_size.to_double().round() as i64;
    w.one_hot(4, usize::try_from(size - 3).ok());
    w.one_hot(5, usize::try_from(personality).ok());
}

fn nearest_enemies(game: &NativeGame, w: &mut Writer) {
    let player = game.player();
    let (px, py) = (player.x.to_double(), player.y.to_double());
    let enemies = game.enemies();
    let mut ranked: Vec<(f64, usize)> = enemies
        .iter()
        .enumerate()
        .map(|(index, enemy)| {
            let dx = enemy.x.to_double() - px;
            let dy = enemy.y.to_double() - py;
            (dx * dx + dy * dy, index)
        })
        .collect();
    ranked.sort_by(|a, b| a.0.total_cmp(&b.0).then(a.1.cmp(&b.1)));
    // Enemies move by vx * spd * frz * e.spd, so velocities are real pixels.
    let view = game.privileged_view();
    let step = view.speed.to_double() * view.freeze_rate.to_double();
    let scale = f64::from(VELOCITY_SCALE);
    for slot in 0..NEAREST_ENEMIES {
        let Some(enemy) = ranked.get(slot).and_then(|(_, index)| enemies.get(*index)) else {
            w.skip(ENEMY_VALUES);
            continue;
        };
        let own = step * enemy.speed.to_double();
        w.push(1.0);
        w.push(ratio(enemy.x.to_double() - px, DISTANCE_SCALE));
        w.push(ratio(enemy.y.to_double() - py, DISTANCE_SCALE));
        w.push(ratio(enemy.vx.to_double() * own, scale));
        w.push(ratio(enemy.vy.to_double() * own, scale));
        w.push(ratio(enemy.size.to_double(), SIZE_SCALE));
        w.push(ratio(enemy.max_size.to_double(), SIZE_SCALE));
        w.push(flag(enemy.isizing));
        w.push(flag(enemy.is_dying));
        w.push(flag(enemy.inside));
        w.push(flag(enemy.life.is_some()));
        w.push(
            enemy
                .life
                .map_or(0.0, |life| ratio(life.to_double(), LIFE_START).max(0.0)),
        );
        let hot = usize::try_from(i32::from(enemy.personality) + 1).ok();
        w.one_hot(6, hot);
    }
}

#[cfg(test)]
#[allow(clippy::indexing_slicing, clippy::expect_used)]
mod tests {
    use super::*;
    use dodge_core::{Action, BUTTON_X_MASK, NativeConfig, TrainingOptions};

    /// Started as the environment starts a game: X tapped for one frame.
    fn started(config: NativeConfig) -> NativeGame {
        let mut game = NativeGame::new(config);
        for frame in 0..13 {
            let mask = if frame == 0 { BUTTON_X_MASK } else { 0 };
            assert!(game.advance_frame_headless(mask).is_ok());
        }
        game
    }

    fn encode(game: &NativeGame) -> Vec<f32> {
        let mut out = vec![9.0; CRITIC_FEATURE_COUNT];
        encode_critic_features(game, &mut out);
        out
    }

    fn slice<'a>(values: &'a [f32], name: &str) -> &'a [f32] {
        let group = CRITIC_GROUPS
            .iter()
            .find(|group| group.0 == name)
            .expect("known group");
        &values[group.1..group.2]
    }

    // The pattern countdown opens the timers group; pattern_active follows.
    const COUNTDOWN: usize = CRITIC_GROUPS[1].1;
    const PATTERN_ACTIVE: usize = COUNTDOWN + 1;

    #[test]
    fn the_layout_has_a_version() {
        const { assert!(CRITIC_FEATURE_VERSION >= 1) };
    }

    #[test]
    fn groups_tile_the_vector() {
        assert_eq!(CRITIC_GROUPS[0].1, 0);
        for pair in CRITIC_GROUPS.windows(2) {
            assert_eq!(pair[0].2, pair[1].1);
        }
        assert_eq!(CRITIC_GROUPS[5].2, CRITIC_FEATURE_COUNT);
    }

    #[test]
    fn encoding_is_a_pure_read() {
        let mut game = started(NativeConfig::new(7));
        for _ in 0..500 {
            assert!(game.advance_frame_headless(0).is_ok());
        }
        let before = game.clone();
        let _ = encode(&game);
        assert_eq!(game, before);
    }

    #[test]
    fn every_feature_stays_in_range() {
        let off = TrainingOptions {
            normal_enemies: false,
            kamikaze_enemies: false,
            ..TrainingOptions::CARTRIDGE
        };
        let configs = [
            NativeConfig {
                difficulty: 3,
                ..NativeConfig::new(11)
            },
            NativeConfig {
                patterns_enabled: false,
                ..NativeConfig::new(12)
            },
            NativeConfig {
                powerups_enabled: false,
                ..NativeConfig::new(13)
            },
            NativeConfig {
                training: off,
                ..NativeConfig::new(14)
            },
        ];
        for config in configs {
            let mut game = started(config);
            let mut state = u64::from(config.seed) | 1;
            for frame in 0..2000 {
                state = state
                    .wrapping_mul(6_364_136_223_846_793_005)
                    .wrapping_add(1_442_695_040_888_963_407);
                let action = Action::ALL[(state >> 33) as usize % Action::ALL.len()];
                let done = game
                    .advance_frame_headless(action.mask())
                    .map(|result| result.done)
                    .unwrap_or(true);
                if done {
                    game = started(config);
                }
                for (slot, value) in encode(&game).iter().enumerate() {
                    assert!(
                        value.is_finite() && (-1.0..=1.0).contains(value),
                        "feature {slot} = {value} at frame {frame}, seed {}",
                        config.seed
                    );
                }
            }
        }
    }

    #[test]
    fn pattern_countdown_ticks_once_per_frame() {
        let mut game = started(NativeConfig::new(21));
        let mut last = encode(&game)[COUNTDOWN];
        assert!(last > 0.0);
        for _ in 0..50 {
            assert!(game.advance_frame_headless(0).is_ok());
            let now = encode(&game)[COUNTDOWN];
            assert!(((last - now) - 1.0 / 600.0).abs() < 1e-6, "{last} -> {now}");
            last = now;
        }
    }

    #[test]
    fn pattern_countdown_scales_with_spawn_rate() {
        let at = |percent: u8| {
            let mut config = NativeConfig::new(22);
            config.training.spawn_rate = PicoFixed::from_f32(f32::from(percent) / 100.0);
            encode(&started(config))[COUNTDOWN]
        };
        let full = at(100);
        let half = at(50);
        assert!(((full * 2.0).min(1.0) - half).abs() < 1e-6, "{full} {half}");
    }

    #[test]
    fn one_hots_are_one_hot() {
        let config = NativeConfig::new(23);
        let mut game = started(config);
        let mut state = 99_u64;
        let mut saw_pattern = false;
        let mut saw_enemy = false;
        for _ in 0..4000 {
            state = state
                .wrapping_mul(6_364_136_223_846_793_005)
                .wrapping_add(1_442_695_040_888_963_407);
            let action = Action::ALL[(state >> 33) as usize % Action::ALL.len()];
            if game
                .advance_frame_headless(action.mask())
                .map_or(true, |r| r.done)
            {
                game = started(config);
            }
            let values = encode(&game);
            let active = slice(&values, "active_pattern");
            let hot: f32 = active[..PATTERN_COUNT].iter().sum();
            assert_eq!(hot, values[PATTERN_ACTIVE]);
            saw_pattern |= hot == 1.0;
            let next = slice(&values, "next_enemy");
            assert_eq!(next[..4].iter().sum::<f32>(), 1.0);
            assert_eq!(next[4..].iter().sum::<f32>(), 1.0);
            for enemy in slice(&values, "nearest_enemies").chunks(ENEMY_VALUES) {
                if enemy[0] == 1.0 {
                    saw_enemy = true;
                    assert_eq!(enemy[12..].iter().sum::<f32>(), 1.0);
                }
            }
        }
        assert!(saw_pattern && saw_enemy);
    }

    #[test]
    fn nearest_enemies_are_sorted() {
        let mut game = started(NativeConfig::new(24));
        let mut checked = 0;
        for _ in 0..1500 {
            if game.advance_frame_headless(0).map_or(true, |r| r.done) {
                break;
            }
            let values = encode(&game);
            // dx and dy are clamped, so compare only unclamped slots.
            let distances: Vec<f32> = slice(&values, "nearest_enemies")
                .chunks(ENEMY_VALUES)
                .filter(|e| e[0] == 1.0 && e[1].abs() < 1.0 && e[2].abs() < 1.0)
                .map(|e| e[1] * e[1] + e[2] * e[2])
                .collect();
            checked += distances.len();
            assert!(distances.windows(2).all(|p| p[0] <= p[1]));
        }
        assert!(checked > 0);
    }
}
