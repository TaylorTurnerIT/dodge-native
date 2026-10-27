use super::*;
use crate::{EnemySerial, PatternRect, PatternTarget, WarningLine};

fn running() -> Result<NativeGame, CoreError> {
    let mut game = NativeGame::new(NativeConfig::new(42));
    game.advance_frame_headless(crate::BUTTON_X_MASK)?;
    for _ in 1..13 {
        game.advance_frame_headless(0)?;
    }
    assert_eq!(game.lifecycle.mode, Mode::Game);
    game.friendly_enabled = false;
    game.patterns_enabled = false;
    game.enemy_timer = PicoFixed::from_int(-10_000);
    game.enemies.clear();
    Ok(game)
}

fn row(personality: i8, x: i32, y: i32) -> EnemyState {
    EnemyState {
        personality,
        ..EnemyState::normal(
            PicoFixed::from_int(x),
            PicoFixed::from_int(y),
            PicoFixed::from_int(3),
        )
    }
}

fn ids(game: &NativeGame) -> Result<Vec<EnemySerial>, CoreError> {
    let ids = game
        .enemy_serials()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    assert_eq!(ids.len(), game.enemies().len());
    assert!(ids.windows(2).all(|pair| pair.first() < pair.last()));
    Ok(ids.to_vec())
}

fn receipt(test: &str, cases: usize) {
    println!("M2_CORE_COVERAGE_JSON {{\"test\":\"{test}\",\"cases\":{cases}}}");
}

#[test]
fn enemy_append_remove_mutate_and_capacity_do_not_alias() -> Result<(), CoreError> {
    let mut game = running()?;
    for x in 0..100 {
        game.enemies.push(row(0, x, 20));
        ids(&game)?;
    }
    let original = ids(&game)?;
    assert_eq!(original.len(), 100); // Core never truncates at the wrapper's cap.
    game.enemies
        .get_mut(1)
        .ok_or(CoreError::InvalidSnapshotValue)?
        .size = PicoFixed::from_int(6);
    assert_eq!(ids(&game)?, original);
    assert_eq!(game.remove_enemy_at(0), Some(row(0, 0, 20)));
    assert_eq!(game.remove_enemy_at(500), None);
    assert_eq!(
        ids(&game)?.as_slice(),
        original.get(1..).unwrap_or_default()
    );
    game.enemies.push(row(1, 120, 20));
    let after = ids(&game)?;
    assert_eq!(after.len(), 100);
    assert!(after.last() > original.last());
    receipt("append_remove_mutate_capacity", 104);
    Ok(())
}

#[test]
fn earlier_removal_requires_serial_matching_for_measured_growth() -> Result<(), CoreError> {
    let mut game = running()?;
    game.enemies.push(row(0, -20, -20));
    game.enemies.push(EnemyState {
        size: PicoFixed::from_int(5),
        max_size: PicoFixed::from_int(6),
        ..row(0, 100, 100)
    });
    let previous_ids = ids(&game)?;
    let previous = game.enemies().to_vec(); // Wrapper-owned test history only.
    game.remove_enemy_at(0);
    game.update_enemies();
    let current_ids = ids(&game)?;
    let current = game
        .enemies()
        .first()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    assert_eq!(current_ids.first(), previous_ids.get(1));
    let matched_index = previous_ids
        .iter()
        .position(|id| Some(id) == current_ids.first())
        .ok_or(CoreError::InvalidSnapshotValue)?;
    let matched = previous
        .get(matched_index)
        .ok_or(CoreError::InvalidSnapshotValue)?;
    let wrong = previous.first().ok_or(CoreError::InvalidSnapshotValue)?;
    assert_eq!(current.size.sub(matched.size), PicoFixed::ONE);
    assert_ne!(current.size.sub(wrong.size), PicoFixed::ONE);
    assert_ne!(current.x.sub(matched.x), current.x.sub(wrong.x));
    receipt("earlier_removal_measured_growth", 1);
    Ok(())
}

#[test]
fn life_expiry_and_dying_kamikaze_append_keep_survivors() -> Result<(), CoreError> {
    let mut game = running()?;
    game.enemy_should_collide = false;
    game.enemies.push(EnemyState {
        life: Some(PicoFixed::ONE),
        ..row(-1, -20, -20)
    });
    game.enemies.push(EnemyState {
        is_dying: true,
        ..row(1, 20, 20)
    });
    game.enemies.push(row(0, 100, 100));
    let before = ids(&game)?;
    game.update_enemies();
    let after = ids(&game)?;
    assert_eq!(after.len(), 2);
    assert_eq!(after.first(), before.last());
    assert!(after.last() > before.last());
    let explosion = game
        .enemies()
        .last()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    assert_eq!(explosion.personality, -1);
    // The appended explosion is visited during the very same update loop.
    assert_eq!(explosion.life, Some(PicoFixed::from_int(59)));
    assert_eq!(explosion.size, PicoFixed::ONE);
    assert_eq!(game.score, SCORE_PER_SHATTER);
    receipt("life_expiry_dying_kamikaze_miditeration_append", 2);
    Ok(())
}

#[test]
fn explode_chain_keeps_old_explosion_and_new_births() -> Result<(), CoreError> {
    let mut game = running()?;
    for enemy in [
        row(2, 64, 64),
        row(1, 20, 20),
        row(-1, 40, 40),
        row(1, 90, 90),
    ] {
        game.enemies.push(enemy);
    }
    let before = ids(&game)?;
    game.explode_powerup_enemy(0);
    let after = ids(&game)?;
    assert_eq!(after.len(), 3);
    assert_eq!(after.first(), before.get(2));
    assert!(after.get(1) > before.last());
    assert!(game.enemies().iter().all(|enemy| enemy.personality == -1));
    // Four original entries plus two appended explosions are visited.
    assert_eq!(game.score, PicoFixed::from_int(6));
    receipt("explode_chain_miditeration_births", 1);
    Ok(())
}

#[test]
fn dying_pair_retains_identity_until_each_actual_removal() -> Result<(), CoreError> {
    let mut game = running()?;
    for _ in 0..2 {
        game.enemies.push(EnemyState {
            inside: true,
            ..row(0, 30, 30)
        });
    }
    let before = ids(&game)?;
    game.update_enemies();
    let pending = ids(&game)?;
    assert_eq!(pending, before.get(..1).unwrap_or_default());
    assert!(game.enemies().iter().all(|enemy| enemy.is_dying));
    assert_eq!(game.score, SCORE_PER_SHATTER);
    game.update_enemies();
    assert!(ids(&game)?.is_empty());
    assert_eq!(game.score, PicoFixed::ONE);
    receipt("dying_pair_actual_removal", 2);
    Ok(())
}

#[test]
fn corner_fyou_clear_reset_and_retry_never_reuse_births() -> Result<(), CoreError> {
    let mut game = running()?;
    let mut events = Vec::new();
    game.friendly_timer = 50;
    game.update_fyou(&mut events);
    let corners = ids(&game)?;
    assert_eq!(corners.len(), 4);
    assert_eq!(events, vec![FrameEvent::EnemySpawn; 4]);
    game.enemies.clear();
    assert!(ids(&game)?.is_empty());
    game.add_corner_enemies(&mut events);
    let after_clear = ids(&game)?;
    assert!(after_clear.first() > corners.last());
    game.restart_gameplay();
    assert!(ids(&game)?.is_empty());
    game.add_corner_enemies(&mut events);
    let after_retry = ids(&game)?;
    assert!(after_retry.first() > after_clear.last());
    game.reset();
    assert!(ids(&game)?.is_empty());
    game.add_corner_enemies(&mut events);
    assert!(ids(&game)?.first() > after_retry.last());
    receipt("corner_fyou_clear_reset_retry", 4);
    Ok(())
}

#[test]
fn fresh_and_restored_namespaces_preserve_wire_and_logical_state() -> Result<(), CoreError> {
    let mut game = running()?;
    game.enemies.push(row(0, 100, 100));
    let original = ids(&game)?;
    let snapshot = game.snapshot();
    let bytes = snapshot.canonical_bytes();
    let mut restored = NativeGame::restore(&snapshot)?;
    let mut restored_bytes = NativeGame::restore_bytes(&bytes)?;
    assert_ne!(ids(&restored)?, original);
    assert_ne!(ids(&restored)?, ids(&restored_bytes)?);
    assert_ne!(restored, game); // Structural equality includes identity metadata.
    assert_eq!(restored.full_state(), game.full_state());
    assert_eq!(restored.snapshot().canonical_bytes(), bytes);
    let mut fresh = NativeGame::new(NativeConfig::new(42));
    fresh.enemies.push(row(0, 100, 100));
    assert_ne!(ids(&fresh)?, original);
    for _ in 0..5 {
        let expected = game.advance_frame_headless(0)?;
        assert_eq!(restored.advance_frame_headless(0)?, expected);
        assert_eq!(restored_bytes.advance_frame_headless(0)?, expected);
        assert_eq!(restored.full_state(), game.full_state());
        assert_eq!(restored_bytes.full_state(), game.full_state());
        assert_eq!(
            restored.snapshot().canonical_bytes(),
            game.snapshot().canonical_bytes()
        );
        ids(&restored)?;
        ids(&restored_bytes)?;
    }
    receipt("fresh_restore_namespaces_wire_logical_parity", 3);
    Ok(())
}

fn warning_game() -> Result<NativeGame, CoreError> {
    let mut game = running()?;
    let pattern = game
        .patterns
        .first_mut()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    pattern.pattern_type = 1;
    pattern.timer = PicoFixed::ZERO;
    pattern.rects = vec![PatternRect {
        x: PicoFixed::from_int(96),
        y: PicoFixed::from_int(96),
        width: PicoFixed::from_int(10),
        height: PicoFixed::from_int(10),
        speed: PicoFixed::ONE,
        dx: PicoFixed::ZERO,
        dy: PicoFixed::ZERO,
        targets: Vec::new(),
        target_index: 0,
        wait: PicoFixed::ZERO,
        shown: false,
        sh: PicoFixed::ZERO,
        warnings: vec![WarningLine {
            x0: PicoFixed::from_f32(8.5),
            y0: PicoFixed::from_f32(20.5),
            x1: PicoFixed::from_f32(16.5),
            y1: PicoFixed::from_f32(20.5),
        }],
        collision_done: false,
        finished: true,
    }];
    game.active_pattern = Some(0);
    // A stale active flag must not override the renderer's actual pattern ref.
    game.pattern_active = false;
    Ok(game)
}

#[test]
fn warning_thresholds_type_and_static_charge_match_renderer() -> Result<(), CoreError> {
    let base = warning_game()?;
    let two = PicoFixed::from_int(2);
    let threshold = PicoFixed::from_int(125);
    let mut cases = 0;
    for kind in [0, 1, 2] {
        for sh in [
            PicoFixed::ZERO,
            PicoFixed::ONE,
            two.sub(PicoFixed::from_raw(1)),
            two,
            two.add(PicoFixed::from_raw(1)),
        ] {
            for timer in [
                threshold.sub(PicoFixed::from_raw(1)),
                threshold,
                threshold.add(PicoFixed::from_raw(1)),
            ] {
                let mut game = base.clone();
                let pattern = game
                    .patterns
                    .first_mut()
                    .ok_or(CoreError::InvalidSnapshotValue)?;
                pattern.pattern_type = kind;
                pattern.timer = timer;
                let rect = pattern
                    .rects
                    .first_mut()
                    .ok_or(CoreError::InvalidSnapshotValue)?;
                rect.sh = sh;
                let expected = timer < threshold && !(kind == 0 && sh < two);
                assert_eq!(game.drawn_warning_lines().count(), usize::from(expected));
                let mut pixels = [0; crate::FRAMEBUFFER_SIZE];
                game.render_into(&mut pixels);
                // rounded_coordinate rounds these .5 values up; line2 keeps
                // both main and y+1 shadow rows, with inclusive endpoints.
                for x in 9..=17 {
                    assert_eq!(
                        pixels.get(21 * 128 + x),
                        Some(&if expected { 7 } else { 12 })
                    );
                    assert_eq!(
                        pixels.get(22 * 128 + x),
                        Some(&if expected { 1 } else { 12 })
                    );
                }
                cases += 1;
            }
        }
    }
    receipt("warning_thresholds_type_static_branch_raster_shadow", cases);
    Ok(())
}

#[test]
fn warning_borrow_staleness_hidden_targets_and_read_immutability() -> Result<(), CoreError> {
    let mut game = warning_game()?;
    let before = game.clone();
    let line = game
        .drawn_warning_lines()
        .next()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    let stored = game
        .patterns
        .first()
        .and_then(|p| p.rects.first())
        .and_then(|r| r.warnings.first())
        .ok_or(CoreError::InvalidSnapshotValue)?;
    assert!(std::ptr::eq(line, stored));
    let lines: Vec<_> = game.drawn_warning_lines().copied().collect();
    let view = game.privileged_view();
    assert!(std::ptr::eq(view.enemies.as_ptr(), game.enemies().as_ptr()));
    let mut pixels = [0; crate::FRAMEBUFFER_SIZE];
    game.render_into(&mut pixels);
    assert_eq!(game, before);
    let pattern = game
        .patterns
        .first_mut()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    pattern.timer = PicoFixed::from_int(100);
    let rect = pattern
        .rects
        .first_mut()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    rect.targets = vec![PatternTarget::Move {
        x: PicoFixed::from_int(-500),
        y: PicoFixed::from_int(500),
        width: PicoFixed::from_int(127),
        height: PicoFixed::ZERO,
    }];
    rect.target_index = 30;
    rect.wait = PicoFixed::from_int(500);
    rect.shown = true;
    rect.finished = false;
    assert_eq!(
        game.drawn_warning_lines().copied().collect::<Vec<_>>(),
        lines
    );
    let mut after = [0; crate::FRAMEBUFFER_SIZE];
    game.render_into(&mut after);
    assert_eq!(pixels, after);
    // Hidden targets never reconstruct a line missing from the stored array.
    game.patterns
        .first_mut()
        .and_then(|p| p.rects.first_mut())
        .ok_or(CoreError::InvalidSnapshotValue)?
        .warnings
        .clear();
    assert_eq!(game.drawn_warning_lines().count(), 0);
    game.active_pattern = None;
    assert_eq!(game.drawn_warning_lines().count(), 0);
    receipt("warning_borrow_stale_hidden_targets_immutability", 4);
    Ok(())
}

#[test]
fn warning_scene_eligibility_is_separate_from_mode_and_death() -> Result<(), CoreError> {
    let mut game = warning_game()?;
    let lines: Vec<_> = game.drawn_warning_lines().copied().collect();
    for mode in [Mode::Game, Mode::Menu, Mode::Settings] {
        for dead in [false, true] {
            game.lifecycle.mode = mode;
            game.lifecycle.dead = dead;
            assert_eq!(
                game.drawn_warning_lines().copied().collect::<Vec<_>>(),
                lines
            );
            let mut pixels = [0; crate::FRAMEBUFFER_SIZE];
            game.render_into(&mut pixels);
            if mode == Mode::Game {
                assert_eq!(pixels.get(21 * 128 + 10), Some(&if dead { 12 } else { 7 }));
            }
        }
    }
    receipt("warning_scene_mode_death_separation", 6);
    Ok(())
}

#[test]
fn repeated_same_frame_deaths_keep_events_but_headless_dead_is_boolean() -> Result<(), CoreError> {
    for deaths in [2, 3] {
        let mut full = running()?;
        for _ in 0..deaths {
            full.enemies.push(row(0, 64, 64));
        }
        let mut headless = full.clone();
        let before = full.survival_frames;
        let legacy = full.advance_frame(0)?;
        let result = headless.advance_frame_headless(0)?;
        assert_eq!(
            legacy
                .events
                .iter()
                .filter(|&&e| e == FrameEvent::Death)
                .count(),
            deaths
        );
        assert_eq!(
            legacy
                .events
                .iter()
                .filter(|&&e| e == FrameEvent::Collision)
                .count(),
            deaths
        );
        assert_eq!(
            legacy
                .audio
                .iter()
                .filter(|&&e| e == AudioEvent::Music { track: 22 })
                .count(),
            deaths
        );
        assert!(result.dead && result.done);
        assert_eq!(result.reward, PicoFixed::ZERO);
        assert_eq!(result.score_delta, PicoFixed::ZERO);
        assert_eq!(headless.survival_frames, before);
        let mut state = full.full_state();
        state.physical_screen = IndexedFramebuffer::blank();
        let mut other = headless.full_state();
        other.physical_screen = IndexedFramebuffer::blank();
        assert_eq!(state, other);
        assert_eq!(ids(&full)?, ids(&headless)?);
        let next = full.advance_frame(0)?;
        assert!(!next.events.contains(&FrameEvent::Death));
        assert!(headless.advance_frame_headless(0)?.dead);
    }
    receipt("repeated_same_frame_death_boolean_boundary", 2);
    Ok(())
}

#[test]
fn exhausted_metadata_preserves_rendered_headless_gameplay_and_rng() -> Result<(), CoreError> {
    let mut ordinary = running()?;
    ordinary.should_collide = false;
    ordinary.enemy_should_collide = false;
    let mut exhausted = ordinary.clone();
    exhausted.enemies = EnemyRows::last_birth_fixture();
    for enemy in [row(0, 20, 20), row(1, 90, 90), row(3, 100, 20)] {
        ordinary.enemies.push(enemy);
        exhausted.enemies.push(enemy);
    }
    assert_eq!(exhausted.enemy_serials(), None);
    assert_eq!(exhausted.enemies().len(), ordinary.enemies().len());
    assert_eq!(
        exhausted.snapshot().canonical_bytes(),
        ordinary.snapshot().canonical_bytes()
    );
    let mut headless = exhausted.clone();
    for _ in 0..100 {
        let control = ordinary.advance_frame(0)?;
        let rendered = exhausted.advance_frame(0)?;
        let skipped = headless.advance_frame_headless(0)?;
        assert_eq!(control, rendered);
        assert_eq!(skipped.dead, rendered.dead);
        assert_eq!(skipped.score, exhausted.score);
        assert_eq!(skipped.score_delta, PicoFixed::ZERO);
        assert_eq!(exhausted.enemy_serials(), None);
        assert_eq!(headless.enemy_serials(), None);
        assert_eq!(ordinary.full_state(), exhausted.full_state());
        let mut a = exhausted.full_state();
        let mut b = headless.full_state();
        a.physical_screen = IndexedFramebuffer::blank();
        b.physical_screen = IndexedFramebuffer::blank();
        assert_eq!(a, b);
    }
    exhausted.reset();
    exhausted.enemies.push(row(0, 20, 20));
    assert_eq!(exhausted.enemy_serials(), None);
    exhausted.restart_gameplay();
    exhausted.enemies.push(row(0, 20, 20));
    assert_eq!(exhausted.enemy_serials(), None);
    assert_eq!(exhausted.enemies().len(), 1);
    println!(
        "M2_CORE_SIZE_JSON {{\"native_game_bytes\":{},\"enemy_state_bytes\":{},\"enemy_serial_bytes\":{},\"enemy_rows_bytes\":{},\"old_vec_bytes\":{}}}",
        std::mem::size_of::<NativeGame>(),
        std::mem::size_of::<EnemyState>(),
        std::mem::size_of::<EnemySerial>(),
        std::mem::size_of::<EnemyRows>(),
        std::mem::size_of::<Vec<EnemyState>>(),
    );
    receipt(
        "exhausted_metadata_rendered_headless_rng_logical_parity",
        102,
    );
    Ok(())
}
