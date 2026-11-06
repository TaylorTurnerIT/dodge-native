use crate::{EnvConfig, EnvError, VecDodgeEnv};

fn config(action_repeat: u8) -> EnvConfig {
    EnvConfig {
        batch_size: 3,
        action_repeat,
        raw_frame_cap: 100_000,
        ..EnvConfig::default()
    }
}

#[test]
fn action_repeat_is_one_to_five() {
    for repeat in 0..=7 {
        let result = config(repeat).validate();
        if (1..=5).contains(&repeat) {
            assert_eq!(result, Ok(()), "{repeat}");
        } else {
            assert_eq!(
                result,
                Err(EnvError::Config("action_repeat must be 1..=5")),
                "{repeat}"
            );
        }
    }
}

#[test]
fn single_frame_decisions_work_in_entity_mode() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(config(1))?;
    for step in 0..300_i64 {
        let batch = env.step(&[step % 9, (step / 3) % 9, 0])?;
        assert_eq!(batch.observations.batch_size(), 3);
        for (slot, elapsed) in batch.elapsed_raw_frames.iter().enumerate() {
            assert_eq!(*elapsed, 1, "slot {slot}");
        }
        if batch.terminated.iter().any(|t| *t) {
            break;
        }
    }
    Ok(())
}

/// Motion history is sampled per raw frame, so how the frames are grouped into
/// decisions changes neither the game nor the entity observation. Games are
/// compared by snapshot: enemy identity namespaces differ between instances.
#[test]
fn grouping_frames_into_decisions_changes_nothing() -> Result<(), EnvError> {
    let mut single = VecDodgeEnv::new(config(1))?;
    let mut grouped = VecDodgeEnv::new(config(4))?;
    for step in 0..150_i64 {
        let actions = [step % 9, (step / 5) % 9, (step * 7) % 9];
        let mut last = None;
        for _ in 0..4 {
            let batch = single.step(&actions)?;
            let ended = batch.terminated.iter().chain(&batch.truncated).any(|t| *t);
            last = Some(batch);
            if ended {
                break;
            }
        }
        let batch = grouped.step(&actions)?;
        let last = last.ok_or(EnvError::Contract("no single-frame step"))?;
        assert_eq!(batch.terminated, last.terminated, "step {step}");
        if batch.terminated.iter().any(|t| *t) {
            break;
        }
        assert_eq!(batch.observations, last.observations, "step {step}");
        for slot in 0..3 {
            assert_eq!(
                single.test_game(slot).snapshot(),
                grouped.test_game(slot).snapshot(),
                "step {step}"
            );
        }
    }
    Ok(())
}
