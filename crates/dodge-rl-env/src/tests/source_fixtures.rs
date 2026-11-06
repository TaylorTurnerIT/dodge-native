//! Replays the scenarios the source fixtures were generated from and checks
//! each listed frame against them. The source game is started with X held for
//! 13 frames, this one with X tapped; both reach the same first gameplay
//! frame. Fixtures stop where the two games diverge, since upstream's game is
//! the reference.
use dodge_core::{
    Action, BUTTON_X_MASK, Mode, NativeConfig, NativeGame, PicoFixed, TrainingOptions,
};

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
pub(super) fn fnv_bytes(bytes: impl IntoIterator<Item = u8>) -> u64 {
    let mut hash = 0xcbf2_9ce4_8422_2325_u64;
    for byte in bytes {
        hash ^= u64::from(byte);
        hash = hash.wrapping_mul(0x0100_0000_01b3);
    }
    hash
}

/// FNV-1a over the little-endian bits of every value.
pub(super) fn fnv(values: &[f32]) -> u64 {
    fnv_bytes(values.iter().flat_map(|v| v.to_bits().to_le_bytes()))
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
    for frame in 0..13 {
        let mask = if frame == 0 { BUTTON_X_MASK } else { 0 };
        assert!(game.advance_frame_headless(mask).is_ok());
    }
    assert_eq!(game.lifecycle().mode, Mode::Game);
    game
}

/// Check every fixture line, `scenario frame hash`, against `digest`.
pub(super) fn check(fixture: &str, digest: impl Fn(&NativeGame) -> u64) {
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
