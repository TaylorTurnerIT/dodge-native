use super::*;
use crate::{Action, DeathCause};

fn running(seed: u32, trace: bool) -> Result<NativeGame, CoreError> {
    let mut game = NativeGame::new(NativeConfig::new(seed));
    game.set_trace_enabled(trace);
    game.advance_frame_headless(crate::BUTTON_X_MASK)?;
    for _ in 1..13 {
        game.advance_frame_headless(0)?;
    }
    assert_eq!(game.lifecycle.mode, Mode::Game);
    Ok(game)
}

/// Deterministic pseudo-random action stream that does not touch game RNG.
fn action_for(policy: u64, frame: u64) -> Action {
    let mixed = (frame / 7)
        .wrapping_mul(0x9E37_79B9_7F4A_7C15)
        .wrapping_add(policy.wrapping_mul(0xD1B5_4A32_D192_ED03));
    Action::ALL
        .get(usize::try_from((mixed >> 33) % 9).unwrap_or(0))
        .copied()
        .unwrap_or(Action::Neutral)
}

#[test]
fn tracing_on_and_off_produce_bit_identical_trajectories() -> Result<(), CoreError> {
    for seed in [1_u32, 42, 7_777, 0xD000_0001] {
        // Policy 0 camps in the center so fyou fires; the others roam.
        for policy in 0_u64..4 {
            let mut off = running(seed, false)?;
            let mut on = running(seed, true)?;
            for frame in 0..4_000_u64 {
                let action = if policy == 0 {
                    Action::Neutral
                } else {
                    action_for(policy, frame)
                };
                let a = off.advance_frame_headless(action.mask())?;
                let b = on.advance_frame_headless(action.mask())?;
                assert_eq!(a, b, "seed {seed} policy {policy} frame {frame}");
                // Whole-game `==` is not usable across two instances: enemy rows
                // carry process-local identity namespaces. `full_state` is the
                // canonical gameplay state, including RNG.
                assert_eq!(off.full_state(), on.full_state());
                if a.dead {
                    break;
                }
            }
            assert_eq!(
                off.death_diagnostic().cause(),
                on.death_diagnostic().cause()
            );
            assert!(!off.run_trace().enabled());
            assert!(off.run_trace().fyou_triggers().is_empty());
            assert!(off.run_trace().patterns().is_empty());
            assert!(off.run_trace().death().is_none());
        }
    }
    Ok(())
}

#[test]
fn camping_player_triggers_fyou_every_fifty_one_frames() -> Result<(), CoreError> {
    let mut game = running(42, true)?;
    game.patterns_enabled = false;
    game.enemy_timer = PicoFixed::from_int(-30_000);
    game.should_collide = false;
    for _ in 0..200 {
        game.advance_frame_headless(0)?;
    }
    let trace = game.run_trace();
    let frames: Vec<u32> = trace.fyou_triggers().iter().map(|t| t.frame).collect();
    // The last startup frames already run the game update, so the timer is
    // ahead of the gameplay frame count by the number of those frames.
    let first = *frames.first().ok_or(CoreError::InvalidSnapshotValue)?;
    assert!((40..=51).contains(&first), "{frames:?}");
    assert_eq!(frames, vec![first, first + 51, first + 102, first + 153]);
    assert!(trace.fyou_triggers().iter().all(|t| t.spawned == 4));
    // Independent of the trace: with ordinary spawns off, the enemy-row birth
    // counter equals the corner enemies the triggers claimed to spawn, and every
    // enemy still alive (some expire) is attributed to fyou.
    let claimed: u64 = trace
        .fyou_triggers()
        .iter()
        .map(|t| u64::from(t.spawned))
        .sum();
    assert_eq!(game.enemies.next_birth(), Some(claimed));
    let serials = game
        .enemies
        .serials()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    assert!(!serials.is_empty());
    assert!(
        serials
            .iter()
            .all(|s| trace.is_fyou_birth(*s) == Some(true))
    );
    assert_eq!(trace.frame(), 200);
    assert_eq!(trace.center_dwell_frames(), 200);
    Ok(())
}

#[test]
fn leaving_the_center_resets_dwell_but_not_the_trace() -> Result<(), CoreError> {
    let mut game = running(42, true)?;
    game.patterns_enabled = false;
    game.enemy_timer = PicoFixed::from_int(-30_000);
    game.should_collide = false;
    for _ in 0..30 {
        game.advance_frame_headless(0)?;
    }
    assert_eq!(game.run_trace().center_dwell_frames(), 30);
    for _ in 0..40 {
        game.advance_frame_headless(Action::Left.mask())?;
    }
    assert_eq!(game.run_trace().center_dwell_frames(), 0);
    assert!(game.run_trace().fyou_triggers().is_empty());
    Ok(())
}

fn first_fyou_game() -> Result<NativeGame, CoreError> {
    let mut game = running(42, true)?;
    game.patterns_enabled = false;
    game.enemy_timer = PicoFixed::from_int(-30_000);
    game.should_collide = false;
    while game.run_trace().fyou_triggers().is_empty() {
        game.advance_frame_headless(0)?;
    }
    // Fyou fires before the frame's collision check; make a non-fyou enemy too.
    game.enemies.push(EnemyState::normal(
        PicoFixed::from_int(10),
        PicoFixed::from_int(10),
        PicoFixed::from_int(3),
    ));
    Ok(game)
}

fn move_onto_player(game: &mut NativeGame, index: usize) -> Result<(), CoreError> {
    let player = game.player;
    let enemy = game
        .enemies
        .get_mut(index)
        .ok_or(CoreError::InvalidSnapshotValue)?;
    enemy.x = player.x;
    enemy.y = player.y;
    Ok(())
}

#[test]
fn killer_attribution_separates_fyou_from_ordinary_spawns() -> Result<(), CoreError> {
    for (index, expected_fyou) in [(0_usize, true), (4_usize, false)] {
        let mut game = first_fyou_game()?;
        assert_eq!(game.enemies.len(), 5);
        game.should_collide = true;
        game.friendly_enabled = false;
        move_onto_player(&mut game, index)?;
        let result = game.advance_frame_headless(0)?;
        assert!(result.dead);
        let death = game
            .run_trace()
            .death()
            .ok_or(CoreError::InvalidSnapshotValue)?;
        assert_eq!(death.cause, DeathCause::NormalEnemy);
        assert_eq!(death.frame, game.run_trace().frame());
        let killer = death.killer.ok_or(CoreError::InvalidSnapshotValue)?;
        assert_eq!(killer.fyou_spawned, Some(expected_fyou));
        // The killer is excluded; the other four of five are counted.
        assert_eq!(death.enemies_alive[0], 4);
        assert_eq!(
            death.fyou_enemies_alive,
            Some(if expected_fyou { 3 } else { 4 })
        );
        // A killer inserted by the test (not by the game) has no recorded birth.
        assert_eq!(killer.age_frames.is_some(), expected_fyou);
    }
    Ok(())
}

#[test]
fn fyou_killer_age_counts_frames_since_spawn() -> Result<(), CoreError> {
    let mut game = first_fyou_game()?;
    let spawn_frame = game
        .run_trace()
        .fyou_triggers()
        .first()
        .ok_or(CoreError::InvalidSnapshotValue)?
        .frame;
    for _ in 0..9 {
        game.advance_frame_headless(0)?;
    }
    game.should_collide = true;
    game.friendly_enabled = false;
    move_onto_player(&mut game, 0)?;
    game.advance_frame_headless(0)?;
    let death = game
        .run_trace()
        .death()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    let killer = death.killer.ok_or(CoreError::InvalidSnapshotValue)?;
    assert_eq!(killer.age_frames, Some(death.frame - spawn_frame));
    assert_eq!(death.frame - spawn_frame, 10);
    Ok(())
}

#[test]
fn natural_deaths_report_pattern_and_cause_consistently() -> Result<(), CoreError> {
    let mut with_pattern = 0;
    let mut deaths = 0;
    for seed in 0_u32..60 {
        let mut game = running(seed, true)?;
        for frame in 0..6_000_u64 {
            let result = game.advance_frame_headless(action_for(u64::from(seed), frame).mask())?;
            if !result.dead {
                continue;
            }
            deaths += 1;
            let trace = game.run_trace();
            let death = trace.death().ok_or(CoreError::InvalidSnapshotValue)?;
            assert_eq!(Some(death.cause), game.death_diagnostic().cause());
            assert_eq!(death.frame, trace.frame());
            match death.cause {
                DeathCause::StaticPatternRect | DeathCause::MovingPatternRect => {
                    let pattern = death
                        .active_pattern
                        .as_ref()
                        .ok_or(CoreError::InvalidSnapshotValue)?;
                    assert_eq!(
                        pattern.pattern_type == 1,
                        death.cause == DeathCause::MovingPatternRect
                    );
                    assert!(death.killer.is_none());
                }
                _ => assert!(death.killer.is_some()),
            }
            if let Some(pattern) = &death.active_pattern {
                with_pattern += 1;
                let span = trace
                    .patterns()
                    .last()
                    .ok_or(CoreError::InvalidSnapshotValue)?;
                assert_eq!((span.id, span.end_frame), (pattern.id, None));
                assert_eq!(pattern.start_frame, span.start_frame);
                assert_eq!(pattern.frames_since_start, death.frame - span.start_frame);
            }
            break;
        }
    }
    assert!(deaths > 40, "{deaths}");
    assert!(with_pattern > 0);
    Ok(())
}

#[test]
fn pattern_spans_close_when_patterns_finish() -> Result<(), CoreError> {
    let mut game = running(42, true)?;
    game.should_collide = false;
    for frame in 0..9_000_u64 {
        game.advance_frame_headless(action_for(3, frame).mask())?;
    }
    let spans = game.run_trace().patterns();
    assert!(spans.len() >= 2, "{spans:?}");
    let (last, finished) = spans.split_last().ok_or(CoreError::InvalidSnapshotValue)?;
    assert!(
        finished
            .iter()
            .all(|s| s.end_frame.is_some_and(|e| e > s.start_frame))
    );
    assert_eq!(last.end_frame.is_none(), game.active_pattern.is_some());
    assert!(
        spans
            .windows(2)
            .all(|w| matches!(w, [a, b] if a.end_frame <= Some(b.start_frame)))
    );
    Ok(())
}

#[test]
fn reset_and_restore_clear_the_trace() -> Result<(), CoreError> {
    let mut game = first_fyou_game()?;
    assert!(!game.run_trace().fyou_triggers().is_empty());
    let snapshot = game.snapshot();
    let restored = NativeGame::restore(&snapshot)?;
    assert!(!restored.run_trace().enabled());
    game.reset();
    assert!(game.run_trace().enabled());
    assert!(game.run_trace().fyou_triggers().is_empty());
    assert_eq!(game.run_trace().frame(), 0);
    Ok(())
}
