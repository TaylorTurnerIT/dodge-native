//! Host-side checks that the browser build plays like the originals.
//!
//!   parity cnn          PyTorch vs Rust on recorded observations, then survival
//!   parity space S...   Python SpaceBot actions vs Rust, frame by frame
//!   parity danger S...  vendored drive() (run_episode) vs the frame-at-a-time Driver
//!   parity bots S...    survival and decision cost for every bot

use std::time::Instant;

use dodge_web::*;

const DIR: &str = env!("CARGO_MANIFEST_DIR");

fn survive(bot: u32, seed: u32, cap: u32) -> (u32, f64) {
    let mut sim = Sim::new(bot, seed, 3, true, true);
    let t0 = Instant::now();
    while !sim.dead && sim.frames < cap {
        sim.step(0);
    }
    let ms = t0.elapsed().as_secs_f64() * 1000.0 / f64::from(sim.frames.max(1));
    (sim.game.survival_frames(), ms)
}

fn cnn() {
    let bytes = std::fs::read(format!("{DIR}/parity/cnn_ref.bin")).expect("run tools/export_cnn.py");
    let floats: Vec<f32> = bytes.chunks_exact(4).map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]])).collect();
    let row = cnn::OBS + 9 + 1 + 1;
    let net = cnn::Cnn::load();
    let (mut worst_lp, mut worst_v, mut agree, mut n) = (0f32, 0f32, 0, 0);
    for r in floats.chunks_exact(row) {
        let out = net.forward(&r[..cnn::OBS]);
        for a in 0..9 {
            worst_lp = worst_lp.max((out.log_pmf[a] - r[cnn::OBS + a]).abs());
        }
        worst_v = worst_v.max((out.value - r[cnn::OBS + 9]).abs());
        agree += usize::from(out.action as f32 == r[cnn::OBS + 10]);
        n += 1;
    }
    println!("cnn: {n} recorded frames, max |dlog p| {worst_lp:.2e}, max |dV| {worst_v:.2e}, actions agree {agree}/{n}");
    let meta = std::fs::read_to_string(format!("{DIR}/parity/cnn_ref.json")).unwrap_or_default();
    println!("cnn: pytorch reference {}", meta.replace('\n', " "));
    for seed in 1..=3 {
        let (frames, ms) = survive(BOT_CNN, seed, 18_000);
        println!("cnn: seed {seed} rust survival {frames} ({ms:.2} ms/frame)");
    }
}

fn space(seeds: &[u32]) {
    for &seed in seeds {
        let path = format!("{DIR}/parity/space_s{seed}.bin");
        let Ok(reference) = std::fs::read(&path) else {
            println!("space: seed {seed}: no {path}");
            continue;
        };
        let mut sim = Sim::new(BOT_SPACE, seed, 3, true, true);
        let mut first_diff = None;
        let t0 = Instant::now();
        for (i, &want) in reference.iter().enumerate() {
            if sim.dead {
                break;
            }
            sim.step(0);
            if sim.last_action != usize::from(want) && first_diff.is_none() {
                first_diff = Some((i, sim.last_action, want));
                break;
            }
        }
        let ms = t0.elapsed().as_secs_f64() * 1000.0 / f64::from(sim.frames.max(1));
        match first_diff {
            None => println!("space: seed {seed}: all {} actions match; rust survival {} ({ms:.2} ms/frame)",
                             reference.len(), sim.game.survival_frames()),
            Some((i, got, want)) => println!("space: seed {seed}: first difference at frame {i}: rust {got}, python {want}"),
        }
    }
}

/// SpaceBot's overlay field (its room map) against Python's `overlay().field`.
fn spaceview(seeds: &[u32]) {
    for &seed in seeds {
        let path = format!("{DIR}/parity/spaceview_s{seed}.bin");
        let Ok(bytes) = std::fs::read(&path) else {
            println!("spaceview: seed {seed}: no {path}");
            continue;
        };
        let word = |at: usize| u32::from_le_bytes([bytes[at], bytes[at + 1], bytes[at + 2], bytes[at + 3]]);
        let mut sim = Sim::new(BOT_SPACE, seed, 3, true, true);
        let (mut at, mut samples, mut worst) = (0usize, 0, 0f64);
        while at < bytes.len() {
            let (frame, g) = (word(at), word(at + 4) as usize);
            at += 8;
            let want: Vec<f32> = (0..g * g).map(|i| f32::from_bits(word(at + 4 * i))).collect();
            at += 4 * g * g;
            while sim.frames <= frame {
                sim.step(0);
            }
            let Bot::Space(bot) = &sim.bot else { unreachable!() };
            let got = bot.room_view(g, 120.0);
            for (a, b) in got.iter().zip(&want) {
                worst = worst.max(f64::from((a - b).abs()));
            }
            samples += 1;
        }
        println!("spaceview: seed {seed}: {samples} sampled frames, max |d room| {worst:.3e} frames");
    }
}

fn danger(seeds: &[u32]) {
    use dodge_danger::{DangerConfig, PolicyKind, run_episode};
    for &seed in seeds {
        for (kind, bot) in [(PolicyKind::Landscape, BOT_LANDSCAPE), (PolicyKind::Lookahead, BOT_LOOKAHEAD)] {
            let config = DangerConfig { seed, difficulty: 3, patterns: true, powerups: true, max_frames: 18_000, ..DangerConfig::default() };
            let original = run_episode(&config, kind, false).expect("episode");
            let (ours, ms) = survive(bot, seed, 18_000);
            println!("danger: {kind:?} seed {seed}: drive() {} vs Driver {ours} ({ms:.2} ms/frame)", original.survival_frames);
        }
    }
}

fn bots(seeds: &[u32]) {
    let names = [(BOT_M0, "M0"), (BOT_RANDOM, "Random"), (BOT_BELIEF, "Belief")];
    for (bot, name) in names {
        for &seed in seeds {
            let (frames, ms) = survive(bot, seed, 18_000);
            println!("bots: {name} seed {seed}: {frames} frames ({ms:.3} ms/frame)");
        }
    }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let seeds: Vec<u32> = args.iter().skip(1).filter_map(|s| s.parse().ok()).collect();
    match args.first().map(String::as_str) {
        Some("cnn") => cnn(),
        Some("space") => space(&seeds),
        Some("spaceview") => spaceview(&seeds),
        Some("danger") => danger(&seeds),
        Some("bots") => bots(&seeds),
        Some("spacedbg") => {
            let mut sim = Sim::new(BOT_SPACE, seeds[0], 3, true, true);
            for f in 0..=seeds[1] {
                sim.step(0);
                if f + 1 >= seeds[1] {
                    if let Bot::Space(b) = &sim.bot {
                        println!("frame {f} action {} hit {:?}", sim.last_action, b.last.hit);
                        println!("  room {:?}", b.last.room);
                    }
                }
            }
        }
        _ => eprintln!("usage: parity cnn | space SEEDS | danger SEEDS | bots SEEDS"),
    }
}
