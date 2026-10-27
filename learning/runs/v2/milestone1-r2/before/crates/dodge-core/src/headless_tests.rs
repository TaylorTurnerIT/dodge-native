use super::*;

#[test]
fn legacy_capture_fingerprints() -> Result<(), CoreError> {
    let mut expected = [
        (7, 1, 2382405504059571444, 4658003992535463839),
        (7, 7, 4918416684084750761, 11922084184276059089),
        (7, 13, 9648576986366091147, 1708781393887045466),
        (7, 14, 9648576986366091147, 17569629299030478356),
        (7, 57, 5682733197914214409, 13646171142066451070),
        (7, 67, 10496645156560837851, 12365251265229754560),
        (7, 400, 11110010719727987246, 5454277453573999821),
        (7, 2000, 11110010719727987246, 5891900393778317937),
        (42, 1, 2382405504059571444, 15090823182380564159),
        (42, 7, 4918416684084750761, 15029457823635562651),
        (42, 13, 9648576986366091147, 8849507733778565182),
        (42, 14, 9648576986366091147, 6109647735718362678),
        (42, 57, 11519952295273132330, 3726709463488178743),
        (42, 67, 5667634479482931506, 3133253928471107290),
        (42, 400, 11110010719727987246, 5749966501647720722),
        (42, 2000, 11110010719727987246, 3541424567596643815),
        (1234, 1, 2382405504059571444, 1372283663662136067),
        (1234, 7, 4918416684084750761, 13120509659350496321),
        (1234, 13, 9648576986366091147, 8228325366525848782),
        (1234, 14, 9648576986366091147, 15992919611806836253),
        (1234, 57, 367697024428938075, 2580479566689377288),
        (1234, 67, 2623419666436361622, 3063020656298531632),
        (1234, 400, 11110010719727987246, 12576243943002496908),
        (1234, 2000, 11110010719727987246, 9628872391059616427),
    ]
    .into_iter();
    for seed in [7, 42, 1234] {
        let mut game = NativeGame::new(NativeConfig::new(seed));
        let mut actions = PicoRng::new(seed + 100);
        for frame in 1..=2000 {
            let mask = if frame == 1 {
                crate::BUTTON_X_MASK
            } else if frame <= 13 {
                0
            } else {
                let index = actions.rnd(PicoFixed::from_int(9)).floor().raw() >> 16;
                Action::ALL
                    .get(index as usize)
                    .copied()
                    .unwrap_or(Action::Neutral)
                    .mask()
            };
            let result = game.advance_frame_with_post_mask(mask, 0)?;
            if [1, 7, 13, 14, 57, 67, 400, 2000].contains(&frame) {
                assert_eq!(
                    Some((
                        seed,
                        frame,
                        result.snapshot.pixel_hash(),
                        result.snapshot.state_hash()
                    )),
                    expected.next()
                );
            }
        }
    }
    assert_eq!(expected.next(), None);
    Ok(())
}

fn random_mask(rng: &mut PicoRng) -> u8 {
    let index = rng.rnd(PicoFixed::from_int(9)).floor().raw() >> 16;
    Action::ALL
        .get(index as usize)
        .copied()
        .unwrap_or(Action::Neutral)
        .mask()
}

fn assert_live_parity(full: &NativeGame, headless: &NativeGame) {
    let mut full_state = full.full_state();
    let mut headless_state = headless.full_state();
    // This is the only excluded FullState field. Compare live state after the
    // method returns, including the extra trail missing from transition snapshots.
    full_state.physical_screen = IndexedFramebuffer::blank();
    headless_state.physical_screen = IndexedFramebuffer::blank();
    assert_eq!(full_state, headless_state);
    assert_eq!(full.config, headless.config);
    assert_eq!(full.frame_audio, headless.frame_audio);
}

fn pair_step(
    full: &mut NativeGame,
    headless: &mut NativeGame,
    mask: u8,
    post: u8,
) -> Result<(FrameResult, HeadlessResult), CoreError> {
    let score_before = full.score;
    // Exercise both public headless entry points, including a different post mask.
    let actual = if mask == post {
        headless.advance_frame_headless(mask)?
    } else {
        headless.advance_frame_headless_with_post_mask(mask, post)?
    };
    let expected = full.advance_frame_with_post_mask(mask, post)?;
    assert_live_parity(full, headless);
    assert_eq!(actual.frame, expected.frame);
    assert_eq!(actual.mode, expected.mode);
    assert_eq!(actual.input_mask, expected.input_mask);
    assert_eq!(actual.previous_input_mask, expected.previous_input_mask);
    assert_eq!(actual.game_ready, expected.game_ready);
    assert_eq!(actual.started, expected.started);
    assert_eq!(actual.dead, expected.dead);
    assert_eq!(actual.done, expected.done);
    assert_eq!(actual.reward, expected.reward);
    assert_eq!(actual.score, full.score);
    assert_eq!(actual.score_delta, full.score.sub(score_before));
    Ok((expected, actual))
}

fn running_game() -> Result<NativeGame, CoreError> {
    let mut game = NativeGame::new(NativeConfig::new(42));
    game.advance_frame_headless(crate::BUTTON_X_MASK)?;
    for _ in 1..13 {
        game.advance_frame_headless(0)?;
    }
    assert_eq!(game.lifecycle.mode, Mode::Game);
    game.friendly_enabled = false;
    game.enemy_timer = PicoFixed::from_int(-10_000);
    game.patterns_enabled = false;
    game.enemies.clear();
    Ok(game)
}

fn enemy(personality: i8, x: i32, y: i32) -> EnemyState {
    EnemyState {
        personality,
        ..EnemyState::normal(
            PicoFixed::from_int(x),
            PicoFixed::from_int(y),
            PicoFixed::from_int(3),
        )
    }
}

#[test]
fn headless_equivalence_100_seeds_2000_raw_frames() -> Result<(), CoreError> {
    let mut alive_frames = 0;
    let mut dead_frames = 0;
    for seed in 0..100 {
        let mut full = NativeGame::new(NativeConfig::new(seed));
        let mut headless = full.clone();
        let mut actions = PicoRng::new(seed + 1000);
        for frame in 0..2000 {
            let mask = if frame == 0 {
                crate::BUTTON_X_MASK
            } else if frame < 13 {
                0
            } else {
                random_mask(&mut actions)
            };
            let post = if frame % 2 == 0 { mask } else { 0 };
            let (_, result) = pair_step(&mut full, &mut headless, mask, post)?;
            if result.dead {
                dead_frames += 1;
            } else if result.mode == Mode::Game {
                alive_frames += 1;
            }
        }
    }
    assert!(alive_frames > 1000);
    assert!(dead_frames > 0);
    Ok(())
}

#[test]
fn headless_start_boundary_preserves_extra_trail_and_cached_pixels() -> Result<(), CoreError> {
    let mut full = NativeGame::new(NativeConfig::new(42));
    let mut headless = full.clone();
    let cached_pixels = headless.snapshot().pixels().to_owned();
    for frame in 1..=13 {
        let mask = if frame == 1 { crate::BUTTON_X_MASK } else { 0 };
        let (legacy, result) = pair_step(&mut full, &mut headless, mask, 0)?;
        assert_eq!(result.reward, PicoFixed::ZERO);
        if frame < 13 {
            assert_eq!(result.mode, Mode::TransitionToGame);
        } else {
            assert_eq!(result.mode, Mode::Game);
            assert_eq!(
                full.particles.len(),
                legacy.snapshot.logical_state().particles.len() + 1
            );
            assert_eq!(headless.particles.last().map(|p| p.age), Some(0));
        }
    }
    assert_eq!(headless.snapshot().pixels(), &cached_pixels);
    Ok(())
}

#[test]
fn headless_invalid_masks_leave_every_field_unchanged() -> Result<(), CoreError> {
    let mut game = running_game()?;
    // Nonempty audio must also survive pre-mutation validation.
    game.emit_music(3);
    for invalid in 64..=u8::MAX {
        let before = game.clone();
        assert_eq!(
            game.advance_frame_headless(invalid),
            Err(CoreError::InvalidButtonMask(invalid))
        );
        assert_eq!(game, before);
        assert_eq!(
            game.advance_frame_headless_with_post_mask(Button::X.mask(), invalid),
            Err(CoreError::InvalidButtonMask(invalid))
        );
        assert_eq!(game, before);
        assert_eq!(
            game.advance_frame_headless_with_post_mask(invalid, 0),
            Err(CoreError::InvalidButtonMask(invalid))
        );
        assert_eq!(game, before);
        assert_eq!(
            game.advance_frame_with_post_mask(Button::X.mask(), invalid),
            Err(CoreError::InvalidButtonMask(invalid))
        );
        assert_eq!(game, before);
    }
    Ok(())
}

#[test]
fn headless_death_input_and_retry_preserve_legacy_reward_and_score_delta() -> Result<(), CoreError>
{
    let mut full = running_game()?;
    full.score = PicoFixed::from_f32(3.5);
    full.enemies.push(enemy(0, 64, 64));
    let mut headless = full.clone();
    let (legacy, result) = pair_step(&mut full, &mut headless, Button::Right.mask(), 0)?;
    assert!(result.dead && result.done);
    assert_eq!(result.mode, Mode::Game);
    assert_eq!(result.reward, PicoFixed::ZERO);
    assert_eq!(result.score_delta, PicoFixed::ZERO);
    assert_eq!(result.input_mask, Button::Right.mask());
    assert_eq!(result.previous_input_mask, Button::Right.mask());
    assert!(legacy.events.contains(&FrameEvent::Death));
    assert!(full.new_highscore);
    let (_, retry) = pair_step(&mut full, &mut headless, Button::X.mask(), 0)?;
    assert!(!retry.dead);
    assert_eq!(retry.reward, PicoFixed::ONE);
    assert_eq!(retry.score_delta, PicoFixed::from_f32(-3.5));
    Ok(())
}

#[test]
fn headless_freeze_shrink_collection_and_expiration() -> Result<(), CoreError> {
    let mut full = running_game()?;
    full.enemies.push(enemy(3, 64, 64));
    let mut headless = full.clone();
    let (_, freeze) = pair_step(&mut full, &mut headless, 0, 0)?;
    assert_eq!(freeze.score_delta, PicoFixed::ONE);
    assert_eq!(freeze.reward, PicoFixed::ONE);
    assert_eq!(headless.freeze_rate, PicoFixed::from_f32(0.4));
    full.enemies.push(enemy(4, 64, 64));
    headless.enemies.push(enemy(4, 64, 64));
    let (_, shrink) = pair_step(&mut full, &mut headless, 0, 0)?;
    assert_eq!(shrink.score_delta, PicoFixed::ONE);
    assert_eq!(headless.player.size, PicoFixed::from_int(2));
    for _ in 0..1000 {
        pair_step(&mut full, &mut headless, 0, 0)?;
    }
    assert!(!headless.freeze_active);
    assert_eq!(headless.freeze_rate, PicoFixed::ONE);
    assert_eq!(headless.player.size, PicoFixed::from_int(4));
    Ok(())
}

#[test]
fn headless_explode_powerup_kamikaze_and_draw_rng() -> Result<(), CoreError> {
    let mut full = running_game()?;
    // Draw-side powerup trails must consume RNG even when no raster runs.
    full.enemies = vec![enemy(2, 20, 20), enemy(3, 30, 30), enemy(4, 40, 40)];
    let mut headless = full.clone();
    let checkpoint = headless.rng_checkpoint();
    pair_step(&mut full, &mut headless, 0, 0)?;
    assert_ne!(checkpoint, headless.rng_checkpoint());
    for colors in [[8, 9, 10], [1, 13, 7], [7, 0, 0]] {
        assert!(
            headless
                .particles
                .iter()
                .any(|p| p.kind == 1 && p.age == 0 && p.colors == colors)
        );
    }
    full.enemies = vec![
        enemy(2, 64, 64),
        enemy(0, 20, 20),
        enemy(1, 30, 30),
        enemy(3, 40, 40),
    ];
    headless.enemies = full.enemies.clone();
    let (_, explode) = pair_step(&mut full, &mut headless, 0, 0)?;
    assert_eq!(explode.score_delta, PicoFixed::from_int(5));
    assert!(headless.enemies.iter().any(|e| e.personality == -1));
    let start_size = headless.enemies.first().map(|e| e.size);
    for _ in 0..15 {
        pair_step(&mut full, &mut headless, 0, 0)?;
    }
    assert!(headless.enemies.first().map(|e| e.size) > start_size);
    for _ in 0..60 {
        pair_step(&mut full, &mut headless, 0, 0)?;
    }
    assert!(headless.enemies.is_empty());
    Ok(())
}

#[test]
fn headless_all_active_patterns_static_moving_and_completion() -> Result<(), CoreError> {
    let base = running_game()?;
    assert!(!base.patterns.is_empty());
    let mut saw_static = false;
    let mut saw_moving = false;
    let mut completed = 0;
    for index in 0..base.patterns.len() {
        let mut full = base.clone();
        full.patterns_enabled = true;
        full.active_pattern = Some(index);
        full.pattern_active = true;
        full.should_collide = false;
        full.enemies = vec![enemy(0, 20, 20), enemy(1, 40, 40), enemy(3, 100, 100)];
        let pattern = full
            .patterns
            .get(index)
            .ok_or(CoreError::InvalidSnapshotValue)?;
        saw_static |= pattern.pattern_type == 0;
        saw_moving |= pattern.pattern_type == 1;
        let mut headless = full.clone();
        for frame in 0..900 {
            let mask = if frame % 80 < 40 {
                Action::UpLeft.mask()
            } else {
                Action::DownRight.mask()
            };
            pair_step(&mut full, &mut headless, mask, mask)?;
            if full.active_pattern.is_none() {
                completed += 1;
                break;
            }
        }
    }
    assert!(saw_static && saw_moving);
    assert!(completed > 0);
    Ok(())
}

#[test]
fn headless_static_charging_and_moving_rect_death() -> Result<(), CoreError> {
    for pattern_type in [0, 1] {
        let mut full = running_game()?;
        full.patterns_enabled = true;
        full.active_pattern = Some(0);
        full.pattern_active = true;
        let pattern = full
            .patterns
            .first_mut()
            .ok_or(CoreError::InvalidSnapshotValue)?;
        pattern.pattern_type = pattern_type;
        pattern.rects.truncate(1);
        let rect = pattern
            .rects
            .first_mut()
            .ok_or(CoreError::InvalidSnapshotValue)?;
        rect.x = PicoFixed::from_int(60);
        rect.y = PicoFixed::from_int(60);
        rect.width = PicoFixed::from_int(8);
        rect.height = PicoFixed::from_int(8);
        rect.sh = PicoFixed::ZERO;
        rect.dx = PicoFixed::ZERO;
        rect.dy = PicoFixed::ZERO;
        let mut headless = full.clone();
        let (_, result) = pair_step(&mut full, &mut headless, 0, 0)?;
        assert_eq!(result.dead, pattern_type == 1);
        if pattern_type == 0 {
            for game in [&mut full, &mut headless] {
                let rect = game
                    .patterns
                    .first_mut()
                    .and_then(|p| p.rects.first_mut())
                    .ok_or(CoreError::InvalidSnapshotValue)?;
                rect.sh = PicoFixed::from_int(2);
            }
            let (_, result) = pair_step(&mut full, &mut headless, 0, 0)?;
            assert!(result.dead);
        }
    }
    Ok(())
}

#[test]
fn headless_settings_and_transitions_match_in_menu_game_and_death() -> Result<(), CoreError> {
    for initial in 0..3 {
        let mut full = if initial == 0 {
            NativeGame::new(NativeConfig::new(42))
        } else {
            running_game()?
        };
        if initial == 2 {
            full.die();
        }
        let mut headless = full.clone();
        pair_step(&mut full, &mut headless, Button::O.mask(), 0)?;
        for _ in 0..13 {
            pair_step(&mut full, &mut headless, 0, 0)?;
        }
        assert_eq!(full.lifecycle.mode, Mode::Settings);
        for mask in [
            Button::Right.mask(),
            0,
            Button::Down.mask(),
            0,
            Button::Left.mask(),
            0,
            Button::Down.mask(),
            0,
            Button::Right.mask(),
            0,
            Button::Down.mask(),
            0,
            Button::Left.mask(),
            0,
            Button::X.mask(),
        ] {
            pair_step(&mut full, &mut headless, mask, 0)?;
        }
        for _ in 0..13 {
            pair_step(&mut full, &mut headless, 0, 0)?;
        }
        assert_eq!(
            full.lifecycle.mode,
            if initial == 0 { Mode::Menu } else { Mode::Game }
        );
        assert_eq!(full.privileged_view(), headless.privileged_view());
    }
    Ok(())
}

fn assert_current_render(game: &NativeGame) {
    let state = game.full_state();
    let view = crate::snapshot::RenderView::from(&state);
    let render = view.render_state();
    // Start from cached physical pixels to verify scratch rendering preserves
    // canonical projection even when physical camera-exposed edges are stale.
    let mut expected = state.physical_screen.clone();
    crate::snapshot::render_full_state_into(&view, &render, &mut expected);
    let mut projected = [0; crate::FRAMEBUFFER_SIZE];
    expected.project_into(&render, &mut projected);
    let mut actual = [255; crate::FRAMEBUFFER_SIZE];
    game.render_into(&mut actual);
    assert_eq!(actual, projected);
    assert!(actual.iter().all(|&p| p < 16));
    assert_eq!(game.full_state(), state);
}

#[test]
fn on_demand_render_cadence_cannot_change_future_state_or_rng() -> Result<(), CoreError> {
    let mut never = running_game()?;
    never.patterns_enabled = true;
    never.active_pattern = Some(16);
    // No catalog entry enables `smooth`. Exercise that supported branch with
    // an explicit synthetic moving/resizing target without changing the engine.
    let pattern = never
        .patterns
        .get_mut(16)
        .ok_or(CoreError::InvalidSnapshotValue)?;
    pattern.smooth = true;
    let rect = pattern
        .rects
        .first_mut()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    rect.sh = PicoFixed::from_int(2);
    rect.targets = vec![crate::PatternTarget::Move {
        x: PicoFixed::from_int(-20),
        y: PicoFixed::from_int(110),
        width: PicoFixed::from_int(127),
        height: PicoFixed::from_int(32),
    }];
    never.pattern_active = true;
    never.should_collide = false;
    never.enemies = vec![
        enemy(1, 20, 20),
        enemy(2, 30, 30),
        enemy(3, 40, 40),
        enemy(4, 50, 50),
    ];
    never.shake = PicoFixed::from_f32(0.1);
    let mut each = never.clone();
    let mut each_k = never.clone();
    let mut actions = PicoRng::new(1234);
    let mut pixels = [0; crate::FRAMEBUFFER_SIZE];
    for frame in 0..2000 {
        let mask = random_mask(&mut actions);
        assert_eq!(
            never.advance_frame_headless(mask)?,
            each.advance_frame_headless(mask)?
        );
        assert_eq!(
            each_k.advance_frame_headless(mask)?.frame,
            never.lifecycle.frame
        );
        let before = each.clone();
        each.render_into(&mut pixels);
        let first = pixels;
        each.render_into(&mut pixels);
        assert_eq!(pixels, first);
        assert_eq!(each, before);
        if frame % 4 == 0 {
            each_k.render_into(&mut pixels);
            assert_current_render(&each_k);
        }
        assert_eq!(never, each);
        assert_eq!(never, each_k);
    }
    Ok(())
}

#[test]
fn privileged_view_borrows_current_geometry_and_matches_post_method_pixels() -> Result<(), CoreError>
{
    let mut game = running_game()?;
    game.enemies.push(enemy(3, 100, 100));
    game.active_pattern = Some(0);
    let view = game.privileged_view();
    assert!(std::ptr::eq(view.player, &game.player));
    assert!(std::ptr::eq(view.enemies.as_ptr(), game.enemies.as_ptr()));
    let active = view.active_pattern.ok_or(CoreError::InvalidSnapshotValue)?;
    let pattern = game
        .patterns
        .first()
        .ok_or(CoreError::InvalidSnapshotValue)?;
    assert!(std::ptr::eq(active.rects.as_ptr(), pattern.rects.as_ptr()));
    assert_eq!(active.pattern_type, pattern.pattern_type);
    assert_eq!(
        (view.freeze_rate, view.speed, view.enemy_est, view.score),
        (game.freeze_rate, game.speed, game.enemy_est, game.score)
    );
    assert_eq!(
        (
            view.difficulty,
            view.patterns_enabled,
            view.powerups_enabled
        ),
        (
            game.settings.difficulty,
            game.patterns_enabled,
            game.powerups_enabled
        )
    );
    assert_current_render(&game);

    let mut legacy = running_game()?;
    legacy.player.vx = PicoFixed::from_int(20);
    let captured = legacy.advance_frame(Action::Right.mask())?;
    // A newly emitted player particle belongs to the post-method state.
    let current = legacy.privileged_view();
    assert_eq!(
        current.player.x,
        legacy
            .particles
            .last()
            .map(|p| p.x)
            .ok_or(CoreError::InvalidSnapshotValue)?
    );
    let mut pixels = [0; crate::FRAMEBUFFER_SIZE];
    legacy.render_into(&mut pixels);
    assert_ne!(&pixels, captured.snapshot.pixels());
    assert_current_render(&legacy);
    Ok(())
}

#[test]
fn headless_frozen_static_rect_charges_at_current_freeze_rate() -> Result<(), CoreError> {
    let mut full = running_game()?;
    full.patterns_enabled = true;
    full.active_pattern = Some(0);
    full.pattern_active = true;
    full.should_collide = false;
    full.freeze_active = true;
    let mut headless = full.clone();
    for _ in 0..100 {
        pair_step(&mut full, &mut headless, 0, 0)?;
    }
    let rect = headless
        .patterns
        .first()
        .and_then(|p| p.rects.first())
        .ok_or(CoreError::InvalidSnapshotValue)?;
    let expected = PicoFixed::from_f32(0.02)
        .mul_fixed(PicoFixed::from_f32(0.4))
        .mul_fixed(PicoFixed::from_int(100));
    assert_eq!(rect.sh, expected);
    assert!(rect.sh < PicoFixed::ONE);
    assert_eq!(
        headless.privileged_view().freeze_rate,
        PicoFixed::from_f32(0.4)
    );
    Ok(())
}

#[test]
fn headless_configurations_and_post_method_renders_match() -> Result<(), CoreError> {
    for difficulty in 1..=3 {
        for flags in 0..4 {
            let config = NativeConfig {
                difficulty,
                patterns_enabled: flags & 1 != 0,
                powerups_enabled: flags & 2 != 0,
                theme_background: 9,
                theme_shadow: 8,
                ..NativeConfig::new(17)
            };
            let mut full = NativeGame::new(config);
            let mut headless = full.clone();
            let mut actions = PicoRng::new(100);
            for frame in 0..160 {
                let mask = if frame == 0 {
                    Button::X.mask()
                } else if frame < 13 {
                    0
                } else {
                    random_mask(&mut actions)
                };
                pair_step(&mut full, &mut headless, mask, 0)?;
                if frame % 4 == 0 {
                    assert_current_render(&headless);
                }
            }
        }
    }
    Ok(())
}
