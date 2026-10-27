use crate::features::History;
use crate::*;
use dodge_core::{
    ActivePatternView, EnemySerial, EnemyState, NativeConfig, NativeGame, PatternRect,
    PatternTarget, PicoFixed, PlayerState, PrivilegedView, WarningLine,
};

#[path = "../tests/support/m0_policy.rs"]
pub(crate) mod m0_policy;
#[path = "../tests/support/wire_fixture.rs"]
pub(crate) mod wire_fixture;

fn q(n: i32) -> PicoFixed {
    PicoFixed::from_int(n)
}
fn enemy(personality: i8, x: i32, y: i32, size: i32) -> EnemyState {
    EnemyState {
        personality,
        size: q(size),
        isizing: false,
        ..EnemyState::normal(q(x), q(y), q(size))
    }
}
fn rect(x: i32, y: i32, w: i32, h: i32, sh: PicoFixed) -> PatternRect {
    PatternRect {
        x: q(x),
        y: q(y),
        width: q(w),
        height: q(h),
        speed: PicoFixed::ZERO,
        dx: PicoFixed::ZERO,
        dy: PicoFixed::ZERO,
        targets: vec![],
        target_index: 0,
        wait: PicoFixed::ZERO,
        shown: true,
        sh,
        warnings: vec![],
        collision_done: false,
        finished: false,
    }
}
fn view<'a>(
    p: &'a PlayerState,
    enemies: &'a [EnemyState],
    rects: Option<(u8, &'a [PatternRect])>,
) -> PrivilegedView<'a> {
    PrivilegedView {
        player: p,
        enemies,
        freeze_rate: PicoFixed::ONE,
        speed: PicoFixed::ONE,
        enemy_est: q(2),
        score: PicoFixed::ZERO,
        active_pattern: rects.map(|(pattern_type, rects)| ActivePatternView {
            pattern_type,
            rects,
        }),
        difficulty: 2,
        patterns_enabled: true,
        powerups_enabled: true,
    }
}
fn ids(n: usize) -> crate::Result<Vec<EnemySerial>> {
    let game = NativeGame::new(NativeConfig::new(1));
    let game = NativeGame::restore(&wire_fixture::with_enemies(
        &game,
        &vec![enemy(0, 10, 10, 2); n],
    )?)?;
    Ok(game.enemy_serials().ok_or("missing serials")?.to_vec())
}
fn obs(
    history: &mut History,
    v: PrivilegedView<'_>,
    serials: &[EnemySerial],
) -> crate::Result<Observation> {
    history.observe_raw(v, Some(serials))?;
    Ok(history.observation(v, std::iter::empty(), true)?)
}
fn evaluation_config(seeds: Vec<Vec<u32>>) -> EnvConfig {
    EnvConfig {
        batch_size: seeds.len(),
        seed_mode: SeedMode::Evaluation {
            seeds_by_slot: seeds,
        },
        ..EnvConfig::default()
    }
}
fn canonical(env: &VecDodgeEnv) -> Vec<Vec<u8>> {
    (0..env.batch_info().config.batch_size)
        .map(|i| env.test_game(i).snapshot().canonical_bytes())
        .collect()
}

#[test]
fn validates_every_config_bound_without_clamping() {
    let good = EnvConfig::default();
    assert_eq!(good.raw_frame_cap, 18000);
    assert_eq!(good.action_repeat, 4);
    for bad in [
        EnvConfig {
            batch_size: 0,
            ..good.clone()
        },
        EnvConfig {
            action_repeat: 1,
            ..good.clone()
        },
        EnvConfig {
            action_repeat: 5,
            ..good.clone()
        },
        EnvConfig {
            difficulty: 0,
            ..good.clone()
        },
        EnvConfig {
            difficulty: 4,
            ..good.clone()
        },
        EnvConfig {
            raw_frame_cap: 0,
            ..good.clone()
        },
        EnvConfig {
            num_threads: 0,
            ..good.clone()
        },
        EnvConfig {
            chunk_size: 0,
            ..good.clone()
        },
        evaluation_config(vec![]),
        evaluation_config(vec![vec![]]),
    ] {
        assert!(bad.validate().is_err(), "{bad:?}");
    }
    for k in 2..=4 {
        for difficulty in 1..=3 {
            assert!(
                EnvConfig {
                    action_repeat: k,
                    difficulty,
                    ..good.clone()
                }
                .validate()
                .is_ok()
            );
        }
    }
}

#[test]
fn exact_global_and_entity_normalizations_and_padding() -> crate::Result<()> {
    let p = PlayerState {
        x: q(32),
        y: q(96),
        vx: PicoFixed::from_f32(1.25),
        vy: PicoFixed::from_f32(-2.5),
        size: q(2),
    };
    let enemies = [enemy(0, 80, 100, 4)];
    let serials = ids(1)?;
    let v = PrivilegedView {
        freeze_rate: PicoFixed::from_f32(0.4),
        speed: PicoFixed::from_f32(1.5),
        enemy_est: q(1),
        score: q(50),
        ..view(&p, &enemies, None)
    };
    let o = obs(&mut History::default(), v, &serials)?;
    assert_eq!(
        o.global_feats[0],
        [
            -0.5,
            0.5,
            0.5,
            -1.0,
            0.5,
            PicoFixed::from_f32(0.4).to_f32(),
            0.5,
            0.5,
            1.0_f64.tanh() as f32,
            0.0,
            30.0 / 123.0,
            93.0 / 123.0,
            94.0 / 123.0,
            29.0 / 123.0
        ]
    );
    assert_eq!(
        o.entity_feats[0],
        [
            18.0 / 128.0,
            38.0 / 128.0,
            2.0 / 64.0,
            2.0 / 64.0,
            50.0 / 128.0,
            6.0 / 128.0,
            0.0,
            0.0,
            0.0,
            0.0,
            47.0 / 64.0,
            3.0 / 64.0,
            1.0,
            0.0,
            0.0,
            1.0
        ]
    );
    assert_eq!(o.entity_types[0], 1);
    assert!(o.entity_mask[0]);
    assert!(o.entity_types[1..].iter().all(|x| *x == 0));
    assert!(o.entity_mask[1..].iter().all(|x| !*x));
    assert!(o.entity_feats[1..].iter().flatten().all(|x| *x == 0.0));
    Ok(())
}

#[test]
fn types_masks_empty_allowlist_and_finite() -> crate::Result<()> {
    let p = PlayerState::new();
    let serials = ids(6)?;
    let enemies: Vec<_> = [0, 1, -1, 2, 3, 4]
        .into_iter()
        .map(|t| enemy(t, 10, 20, 4))
        .collect();
    let rects = [rect(10, 10, 20, 20, q(2))];
    let mut history = History::default();
    let mut o = obs(
        &mut history,
        view(&p, &enemies, Some((0, &rects))),
        &serials,
    )?;
    assert_eq!(&o.entity_types[..6], &[1, 2, 3, 4, 5, 6]);
    assert_eq!(o.entity_types[64], 7);
    o = obs(
        &mut history,
        view(&p, &enemies, Some((1, &rects))),
        &serials,
    )?;
    assert_eq!(o.entity_types[64], 8);
    assert_eq!(o.entity_mask.iter().filter(|x| **x).count(), 7);
    assert!(
        o.global_feats
            .iter()
            .flatten()
            .chain(o.entity_feats.iter().flatten())
            .all(|x| x.is_finite())
    );
    let empty = obs(&mut History::default(), view(&p, &[], None), &[])?;
    assert_eq!(empty.global_feats[0].len(), 14);
    assert_eq!(empty.entity_feats.len(), 80);
    assert_eq!(empty.entity_feats[0].len(), 16);
    assert!(empty.entity_mask.iter().all(|x| !x));
    assert_eq!(empty.global_feats[0][9], 0.0);
    Ok(())
}

#[test]
fn stable_serial_merge_survives_earlier_removal_and_new_birth() -> crate::Result<()> {
    let p = PlayerState::new();
    let serials = ids(3)?;
    let mut h = History::default();
    let first = [enemy(0, 10, 10, 2), enemy(1, 20, 20, 2)];
    obs(&mut h, view(&p, &first, None), &serials[..2])?;
    let mut moved = first[1];
    moved.x = q(25);
    moved.size = q(3);
    let next = [moved, enemy(0, 100, 100, 1)];
    let o = obs(&mut h, view(&p, &next, None), &serials[1..])?;
    assert_eq!(o.entity_feats[0][6], 5.5 / 4.0);
    assert_eq!(o.entity_feats[0][8], 0.5 / 4.0);
    assert_eq!(&o.entity_feats[1][6..10], &[0.0; 4]);
    assert_eq!(o.diagnostics.unknown_enemy_samples, 3);
    Ok(())
}

#[test]
fn half_raw_growth_and_powerup_internal_size_jump() -> crate::Result<()> {
    let p = PlayerState::new();
    let serials = ids(2)?;
    let mut h = History::default();
    let mut enemies = [enemy(0, 10, 10, 1), enemy(3, 20, 20, 1)];
    obs(&mut h, view(&p, &enemies, None), &serials)?;
    enemies[0].size = PicoFixed::from_raw(q(1).raw() + 1);
    enemies[1].size = q(4);
    let o = obs(&mut h, view(&p, &enemies, None), &serials)?;
    assert_eq!(o.entity_feats[0][6], 0.5 / (65536.0 * 4.0));
    assert_eq!(o.entity_feats[0][8], 0.5 / (65536.0 * 4.0));
    assert_eq!(&o.entity_feats[1][6..10], &[0.0; 4]);
    assert_eq!(o.entity_feats[1][2], 4.0 / 64.0);
    Ok(())
}

#[test]
fn missing_mismatched_or_unordered_serials_fail_closed() -> crate::Result<()> {
    let p = PlayerState::new();
    let enemies = [enemy(0, 10, 10, 1), enemy(0, 20, 20, 1)];
    let serials = ids(2)?;
    for serials in [
        None,
        Some(&serials[..1]),
        Some(&[serials[1], serials[0]][..]),
    ] {
        assert!(
            History::default()
                .observe_raw(view(&p, &enemies, None), serials)
                .is_err()
        );
    }
    Ok(())
}

#[test]
fn final_raw_delta_not_repeat_average_and_every_none_gap_resets() -> crate::Result<()> {
    let p = PlayerState::new();
    let mut rects = [rect(0, 10, 20, 20, q(1))];
    let mut h = History::default();
    obs(&mut h, view(&p, &[], Some((0, &rects))), &[])?;
    for x in [2, 8, 9, 15] {
        rects[0].x = q(x);
        h.observe_raw(view(&p, &[], Some((0, &rects))), Some(&[]))?;
    }
    let o = h.observation(view(&p, &[], Some((0, &rects))), std::iter::empty(), true)?;
    assert_eq!(o.entity_feats[64][6], 6.0 / 4.0);
    h.observe_raw(view(&p, &[], None), Some(&[]))?;
    rects[0].x = q(100);
    rects[0].sh = PicoFixed::from_f32(1.5);
    let o = obs(&mut h, view(&p, &[], Some((0, &rects))), &[])?;
    assert_eq!(&o.entity_feats[64][6..10], &[0.0; 4]);
    assert_eq!(o.entity_feats[64][13], 1.0);
    assert_eq!(o.diagnostics.raw_history_samples, 7);
    Ok(())
}

#[test]
fn charge_unknown_flat_fading_full_and_moving_phases() -> crate::Result<()> {
    let p = PlayerState::new();
    let mut rects = [rect(10, 10, 127, 32, q(1))];
    let mut h = History::default();
    let first = obs(&mut h, view(&p, &[], Some((0, &rects))), &[])?;
    assert_eq!(first.entity_feats[64][13], 1.0);
    assert_eq!(first.diagnostics.unknown_phase_samples, 1);
    rects[0].sh = PicoFixed::from_f32(1.02);
    let o = obs(&mut h, view(&p, &[], Some((0, &rects))), &[])?;
    let expected =
        ((2.0 - rects[0].sh.to_double()) / (rects[0].sh.to_double() - 1.0) / 120.0) as f32;
    assert_eq!(o.entity_feats[64][13], expected);
    assert!(
        o.auxiliary.as_ref().unwrap()[1]
            .iter()
            .flatten()
            .any(|v| *v == 1.0)
    );
    for sh in [rects[0].sh, PicoFixed::ONE, PicoFixed::from_f32(0.9)] {
        rects[0].sh = sh;
        let o = obs(&mut h, view(&p, &[], Some((0, &rects))), &[])?;
        assert_eq!(o.entity_feats[64][13], 1.0);
        assert_eq!(o.entity_feats[64][15], 0.0);
        assert!(
            o.auxiliary.as_ref().unwrap()[1]
                .iter()
                .flatten()
                .all(|v| *v == 0.0)
        );
    }
    rects[0].sh = q(2);
    let o = obs(&mut h, view(&p, &[], Some((0, &rects))), &[])?;
    assert_eq!(o.entity_feats[64][13], 0.0);
    assert_eq!(o.entity_feats[64][15], 1.0);
    rects[0].sh = q(1);
    let o = obs(&mut h, view(&p, &[], Some((1, &rects))), &[])?;
    assert_eq!(o.entity_feats[64][15], 1.0);
    Ok(())
}

#[test]
fn hidden_enemy_rect_and_config_fields_do_not_enter_neural_arrays() -> crate::Result<()> {
    let p = PlayerState::new();
    let serials = ids(1)?;
    let mut enemies = [enemy(0, 10, 10, 3)];
    let mut rects = [rect(20, 20, 30, 30, q(1))];
    let mut a = History::default();
    let mut b = History::default();
    obs(&mut a, view(&p, &enemies, Some((0, &rects))), &serials)?;
    obs(&mut b, view(&p, &enemies, Some((0, &rects))), &serials)?;
    let before = obs(&mut a, view(&p, &enemies, Some((0, &rects))), &serials)?;
    enemies[0].max_size = q(300);
    enemies[0].life = Some(q(60));
    enemies[0].speed = q(200);
    enemies[0].vx = q(20);
    enemies[0].vy = q(-20);
    enemies[0].inside = true;
    enemies[0].is_dying = true;
    enemies[0].isizing = true;
    rects[0].targets = vec![PatternTarget::Wait(q(10))];
    rects[0].target_index = 2;
    rects[0].wait = q(100);
    rects[0].shown = false;
    rects[0].dx = q(50);
    rects[0].dy = q(-50);
    rects[0].speed = q(60);
    rects[0].collision_done = true;
    rects[0].finished = true;
    let v = PrivilegedView {
        difficulty: 3,
        patterns_enabled: false,
        powerups_enabled: false,
        ..view(&p, &enemies, Some((0, &rects)))
    };
    let after = obs(&mut b, v, &serials)?;
    assert_eq!(before, after);
    Ok(())
}

#[test]
fn current_admission_keeps_unclipped_geometry_without_sticky_tracking() -> crate::Result<()> {
    let p = PlayerState::new();
    let serials = ids(3)?;
    let mut h = History::default();
    let mut enemies = [
        enemy(0, -2, 10, 4),
        enemy(-1, 127, 10, -4),
        enemy(3, 131, 127, 1),
    ];
    let o = obs(&mut h, view(&p, &enemies, None), &serials)?;
    assert_eq!(o.diagnostics.admitted_enemies, 3);
    assert_eq!(o.entity_feats[0][0], -0.5);
    assert!(o.entity_feats[2][0] > (127.0 - 64.0) / 128.0);
    assert!(o.entity_feats[1][2] < 0.0);
    assert_eq!(o.diagnostics.inverted_boxes, 1);
    assert_eq!(o.diagnostics.inverted_axes, 2);
    enemies[0].x = q(-100);
    enemies[1].x = q(128);
    enemies[2].x = q(132);
    let o = obs(&mut h, view(&p, &enemies, None), &serials)?;
    assert!(o.entity_mask.iter().all(|x| !x));
    Ok(())
}

#[test]
fn auxiliary_enemy_body_excludes_explosions() -> crate::Result<()> {
    let player = PlayerState::new();
    let enemies = [enemy(0, 8, 8, 2), enemy(1, 24, 8, 2), enemy(-1, 40, 8, 2)];
    let serials = ids(enemies.len())?;
    let observation = obs(
        &mut History::default(),
        view(&player, &enemies, None),
        &serials,
    )?;
    assert_eq!(&observation.entity_types[..3], &[1, 2, 3]);
    let auxiliary = observation.auxiliary.ok_or("missing targets")?;
    // Each body occupies one distinct patch. Explosions remain lethal, while
    // only normal and kamikaze bodies belong to the enemy-collision target.
    for y in 0..16 {
        for x in 0..16 {
            assert_eq!(
                auxiliary[0][y][x],
                f32::from(y == 1 && [1, 3, 5].contains(&x))
            );
            assert_eq!(auxiliary[1][y][x], 0.0);
            assert_eq!(auxiliary[2][y][x], f32::from(y == 1 && [1, 3].contains(&x)));
            assert_eq!(auxiliary[3][y][x], 0.0);
            assert_eq!(
                auxiliary[4][y][x],
                f32::from([7, 8].contains(&y) && [7, 8].contains(&x))
            );
        }
    }
    Ok(())
}

#[test]
fn warnings_do_not_admit_hidden_control_and_shadow_is_onscreen() -> crate::Result<()> {
    let p = PlayerState::new();
    let rects = [rect(-50, -50, 0, 0, PicoFixed::ZERO)];
    let v = view(&p, &[], Some((1, &rects)));
    let mut h = History::default();
    h.observe_raw(v, Some(&[]))?;
    let hidden = h.observation(v, std::iter::empty(), true)?;
    assert_eq!(hidden.global_feats[0][9], 0.0);
    assert!(!hidden.entity_mask[64]);
    let warning = WarningLine {
        x0: q(8),
        y0: q(-1),
        x1: q(15),
        y1: q(-1),
    };
    let o = h.observation(v, std::iter::once(&warning), true)?;
    assert_eq!(o.global_feats[0][9], 1.0);
    assert!(!o.entity_mask[64]);
    assert_eq!(o.diagnostics.onscreen_warnings, 1);
    let aux = o.auxiliary.unwrap();
    assert_eq!(aux[1][0][1], 1.0);
    assert_eq!(aux[1].iter().flatten().sum::<f32>(), 1.0);
    let diagonal = WarningLine {
        x0: q(0),
        y0: q(0),
        x1: q(10),
        y1: q(10),
    };
    assert!(h.observation(v, std::iter::once(&diagonal), true).is_err());
    Ok(())
}

#[test]
fn caps_apply_after_admission_enemy_ties_use_serial_and_rect_overflow_errors() -> crate::Result<()>
{
    let p = PlayerState::new();
    let serials = ids(66)?;
    let mut enemies = vec![enemy(0, 10, 10, 1); 66];
    enemies[0].x = q(-100); // hidden row consumes no slot
    for (i, e) in enemies.iter_mut().enumerate().skip(1) {
        e.x = PicoFixed::from_raw(q(10).raw() + i as i32);
    }
    let o = obs(&mut History::default(), view(&p, &enemies, None), &serials)?;
    assert_eq!(o.diagnostics.admitted_enemies, 65);
    assert_eq!(o.diagnostics.dropped_enemies, 1);
    assert_eq!(o.entity_mask.iter().filter(|x| **x).count(), 64);
    // All stationary nonoverlap times tie at 120; keep earliest admitted births.
    assert_eq!(
        o.entity_feats[63][0],
        ((10.5 + 64.0 / 65536.0 - 64.0) / 128.0) as f32
    );
    let rects = vec![rect(10, 10, 127, 32, q(2)); 17];
    let mut h = History::default();
    h.observe_raw(view(&p, &[], Some((0, &rects))), Some(&[]))?;
    assert_eq!(
        h.observation(view(&p, &[], Some((0, &rects))), std::iter::empty(), true),
        Err(EnvError::RectangleOverflow(17))
    );
    Ok(())
}

#[test]
fn fresh_startup_and_seed_stream_preserve_high_bits_and_reserved_split() -> crate::Result<()> {
    assert_ne!(
        training_seed(1, 0, 0)?.actual_seed,
        training_seed(1 + (1_u64 << 32), 0, 0)?.actual_seed
    );
    for slot in 0..7 {
        for episode in 0..20 {
            let s = training_seed(u64::MAX, slot, episode)?;
            assert!(!(0xB0000000..=0xB00003E7).contains(&s.actual_seed));
            assert_eq!(s, training_seed(u64::MAX, slot, episode)?);
        }
    }
    let mut env = VecDodgeEnv::new(EnvConfig {
        raw_frame_cap: 1,
        ..EnvConfig::default()
    })?;
    let first = env.episode_info()[0].clone();
    assert_eq!(first.startup_frames, 13);
    assert_eq!(first.gameplay_frames, 0);
    let initial = env.test_game(0).snapshot();
    let state = initial.logical_state();
    assert_eq!(state.highscores, [PicoFixed::ZERO; 12]);
    assert_eq!(
        [state.settings.theme_background, state.settings.theme_shadow],
        [12, 1]
    );
    env.step(&[0])?;
    let reset = env.reset_done(&[0])?;
    assert_eq!(reset.info[0].seed.episode, 1);
    assert_ne!(reset.info[0].seed.actual_seed, first.seed.actual_seed);
    assert_eq!(reset.info[0].diagnostics.raw_history_samples, 1);
    assert_eq!(
        env.test_game(0).snapshot().logical_state().highscores,
        [PicoFixed::ZERO; 12]
    );
    Ok(())
}

#[test]
fn action_and_reset_requests_validate_whole_batch_before_mutation() -> crate::Result<()> {
    let mut env = VecDodgeEnv::new(EnvConfig {
        batch_size: 3,
        raw_frame_cap: 1,
        ..EnvConfig::default()
    })?;
    let initial = canonical(&env);
    let info = env.episode_info();
    for ids in [&[0, 0][..], &[0, 0, 9][..], &[0, -1, 0][..]] {
        assert!(env.step(ids).is_err());
        assert_eq!(canonical(&env), initial);
        assert_eq!(env.episode_info(), info);
    }
    assert!(matches!(
        env.reset_done(&[2, 0]),
        Err(EnvError::SlotNotEnded(2))
    ));
    assert_eq!(canonical(&env), initial);
    env.step(&[0, 0, 0])?;
    let ended = canonical(&env);
    let info = env.episode_info();
    for indices in [&[0, 0][..], &[1, 3][..]] {
        assert!(env.reset_done(indices).is_err());
        assert_eq!(canonical(&env), ended);
        assert_eq!(env.episode_info(), info);
    }
    assert!(matches!(env.step(&[0, 0, 0]), Err(EnvError::SlotEnded(0))));
    assert_eq!(canonical(&env), ended);
    let reset = env.reset_done(&[2, 0])?;
    assert_eq!(reset.observations.indices, vec![2, 0]);
    assert_eq!(
        reset.info.iter().map(|i| i.seed.slot).collect::<Vec<_>>(),
        vec![2, 0]
    );
    let before = canonical(&env);
    assert!(matches!(
        env.reset_done(&[1, 0]),
        Err(EnvError::SlotNotEnded(0))
    ));
    assert_eq!(canonical(&env), before);
    Ok(())
}

#[test]
fn cap_ragged_steps_alive_bootstrap_and_terminal_stack() -> crate::Result<()> {
    let mut env = VecDodgeEnv::new(EnvConfig {
        raw_frame_cap: 5,
        render_pixels: true,
        auxiliary_targets: true,
        ..EnvConfig::default()
    })?;
    let initial = env.observations()?;
    let pixels = initial.pixels.as_ref().unwrap();
    assert!(pixels.chunks_exact(16384).all(|p| p == &pixels[..16384]));
    let a = env.step(&[2])?;
    assert_eq!(a.elapsed_raw_frames, vec![4]);
    assert_eq!(a.alive_raw_frames, vec![4]);
    assert_eq!(a.rewards, vec![0.04]);
    let b = env.step(&[2])?;
    assert_eq!(b.elapsed_raw_frames, vec![1]);
    assert_eq!(b.truncated, vec![true]);
    assert_eq!(b.terminated, vec![false]);
    assert!(b.info[0].bootstrap);
    assert_eq!(b.observations.pixel_valid, vec![true]);
    assert_eq!(b.observations.pixel_aux_pair_valid, vec![true]);
    assert_eq!(b.info[0].diagnostics.raw_history_samples, 6);
    let mut dead = VecDodgeEnv::new(EnvConfig {
        raw_frame_cap: 1,
        render_pixels: true,
        auxiliary_targets: true,
        ..EnvConfig::default()
    })?;
    let fixture = wire_fixture::with_enemies(
        dead.test_game(0),
        &[enemy(0, 64, 64, 4), enemy(3, 64, 64, 4)],
    )?;
    dead.test_restore(0, &fixture)?;
    let pixels = dead.observations()?.pixels.unwrap();
    let d = dead.step(&[2])?;
    assert_eq!(d.elapsed_raw_frames, vec![1]);
    assert_eq!(d.alive_raw_frames, vec![0]);
    assert_eq!(d.terminated, vec![true]);
    assert_eq!(d.truncated, vec![false]);
    assert_eq!(d.score_delta_raw_fixed, vec![65536]);
    assert_eq!(d.rewards, vec![-4.0]);
    assert!(!d.info[0].bootstrap);
    assert_eq!(d.observations.pixels.unwrap(), pixels);
    assert_eq!(d.observations.pixel_valid, vec![false]);
    assert_eq!(d.observations.pixel_aux_pair_valid, vec![false]);
    assert_eq!(
        d.observations.global_feats[8],
        (1.0_f64 / 50.0).tanh() as f32
    );
    Ok(())
}

#[test]
fn repeated_same_frame_deaths_pickup_both_orders_one_penalty_and_ragged_batch() -> crate::Result<()>
{
    for personality in [3, 4] {
        for pickup_first in [false, true] {
            let mut env = VecDodgeEnv::new(EnvConfig {
                batch_size: 2,
                raw_frame_cap: 3,
                ..EnvConfig::default()
            })?;
            let mut enemies = vec![enemy(0, 64, 64, 4), enemy(1, 64, 64, 4)];
            let pickup = enemy(personality, 64, 64, 4);
            if pickup_first {
                enemies.insert(0, pickup)
            } else {
                enemies.push(pickup)
            }
            let fixture = wire_fixture::with_enemies(env.test_game(0), &enemies)?;
            let mut full = NativeGame::restore(&fixture)?;
            let native = full.advance_frame(0)?;
            assert_eq!(
                native
                    .events
                    .iter()
                    .filter(|e| **e == dodge_core::FrameEvent::Death)
                    .count(),
                2
            );
            assert_eq!(full.score(), PicoFixed::ONE);
            env.test_restore(0, &fixture)?;
            let result = env.step(&[0, 0])?;
            assert_eq!(result.elapsed_raw_frames, vec![1, 3]);
            assert_eq!(result.alive_raw_frames, vec![0, 3]);
            assert_eq!(result.rewards, vec![-4.0, 0.03]);
            assert_eq!(result.terminated, vec![true, false]);
            assert_eq!(result.truncated, vec![false, true]);
            assert_eq!(result.info[0].objective_return, -4.0);
        }
    }
    Ok(())
}

#[test]
fn returned_buffers_are_owned_and_resets_refill_pixel_history() -> crate::Result<()> {
    let mut env = VecDodgeEnv::new(EnvConfig {
        raw_frame_cap: 1,
        render_pixels: true,
        auxiliary_targets: true,
        ..EnvConfig::default()
    })?;
    let initial = env.observations()?;
    let saved = initial.clone();
    let mut result = env.step(&[2])?;
    let current = env.observations()?;
    result.observations.global_feats.fill(123.0);
    result.observations.entity_feats.fill(456.0);
    result.observations.entity_mask.fill(true);
    result.observations.entity_types.fill(99);
    result.observations.pixels.as_mut().unwrap().fill(200);
    result.observations.auxiliary.as_mut().unwrap().fill(400.0);
    assert_eq!(env.observations()?, current);
    assert_eq!(initial, saved);
    let reset = env.reset_done(&[0])?;
    let pixels = reset.observations.pixels.unwrap();
    assert!(pixels.chunks_exact(16384).all(|p| p == &pixels[..16384]));
    assert_eq!(reset.info[0].gameplay_frames, 0);
    assert_eq!(reset.observations.pixel_aux_pair_valid, vec![true]);
    Ok(())
}

#[test]
fn parallel_error_poison_retains_partial_state_and_only_reset_all_recovers() -> crate::Result<()> {
    let mut env = VecDodgeEnv::new(EnvConfig {
        batch_size: 3,
        num_threads: 2,
        chunk_size: 1,
        ..EnvConfig::default()
    })?;
    env.test_inject_error(1, EnvError::RectangleOverflow(17));
    let result = env.step(&[0, 0, 0]);
    assert!(matches!(result, Err(EnvError::BatchFailure(_))));
    assert!(env.is_poisoned());
    assert_eq!(
        env.episode_info()
            .iter()
            .map(|i| i.gameplay_frames)
            .collect::<Vec<_>>(),
        vec![4, 1, 4]
    );
    assert!(env.last_failures()[0].1.contains("RectangleOverflow(17)"));
    assert!(matches!(env.observations(), Err(EnvError::Poisoned)));
    assert!(matches!(env.step(&[0, 0, 0]), Err(EnvError::Poisoned)));
    assert!(matches!(env.reset_done(&[1]), Err(EnvError::Poisoned)));
    let reset = env.reset_all()?;
    assert!(!env.is_poisoned());
    assert!(env.last_failures().is_empty());
    assert!(
        reset
            .info
            .iter()
            .all(|i| i.gameplay_frames == 0 && i.seed.episode == 1)
    );
    Ok(())
}

#[test]
fn explicit_evaluation_exhaustion_does_not_mutate_or_generate_training_seeds() -> crate::Result<()>
{
    let mut env = VecDodgeEnv::new(EnvConfig {
        raw_frame_cap: 1,
        ..evaluation_config(vec![vec![0xB0000000], vec![0xB0000001, 9]])
    })?;
    assert!(env.episode_info().iter().all(|i| i.seed.evaluation));
    env.step(&[0, 0])?;
    let old = canonical(&env);
    assert!(matches!(
        env.reset_done(&[1, 0]),
        Err(EnvError::SeedExhausted {
            slot: 0,
            episode: 1
        })
    ));
    assert_eq!(canonical(&env), old);
    assert!(!env.is_poisoned());
    Ok(())
}

#[test]
fn thread_and_chunk_trajectory_invariance_uses_logical_state_not_native_equality()
-> crate::Result<()> {
    let config = EnvConfig {
        batch_size: 5,
        raw_frame_cap: 16,
        auxiliary_targets: true,
        ..EnvConfig::default()
    };
    let mut a = VecDodgeEnv::new(EnvConfig {
        num_threads: 1,
        chunk_size: 1,
        ..config.clone()
    })?;
    let mut b = VecDodgeEnv::new(EnvConfig {
        num_threads: 3,
        chunk_size: 2,
        ..config
    })?;
    for episode in 0..3 {
        assert_eq!(a.observations()?, b.observations()?);
        assert_eq!(canonical(&a), canonical(&b));
        for step in 0..4 {
            let actions: Vec<i64> = (0..5).map(|i| (i + step + episode) % 9).collect();
            assert_eq!(a.step(&actions)?, b.step(&actions)?);
            assert_eq!(canonical(&a), canonical(&b));
        }
        assert_eq!(a.reset_all()?, b.reset_all()?);
    }
    Ok(())
}

struct Expected {
    policy: &'static str,
    seed: u32,
    score: i32,
    frames: u32,
    alive: u32,
    dead: bool,
    cap: bool,
    full_state_hash: u64,
}
include!("../tests/support/m0_expected.rs");

/// Validation-only expensive work: exact frozen policy in both full and batch
/// paths, per-raw-frame full logical-state comparison, retained original M0
/// totals and final full-path fingerprint. No production snapshots are used.
#[test]
#[ignore = "bounded release replay only after parent long-campaign lease ends"]
fn frozen_m0_ten_paired_episodes_per_policy() -> crate::Result<()> {
    use m0_policy::{Policy, PolicyKind};
    use std::collections::VecDeque;
    use std::sync::{Arc, Mutex};
    use std::time::{Duration, Instant};
    let start = Instant::now();
    let deadline = Duration::from_secs(120);
    let mut total_frames = 0_u64;
    let mut active_patterns = std::collections::BTreeMap::<u8, u64>::new();
    for kind in PolicyKind::ALL {
        for expected in EXPECTED.iter().filter(|e| e.policy == kind.name()) {
            assert!(
                start.elapsed() < deadline,
                "120-second replay deadline reached; no retry"
            );
            let mut full = NativeGame::new(NativeConfig::new(expected.seed));
            let mut frame = full.advance_frame(dodge_core::BUTTON_X_MASK)?;
            for _ in 0..12 {
                frame = full.advance_frame(0)?;
            }
            assert_eq!(full.lifecycle().mode, dodge_core::Mode::Game);
            let mut full_policy = Policy::new(kind, expected.seed);
            full_policy.observe(frame.snapshot.logical_state());
            let vector_policy = Arc::new(Mutex::new(Policy::new(kind, expected.seed)));
            let mut env = VecDodgeEnv::new(evaluation_config(vec![vec![expected.seed]]))?;
            vector_policy
                .lock()
                .unwrap()
                .observe(env.test_game(0).snapshot().logical_state());
            let raw_states = Arc::new(Mutex::new(VecDeque::<dodge_core::FullState>::new()));
            let observer_states = Arc::clone(&raw_states);
            let observer_policy = Arc::clone(&vector_policy);
            env.test_observer(
                0,
                Box::new(move |game| {
                    let snapshot = game.snapshot();
                    let actual = snapshot.logical_state();
                    let mut expected = observer_states.lock().unwrap().pop_front().unwrap();
                    // Headless intentionally keeps its old physical framebuffer.
                    // All other fields, including RNG/input/particles, must match.
                    expected.physical_screen = actual.physical_screen.clone();
                    assert_eq!(
                        &expected, actual,
                        "raw full/headless logical-state mismatch"
                    );
                    observer_policy.lock().unwrap().observe(actual);
                }),
            );
            let mut frames = 0;
            let mut alive = 0;
            let mut score_sum = 0_i64;
            let mut death_events = 0;
            let mut last;
            loop {
                assert!(
                    start.elapsed() < deadline,
                    "120-second replay deadline reached; no retry"
                );
                let full_action = full_policy.action(frame.snapshot.logical_state());
                let action = vector_policy
                    .lock()
                    .unwrap()
                    .action(env.test_game(0).snapshot().logical_state());
                assert_eq!(full_action, action, "frozen policy diverged");
                let id = ActionIndex::of(action);
                let before = full.score().raw();
                let before_alive = alive;
                let before_frames = frames;
                for _ in 0..4 {
                    frame = full.advance_frame(action.mask())?;
                    frames += 1;
                    alive += u32::from(!frame.dead);
                    death_events += frame
                        .events
                        .iter()
                        .filter(|e| **e == dodge_core::FrameEvent::Death)
                        .count();
                    full_policy.observe(frame.snapshot.logical_state());
                    let snapshot = full.snapshot();
                    let state = snapshot.logical_state();
                    raw_states.lock().unwrap().push_back(state.clone());
                    if let Some(p) = state.active_pattern.and_then(|i| state.patterns.get(i)) {
                        *active_patterns.entry(p.id).or_default() += 1;
                    }
                    if frame.dead || frames == 18000 {
                        break;
                    }
                }
                let result = env.step(&[id])?;
                assert!(raw_states.lock().unwrap().is_empty());
                let score_delta = i64::from(full.score().raw()) - i64::from(before);
                score_sum += score_delta;
                assert_eq!(result.score_delta_raw_fixed[0], score_delta);
                assert_eq!(result.elapsed_raw_frames[0], frames - before_frames);
                assert_eq!(result.alive_raw_frames[0], alive - before_alive);
                let reward = score_delta as f64 / 65536.0 + f64::from(alive - before_alive) / 100.0
                    - if frame.dead { 5.0 } else { 0.0 };
                assert!(
                    (f64::from(result.rewards[0]) - reward).abs() <= 1e-5,
                    "only f32 step reward uses a tolerance"
                );
                last = result.info[0].clone();
                if last.terminated || last.truncated {
                    break;
                }
            }
            assert_eq!(
                (
                    last.score_raw_fixed,
                    frames,
                    alive,
                    last.terminated,
                    last.truncated
                ),
                (
                    expected.score,
                    expected.frames,
                    expected.alive,
                    expected.dead,
                    expected.cap
                )
            );
            assert_eq!(last.score_delta_sum_raw_fixed, score_sum);
            assert_eq!(score_sum, i64::from(expected.score));
            assert_eq!(
                full.snapshot().state_hash(),
                expected.full_state_hash,
                "retained original full-path state fingerprint"
            );
            assert_eq!(
                last.objective_return,
                expected.score as f64 / 65536.0 + f64::from(expected.alive) / 100.0
                    - if expected.dead { 5.0 } else { 0.0 }
            );
            total_frames += u64::from(frames);
            println!(
                "REPLAY_EPISODE {{\"policy\":\"{}\",\"seed\":{},\"score_raw_fixed\":{},\"raw_frames\":{},\"alive_frames\":{},\"terminated\":{},\"truncated\":{},\"death_events\":{},\"full_state_hash\":{},\"objective_return\":{}}}",
                kind.name(),
                expected.seed,
                last.score_raw_fixed,
                frames,
                alive,
                last.terminated,
                last.truncated,
                death_events,
                expected.full_state_hash,
                last.objective_return
            );
        }
    }
    println!(
        "REPLAY_TOTAL {{\"episodes\":30,\"raw_frames_per_path\":{},\"elapsed_seconds\":{},\"catalog_ids_seen\":{}}}",
        total_frames,
        start.elapsed().as_secs_f64(),
        active_patterns.len()
    );
    println!("REPLAY_PATTERN_FRAMES {:?}", active_patterns);
    Ok(())
}

struct ActionIndex;
impl ActionIndex {
    fn of(action: dodge_core::Action) -> i64 {
        dodge_core::Action::ALL
            .iter()
            .position(|a| *a == action)
            .unwrap() as i64
    }
}

#[test]
fn renderer_entity_differences_stay_inside_current_conservative_footprints() -> crate::Result<()> {
    use crate::geometry::{enemy_footprint, powerup_footprint};
    let env = VecDodgeEnv::new(EnvConfig::default())?;
    let game = env.test_game(0);
    let mut base = [0; 16384];
    game.render_into(&mut base);
    for (personality, x, y, size) in [
        (0, -2, 10, 4),
        (1, 126, 20, 4),
        (-1, 127, 30, 0),
        (-1, 127, 40, -4),
        (2, 131, 127, 1),
        (3, -4, 50, 4),
        (4, 10, -4, 4),
    ] {
        let entity = enemy(personality, x, y, size);
        let changed = NativeGame::restore(&wire_fixture::with_enemies(game, &[entity])?)?;
        let mut pixels = [0; 16384];
        changed.render_into(&mut pixels);
        let footprint = if personality >= 2 {
            powerup_footprint(q(x).raw(), q(y).raw())
        } else {
            enemy_footprint(q(x).raw(), q(y).raw(), q(size).raw())
        };
        let mut differences = 0;
        for (i, (&a, &b)) in base.iter().zip(&pixels).enumerate() {
            if a != b {
                differences += 1;
                let x = (i % 128) as i64;
                let y = (i / 128) as i64;
                assert!(
                    x >= footprint.min_x
                        && x <= footprint.max_x
                        && y >= footprint.min_y
                        && y <= footprint.max_y,
                    "{personality} {x} {y} {footprint:?}"
                );
            }
        }
        assert!(
            differences > 0,
            "single-entity boundary fixture drew no changed pixel: {personality} {x} {y} {size}"
        );
    }
    Ok(())
}

#[test]
fn renderer_rectangles_and_gated_warning_footprints_match_boundary_fixtures() -> crate::Result<()> {
    use crate::geometry::rectangle_footprint;
    let env = VecDodgeEnv::new(EnvConfig::default())?;
    let game = env.test_game(0);
    let mut base = [0; 16384];
    game.render_into(&mut base);
    for r in [
        rect(-5, 20, 10, 10, q(2)),
        rect(130, 30, -6, 10, q(2)),
        rect(10, -2, 20, 4, q(1)),
        rect(127, 60, 1, 1, q(2)),
    ] {
        let mut pattern = game.patterns()[0].clone();
        pattern.pattern_type = 0;
        pattern.rects = vec![r.clone()];
        pattern.timer = PicoFixed::ZERO;
        let fixture = NativeGame::restore(&wire_fixture::with_pattern(game, pattern)?)?;
        let mut pixels = [0; 16384];
        fixture.render_into(&mut pixels);
        let f = rectangle_footprint(r.x.raw(), r.y.raw(), r.width.raw(), r.height.raw());
        let mut changes = 0;
        for (i, (&a, &b)) in base.iter().zip(&pixels).enumerate() {
            if a != b {
                changes += 1;
                let x = (i % 128) as i64;
                let y = (i / 128) as i64;
                assert!(x >= f.min_x && x <= f.max_x && y >= f.min_y && y <= f.max_y);
            }
        }
        assert!(changes > 0);
    }
    let mut r = rect(-50, -50, 0, 0, q(1));
    r.warnings = vec![WarningLine {
        x0: q(10),
        y0: q(20),
        x1: q(30),
        y1: q(20),
    }];
    let mut pattern = game.patterns()[0].clone();
    pattern.pattern_type = 0;
    pattern.timer = q(10);
    pattern.rects = vec![r];
    let hidden = NativeGame::restore(&wire_fixture::with_pattern(game, pattern.clone())?)?;
    assert_eq!(hidden.drawn_warning_lines().count(), 0);
    pattern.rects[0].sh = q(2);
    let shown = NativeGame::restore(&wire_fixture::with_pattern(game, pattern.clone())?)?;
    assert_eq!(shown.drawn_warning_lines().count(), 1);
    pattern.timer = q(125);
    let late = NativeGame::restore(&wire_fixture::with_pattern(game, pattern)?)?;
    assert_eq!(late.drawn_warning_lines().count(), 0);
    Ok(())
}

#[test]
fn actual_rectangle_overflow_after_raw_mutation_poisons_batch() -> crate::Result<()> {
    let mut env = VecDodgeEnv::new(EnvConfig {
        batch_size: 2,
        num_threads: 2,
        chunk_size: 1,
        ..EnvConfig::default()
    })?;
    let mut pattern = env.test_game(0).patterns()[0].clone();
    pattern.pattern_type = 0;
    pattern.rects = vec![rect(10, 10, 10, 10, q(1)); 17];
    // Installing overflow state retains its raw game and error; this explicit
    // validation seam clears geometry history, never recovers a production run.
    let snapshot = wire_fixture::with_pattern(env.test_game(0), pattern)?;
    assert!(matches!(
        env.test_restore(0, &snapshot),
        Err(EnvError::RectangleOverflow(17))
    ));
    assert!(matches!(env.step(&[0, 0]), Err(EnvError::BatchFailure(_))));
    assert!(env.is_poisoned());
    assert!(env.last_failures()[0].1.contains("RectangleOverflow(17)"));
    assert!(env.episode_info().iter().all(|i| i.gameplay_frames == 4));
    env.reset_all()?;
    assert!(!env.is_poisoned());
    Ok(())
}

#[test]
fn real_native_growth_features_use_last_executed_raw_frame() -> crate::Result<()> {
    use std::sync::{Arc, Mutex};
    let mut env = VecDodgeEnv::new(EnvConfig::default())?;
    let mut growing = enemy(0, 10, 10, 1);
    growing.max_size = q(6);
    growing.isizing = true;
    let snapshot = wire_fixture::with_enemies(env.test_game(0), &[growing])?;
    env.test_restore(0, &snapshot)?;
    let seen = Arc::new(Mutex::new(Vec::new()));
    let captured = Arc::clone(&seen);
    env.test_observer(
        0,
        Box::new(move |g| {
            let e = g.enemies()[0];
            captured
                .lock()
                .unwrap()
                .push(crate::geometry::enemy_box(e.x.raw(), e.y.raw(), e.size.raw()).measures());
        }),
    );
    let result = env.step(&[0])?;
    let frames = seen.lock().unwrap();
    assert_eq!(frames.len(), 4);
    let a = frames[2];
    let b = frames[3];
    let expected = [
        b.center_x_twice_raw - a.center_x_twice_raw,
        b.center_y_twice_raw - a.center_y_twice_raw,
        b.half_x_twice_raw - a.half_x_twice_raw,
        b.half_y_twice_raw - a.half_y_twice_raw,
    ]
    .map(|d| (d as f64 / (2.0 * 65536.0 * 4.0)) as f32);
    assert_eq!(&result.observations.entity_feats[6..10], &expected);
    assert!(expected[2] > 0.0);
    Ok(())
}
