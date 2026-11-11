//! SpaceBot, ported line for line from `learning/dodge/heuristics/space.py`.
//!
//! The Python version is vectorised numpy over (9 plans, N movers); here the
//! same arrays are explicit loops in the same order of operations, so the two
//! choose the same action from the same `SlotState`. Where numpy semantics
//! differ from Rust's (np.sign(0) == 0, pairwise summation in `sum`), they are
//! reproduced.

use dodge_rl_env::SlotState;

const ONE: i64 = 65536;
const F08: i64 = 52428;
const HALF: i64 = 32768;
const LO: i64 = 2 * ONE;
const HI: i64 = 125 * ONE;
const MASKS: [u8; 9] = [0, 1, 2, 4, 8, 5, 6, 9, 10];
const E_FRICTION: f64 = 64880.0 / 65536.0;
const E_ACCEL: f64 = 655.0 / 65536.0;

const HORIZON: usize = 24;
const ROOM_TMAX: f64 = 60.0;
const ROOM_CAP: f64 = 30.0;
const GRIDN: usize = 12;
const W_CLEAR: f64 = 0.3;
const CLEAR_CAP: f64 = 16.0;
const CENTRE_GUARD: f64 = 35.0;
const W_SWEEP: f64 = 1.0;
const SWEEP_MARGIN: f64 = 30.0;
const W_SEEK: f64 = 0.5;
const BOUNCE_CAP: f64 = 0.6;
const INF: f64 = f64::INFINITY;

fn pickup_value(p: i8) -> f64 {
    match p {
        2 => 2.0,
        3 => 0.8,
        4 => 0.5,
        _ => 0.0,
    }
}

#[inline]
fn sign(v: f64) -> f64 {
    if v > 0.0 {
        1.0
    } else if v < 0.0 {
        -1.0
    } else {
        0.0
    }
}

#[inline]
fn clip(v: f64, lo: f64, hi: f64) -> f64 {
    // np.clip(a, lo, hi) == minimum(maximum(a, lo), hi)
    v.max(lo).min(hi)
}

/// numpy's pairwise summation, as `np.add.reduce` uses it on a contiguous axis.
fn pairwise(a: &[f64]) -> f64 {
    let n = a.len();
    if n < 8 {
        let mut res = 0.0;
        for v in a {
            res += v;
        }
        res
    } else if n <= 128 {
        let mut r = [0.0; 8];
        r.copy_from_slice(&a[..8]);
        let mut i = 8;
        while i < n - (n % 8) {
            for j in 0..8 {
                r[j] += a[i + j];
            }
            i += 8;
        }
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            res += a[i];
            i += 1;
        }
        res
    } else {
        let mut n2 = n / 2;
        n2 -= n2 % 8;
        pairwise(&a[..n2]) + pairwise(&a[n2..])
    }
}

/// `ndarray.sum(axis=-1)` on a contiguous row: numpy 2.x runs the pairwise
/// sum over the whole row (checked against numpy 2.4.6 on 18,000 random rows).
fn np_sum(a: &[f64]) -> f64 {
    pairwise(a)
}

fn gap(ax0: f64, ay0: f64, ax1: f64, ay1: f64, bx0: f64, by0: f64, bx1: f64, by1: f64) -> f64 {
    let x = (bx0 - ax1).max(ax0 - bx1);
    let y = (by0 - ay1).max(ay0 - by1);
    if x <= 0.0 && y <= 0.0 { x.max(y) } else { x.max(0.0).hypot(y.max(0.0)) }
}

/// x0 y0 x1 y1 vx vy lethal_after half move_from grow emin emax
type BoxRow = [f64; 12];

fn box_at(b: &BoxRow, t: f64) -> (f64, f64, f64, f64) {
    let m = (t - b[8]).max(0.0);
    let e = clip(t * b[9], b[10], b[11]);
    (b[0] + m * b[4] - e, b[1] + m * b[5] - e, b[2] + m * b[4] + e, b[3] + m * b[5] + e)
}

fn player_paths(x: i64, y: i64, vx: i64, vy: i64) -> Vec<[[f64; 2]; HORIZON + 1]> {
    let mut out = vec![[[0.0; 2]; HORIZON + 1]; 9];
    for (a, &mask) in MASKS.iter().enumerate() {
        let (mut px, mut py, mut pvx, mut pvy) = (x, y, vx, vy);
        out[a][0] = [px as f64 / ONE as f64, py as f64 / ONE as f64];
        for t in 1..=HORIZON {
            pvx = (pvx * F08) >> 16;
            pvy = (pvy * F08) >> 16;
            if mask & 1 != 0 { pvx -= HALF; }
            if mask & 2 != 0 { pvx += HALF; }
            if mask & 4 != 0 { pvy -= HALF; }
            if mask & 8 != 0 { pvy += HALF; }
            px = (px + pvx).clamp(LO, HI);
            py = (py + pvy).clamp(LO, HI);
            out[a][t] = [px as f64 / ONE as f64, py as f64 / ONE as f64];
        }
    }
    out
}

fn raw(v: f64) -> i64 {
    (v * ONE as f64).round() as i64
}

/// Enemies projected past the plan, per plan: (9, N) each.
#[derive(Clone)]
struct Projected {
    ex: Vec<Vec<f64>>,
    ey: Vec<Vec<f64>>,
    vx: Vec<Vec<f64>>,
    vy: Vec<Vec<f64>>,
    sp: Vec<Vec<f64>>,
    es: Vec<f64>,
}

/// The last decision, for drawing.
#[derive(Clone, Default)]
pub struct Decision {
    pub best: usize,
    pub path: Vec<(f64, f64)>,
    pub hit: [f64; 9],
    pub score: [f64; 9],
    pub room: [f64; 9],
    ends: Vec<[f64; 2]>,
    size: f64,
    step: f64,
    enemies: Option<Projected>,
    boxes: Vec<BoxRow>,
}

pub struct SpaceBot {
    prev_pattern: Option<u8>,
    prev_rects: Vec<[f64; 4]>,
    prev_sh: Vec<f64>,
    rect_change: Vec<[f64; 4]>,
    sh_change: Vec<Option<f64>>,
    prev_blasts: Vec<(f64, f64, f64)>,
    cx: Vec<f64>,
    cy: Vec<f64>,
    t: Vec<f64>,
    pub last: Decision,
}

impl Default for SpaceBot {
    fn default() -> Self {
        Self::new()
    }
}

impl SpaceBot {
    pub fn new() -> Self {
        let centres: Vec<f64> = (0..GRIDN).map(|i| (i as f64 + 0.5) * (128.0 / GRIDN as f64)).collect();
        let mut cx = Vec::new();
        let mut cy = Vec::new();
        for i in 0..GRIDN {
            for j in 0..GRIDN {
                cx.push(centres[i]);
                cy.push(centres[j]);
            }
        }
        let t = (0..=(ROOM_TMAX as usize)).step_by(4).map(|v| v as f64).collect();
        Self {
            prev_pattern: None,
            prev_rects: Vec::new(),
            prev_sh: Vec::new(),
            rect_change: Vec::new(),
            sh_change: Vec::new(),
            prev_blasts: Vec::new(),
            cx,
            cy,
            t,
            last: Decision::default(),
        }
    }

    pub fn observe(&mut self, s: &SlotState) {
        let pid = s.cp.as_ref().map(|cp| cp.id);
        let rects: Vec<[f64; 4]> = s.cp.as_ref().map_or(Vec::new(), |cp| {
            cp.rects.iter().map(|r| [r.x, r.y, r.x + r.w - 1.0, r.y + r.h - 1.0]).collect()
        });
        let shs: Vec<f64> = s.cp.as_ref().map_or(Vec::new(), |cp| cp.rects.iter().map(|r| r.sh).collect());
        let same = pid == self.prev_pattern;
        self.rect_change = rects
            .iter()
            .enumerate()
            .map(|(i, b)| {
                if same && i < self.prev_rects.len() {
                    let o = self.prev_rects[i];
                    [b[0] - o[0], b[1] - o[1], b[2] - o[2], b[3] - o[3]]
                } else {
                    [0.0; 4]
                }
            })
            .collect();
        self.sh_change = shs
            .iter()
            .enumerate()
            .map(|(i, sh)| if same && i < self.prev_sh.len() { Some(sh - self.prev_sh[i]) } else { None })
            .collect();
        self.prev_pattern = pid;
        self.prev_rects = rects;
        self.prev_sh = shs;
    }

    fn blast_growing(&self, x: f64, y: f64, s: f64) -> bool {
        let (cx, cy) = (x + s / 2.0, y + s / 2.0);
        for &(px, py, ps) in &self.prev_blasts {
            if (px - cx).abs() < 0.75 && (py - cy).abs() < 0.75 {
                return s > ps;
            }
        }
        s < 30.0
    }

    pub fn act(&mut self, s: &SlotState) -> usize {
        let h = HORIZON;
        let hf = h as f64;
        let size = s.size;
        let step = s.spd * s.frz;
        let paths = player_paths(raw(s.px), raw(s.py), raw(s.dpx), raw(s.dpy));

        let blasts: Vec<_> = s.enemies.iter().filter(|e| e.p == -1).collect();
        let growing: Vec<bool> = blasts.iter().map(|e| self.blast_growing(e.x, e.y, e.s)).collect();
        self.prev_blasts = blasts.iter().map(|e| (e.x + e.s / 2.0, e.y + e.s / 2.0, e.s)).collect();

        let mut hit_t = [hf + 1.0; 9];
        let mut hit_p = [hf + 1.0; 9];
        let mut room_extra: Vec<BoxRow> = Vec::new();
        let mut min_clear = [1e9f64; 9];
        let mut end_enemies: Option<Projected> = None;

        // lit rectangles reflect enemies
        let mut bounce: Vec<[f64; 9]> = Vec::new();
        if let Some(cp) = &s.cp {
            for (i, r) in cp.rects.iter().enumerate() {
                let lit_from = if r.sh == 2.0 {
                    0.0
                } else {
                    let ch = self.sh_change.get(i).copied().flatten();
                    match ch {
                        Some(c) if 0.0 < r.sh && r.sh < 2.0 && c > 0.0 => (2.0 - r.sh) / c,
                        _ => continue,
                    }
                };
                let d = self.rect_change.get(i).copied().unwrap_or([0.0; 4]);
                bounce.push([r.x, r.y, r.w, r.h, r.dx, r.dy, d[0], d[1], lit_from]);
            }
        }

        let movers: Vec<_> = s.enemies.iter().filter(|e| e.p != -1).collect();
        let n = movers.len();
        let pers: Vec<i8> = movers.iter().map(|e| e.p).collect();
        let mut got_t = vec![vec![INF; n]; 9];
        let mut alive_out = vec![vec![true; n]; 9];
        let mut ex_out = vec![vec![0.0; n]; 9];
        let mut ey_out = vec![vec![0.0; n]; 9];
        if n > 0 {
            let row = |f: &dyn Fn(usize) -> f64| -> Vec<Vec<f64>> { vec![(0..n).map(f).collect(); 9] };
            let mut ex = row(&|k| movers[k].x);
            let mut ey = row(&|k| movers[k].y);
            let mut vx = row(&|k| movers[k].vx);
            let mut vy = row(&|k| movers[k].vy);
            let mut sp = row(&|k| movers[k].spd);
            let pw: Vec<bool> = pers.iter().map(|&p| p >= 2).collect();
            let kam: Vec<bool> = pers.iter().map(|&p| p == 1).collect();
            let pwf: Vec<f64> = pw.iter().map(|&b| if b { 1.0 } else { 0.0 }).collect();
            let es: Vec<f64> = (0..n).map(|k| if pw[k] { 4.0 } else { movers[k].s }).collect();
            let lo: Vec<f64> = (0..n).map(|k| if pw[k] { -4.0 } else { 0.0 }).collect();
            let mut inside: Vec<Vec<bool>> = (0..9)
                .map(|a| {
                    (0..n)
                        .map(|k| {
                            let (x, v) = (ex[a][k], vx[a][k]);
                            (x >= 1.0 && x <= 128.0) || (x < 1.0 && v < 0.0) || (x > 128.0 && v > 0.0)
                        })
                        .collect()
                })
                .collect();
            let half = size - 1.0;
            let mut alive = vec![vec![true; n]; 9];
            let mut cleared = vec![vec![false; n]; 9];
            let mut born = vec![vec![INF; n]; 9];
            let mut bcx = vec![vec![0.0; n]; 9];
            let mut bcy = vec![vec![0.0; n]; 9];
            let mut stp = [step; 9];
            let mut ax0 = vec![vec![0.0; n]; 9];
            let mut ay0 = vec![vec![0.0; n]; 9];
            let mut ax1 = vec![vec![0.0; n]; 9];
            let mut ay1 = vec![vec![0.0; n]; 9];
            for t in 0..=h {
                let tf = t as f64;
                if t > 0 {
                    for a in 0..9 {
                        let (px, py) = (paths[a][t][0], paths[a][t][1]);
                        for k in 0..n {
                            vx[a][k] = vx[a][k] * E_FRICTION + E_ACCEL * sign(px - ex[a][k]);
                            vy[a][k] = vy[a][k] * E_FRICTION + E_ACCEL * sign(py - ey[a][k]);
                        }
                    }
                    for b in &bounce {
                        let [rx, ry, rw, rh, rdx, rdy, mdx, mdy, lit_from] = *b;
                        if tf - 1.0 < lit_from {
                            continue;
                        }
                        let rx_t = rx + mdx * (tf - 1.0);
                        let ry_t = ry + mdy * (tf - 1.0);
                        for a in 0..9 {
                            for k in 0..n {
                                let (x, y, v, w) = (ex[a][k], ey[a][k], vx[a][k], vy[a][k]);
                                let hitr = (x + v - 3.0 * pwf[k] < rx_t + rw)
                                    && (x + es[k] > rx_t + rdx)
                                    && (y + es[k] > ry_t + rdy)
                                    && (y + w - 3.0 * pwf[k] < ry_t + rh);
                                if !hitr {
                                    continue;
                                }
                                let mut nvx = if x + v < rx_t {
                                    -v.abs().max(BOUNCE_CAP)
                                } else if x + v + es[k] > rx_t + rw {
                                    v.abs().max(BOUNCE_CAP)
                                } else {
                                    v
                                };
                                let mut nvy = if y + w < ry_t {
                                    -w.abs().max(BOUNCE_CAP)
                                } else if y + w + es[k] > ry_t + rh {
                                    w.abs().max(BOUNCE_CAP)
                                } else {
                                    w
                                };
                                nvx = sign(nvx) * nvx.abs().min(BOUNCE_CAP);
                                nvy = sign(nvy) * nvy.abs().min(BOUNCE_CAP);
                                vx[a][k] = nvx;
                                vy[a][k] = nvy;
                            }
                        }
                    }
                    for a in 0..9 {
                        let (px, py) = (paths[a][t][0], paths[a][t][1]);
                        for k in 0..n {
                            let d2 = (ex[a][k] - px).powi(2) + (ey[a][k] - py).powi(2);
                            if kam[k] {
                                sp[a][k] = if d2 <= 625.0 { sp[a][k] - 0.01 } else { (sp[a][k] + 0.01).min(1.0) };
                            }
                            let ins = inside[a][k];
                            if ins && ey[a][k] >= 129.0 - es[k] {
                                vy[a][k] = -vy[a][k].abs();
                            } else if ins && ey[a][k] <= -2.0 {
                                vy[a][k] = vy[a][k].abs();
                            }
                            if ins && ex[a][k] >= 129.0 - es[k] {
                                vx[a][k] = -vx[a][k].abs();
                            } else if ins && ex[a][k] <= -2.0 {
                                vx[a][k] = vx[a][k].abs();
                            }
                            ex[a][k] += vx[a][k] * stp[a] * sp[a][k];
                            ey[a][k] += vy[a][k] * stp[a] * sp[a][k];
                            inside[a][k] |= ex[a][k] >= 1.0 && ex[a][k] <= 128.0;
                        }
                    }
                }
                for a in 0..9 {
                    for k in 0..n {
                        ax0[a][k] = ex[a][k] + lo[k];
                        ay0[a][k] = ey[a][k] + lo[k];
                        ax1[a][k] = ex[a][k] + es[k];
                        ay1[a][k] = ey[a][k] + es[k];
                    }
                }
                for a in 0..9 {
                    let (px, py) = (paths[a][t][0], paths[a][t][1]);
                    if t > 0 {
                        let both: Vec<bool> = (0..n).map(|k| alive[a][k] && inside[a][k]).collect();
                        let mut dying = vec![false; n];
                        for k in 0..n {
                            if !both[k] {
                                continue;
                            }
                            for j in 0..n {
                                if j != k
                                    && both[j]
                                    && ax1[a][k] > ax0[a][j]
                                    && ay1[a][k] > ay0[a][j]
                                    && ax0[a][k] < ax1[a][j]
                                    && ay0[a][k] < ay1[a][j]
                                {
                                    dying[k] = true;
                                    break;
                                }
                            }
                        }
                        let got: Vec<bool> = (0..n)
                            .map(|k| {
                                px + size > ax0[a][k]
                                    && py + size > ay0[a][k]
                                    && px - size < ax1[a][k]
                                    && py - size < ay1[a][k]
                                    && pw[k]
                                    && alive[a][k]
                            })
                            .collect();
                        for k in 0..n {
                            if got[k] {
                                got_t[a][k] = tf;
                            }
                        }
                        let boom = (0..n).any(|k| got[k] && pers[k] == 2);
                        let froze = (0..n).any(|k| got[k] && pers[k] == 3);
                        if froze {
                            stp[a] = s.spd * 0.4;
                        }
                        for k in 0..n {
                            cleared[a][k] |= (boom || got[k]) && alive[a][k];
                            dying[k] |= cleared[a][k] && alive[a][k];
                            let newly = dying[k] && kam[k] && born[a][k].is_infinite();
                            if newly {
                                bcx[a][k] = ex[a][k] + es[k] / 2.0;
                                bcy[a][k] = ey[a][k] + es[k] / 2.0;
                                born[a][k] = tf;
                            }
                            alive[a][k] &= !dying[k];
                        }
                    }
                    let mut any_touch = false;
                    let mut over = false;
                    let mut clr_min = 1e9f64;
                    for k in 0..n {
                        let touching = px + half > ax0[a][k]
                            && py + half > ay0[a][k]
                            && px - half < ax1[a][k]
                            && py - half < ay1[a][k]
                            && !pw[k];
                        any_touch |= touching && !cleared[a][k];
                        over |= touching && alive[a][k];
                        let hb = clip((tf - born[a][k]) * s.frz, 0.0, 30.0) / 2.0;
                        let live_b = born[a][k].is_finite() && born[a][k] < tf;
                        over |= px + half > bcx[a][k] - hb
                            && py + half > bcy[a][k] - hb
                            && px - half < bcx[a][k] + hb
                            && py - half < bcy[a][k] + hb
                            && live_b;
                        let mut clr = if alive[a][k] && !pw[k] {
                            gap(px - half, py - half, px + half, py + half, ax0[a][k], ay0[a][k], ax1[a][k], ay1[a][k])
                        } else {
                            1e9
                        };
                        let bclr = if born[a][k].is_finite() {
                            gap(px - half, py - half, px + half, py + half,
                                bcx[a][k] - 15.0, bcy[a][k] - 15.0, bcx[a][k] + 15.0, bcy[a][k] + 15.0)
                        } else {
                            1e9
                        };
                        clr = clr.min(bclr);
                        clr_min = clr_min.min(clr);
                    }
                    if any_touch && hit_p[a] > hf {
                        hit_p[a] = tf;
                    }
                    if over && hit_t[a] > hf {
                        hit_t[a] = tf;
                    }
                    hit_p[a] = hit_p[a].min(hit_t[a]);
                    min_clear[a] = min_clear[a].min(clr_min);
                }
            }
            let es_reach: Vec<f64> = (0..n).map(|k| if kam[k] { es[k] + 30.0 } else { es[k] }).collect();
            let mut any_threat = false;
            let mut ex_r = vec![vec![0.0; n]; 9];
            let mut ey_r = vec![vec![0.0; n]; 9];
            for a in 0..9 {
                for k in 0..n {
                    let threat = alive[a][k] && !pw[k];
                    any_threat |= threat;
                    ex_r[a][k] = if threat { if kam[k] { ex[a][k] - 15.0 } else { ex[a][k] } } else { 1e6 };
                    ey_r[a][k] = if threat { if kam[k] { ey[a][k] - 15.0 } else { ey[a][k] } } else { 1e6 };
                }
            }
            if any_threat {
                end_enemies = Some(Projected { ex: ex_r, ey: ey_r, vx: vx.clone(), vy: vy.clone(), sp: sp.clone(), es: es_reach });
            }
            for k in 0..n {
                if let Some(a) = (0..9).find(|&a| born[a][k].is_finite()) {
                    let c = (bcx[a][k], bcy[a][k]);
                    room_extra.push([c.0 - 15.0, c.1 - 15.0, c.0 + 15.0, c.1 + 15.0, 0.0, 0.0, 0.0, size - 1.0, 0.0, 0.0, 0.0, 0.0]);
                }
            }
            alive_out = alive;
            ex_out = ex;
            ey_out = ey;
        }

        // blasts: grow frz/2 a side per frame up to 30 wide, then shrink
        let frz = s.frz;
        let mut static_boxes: Vec<BoxRow> = Vec::new();
        let mut sweepers: Vec<BoxRow> = Vec::new();
        for (e, &grow) in blasts.iter().zip(&growing) {
            let (x0, y0, w) = (e.x, e.y, e.s);
            let (g, lo, hi) = if grow { (frz / 2.0, 0.0, (30.0 - w) / 2.0) } else { (-frz / 2.0, -w / 2.0, 0.0) };
            static_boxes.push([x0, y0, x0 + w, y0 + w, 0.0, 0.0, 0.0, size - 1.0, 0.0, g, lo, hi]);
        }
        if let Some(cp) = &s.cp {
            for (i, r) in cp.rects.iter().enumerate() {
                if r.w == 0.0 && r.h == 0.0 && (r.x < -20.0 || r.y < -20.0) {
                    continue;
                }
                let ch = self.sh_change.get(i).copied().flatten();
                let after = if cp.tpe == 1 || r.sh == 2.0 {
                    0.0
                } else if 0.0 < r.sh && r.sh < 2.0 {
                    match ch {
                        Some(c) if c > 0.0 => (2.0 - r.sh) / c,
                        _ => continue,
                    }
                } else {
                    continue;
                };
                let d = self.rect_change.get(i).copied().unwrap_or([0.0; 4]);
                let (mut vx_r, mut vy_r, mut move_from) = (d[0], d[1], 0.0);
                let any_d = d.iter().any(|v| *v != 0.0);
                if cp.tpe == 1 && !any_d && (r.dx != 0.0 || r.dy != 0.0) {
                    let v = r.spd * frz;
                    vx_r = sign(r.dx) * v;
                    vy_r = sign(r.dy) * v;
                    if r.sh < 2.0 {
                        let denom = match ch {
                            Some(c) if c > 0.0 => c,
                            _ => 0.02 * frz,
                        };
                        move_from = (2.0 - r.sh) / denom;
                    }
                }
                let row = [r.x, r.y, r.x + r.w - 1.0, r.y + r.h - 1.0, vx_r, vy_r, after, size - 2.0, move_from, 0.0, 0.0, 0.0];
                static_boxes.push(row);
                if vx_r != 0.0 || vy_r != 0.0 {
                    sweepers.push(row);
                }
            }
        }
        if !static_boxes.is_empty() {
            for a in 0..9 {
                let mut first = hf + 1.0;
                let mut clr_min = 1e9f64;
                for t in 0..=h {
                    let tf = t as f64;
                    let (px, py) = (paths[a][t][0], paths[a][t][1]);
                    for b in &static_boxes {
                        let (bx0, by0, bx1, by1) = box_at(b, tf);
                        let live = tf >= b[6];
                        let hh = b[7];
                        if live && px + hh > bx0 && py + hh > by0 && px - hh < bx1 && py - hh < by1 && tf < first {
                            first = tf;
                        }
                        let c = if live { gap(px - hh, py - hh, px + hh, py + hh, bx0, by0, bx1, by1) } else { 1e9 };
                        clr_min = clr_min.min(c);
                    }
                }
                hit_t[a] = hit_t[a].min(first);
                hit_p[a] = hit_p[a].min(first);
                min_clear[a] = min_clear[a].min(clr_min);
            }
        }

        let ends: Vec<[f64; 2]> = (0..9).map(|a| paths[a][h]).collect();
        let mut boxes_all = static_boxes.clone();
        boxes_all.extend(room_extra.iter().copied());
        let room = self.room(&ends, size, step, end_enemies.as_ref(), &boxes_all, hf);
        let mut score = [0.0; 9];
        for a in 0..9 {
            score[a] = room[a] + W_CLEAR * min_clear[a].min(CLEAR_CAP) / CLEAR_CAP;
        }
        if n > 0 && pers.iter().any(|&p| p >= 2) {
            let bonus = self.pickup_bonus(s, &pers, &got_t, &alive_out, &ex_out, &ey_out, &ends, size, step,
                                          end_enemies.as_ref(), &boxes_all, hf);
            for a in 0..9 {
                score[a] += bonus[a];
            }
        }
        if !sweepers.is_empty() {
            let risk = sweep_risk(&ends, &sweepers, hf);
            for a in 0..9 {
                score[a] -= W_SWEEP * risk[a];
            }
        }
        if s.fy && (s.ftimer as f64) + hf > 50.0 + (50.0 - CENTRE_GUARD) {
            for a in 0..9 {
                let e = ends[a];
                let in_box = e[0] + size - 2.0 > 60.0 && e[1] + size - 2.0 > 60.0 && e[0] - size + 2.0 < 68.0 && e[1] - size + 2.0 < 68.0;
                if in_box {
                    score[a] -= 2.0;
                }
            }
        }
        let mut best = 0;
        for a in 1..9 {
            let key = (hit_p[a], hit_t[a], score[a]);
            let cur = (hit_p[best], hit_t[best], score[best]);
            if key.partial_cmp(&cur) == Some(std::cmp::Ordering::Greater) {
                best = a;
            }
        }
        self.last = Decision {
            best,
            path: paths[best].iter().map(|p| (p[0], p[1])).collect(),
            hit: hit_p,
            score,
            room,
            ends,
            size,
            step,
            enemies: end_enemies,
            boxes: boxes_all,
        };
        best
    }

    #[allow(clippy::too_many_arguments)]
    fn pickup_bonus(&self, s: &SlotState, pers: &[i8], got_t: &[Vec<f64>], alive: &[Vec<bool>],
                    ex: &[Vec<f64>], ey: &[Vec<f64>], ends: &[[f64; 2]], size: f64, step: f64,
                    enemies: Option<&Projected>, boxes: &[BoxRow], hf: f64) -> [f64; 9] {
        let mut value: Vec<f64> = pers.iter().map(|&p| pickup_value(p)).collect();
        for (k, &p) in pers.iter().enumerate() {
            if s.frz < 1.0 && p == 3 { value[k] *= 0.5; }
            if s.size < 4.0 && p == 4 { value[k] *= 0.5; }
        }
        let ks: Vec<usize> = (0..pers.len()).filter(|&k| pers[k] >= 2).collect();
        let mut out = [0.0; 9];
        for a in 0..9 {
            let terms: Vec<f64> = (0..pers.len())
                .map(|k| value[k] * if got_t[a][k].is_finite() { 1.0 - 0.25 * got_t[a][k] / hf } else { 0.0 })
                .collect();
            let bonus = np_sum(&terms);
            let qx: Vec<f64> = ks.iter().map(|&k| ex[a][k]).collect();
            let qy: Vec<f64> = ks.iter().map(|&k| ey[a][k]).collect();
            let margin = self.room_map_one(a, ends[a], size, step, enemies, boxes, hf, &qx, &qy, &self.t, true);
            let seek: Vec<f64> = ks
                .iter()
                .enumerate()
                .map(|(j, &k)| {
                    let tp = (qx[j] - ends[a][0]).abs().max((qy[j] - ends[a][1]).abs()) / 2.5;
                    let near = clip(1.0 - tp / ROOM_TMAX, 0.0, 1.0);
                    if alive[a][k] && margin[j] > 0.0 { value[k] * near } else { 0.0 }
                })
                .collect();
            out[a] = bonus + W_SEEK * np_sum(&seek);
        }
        out
    }

    fn room(&self, ends: &[[f64; 2]], size: f64, step: f64, enemies: Option<&Projected>, boxes: &[BoxRow], hf: f64) -> [f64; 9] {
        let valid: Vec<bool> = (0..self.cx.len())
            .map(|c| self.cx[c] >= 2.0 && self.cx[c] <= 125.0 && self.cy[c] >= 2.0 && self.cy[c] <= 125.0)
            .collect();
        let count = valid.iter().filter(|v| **v).count() as f64;
        let mut out = [0.0; 9];
        for a in 0..9 {
            let roomy = self.room_map_one(a, ends[a], size, step, enemies, boxes, hf, &self.cx, &self.cy, &self.t, false);
            let terms: Vec<f64> = roomy.iter().zip(&valid).map(|(r, v)| r * if *v { 1.0 } else { 0.0 }).collect();
            out[a] = np_sum(&terms) / count;
        }
        out
    }

    /// `_room_map` for one plan `a`, at points (cx, cy).
    #[allow(clippy::too_many_arguments)]
    fn room_map_one(&self, a: usize, end: [f64; 2], size: f64, step: f64, enemies: Option<&Projected>,
                    boxes: &[BoxRow], hf: f64, cx: &[f64], cy: &[f64], tt: &[f64], margin: bool) -> Vec<f64> {
        let drift: Vec<f64> = tt.iter().map(|t| 99.0 * (1.0 - 0.99f64.powf(*t))).collect();
        let spread: Vec<f64> = tt.iter().zip(&drift).map(|(t, d)| t - d).collect();
        let mut threat = vec![INF; cx.len()];
        if let Some(e) = enemies {
            for k in 0..e.es.len() {
                let s_ = step * e.sp[a][k];
                for (ti, &t) in tt.iter().enumerate() {
                    let cen_x = (e.ex[a][k] + e.es[k] / 2.0) + s_ * e.vx[a][k] * drift[ti];
                    let cen_y = (e.ey[a][k] + e.es[k] / 2.0) + s_ * e.vy[a][k] * drift[ti];
                    let reach = s_ * spread[ti] + e.es[k] / 2.0 + size;
                    for c in 0..cx.len() {
                        if t < threat[c] && (cx[c] - cen_x).abs() <= reach && (cy[c] - cen_y).abs() <= reach {
                            threat[c] = t;
                        }
                    }
                }
            }
        }
        for b in boxes {
            for &t in tt {
                let t2 = t + hf;
                if t2 < b[6] {
                    continue;
                }
                let (x0, y0, x1, y1) = box_at(b, t2);
                let (x0, y0, x1, y1) = (x0 - size, y0 - size, x1 + size, y1 + size);
                for c in 0..cx.len() {
                    if t < threat[c] && cx[c] > x0 && cx[c] < x1 && cy[c] > y0 && cy[c] < y1 {
                        threat[c] = t;
                    }
                }
            }
        }
        let t_last = *tt.last().unwrap_or(&0.0);
        (0..cx.len())
            .map(|c| {
                let tp = (cx[c] - end[0]).abs().max((cy[c] - end[1]).abs()) / 2.5;
                if margin { threat[c].min(t_last) - tp } else { clip(threat[c] - tp, 0.0, ROOM_CAP) / ROOM_CAP }
            })
            .collect()
    }

    /// The chosen plan's breathing room, in frames, on a g x g grid (rows are y),
    /// looking `tmax` frames ahead: what the Python overlay draws.
    pub fn room_view(&self, g: usize, tmax: f64) -> Vec<f32> {
        let d = &self.last;
        if d.ends.is_empty() {
            return vec![0.0; g * g];
        }
        let centres: Vec<f64> = (0..g).map(|i| (i as f64 + 0.5) * (128.0 / g as f64)).collect();
        let mut cx = Vec::with_capacity(g * g);
        let mut cy = Vec::with_capacity(g * g);
        for y in &centres {
            for x in &centres {
                cx.push(*x);
                cy.push(*y);
            }
        }
        let tt: Vec<f64> = (0..=(tmax as usize)).step_by(4).map(|v| v as f64).collect();
        self.room_map_one(d.best, d.ends[d.best], d.size, d.step, d.enemies.as_ref(), &d.boxes, HORIZON as f64, &cx, &cy, &tt, true)
            .into_iter()
            .map(|v| v as f32)
            .collect()
    }
}

fn sweep_risk(ends: &[[f64; 2]], sweepers: &[BoxRow], hf: f64) -> [f64; 9] {
    let mut out = [f64::NEG_INFINITY; 9];
    for b in sweepers {
        let (x0, y0, x1, y1) = box_at(b, hf);
        let (vx, vy, move_from, hh) = (b[4], b[5], b[8], b[7]);
        let along_x = vx.abs() >= vy.abs();
        let speed = (if along_x { vx.abs() } else { vy.abs() }).max(1e-6);
        for a in 0..9 {
            let (ex, ey) = (ends[a][0], ends[a][1]);
            let ahead = if along_x {
                if vx > 0.0 { (ex - hh) - x1 } else { x0 - (ex + hh) }
            } else if vy > 0.0 {
                (ey - hh) - y1
            } else {
                y0 - (ey + hh)
            };
            let behind = if along_x {
                if vx > 0.0 { ex + hh <= x0 } else { ex - hh >= x1 }
            } else if vy > 0.0 {
                ey + hh <= y0
            } else {
                ey - hh >= y1
            };
            let lo_edge = (if along_x { y0 } else { x0 }) - hh - 1.0;
            let hi_edge = (if along_x { y1 } else { x1 }) + hh + 1.0;
            let pos = if along_x { ey } else { ex };
            let in_band = pos > lo_edge && pos < hi_edge;
            let d_lo = if lo_edge >= 2.0 { pos - lo_edge } else { INF };
            let d_hi = if hi_edge <= 125.0 { hi_edge - pos } else { INF };
            let t_exit = d_lo.min(d_hi) / 2.5;
            let t_arrive = ahead.max(0.0) / speed + (move_from - hf).max(0.0);
            let risk = clip((t_exit + SWEEP_MARGIN - t_arrive) / SWEEP_MARGIN, 0.0, 1.0);
            let risk = if in_band && !behind { risk } else { 0.0 };
            out[a] = out[a].max(risk);
        }
    }
    out
}
