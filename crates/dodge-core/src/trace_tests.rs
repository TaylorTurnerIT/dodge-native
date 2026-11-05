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
            // The path ends at the frame before death and agrees with the death position.
            let last = death.recent.last().ok_or(CoreError::InvalidSnapshotValue)?;
            assert_eq!((last.x, last.y), (death.player_x_raw, death.player_y_raw));
            assert!(
                death
                    .recent
                    .windows(2)
                    .all(|w| matches!(w, [a, b] if b.frame == a.frame + 1))
            );
            assert!(last.frame + 1 == death.frame || death.frame == 1);
            if let Some(killer) = death.killer {
                // The killer's last recorded position is where it collided.
                let end = death
                    .killer_path
                    .last()
                    .ok_or(CoreError::InvalidSnapshotValue)?;
                assert_eq!(*end, (1, killer.x, killer.y));
            }
            if matches!(
                death.cause,
                DeathCause::StaticPatternRect | DeathCause::MovingPatternRect
            ) {
                assert!(death.rects.iter().any(|r| r.lethal));
                assert_eq!(
                    last.lethal_rect_gap, 0,
                    "inside a lethal rectangle at death"
                );
            }
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

#[test]
fn samples_cover_the_whole_game_every_thirty_frames() -> Result<(), CoreError> {
    let mut game = running(42, true)?;
    game.should_collide = false;
    for frame in 0..400_u64 {
        game.advance_frame_headless(action_for(5, frame).mask())?;
    }
    let frames: Vec<u32> = game.run_trace().samples().iter().map(|s| s.frame).collect();
    assert_eq!(frames, (1..=13).map(|k| k * 30).collect::<Vec<_>>());
    assert!(game.run_trace().samples().iter().all(|s| s.enemy_gap >= -1));
    Ok(())
}

// LaunchSpark's extension: every pattern appearance keeps the player's path and its
// rectangles, so survived appearances can be drawn as well as deaths.

fn hard(seed: u32, trace: bool) -> Result<NativeGame, CoreError> {
    let mut config = NativeConfig::new(seed);
    config.difficulty = 3;
    config.patterns_enabled = true;
    config.powerups_enabled = true;
    let mut game = NativeGame::new(config);
    game.set_trace_enabled(trace);
    game.advance_frame_headless(crate::BUTTON_X_MASK)?;
    for _ in 1..13 {
        game.advance_frame_headless(0)?;
    }
    assert_eq!(game.lifecycle.mode, Mode::Game);
    Ok(game)
}

fn any_lethal(game: &NativeGame) -> bool {
    game.active_pattern
        .and_then(|index| game.patterns.get(index))
        .is_some_and(|pattern| {
            pattern
                .rects
                .iter()
                .any(|rect| pattern.pattern_type == 1 || rect.sh == PicoFixed::from_int(2))
        })
}

#[test]
fn recorder_does_not_change_the_game() -> Result<(), CoreError> {
    for seed in 0_u32..32 {
        let mut off = hard(seed, false)?;
        let mut on = hard(seed, true)?;
        for frame in 0..1_500_u64 {
            let action = if seed % 4 == 0 {
                Action::Neutral
            } else {
                action_for(u64::from(seed), frame)
            };
            let a = off.advance_frame_headless(action.mask())?;
            let b = on.advance_frame_headless(action.mask())?;
            assert_eq!(a, b, "seed {seed} frame {frame}");
            assert_eq!(off.full_state(), on.full_state());
            assert_eq!(off.telemetry(), on.telemetry());
            if a.dead {
                break;
            }
        }
        assert_eq!(off.snapshot(), on.snapshot());
    }
    Ok(())
}

#[test]
fn pattern_spans_are_separate_per_appearance() -> Result<(), CoreError> {
    let mut game = hard(42, true)?;
    game.should_collide = false;
    let mut repeated = None;
    for frame in 0..40_000_u64 {
        game.advance_frame_headless(action_for(3, frame).mask())?;
        let spans = game.run_trace().patterns();
        let finished: Vec<_> = spans.iter().filter(|s| s.end_frame.is_some()).collect();
        repeated = finished.iter().enumerate().find_map(|(i, a)| {
            finished
                .get(i + 1..)
                .and_then(|rest| rest.iter().find(|b| b.id == a.id))
                .map(|b| (a.start_frame, b.start_frame))
        });
        if repeated.is_some() {
            break;
        }
    }
    let (first, second) = repeated.ok_or(CoreError::InvalidSnapshotValue)?;
    assert!(first < second);
    for span in game.run_trace().patterns() {
        let Some(end) = span.end_frame else {
            continue;
        };
        assert_eq!(
            span.path.len(),
            (end - span.start_frame + 1) as usize,
            "{span:?}"
        );
    }
    Ok(())
}

#[test]
fn span_path_and_rects_are_recorded() -> Result<(), CoreError> {
    let mut game = hard(7, true)?;
    game.should_collide = false;
    let mut positions = Vec::new();
    let mut first_lethal: Vec<(u32, u32)> = Vec::new();
    for frame in 0..20_000_u64 {
        game.advance_frame_headless(action_for(9, frame).mask())?;
        let now = game.run_trace().frame();
        positions.push((now, game.player.x.raw(), game.player.y.raw()));
        if let Some(span) = game.run_trace().active_span() {
            let start = span.start_frame;
            if any_lethal(&game) && !first_lethal.iter().any(|(s, _)| *s == start) {
                first_lethal.push((start, now));
            }
        }
        let static_done = game
            .run_trace()
            .patterns()
            .iter()
            .filter(|s| s.pattern_type != 1 && s.end_frame.is_some())
            .count();
        if static_done >= 2 {
            break;
        }
    }
    let spans = game.run_trace().patterns();
    let checked = spans
        .iter()
        .filter(|s| s.pattern_type != 1 && s.end_frame.is_some())
        .count();
    assert!(checked >= 2, "{spans:?}");
    for span in spans.iter().filter(|s| s.end_frame.is_some()) {
        let expected = first_lethal
            .iter()
            .find(|(start, _)| *start == span.start_frame)
            .map(|(_, frame)| *frame);
        assert_eq!(span.rects_frame, expected, "{span:?}");
        assert_eq!(span.rects.is_empty(), expected.is_none());
        assert!(span.rects.is_empty() || span.rects.iter().any(|r| r.lethal));
        for (offset, point) in span.path.iter().enumerate() {
            let frame = span.start_frame + offset as u32;
            let recorded = positions
                .iter()
                .find(|(f, _, _)| *f == frame)
                .map(|(_, x, y)| (*x, *y));
            assert_eq!(Some(*point), recorded, "frame {frame}");
        }
    }
    let latest = game
        .run_trace()
        .latest_sample()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    assert_eq!(latest.frame, game.run_trace().frame());
    assert_eq!(
        (latest.x, latest.y),
        (game.player.x.raw(), game.player.y.raw())
    );
    Ok(())
}

#[test]
fn death_in_pattern_leaves_span_open() -> Result<(), CoreError> {
    let mut checked = 0;
    for seed in 0_u32..80 {
        let mut game = hard(seed, true)?;
        for frame in 0..8_000_u64 {
            if !game
                .advance_frame_headless(action_for(u64::from(seed), frame).mask())?
                .dead
            {
                continue;
            }
            let trace = game.run_trace();
            let death = trace.death().ok_or(CoreError::InvalidSnapshotValue)?;
            if death.active_pattern.is_some() {
                let span = trace
                    .patterns()
                    .last()
                    .ok_or(CoreError::InvalidSnapshotValue)?;
                assert_eq!(span.end_frame, None);
                assert_eq!(
                    span.start_frame + span.path.len() as u32 - 1,
                    death.frame,
                    "seed {seed}"
                );
                checked += 1;
            }
            break;
        }
    }
    assert!(checked > 0);
    Ok(())
}

#[test]
fn killer_age_and_fyou_flag_are_exact() -> Result<(), CoreError> {
    let mut game = first_fyou_game()?;
    let spawn_frame = game
        .run_trace()
        .fyou_triggers()
        .first()
        .ok_or(CoreError::InvalidSnapshotValue)?
        .frame;
    for _ in 0..24 {
        game.advance_frame_headless(0)?;
    }
    game.should_collide = true;
    game.friendly_enabled = false;
    move_onto_player(&mut game, 1)?;
    assert!(game.advance_frame_headless(0)?.dead);
    let death = game
        .run_trace()
        .death()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    let killer = death.killer.ok_or(CoreError::InvalidSnapshotValue)?;
    assert_eq!(killer.fyou_spawned, Some(true));
    assert_eq!(killer.age_frames, Some(death.frame - spawn_frame));
    assert_eq!(death.frame - spawn_frame, 25);
    Ok(())
}

fn with_options(options: crate::TrainingOptions) -> Result<NativeGame, CoreError> {
    let mut game = NativeGame::new(NativeConfig {
        training: options,
        ..NativeConfig::new(42)
    });
    game.set_trace_enabled(true);
    game.advance_frame_headless(crate::BUTTON_X_MASK)?;
    for _ in 1..13 {
        game.advance_frame_headless(0)?;
    }
    game.patterns_enabled = false;
    game.enemy_timer = PicoFixed::from_int(-30_000);
    game.should_collide = false;
    Ok(game)
}

#[test]
fn fyou_counts_the_enemies_it_actually_adds() -> Result<(), CoreError> {
    let mut game = with_options(crate::TrainingOptions {
        normal_enemies: false,
        ..crate::TrainingOptions::CARTRIDGE
    })?;
    while game.run_trace().fyou_triggers().is_empty() {
        game.advance_frame_headless(0)?;
    }
    assert!(
        game.run_trace()
            .fyou_triggers()
            .iter()
            .all(|t| t.spawned == 0)
    );
    assert!(game.enemies.is_empty());
    Ok(())
}

#[test]
fn a_contact_absorbed_by_a_life_is_not_a_death() -> Result<(), CoreError> {
    let mut game = with_options(crate::TrainingOptions {
        lives: 1,
        ..crate::TrainingOptions::CARTRIDGE
    })?;
    while game.run_trace().fyou_triggers().is_empty() {
        game.advance_frame_headless(0)?;
    }
    game.should_collide = true;
    game.friendly_enabled = false;
    move_onto_player(&mut game, 0)?;
    assert!(!game.advance_frame_headless(0)?.dead);
    assert!(game.run_trace().death().is_none());
    assert_eq!(game.telemetry().lives_spent, 1);
    move_onto_player(&mut game, 0)?;
    assert!(game.advance_frame_headless(0)?.dead);
    let death = game
        .run_trace()
        .death()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    assert_eq!(death.cause, DeathCause::NormalEnemy);
    assert_eq!(death.frame, game.run_trace().frame());
    Ok(())
}
