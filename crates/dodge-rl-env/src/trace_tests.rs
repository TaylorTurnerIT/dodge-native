//! The gameplay trace is observation-only: on or off, the env is identical.
use crate::*;

fn env(trace: bool, repeat: u8, seeds: Vec<u32>) -> crate::Result<VecDodgeEnv> {
    Ok(VecDodgeEnv::new(EnvConfig {
        batch_size: 1,
        action_repeat: repeat,
        seed_mode: SeedMode::Evaluation {
            seeds_by_slot: vec![seeds],
        },
        trace,
        ..EnvConfig::default()
    })?)
}

fn action_for(step: usize) -> i64 {
    // Mostly camp, with bursts of movement, so fyou, patterns and deaths occur.
    if (step / 40).is_multiple_of(3) {
        i64::try_from((step * 7) % 9).unwrap_or(0)
    } else {
        0
    }
}

#[test]
fn trace_on_off_gives_identical_steps_and_matching_frames() -> crate::Result<()> {
    for repeat in [1_u8, 4] {
        for seed in [0xD000_0003_u32, 0xD000_0017, 0xD000_0042] {
            let mut off = env(false, repeat, vec![seed])?;
            let mut on = env(true, repeat, vec![seed])?;
            assert_eq!(off.observations()?, on.observations()?);
            for step in 0..6_000 {
                let a = off.step(&[action_for(step)])?;
                let mut b = on.step(&[action_for(step)])?;
                let trace = b
                    .info
                    .iter_mut()
                    .map(|i| i.trace.take())
                    .collect::<Vec<_>>();
                assert!(a.info.iter().all(|i| i.trace.is_none()));
                assert_eq!(a, b, "repeat {repeat} seed {seed} step {step}");
                let ended = a.terminated[0] || a.truncated[0];
                // Live episodes report no trace (it is only built when ended).
                assert_eq!(trace.first().is_some_and(Option::is_some), ended);
                if ended {
                    let trace = trace
                        .first()
                        .cloned()
                        .flatten()
                        .ok_or("ended without trace")?;
                    let info = &a.info[0];
                    assert_eq!(trace.frames, info.gameplay_frames);
                    if let Some(death) = info.death {
                        let context = trace.death.ok_or("terminated without death context")?;
                        assert_eq!(context.frame, death.fatal_gameplay_frame);
                        assert_eq!(context.cause, death.cause);
                    } else {
                        assert!(trace.death.is_none());
                    }
                    break;
                }
            }
        }
    }
    Ok(())
}
