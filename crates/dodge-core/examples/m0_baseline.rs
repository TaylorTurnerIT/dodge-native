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
    time::{Duration, Instant},
};

type Result<T> = std::result::Result<T, Box<dyn Error + Send + Sync>>;
const BASE_HEAD: &str = "d7ad95127ad7529c5217a51ae9dc5cfedd3f2365";
const SEED_BASE: u32 = 0xB000_0000;
const ENEMY_CAP: usize = 64;
const RECT_CAP: usize = 16;
const DEADLINE_ERROR: &str = "global --max-seconds deadline reached; partial receipts retained";

#[derive(Clone, Copy)]
struct Budget {
    started: Instant,
    limit: Duration,
}

impl Budget {
    fn new(seconds: u32) -> Self {
        Self {
            started: Instant::now(),
            limit: Duration::from_secs(u64::from(seconds)),
        }
    }

    fn check_elapsed(self, elapsed: Duration) -> Result<()> {
        if elapsed >= self.limit {
            return Err(DEADLINE_ERROR.into());
        }
        Ok(())
    }

    fn check(self) -> Result<()> {
        self.check_elapsed(self.started.elapsed())
    }
}

#[derive(Debug)]
struct Options {
    episodes: u32,
    max_frames: u32,
    action_repeat: u32,
    output_dir: PathBuf,
    benchmark_seconds: Option<u32>,
    threads: Option<usize>,
    config: NativeConfig,
    max_seconds: u32,
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
            config: NativeConfig::new(SEED_BASE),
            max_seconds: 3600,
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
                "--difficulty" => value.config.difficulty = next.parse()?,
                "--patterns" => value.config.patterns_enabled = next.parse()?,
                "--powerups" => value.config.powerups_enabled = next.parse()?,
                "--max-seconds" => value.max_seconds = next.parse()?,
                _ => return Err(format!("unknown argument: {arg}").into()),
            }
        }
        if !(1..=1000).contains(&value.episodes)
            || !(1..=18_000).contains(&value.max_frames)
            || !(2..=4).contains(&value.action_repeat)
            || value.output_dir.as_os_str().is_empty()
            || !(1..=3).contains(&value.config.difficulty)
            || !(1..=3600).contains(&value.max_seconds)
            || value
                .benchmark_seconds
                .is_some_and(|n| !(1..=50).contains(&n))
            || (value.threads.is_some() && value.benchmark_seconds.is_none())
            || (value.benchmark_seconds.is_some()
                && (seen.contains("--episodes") || seen.contains("--max-frames")))
        {
            return Err("require --output-dir NEW_DIR; episodes 1..1000, max-frames 1..18000, repeat 2..4, difficulty 1..3, patterns/powerups true|false, max-seconds 1..3600; benchmark-seconds 1..50 is a separate mode".into());
        }
        Ok(value)
    }
}

/// A new instance for every episode; never reset or press retry.
fn start_game(config: NativeConfig, budget: Budget) -> Result<(NativeGame, Snapshot, u64)> {
    budget.check()?;
    let mut game = NativeGame::new(config);
    budget.check()?;
    let mut frame = game.advance_frame(BUTTON_X_MASK)?;
    let mut startup_frames = 1;
    while game.lifecycle().mode != Mode::Game {
        budget.check()?;
        if startup_frames >= 120 {
            return Err("startup did not reach Mode::Game within 120 raw frames".into());
        }
        frame = game.advance_frame(0)?;
        startup_frames += 1;
    }
    budget.check()?;
    let state = frame.snapshot.logical_state();
    if startup_frames != 13
        || state.seed != config.seed
        || state.settings.difficulty != config.difficulty
        || state.settings.patterns_enabled != config.patterns_enabled
        || state.settings.powerups_enabled != config.powerups_enabled
        || state.patterns_enabled != config.patterns_enabled
        || state.powerups_enabled != config.powerups_enabled
        || state.settings.theme_background != config.theme_background
        || state.settings.theme_shadow != config.theme_shadow
        || state.highscores != config.highscores
    {
        return Err("startup count/configuration mismatch: expected X + 12 neutral frames and exact NativeConfig".into());
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
    let mut decision_executed = false;
    for _ in 0..repeat {
        if totals.dead || totals.raw_frames >= u64::from(cap) {
            break;
        }
        let frame = advance()?;
        if !decision_executed {
            totals.decisions += 1;
            decision_executed = true;
        }
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

struct Scores {
    final_score: PicoFixed,
    highscore_slot: usize,
    stored_highscore: PicoFixed,
    new_highscore: bool,
}

impl Scores {
    fn capture(state: &dodge_core::FullState) -> Result<Self> {
        let settings = state.settings;
        let highscore_slot = (0..12)
            .find(|index| {
                let slot = index % 4;
                index / 4 + 1 == usize::from(settings.difficulty)
                    && settings.patterns_enabled == (slot == 0 || slot == 1)
                    && settings.powerups_enabled == (slot == 0 || slot == 3)
            })
            .ok_or("invalid native highscore category")?;
        let stored_highscore = state
            .highscores
            .get(highscore_slot)
            .copied()
            .ok_or("missing native highscore slot")?;
        Ok(Self {
            final_score: state.score,
            highscore_slot,
            stored_highscore,
            new_highscore: state.new_highscore,
        })
    }

    fn json(&self) -> J {
        J::object(vec![
            (
                "final_score_raw_fixed",
                J::i(i64::from(self.final_score.raw())),
            ),
            ("final_score_raw", J::f(self.final_score.to_double())),
            (
                "final_score_display_ceil",
                J::i(i64::from(self.final_score.ceil().raw()) / 65_536),
            ),
            (
                "stored_highscore_category_slot_zero_based",
                J::u(self.highscore_slot as u64),
            ),
            (
                "stored_highscore_raw_fixed",
                J::i(i64::from(self.stored_highscore.raw())),
            ),
            ("stored_highscore", J::f(self.stored_highscore.to_double())),
            ("new_highscore", J::b(self.new_highscore)),
        ])
    }
}

struct Episode {
    seed: u32,
    startup_frames: u64,
    totals: Totals,
    counts: Counts,
    scores: Scores,
    config: NativeConfig,
    failure: Option<String>,
    final_state_hash: u64,
    native_survival_frames: u32,
    startup_seconds: f64,
    gameplay_seconds: f64,
}

impl Episode {
    fn run(kind: PolicyKind, seed: u32, options: &Options, budget: Budget) -> Result<Self> {
        let startup_clock = Instant::now();
        let config = NativeConfig {
            seed,
            ..options.config
        };
        let (mut game, mut snapshot, startup_frames) = start_game(config, budget)?;
        let startup_seconds = startup_clock.elapsed().as_secs_f64();
        let mut policy = Policy::new(kind, seed);
        policy.observe(snapshot.logical_state());
        let mut counts = Counts::default();
        counts.observe(snapshot.logical_state(), false);
        let mut totals = Totals::default();
        let initial_native_survival = game.survival_frames();
        let mut previous_score = i64::from(game.score().raw());
        let gameplay_clock = Instant::now();
        let execution = (|| -> Result<()> {
            while totals.raw_frames < u64::from(options.max_frames) && !totals.dead {
                budget.check()?;
                if game.lifecycle().mode != Mode::Game {
                    return Err("decision began outside Mode::Game".into());
                }
                let action = policy.action(snapshot.logical_state());
                advance_repeat(
                    &mut totals,
                    options.action_repeat,
                    options.max_frames,
                    || {
                        budget.check()?;
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
            Ok(())
        })();
        let mut failure = execution.err().map(|e| e.to_string());
        let gameplay_seconds = gameplay_clock.elapsed().as_secs_f64();
        let native_survival_frames = game.survival_frames() - initial_native_survival;
        if u64::from(native_survival_frames) != totals.alive_frames
            || totals.score_delta_raw != i64::from(game.score().raw())
            || (failure.is_none() && !(totals.dead || totals.truncated(options.max_frames)))
        {
            failure =
                Some("episode accounting invariant failed; partial receipts retained".to_owned());
        }
        let final_snapshot = game.snapshot();
        Ok(Self {
            seed,
            startup_frames,
            totals,
            counts,
            scores: Scores::capture(final_snapshot.logical_state())?,
            config,
            failure,
            final_state_hash: final_snapshot.state_hash(),
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
            ("native_config", report::config(self.config)),
            (
                "episode_status",
                J::s(if self.failure.is_some() {
                    "interrupted"
                } else {
                    "complete"
                }),
            ),
            ("failure", J::s(self.failure.as_deref().unwrap_or(""))),
            ("final_state_hash", J::u(self.final_state_hash)),
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
            ("scores", self.scores.json()),
            (
                "score_delta_sum_raw_fixed",
                J::i(self.totals.score_delta_raw),
            ),
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
                "run_deadline_truncation",
                J::b(self.failure.as_deref() == Some(DEADLINE_ERROR) && !self.totals.dead),
            ),
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
            "raw_score",
            dist(
                episodes
                    .iter()
                    .map(|e| e.scores.final_score.to_double())
                    .collect(),
            ),
        ),
        (
            "display_score_ceil",
            dist(
                episodes
                    .iter()
                    .map(|e| e.scores.final_score.ceil().to_double())
                    .collect(),
            ),
        ),
        (
            "stored_highscore",
            dist(
                episodes
                    .iter()
                    .map(|e| e.scores.stored_highscore.to_double())
                    .collect(),
            ),
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

#[derive(Default)]
struct Progress {
    policy: Option<&'static str>,
    episode_index: u32,
    completed_episodes: u64,
    episode_records: u64,
}

fn failure_metadata(error: &str, progress: &Progress, budget: Budget) -> J {
    J::object(vec![
        ("status", J::s("failed")),
        ("error", J::s(error)),
        ("global_deadline_reached", J::b(budget.check().is_err())),
        ("max_seconds", J::f(budget.limit.as_secs_f64())),
        (
            "elapsed_seconds",
            J::f(budget.started.elapsed().as_secs_f64()),
        ),
        ("last_policy", J::s(progress.policy.unwrap_or(""))),
        (
            "last_episode_index",
            J::u(u64::from(progress.episode_index)),
        ),
        ("completed_episodes", J::u(progress.completed_episodes)),
        ("episode_jsonl_records", J::u(progress.episode_records)),
        ("partial_receipts_retained", J::b(true)),
        (
            "deadline_contract",
            J::s(
                "synchronous checks between native frames, episodes and run stages; no OS preemption of calls or I/O",
            ),
        ),
    ])
}

fn run_baselines(options: &Options, budget: Budget, progress: &mut Progress) -> Result<J> {
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
            progress.policy = Some(kind.name());
            progress.episode_index = index;
            budget.check()?;
            let episode = Episode::run(kind, SEED_BASE + index, options, budget)?;
            write_episode(&mut output, &episode, kind, index, options.max_frames)?;
            progress.episode_records += 1;
            if let Some(error) = &episode.failure {
                return Err(error.clone().into());
            }
            progress.completed_episodes += 1;
            episodes.push(episode);
        }
        summaries.push(policy_summary(kind, &episodes));
    }
    Ok(J::object(vec![
        ("status", J::s("complete")),
        ("policies", J::array(summaries)),
        (
            "quantiles",
            J::s("median averages central pair; p10/p25/p75/p90 nearest-rank ceil(p*n)"),
        ),
        (
            "capacity_conclusion",
            J::s("observations only; no capacity or teacher gate accepted by this harness"),
        ),
    ]))
}

fn write_episode(
    output: &mut BufWriter<std::fs::File>,
    episode: &Episode,
    kind: PolicyKind,
    index: u32,
    cap: u32,
) -> Result<()> {
    episode.json(kind, index, cap).write(output)?;
    writeln!(output)?;
    output.flush()?;
    output.get_ref().sync_data()?;
    Ok(())
}

fn main() -> Result<()> {
    if std::env::args().any(|arg| arg == "--help") {
        println!(
            "m0_baseline --episodes 1..1000 --max-frames 1..18000 --action-repeat 2..4 --output-dir NEW_DIR\nm0_baseline --benchmark-seconds 1..50 --threads N --output-dir NEW_DIR\nBoth modes: --difficulty 1|2|3 --patterns true|false --powerups true|false --max-seconds 1..3600\nDefaults: 1000 episodes per policy, 18000 raw gameplay frames, repeat 4, difficulty 2, patterns/powerups true, max-seconds 3600. Existing output directories are rejected. Deadline checks are synchronous; no OS preemption."
        );
        return Ok(());
    }
    let options = Options::parse(std::env::args().skip(1))?;
    let budget = Budget::new(options.max_seconds);
    // Atomic directory creation rejects every existing destination, including empty ones.
    fs::create_dir(&options.output_dir)?;
    let mut progress = Progress::default();
    let outcome = (|| -> Result<()> {
        budget.check()?;
        let identity = report::identity()?;
        budget.check()?;
        let baseline_episodes = if options.benchmark_seconds.is_some() {
            0
        } else {
            options.episodes
        };
        let manifest = J::object(vec![
            ("schema_version", J::u(2)),
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
                J::s(
                    "production default fixed at 18000; parent free Beam review required before campaign",
                ),
            ),
            ("action_repeat", J::u(u64::from(options.action_repeat))),
            ("native_config", report::config(options.config)),
            (
                "startup_expected_native_frames_verified_per_instance",
                J::u(13),
            ),
            ("max_seconds", J::u(u64::from(options.max_seconds))),
            (
                "deadline_scope",
                J::s(
                    "global after CLI parsing, including provenance/startup/simulation; synchronous checks between frames/episodes/stages; no OS preemption of calls or I/O",
                ),
            ),
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
        budget.check()?;
        let summary = if let Some(seconds) = options.benchmark_seconds {
            benchmark::run(seconds, &options, budget)?
        } else {
            run_baselines(&options, budget, &mut progress)?
        };
        budget.check()?;
        report::write_file(&options.output_dir.join("summary.json"), &summary)?;
        Ok(())
    })();
    if let Err(error) = outcome {
        let metadata = failure_metadata(&error.to_string(), &progress, budget);
        report::write_file(&options.output_dir.join("failure.json"), &metadata)?;
        return Err(error);
    }
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
            vec!["--max-seconds", "0", "--output-dir", "new"],
            vec!["--max-seconds", "3601", "--output-dir", "new"],
            vec!["--difficulty", "0", "--output-dir", "new"],
            vec!["--difficulty", "4", "--output-dir", "new"],
            vec!["--patterns", "yes", "--output-dir", "new"],
            vec!["--powerups", "1", "--output-dir", "new"],
        ] {
            assert!(Options::parse(args.into_iter().map(str::to_owned)).is_err());
        }
    }

    #[test]
    fn configuration_defaults_and_all_startup_categories_match_native() -> Result<()> {
        let defaults = Options::parse(["--output-dir", "unused"].map(str::to_owned))?;
        assert_eq!(defaults.config, NativeConfig::new(SEED_BASE));
        assert_eq!(
            (
                defaults.episodes,
                defaults.max_frames,
                defaults.action_repeat,
                defaults.max_seconds
            ),
            (1000, 18_000, 4, 3600)
        );
        for difficulty in 1..=3 {
            for patterns in [false, true] {
                for powerups in [false, true] {
                    let options = Options::parse([
                        "--output-dir".to_owned(),
                        "unused".to_owned(),
                        "--difficulty".to_owned(),
                        difficulty.to_string(),
                        "--patterns".to_owned(),
                        patterns.to_string(),
                        "--powerups".to_owned(),
                        powerups.to_string(),
                        "--max-seconds".to_owned(),
                        "1".to_owned(),
                    ])?;
                    let (game, _, frames) = start_game(options.config, Budget::new(10))?;
                    assert_eq!(frames, 13);
                    let state = game.snapshot().logical_state().clone();
                    assert_eq!(state.settings.difficulty, difficulty);
                    assert_eq!(state.settings.patterns_enabled, patterns);
                    assert_eq!(state.settings.powerups_enabled, powerups);
                    assert_eq!(
                        (state.settings.theme_background, state.settings.theme_shadow),
                        (12, 1)
                    );
                    assert_eq!(state.highscores, [PicoFixed::ZERO; 12]);
                    let scores = Scores::capture(&state)?;
                    let subslot = match (patterns, powerups) {
                        (true, true) => 0,
                        (true, false) => 1,
                        (false, false) => 2,
                        (false, true) => 3,
                    };
                    assert_eq!(
                        scores.highscore_slot,
                        usize::from(difficulty - 1) * 4 + subslot
                    );
                }
            }
        }
        Ok(())
    }

    #[test]
    fn raw_display_and_stored_highscore_remain_distinct_on_terminal_fixture() -> Result<()> {
        let mut state = NativeGame::new(NativeConfig::new(SEED_BASE))
            .snapshot()
            .logical_state()
            .clone();
        state.lifecycle.dead = true;
        state.score = PicoFixed::from_f32(1.5);
        // die() can save a category before a later same-frame pickup changes score.
        if let Some(slot) = state.highscores.get_mut(4) {
            *slot = PicoFixed::ONE;
        }
        state.new_highscore = true;
        let scores = Scores::capture(&state)?;
        assert_eq!(scores.final_score.raw(), 98_304);
        assert_eq!(scores.final_score.to_double(), 1.5);
        assert_eq!(scores.final_score.ceil(), PicoFixed::from_int(2));
        assert_eq!(scores.stored_highscore, PicoFixed::ONE);
        assert_eq!(scores.highscore_slot, 4);
        let mut bytes = Vec::new();
        scores.json().write(&mut bytes)?;
        let json = String::from_utf8(bytes)?;
        assert!(json.contains("\"final_score_raw_fixed\":98304"));
        assert!(json.contains("\"final_score_raw\":1.5"));
        assert!(json.contains("\"final_score_display_ceil\":2"));
        assert!(json.contains("\"stored_highscore_raw_fixed\":65536"));
        Ok(())
    }

    #[test]
    fn synchronous_deadline_stops_inside_repeat_without_extra_native_call() -> Result<()> {
        let budget = Budget::new(1);
        assert!(budget.check_elapsed(Duration::from_millis(999)).is_ok());
        assert!(budget.check_elapsed(Duration::from_secs(1)).is_err());
        let mut totals = Totals::default();
        let mut calls = 0;
        let error = advance_repeat(&mut totals, 4, 2000, || {
            budget.check_elapsed(Duration::from_millis(calls * 500))?;
            calls += 1;
            Ok(RawTally {
                score_delta_raw: 32_768,
                reward_raw: 65_536,
                dead: false,
                events: vec![],
            })
        });
        assert_eq!(
            error.err().map(|e| e.to_string()).as_deref(),
            Some(DEADLINE_ERROR)
        );
        assert_eq!(calls, 2);
        assert_eq!(totals.raw_frames, 2);
        assert_eq!(totals.score_delta_raw, 65_536);
        assert!(!totals.truncated(2000));
        let mut untouched = Totals::default();
        assert!(
            advance_repeat(&mut untouched, 4, 2000, || {
                budget.check_elapsed(Duration::from_secs(1))?;
                Err("must not reach synthetic native call".into())
            })
            .is_err()
        );
        assert_eq!(untouched.decisions, 0);
        assert_eq!(untouched.raw_frames, 0);
        Ok(())
    }

    #[test]
    fn expired_episode_boundary_retains_jsonl_and_exclusive_failure_metadata() -> Result<()> {
        let parent = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/v2-m0-review-r2/synthetic-tests");
        fs::create_dir_all(&parent)?;
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos();
        let path = parent.join(format!("deadline-{}-{unique}", std::process::id()));
        fs::create_dir(&path)?;
        let options = Options::parse([
            "--output-dir".to_owned(),
            path.display().to_string(),
            "--episodes".to_owned(),
            "1".to_owned(),
        ])?;
        let budget = Budget {
            started: Instant::now(),
            limit: Duration::ZERO,
        };
        let mut progress = Progress::default();
        let error = run_baselines(&options, budget, &mut progress)
            .err()
            .ok_or("expired run unexpectedly passed")?;
        assert_eq!(error.to_string(), DEADLINE_ERROR);
        assert_eq!(progress.episode_records, 0);
        assert!(path.join("episodes.jsonl").exists());
        let failure = failure_metadata(&error.to_string(), &progress, budget);
        let receipt = path.join("failure.json");
        report::write_file(&receipt, &failure)?;
        let before = fs::read(&receipt)?;
        assert!(report::write_file(&receipt, &J::s("overwrite")).is_err());
        assert_eq!(fs::read(&receipt)?, before);
        assert!(fs::create_dir(&path).is_err());
        // Retain a synthetic interrupted episode through the same flush/sync path
        // used by native execution; no extra gameplay episodes are run here.
        let mut state = NativeGame::new(options.config)
            .snapshot()
            .logical_state()
            .clone();
        state.score = PicoFixed::ONE;
        let partial = Episode {
            seed: SEED_BASE,
            startup_frames: 13,
            totals: Totals {
                raw_frames: 2,
                alive_frames: 2,
                decisions: 1,
                score_delta_raw: 65_536,
                ..Totals::default()
            },
            counts: Counts::default(),
            scores: Scores::capture(&state)?,
            config: options.config,
            failure: Some(DEADLINE_ERROR.to_owned()),
            final_state_hash: 0,
            native_survival_frames: 2,
            startup_seconds: 0.0,
            gameplay_seconds: 0.0,
        };
        let mut output = BufWriter::new(
            OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(path.join("partial-episodes.jsonl"))?,
        );
        write_episode(&mut output, &partial, PolicyKind::Random, 0, 2000)?;
        let text = fs::read_to_string(path.join("partial-episodes.jsonl"))?;
        assert_eq!(text.lines().count(), 1);
        assert!(text.contains("\"episode_status\":\"interrupted\""));
        assert!(text.contains("\"run_deadline_truncation\":true"));
        assert!(text.contains("\"gameplay_native_frames\":2"));
        assert!(text.contains("\"final_score_raw_fixed\":65536"));
        Ok(())
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
