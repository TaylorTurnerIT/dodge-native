//! Synthetic CPU fixtures only. No study seed/cohort, checkpoint or Python use.
use super::*;
use crate::tests::wire_fixture;
use crate::{SeedMode, StepBatch};
use dodge_core::{DeathCause, EnemyState, PicoFixed};
use std::sync::{
    Arc,
    atomic::{AtomicUsize, Ordering},
};

fn safe_env(
    batch: usize,
    threads: usize,
    chunk: usize,
    pixels: bool,
) -> crate::Result<VecDodgeEnv> {
    let mut env = VecDodgeEnv::new(EnvConfig {
        batch_size: batch,
        num_threads: threads,
        chunk_size: chunk,
        patterns_enabled: false,
        powerups_enabled: false,
        render_pixels: pixels,
        auxiliary_targets: true,
        // Explicit tiny unit-fixture values, never B/E or study seeds.
        seed_mode: SeedMode::Evaluation {
            seeds_by_slot: (0..batch)
                .map(|i| vec![31 + i as u32, 131 + i as u32, 231 + i as u32])
                .collect(),
        },
        ..EnvConfig::default()
    })?;
    make_safe(&mut env, &(0..batch).collect::<Vec<_>>())?;
    Ok(env)
}

fn make_safe(env: &mut VecDodgeEnv, indices: &[usize]) -> crate::Result<()> {
    for &i in indices {
        let fixture = wire_fixture::without_spawns(env.test_game(i))?;
        env.test_restore(i, &fixture)?;
    }
    Ok(())
}

fn advance(env: &mut VecDodgeEnv, decisions: usize) -> crate::Result<StepBatch> {
    let actions = vec![0; env.slots.len()];
    let mut last = None;
    for _ in 0..decisions {
        last = Some(env.step(&actions)?);
    }
    last.ok_or_else(|| "positive decision count required".into())
}

#[derive(Debug, PartialEq)]
struct State {
    native: Vec<Vec<u8>>,
    info: Vec<EpisodeInfo>,
    observations: Vec<Option<Observation>>,
    pixels: Vec<Option<Vec<u8>>>,
    history_diagnostics: Vec<crate::Diagnostics>,
    history_fields: Vec<String>,
    poisoned: bool,
    failures: Vec<(usize, String)>,
}

fn state(env: &VecDodgeEnv) -> State {
    State {
        native: env
            .slots
            .iter()
            .map(|s| s.game.snapshot().canonical_bytes())
            .collect(),
        info: env.episode_info(),
        observations: env.slots.iter().map(|s| s.observation.clone()).collect(),
        pixels: env.slots.iter().map(|s| s.pixel_stack.clone()).collect(),
        history_diagnostics: env
            .slots
            .iter()
            .map(|s| s.history.cumulative_diagnostics())
            .collect(),
        history_fields: env
            .slots
            .iter()
            .map(|s| format!("{:?}", s.history))
            .collect(),
        poisoned: env.poisoned,
        failures: env.last_failures.clone(),
    }
}

fn rejects_unchanged(env: &mut VecDodgeEnv, indices: &[usize], horizons: &[u32]) -> EnvError {
    let before = state(env);
    let error = env
        .truncate_practice(indices, horizons)
        .err()
        .expect("must reject request");
    assert_eq!(state(env), before, "whole request must be atomic: {error}");
    error
}

#[test]
fn practice_h1000_h2000_preserves_final_buffers_and_one_subset_reset() -> crate::Result<()> {
    let mut env = safe_env(2, 2, 1, true)?;
    let raw = Arc::new(AtomicUsize::new(0));
    let seen = raw.clone();
    env.test_observer(
        0,
        Box::new(move |_| {
            seen.fetch_add(1, Ordering::SeqCst);
        }),
    );
    let final_step = advance(&mut env, 250)?;
    assert_eq!(raw.load(Ordering::SeqCst), 1000);
    assert_eq!(final_step.info[0].gameplay_frames, 1000);
    assert_eq!(final_step.info[0].alive_frames, 1000);
    assert_eq!(final_step.info[0].diagnostics.raw_history_samples, 1001);
    let mut expected = state(&env);
    expected.info[0].truncated = true;
    let returned = env.truncate_practice(&[0], &[1000])?;
    assert_eq!(state(&env), expected);
    assert_eq!(returned, vec![env.episode_info()[0].clone()]);
    assert_eq!(raw.load(Ordering::SeqCst), 1000, "cutoff never simulates");
    assert!(returned[0].bootstrap && !returned[0].terminated);
    assert_eq!(returned[0].death, None);
    assert_eq!(
        returned[0].objective_return,
        final_step.info[0].objective_return
    );
    rejects_unchanged(&mut env, &[0], &[1000]);
    let before_reset = state(&env);
    let reset = env.reset_done(&[0])?;
    assert_eq!(reset.info[0].seed.episode, 1);
    assert_eq!(reset.info[0].gameplay_frames, 0);
    assert_eq!(env.episode_info()[1], before_reset.info[1]);
    assert_eq!(
        env.slots[1].game.snapshot().canonical_bytes(),
        before_reset.native[1]
    );
    assert_eq!(env.slots[1].observation, before_reset.observations[1]);
    assert_eq!(returned[0], expected.info[0], "owned info survives reset");
    assert_eq!(
        final_step.observations,
        ObservationBatch::collect(
            vec![0, 1],
            before_reset
                .observations
                .iter()
                .map(|o| o.as_ref().expect("observation")),
            true,
            true
        )
    );
    assert_eq!(
        final_step.truncated,
        vec![false, false],
        "caller must synchronize retained flags"
    );
    assert_eq!(final_step.elapsed_raw_frames, vec![4, 4]);
    assert_eq!(final_step.alive_raw_frames, vec![4, 4]);
    assert_eq!(final_step.rewards, vec![0.04, 0.04]);
    assert!(matches!(
        env.reset_done(&[0]),
        Err(EnvError::SlotNotEnded(0))
    ));
    make_safe(&mut env, &[0])?;
    let final_step = advance(&mut env, 250)?;
    assert_eq!(
        final_step
            .info
            .iter()
            .map(|i| i.gameplay_frames)
            .collect::<Vec<_>>(),
        vec![1000, 2000]
    );
    assert_eq!(final_step.info[1].diagnostics.raw_history_samples, 2001);
    let info = env.truncate_practice(&[1, 0], &[2000, 1000])?;
    assert_eq!(
        info,
        vec![env.episode_info()[1].clone(), env.episode_info()[0].clone()]
    );
    let reset = env.reset_done(&[1, 0])?;
    assert_eq!(reset.observations.indices, vec![1, 0]);
    assert_eq!(
        reset
            .info
            .iter()
            .map(|i| i.seed.episode)
            .collect::<Vec<_>>(),
        vec![1, 2]
    );
    assert_eq!(
        info.iter().map(|i| i.seed.episode).collect::<Vec<_>>(),
        vec![0, 1]
    );
    Ok(())
}

#[test]
fn practice_all_validation_errors_leave_every_slot_unchanged() -> crate::Result<()> {
    let mut env = safe_env(3, 2, 2, false)?;
    advance(&mut env, 250)?;
    for (indices, horizons) in [
        (vec![0, 1], vec![1000]),
        (vec![0], vec![1000, 1000]),
        (vec![0, 0], vec![1000, 1000]),
        (vec![0, 3], vec![1000, 1000]),
        (vec![0, usize::MAX], vec![1000, 1000]),
        (vec![0, 1], vec![1000, 2000]),
    ] {
        rejects_unchanged(&mut env, &indices, &horizons);
    }
    for horizon in [0, 999, 1001, 1004, 18000, 19000, u32::MAX] {
        rejects_unchanged(&mut env, &[0, 1], &[1000, horizon]);
    }
    let before = state(&env);
    assert!(env.truncate_practice(&[], &[])?.is_empty());
    assert_eq!(state(&env), before);
    // Invalid-counter fixture, never a production frame jump.
    env.slots[1].gameplay_frames = 999;
    assert!(matches!(
        rejects_unchanged(&mut env, &[0, 1], &[1000, 1000]),
        EnvError::PracticeFrame { .. }
    ));
    env.slots[1].gameplay_frames = 1000;
    env.truncate_practice(&[1], &[1000])?;
    assert!(matches!(
        rejects_unchanged(&mut env, &[0, 1], &[1000, 1000]),
        EnvError::SlotEnded(1)
    ));
    Ok(())
}

fn mover_fixture(
    env: &VecDodgeEnv,
    slot: usize,
    fatal_offset: u32,
) -> crate::Result<dodge_core::Snapshot> {
    // Existing deterministic death-test technique: choose a moving-enemy
    // snapshot by bounded raw-frame probe. No production force-death API.
    for dx in 0..40 {
        let enemy = EnemyState {
            size: PicoFixed::from_int(4),
            isizing: false,
            vx: PicoFixed::from_int(-1),
            ..EnemyState::normal(
                PicoFixed::from_int(64 + dx),
                PicoFixed::from_int(64),
                PicoFixed::from_int(4),
            )
        };
        let fixture = wire_fixture::with_enemies(env.test_game(slot), &[enemy])?;
        let mut probe = NativeGame::restore(&fixture)?;
        for frame in 1..=fatal_offset {
            if probe.advance_frame_headless(0)?.dead {
                if frame == fatal_offset {
                    return Ok(fixture);
                }
                break;
            }
        }
    }
    Err(format!("no synthetic mover offset for fatal raw frame {fatal_offset}").into())
}

#[test]
fn practice_death_h_minus_one_h_and_h_plus_one_has_native_precedence() -> crate::Result<()> {
    for horizon in [1000, 2000] {
        for fatal_offset in [3, 4, 5] {
            let mut env = safe_env(1, 1, 1, false)?;
            advance(&mut env, (horizon / 4 - 1) as usize)?;
            let fixture = mover_fixture(&env, 0, fatal_offset)?;
            env.test_restore(0, &fixture)?;
            let mut control = safe_env(1, 1, 1, false)?;
            advance(&mut control, (horizon / 4 - 1) as usize)?;
            control.test_restore(0, &fixture)?;
            let step = env.step(&[0])?;
            assert_eq!(step, control.step(&[0])?);
            if fatal_offset <= 4 {
                assert!(step.terminated[0] && !step.truncated[0]);
                assert_eq!(step.info[0].gameplay_frames, horizon - 4 + fatal_offset);
                assert_eq!(step.info[0].alive_frames, horizon - 5 + fatal_offset);
                let death = step.info[0].death.ok_or("missing cause")?;
                assert_eq!(death.cause, DeathCause::NormalEnemy);
                assert_eq!(death.fatal_gameplay_frame, horizon - 4 + fatal_offset);
                assert_eq!(death.observed_lethal_contacts, [1, 0, 0, 0, 0, 0]);
                assert_eq!(
                    step.rewards[0],
                    (f64::from(fatal_offset - 1) / 100.0 - 5.0) as f32
                );
                assert_eq!(
                    step.info[0].objective_return,
                    f64::from(step.info[0].alive_frames) / 100.0 - 5.0
                );
                assert!(!step.info[0].bootstrap);
                assert!(matches!(
                    rejects_unchanged(&mut env, &[0], &[horizon]),
                    EnvError::SlotEnded(0)
                ));
            } else {
                assert_eq!(step.info[0].gameplay_frames, horizon);
                assert_eq!(step.info[0].alive_frames, horizon);
                let before = state(&env);
                let info = env.truncate_practice(&[0], &[horizon])?;
                assert!(info[0].truncated && info[0].bootstrap && !info[0].terminated);
                assert_eq!(info[0].death, None);
                assert_eq!(state(&env).native, before.native, "never execute fatal H+1");
                assert!(matches!(env.step(&[0]), Err(EnvError::SlotEnded(0))));
                let death = control.step(&[0])?;
                assert_eq!(death.elapsed_raw_frames, vec![1]);
                assert_eq!(
                    death.info[0]
                        .death
                        .ok_or("missing H+1 death")?
                        .fatal_gameplay_frame,
                    horizon + 1
                );
            }
            let ended = env.episode_info()[0].clone();
            let reset = env.reset_done(&[0])?;
            assert_eq!(reset.info[0].seed.episode, ended.seed.episode + 1);
            assert_eq!(reset.info[0].death, None);
        }
    }
    Ok(())
}

#[test]
fn practice_mixed_death_cutoff_continuing_resets_only_ended_once() -> crate::Result<()> {
    let mut env = safe_env(3, 3, 2, false)?;
    advance(&mut env, 249)?;
    let fixture = mover_fixture(&env, 0, 4)?;
    env.test_restore(0, &fixture)?;
    let step = env.step(&[0, 0, 0])?;
    assert_eq!(step.terminated, vec![true, false, false]);
    rejects_unchanged(&mut env, &[1, 0], &[1000, 1000]);
    let mut before = state(&env);
    let info = env.truncate_practice(&[1], &[1000])?;
    before.info[1].truncated = true;
    assert_eq!(state(&env), before);
    assert_eq!(info[0], env.episode_info()[1]);
    let reset = env.reset_done(&[0, 1])?;
    assert_eq!(
        reset
            .info
            .iter()
            .map(|i| i.seed.episode)
            .collect::<Vec<_>>(),
        vec![1, 1]
    );
    let after = state(&env);
    assert_eq!(after.native[2], before.native[2]);
    assert_eq!(after.info[2], before.info[2]);
    assert_eq!(after.observations[2], before.observations[2]);
    assert!(matches!(
        env.reset_done(&[0, 1]),
        Err(EnvError::SlotNotEnded(0))
    ));
    assert_eq!(state(&env), after);
    Ok(())
}

#[test]
fn practice_ordinary_18000_cap_keeps_existing_native_behavior() -> crate::Result<()> {
    let mut env = safe_env(1, 1, 1, false)?;
    let cap = advance(&mut env, 4500)?; // No practice method call at H18000.
    assert_eq!(cap.info[0].gameplay_frames, 18000);
    assert_eq!(cap.info[0].alive_frames, 18000);
    assert_eq!(cap.info[0].diagnostics.raw_history_samples, 18001);
    assert_eq!(cap.info[0].objective_return, 180.0);
    assert_eq!(cap.info[0].death, None);
    assert_eq!(cap.terminated, vec![false]);
    assert_eq!(cap.truncated, vec![true]);
    assert!(cap.info[0].bootstrap);
    assert_eq!(cap.elapsed_raw_frames, vec![4]);
    assert_eq!(cap.rewards, vec![0.04]);
    assert!(matches!(
        rejects_unchanged(&mut env, &[0], &[17000]),
        EnvError::SlotEnded(0)
    ));
    assert_eq!(env.reset_done(&[0])?.info[0].seed.episode, 1);
    Ok(())
}

#[test]
fn practice_fixed_18000_ceiling_and_configured_cap_both_reject() -> crate::Result<()> {
    let mut env = safe_env(2, 2, 1, false)?;
    env.config.raw_frame_cap = 20_000; // Synthetic configuration fixture.
    advance(&mut env, 4500)?;
    assert!(env.episode_info().iter().all(|i| !i.truncated));
    for horizon in [18_000, 19_000] {
        assert!(matches!(
            rejects_unchanged(&mut env, &[0, 1], &[horizon, horizon]),
            EnvError::PracticeHorizon { .. }
        ));
    }
    let mut env = safe_env(2, 2, 1, false)?;
    advance(&mut env, 250)?;
    env.config.raw_frame_cap = 1000; // Cap check independent of ended flags.
    assert!(matches!(
        rejects_unchanged(&mut env, &[0, 1], &[1000, 1000]),
        EnvError::PracticeHorizon { .. }
    ));
    Ok(())
}

#[test]
fn practice_real_undershoot_and_overshoot_are_atomic() -> crate::Result<()> {
    let mut env = safe_env(2, 2, 1, false)?;
    advance(&mut env, 249)?;
    assert_eq!(env.episode_info()[0].gameplay_frames, 996);
    rejects_unchanged(&mut env, &[0, 1], &[1000, 1000]);
    env.step(&[0, 0])?;
    env.step(&[0, 0])?;
    assert_eq!(env.episode_info()[0].gameplay_frames, 1004);
    rejects_unchanged(&mut env, &[0, 1], &[1000, 1000]);
    Ok(())
}

#[test]
fn practice_rejects_k2_k3_and_dead_native_state_without_mutation() -> crate::Result<()> {
    for repeat in [2, 3] {
        let mut env = safe_env(1, 1, 1, false)?;
        env.config.action_repeat = repeat; // Configuration-validation fixture.
        assert!(matches!(
            rejects_unchanged(&mut env, &[0], &[1000]),
            EnvError::Config(_)
        ));
    }
    let mut env = safe_env(1, 1, 1, false)?;
    let fixture = mover_fixture(&env, 0, 1)?;
    env.test_restore(0, &fixture)?;
    env.step(&[0])?;
    env.slots[0].terminated = false; // Test only: inconsistent live wrapper flag.
    assert!(matches!(
        rejects_unchanged(&mut env, &[0], &[1000]),
        EnvError::Contract(_)
    ));
    Ok(())
}

#[test]
fn practice_poison_failure_keeps_partial_state_and_diagnostics() -> crate::Result<()> {
    let mut env = safe_env(3, 2, 1, false)?;
    env.test_inject_error(1, EnvError::RectangleOverflow(17));
    assert!(matches!(
        env.step(&[0, 0, 0]),
        Err(EnvError::BatchFailure(_))
    ));
    assert_eq!(
        env.episode_info()
            .iter()
            .map(|i| i.gameplay_frames)
            .collect::<Vec<_>>(),
        vec![4, 1, 4]
    );
    assert!(env.last_failures()[0].1.contains("RectangleOverflow(17)"));
    assert_eq!(
        rejects_unchanged(&mut env, &[0], &[1000]),
        EnvError::Poisoned
    );
    assert_eq!(rejects_unchanged(&mut env, &[], &[]), EnvError::Poisoned);
    assert!(matches!(env.reset_done(&[0]), Err(EnvError::Poisoned)));
    Ok(())
}

#[test]
fn practice_episode_overflow_rejects_atomically_without_wrapping() -> crate::Result<()> {
    let mut env = safe_env(2, 1, 1, false)?;
    advance(&mut env, 250)?;
    env.slots[1].seed.episode = u64::MAX; // Synthetic overflow fixture only.
    assert_eq!(
        rejects_unchanged(&mut env, &[0, 1], &[1000, 1000]),
        EnvError::CounterExhausted
    );
    // Existing reset overflow behavior remains whole-request prevalidated.
    env.slots[0].truncated = true;
    env.slots[1].truncated = true;
    let before = state(&env);
    assert!(matches!(
        env.reset_done(&[0, 1]),
        Err(EnvError::CounterExhausted)
    ));
    assert_eq!(state(&env), before);
    Ok(())
}

#[test]
fn practice_reset_seed_exhaustion_retains_cutoffs_and_earlier_slots() -> crate::Result<()> {
    let mut env = safe_env(2, 1, 1, false)?;
    advance(&mut env, 250)?;
    if let SeedMode::Evaluation { seeds_by_slot } = &mut env.config.seed_mode {
        seeds_by_slot[1].truncate(1); // Exhaustion fixture, not a seed campaign.
    }
    env.truncate_practice(&[0, 1], &[1000, 1000])?;
    let before = state(&env);
    assert!(matches!(
        env.reset_done(&[0, 1]),
        Err(EnvError::SeedExhausted {
            slot: 1,
            episode: 1
        })
    ));
    assert_eq!(state(&env), before);
    assert!(!env.is_poisoned());
    Ok(())
}

#[test]
fn practice_thread_chunk_layouts_match_before_cutoff_after_reset_and_next_step() -> crate::Result<()>
{
    let mut a = safe_env(5, 1, 1, false)?;
    let mut b = safe_env(5, 3, 2, false)?;
    assert_eq!(advance(&mut a, 250)?, advance(&mut b, 250)?);
    assert_eq!(state(&a), state(&b));
    assert_eq!(
        a.truncate_practice(&[4, 1, 0], &[1000, 1000, 1000])?,
        b.truncate_practice(&[4, 1, 0], &[1000, 1000, 1000])?
    );
    assert_eq!(state(&a), state(&b));
    assert_eq!(a.reset_done(&[0, 1, 4])?, b.reset_done(&[0, 1, 4])?);
    assert_eq!(state(&a), state(&b));
    assert_eq!(a.step(&[0, 1, 2, 3, 4])?, b.step(&[0, 1, 2, 3, 4])?);
    assert_eq!(state(&a), state(&b));
    Ok(())
}
