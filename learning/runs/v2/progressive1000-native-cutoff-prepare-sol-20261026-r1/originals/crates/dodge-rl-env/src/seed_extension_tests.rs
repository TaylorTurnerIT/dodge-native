use crate::*;

#[test]
fn known_candidate_is_rejected_before_native_construction() -> crate::Result<()> {
    let original = training_seed(7, 0, 0)?;
    let ranges = vec![(original.actual_seed, original.actual_seed)];
    let expected = training_seed_with_exclusions(7, 0, 0, &ranges)?;
    assert!(expected.counter > original.counter);
    assert_ne!(expected.actual_seed, original.actual_seed);
    let mut env = VecDodgeEnv::new(EnvConfig {
        seed_mode: SeedMode::Training { run_seed: 7 },
        excluded_seed_ranges: ranges.clone(),
        ..EnvConfig::default()
    })?;
    assert_eq!(env.episode_info()[0].seed, expected);
    assert_eq!(
        env.batch_info().effective_excluded_seed_ranges,
        normalize_seed_exclusions(&ranges)?
    );
    let before = env.observations()?;
    let mut reference = VecDodgeEnv::new(EnvConfig {
        seed_mode: SeedMode::Evaluation {
            seeds_by_slot: vec![vec![expected.actual_seed]],
        },
        ..EnvConfig::default()
    })?;
    assert_eq!(before, reference.observations()?);
    assert_eq!(
        env.step(&[0])?.observations,
        reference.step(&[0])?.observations
    );
    Ok(())
}

#[test]
fn default_seed_identity_offsets_and_reset_continuity() -> crate::Result<()> {
    let mut default_env = VecDodgeEnv::new(EnvConfig::default())?;
    assert_eq!(default_env.episode_info()[0].seed, training_seed(0, 0, 0)?);
    assert_eq!(
        default_env.reset_all()?.info[0].seed,
        training_seed(0, 0, 1)?
    );
    let mut env = VecDodgeEnv::new(EnvConfig {
        batch_size: 2,
        initial_episode_indices: Some(vec![9, 27]),
        ..EnvConfig::default()
    })?;
    assert_eq!(env.episode_info()[0].seed, training_seed(0, 0, 9)?);
    assert_eq!(env.episode_info()[1].seed, training_seed(0, 1, 27)?);
    assert_eq!(env.batch_info().initial_episode_indices, [9, 27]);
    let info = env.reset_all()?.info;
    assert_eq!(info[0].seed, training_seed(0, 0, 10)?);
    assert_eq!(info[1].seed, training_seed(0, 1, 28)?);
    Ok(())
}

#[test]
fn invalid_reservations_indices_and_counter_overflow_fail_before_mutation() -> crate::Result<()> {
    for config in [
        EnvConfig {
            excluded_seed_ranges: vec![(2, 1)],
            ..EnvConfig::default()
        },
        EnvConfig {
            excluded_seed_ranges: vec![(0, u32::MAX)],
            ..EnvConfig::default()
        },
        EnvConfig {
            initial_episode_indices: Some(vec![0, 0]),
            ..EnvConfig::default()
        },
    ] {
        assert!(VecDodgeEnv::new(config).is_err());
    }
    let mut env = VecDodgeEnv::new(EnvConfig {
        batch_size: 2,
        initial_episode_indices: Some(vec![0, u64::MAX]),
        ..EnvConfig::default()
    })?;
    let before = env.episode_info();
    assert_eq!(env.reset_all(), Err(EnvError::CounterExhausted));
    assert_eq!(env.episode_info(), before);
    assert!(!env.is_poisoned());
    Ok(())
}

#[test]
fn evaluation_offsets_do_not_reject_reserved_seeds_or_fall_back() -> crate::Result<()> {
    let mut env = VecDodgeEnv::new(EnvConfig {
        seed_mode: SeedMode::Evaluation {
            seeds_by_slot: vec![vec![1, 0xD000_0000, 0xB000_0000]],
        },
        excluded_seed_ranges: vec![(0xD000_0000, 0xD000_007F)],
        initial_episode_indices: Some(vec![1]),
        ..EnvConfig::default()
    })?;
    assert_eq!(env.episode_info()[0].seed.actual_seed, 0xD000_0000);
    assert_eq!(env.reset_all()?.info[0].seed.actual_seed, 0xB000_0000);
    let before = env.episode_info();
    assert!(matches!(
        env.reset_all(),
        Err(EnvError::SeedExhausted { .. })
    ));
    assert_eq!(env.episode_info(), before);
    Ok(())
}

#[test]
fn reservations_offsets_and_explicit_resets_are_thread_chunk_invariant() -> crate::Result<()> {
    let config = EnvConfig {
        batch_size: 7,
        raw_frame_cap: 19,
        render_pixels: true,
        auxiliary_targets: true,
        initial_episode_indices: Some(vec![1, 2, 3, 4, 5, 6, 7]),
        excluded_seed_ranges: vec![(0xD000_0000, 0xD000_007F), (0xE000_0000, 0xE000_03E7)],
        ..EnvConfig::default()
    };
    let mut a = VecDodgeEnv::new(EnvConfig {
        chunk_size: 1,
        ..config.clone()
    })?;
    let mut b = VecDodgeEnv::new(EnvConfig {
        num_threads: 4,
        chunk_size: 3,
        ..config
    })?;
    for _ in 0..3 {
        assert_eq!(a.observations()?, b.observations()?);
        for _ in 0..5 {
            assert_eq!(
                a.step(&[0, 1, 2, 3, 4, 5, 6])?,
                b.step(&[0, 1, 2, 3, 4, 5, 6])?
            );
        }
        assert_eq!(
            a.reset_done(&[6, 2, 0, 1, 3, 4, 5])?,
            b.reset_done(&[6, 2, 0, 1, 3, 4, 5])?
        );
    }
    Ok(())
}
