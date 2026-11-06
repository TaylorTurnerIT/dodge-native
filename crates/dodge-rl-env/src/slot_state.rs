//! One slot's raw game state under the cartridge's own names: what a scripted
//! controller reads, and what checks the native VelocityFlow encoder against a
//! reference implementation. Ported from TaylorTurnerIT/dodge-ai-3
//! velocity-flow (`lane_state`); the keys, units and types are the same.
//! Positions and sizes are pixels (f64), as `PicoFixed::to_double` gives them.
use dodge_core::NativeGame;

#[derive(Clone, Debug, PartialEq)]
pub struct EnemyState {
    pub x: f64,
    pub y: f64,
    pub s: f64,
    /// Personality: 0 normal, 1 and -1 kamikaze.
    pub p: i8,
    pub vx: f64,
    pub vy: f64,
    pub spd: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RectState {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
    pub sh: f64,
    pub dx: f64,
    pub dy: f64,
    pub spd: f64,
    /// `(x0, y0, x1, y1)` per warning line.
    pub warnings: Vec<(f64, f64, f64, f64)>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct PatternSnapshot {
    pub id: u8,
    pub tpe: u8,
    pub timer: f64,
    pub rects: Vec<RectState>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct SlotState {
    pub px: f64,
    pub py: f64,
    pub dpx: f64,
    pub dpy: f64,
    pub size: f64,
    pub ftimer: u32,
    pub fy: bool,
    pub spd: f64,
    pub frz: f64,
    pub enemies: Vec<EnemyState>,
    /// The active pattern, `None` between patterns.
    pub cp: Option<PatternSnapshot>,
}

impl SlotState {
    pub fn read(game: &NativeGame) -> Self {
        let player = game.player();
        let view = game.privileged_view();
        let enemies = game
            .enemies()
            .iter()
            .map(|e| EnemyState {
                x: e.x.to_double(),
                y: e.y.to_double(),
                s: e.size.to_double(),
                p: e.personality,
                vx: e.vx.to_double(),
                vy: e.vy.to_double(),
                spd: e.speed.to_double(),
            })
            .collect();
        let cp = game
            .active_pattern_index()
            .and_then(|index| game.patterns().get(index))
            .map(|pattern| PatternSnapshot {
                id: pattern.id,
                tpe: pattern.pattern_type,
                timer: pattern.timer.to_double(),
                rects: pattern
                    .rects
                    .iter()
                    .map(|rect| RectState {
                        x: rect.x.to_double(),
                        y: rect.y.to_double(),
                        w: rect.width.to_double(),
                        h: rect.height.to_double(),
                        sh: rect.sh.to_double(),
                        dx: rect.dx.to_double(),
                        dy: rect.dy.to_double(),
                        spd: rect.speed.to_double(),
                        warnings: rect
                            .warnings
                            .iter()
                            .map(|l| {
                                (
                                    l.x0.to_double(),
                                    l.y0.to_double(),
                                    l.x1.to_double(),
                                    l.y1.to_double(),
                                )
                            })
                            .collect(),
                    })
                    .collect(),
            });
        Self {
            px: player.x.to_double(),
            py: player.y.to_double(),
            dpx: player.vx.to_double(),
            dpy: player.vy.to_double(),
            size: player.size.to_double(),
            ftimer: game.friendly_timer(),
            fy: game.friendly_enabled(),
            spd: view.speed.to_double(),
            frz: view.freeze_rate.to_double(),
            enemies,
            cp,
        }
    }
}
