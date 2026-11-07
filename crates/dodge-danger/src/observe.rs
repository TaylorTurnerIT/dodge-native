//! Frame-to-frame tracking using visible enemy geometry only.
use std::cell::RefCell;
use std::collections::VecDeque;

use dodge_core::NativeGame;

#[derive(Clone, Copy, Debug)]
pub(crate) struct Sample {
    pub x: f64,
    pub y: f64,
    pub size: f64,
    pub kind: i8,
}

#[derive(Clone, Debug)]
pub(crate) struct Track {
    pub samples: VecDeque<Sample>,
    pub inside: bool,
}

impl Track {
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
}
thread_local! { static CURRENT: RefCell<Observation> = RefCell::new(Observation::default()); }

pub fn enabled() -> bool {
    std::env::var("HNN_OBSERVED").is_ok_and(|v| v == "1")
}

pub fn reset() {
    CURRENT.with(|c| *c.borrow_mut() = Observation::default());
}

/// Record one state per frame, before any planner queries for that frame.
pub fn feed(game: &NativeGame) {
    if !enabled() {
        return;
    }
    let samples: Vec<_> = game
        .enemies()
        .iter()
        .filter(|e| e.personality < 2)
        .map(|e| Sample {
            x: e.x.to_double(),
            y: e.y.to_double(),
            size: e.size.to_double(),
            kind: e.personality,
        })
        .collect();
    let window = std::env::var("HNN_OBS_WINDOW")
        .ok()
        .and_then(|s| s.parse::<usize>().ok())
        .unwrap_or(3)
        .clamp(2, 5);
    CURRENT.with(|c| {
        let mut c = c.borrow_mut();
        let old = std::mem::take(&mut c.tracks);
        let mut candidates = Vec::new();
        for (i, track) in old.iter().enumerate() {
            let Some(last) = track.samples.back() else {
                continue;
            };
            let (vx, vy) = track.velocity();
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
                });
                track.inside |= (1.0..=128.0).contains(&sample.x);
                track.samples.push_back(sample);
                while track.samples.len() > window {
                    track.samples.pop_front();
                }
                track
            })
            .collect();
    });
}

pub(crate) fn tracks() -> Vec<Track> {
    CURRENT.with(|c| c.borrow().tracks.clone())
}
