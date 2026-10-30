//! Pre-headless M0 measurements. See docs/m0-baseline.md for the frozen recipe.

#[path = "m0/benchmark.rs"]
mod benchmark;
#[path = "m0/policy.rs"]
mod policy;
#[path = "m0/report.rs"]
mod report;

use dodge_core::{BUTTON_X_MASK, FrameEvent, Mode, NativeConfig, NativeGame, PicoFixed, Snapshot};
use policy::{Policy, PolicyKind};
use report::Json as J;
use std::{
    collections::{BTreeMap, BTreeSet},
    error::Error,
    fs::{self, OpenOptions},
    io::{BufWriter, Write},
    path::PathBuf,
    time::Instant,
};

type Result<T> = std::result::Result<T, Box<dyn Error + Send + Sync>>;
const BASE_HEAD: &str = "d7ad95127ad7529c5217a51ae9dc5cfedd3f2365";
const SEED_BASE: u32 = 0xB000_0000;
const ENEMY_CAP: usize = 64;
const RECT_CAP: usize = 16;

#[derive(Debug)]
struct Options {
    episodes: u32,
    max_frames: u32,
    action_repeat: u32,
    output_dir: PathBuf,
    benchmark_seconds: Option<u32>,
    threads: Option<usize>,
}

impl Options {
    fn parse(args: impl IntoIterator<Item = String>) -> Result<Self> {
        let mut value = Self {
            episodes: 1000,
            max_frames: 18_000,
            action_repeat: 4,
            output_dir: PathBuf::new(),
            benchmark_seconds: None,
            threads: None,
        };
        let mut seen = BTreeSet::new();
        let mut args = args.into_iter();
        while let Some(arg) = args.next() {
            if !seen.insert(arg.clone()) {
                return Err(format!("duplicate argument: {arg}").into());
            }
            let next = args
                .next()
                .ok_or_else(|| format!("missing value for {arg}"))?;
            match arg.as_str() {
                "--episodes" => value.episodes = next.parse()?,
                "--max-frames" => value.max_frames = next.parse()?,
                "--action-repeat" => value.action_repeat = next.parse()?,
                "--output-dir" => value.output_dir = next.into(),
                "--benchmark-seconds" => value.benchmark_seconds = Some(next.parse()?),
                "--threads" => value.threads = Some(next.parse()?),
                _ => return Err(format!("unknown argument: {arg}").into()),
            }
        }
        if !(1..=1000).contains(&value.episodes)
            || !(1..=18_000).contains(&value.max_frames)
            || !(2..=4).contains(&value.action_repeat)
            || value.output_dir.as_os_str().is_empty()
            || value
                .benchmark_seconds
                .is_some_and(|n| !(1..=50).contains(&n))
            || (value.threads.is_some() && value.benchmark_seconds.is_none())
            || (value.benchmark_seconds.is_some()
                && (seen.contains("--episodes") || seen.contains("--max-frames")))
        {
            return Err("require --output-dir NEW_DIR; episodes 1..1000, max-frames 1..18000, repeat 2..4; benchmark-seconds 1..50 is a separate mode".into());
        }
        Ok(value)
    }
}

/// A new instance for every episode; never reset or press retry.
fn start_game(seed: u32) -> Result<(NativeGame, Snapshot, u64)> {
    let config = NativeConfig {
        difficulty: 2,
        patterns_enabled: true,
        powerups_enabled: true,
        theme_background: 12,
        theme_shadow: 1,
        highscores: [PicoFixed::ZERO; 12],
        ..NativeConfig::new(seed)
    };
    let mut game = NativeGame::new(config);
    let mut frame = game.advance_frame(BUTTON_X_MASK)?;
    let mut startup_frames = 1;
    while game.lifecycle().mode != Mode::Game {
        if startup_frames >= 120 {
            return Err("startup did not reach Mode::Game within 120 raw frames".into());
        }
        frame = game.advance_frame(0)?;
        startup_frames += 1;
    }
    if game.lifecycle().dead || game.score() != PicoFixed::ZERO {
        return Err("fresh startup was dead or had nonzero score; no retry performed".into());
    }
    Ok((game, frame.snapshot, startup_frames))
}

#[derive(Default, Debug)]
struct Totals {
    raw_frames: u64,
    alive_frames: u64,
    decisions: u64,
    score_delta_raw: i64,
    native_reward_raw: i64,
    events: [u64; 5],
    dead: bool,
}

impl Totals {
    fn record(&mut self, score_delta_raw: i64, reward_raw: i64, dead: bool, events: &[FrameEvent]) {
        self.raw_frames += 1;
        self.alive_frames += u64::from(!dead);
        self.score_delta_raw += score_delta_raw;
        self.native_reward_raw += reward_raw;
        self.dead = dead;
        for event in events {
            let index = match event {
                FrameEvent::EnemySpawn => 0,
                FrameEvent::Collision => 1,
                FrameEvent::Death => 2,
                FrameEvent::PatternActive => 3,
                FrameEvent::Terminal => 4,
            };
            if let Some(count) = self.events.get_mut(index) {
                *count += 1;
            }
        }
    }

    fn objective_return(&self) -> f64 {
        self.score_delta_raw as f64 / 65_536.0 + 0.01 * self.alive_frames as f64
            - if self.dead { 5.0 } else { 0.0 }
    }

    fn truncated(&self, cap: u32) -> bool {
        !self.dead && self.raw_frames == u64::from(cap)
    }
}

struct RawTally {
    score_delta_raw: i64,
    reward_raw: i64,
    dead: bool,
    events: Vec<FrameEvent>,
}

/// Shared by the native loop and synthetic boundary tests.
fn advance_repeat(
    totals: &mut Totals,
    repeat: u32,
    cap: u32,
    mut advance: impl FnMut() -> Result<RawTally>,
) -> Result<()> {
    if totals.dead || totals.raw_frames >= u64::from(cap) {
        return Ok(());
    }
    totals.decisions += 1;
    for _ in 0..repeat {
        if totals.dead || totals.raw_frames >= u64::from(cap) {
            break;
        }
        let frame = advance()?;
        totals.record(
            frame.score_delta_raw,
            frame.reward_raw,
            frame.dead,
            &frame.events,
        );
    }
    Ok(())
}

#[derive(Default, Debug)]
struct Counts {
    max_enemies: usize,
    max_rects: usize,
    enemy_overflow_frames: u64,
    rect_overflow_frames: u64,
    enemy_excess_records: u64,
    rect_excess_records: u64,
    active_pattern_frames: u64,
    pattern_ids: BTreeSet<u8>,
    pattern_frames: BTreeMap<u8, u64>,
}

impl Counts {
    fn observe(&mut self, state: &dodge_core::FullState, count_frame: bool) {
        let enemies = state.enemies.len();
        // Never inspect or count the inactive catalog.
        let pattern = state
            .active_pattern
            .and_then(|index| state.patterns.get(index));
        let rects = pattern.map_or(0, |p| p.rects.len());
        self.max_enemies = self.max_enemies.max(enemies);
        self.max_rects = self.max_rects.max(rects);
        if count_frame {
            self.enemy_overflow_frames += u64::from(enemies > ENEMY_CAP);
            self.rect_overflow_frames += u64::from(rects > RECT_CAP);
            self.enemy_excess_records += enemies.saturating_sub(ENEMY_CAP) as u64;
            self.rect_excess_records += rects.saturating_sub(RECT_CAP) as u64;
        }
        if let Some(pattern) = pattern {
            self.pattern_ids.insert(pattern.id);
            if count_frame {
                self.active_pattern_frames += 1;
                *self.pattern_frames.entry(pattern.id).or_default() += 1;
            }
        }
    }

    fn json(&self) -> J {
        J::object(vec![
            (
                "max_active_enemy_family_count",
                J::u(self.max_enemies as u64),
            ),
            ("max_active_pattern_rect_count", J::u(self.max_rects as u64)),
            (
                "enemy_overflow_frames_above_64",
                J::u(self.enemy_overflow_frames),
            ),
            (
                "rect_overflow_frames_above_16",
                J::u(self.rect_overflow_frames),
            ),
            (
                "enemy_excess_record_frames",
                J::u(self.enemy_excess_records),
            ),
            ("rect_excess_record_frames", J::u(self.rect_excess_records)),
            ("active_pattern_frames", J::u(self.active_pattern_frames)),
            (
                "pattern_ids",
                J::array(
                    self.pattern_ids
                        .iter()
                        .map(|&n| J::u(u64::from(n)))
                        .collect(),
                ),
            ),
            (
                "pattern_frames",
                J::array(
                    self.pattern_frames
                        .iter()
                        .map(|(&id, &frames)| {
                            J::object(vec![("id", J::u(u64::from(id))), ("frames", J::u(frames))])
                        })
                        .collect(),
                ),
            ),
        ])
    }
}

struct Episode {
    seed: u32,
    startup_frames: u64,
    totals: Totals,
    counts: Counts,
    final_score: f64,
    native_survival_frames: u32,
    startup_seconds: f64,
    gameplay_seconds: f64,
}

impl Episode {
    fn run(kind: PolicyKind, seed: u32, options: &Options) -> Result<Self> {
        let startup_clock = Instant::now();
        let (mut game, mut snapshot, startup_frames) = start_game(seed)?;
        let startup_seconds = startup_clock.elapsed().as_secs_f64();
        let mut policy = Policy::new(kind, seed);
        policy.observe(snapshot.logical_state());
        let mut counts = Counts::default();
        counts.observe(snapshot.logical_state(), false);
        let mut totals = Totals::default();
        let initial_native_survival = game.survival_frames();
        let mut previous_score = i64::from(game.score().raw());
        let gameplay_clock = Instant::now();
        while totals.raw_frames < u64::from(options.max_frames) && !totals.dead {
            let action = policy.action(snapshot.logical_state());
            advance_repeat(
                &mut totals,
                options.action_repeat,
                options.max_frames,
                || {
                    // NativeGame::step drops intermediate rewards/events. Do not use it.
                    let frame = game.advance_frame(action.mask())?;
                    let score = i64::from(game.score().raw());
                    let tally = RawTally {
                        score_delta_raw: score - previous_score,
                        reward_raw: i64::from(frame.reward.raw()),
                        dead: frame.dead,
                        events: frame.events,
                    };
                    previous_score = score;
                    counts.observe(frame.snapshot.logical_state(), true);
                    policy.observe(frame.snapshot.logical_state());
                    snapshot = frame.snapshot;
                    Ok(tally)
                },
            )?;
        }
        let gameplay_seconds = gameplay_clock.elapsed().as_secs_f64();
        let native_survival_frames = game.survival_frames() - initial_native_survival;
        if u64::from(native_survival_frames) != totals.alive_frames
            || totals.score_delta_raw != i64::from(game.score().raw())
            || !(totals.dead || totals.truncated(options.max_frames))
        {
            return Err("episode accounting invariant failed; partial receipts retained".into());
        }
        Ok(Self {
            seed,
            startup_frames,
            totals,
            counts,
            final_score: game.score().to_double(),
            native_survival_frames,
            startup_seconds,
            gameplay_seconds,
        })
    }

    fn json(&self, kind: PolicyKind, index: u32, cap: u32) -> J {
        J::object(vec![
            ("policy", J::s(kind.name())),
            ("episode_index", J::u(u64::from(index))),
            ("seed", J::u(u64::from(self.seed))),
            (
                "policy_rng_initial_state",
                J::u(policy::PrivateRng::initial_state(self.seed)),
            ),
            ("startup_native_frames_excluded", J::u(self.startup_frames)),
            ("gameplay_native_frames", J::u(self.totals.raw_frames)),
            ("raw_survival_frames", J::u(self.totals.alive_frames)),
            (
                "native_survival_frames_delta",
                J::u(u64::from(self.native_survival_frames)),
            ),
            (
                "survival_seconds_60hz",
                J::f(self.totals.alive_frames as f64 / 60.0),
            ),
            ("decision_steps", J::u(self.totals.decisions)),
            ("final_score", J::f(self.final_score)),
            (
                "score_delta_sum",
                J::f(self.totals.score_delta_raw as f64 / 65_536.0),
            ),
            (
                "legacy_native_reward_sum",
                J::f(self.totals.native_reward_raw as f64 / 65_536.0),
            ),
            (
                "score_survival_objective_return",
                J::f(self.totals.objective_return()),
            ),
            ("death", J::b(self.totals.dead)),
            ("cap_truncation", J::b(self.totals.truncated(cap))),
            (
                "frame_event_counts_enemy_spawn_collision_death_pattern_active_terminal",
                J::array(self.totals.events.iter().copied().map(J::u).collect()),
            ),
            ("counts", self.counts.json()),
            ("construction_startup_seconds", J::f(self.startup_seconds)),
            (
                "gameplay_seconds_including_policy_and_metrics",
                J::f(self.gameplay_seconds),
            ),
        ])
    }
}

fn policy_summary(kind: PolicyKind, episodes: &[Episode]) -> J {
    let dist = |values: Vec<f64>| report::distribution(values);
    let sum = |f: fn(&Episode) -> u64| episodes.iter().map(f).sum::<u64>();
    let pattern_ids: BTreeSet<u8> = episodes
        .iter()
        .flat_map(|e| e.counts.pattern_ids.iter().copied())
        .collect();
    J::object(vec![
        ("policy", J::s(kind.name())),
        ("episodes", J::u(episodes.len() as u64)),
        (
            "death_count",
            J::u(episodes.iter().filter(|e| e.totals.dead).count() as u64),
        ),
        (
            "cap_truncation_count",
            J::u(episodes.iter().filter(|e| !e.totals.dead).count() as u64),
        ),
        (
            "score",
            dist(episodes.iter().map(|e| e.final_score).collect()),
        ),
        (
            "raw_survival_frames",
            dist(
                episodes
                    .iter()
                    .map(|e| e.totals.alive_frames as f64)
                    .collect(),
            ),
        ),
        (
            "survival_seconds_60hz",
            dist(
                episodes
                    .iter()
                    .map(|e| e.totals.alive_frames as f64 / 60.0)
                    .collect(),
            ),
        ),
        (
            "max_active_enemy_family_count",
            dist(
                episodes
                    .iter()
                    .map(|e| e.counts.max_enemies as f64)
                    .collect(),
            ),
        ),
        (
            "max_active_pattern_rect_count",
            dist(episodes.iter().map(|e| e.counts.max_rects as f64).collect()),
        ),
        ("startup_native_frames", J::u(sum(|e| e.startup_frames))),
        ("gameplay_native_frames", J::u(sum(|e| e.totals.raw_frames))),
        ("decision_steps", J::u(sum(|e| e.totals.decisions))),
        (
            "enemy_overflow_frames_above_64",
            J::u(sum(|e| e.counts.enemy_overflow_frames)),
        ),
        (
            "rect_overflow_frames_above_16",
            J::u(sum(|e| e.counts.rect_overflow_frames)),
        ),
        (
            "enemy_excess_record_frames",
            J::u(sum(|e| e.counts.enemy_excess_records)),
        ),
        (
            "rect_excess_record_frames",
            J::u(sum(|e| e.counts.rect_excess_records)),
        ),
        (
            "episodes_with_enemy_overflow",
            J::u(
                episodes
                    .iter()
                    .filter(|e| e.counts.enemy_overflow_frames > 0)
                    .count() as u64,
            ),
        ),
        (
            "episodes_with_rect_overflow",
            J::u(
                episodes
                    .iter()
                    .filter(|e| e.counts.rect_overflow_frames > 0)
                    .count() as u64,
            ),
        ),
        (
            "active_pattern_frames",
            J::u(sum(|e| e.counts.active_pattern_frames)),
        ),
        (
            "pattern_ids",
            J::array(
                pattern_ids
                    .into_iter()
                    .map(|n| J::u(u64::from(n)))
                    .collect(),
            ),
        ),
    ])
}

fn run_baselines(options: &Options) -> Result<J> {
    let mut output = BufWriter::new(
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(options.output_dir.join("episodes.jsonl"))?,
    );
    let mut summaries = Vec::new();
    for kind in PolicyKind::ALL {
        let mut episodes = Vec::new();
        for index in 0..options.episodes {
            let episode = Episode::run(kind, SEED_BASE + index, options)?;
            episode
                .json(kind, index, options.max_frames)
                .write(&mut output)?;
            writeln!(output)?;
            output.flush()?;
            episodes.push(episode);
        }
        summaries.push(policy_summary(kind, &episodes));
    }
    Ok(J::object(vec![
        ("status", J::s("complete")),
        ("policies", J::array(summaries)),
        (
            "quantiles",
            J::s("median averages central pair; p90 nearest-rank ceil(0.9*n)"),
        ),
        (
            "capacity_conclusion",
            J::s("observations only; no capacity or teacher gate accepted by this harness"),
        ),
    ]))
}

fn main() -> Result<()> {
    if std::env::args().any(|arg| arg == "--help") {
        println!(
            "m0_baseline --episodes 1..1000 --max-frames 1..18000 --action-repeat 2..4 --output-dir NEW_DIR\nm0_baseline --benchmark-seconds 1..50 --threads N --output-dir NEW_DIR\nDefaults: 1000 episodes per policy, 18000 raw gameplay frames, repeat 4. Existing output directories are rejected."
        );
        return Ok(());
    }
    let options = Options::parse(std::env::args().skip(1))?;
    let identity = report::identity()?;
    // Atomic directory creation rejects every existing destination, including empty ones.
    fs::create_dir(&options.output_dir)?;
    let baseline_episodes = if options.benchmark_seconds.is_some() {
        0
    } else {
        options.episodes
    };
    let manifest = J::object(vec![
        ("schema_version", J::u(1)),
        (
            "baseline",
            J::s("PREHEADLESS full advance_frame, unchanged d7ad951 core"),
        ),
        ("identity", identity),
        (
            "mode",
            J::s(if options.benchmark_seconds.is_some() {
                "benchmark"
            } else {
                "baseline"
            }),
        ),
        ("episodes_per_policy", J::u(u64::from(baseline_episodes))),
        ("baseline_seed_base", J::u(u64::from(SEED_BASE))),
        (
            "baseline_seed_recipe",
            J::s("0xB0000000 + episode_index, identical paired stream for each policy"),
        ),
        (
            "all_baseline_seeds",
            J::array(
                (0..baseline_episodes)
                    .map(|i| J::u(u64::from(SEED_BASE + i)))
                    .collect(),
            ),
        ),
        (
            "max_raw_gameplay_frames",
            J::u(u64::from(if options.benchmark_seconds.is_some() {
                2000
            } else {
                options.max_frames
            })),
        ),
        (
            "cap_status",
            J::s("provisional; parent review required before long campaign"),
        ),
        ("action_repeat", J::u(u64::from(options.action_repeat))),
        ("difficulty", J::u(2)),
        ("patterns_enabled", J::b(true)),
        ("powerups_enabled", J::b(true)),
        ("theme_background_shadow", J::array(vec![J::u(12), J::u(1)])),
        ("initial_highscores", J::array(vec![J::u(0); 12])),
        (
            "game_rng",
            J::s("native PicoRng seeded by u32 NativeConfig.seed; no reset/retry"),
        ),
        (
            "policy_rng",
            J::s(
                "private SplitMix64, initial state u64(seed) XOR 0xD1B54A32D192ED03; rejection-sampled uniform 9 actions",
            ),
        ),
        (
            "simulation_input_path",
            J::s(
                "X once, neutral until Mode::Game; every gameplay raw frame calls existing NativeGame::advance_frame(action.mask()); never step()",
            ),
        ),
        (
            "enemy_family_definition",
            J::s("all entries in live enemies, including explosions and powerups"),
        ),
        (
            "active_rect_definition",
            J::s(
                "all rects only in active_pattern, including charging/finished entries while native pattern remains active; no catalog count",
            ),
        ),
        (
            "command_argv",
            J::array(std::env::args().map(J::s).collect()),
        ),
    ]);
    report::write_file(&options.output_dir.join("manifest.json"), &manifest)?;
    let summary = if let Some(seconds) = options.benchmark_seconds {
        benchmark::run(seconds, options.threads, options.action_repeat)?
    } else {
        run_baselines(&options)?
    };
    report::write_file(&options.output_dir.join("summary.json"), &summary)?;
    println!("complete: {}", options.output_dir.display());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accumulates_every_raw_frame_and_death_once() {
        let mut totals = Totals {
            decisions: 1,
            ..Totals::default()
        };
        totals.record(32_768, 65_536, false, &[FrameEvent::EnemySpawn]);
        totals.record(65_536, 65_536, false, &[FrameEvent::Collision]);
        totals.record(32_768, 0, true, &[FrameEvent::Death, FrameEvent::Terminal]);
        assert_eq!(totals.raw_frames, 3);
        assert_eq!(totals.alive_frames, 2);
        assert_eq!(totals.score_delta_raw, 131_072);
        assert_eq!(totals.events, [1, 1, 1, 0, 1]);
        assert!((totals.objective_return() - (-2.98)).abs() < 1e-10);
        assert!(!totals.truncated(3));
        let capped = Totals {
            raw_frames: 3,
            ..Totals::default()
        };
        assert!(capped.truncated(3));
        assert!(!capped.truncated(4));
    }

    #[test]
    fn repeat_loop_breaks_on_death_and_partial_cap_without_extra_calls() -> Result<()> {
        let mut totals = Totals::default();
        let mut calls = 0;
        let mut synthetic = || {
            calls += 1;
            Ok(RawTally {
                score_delta_raw: 32_768,
                reward_raw: if calls == 2 { 0 } else { 65_536 },
                dead: calls == 2,
                events: if calls == 2 {
                    vec![FrameEvent::Death]
                } else {
                    vec![]
                },
            })
        };
        advance_repeat(&mut totals, 4, 100, &mut synthetic)?;
        advance_repeat(&mut totals, 4, 100, &mut synthetic)?;
        assert_eq!(calls, 2);
        assert_eq!(totals.decisions, 1);
        assert_eq!(totals.raw_frames, 2);
        assert_eq!(totals.alive_frames, 1);
        assert_eq!(totals.score_delta_raw, 65_536);
        assert!((totals.objective_return() - (-3.99)).abs() < 1e-10);
        let mut capped = Totals::default();
        advance_repeat(&mut capped, 4, 3, || {
            Ok(RawTally {
                score_delta_raw: 0,
                reward_raw: 65_536,
                dead: false,
                events: vec![],
            })
        })?;
        assert_eq!(capped.raw_frames, 3);
        assert_eq!(capped.alive_frames, 3);
        assert!(capped.truncated(3));
        Ok(())
    }

    #[test]
    fn rejects_unbounded_or_ambiguous_cli() {
        for args in [
            vec!["--episodes", "1001", "--output-dir", "new"],
            vec!["--max-frames", "18001", "--output-dir", "new"],
            vec!["--benchmark-seconds", "51", "--output-dir", "new"],
            vec![
                "--benchmark-seconds",
                "1",
                "--episodes",
                "1",
                "--output-dir",
                "new",
            ],
            vec!["--episodes", "1", "--episodes", "2", "--output-dir", "new"],
        ] {
            assert!(Options::parse(args.into_iter().map(str::to_owned)).is_err());
        }
    }

    #[test]
    fn active_counts_ignore_inactive_catalog_and_log_overflow() {
        let game = NativeGame::new(NativeConfig::new(SEED_BASE));
        let mut state = game.snapshot().logical_state().clone();
        assert!(!state.patterns.is_empty());
        let mut counts = Counts::default();
        counts.observe(&state, true);
        assert_eq!(counts.max_rects, 0);
        state.active_pattern = Some(0);
        let rect = state
            .patterns
            .first()
            .and_then(|p| p.rects.first())
            .cloned();
        assert!(rect.is_some());
        if let (Some(pattern), Some(rect)) = (state.patterns.first_mut(), rect) {
            pattern.rects = vec![rect; 17];
        }
        state.enemies =
            vec![
                dodge_core::EnemyState::normal(PicoFixed::ZERO, PicoFixed::ZERO, PicoFixed::ONE);
                65
            ];
        counts.observe(&state, true);
        assert_eq!(counts.max_rects, 17);
        assert_eq!(counts.max_enemies, 65);
        assert_eq!(counts.enemy_overflow_frames, 1);
        assert_eq!(counts.rect_overflow_frames, 1);
        assert_eq!(counts.enemy_excess_records, 1);
        assert_eq!(counts.rect_excess_records, 1);
        assert_eq!(counts.pattern_ids.len(), 1);
    }
}
