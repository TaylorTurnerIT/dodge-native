//! Source-level death-cause telemetry tests for the Rust wrapper.
use crate::features::History;
use crate::*;
use dodge_core::{DeathCause, EnemyState, FrameEvent, NativeGame, PatternRect, PicoFixed};

use crate::tests::wire_fixture;

fn q(n: i32) -> PicoFixed {
    PicoFixed::from_int(n)
}

fn enemy(personality: i8, x: i32, y: i32) -> EnemyState {
    EnemyState {
        personality,
        size: q(4),
        isizing: false,
        ..EnemyState::normal(q(x), q(y), q(4))
    }
}

fn rect_pattern(env: &VecDodgeEnv, pattern_type: u8, sh: i32) -> dodge_core::PatternState {
    let mut pattern = env.test_game(0).patterns()[0].clone();
    pattern.pattern_type = pattern_type;
    pattern.rects = vec![PatternRect {
        x: q(56),
        y: q(56),
        width: q(16),
        height: q(16),
        speed: PicoFixed::ZERO,
        dx: PicoFixed::ZERO,
        dy: PicoFixed::ZERO,
        targets: vec![],
        target_index: 0,
        wait: PicoFixed::ZERO,
        shown: true,
        sh: q(sh),
        warnings: vec![],
        collision_done: false,
        finished: false,
    }];
    pattern
}

fn env(cap: u32) -> crate::Result<VecDodgeEnv> {
    Ok(VecDodgeEnv::new(EnvConfig {
        raw_frame_cap: cap,
        ..EnvConfig::default()
    })?)
}

fn die_with(env: &mut VecDodgeEnv, fixture: &dodge_core::Snapshot) -> crate::Result<StepBatch> {
    env.test_restore(0, fixture)?;
    Ok(env.step(&[0])?)
}

#[test]
fn every_cause_reaches_episode_info_with_first_dead_frame() -> crate::Result<()> {
    let cases: [(&str, DeathCause, [u16; 6]); 5] = [
        ("normal", DeathCause::NormalEnemy, [1, 0, 0, 0, 0, 0]),
        ("kamikaze", DeathCause::KamikazeEnemy, [0, 1, 0, 0, 0, 0]),
        (
            "explosion",
            DeathCause::KamikazeExplosion,
            [0, 0, 1, 0, 0, 0],
        ),
        ("static", DeathCause::StaticPatternRect, [0, 0, 0, 1, 0, 0]),
        ("moving", DeathCause::MovingPatternRect, [0, 0, 0, 0, 1, 0]),
    ];
    for (name, cause, contacts) in cases {
        let mut env = env(10)?;
        let fixture = match name {
            "normal" => wire_fixture::with_enemies(env.test_game(0), &[enemy(0, 64, 64)])?,
            "kamikaze" => wire_fixture::with_enemies(env.test_game(0), &[enemy(1, 64, 64)])?,
            "explosion" => wire_fixture::with_enemies(env.test_game(0), &[enemy(-1, 64, 64)])?,
            "static" => wire_fixture::with_pattern(env.test_game(0), rect_pattern(&env, 0, 2))?,
            _ => wire_fixture::with_pattern(env.test_game(0), rect_pattern(&env, 1, 0))?,
        };
        let step = die_with(&mut env, &fixture)?;
        let death = step.info[0].death.ok_or(name)?;
        assert_eq!(death.cause, cause, "{name}");
        assert_eq!(death.observed_lethal_contacts, contacts, "{name}");
        assert_eq!(death.fatal_gameplay_frame, step.info[0].gameplay_frames);
        assert_eq!(step.terminated, vec![true]);
        assert_eq!(step.alive_raw_frames, vec![0]);
        assert_eq!(step.rewards, vec![-5.0]);
        // Persisted through later reads of the ended slot.
        assert_eq!(env.episode_info()[0].death, step.info[0].death);
    }
    Ok(())
}

#[test]
fn fatal_frame_is_the_gameplay_frame_of_k4_early_termination() -> crate::Result<()> {
    // Find a start offset where a moving enemy first touches on raw frame 3.
    let mut chosen = None;
    for dx in 0..40 {
        let env = env(100)?;
        let mut mover = enemy(0, 64 + dx, 64);
        mover.vx = q(-1);
        let fixture = wire_fixture::with_enemies(env.test_game(0), &[mover])?;
        let mut probe = NativeGame::restore(&fixture)?;
        for frame in 1..=4 {
            if probe.advance_frame_headless(0)?.dead {
                if frame == 3 {
                    chosen = Some(fixture);
                }
                break;
            }
        }
        if chosen.is_some() {
            break;
        }
    }
    let fixture = chosen.ok_or("no offset kills on raw frame 3")?;
    let mut env = env(100)?;
    let before = env.step(&[0])?;
    assert_eq!(before.info[0].death, None);
    assert_eq!(before.info[0].gameplay_frames, 4);
    env.test_restore(0, &fixture)?;
    let step = env.step(&[0])?;
    assert_eq!(
        step.elapsed_raw_frames,
        vec![3],
        "K4 stopped on the death frame"
    );
    assert_eq!(step.alive_raw_frames, vec![2]);
    let death = step.info[0].death.ok_or("missing death")?;
    assert_eq!(death.fatal_gameplay_frame, 7);
    assert_eq!(death.fatal_gameplay_frame, step.info[0].gameplay_frames);
    assert_eq!(death.cause, DeathCause::NormalEnemy);
    assert_eq!(step.rewards, vec![0.02 - 5.0]);
    Ok(())
}

#[test]
fn same_frame_contacts_keep_first_cause_with_one_termination_penalty() -> crate::Result<()> {
    for (enemies, first, contacts) in [
        (
            vec![enemy(0, 64, 64), enemy(1, 64, 64), enemy(-1, 64, 64)],
            DeathCause::NormalEnemy,
            [1, 1, 1, 0, 0, 0],
        ),
        (
            vec![enemy(-1, 64, 64), enemy(0, 64, 64), enemy(0, 63, 64)],
            DeathCause::KamikazeExplosion,
            [2, 0, 1, 0, 0, 0],
        ),
    ] {
        let mut env = env(10)?;
        let fixture = wire_fixture::with_enemies(env.test_game(0), &enemies)?;
        let mut legacy = NativeGame::restore(&fixture)?;
        let events = legacy.advance_frame(0)?.events;
        let step = die_with(&mut env, &fixture)?;
        let death = step.info[0].death.ok_or("missing death")?;
        assert_eq!(death.cause, first);
        assert_eq!(death.observed_lethal_contacts, contacts);
        // Contact counts equal the legacy repeated Death events exactly.
        assert_eq!(
            events.iter().filter(|e| **e == FrameEvent::Death).count(),
            usize::from(contacts.iter().sum::<u16>())
        );
        assert_eq!(step.terminated, vec![true]);
        assert_eq!(step.rewards, vec![-5.0]);
        assert_eq!(step.info[0].objective_return, -5.0);
        assert_eq!(step.info[0].alive_frames, step.info[0].gameplay_frames - 1);
    }
    Ok(())
}

#[test]
fn live_cap_truncated_and_reset_episodes_have_no_cause() -> crate::Result<()> {
    let mut env = env(5)?;
    assert_eq!(env.episode_info()[0].death, None);
    let live = env.step(&[2])?;
    assert_eq!(live.info[0].death, None);
    let capped = env.step(&[2])?;
    assert_eq!(capped.truncated, vec![true]);
    assert_eq!(capped.terminated, vec![false]);
    assert_eq!(capped.info[0].death, None);

    let mut env = self::env(10)?;
    let fixture = wire_fixture::with_enemies(env.test_game(0), &[enemy(0, 64, 64)])?;
    assert!(die_with(&mut env, &fixture)?.info[0].death.is_some());
    let reset = env.reset_done(&[0])?;
    assert_eq!(reset.info[0].death, None);
    assert_eq!(env.episode_info()[0].death, None);
    // A restore of an already-dead state is `Unknown`, never a stale cause.
    env.test_restore(0, &fixture)?;
    assert_eq!(
        env.episode_info()[0].death,
        None,
        "alive restore has no cause"
    );
    let dead_bytes = {
        let mut game = NativeGame::restore(&fixture)?;
        assert!(game.advance_frame_headless(0)?.dead);
        game.snapshot()
    };
    env.test_restore(0, &dead_bytes)?;
    let unknown = env.episode_info()[0].death.ok_or("restored dead")?;
    assert_eq!(unknown.cause, DeathCause::Unknown);
    assert_eq!(unknown.observed_lethal_contacts, [0; 6]);
    Ok(())
}

#[test]
fn diagnostic_cause_never_changes_neural_tensors() -> crate::Result<()> {
    let env = env(10)?;
    let fixture =
        wire_fixture::with_enemies(env.test_game(0), &[enemy(0, 64, 64), enemy(1, 64, 64)])?;
    let mut dead = NativeGame::restore(&fixture)?;
    assert!(dead.advance_frame_headless(0)?.dead);
    assert_eq!(
        dead.death_diagnostic().cause(),
        Some(DeathCause::NormalEnemy)
    );
    let restored = NativeGame::restore(&dead.snapshot())?;
    assert_eq!(
        restored.death_diagnostic().cause(),
        Some(DeathCause::Unknown)
    );
    let tensors = |game: &NativeGame| -> crate::Result<ObservationBatch> {
        let mut history = History::default();
        history.observe_raw(game.privileged_view(), game.enemy_serials())?;
        let observation = history.observation(game.privileged_view(), std::iter::empty(), true)?;
        Ok(ObservationBatch::collect(
            vec![0],
            [&observation].into_iter(),
            false,
            true,
        ))
    };
    let (a, b) = (tensors(&dead)?, tensors(&restored)?);
    assert_eq!(a, b);
    assert_eq!(a.global_feats.len(), GLOBAL_DIM);
    assert_eq!(a.entity_feats.len(), ENTITY_SLOTS * ENTITY_DIM);
    Ok(())
}
