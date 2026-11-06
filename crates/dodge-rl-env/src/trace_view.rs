//! A slot's gameplay trace in the units and shapes the source binding returns
//! to Python: pixels as `f64`, a missing gap or pattern as `None`. Ported from
//! TaylorTurnerIT/dodge-ai-3 velocity-flow (`trace_dict`, `sample_dict`).
use dodge_core::{DeathContext, FrameSample, NativeGame, RectAtDeath, RunTrace};

fn pixels(raw: i32) -> f64 {
    f64::from(raw) / 65536.0
}

/// A gap in pixels; -1 (no such object) becomes `None`.
fn gap(raw: i32) -> Option<f64> {
    (raw >= 0).then(|| pixels(raw))
}

/// A pattern id, with 0 (none) as `None`.
fn pattern(id: u8) -> Option<u8> {
    (id != 0).then_some(id)
}

#[derive(Clone, Debug, PartialEq)]
pub struct SampleView {
    pub frame: u32,
    pub x: f64,
    pub y: f64,
    pub vx: f64,
    pub vy: f64,
    pub lethal_rect_gap: Option<f64>,
    pub pending_rect_gap: Option<f64>,
    pub enemy_gap: Option<f64>,
    pub enemies: u16,
    pub pattern_id: Option<u8>,
}

impl SampleView {
    pub fn new(sample: &FrameSample) -> Self {
        Self {
            frame: sample.frame,
            x: pixels(sample.x),
            y: pixels(sample.y),
            vx: pixels(sample.vx),
            vy: pixels(sample.vy),
            lethal_rect_gap: gap(sample.lethal_rect_gap),
            pending_rect_gap: gap(sample.pending_rect_gap),
            enemy_gap: gap(sample.enemy_gap),
            enemies: sample.enemies,
            pattern_id: pattern(sample.pattern_id),
        }
    }
}

/// `(x, y, width, height, lethal as 0 or 1)`, in pixels.
pub type RectView = (f64, f64, f64, f64, u8);

fn rects(list: &[RectAtDeath]) -> Vec<RectView> {
    list.iter()
        .map(|r| {
            (
                pixels(r.x),
                pixels(r.y),
                pixels(r.width),
                pixels(r.height),
                u8::from(r.lethal),
            )
        })
        .collect()
}

#[derive(Clone, Debug, PartialEq)]
pub struct TriggerView {
    pub frame: u32,
    pub spawned: u8,
}

#[derive(Clone, Debug, PartialEq)]
pub struct SpanView {
    pub id: u8,
    pub pattern_type: u8,
    pub start: u32,
    pub end: Option<u32>,
    pub x: Vec<f64>,
    pub y: Vec<f64>,
    pub rects: Vec<RectView>,
    pub rects_frame: Option<u32>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct KillerView {
    pub personality: i8,
    pub x: f64,
    pub y: f64,
    pub size: f64,
    pub fyou_spawned: Option<bool>,
    pub age: Option<u32>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct PlayerView {
    pub x: f64,
    pub y: f64,
    pub vx: f64,
    pub vy: f64,
    pub size: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct DeathPatternView {
    pub id: u8,
    pub pattern_type: u8,
    pub start: u32,
    pub since: u32,
}

/// The `recent` window as parallel columns.
#[derive(Clone, Debug, PartialEq)]
pub struct RecentView {
    pub frame: Vec<u32>,
    pub x: Vec<f64>,
    pub y: Vec<f64>,
    pub vx: Vec<f64>,
    pub vy: Vec<f64>,
    pub lethal_rect_gap: Vec<Option<f64>>,
    pub pending_rect_gap: Vec<Option<f64>>,
    pub enemy_gap: Vec<Option<f64>>,
    pub enemies: Vec<u16>,
    pub pattern_id: Vec<Option<u8>>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct DeathView {
    pub cause: &'static str,
    pub frame: u32,
    pub killer: Option<KillerView>,
    pub enemies_alive: Vec<u16>,
    pub player: PlayerView,
    pub active_pattern: Option<DeathPatternView>,
    pub rects: Vec<RectView>,
    /// `(frames before death, x, y)`.
    pub killer_path: Vec<(u32, f64, f64)>,
    pub recent: RecentView,
}

impl DeathView {
    fn new(death: &DeathContext) -> Self {
        let samples = &death.recent;
        Self {
            cause: death.cause.as_str(),
            frame: death.frame,
            killer: death.killer.map(|k| KillerView {
                personality: k.personality,
                x: pixels(k.x),
                y: pixels(k.y),
                size: pixels(k.size),
                fyou_spawned: k.fyou_spawned,
                age: k.age_frames,
            }),
            enemies_alive: death.enemies_alive.to_vec(),
            player: PlayerView {
                x: pixels(death.player_x_raw),
                y: pixels(death.player_y_raw),
                vx: pixels(death.player_vx_raw),
                vy: pixels(death.player_vy_raw),
                size: pixels(death.player_size_raw),
            },
            active_pattern: death.active_pattern.as_ref().map(|p| DeathPatternView {
                id: p.id,
                pattern_type: p.pattern_type,
                start: p.start_frame,
                since: p.frames_since_start,
            }),
            rects: rects(&death.rects),
            killer_path: death
                .killer_path
                .iter()
                .map(|(before, x, y)| (*before, pixels(*x), pixels(*y)))
                .collect(),
            recent: RecentView {
                frame: samples.iter().map(|s| s.frame).collect(),
                x: samples.iter().map(|s| pixels(s.x)).collect(),
                y: samples.iter().map(|s| pixels(s.y)).collect(),
                vx: samples.iter().map(|s| pixels(s.vx)).collect(),
                vy: samples.iter().map(|s| pixels(s.vy)).collect(),
                lethal_rect_gap: samples.iter().map(|s| gap(s.lethal_rect_gap)).collect(),
                pending_rect_gap: samples.iter().map(|s| gap(s.pending_rect_gap)).collect(),
                enemy_gap: samples.iter().map(|s| gap(s.enemy_gap)).collect(),
                enemies: samples.iter().map(|s| s.enemies).collect(),
                pattern_id: samples.iter().map(|s| pattern(s.pattern_id)).collect(),
            },
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct TraceView {
    pub frame: u32,
    pub fyou_triggers: Vec<TriggerView>,
    pub patterns: Vec<SpanView>,
    pub death: Option<DeathView>,
    /// Lethal contacts the engine processed on the fatal frame, by cause index.
    pub contacts: Vec<u16>,
}

impl TraceView {
    fn new(trace: &RunTrace, contacts: [u16; 6]) -> Self {
        Self {
            frame: trace.frame(),
            fyou_triggers: trace
                .fyou_triggers()
                .iter()
                .map(|t| TriggerView {
                    frame: t.frame,
                    spawned: t.spawned,
                })
                .collect(),
            patterns: trace
                .patterns()
                .iter()
                .map(|span| SpanView {
                    id: span.id,
                    pattern_type: span.pattern_type,
                    start: span.start_frame,
                    end: span.end_frame,
                    x: span.path.iter().map(|p| pixels(p.0)).collect(),
                    y: span.path.iter().map(|p| pixels(p.1)).collect(),
                    rects: rects(&span.rects),
                    rects_frame: span.rects_frame,
                })
                .collect(),
            death: trace.death().map(DeathView::new),
            contacts: contacts.to_vec(),
        }
    }

    /// `None` while the game's trace is off.
    pub fn read(game: &NativeGame) -> Option<Self> {
        let trace = game.run_trace();
        trace
            .enabled()
            .then(|| Self::new(trace, game.death_diagnostic().observed_contacts()))
    }
}

/// The latest frame sample, `None` while the trace is off or before the first
/// gameplay frame.
pub fn latest_sample(game: &NativeGame) -> Option<SampleView> {
    let trace = game.run_trace();
    trace
        .latest_sample()
        .filter(|_| trace.enabled())
        .map(|s| SampleView::new(&s))
}
