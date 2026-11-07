//! Frame-to-frame tracking using visible enemy geometry only.
use std::cell::RefCell;
use std::collections::VecDeque;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::OnceLock;

use dodge_core::NativeGame;
use serde::Deserialize;

#[derive(Clone, Copy, Debug)]
pub(crate) struct Sample {
    pub x: f64,
    pub y: f64,
    pub size: f64,
    pub kind: i8,
    pub player_x: f64,
    pub player_y: f64,
}

#[derive(Clone, Debug)]
pub(crate) struct Track {
    pub samples: VecDeque<Sample>,
    pub inside: bool,
    pub id: u64,
    pub age: usize,
    pub speed_factor: f64,
    serial: Option<dodge_core::EnemySerial>,
}

impl Track {
    pub fn size_velocity(&self) -> f64 {
        let n = self.samples.len();
        if n < 2 {
            return 0.0;
        }
        let mean = (n - 1) as f64 / 2.0;
        let denom: f64 = (0..n).map(|i| (i as f64 - mean).powi(2)).sum();
        self.samples
            .iter()
            .enumerate()
            .map(|(i, s)| (i as f64 - mean) * s.size)
            .sum::<f64>()
            / denom
    }
    pub fn velocity(&self) -> (f64, f64) {
        let n = self.samples.len();
        if n < 2 {
            return (0.0, 0.0);
        }
        let mean = (n - 1) as f64 / 2.0;
        let denom: f64 = (0..n).map(|i| (i as f64 - mean).powi(2)).sum();
        let fit = |f: fn(&Sample) -> f64| {
            self.samples
                .iter()
                .enumerate()
                .map(|(i, s)| (i as f64 - mean) * f(s))
                .sum::<f64>()
                / denom
        };
        (fit(|s| s.x), fit(|s| s.y))
    }
    pub fn growing(&self) -> bool {
        match (self.samples.front(), self.samples.back()) {
            (Some(first), Some(last)) if last.size < first.size - 1e-6 => false,
            _ => true,
        }
    }
}

#[derive(Default)]
struct Observation {
    tracks: Vec<Track>,
    frame: usize,
    next_id: u64,
    global_rate: f64,
    rate_frame: usize,
}
thread_local! { static CURRENT: RefCell<Observation> = RefCell::new(Observation::default()); }

pub fn enabled() -> bool {
    full() || std::env::var("HNN_OBS_ABLATION").is_ok_and(|v| !v.is_empty())
}
pub fn full() -> bool {
    std::env::var("HNN_OBSERVED").is_ok_and(|v| v == "1" || v == "2")
}
pub(crate) fn learned() -> bool {
    std::env::var("HNN_OBSERVED").is_ok_and(|v| v == "2")
}
pub(crate) fn improved() -> bool {
    std::env::var_os("HNN_OBS_LEGACY").is_none()
}
pub(crate) fn rate_enabled() -> bool {
    improved()
        && std::env::var("HNN_OBS_RATE_LS")
            .ok()
            .is_none_or(|v| v != "0")
}
pub(crate) fn centre_enabled() -> bool {
    improved()
        && std::env::var("HNN_OBS_BLAST_CENTRE")
            .ok()
            .is_none_or(|v| v != "0")
}
pub fn replace(name: &str) -> bool {
    full() || std::env::var("HNN_OBS_ABLATION").is_ok_and(|v| v == name)
}
static FRAMES: AtomicU64 = AtomicU64::new(0);
static BODY_FRAMES: AtomicU64 = AtomicU64::new(0);
static PRIOR: AtomicU64 = AtomicU64::new(0);
static MATCHES: AtomicU64 = AtomicU64::new(0);
static MISMATCHES: AtomicU64 = AtomicU64::new(0);
static DIAG_COUNT: [AtomicU64; 4] = [const { AtomicU64::new(0) }; 4];
static DIAG_VELOCITY: [AtomicU64; 4] = [const { AtomicU64::new(0) }; 4];
static DIAG_RATE: [AtomicU64; 4] = [const { AtomicU64::new(0) }; 4];
static TEMPO_COUNT: [AtomicU64; 16] = [const { AtomicU64::new(0) }; 16];
static TEMPO_SUM: [AtomicU64; 16] = [const { AtomicU64::new(0) }; 16];

pub(crate) fn tempo_sample(rate: f64) {
    let frame = CURRENT.with(|c| c.borrow().frame);
    let bin = (frame / 500).min(15);
    TEMPO_COUNT[bin].fetch_add(1, Ordering::Relaxed);
    TEMPO_SUM[bin].fetch_add((rate * 1_000_000.0) as u64, Ordering::Relaxed);
}
pub(crate) fn frame() -> usize {
    CURRENT.with(|c| c.borrow().frame)
}
pub(crate) fn global_rate(measured: Option<f64>, prior: f64) -> f64 {
    CURRENT.with(|c| {
        let mut c = c.borrow_mut();
        if c.rate_frame != c.frame {
            if c.global_rate <= 0.0 {
                c.global_rate = measured.unwrap_or(prior);
            } else {
                let target = measured.map_or(prior, |r| 0.98 * r + 0.02 * prior);
                c.global_rate = 0.8 * c.global_rate + 0.2 * target;
            }
            c.rate_frame = c.frame;
        }
        c.global_rate.max(0.2)
    })
}

/// Test-only comparison against engine labels. Values never feed the planner.
pub(crate) fn diagnostic(category: usize, velocity_error: f64, rate_error: f64) {
    DIAG_COUNT[category].fetch_add(1, Ordering::Relaxed);
    DIAG_VELOCITY[category].fetch_add((velocity_error * 1_000_000.0) as u64, Ordering::Relaxed);
    DIAG_RATE[category].fetch_add((rate_error * 1_000_000.0) as u64, Ordering::Relaxed);
}
/// Diagnostic counters only; identities are never used to choose a match.
pub fn report() {
    let frames = FRAMES.load(Ordering::Relaxed);
    let bodies = BODY_FRAMES.load(Ordering::Relaxed);
    eprintln!(
        "observation: frames={frames} body_frames={bodies} prior_body_frames={} identity_matches={} identity_mismatches={} mismatches_per_1000_frames={:.4}",
        PRIOR.load(Ordering::Relaxed),
        MATCHES.load(Ordering::Relaxed),
        MISMATCHES.load(Ordering::Relaxed),
        1000.0 * MISMATCHES.load(Ordering::Relaxed) as f64 / frames.max(1) as f64
    );
    for (i, label) in ["new", "abrupt", "blast", "other"].iter().enumerate() {
        let count = DIAG_COUNT[i].load(Ordering::Relaxed);
        if count > 0 {
            eprintln!("diagnostic {label}: count={count} velocity_mae_px_per_frame={:.5} rate_mape_percent={:.2}",
                DIAG_VELOCITY[i].load(Ordering::Relaxed) as f64 / count as f64 / 1_000_000.0,
                DIAG_RATE[i].load(Ordering::Relaxed) as f64 / count as f64 / 10_000.0);
        }
    }
    for i in 0..16 {
        let count = TEMPO_COUNT[i].load(Ordering::Relaxed);
        if count > 0 {
            eprintln!(
                "tempo bin={} count={count} mean={:.5}",
                i * 500,
                TEMPO_SUM[i].load(Ordering::Relaxed) as f64 / count as f64 / 1_000_000.0
            );
        }
    }
}

pub fn reset() {
    if std::env::var_os("HNN_OBS_KAMIKAZE_PROBE").is_some() {
        eprintln!("probe-reset");
    }
    CURRENT.with(|c| *c.borrow_mut() = Observation::default());
}

/// Record one state per frame, before any planner queries for that frame.
pub fn feed(game: &NativeGame) {
    if !enabled() {
        return;
    }
    FRAMES.fetch_add(1, Ordering::Relaxed);
    let serials: Vec<_> = std::env::var_os("HNN_OBS_DIAGNOSTIC")
        .and_then(|_| game.enemy_serials())
        .map(|ids| {
            game.enemies()
                .iter()
                .zip(ids)
                .filter(|(e, _)| e.personality < 2)
                .map(|(_, id)| Some(*id))
                .collect()
        })
        .unwrap_or_default();
    let samples: Vec<_> = game
        .enemies()
        .iter()
        .filter(|e| e.personality < 2)
        .map(|e| Sample {
            x: e.x.to_double(),
            y: e.y.to_double(),
            size: e.size.to_double(),
            kind: e.personality,
            player_x: game.player().x.to_double(),
            player_y: game.player().y.to_double(),
        })
        .collect();
    BODY_FRAMES.fetch_add(samples.len() as u64, Ordering::Relaxed);
    let window = std::env::var("HNN_OBS_WINDOW")
        .ok()
        .and_then(|s| s.parse::<usize>().ok())
        .unwrap_or(if rate_enabled() { 8 } else { 3 })
        .clamp(2, 8);
    CURRENT.with(|c| {
        let mut c = c.borrow_mut();
        c.frame += 1;
        let old = std::mem::take(&mut c.tracks);
        let mut next_id = c.next_id;
        let mut candidates = Vec::new();
        for (i, track) in old.iter().enumerate() {
            let Some(last) = track.samples.back() else {
                continue;
            };
            let (vx, vy) = if learned() && track.samples.len() >= 2 {
                let previous = track.samples[track.samples.len() - 2];
                (last.x - previous.x, last.y - previous.y)
            } else {
                track.velocity()
            };
            for (j, sample) in samples.iter().enumerate() {
                if sample.kind == last.kind {
                    let distance = (sample.x - last.x - vx).hypot(sample.y - last.y - vy);
                    if distance <= 2.0 {
                        candidates.push((distance, i, j));
                    }
                }
            }
        }
        candidates.sort_by(|a, b| a.0.total_cmp(&b.0));
        let mut used_old = vec![false; old.len()];
        let mut matches = vec![None; samples.len()];
        for (_, i, j) in candidates {
            if !used_old[i] && matches[j].is_none() {
                used_old[i] = true;
                matches[j] = Some(i);
            }
        }
        c.tracks = samples
            .into_iter()
            .enumerate()
            .map(|(j, sample)| {
                let mut track = matches[j].map(|i| old[i].clone()).unwrap_or_else(|| Track {
                    samples: VecDeque::new(),
                    inside: false,
                    id: {
                        let id = next_id;
                        next_id += 1;
                        id
                    },
                    age: 0,
                    speed_factor: 1.0,
                    serial: None,
                });
                track.age += 1;
                if sample.kind == 1 {
                    if let Some(before) = track.samples.back() {
                        let distance =
                            (before.x - sample.player_x).hypot(before.y - sample.player_y);
                        let change = if distance <= 26.0 { -0.007 } else { 0.007 };
                        track.speed_factor = (track.speed_factor + change).clamp(0.05, 1.0);
                    }
                }
                let serial = serials.get(j).copied().flatten();
                if let (Some(old), Some(now)) = (track.serial, serial) {
                    MATCHES.fetch_add(1, Ordering::Relaxed);
                    if old != now {
                        MISMATCHES.fetch_add(1, Ordering::Relaxed);
                    }
                }
                track.serial = serial;
                if track.samples.is_empty() {
                    PRIOR.fetch_add(1, Ordering::Relaxed);
                }
                track.inside |= (1.0..=128.0).contains(&sample.x);
                track.samples.push_back(sample);
                while track.samples.len() > window {
                    track.samples.pop_front();
                }
                track
            })
            .collect();
        c.next_id = next_id;
    });
}

pub(crate) fn tracks() -> Vec<Track> {
    CURRENT.with(|c| c.borrow().tracks.clone())
}

#[derive(Deserialize)]
struct LearnedWeights {
    #[serde(rename = "entity.weight")]
    entity_w: Vec<Vec<f64>>,
    #[serde(rename = "entity.bias")]
    entity_b: Vec<f64>,
    #[serde(rename = "global_hidden.weight")]
    global_w: Vec<Vec<f64>>,
    #[serde(rename = "global_hidden.bias")]
    global_b: Vec<f64>,
    #[serde(rename = "global_output.weight")]
    output_w: Vec<Vec<f64>>,
    #[serde(rename = "global_output.bias")]
    output_b: Vec<f64>,
    #[serde(rename = "local_hidden.weight")]
    local_w: Vec<Vec<f64>>,
    #[serde(rename = "local_hidden.bias")]
    local_b: Vec<f64>,
    #[serde(rename = "local_output.weight")]
    local_output_w: Vec<Vec<f64>>,
    #[serde(rename = "local_output.bias")]
    local_output_b: Vec<f64>,
}

#[derive(Deserialize)]
struct LearnedModel {
    format: String,
    history: usize,
    state: LearnedWeights,
}

fn affine(input: &[f64], weights: &[Vec<f64>], bias: &[f64], tanh: bool) -> Vec<f64> {
    weights
        .iter()
        .zip(bias)
        .map(|(row, b)| {
            let value = row.iter().zip(input).map(|(w, x)| w * x).sum::<f64>() + b;
            if tanh {
                value.tanh()
            } else {
                value
            }
        })
        .collect()
}

/// Global tempo and per-track velocity/factor from visible geometry only.
pub(crate) fn infer(tracks: &[Track]) -> (f64, Vec<Option<(f64, f64, f64)>>) {
    static MODEL: OnceLock<LearnedModel> = OnceLock::new();
    let model = MODEL.get_or_init(|| {
        let path = std::env::var("HNN_OBS_MODEL")
            .unwrap_or_else(|_| format!("{}/models/observed.json", env!("CARGO_MANIFEST_DIR")));
        let result = std::fs::read_to_string(&path)
            .map_err(|e| e.to_string())
            .and_then(|text| {
                serde_json::from_str::<LearnedModel>(&text).map_err(|e| e.to_string())
            });
        match result {
            Ok(model) if model.format == "observed_estimator_v1" && model.history == 5 => model,
            Ok(_) => {
                eprintln!("unsupported observed estimator model");
                std::process::exit(2)
            }
            Err(e) => {
                eprintln!("cannot load observed estimator from {path}: {e}");
                std::process::exit(2)
            }
        }
    });
    let w = &model.state;
    let frame = frame() as f64;
    let mut embedded = Vec::new();
    for (index, track) in tracks.iter().enumerate() {
        if track.samples.len() < 5 {
            continue;
        }
        let n = track.samples.len();
        let last = track.samples[n - 1];
        if !(0..=1).contains(&last.kind) {
            continue;
        }
        let mut x = Vec::with_capacity(16);
        for i in n - 4..n {
            x.push(track.samples[i].x - track.samples[i - 1].x);
            x.push(track.samples[i].y - track.samples[i - 1].y);
        }
        x.extend([
            (last.x - last.player_x) / 128.0,
            (last.y - last.player_y) / 128.0,
            f64::from(last.kind),
            (track.age as f64 / 300.0).min(3.0),
            last.x / 128.0,
            last.y / 128.0,
            last.size / 30.0,
            (frame / 8000.0).min(1.5),
        ]);
        let h = affine(&x, &w.entity_w, &w.entity_b, true);
        embedded.push((index, x, h));
        if embedded.len() == 24 {
            break;
        }
    }
    let mut predictions = vec![None; tracks.len()];
    if embedded.is_empty() {
        return (2.15, predictions);
    }
    let mut pooled = vec![0.0; w.entity_b.len()];
    for (_, _, h) in &embedded {
        for (p, v) in pooled.iter_mut().zip(h) {
            *p += v / embedded.len() as f64;
        }
    }
    let h = affine(&pooled, &w.global_w, &w.global_b, true);
    let logit = affine(&h, &w.output_w, &w.output_b, false)[0];
    let global = 0.3 + 3.7 / (1.0 + (-logit).exp());
    for (index, x, h) in embedded {
        let h = affine(&h, &w.local_w, &w.local_b, true);
        let local = affine(&h, &w.local_output_w, &w.local_output_b, false);
        let factor = if x[10] > 0.5 {
            2.0 / (1.0 + (-local[2]).exp())
        } else {
            1.0
        };
        let rate = (global * factor).max(0.05);
        predictions[index] = Some((
            x[6] / rate + 0.1 * local[0].tanh(),
            x[7] / rate + 0.1 * local[1].tanh(),
            factor,
        ));
    }
    (global, predictions)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn linear_fit_and_size_trend() {
        let mut track = Track {
            samples: VecDeque::new(),
            inside: false,
            id: 0,
            age: 0,
            speed_factor: 1.0,
            serial: None,
        };
        assert_eq!(track.velocity(), (0.0, 0.0));
        for i in 0..5 {
            track.samples.push_back(Sample {
                x: 4.0 + i as f64 * 0.5,
                y: 9.0 - i as f64,
                size: 5.0 - i as f64,
                kind: -1,
                player_x: 0.0,
                player_y: 0.0,
            });
        }
        assert_eq!(track.velocity(), (0.5, -1.0));
        assert!(!track.growing());
    }
}
