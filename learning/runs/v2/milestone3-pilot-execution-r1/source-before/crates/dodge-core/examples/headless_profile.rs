//! Matched local stepping microbenchmark, not the unmodified-engine M0 baseline.
//!
//! Run with `cargo +1.97.1 run --release -p dodge-core --example headless_profile`.
//! Uses 64 fresh seeds, deterministic K=4 random actions, immediate death stops,
//! and a 2,000-frame cap. Startup, initialization, schedule generation, and final
//! state comparisons are outside timings. Five rounds rotate execution order.
//! Reports stepping wall time only; it does not measure allocation counts.
use std::{hint::black_box, time::Instant};

use dodge_core::{
    Action, BUTTON_X_MASK, CoreError, FRAMEBUFFER_SIZE, FullState, IndexedFramebuffer, Mode,
    NativeConfig, NativeGame, PicoFixed, PicoRng,
};

const SEEDS: u32 = 64;
const ROUNDS: usize = 5;

#[derive(Clone, Copy)]
enum Path {
    Full,
    Headless,
    RenderK4,
}

struct Episode {
    seed: u32,
    masks: Vec<u8>,
    final_state: FullState,
}

fn started(seed: u32, path: Path) -> Result<NativeGame, CoreError> {
    let mut game = NativeGame::new(NativeConfig::new(seed));
    for frame in 0..13 {
        let mask = if frame == 0 { BUTTON_X_MASK } else { 0 };
        match path {
            Path::Full => {
                black_box(game.advance_frame(mask)?);
            }
            Path::Headless | Path::RenderK4 => {
                black_box(game.advance_frame_headless(mask)?);
            }
        }
    }
    if game.lifecycle().mode != Mode::Game {
        return Err(CoreError::InvalidSnapshotValue);
    }
    Ok(game)
}

fn logical_state(game: &NativeGame) -> FullState {
    let mut state = game.snapshot().logical_state().clone();
    state.physical_screen = IndexedFramebuffer::blank();
    state
}

fn schedules() -> Result<Vec<Episode>, CoreError> {
    let mut episodes = Vec::new();
    for seed in 1000..1000 + SEEDS {
        let mut game = started(seed, Path::Headless)?;
        let mut rng = PicoRng::new(seed + 10_000);
        let mut masks = Vec::new();
        let mut mask = 0;
        for frame in 0..2000 {
            if frame % 4 == 0 {
                let index = rng.rnd(PicoFixed::from_int(9)).floor().raw() >> 16;
                mask = Action::ALL
                    .get(index as usize)
                    .copied()
                    .ok_or(CoreError::InvalidActionName)?
                    .mask();
            }
            masks.push(mask);
            if game.advance_frame_headless(mask)?.dead {
                break;
            }
        }
        episodes.push(Episode {
            seed,
            masks,
            final_state: logical_state(&game),
        });
    }
    Ok(episodes)
}

fn measure(episodes: &[Episode], path: Path) -> Result<f64, CoreError> {
    let mut seconds = 0.0;
    for episode in episodes {
        let mut game = started(episode.seed, path)?;
        let mut pixels = [0; FRAMEBUFFER_SIZE];
        let begin = Instant::now();
        for (frame, &mask) in episode.masks.iter().enumerate() {
            match path {
                Path::Full => {
                    black_box(game.advance_frame(black_box(mask))?);
                }
                Path::Headless | Path::RenderK4 => {
                    black_box(game.advance_frame_headless(black_box(mask))?);
                    if matches!(path, Path::RenderK4) && (frame + 1) % 4 == 0 {
                        game.render_into(black_box(&mut pixels));
                        black_box(&pixels);
                    }
                }
            }
        }
        seconds += begin.elapsed().as_secs_f64();
        if logical_state(&game) != episode.final_state {
            return Err(CoreError::InvalidSnapshotValue);
        }
    }
    Ok(seconds)
}

fn median(values: &[f64]) -> Result<f64, CoreError> {
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    sorted
        .get(sorted.len() / 2)
        .copied()
        .ok_or(CoreError::InvalidSnapshotValue)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let episodes = schedules()?;
    let frames: usize = episodes.iter().map(|e| e.masks.len()).sum();
    let deaths = episodes
        .iter()
        .filter(|e| e.final_state.lifecycle.dead)
        .count();
    let mut full = Vec::new();
    let mut headless = Vec::new();
    let mut render_k4 = Vec::new();
    // Warm each path before timed rounds.
    for path in [Path::Full, Path::Headless, Path::RenderK4] {
        black_box(measure(&episodes, path)?);
    }
    for round in 0..ROUNDS {
        let order = match round % 3 {
            0 => [Path::Full, Path::Headless, Path::RenderK4],
            1 => [Path::Headless, Path::RenderK4, Path::Full],
            _ => [Path::RenderK4, Path::Full, Path::Headless],
        };
        for path in order {
            let seconds = measure(&episodes, path)?;
            match path {
                Path::Full => full.push(seconds),
                Path::Headless => headless.push(seconds),
                Path::RenderK4 => render_k4.push(seconds),
            }
        }
    }
    let full_median = median(&full)?;
    let headless_median = median(&headless)?;
    let render_median = median(&render_k4)?;
    println!(
        "{{\"kind\":\"modified-core matched stepping microbenchmark\",\"seeds\":\"1000..1064\",\"difficulty\":2,\"patterns_enabled\":true,\"powerups_enabled\":true,\"action_repeat\":4,\"cap_raw_frames\":2000,\"episodes\":{},\"deaths\":{deaths},\"raw_frames_per_round\":{frames},\"rounds\":{ROUNDS},\"full_seconds\":{full:?},\"headless_seconds\":{headless:?},\"headless_render_k4_seconds\":{render_k4:?},\"full_median_sps\":{},\"headless_median_sps\":{},\"headless_render_k4_median_sps\":{},\"headless_speedup\":{},\"render_k4_speedup\":{},\"final_logical_states_match\":true}}",
        episodes.len(),
        frames as f64 / full_median,
        frames as f64 / headless_median,
        frames as f64 / render_median,
        full_median / headless_median,
        full_median / render_median
    );
    Ok(())
}
