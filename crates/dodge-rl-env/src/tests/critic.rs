use crate::{
    CRITIC_FEATURE_COUNT, CRITIC_FEATURE_VERSION, CRITIC_GROUPS, EnvConfig, EnvError,
    ObservationKind, VecDodgeEnv, encode_critic_features,
};

fn config(critic_features: bool) -> EnvConfig {
    EnvConfig {
        batch_size: 4,
        action_repeat: 3,
        raw_frame_cap: 100_000,
        observation: ObservationKind::VelocityFlow,
        critic_features,
        ..EnvConfig::default()
    }
}

fn encode(game: &dodge_core::NativeGame) -> Vec<f32> {
    let mut out = vec![f32::NAN; CRITIC_FEATURE_COUNT];
    encode_critic_features(game, &mut out);
    out
}

#[test]
fn layout_constants() {
    assert_eq!(CRITIC_FEATURE_VERSION, 1);
    assert_eq!(CRITIC_FEATURE_COUNT, 295);
    let names: Vec<_> = CRITIC_GROUPS.iter().map(|g| g.0).collect();
    assert_eq!(
        names,
        [
            "clock",
            "timers",
            "active_pattern",
            "next_pattern",
            "next_enemy",
            "nearest_enemies"
        ]
    );
    assert!(!EnvConfig::default().critic_features);
}

/// Bit parity with the source encoder, previews included, on the games both
/// engines play alike; so the version stays 1.
#[test]
fn matches_the_source_encoder() {
    super::source_fixtures::check(include_str!("fixtures/critic_source.txt"), |game| {
        super::source_fixtures::fnv(&encode(game))
    });
}

#[test]
fn critic_features_need_the_velocity_flow_observation() {
    let entity = EnvConfig {
        observation: ObservationKind::Entity,
        ..config(true)
    };
    assert_eq!(
        entity.validate(),
        Err(EnvError::Config(
            "critic_features needs the velocity_flow observation"
        ))
    );
    assert_eq!(config(true).validate(), Ok(()));
}

/// Critic rows encode each slot's game at the end of the call, and turning
/// them on changes neither the games nor the VelocityFlow rows.
#[test]
fn critic_rows_come_with_the_observation() -> Result<(), EnvError> {
    let mut with = VecDodgeEnv::new(config(true))?;
    let mut without = VecDodgeEnv::new(config(false))?;
    assert!(without.observations()?.critic.is_none());
    let check = |env: &VecDodgeEnv, batch: &crate::ObservationBatch| {
        let rows = batch.critic.as_deref().unwrap_or_default();
        assert_eq!(rows.len(), batch.batch_size() * CRITIC_FEATURE_COUNT);
        for (row, slot) in rows.chunks(CRITIC_FEATURE_COUNT).zip(&batch.indices) {
            assert_eq!(row, encode(env.test_game(*slot)).as_slice(), "slot {slot}");
        }
    };
    check(&with, &with.observations()?);
    let mut resets = 0;
    for step in 0..1_500_i64 {
        let actions = [step % 9, (step / 5) % 9, 0, (step / 2) % 9];
        let a = with.step(&actions)?;
        let b = without.step(&actions)?;
        check(&with, &a.observations);
        assert!(b.observations.critic.is_none());
        assert_eq!(a.observations.velocity_flow, b.observations.velocity_flow);
        assert_eq!(a.counters, b.counters);
        let ended: Vec<usize> = (0..4).filter(|i| a.terminated[*i]).collect();
        if !ended.is_empty() {
            let reset = with.reset_done(&ended)?;
            check(&with, &reset.observations);
            without.reset_done(&ended)?;
            resets += 1;
        }
    }
    assert!(resets > 0);
    Ok(())
}
