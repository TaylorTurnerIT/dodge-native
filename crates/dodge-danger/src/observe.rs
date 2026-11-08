//! Frame-to-frame tracking using visible enemy geometry only.
use std::cell::RefCell;
use std::collections::VecDeque;
use std::sync::OnceLock;
use std::sync::atomic::{AtomicU64, Ordering};

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
    pub(crate) serial: Option<dodge_core::EnemySerial>,
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

#[derive(Clone, Copy)]
struct NoiseConfig {
    sigma: f64,
    quantize: bool,
    dropout: f64,
    confusion: f64,
    phantom_rate: f64,
}

impl NoiseConfig {
    fn from_env() -> Option<Self> {
        if std::env::var("HNN_NOISE").ok().as_deref() != Some("1") {
            return None;
        }
        let number = |name: &str| {
            std::env::var(name)
                .ok()
                .and_then(|v| v.parse::<f64>().ok())
                .filter(|v| v.is_finite())
                .unwrap_or(0.0)
        };
        Some(Self {
            sigma: number("HNN_NOISE_SIGMA").max(0.0),
            quantize: std::env::var("HNN_NOISE_QUANTIZE").ok().as_deref() == Some("1"),
            dropout: number("HNN_NOISE_DROPOUT").clamp(0.0, 1.0),
            confusion: number("HNN_NOISE_CONFUSION").clamp(0.0, 1.0),
            phantom_rate: number("HNN_NOISE_PHANTOM_RATE").clamp(0.0, 1.0),
        })
    }
}

struct Noise {
    rng: u64,
    phantoms: Vec<(Sample, u8)>,
}

impl Default for Noise {
    fn default() -> Self {
        let seed = std::env::var("HNN_NOISE_SEED")
            .ok()
            .and_then(|v| v.parse::<u64>().ok())
            .unwrap_or(1847);
        Self {
            rng: seed,
            phantoms: Vec::new(),
        }
    }
}

impl Noise {
    fn uniform(&mut self) -> f64 {
        self.rng = self.rng.wrapping_add(0x9e3779b97f4a7c15);
        let mut z = self.rng;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
        ((z ^ (z >> 31)) >> 11) as f64 / ((1_u64 << 53) as f64)
    }
    fn normal(&mut self) -> f64 {
        let u = (1.0 - self.uniform()).max(f64::MIN_POSITIVE);
        (-2.0 * u.ln()).sqrt() * (std::f64::consts::TAU * self.uniform()).cos()
    }
    fn apply(
        &mut self,
        config: NoiseConfig,
        samples: Vec<(Sample, Option<dodge_core::EnemySerial>)>,
        player: (f64, f64),
    ) -> Vec<(Sample, Option<dodge_core::EnemySerial>)> {
        let mut out = Vec::new();
        for (mut sample, serial) in samples {
            // Explosions are not enemy detections, but their geometry is still visible.
            if sample.kind >= 0 && self.uniform() < config.dropout {
                continue;
            }
            sample.x += config.sigma * self.normal();
            sample.y += config.sigma * self.normal();
            if config.quantize {
                sample.x = sample.x.round();
                sample.y = sample.y.round();
                sample.size = sample.size.round();
            }
            if sample.kind >= 0 && self.uniform() < config.confusion {
                sample.kind = 1 - sample.kind;
            }
            out.push((sample, serial));
        }
        if self.uniform() < config.phantom_rate {
            let sample = Sample {
                x: 128.0 * self.uniform(),
                y: 128.0 * self.uniform(),
                size: 8.0,
                kind: if self.uniform() < 0.5 { 0 } else { 1 },
                player_x: player.0,
                player_y: player.1,
            };
            let lifetime = 1 + (self.uniform() * 3.0) as u8;
            self.phantoms.push((sample, lifetime));
        }
        for (sample, left) in &mut self.phantoms {
            sample.player_x = player.0;
            sample.player_y = player.1;
            out.push((*sample, None));
            *left -= 1;
        }
        self.phantoms.retain(|(_, left)| *left > 0);
        out
    }
}

#[derive(Default)]
struct Observation {
    tracks: Vec<Track>,
    frame: usize,
    next_id: u64,
    global_rate: f64,
    rate_frame: usize,
    noise: Noise,
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
// Diagnostic-only sums: count, prediction, truth, squares, product, absolute error.
static LABELS: [[AtomicU64; 7]; 3] = [const { [const { AtomicU64::new(0) }; 7] }; 3];
static LABEL_CURVE_COUNT: [AtomicU64; 16] = [const { AtomicU64::new(0) }; 16];
static LABEL_CURVE_SUM: [AtomicU64; 16] = [const { AtomicU64::new(0) }; 16];

fn add_float(slot: &AtomicU64, value: f64) {
    let _ = slot.fetch_update(Ordering::Relaxed, Ordering::Relaxed, |old| {
        Some((f64::from_bits(old) + value).to_bits())
    });
}

pub(crate) fn label_error(category: usize, prediction: f64, truth: f64) {
    let slots = &LABELS[category];
    slots[0].fetch_add(1, Ordering::Relaxed);
    for (slot, value) in slots[1..].iter().zip([
        prediction,
        truth,
        prediction * prediction,
        truth * truth,
        prediction * truth,
        (prediction - truth).abs(),
    ]) {
        add_float(slot, value);
    }
    if category == 0 {
        let bin = (frame() / 500).min(15);
        LABEL_CURVE_COUNT[bin].fetch_add(1, Ordering::Relaxed);
        add_float(&LABEL_CURVE_SUM[bin], prediction);
    }
}

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
            eprintln!(
                "diagnostic {label}: count={count} velocity_mae_px_per_frame={:.5} rate_mape_percent={:.2}",
                DIAG_VELOCITY[i].load(Ordering::Relaxed) as f64 / count as f64 / 1_000_000.0,
                DIAG_RATE[i].load(Ordering::Relaxed) as f64 / count as f64 / 10_000.0
            );
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
    for (i, label) in ["global_rate", "raw_velocity_component", "kamikaze_factor"]
        .iter()
        .enumerate()
    {
        let s = &LABELS[i];
        let n = s[0].load(Ordering::Relaxed) as f64;
        if n > 1.0 {
            let sums: Vec<f64> = s[1..]
                .iter()
                .map(|x| f64::from_bits(x.load(Ordering::Relaxed)))
                .collect();
            let covariance = sums[4] - sums[0] * sums[1] / n;
            let variance = ((sums[2] - sums[0] * sums[0] / n) * (sums[3] - sums[1] * sums[1] / n))
                .max(0.0)
                .sqrt();
            let correlation = if variance > 0.0 {
                covariance / variance
            } else {
                0.0
            };
            eprintln!(
                "label {label}: count={} mae={:.6} correlation={:.5}",
                n as u64,
                sums[5] / n,
                correlation
            );
        }
    }
    for i in 0..16 {
        let count = LABEL_CURVE_COUNT[i].load(Ordering::Relaxed);
        if count > 0 {
            eprintln!(
                "label global_curve frame={} count={count} mean={:.5}",
                i * 500,
                f64::from_bits(LABEL_CURVE_SUM[i].load(Ordering::Relaxed)) / count as f64
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
    let samples: Vec<_> = samples
        .into_iter()
        .enumerate()
        .map(|(i, sample)| (sample, serials.get(i).copied().flatten()))
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
        let samples = if let Some(config) = NoiseConfig::from_env() {
            c.noise.apply(
                config,
                samples,
                (game.player().x.to_double(), game.player().y.to_double()),
            )
        } else {
            samples
        };
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
            for (j, (sample, _)) in samples.iter().enumerate() {
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
            .map(|(j, (sample, serial))| {
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
            if tanh { value.tanh() } else { value }
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
    fn seeded_noise_is_repeatable_and_quantized() {
        let config = NoiseConfig {
            sigma: 0.5,
            quantize: true,
            dropout: 0.0,
            confusion: 1.0,
            phantom_rate: 0.0,
        };
        let sample = Sample {
            x: 12.25,
            y: 23.75,
            size: 7.7,
            kind: 0,
            player_x: 0.0,
            player_y: 0.0,
        };
        let mut a = Noise {
            rng: 7,
            phantoms: Vec::new(),
        };
        let mut b = Noise {
            rng: 7,
            phantoms: Vec::new(),
        };
        let x = a.apply(config, vec![(sample, None)], (0.0, 0.0))[0].0;
        let y = b.apply(config, vec![(sample, None)], (0.0, 0.0))[0].0;
        assert_eq!((x.x, x.y, x.size, x.kind), (y.x, y.y, y.size, y.kind));
        assert_eq!(
            (x.x.fract(), x.y.fract(), x.size, x.kind),
            (0.0, 0.0, 8.0, 1)
        );
        let dropped = a.apply(
            NoiseConfig {
                dropout: 1.0,
                ..config
            },
            vec![(sample, None)],
            (0.0, 0.0),
        );
        assert!(dropped.is_empty());
    }

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
