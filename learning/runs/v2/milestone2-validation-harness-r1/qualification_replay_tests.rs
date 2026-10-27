//! Validation-only template. Parent must integrate and compile after binding
//! source freezes. This file has not been executed in its drafting directory.
use crate::{EnvConfig, SeedMode, VecDodgeEnv};
use dodge_core::{Action, NativeConfig, NativeGame};

#[path = "../tests/support/m0_policy.rs"]
mod m0_policy;

struct Expected {
    seed: u32,
    score: i32,
    frames: u32,
    alive: u32,
    dead: bool,
    cap: bool,
    full_state_hash: u64,
    death_events: usize,
}
include!("../tests/support/qualification_expected.rs");

/// Validation snapshots and frozen heuristic bookkeeping are excluded from
/// production throughput. A queue holds at most K=4 raw states per episode.
#[test]
#[ignore = "parent-owned frozen M2 campaign only; 900-second wall guard"]
fn frozen_m0_full_heuristic_d2_d3() -> crate::Result<()> {
    use m0_policy::{Policy, PolicyKind};
    use std::collections::{BTreeMap, VecDeque};
    use std::sync::{Arc, Mutex};
    use std::time::{Duration, Instant};

    let started = Instant::now();
    assert_eq!(
        PolicyKind::ALL.map(PolicyKind::name),
        ["random", "neutral", "nearest_lethal_aabb_safe_powerup"]
    );
    let deadline = Duration::from_secs(900);
    let mut total_frames = 0_u64;
    for (difficulty, expected_rows) in [(2, EXPECTED_D2.as_slice()), (3, EXPECTED_D3.as_slice())] {
        let mut pattern_frames = BTreeMap::<u8, u64>::new();
        let mut difficulty_frames = 0_u64;
        let mut score_sum = 0_i64;
        let mut alive_sum = 0_u64;
        let mut capped = 0_u32;
        for (episode_index, expected) in expected_rows.iter().enumerate() {
            assert!(started.elapsed() < deadline, "M2 parity deadline; no retry");
            let mut native = NativeConfig::new(expected.seed);
            native.difficulty = difficulty;
            native.patterns_enabled = true;
            native.powerups_enabled = true;
            let mut full = NativeGame::new(native);
            let mut frame = full.advance_frame(dodge_core::BUTTON_X_MASK)?;
            for _ in 0..12 {
                frame = full.advance_frame(0)?;
            }
            assert_eq!(full.lifecycle().mode, dodge_core::Mode::Game);
            assert!(!frame.dead);
            let mut full_policy = Policy::new(PolicyKind::AabbDodger, expected.seed);
            full_policy.observe(frame.snapshot.logical_state());
            let vector_policy = Arc::new(Mutex::new(Policy::new(
                PolicyKind::AabbDodger,
                expected.seed,
            )));
            let mut env = VecDodgeEnv::new(EnvConfig {
                difficulty,
                seed_mode: SeedMode::Evaluation {
                    seeds_by_slot: vec![vec![expected.seed]],
                },
                ..EnvConfig::default()
            })?;
            vector_policy
                .lock()
                .unwrap()
                .observe(env.test_game(0).snapshot().logical_state());
            let raw_states = Arc::new(Mutex::new(VecDeque::<dodge_core::FullState>::new()));
            let observer_states = Arc::clone(&raw_states);
            let observer_policy = Arc::clone(&vector_policy);
            env.test_observer(
                0,
                Box::new(move |game| {
                    let snapshot = game.snapshot();
                    let actual = snapshot.logical_state();
                    let mut expected = observer_states.lock().unwrap().pop_front().unwrap();
                    expected.physical_screen = actual.physical_screen.clone();
                    assert_eq!(
                        &expected, actual,
                        "per-raw-frame full/headless state mismatch"
                    );
                    observer_policy.lock().unwrap().observe(actual);
                }),
            );
            let mut frames = 0_u32;
            let mut alive = 0_u32;
            let mut fixed_sum = 0_i64;
            let mut death_events = 0;
            let last = loop {
                assert!(started.elapsed() < deadline, "M2 parity deadline; no retry");
                let action = full_policy.action(frame.snapshot.logical_state());
                let vector_action = vector_policy
                    .lock()
                    .unwrap()
                    .action(env.test_game(0).snapshot().logical_state());
                assert_eq!(action, vector_action, "frozen heuristic action diverged");
                let action_id = Action::ALL
                    .iter()
                    .position(|candidate| *candidate == action)
                    .unwrap() as i64;
                let before_score = full.score().raw();
                let before_alive = alive;
                let before_frames = frames;
                for _ in 0..4 {
                    frame = full.advance_frame(action.mask())?;
                    frames += 1;
                    alive += u32::from(!frame.dead);
                    death_events += frame
                        .events
                        .iter()
                        .filter(|event| **event == dodge_core::FrameEvent::Death)
                        .count();
                    full_policy.observe(frame.snapshot.logical_state());
                    let snapshot = full.snapshot();
                    let state = snapshot.logical_state();
                    raw_states.lock().unwrap().push_back(state.clone());
                    if let Some(pattern) = state
                        .active_pattern
                        .and_then(|index| state.patterns.get(index))
                    {
                        *pattern_frames.entry(pattern.id).or_default() += 1;
                    }
                    if frame.dead || frames == 18_000 {
                        break;
                    }
                }
                let result = env.step(&[action_id])?;
                assert!(raw_states.lock().unwrap().is_empty());
                let delta = i64::from(full.score().raw()) - i64::from(before_score);
                fixed_sum += delta;
                assert_eq!(result.score_delta_raw_fixed[0], delta);
                assert_eq!(result.elapsed_raw_frames[0], frames - before_frames);
                assert_eq!(result.alive_raw_frames[0], alive - before_alive);
                let reward = delta as f64 / 65_536.0 + f64::from(alive - before_alive) / 100.0
                    - if frame.dead { 5.0 } else { 0.0 };
                assert!(
                    (f64::from(result.rewards[0]) - reward).abs() <= 1e-5,
                    "f32 reward only uses tolerance"
                );
                let info = result.info[0].clone();
                if info.terminated || info.truncated {
                    break info;
                }
            };
            assert_eq!(
                (
                    last.score_raw_fixed,
                    frames,
                    alive,
                    last.terminated,
                    last.truncated
                ),
                (
                    expected.score,
                    expected.frames,
                    expected.alive,
                    expected.dead,
                    expected.cap
                )
            );
            assert_eq!(last.startup_frames, 13);
            assert_eq!(last.seed.actual_seed, expected.seed);
            assert!(last.seed.evaluation);
            assert_eq!(last.score_delta_sum_raw_fixed, fixed_sum);
            assert_eq!(fixed_sum, i64::from(expected.score));
            assert_eq!(death_events, expected.death_events);
            let full_hash = full.snapshot().state_hash();
            assert_eq!(
                full_hash, expected.full_state_hash,
                "original M0 final fingerprint"
            );
            let objective = f64::from(expected.score) / 65_536.0
                + f64::from(expected.alive) / 100.0
                - if expected.dead { 5.0 } else { 0.0 };
            assert_eq!(last.objective_return, objective);
            assert_eq!(last.bootstrap, !expected.dead);
            difficulty_frames += u64::from(frames);
            alive_sum += u64::from(alive);
            score_sum += i64::from(expected.score);
            capped += u32::from(expected.cap);
            println!(
                "V2_FULL_PARITY_EPISODE {{\"difficulty\":{},\"episode_index\":{},\"seed\":{},\"score_raw_fixed\":{},\"raw_frames\":{},\"alive_frames\":{},\"terminated\":{},\"truncated\":{},\"death_events\":{},\"full_state_hash\":{},\"objective_return\":{}}}",
                difficulty,
                episode_index,
                expected.seed,
                last.score_raw_fixed,
                frames,
                alive,
                last.terminated,
                last.truncated,
                death_events,
                full_hash,
                last.objective_return
            );
        }
        for (id, frames) in &pattern_frames {
            println!(
                "V2_FULL_PARITY_PATTERN {{\"difficulty\":{},\"id\":{},\"frames\":{}}}",
                difficulty, id, frames
            );
        }
        println!(
            "V2_FULL_PARITY_DIFFICULTY {{\"difficulty\":{},\"episodes\":1000,\"raw_frames_per_path\":{},\"alive_frames\":{},\"score_sum_raw_fixed\":{},\"caps\":{},\"pattern_ids\":{}}}",
            difficulty,
            difficulty_frames,
            alive_sum,
            score_sum,
            capped,
            pattern_frames.len()
        );
        total_frames += difficulty_frames;
    }
    println!(
        "V2_FULL_PARITY_TOTAL {{\"episodes\":2000,\"raw_frames_per_path\":{},\"wall_seconds\":{}}}",
        total_frames,
        started.elapsed().as_secs_f64()
    );
    Ok(())
}
