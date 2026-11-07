//! Resets that start on caller-chosen seeds. Only ended slots can be reset
//! with `reset_done`; `reset_all` resets everything.
use crate::{EnvConfig, EnvError, SeedMode, TrainingConfig, VecDodgeEnv};

/// Four-frame decisions and a 40-frame cap: every slot is truncated on the
/// tenth step, so it can be reset without waiting for a death.
fn short(batch_size: usize) -> EnvConfig {
    EnvConfig {
        batch_size,
        raw_frame_cap: 40,
        ..EnvConfig::default()
    }
}

fn run_to_end(env: &mut VecDodgeEnv) -> Result<(), EnvError> {
    for step in 0..10_i64 {
        env.step(&vec![step % 9; env.episode_info().len()])?;
    }
    Ok(())
}

#[test]
fn a_given_seed_reproduces_a_fresh_evaluation_game() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(short(2))?;
    run_to_end(&mut env)?;
    let reset = env.reset_done_seeded(&[1, 0], Some(&[777, 1234]))?;
    assert_eq!(reset.info[0].seed.actual_seed, 777);
    assert_eq!(reset.info[1].seed.actual_seed, 1234);
    assert!(reset.info.iter().all(|i| i.seed.explicit));
    // Slot 0 got 1234 and slot 1 got 777; a fresh evaluation env with those
    // seeds is the same game at the start and after every step.
    let mut fresh = VecDodgeEnv::new(EnvConfig {
        seed_mode: SeedMode::Evaluation {
            seeds_by_slot: vec![vec![1234], vec![777]],
        },
        ..short(2)
    })?;
    for step in -1..8_i64 {
        if step >= 0 {
            env.step(&[step % 9, (step + 3) % 9])?;
            fresh.step(&[step % 9, (step + 3) % 9])?;
        }
        for slot in 0..2 {
            assert_eq!(
                env.test_game(slot).snapshot(),
                fresh.test_game(slot).snapshot(),
                "slot {slot} step {step}"
            );
        }
    }
    Ok(())
}

#[test]
fn reset_all_takes_seeds_for_live_games_too() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(short(3))?;
    env.step(&[0, 0, 0])?;
    let reset = env.reset_all_seeded(Some(&[5, 6, 7]))?;
    let seeds: Vec<u32> = reset.info.iter().map(|i| i.seed.actual_seed).collect();
    assert_eq!(seeds, [5, 6, 7]);
    for info in &reset.info {
        assert_eq!(info.gameplay_frames, 0);
    }
    Ok(())
}

#[test]
fn live_slots_are_still_refused_and_nothing_changes() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(short(2))?;
    env.step(&[0, 0])?;
    let before = env.episode_info();
    assert_eq!(
        env.reset_done_seeded(&[0], Some(&[9])).err(),
        Some(EnvError::SlotNotEnded(0))
    );
    assert_eq!(env.episode_info(), before);
    Ok(())
}

#[test]
fn bad_seed_requests_change_nothing() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(short(3))?;
    run_to_end(&mut env)?;
    let before = env.episode_info();
    let snapshot = env.test_game(0).snapshot();
    for (indices, seeds, error) in [
        (
            vec![0, 1],
            vec![1],
            EnvError::Config("seeds must have one entry per reset slot"),
        ),
        (
            vec![0],
            vec![1, 2],
            EnvError::Config("seeds must have one entry per reset slot"),
        ),
        (vec![0, 3], vec![1, 2], EnvError::SlotIndex(3)),
        (vec![2, 2], vec![1, 2], EnvError::DuplicateReset(2)),
    ] {
        assert_eq!(
            env.reset_done_seeded(&indices, Some(&seeds)).err(),
            Some(error)
        );
        assert_eq!(env.episode_info(), before);
        assert_eq!(env.test_game(0).snapshot(), snapshot);
    }
    assert_eq!(
        env.reset_all_seeded(Some(&[1, 2])).err(),
        Some(EnvError::Config("seeds must have one entry per reset slot"))
    );
    assert_eq!(env.episode_info(), before);
    Ok(())
}

#[test]
fn seeded_resets_are_refused_while_poisoned() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(short(1))?;
    env.test_inject_error(0, EnvError::Contract("injected"));
    assert!(env.step(&[0]).is_err());
    assert!(env.is_poisoned());
    assert_eq!(
        env.reset_done_seeded(&[0], Some(&[1])).err(),
        Some(EnvError::Poisoned)
    );
    // reset_all recovers, on the given seed.
    let reset = env.reset_all_seeded(Some(&[4]))?;
    assert!(!env.is_poisoned());
    assert_eq!(reset.info[0].seed.actual_seed, 4);
    Ok(())
}

#[test]
fn explicit_seeds_do_not_advance_the_stream() -> Result<(), EnvError> {
    let mut with_explicit = VecDodgeEnv::new(short(1))?;
    let mut plain = VecDodgeEnv::new(short(1))?;
    run_to_end(&mut with_explicit)?;
    run_to_end(&mut plain)?;
    let given = with_explicit.reset_done_seeded(&[0], Some(&[31337]))?;
    assert_eq!(given.info[0].seed.episode, 0);
    run_to_end(&mut with_explicit)?;
    let next = with_explicit.reset_done(&[0])?;
    let expected = plain.reset_done(&[0])?;
    assert_eq!(next.info[0].seed, expected.info[0].seed);
    assert!(!next.info[0].seed.explicit);
    Ok(())
}

#[test]
fn explicit_seeds_do_not_consume_an_evaluation_list() -> Result<(), EnvError> {
    let config = EnvConfig {
        seed_mode: SeedMode::Evaluation {
            seeds_by_slot: vec![vec![10, 20]],
        },
        ..short(1)
    };
    let mut env = VecDodgeEnv::new(config)?;
    run_to_end(&mut env)?;
    env.reset_done_seeded(&[0], Some(&[99]))?;
    run_to_end(&mut env)?;
    // Episode 1 of the list is still there.
    assert_eq!(env.reset_done(&[0])?.info[0].seed.actual_seed, 20);
    Ok(())
}

#[test]
fn any_u32_is_accepted_including_reserved_ranges() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(short(2))?;
    let reset = env.reset_all_seeded(Some(&[0xB000_0000, u32::MAX]))?;
    assert_eq!(reset.info[0].seed.actual_seed, 0xB000_0000);
    assert_eq!(reset.info[1].seed.actual_seed, u32::MAX);
    Ok(())
}

#[test]
fn a_maximal_frame_cap_runs_past_the_default() -> Result<(), EnvError> {
    // No hostile enemies or patterns, so the player cannot die.
    let config = EnvConfig {
        action_repeat: 5,
        raw_frame_cap: u32::MAX,
        patterns_enabled: false,
        training: TrainingConfig {
            normal_enemies: false,
            kamikaze_enemies: false,
            ..TrainingConfig::default()
        },
        ..EnvConfig::default()
    };
    config.validate()?;
    let mut env = VecDodgeEnv::new(config)?;
    for _ in 0..3_700 {
        let batch = env.step(&[0])?;
        assert!(!batch.truncated[0] && !batch.terminated[0]);
    }
    let info = &env.episode_info()[0];
    assert_eq!(info.gameplay_frames, 18_500);
    assert!(!info.truncated);
    // The default cap would have ended it.
    let mut capped = VecDodgeEnv::new(EnvConfig {
        raw_frame_cap: 18_000,
        ..short(1)
    })?;
    assert_eq!(capped.step(&[0])?.truncated, [false]);
    Ok(())
}
