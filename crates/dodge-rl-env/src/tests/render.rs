use dodge_core::FRAMEBUFFER_SIZE;

use crate::{EnvConfig, EnvError, TrainingConfig, VecDodgeEnv};

fn config() -> EnvConfig {
    EnvConfig {
        batch_size: 3,
        raw_frame_cap: 100_000,
        ..EnvConfig::default()
    }
}

#[test]
fn render_returns_each_slots_current_frame() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(config())?;
    for step in 0..30_i64 {
        env.step(&[step % 9, 0, (step / 2) % 9])?;
    }
    let frames = env.render(&[2, 0, 2])?;
    assert_eq!(frames.len(), 3 * FRAMEBUFFER_SIZE);
    for (n, slot) in [2, 0, 2].into_iter().enumerate() {
        let mut expected = [0; FRAMEBUFFER_SIZE];
        env.test_game(slot).render_into(&mut expected);
        assert_eq!(
            frames[n * FRAMEBUFFER_SIZE..(n + 1) * FRAMEBUFFER_SIZE],
            expected
        );
    }
    assert!(frames.iter().all(|v| *v <= 15));
    assert_ne!(
        frames[..FRAMEBUFFER_SIZE],
        frames[FRAMEBUFFER_SIZE..2 * FRAMEBUFFER_SIZE]
    );
    assert!(env.render(&[]).is_ok_and(|v| v.is_empty()));
    assert_eq!(env.render(&[0, 3]).err(), Some(EnvError::SlotIndex(3)));
    Ok(())
}

#[test]
fn rendering_changes_nothing() -> Result<(), EnvError> {
    for pixels in [false, true] {
        let cfg = EnvConfig {
            render_pixels: pixels,
            ..config()
        };
        let mut plain = VecDodgeEnv::new(cfg.clone())?;
        let mut rendered = VecDodgeEnv::new(cfg)?;
        for step in 0..60_i64 {
            let actions = [step % 9, (step / 3) % 9, (step * 5) % 9];
            let a = plain.step(&actions)?;
            rendered.render(&[0, 1, 2])?;
            let b = rendered.step(&actions)?;
            rendered.render(&[1])?;
            assert_eq!(a, b, "pixels {pixels} step {step}");
            for slot in 0..3 {
                assert_eq!(
                    plain.test_game(slot).snapshot(),
                    rendered.test_game(slot).snapshot()
                );
            }
            if a.terminated.iter().chain(&a.truncated).any(|t| *t) {
                break;
            }
        }
        assert_eq!(plain.observations()?, rendered.observations()?);
        assert_eq!(plain.episode_info(), rendered.episode_info());
    }
    Ok(())
}

/// A slot that has died or been truncated still draws, and a dead slot draws
/// its death frame again on every call.
#[test]
fn render_works_after_death_and_after_truncation() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(EnvConfig {
        batch_size: 1,
        ..config()
    })?;
    let mut died = false;
    for step in 0..5_000_i64 {
        if env.step(&[(step / 3) % 9])?.terminated[0] {
            died = true;
            break;
        }
    }
    assert!(died);
    assert!(env.test_game(0).lifecycle().dead);
    let first = env.render(&[0])?;
    let mut expected = [0; FRAMEBUFFER_SIZE];
    env.test_game(0).render_into(&mut expected);
    assert_eq!(first, expected);
    assert!(first.iter().any(|v| *v != 0));
    assert_eq!(env.render(&[0])?, first);
    let before = env.episode_info();
    env.render(&[0])?;
    assert_eq!(env.episode_info(), before);
    // The ended slot can still be reset afterwards.
    env.reset_done(&[0])?;
    assert!(!env.render(&[0])?.is_empty());

    let mut capped = VecDodgeEnv::new(EnvConfig {
        batch_size: 1,
        raw_frame_cap: 4,
        training: TrainingConfig::default(),
        ..EnvConfig::default()
    })?;
    assert!(capped.step(&[0])?.truncated[0]);
    assert_eq!(capped.render(&[0])?.len(), FRAMEBUFFER_SIZE);
    Ok(())
}
