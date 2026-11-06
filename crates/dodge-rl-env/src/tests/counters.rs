use dodge_core::DeathCause;

use crate::{
    EnvConfig, EnvError, LaneCounters, ObservationKind, TrainingConfig, VecDodgeEnv,
    death_cause_code,
};

fn config(observation: ObservationKind, training: TrainingConfig) -> EnvConfig {
    EnvConfig {
        batch_size: 4,
        action_repeat: 2,
        raw_frame_cap: 100_000,
        observation,
        training,
        ..EnvConfig::default()
    }
}

/// Fixed-point values are exact in f64, so the fixture's raw values return.
fn digest(game: &dodge_core::NativeGame) -> u64 {
    let c = LaneCounters::read(game);
    let raw = |value: f64| (value * 65536.0) as i64;
    let text = format!(
        "{} {} {} {} {} {} {} {} {} {} {} {:?} {}",
        raw(c.score),
        raw(c.player_x),
        raw(c.player_y),
        c.dead,
        c.uncontrolled_kills,
        c.survival_frames,
        c.pattern_active,
        c.pattern_id,
        c.death_cause,
        c.death_pattern,
        c.fyou_triggers,
        c.pickups,
        c.lives_spent
    );
    super::source_fixtures::fnv_bytes(text.bytes())
}

#[test]
fn matches_the_source_counters() {
    super::source_fixtures::check(include_str!("fixtures/counters_source.txt"), digest);
}

#[test]
fn death_cause_codes_are_dodgeai_codes() {
    let codes = [
        (None, 0),
        (Some(DeathCause::NormalEnemy), 1),
        (Some(DeathCause::KamikazeEnemy), 2),
        (Some(DeathCause::KamikazeExplosion), 3),
        (Some(DeathCause::StaticPatternRect), 4),
        (Some(DeathCause::MovingPatternRect), 5),
        (Some(DeathCause::Unknown), 0),
    ];
    for (cause, code) in codes {
        assert_eq!(death_cause_code(cause), code, "{cause:?}");
    }
}

#[test]
fn entity_mode_returns_no_counters() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(config(ObservationKind::Entity, TrainingConfig::default()))?;
    assert!(env.step(&[0; 4])?.counters.is_none());
    assert!(env.reset_all()?.counters.is_none());
    Ok(())
}

/// Step and reset counters are each slot's game, read at the end of the call,
/// with rows in observation order.
#[test]
fn counters_follow_the_games() -> Result<(), EnvError> {
    let training = TrainingConfig {
        lives: 1,
        ..TrainingConfig::default()
    };
    let mut env = VecDodgeEnv::new(config(ObservationKind::VelocityFlow, training))?;
    let mut deaths = 0;
    let mut lives_spent = 0;
    for step in 0..3_000_i64 {
        let batch = env.step(&[step % 9, (step / 7) % 9, 0, (step / 2) % 9])?;
        let counters = batch.counters.ok_or(EnvError::Contract("no counters"))?;
        assert_eq!(counters.indices, batch.observations.indices);
        assert_eq!(counters.pickups.len(), 12);
        for slot in 0..4 {
            let row = counters.row(slot).ok_or(EnvError::Contract("no row"))?;
            assert_eq!(row, LaneCounters::read(env.test_game(slot)));
            assert_eq!(row.dead, batch.terminated[slot]);
            assert_eq!(row.dead, row.death_cause != 0, "slot {slot}");
            assert_eq!(row.pattern_active, row.pattern_id >= 0);
            lives_spent += row.lives_spent;
        }
        let ended: Vec<usize> = (0..4).filter(|i| batch.terminated[*i]).rev().collect();
        if !ended.is_empty() {
            deaths += ended.len();
            let reset = env.reset_done(&ended)?;
            let counters = reset.counters.ok_or(EnvError::Contract("no counters"))?;
            assert_eq!(counters.indices, ended);
            for (row, slot) in ended.iter().enumerate() {
                let fresh = counters.row(row).ok_or(EnvError::Contract("no row"))?;
                assert_eq!(fresh, LaneCounters::read(env.test_game(*slot)));
                assert!(!fresh.dead && fresh.death_cause == 0 && fresh.lives_spent == 0);
                assert_eq!(fresh.death_pattern, -1);
            }
        }
    }
    assert!(deaths > 0 && lives_spent > 0);
    Ok(())
}
