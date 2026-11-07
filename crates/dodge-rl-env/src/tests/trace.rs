//! The gameplay trace against the source binding. `source_fixtures::check`
//! starts games with the trace off, so this file replays the same scenarios
//! (same list, same actions, same startup) with it on. Games are compared on the
//! frames where the source game and this one are identical.
use dodge_core::{
    Action, BUTTON_X_MASK, Mode, NativeConfig, NativeGame, PicoFixed, TrainingOptions,
};
use std::fmt::Write as _;

use crate::{EnvConfig, EnvError, SampleView, TraceView, VecDodgeEnv, trace_view::latest_sample};

#[derive(Clone, Copy)]
struct Scenario {
    seed: u32,
    difficulty: u8,
    patterns: bool,
    powerups: bool,
    normal: bool,
    kamikaze: bool,
    spawn_percent: u32,
    lives: u8,
}

const fn plain(seed: u32) -> Scenario {
    Scenario {
        seed,
        difficulty: 2,
        patterns: true,
        powerups: true,
        normal: true,
        kamikaze: true,
        spawn_percent: 100,
        lives: 0,
    }
}

fn scenarios() -> Vec<Scenario> {
    let mut out: Vec<Scenario> = (1..=10).map(plain).collect();
    out.push(Scenario {
        difficulty: 1,
        ..plain(11)
    });
    out.push(Scenario {
        difficulty: 3,
        ..plain(12)
    });
    out.push(Scenario {
        patterns: false,
        ..plain(13)
    });
    out.push(Scenario {
        powerups: false,
        ..plain(14)
    });
    out.push(Scenario {
        normal: false,
        kamikaze: false,
        ..plain(15)
    });
    out.push(Scenario {
        normal: false,
        ..plain(16)
    });
    out.push(Scenario {
        spawn_percent: 60,
        lives: 3,
        ..plain(17)
    });
    out.push(Scenario {
        spawn_percent: 150,
        lives: 1,
        ..plain(18)
    });
    out.push(Scenario {
        difficulty: 3,
        spawn_percent: 140,
        ..plain(1_000_003)
    });
    out.push(Scenario {
        difficulty: 1,
        kamikaze: false,
        ..plain(2_000_007)
    });
    // Long games: lives keep them going through many patterns.
    out.push(Scenario {
        lives: 40,
        ..plain(21)
    });
    out.push(Scenario {
        lives: 40,
        difficulty: 3,
        ..plain(22)
    });
    out.push(Scenario {
        lives: 40,
        spawn_percent: 50,
        ..plain(23)
    });
    out.push(Scenario {
        lives: 40,
        powerups: false,
        ..plain(24)
    });
    out
}

/// Held for six frames at a time, from an LCG seeded by the scenario seed.
fn action_index(seed: u32, frame: u32) -> usize {
    let lcg = |state: u64| {
        state
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407)
    };
    let mut state = u64::from(seed) | 1;
    let decision = frame / 6;
    for _ in 0..=(decision % 64) {
        state = lcg(state);
    }
    state ^= u64::from(decision).wrapping_mul(0x9E37_79B9_7F4A_7C15);
    ((lcg(state) >> 33) % 9) as usize
}

/// FNV-1a over bytes.
fn fnv_bytes(bytes: impl IntoIterator<Item = u8>) -> u64 {
    let mut hash = 0xcbf2_9ce4_8422_2325_u64;
    for byte in bytes {
        hash ^= u64::from(byte);
        hash = hash.wrapping_mul(0x0100_0000_01b3);
    }
    hash
}

fn started(s: Scenario) -> NativeGame {
    let mut config = NativeConfig::new(s.seed);
    config.difficulty = s.difficulty;
    config.patterns_enabled = s.patterns;
    config.powerups_enabled = s.powerups;
    config.training = TrainingOptions {
        normal_enemies: s.normal,
        kamikaze_enemies: s.kamikaze,
        spawn_rate: PicoFixed::from_f32(s.spawn_percent as f32 / 100.0),
        lives: s.lives,
    };
    let mut game = NativeGame::new(config);
    game.set_trace_enabled(true);
    for frame in 0..13 {
        let mask = if frame == 0 { BUTTON_X_MASK } else { 0 };
        assert!(game.advance_frame_headless(mask).is_ok());
    }
    assert_eq!(game.lifecycle().mode, Mode::Game);
    game
}

/// Check every fixture line, `scenario frame hash`, against `digest`.
fn check(fixture: &str, digest: impl Fn(&NativeGame) -> u64) {
    let mut expected: Vec<Vec<(u32, u64)>> = vec![Vec::new(); scenarios().len()];
    for line in fixture.lines().filter(|l| !l.starts_with('#')) {
        let fields: Vec<&str> = line.split_whitespace().collect();
        let [scenario, frame, hash] = fields.as_slice() else {
            unreachable!("bad fixture line {line}");
        };
        let parsed = (
            scenario.parse::<usize>(),
            frame.parse::<u32>(),
            u64::from_str_radix(hash, 16),
        );
        let (Ok(scenario), Ok(frame), Ok(hash)) = parsed else {
            unreachable!("bad fixture line {line}");
        };
        let Some(frames) = expected.get_mut(scenario) else {
            unreachable!("unknown scenario in {line}");
        };
        frames.push((frame, hash));
    }
    let mut checked = 0;
    for (index, (scenario, frames)) in scenarios().into_iter().zip(&expected).enumerate() {
        let mut game = started(scenario);
        let mut frame = 0;
        for &(target, hash) in frames {
            while frame < target {
                let action = Action::ALL[action_index(scenario.seed, frame)];
                assert!(game.advance_frame_headless(action.mask()).is_ok());
                frame += 1;
            }
            assert_eq!(
                digest(&game),
                hash,
                "scenario {index} seed {} frame {frame}",
                scenario.seed
            );
            checked += 1;
        }
    }
    assert!(checked > 1000, "only {checked} fixture rows");
}

fn raw(value: f64) -> i64 {
    (value * 65536.0).round() as i64
}

fn raw_opt(value: Option<f64>) -> String {
    value.map_or_else(|| "-".to_string(), |v| raw(v).to_string())
}

fn on<T: std::fmt::Display>(value: Option<T>) -> String {
    value.map_or_else(|| "-".to_string(), |v| v.to_string())
}

fn join<T: std::fmt::Display>(values: impl IntoIterator<Item = T>) -> String {
    values
        .into_iter()
        .map(|v| v.to_string())
        .collect::<Vec<_>>()
        .join(",")
}

fn rects(list: &[(f64, f64, f64, f64, u8)]) -> String {
    list.iter()
        .map(|r| {
            format!(
                "{},{},{},{},{}",
                raw(r.0),
                raw(r.1),
                raw(r.2),
                raw(r.3),
                r.4
            )
        })
        .collect::<Vec<_>>()
        .join(";")
}

fn sample_text(sample: Option<&SampleView>) -> String {
    match sample {
        None => "S-".to_string(),
        Some(s) => format!(
            "S {} {} {} {} {} {} {} {} {} {}",
            s.frame,
            raw(s.x),
            raw(s.y),
            raw(s.vx),
            raw(s.vy),
            raw_opt(s.lethal_rect_gap),
            raw_opt(s.pending_rect_gap),
            raw_opt(s.enemy_gap),
            s.enemies,
            on(s.pattern_id)
        ),
    }
}

/// The layout the source fixture generator used for `trace_dict`'s values.
fn trace_text(trace: &TraceView) -> String {
    let mut t = format!("T {} F{}", trace.frame, trace.fyou_triggers.len());
    for f in &trace.fyou_triggers {
        let _ = write!(t, " {}:{}", f.frame, f.spawned);
    }
    let _ = write!(t, " P{}", trace.patterns.len());
    for s in &trace.patterns {
        let _ = write!(
            t,
            " [{} {} {} {} {} x:{} y:{} r:{}]",
            s.id,
            s.pattern_type,
            s.start,
            on(s.end),
            on(s.rects_frame),
            join(s.x.iter().map(|v| raw(*v))),
            join(s.y.iter().map(|v| raw(*v))),
            rects(&s.rects)
        );
    }
    match &trace.death {
        None => t.push_str(" D-"),
        Some(d) => {
            let _ = write!(t, " D {} {}", d.cause, d.frame);
            match &d.killer {
                None => t.push_str(" K-"),
                Some(k) => {
                    let _ = write!(
                        t,
                        " K {} {} {} {} {} {}",
                        k.personality,
                        raw(k.x),
                        raw(k.y),
                        raw(k.size),
                        on(k.fyou_spawned),
                        on(k.age)
                    );
                }
            }
            let p = &d.player;
            let _ = write!(
                t,
                " alive {} pl {} {} {} {} {}",
                join(d.enemies_alive.iter()),
                raw(p.x),
                raw(p.y),
                raw(p.vx),
                raw(p.vy),
                raw(p.size)
            );
            match &d.active_pattern {
                None => t.push_str(" A-"),
                Some(a) => {
                    let _ = write!(t, " A {} {} {} {}", a.id, a.pattern_type, a.start, a.since);
                }
            }
            let path: Vec<String> = d
                .killer_path
                .iter()
                .map(|(b, x, y)| format!("{b},{},{}", raw(*x), raw(*y)))
                .collect();
            let r = &d.recent;
            let _ = write!(
                t,
                " r:{} kp:{} rec f:{} x:{} y:{} vx:{} vy:{} lg:{} pg:{} eg:{} en:{} pid:{}",
                rects(&d.rects),
                path.join(";"),
                join(r.frame.iter()),
                join(r.x.iter().map(|v| raw(*v))),
                join(r.y.iter().map(|v| raw(*v))),
                join(r.vx.iter().map(|v| raw(*v))),
                join(r.vy.iter().map(|v| raw(*v))),
                join(r.lethal_rect_gap.iter().map(|v| raw_opt(*v))),
                join(r.pending_rect_gap.iter().map(|v| raw_opt(*v))),
                join(r.enemy_gap.iter().map(|v| raw_opt(*v))),
                join(r.enemies.iter()),
                join(r.pattern_id.iter().map(|v| on(*v)))
            );
        }
    }
    let _ = write!(t, " C {}", join(trace.contacts.iter()));
    t
}

fn digest(game: &NativeGame) -> u64 {
    let Some(trace) = TraceView::read(game) else {
        unreachable!("trace is on");
    };
    let sample = latest_sample(game);
    fnv_bytes(format!("{} | {}", trace_text(&trace), sample_text(sample.as_ref())).bytes())
}

#[test]
fn matches_the_source_trace_and_sample() {
    check(include_str!("fixtures/trace_source.txt"), digest);
}

fn env_config(trace: bool) -> EnvConfig {
    EnvConfig {
        batch_size: 2,
        raw_frame_cap: 40,
        trace,
        ..EnvConfig::default()
    }
}

#[test]
fn the_trace_is_off_by_default() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(env_config(false))?;
    env.step(&[0, 0])?;
    assert_eq!(env.slot_trace(0)?, None);
    assert_eq!(env.slot_sample(1)?, None);
    assert_eq!(env.slot_trace(2).err(), Some(EnvError::SlotIndex(2)));
    assert_eq!(env.slot_sample(2).err(), Some(EnvError::SlotIndex(2)));
    Ok(())
}

#[test]
fn recording_a_trace_changes_nothing_in_the_game() -> Result<(), EnvError> {
    let mut plain = VecDodgeEnv::new(env_config(false))?;
    let mut traced = VecDodgeEnv::new(env_config(true))?;
    assert_eq!(traced.slot_sample(0)?, None, "no gameplay frame yet");
    for step in 0..9_i64 {
        let actions = [step % 9, (step + 4) % 9];
        let a = plain.step(&actions)?;
        let b = traced.step(&actions)?;
        assert_eq!(a, b, "step {step}");
        for slot in 0..2 {
            assert_eq!(
                plain.test_game(slot).snapshot(),
                traced.test_game(slot).snapshot()
            );
        }
        let sample = traced.slot_sample(0)?;
        assert_eq!(sample.map(|s| s.frame), Some(4 * (step as u32 + 1)));
        assert!(
            traced
                .slot_trace(1)?
                .is_some_and(|t| t.frame == 4 * (step as u32 + 1))
        );
    }
    Ok(())
}

#[test]
fn set_trace_enabled_takes_effect_on_the_next_reset() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(env_config(false))?;
    env.set_trace_enabled(true);
    assert_eq!(env.slot_trace(0)?, None, "the running game is unchanged");
    for _ in 0..10 {
        env.step(&[0, 0])?;
    }
    env.reset_done(&[1])?;
    assert!(env.slot_trace(1)?.is_some());
    assert_eq!(env.slot_trace(0)?, None);
    env.reset_all()?;
    assert!(env.slot_trace(0)?.is_some());
    env.set_trace_enabled(false);
    env.reset_all()?;
    assert_eq!(env.slot_trace(0)?, None);
    assert_eq!(env.slot_sample(0)?, None);
    Ok(())
}

#[test]
fn a_death_leaves_its_context_in_the_trace() -> Result<(), EnvError> {
    let mut env = VecDodgeEnv::new(EnvConfig {
        raw_frame_cap: 100_000,
        trace: true,
        ..EnvConfig::default()
    })?;
    for step in 0..5_000_i64 {
        if env.step(&[(step / 3) % 9])?.terminated[0] {
            break;
        }
    }
    let Some(trace) = env.slot_trace(0)? else {
        unreachable!("trace is on");
    };
    let Some(death) = trace.death else {
        unreachable!("the game ended in a death");
    };
    assert_eq!(death.frame, trace.frame);
    assert!(!death.recent.frame.is_empty());
    assert_eq!(death.recent.frame.len(), death.recent.x.len());
    assert!(trace.contacts.iter().any(|c| *c > 0));
    Ok(())
}
