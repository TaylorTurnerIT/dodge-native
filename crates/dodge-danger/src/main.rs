use std::{
    env,
    io::{BufWriter, Write as IoWrite},
    path::{Path, PathBuf},
    process,
};

use dodge_danger::{DangerConfig, PolicyKind, compare, run_episode, stream_episode, trace_meta};

const DEFAULT_MAX_FRAMES: u32 = 2_400;
const DEFAULT_HORIZON: u32 = 36;
const DEFAULT_GRID: usize = 40;
const DEFAULT_GOAL_EVERY: u32 = 8;
const DEFAULT_HEAT_EVERY: u32 = 10;

#[derive(Debug)]
struct Options {
    config: DangerConfig,
    policy: PolicyKind,
    output: Option<PathBuf>,
    compare: bool,
    stream: bool,
    dataset: bool,
    deaths: bool,
    survival: bool,
    seeds: u32,
    help: bool,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("dodge-danger: {error}");
        process::exit(2);
    }
}

fn run() -> Result<(), String> {
    let options = parse_options(env::args().skip(1))?;
    if options.help {
        print!("{}", usage());
        return Ok(());
    }

    if options.stream {
        return stream(&options);
    }

    if options.dataset {
        return dataset(&options);
    }

    if options.survival {
        let threads = dodge_danger::worker_threads();
        let rows = dodge_danger::survival_parallel(
            &options.config,
            options.policy,
            options.seeds,
            threads,
        )?;
        let total: u64 = rows.iter().map(|row| u64::from(row.1)).sum();
        let died = rows.iter().filter(|row| row.2).count();
        let worst = rows.iter().map(|row| row.1).min().unwrap_or(0);
        println!(
            "{} D{}: mean {:.0} frames, min {}, died {}/{} (cap {})",
            options.policy.name(),
            options.config.difficulty,
            total as f64 / rows.len().max(1) as f64,
            worst,
            died,
            rows.len(),
            options.config.max_frames
        );
        return Ok(());
    }

    if options.deaths {
        let threads = dodge_danger::worker_threads();
        let study = dodge_danger::deaths::run(&options.config, options.seeds, threads)?;
        let mut bytes = Vec::new();
        for case in &study.deaths {
            serde_json::to_writer(&mut bytes, case).map_err(|error| error.to_string())?;
            bytes.push(b'\n');
        }
        write_output(options.output.as_deref(), &bytes)?;
        eprintln!(
            "dodge-danger: {} of {} games ended in a death before {} frames",
            study.deaths.len(),
            study.games,
            options.config.max_frames
        );
        return Ok(());
    }

    if options.compare {
        let output = compare(&options.config, options.seeds)?;
        let mut bytes = Vec::new();
        serde_json::to_writer_pretty(&mut bytes, &output)
            .map_err(|error| format!("could not encode comparison: {error}"))?;
        bytes.push(b'\n');
        write_output(options.output.as_deref(), &bytes)?;
        for row in &output.rows {
            eprintln!(
                "dodge-danger: {:>9}  mean {:7.1}  min {:5}  max {:5}{}",
                row.policy,
                row.mean_survival,
                row.min_survival,
                row.max_survival,
                if row.censored { "  (censored)" } else { "" }
            );
        }
        return Ok(());
    }

    let episode = run_episode(&options.config, options.policy, true)?;
    let trace = episode
        .trace
        .ok_or_else(|| "trace was not captured".to_owned())?;
    let mut bytes = Vec::new();
    serde_json::to_writer(&mut bytes, &trace)
        .map_err(|error| format!("could not encode trace: {error}"))?;
    bytes.push(b'\n');
    write_output(options.output.as_deref(), &bytes)?;
    eprintln!(
        "dodge-danger: seed={} difficulty={} policy={} survival={} dead={} frames={}",
        options.config.seed,
        options.config.difficulty,
        options.policy.name(),
        episode.survival_frames,
        episode.dead,
        trace.result.captured_frames,
    );
    Ok(())
}

const OUTPUT_CLOSED: &str = "output closed";

/// Run with no frame limit and write one JSON line per frame to stdout.
///
/// Line 1 is `{"meta": ...}`, each frame is a frame record, and the last line is
/// `{"result": ...}`. Writing blocks when the reader is slow, so the reader sets
/// the pace. The run stops quietly when the reader closes the pipe.
fn stream(options: &Options) -> Result<(), String> {
    let stdout = std::io::stdout();
    let mut out = BufWriter::new(stdout.lock());
    let mut write_line = |value: &dyn erased::Json| -> Result<(), String> {
        value.write(&mut out)?;
        out.write_all(b"\n").map_err(|_| OUTPUT_CLOSED.to_owned())?;
        out.flush().map_err(|_| OUTPUT_CLOSED.to_owned())
    };

    let meta = trace_meta(&options.config, options.policy);
    let outcome = write_line(&erased::Wrapped("meta", &meta)).and_then(|()| {
        stream_episode(&options.config, options.policy, None, &mut |record| {
            write_line(&erased::Bare(&record))
        })
    });
    match outcome {
        Ok(result) => match write_line(&erased::Wrapped("result", &result)) {
            Ok(()) | Err(_) => Ok(()),
        },
        Err(error) if error == OUTPUT_CLOSED => Ok(()),
        Err(error) => Err(error),
    }
}

/// Write a training set: one compact line per frame, for `--seeds` consecutive
/// games of at most `--frames` frames each. A line holds only what the player can see
/// (`p` player, `e` enemies, `r` pattern rectangles) and the labels (`c` nine costs,
/// `a` the policy's action, `x` the played action when a random burst replaced it).
fn dataset(options: &Options) -> Result<(), String> {
    use serde_json::json;
    let stdout = std::io::stdout();
    let mut out = BufWriter::new(stdout.lock());
    let mut config = options.config;
    // Store the arrival field on the frames where the lookahead goal is recomputed,
    // so the field always matches the observation on the same line.
    config.heat_every = config.goal_every;
    let first_seed = config.seed;
    let outcome = (|| -> Result<(), String> {
        for offset in 0..options.seeds {
            config.seed = first_seed.wrapping_add(offset);
            let seed = config.seed;
            let mut index: u32 = 0;
            let result = stream_episode(
                &config,
                options.policy,
                Some(config.max_frames),
                &mut |record| {
                    let mut line = json!({
                        "s": seed, "f": index, "p": record.p, "e": record.e,
                        "c": record.costs, "a": record.a,
                    });
                    if !record.r.is_empty() {
                        line["r"] = json!(record.r);
                    }
                    if !record.ph.is_empty() {
                        line["ph"] = json!(record.ph);
                        line["dy"] = json!(record.dy);
                        if !record.rs.is_empty() {
                            line["rs"] = json!(record.rs);
                        }
                    }
                    if let Some(played) = record.x {
                        line["x"] = json!(played);
                    }
                    // Arrival field on a coarse grid: 2x2 blocks of the field, bytes 0..=255.
                    if let Some(heat) = &record.h
                        && heat.w % 2 == 0
                        && heat.h % 2 == 0
                    {
                        let mut coarse = Vec::with_capacity(heat.w * heat.h / 4);
                        for row in 0..heat.h / 2 {
                            for column in 0..heat.w / 2 {
                                let mut sum = 0u32;
                                for (dy, dx) in [(0, 0), (0, 1), (1, 0), (1, 1)] {
                                    let index = (row * 2 + dy) * heat.w + column * 2 + dx;
                                    sum += u32::from(heat.a.get(index).copied().unwrap_or(0));
                                }
                                coarse.push(sum / 4);
                            }
                        }
                        line["h"] = json!({"w": heat.w / 2, "a": coarse});
                    }
                    index += 1;
                    serde_json::to_writer(&mut out, &line).map_err(|_| OUTPUT_CLOSED.to_owned())?;
                    out.write_all(b"\n").map_err(|_| OUTPUT_CLOSED.to_owned())
                },
            )?;
            let end = json!({"end": {"s": seed, "survival": result.survival_frames,
                "dead": result.dead, "frames": result.captured_frames}});
            serde_json::to_writer(&mut out, &end).map_err(|_| OUTPUT_CLOSED.to_owned())?;
            out.write_all(b"\n").map_err(|_| OUTPUT_CLOSED.to_owned())?;
        }
        out.flush().map_err(|_| OUTPUT_CLOSED.to_owned())
    })();
    match outcome {
        Err(error) if error != OUTPUT_CLOSED => Err(error),
        _ => Ok(()),
    }
}

/// Small helpers so one closure can write different serialisable values.
mod erased {
    use serde::Serialize;
    use std::io::Write;

    pub trait Json {
        fn write(&self, out: &mut dyn Write) -> Result<(), String>;
    }

    pub struct Bare<'a, T: Serialize>(pub &'a T);
    pub struct Wrapped<'a, T: Serialize>(pub &'static str, pub &'a T);

    impl<T: Serialize> Json for Bare<'_, T> {
        fn write(&self, out: &mut dyn Write) -> Result<(), String> {
            serde_json::to_writer(out, self.0).map_err(|_| super::OUTPUT_CLOSED.to_owned())
        }
    }

    impl<T: Serialize> Json for Wrapped<'_, T> {
        fn write(&self, out: &mut dyn Write) -> Result<(), String> {
            let value = serde_json::json!({ self.0: self.1 });
            serde_json::to_writer(out, &value).map_err(|_| super::OUTPUT_CLOSED.to_owned())
        }
    }
}

fn parse_options<I>(arguments: I) -> Result<Options, String>
where
    I: IntoIterator<Item = String>,
{
    let mut values = arguments.into_iter();
    let mut config = DangerConfig::default();
    let mut policy = PolicyKind::Lookahead;
    let mut output = None;
    let mut compare = false;
    let mut stream = false;
    let mut dataset = false;
    let mut deaths = false;
    let mut survival = false;
    let mut seeds = 1;
    let mut help = false;

    while let Some(argument) = values.next() {
        match argument.as_str() {
            "--seed" => config.seed = parse_u32(&next_value(&mut values, "--seed")?, "seed")?,
            "--difficulty" => {
                let value = parse_u32(&next_value(&mut values, "--difficulty")?, "difficulty")?;
                config.difficulty =
                    u8::try_from(value).map_err(|_| "difficulty must be 1, 2, or 3".to_owned())?;
            }
            "--frames" => {
                config.max_frames = parse_u32(&next_value(&mut values, "--frames")?, "frames")?;
            }
            "--horizon" => {
                config.horizon = parse_u32(&next_value(&mut values, "--horizon")?, "horizon")?;
            }
            "--grid" => {
                config.grid = parse_usize(&next_value(&mut values, "--grid")?, "grid")?;
            }
            "--goal-every" => {
                config.goal_every =
                    parse_u32(&next_value(&mut values, "--goal-every")?, "goal-every")?;
            }
            "--heat-every" => {
                config.heat_every =
                    parse_u32(&next_value(&mut values, "--heat-every")?, "heat-every")?;
            }
            "--policy" => {
                let name = next_value(&mut values, "--policy")?;
                policy = PolicyKind::from_name(&name)
                    .ok_or_else(|| format!("unknown policy {name}\n{}", usage()))?;
            }
            "--out" => output = Some(PathBuf::from(next_value(&mut values, "--out")?)),
            "--compare" => compare = true,
            "--stream" => stream = true,
            "--dataset" => dataset = true,
            "--deaths" => deaths = true,
            "--survival" => survival = true,
            "--physics" => config.physics = true,
            "--physics-model" => {
                let path = next_value(&mut values, "--physics-model")?;
                let text = std::fs::read_to_string(&path)
                    .map_err(|error| format!("could not read {path}: {error}"))?;
                dodge_danger::hnnplan::install(dodge_danger::hnnplan::PhysicsModel::from_json(
                    &text,
                )?)?;
            }
            "--model" | "--drive-model" => {
                let path = next_value(&mut values, argument.as_str())?;
                let text = std::fs::read_to_string(&path)
                    .map_err(|error| format!("could not read {path}: {error}"))?;
                dodge_danger::learned::install(dodge_danger::learned::Model::from_json(&text)?)?;
                config.drive_model = argument == "--drive-model";
            }
            "--epsilon" => {
                let text = next_value(&mut values, "--epsilon")?;
                config.epsilon = text
                    .parse::<f64>()
                    .map_err(|error| format!("epsilon must be a number: {error}"))?;
            }
            "--seeds" => seeds = parse_u32(&next_value(&mut values, "--seeds")?, "seeds")?,
            "--params" => {
                let path = next_value(&mut values, "--params")?;
                let text = std::fs::read_to_string(&path)
                    .map_err(|error| format!("could not read {path}: {error}"))?;
                config.landscape = serde_json::from_str(&text)
                    .map_err(|error| format!("could not parse {path}: {error}"))?;
            }
            "--patterns" => config.patterns = true,
            "--powerups" => config.powerups = true,
            "--help" | "-h" => help = true,
            value => return Err(format!("unknown argument {value}\n{}", usage())),
        }
    }

    config.validate()?;
    if seeds == 0 {
        return Err("seeds must be greater than zero".to_owned());
    }

    Ok(Options {
        config,
        policy,
        output,
        compare,
        stream,
        dataset,
        deaths,
        survival,
        seeds,
        help,
    })
}

fn next_value<I>(values: &mut I, option: &str) -> Result<String, String>
where
    I: Iterator<Item = String>,
{
    values
        .next()
        .ok_or_else(|| format!("{option} requires a value"))
}

fn parse_u32(value: &str, name: &str) -> Result<u32, String> {
    value
        .parse::<u32>()
        .map_err(|error| format!("{name} must be an unsigned integer: {error}"))
}

fn parse_usize(value: &str, name: &str) -> Result<usize, String> {
    value
        .parse::<usize>()
        .map_err(|error| format!("{name} must be an unsigned integer: {error}"))
}

fn write_output(path: Option<&Path>, bytes: &[u8]) -> Result<(), String> {
    if let Some(path) = path {
        if let Some(parent) = path.parent()
            && !parent.as_os_str().is_empty()
        {
            std::fs::create_dir_all(parent)
                .map_err(|error| format!("could not create {}: {error}", parent.display()))?;
        }
        std::fs::write(path, bytes)
            .map_err(|error| format!("could not write {}: {error}", path.display()))
    } else {
        std::io::stdout()
            .write_all(bytes)
            .map_err(|error| format!("could not write stdout: {error}"))
    }
}

fn usage() -> String {
    format!(
        "usage: dodge-danger [options]\n\
         \n\
         Trace options:\n\
           --seed N             game seed (default 42)\n\
           --difficulty N       1, 2, or 3 (default 2)\n\
           --policy NAME        lookahead | landscape | potential | flee | random | neutral\n\
           --frames N           maximum gameplay frames (default {DEFAULT_MAX_FRAMES})\n\
           --horizon N          lookahead frames (default {DEFAULT_HORIZON})\n\
           --grid N             heat-map cells per side (default {DEFAULT_GRID})\n\
           --goal-every N       recompute goal every N frames (default {DEFAULT_GOAL_EVERY})\n\
           --heat-every N       store a heat map every N frames (default {DEFAULT_HEAT_EVERY})\n\
           --patterns           enable patterns (heat map becomes approximate)\n\
           --powerups           enable powerups (heat map becomes approximate)\n\
           --out PATH           write JSON to PATH instead of stdout\n\
           --params PATH        JSON overrides for the landscape policy's shapes\n\
           --stream             no frame limit; one JSON line per frame on stdout\n\
           --dataset            training set: compact line per frame, --seeds games, --frames cap each\n\
           --model PATH         load a learned model (adds it to --compare; use --policy learned)\n\
           --drive-model PATH   load a model and play its actions; the policy still labels\n\
           --physics            with --dataset: add each enemy's raw velocity and clock rate (ph)\n\
           --physics-model PATH load a learned enemy model; adds the hnn policy to --compare\n\
           --deaths             play --seeds games with the hnn policy, explain each death (NDJSON)\n\
           --survival           play --seeds games with --policy in parallel; print the mean survival\n\
           --epsilon P          per-frame chance of a random-action burst (label stays the policy's)\n\
                                (runs until death; --frames is ignored)\n\
         \n\
         Comparison:\n\
           --compare            run lookahead, landscape, potential, flee, random\n\
           --seeds N            number of consecutive seeds (default 1)\n\
         \n\
           --help               show this text\n"
    )
}
