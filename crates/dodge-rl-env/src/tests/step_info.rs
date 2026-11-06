use crate::{EnvConfig, EnvError, ObservationKind, StepInfo, VecDodgeEnv};

fn config(step_info: StepInfo, observation: ObservationKind) -> EnvConfig {
    EnvConfig {
        batch_size: 5,
        action_repeat: 4,
        raw_frame_cap: 300,
        observation,
        step_info,
        ..EnvConfig::default()
    }
}

#[test]
fn default_reports_every_slot() {
    assert_eq!(EnvConfig::default().step_info, StepInfo::All);
}

/// Every mode plays the same games and returns the same arrays; `Ended`
/// reports exactly the ended slots' info, and `None` reports none.
#[test]
fn step_info_selects_which_slots_report() -> Result<(), EnvError> {
    for observation in [ObservationKind::Entity, ObservationKind::VelocityFlow] {
        let mut all = VecDodgeEnv::new(config(StepInfo::All, observation))?;
        let mut ended = VecDodgeEnv::new(config(StepInfo::Ended, observation))?;
        let mut none = VecDodgeEnv::new(config(StepInfo::None, observation))?;
        let mut reported = 0;
        for step in 0..400_i64 {
            let actions: Vec<i64> = (0..5).map(|slot| (step / (slot + 1)) % 9).collect();
            let a = all.step(&actions)?;
            let e = ended.step(&actions)?;
            let n = none.step(&actions)?;
            assert_eq!(a.info.len(), 5);
            assert!(a.info_indices.is_none());
            let finished: Vec<usize> = (0..5)
                .filter(|i| a.terminated[*i] || a.truncated[*i])
                .collect();
            assert_eq!(e.info_indices.as_deref(), Some(finished.as_slice()));
            let expected: Vec<_> = finished.iter().map(|i| a.info[*i].clone()).collect();
            assert_eq!(e.info, expected);
            assert!(n.info.is_empty());
            assert_eq!(n.info_indices.as_deref(), Some(&[][..]));
            reported += e.info.len();
            for other in [&e, &n] {
                assert_eq!(other.rewards, a.rewards);
                assert_eq!(other.terminated, a.terminated);
                assert_eq!(other.truncated, a.truncated);
                assert_eq!(other.elapsed_raw_frames, a.elapsed_raw_frames);
                assert_eq!(other.observations, a.observations);
                assert_eq!(other.counters, a.counters);
            }
            assert_eq!(ended.episode_info(), all.episode_info());
            if !finished.is_empty() {
                all.reset_done(&finished)?;
                ended.reset_done(&finished)?;
                none.reset_done(&finished)?;
            }
        }
        assert!(reported > 5, "{observation:?}: {reported} ended slots");
    }
    Ok(())
}
