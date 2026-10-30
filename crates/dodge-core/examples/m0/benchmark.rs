use super::{Budget, Options, Result, policy::PrivateRng, report::Json as J, start_game};
use dodge_core::NativeConfig;
use std::{
    sync::{Arc, Barrier},
    thread,
    time::{Duration, Instant},
};

#[derive(Default)]
struct Worker {
    id: usize,
    startup_frames: u64,
    gameplay_frames: u64,
    decisions: u64,
    alive_frames: u64,
    deaths: u64,
    cap_truncations: u64,
    deadline_truncations: u64,
    instances: u64,
    startup_seconds: f64,
    simulation_seconds: f64,
    first_seed: u32,
    last_seed: u32,
    seeds: Vec<u32>,
    failure: Option<String>,
}

impl Worker {
    fn json(&self) -> J {
        J::object(vec![
            ("worker_id", J::u(self.id as u64)),
            ("failure", J::s(self.failure.as_deref().unwrap_or(""))),
            ("fresh_instances", J::u(self.instances)),
            ("first_seed", J::u(u64::from(self.first_seed))),
            ("last_seed", J::u(u64::from(self.last_seed))),
            (
                "all_seeds",
                J::array(
                    self.seeds
                        .iter()
                        .map(|&seed| J::u(u64::from(seed)))
                        .collect(),
                ),
            ),
            ("startup_native_frames", J::u(self.startup_frames)),
            ("gameplay_native_frames", J::u(self.gameplay_frames)),
            ("alive_raw_frames", J::u(self.alive_frames)),
            ("decision_steps", J::u(self.decisions)),
            ("deaths", J::u(self.deaths)),
            ("episode_cap_truncations", J::u(self.cap_truncations)),
            ("deadline_truncations", J::u(self.deadline_truncations)),
            ("construction_startup_seconds", J::f(self.startup_seconds)),
            (
                "simulation_seconds_including_action_rng",
                J::f(self.simulation_seconds),
            ),
        ])
    }
}

fn worker(
    id: usize,
    threads: usize,
    deadline: Instant,
    barrier: Arc<Barrier>,
    repeat: u32,
    config: NativeConfig,
    budget: Budget,
) -> Result<Worker> {
    let mut result = Worker {
        id,
        ..Worker::default()
    };
    barrier.wait();
    let execution = (|| -> Result<()> {
        while Instant::now() < deadline {
            budget.check()?;
            // Disjoint strided streams across workers. Explicit checked u32 arithmetic.
            let index = result
                .instances
                .checked_mul(threads as u64)
                .and_then(|n| n.checked_add(id as u64))
                .ok_or("benchmark seed counter overflow")?;
            let seed = 0xC000_0000_u32
                .checked_add(u32::try_from(index)?)
                .ok_or("benchmark seed overflow")?;
            let startup_clock = Instant::now();
            let (mut game, snapshot, startup_frames) =
                start_game(NativeConfig { seed, ..config }, budget)?;
            drop(snapshot);
            result.startup_seconds += startup_clock.elapsed().as_secs_f64();
            result.startup_frames += startup_frames;
            if result.instances == 0 {
                result.first_seed = seed;
            }
            result.last_seed = seed;
            result.seeds.push(seed);
            result.instances += 1;
            let mut rng = PrivateRng::new(seed);
            let simulation_clock = Instant::now();
            let mut frames = 0;
            while frames < 2000 && !game.lifecycle().dead && Instant::now() < deadline {
                let action = rng.action();
                let mut decision_executed = false;
                for _ in 0..repeat {
                    if frames >= 2000 || game.lifecycle().dead || Instant::now() >= deadline {
                        break;
                    }
                    budget.check()?;
                    // Existing full rendering/snapshot path. No heuristic or metrics scan.
                    if !decision_executed {
                        result.decisions += 1;
                        decision_executed = true;
                    }
                    let frame = game.advance_frame(action.mask())?;
                    frames += 1;
                    result.gameplay_frames += 1;
                    result.alive_frames += u64::from(!frame.dead);
                    drop(frame);
                }
            }
            result.simulation_seconds += simulation_clock.elapsed().as_secs_f64();
            if game.lifecycle().dead {
                result.deaths += 1;
            } else if frames == 2000 {
                result.cap_truncations += 1;
            } else {
                result.deadline_truncations += 1;
            }
        }
        budget.check()?;
        Ok(())
    })();
    result.failure = execution.err().map(|e| e.to_string());
    Ok(result)
}

fn phase(
    name: &str,
    threads: usize,
    seconds: f64,
    outer_deadline: Instant,
    options: &Options,
    budget: Budget,
) -> Result<J> {
    budget.check()?;
    let phase_clock = Instant::now();
    let deadline = (phase_clock + Duration::from_secs_f64(seconds)).min(outer_deadline);
    let barrier = Arc::new(Barrier::new(threads + 1));
    let mut handles = Vec::new();
    for id in 0..threads {
        let barrier = Arc::clone(&barrier);
        let repeat = options.action_repeat;
        let config = options.config;
        handles.push(thread::spawn(move || {
            worker(id, threads, deadline, barrier, repeat, config, budget)
        }));
    }
    barrier.wait();
    let mut workers = Vec::new();
    for handle in handles {
        workers.push(handle.join().map_err(|_| "benchmark worker panicked")??);
    }
    let wall_seconds = phase_clock.elapsed().as_secs_f64();
    let sum = |f: fn(&Worker) -> u64| workers.iter().map(f).sum::<u64>();
    let gameplay = sum(|w| w.gameplay_frames);
    let startup = sum(|w| w.startup_frames);
    let decisions = sum(|w| w.decisions);
    let simulation_worker_seconds: f64 = workers.iter().map(|w| w.simulation_seconds).sum();
    let startup_worker_seconds: f64 = workers.iter().map(|w| w.startup_seconds).sum();
    let failure = workers.iter().find_map(|w| w.failure.as_deref());
    let summary = J::object(vec![
        (
            "status",
            J::s(if failure.is_some() {
                "failed"
            } else {
                "complete"
            }),
        ),
        ("native_config", super::report::config(options.config)),
        ("startup_frames_per_instance_verified", J::u(13)),
        ("threads", J::u(threads as u64)),
        (
            "elapsed_wall_seconds_including_startups_and_thread_lifecycle",
            J::f(wall_seconds),
        ),
        (
            "simulation_worker_seconds_sum",
            J::f(simulation_worker_seconds),
        ),
        (
            "construction_startup_worker_seconds_sum",
            J::f(startup_worker_seconds),
        ),
        ("gameplay_native_frames", J::u(gameplay)),
        ("startup_native_frames", J::u(startup)),
        ("decision_steps", J::u(decisions)),
        (
            "gameplay_raw_frames_per_wall_second",
            J::f(gameplay as f64 / wall_seconds),
        ),
        (
            "all_native_frames_per_wall_second",
            J::f((gameplay + startup) as f64 / wall_seconds),
        ),
        (
            "decision_steps_per_wall_second",
            J::f(decisions as f64 / wall_seconds),
        ),
        (
            "gameplay_raw_frames_per_simulation_worker_second",
            J::f(if simulation_worker_seconds > 0.0 {
                gameplay as f64 / simulation_worker_seconds
            } else {
                0.0
            }),
        ),
        (
            "decision_steps_per_simulation_worker_second",
            J::f(if simulation_worker_seconds > 0.0 {
                decisions as f64 / simulation_worker_seconds
            } else {
                0.0
            }),
        ),
        (
            "workers",
            J::array(workers.iter().map(Worker::json).collect()),
        ),
    ]);
    // Write even a failed phase before propagating its error.
    super::report::write_file(
        &options.output_dir.join(format!("benchmark-{name}.json")),
        &summary,
    )?;
    if let Some(error) = failure {
        return Err(error.to_owned().into());
    }
    if gameplay == 0 || simulation_worker_seconds <= 0.0 {
        return Err("benchmark produced no measured simulation frames".into());
    }
    Ok(summary)
}

fn physical_threads() -> Result<(usize, String)> {
    if cfg!(target_os = "macos") {
        let output = super::report::command(
            std::path::Path::new("/"),
            "sysctl",
            &["-n", "hw.physicalcpu"],
        )?;
        return Ok((output.parse()?, "sysctl -n hw.physicalcpu".to_owned()));
    }
    // Conservative: do not silently treat logical CPUs as physical CPUs.
    Err(
        "physical CPU discovery is implemented for macOS; refusing unverifiable thread limit"
            .into(),
    )
}

pub fn run(seconds: u32, options: &Options, budget: Budget) -> Result<J> {
    budget.check()?;
    if cfg!(debug_assertions) {
        return Err("benchmark requires cargo --release".into());
    }
    let (physical, physical_source) = physical_threads()?;
    let available = thread::available_parallelism()?.get();
    let limit = physical.min(available);
    let threads = options.threads.unwrap_or(limit.min(4));
    if threads == 0 || threads > limit || (limit > 1 && threads < 2) {
        return Err(format!(
            "multithread phase requires 2..{limit} threads (or one on a one-core host)"
        )
        .into());
    }
    let clock = Instant::now();
    // One single-thread phase, then one multithread phase. No overlapping phases.
    // Synchronous deadlines cannot preempt an in-flight call on any worker.
    let outer_deadline =
        (clock + Duration::from_secs(u64::from(seconds))).min(budget.started + budget.limit);
    let single = phase(
        "single",
        1,
        f64::from(seconds) / 2.0,
        outer_deadline,
        options,
        budget,
    )?;
    let remaining = outer_deadline
        .saturating_duration_since(Instant::now())
        .as_secs_f64();
    if remaining <= 0.0 {
        return Err("single-thread phase exhausted benchmark wall budget".into());
    }
    let multi = phase("multi", threads, remaining, outer_deadline, options, budget)?;
    let elapsed = clock.elapsed().as_secs_f64();
    if elapsed > 60.0 {
        return Err("benchmark exceeded authorized 60-second total wall limit".into());
    }
    Ok(J::object(vec![
        ("status", J::s("complete")),
        ("native_config", super::report::config(options.config)),
        ("elapsed_total_wall_seconds", J::f(elapsed)),
        ("requested_total_wall_seconds", J::u(u64::from(seconds))),
        ("physical_cpu_count", J::u(physical as u64)),
        ("physical_cpu_count_source", J::s(physical_source)),
        ("available_parallelism", J::u(available as u64)),
        ("nonoverlapping_phases", J::b(true)),
        (
            "seed_recipe",
            J::s(
                "each phase independently: 0xC0000000 + worker_id + episode_index * phase_threads",
            ),
        ),
        (
            "rng",
            J::s(
                "native PicoRng, private SplitMix64 uniform nine-action decisions, repeat from manifest",
            ),
        ),
        (
            "input_path",
            J::s(
                "start_game then full NativeGame::advance_frame on every raw gameplay frame; death/cap fresh instances; 2000 raw-frame benchmark episode cap",
            ),
        ),
        (
            "timing_boundary",
            J::s(
                "simulation clocks exclude construction/startup; include action RNG, full advance_frame and returned snapshot destruction; wall rates include startup, OS scheduling and thread lifecycle; worker seconds are sums, not parallel wall time",
            ),
        ),
        ("single_thread", single),
        ("multi_thread", multi),
    ]))
}
