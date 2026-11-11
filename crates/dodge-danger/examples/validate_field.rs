//! Checks the hand-written homing predictor against exact neutral rollouts.
//!
//! The predictor returns `horizon` for "no collision inside the horizon". The
//! exact rollout is mapped to the same sentinel. A sample counts only when at
//! least one side reports a collision before the horizon.
//!
//! Run with: `cargo run --release -p dodge-danger --example validate_field`

use dodge_core::{Action, NativeConfig, NativeGame};
use dodge_danger::{predict_player_arrival, start_game};

const HORIZON: u32 = 36;
const SEEDS: u32 = 24;
const MAX_FRAMES: u32 = 3_000;

#[derive(Default)]
struct Tally {
    compared: u32,
    both_hit: u32,
    exact: u32,
    early: u32,
    late: u32,
    missed_hit: u32,
    false_alarm: u32,
    abs_error: i64,
    worst: i32,
}

fn main() {
    for difficulty in 1..=3_u8 {
        let mut tally = Tally::default();
        for seed in 0..SEEDS {
            run_seed(seed, difficulty, &mut tally);
        }
        println!(
            "difficulty {difficulty}: compared {}, both hit {}, exact {}, predicted early {}, predicted late {}, \
             missed hit {}, false alarm {}, mean abs error {:.2} frames, worst {} frames",
            tally.compared,
            tally.both_hit,
            tally.exact,
            tally.early,
            tally.late,
            tally.missed_hit,
            tally.false_alarm,
            tally.abs_error as f64 / f64::from(tally.both_hit.max(1)),
            tally.worst,
        );
    }
}

fn run_seed(seed: u32, difficulty: u8, tally: &mut Tally) {
    let config = NativeConfig {
        difficulty,
        patterns_enabled: false,
        powerups_enabled: false,
        ..NativeConfig::new(seed)
    };
    let mut game = NativeGame::new(config);
    if start_game(&mut game).is_err() {
        return;
    }
    for _ in 0..MAX_FRAMES {
        // The neutral player starts at rest, so "stay put" is exact only while
        // the player has no velocity. Skip frames where it does.
        let player = game.player();
        let at_rest = player.vx.to_double().abs() < 1e-9 && player.vy.to_double().abs() < 1e-9;
        if at_rest && !game.enemies().is_empty() {
            let predicted = predict_player_arrival(&game, HORIZON);
            let actual = exact_arrival(&game);
            if predicted < HORIZON as f32 || actual < HORIZON {
                tally.compared += 1;
                if actual >= HORIZON {
                    tally.false_alarm += 1;
                } else if predicted >= HORIZON as f32 {
                    tally.missed_hit += 1;
                } else {
                    let delta = predicted as i32 - actual as i32;
                    tally.both_hit += 1;
                    tally.abs_error += i64::from(delta.abs());
                    tally.worst = tally.worst.max(delta.abs());
                    match delta {
                        0 => tally.exact += 1,
                        d if d < 0 => tally.early += 1,
                        _ => tally.late += 1,
                    }
                }
            }
        }
        match game.advance_frame_headless(Action::Neutral.mask()) {
            Ok(result) if !result.dead => {}
            _ => break,
        }
    }
}

/// First frame at which a neutral player dies in an exact engine rollout.
/// Returns `HORIZON` when no collision happens inside the horizon.
fn exact_arrival(game: &NativeGame) -> u32 {
    let mut sim = game.clone();
    for step in 1..=HORIZON {
        match sim.advance_frame_headless(Action::Neutral.mask()) {
            Ok(result) if result.dead => return step,
            Ok(_) => {}
            Err(_) => break,
        }
    }
    HORIZON
}
