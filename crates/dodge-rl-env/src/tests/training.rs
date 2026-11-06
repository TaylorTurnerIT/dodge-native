use dodge_core::{PicoFixed, TrainingOptions};

use crate::{EnvConfig, EnvError, TrainingConfig, VecDodgeEnv};

fn config(training: TrainingConfig) -> EnvConfig {
    EnvConfig {
        batch_size: 2,
        raw_frame_cap: 100_000,
        training,
        ..EnvConfig::default()
    }
}

#[test]
fn default_training_is_the_cartridge() {
    assert_eq!(EnvConfig::default().training, TrainingConfig::default());
    assert_eq!(
        TrainingConfig::default().options(),
        TrainingOptions::CARTRIDGE
    );
}

#[test]
fn spawn_rate_converts_like_the_batch_binding() {
    for percent in [50, 75, 100, 133, 150] {
        let training = TrainingConfig {
            spawn_rate_percent: percent,
            ..TrainingConfig::default()
        };
        assert_eq!(
            training.options().spawn_rate,
            PicoFixed::from_f32(percent as f32 / 100.0)
        );
    }
}

#[test]
fn spawn_rate_outside_50_to_150_is_refused() {
    for (percent, ok) in [
        (49, false),
        (50, true),
        (150, true),
        (151, false),
        (0, false),
    ] {
        let mut config = config(TrainingConfig {
            spawn_rate_percent: percent,
            ..TrainingConfig::default()
        });
        config.batch_size = 1;
        let result = config.validate();
        if ok {
            assert_eq!(result, Ok(()), "{percent}");
        } else {
            assert_eq!(
                result,
                Err(EnvError::Config(
                    "spawn_rate_percent must be between 50 and 150"
                )),
                "{percent}"
            );
        }
    }
}

#[test]
fn games_receive_the_training_options() -> Result<(), EnvError> {
    let training = TrainingConfig {
        normal_enemies: false,
        kamikaze_enemies: true,
        spawn_rate_percent: 70,
        lives: 3,
    };
    let env = VecDodgeEnv::new(config(training))?;
    assert_eq!(env.test_game(0).spawn_rate(), training.options().spawn_rate);
    assert_eq!(env.batch_info().config.training, training);
    Ok(())
}

#[test]
fn enemy_toggles_keep_hostile_enemies_out() -> Result<(), EnvError> {
    let training = TrainingConfig {
        normal_enemies: false,
        kamikaze_enemies: false,
        ..TrainingConfig::default()
    };
    let mut env = VecDodgeEnv::new(config(training))?;
    for step in 0..600 {
        let batch = env.step(&[step % 9, (step * 7) % 9])?;
        for slot in 0..2 {
            assert!(
                env.test_game(slot)
                    .enemies()
                    .iter()
                    .all(|enemy| !(-1..=1).contains(&enemy.personality)),
                "slot {slot} step {step}"
            );
        }
        if batch.terminated.iter().any(|t| *t) {
            break;
        }
    }
    Ok(())
}

#[test]
fn a_life_absorbs_a_lethal_contact() -> Result<(), EnvError> {
    let training = TrainingConfig {
        lives: 2,
        ..TrainingConfig::default()
    };
    let mut env = VecDodgeEnv::new(config(training))?;
    let mut absorbed = [false; 2];
    for _ in 0..20_000 {
        let batch = env.step(&[0, 0])?;
        for (slot, seen) in absorbed.iter_mut().enumerate() {
            let spent = env.test_game(slot).telemetry().lives_spent;
            if spent >= 1 && !*seen {
                *seen = true;
                // With two lives, only a third contact can end the episode.
                assert!(!batch.terminated[slot] || spent == 2, "slot {slot}");
            }
        }
        if absorbed.iter().all(|s| *s) || batch.terminated.iter().any(|t| *t) {
            break;
        }
    }
    assert!(
        absorbed.iter().any(|s| *s),
        "no lethal contact was absorbed"
    );
    Ok(())
}
