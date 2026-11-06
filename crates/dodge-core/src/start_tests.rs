//! Tapping X once and holding it through the 13 startup frames start the same
//! game. Upstream's environment taps; LaunchSpark/DodgeAI's batch environment
//! held X (with X as the post-frame mask too), so evaluations recorded under
//! either start stay comparable.

use super::*;
use crate::Action;

const STARTUP_FRAMES: u32 = 13;

fn tapped(config: NativeConfig) -> Result<NativeGame, CoreError> {
    let mut game = NativeGame::new(config);
    game.advance_frame_headless(crate::BUTTON_X_MASK)?;
    for _ in 1..STARTUP_FRAMES {
        game.advance_frame_headless(0)?;
    }
    Ok(game)
}

fn held(config: NativeConfig) -> Result<NativeGame, CoreError> {
    let mut game = NativeGame::new(config);
    for _ in 0..STARTUP_FRAMES {
        game.advance_frame_headless_with_post_mask(crate::BUTTON_X_MASK, crate::BUTTON_X_MASK)?;
    }
    Ok(game)
}

/// Gameplay state without the input masks, which record the button itself.
fn without_input(game: &NativeGame) -> FullState {
    FullState {
        input: InputState::new(),
        ..game.full_state()
    }
}

fn action_for(seed: u32, frame: u32) -> Action {
    let mixed = u64::from(frame / 5)
        .wrapping_mul(0x9E37_79B9_7F4A_7C15)
        .wrapping_add(u64::from(seed).wrapping_mul(0xD1B5_4A32_D192_ED03));
    Action::ALL
        .get(usize::try_from((mixed >> 33) % 9).unwrap_or(0))
        .copied()
        .unwrap_or(Action::Neutral)
}

#[test]
fn tapping_and_holding_x_start_the_same_game() -> Result<(), CoreError> {
    for seed in [0_u32, 1, 13, 42, 7_777, 30_100, 0xD000_0001] {
        for difficulty in 1..=3 {
            for flags in 0..4 {
                let config = NativeConfig {
                    difficulty,
                    patterns_enabled: flags & 1 != 0,
                    powerups_enabled: flags & 2 != 0,
                    ..NativeConfig::new(seed)
                };
                let mut tap = tapped(config)?;
                let mut hold = held(config)?;
                assert_eq!(tap.lifecycle().mode, Mode::Game);
                assert_eq!(hold.lifecycle().mode, Mode::Game);
                // Same RNG, player, enemies, patterns and timers; only the
                // input masks differ (X still down, or released).
                assert_eq!(without_input(&tap), without_input(&hold));
                assert_eq!(tap.input().current_mask(), 0);
                assert_eq!(hold.input().current_mask(), crate::BUTTON_X_MASK);
                // After the first gameplay frame nothing differs at all.
                for frame in 0..2_000 {
                    let mask = action_for(seed, frame).mask();
                    let a = tap.advance_frame_headless(mask)?;
                    let b = hold.advance_frame_headless(mask)?;
                    assert_eq!(a, b, "seed {seed} difficulty {difficulty} frame {frame}");
                    assert_eq!(tap.full_state(), hold.full_state());
                    if a.dead {
                        break;
                    }
                }
            }
        }
    }
    Ok(())
}
