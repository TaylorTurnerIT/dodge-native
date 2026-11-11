//! velocity-flow-v2 in plain Rust, for the browser.
//!
//! Mirrors `dodge/velocity.py` (VelocityFlowV2Extractor, half-resolution
//! trunk), `_FieldLogits` and SB3's value head op for op:
//!
//!   obs(3076) -> 11x32x32 planes -> stem conv -> 2x2 avg pool -> 3 convs at
//!   16x16 (one dilated) -> bilinear up to 32x32 = trunk
//!   trunk -> adaptive pool 4x4 -> 2 convs -> bilinear up = context
//!   1x1 head on [trunk, context] -> 6 danger slices
//!   controller: read slice k at each action's position at frame k, weighted
//!   sum -> path danger; logits = standardise(-danger) * exp(log_temperature)
//!   critic: [trunk mean, 8x4x4 summary, player 4, senses 6] -> 64 -> 64,
//!   [-danger, that] -> 64 -> value

pub const GRID: usize = 32;
pub const CELLS: usize = GRID * GRID;
pub const OBS: usize = 4 + 3 * CELLS;
pub const SLICES: usize = 6;
const SLOPE: f32 = 0.01;

static WEIGHTS: &[u8] = include_bytes!("../cnn_weights.bin");

struct Conv {
    cin: usize,
    cout: usize,
    k: usize,
    w: Vec<f32>,
    b: Vec<f32>,
}

pub struct Cnn {
    offsets: Vec<f32>, // 9 x 6 x 2
    sample_weights: Vec<f32>,
    stem: Conv,
    body0: Conv,
    body2: Conv,
    body4: Conv,
    ctx0: Conv,
    ctx2: Conv,
    head: Conv,
    vpool: Conv,
    v0w: Vec<f32>,
    v0b: Vec<f32>,
    v2w: Vec<f32>,
    v2b: Vec<f32>,
    m0w: Vec<f32>,
    m0b: Vec<f32>,
    vw: Vec<f32>,
    vb: Vec<f32>,
    log_temperature: f32,
}

/// Everything one forward pass produces, kept for the overlay.
pub struct Output {
    pub field: Vec<f32>, // SLICES x 32 x 32
    pub danger: [f32; 9],
    pub log_pmf: [f32; 9],
    pub value: f32,
    pub action: usize,
}

struct Reader<'a> {
    bytes: &'a [u8],
    at: usize,
}

impl Reader<'_> {
    fn take(&mut self, n: usize) -> Vec<f32> {
        let out = self.bytes[self.at..self.at + 4 * n]
            .chunks_exact(4)
            .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
            .collect();
        self.at += 4 * n;
        out
    }
    fn conv(&mut self, cout: usize, cin: usize, k: usize) -> Conv {
        let w = self.take(cout * cin * k * k);
        let b = self.take(cout);
        Conv { cin, cout, k, w, b }
    }
}

#[inline]
fn lrelu(x: f32) -> f32 {
    if x >= 0.0 { x } else { x * SLOPE }
}

/// 3x3 convolution (or 1x1 when k == 1), zero padding, optional dilation,
/// same spatial size, LeakyReLU when `act`. Planes are channel-major.
fn conv(c: &Conv, input: &[f32], h: usize, w: usize, dilation: usize, act: bool) -> Vec<f32> {
    let hw = h * w;
    let mut out = vec![0.0f32; c.cout * hw];
    if c.k == 1 {
        for o in 0..c.cout {
            let dst = &mut out[o * hw..(o + 1) * hw];
            dst.fill(c.b[o]);
            for i in 0..c.cin {
                let wt = c.w[o * c.cin + i];
                let src = &input[i * hw..(i + 1) * hw];
                for (d, s) in dst.iter_mut().zip(src) {
                    *d += wt * s;
                }
            }
        }
    } else {
        let pad = dilation as isize;
        for o in 0..c.cout {
            let dst = &mut out[o * hw..(o + 1) * hw];
            dst.fill(c.b[o]);
            for i in 0..c.cin {
                let src = &input[i * hw..(i + 1) * hw];
                let base = (o * c.cin + i) * 9;
                for ky in 0..3 {
                    let dy = ky as isize * dilation as isize - pad;
                    for kx in 0..3 {
                        let dx = kx as isize * dilation as isize - pad;
                        let wt = c.w[base + ky * 3 + kx];
                        // rows whose source row is in range
                        let y0 = (-dy).max(0) as usize;
                        let y1 = (h as isize - dy.max(0)) as usize;
                        let x0 = (-dx).max(0) as usize;
                        let x1 = (w as isize - dx.max(0)) as usize;
                        for y in y0..y1 {
                            let sy = (y as isize + dy) as usize;
                            let drow = &mut dst[y * w + x0..y * w + x1];
                            let sstart = (sy * w) as isize + x0 as isize + dx;
                            let srow = &src[sstart as usize..sstart as usize + (x1 - x0)];
                            for (d, s) in drow.iter_mut().zip(srow) {
                                *d += wt * s;
                            }
                        }
                    }
                }
            }
        }
    }
    if act {
        for v in &mut out {
            *v = lrelu(*v);
        }
    }
    out
}

/// PyTorch bilinear interpolation index, align_corners=False.
fn source_index(dst: usize, input: usize, output: usize) -> (usize, usize, f32) {
    let scale = input as f32 / output as f32;
    let src = ((dst as f32 + 0.5) * scale - 0.5).max(0.0);
    let i0 = src as usize;
    let i1 = if i0 < input - 1 { i0 + 1 } else { i0 };
    (i0, i1, src - i0 as f32)
}

fn upsample(input: &[f32], channels: usize, n: usize, m: usize) -> Vec<f32> {
    let idx: Vec<(usize, usize, f32)> = (0..m).map(|d| source_index(d, n, m)).collect();
    let mut out = vec![0.0f32; channels * m * m];
    for c in 0..channels {
        let src = &input[c * n * n..(c + 1) * n * n];
        for (y, &(y0, y1, ly)) in idx.iter().enumerate() {
            for (x, &(x0, x1, lx)) in idx.iter().enumerate() {
                let top = (1.0 - lx) * src[y0 * n + x0] + lx * src[y0 * n + x1];
                let bottom = (1.0 - lx) * src[y1 * n + x0] + lx * src[y1 * n + x1];
                out[c * m * m + y * m + x] = (1.0 - ly) * top + ly * bottom;
            }
        }
    }
    out
}

fn avg_pool(input: &[f32], channels: usize, n: usize, bins: usize) -> Vec<f32> {
    let k = n / bins;
    let mut out = vec![0.0f32; channels * bins * bins];
    for c in 0..channels {
        for by in 0..bins {
            for bx in 0..bins {
                let mut s = 0.0f32;
                for y in 0..k {
                    for x in 0..k {
                        s += input[c * n * n + (by * k + y) * n + bx * k + x];
                    }
                }
                out[c * bins * bins + by * bins + bx] = s / (k * k) as f32;
            }
        }
    }
    out
}

fn linear(w: &[f32], b: &[f32], x: &[f32], act: bool) -> Vec<f32> {
    let n = b.len();
    let m = x.len();
    (0..n)
        .map(|o| {
            let s = b[o] + w[o * m..(o + 1) * m].iter().zip(x).map(|(a, c)| a * c).sum::<f32>();
            if act { lrelu(s) } else { s }
        })
        .collect()
}

impl Cnn {
    pub fn load() -> Self {
        let mut r = Reader { bytes: WEIGHTS, at: 0 };
        let offsets = r.take(9 * SLICES * 2);
        let sample_weights = r.take(SLICES);
        let stem = r.conv(32, 11, 3);
        let body0 = r.conv(64, 32, 3);
        let body2 = r.conv(64, 64, 3);
        let body4 = r.conv(32, 64, 3);
        let ctx0 = r.conv(32, 32, 3);
        let ctx2 = r.conv(16, 32, 3);
        let head = r.conv(SLICES, 48, 1);
        let vpool = r.conv(8, 32, 1);
        let v0w = r.take(64 * 170);
        let v0b = r.take(64);
        let v2w = r.take(64 * 64);
        let v2b = r.take(64);
        let m0w = r.take(64 * 73);
        let m0b = r.take(64);
        let vw = r.take(64);
        let vb = r.take(1);
        let log_temperature = r.take(1)[0];
        assert_eq!(r.at, WEIGHTS.len(), "cnn_weights.bin layout");
        Self {
            offsets, sample_weights, stem, body0, body2, body4, ctx0, ctx2, head, vpool,
            v0w, v0b, v2w, v2b, m0w, m0b, vw, vb, log_temperature,
        }
    }

    pub fn forward(&self, obs: &[f32]) -> Output {
        assert_eq!(obs.len(), OBS);
        let coords = &obs[..4];
        // --- policy_inputs: 8 one-hot types, player cell, vx, vy ---
        let mut planes = vec![0.0f32; 11 * CELLS];
        for cell in 0..CELLS {
            let id = (obs[4 + cell] * 8.0).round().clamp(0.0, 8.0) as usize;
            if id > 0 {
                planes[(id - 1) * CELLS + cell] = 1.0;
            }
            planes[9 * CELLS + cell] = obs[4 + CELLS + cell];
            planes[10 * CELLS + cell] = obs[4 + 2 * CELLS + cell];
        }
        let scale = 127.0f32 / 4.0;
        let pcx = ((coords[0] * scale) as i64).clamp(0, 31) as usize;
        let pcy = ((coords[1] * scale) as i64).clamp(0, 31) as usize;
        planes[8 * CELLS + pcy * GRID + pcx] = 1.0;

        // --- trunk ---
        let stem = conv(&self.stem, &planes, GRID, GRID, 1, true);
        let half = avg_pool(&stem, 32, GRID, 16);
        let b0 = conv(&self.body0, &half, 16, 16, 1, true);
        let b2 = conv(&self.body2, &b0, 16, 16, 2, true);
        let body = conv(&self.body4, &b2, 16, 16, 1, true);
        let trunk = upsample(&body, 32, 16, GRID);

        // --- context and field ---
        let pooled = avg_pool(&trunk, 32, GRID, 4);
        let c0 = conv(&self.ctx0, &pooled, 4, 4, 1, true);
        let c2 = conv(&self.ctx2, &c0, 4, 4, 1, true);
        let context = upsample(&c2, 16, 4, GRID);
        let mut both = trunk.clone();
        both.extend_from_slice(&context);
        let field = conv(&self.head, &both, GRID, GRID, 1, false);

        // --- controller: path danger ---
        let px = coords[0] * 127.0;
        let py = coords[1] * 127.0;
        let mut danger = [0.0f32; 9];
        for (a, d) in danger.iter_mut().enumerate() {
            for k in 0..SLICES {
                let ox = self.offsets[(a * SLICES + k) * 2];
                let oy = self.offsets[(a * SLICES + k) * 2 + 1];
                let v = sample(&field[k * CELLS..(k + 1) * CELLS], px + ox, py + oy);
                *d += v * self.sample_weights[k];
            }
        }
        let neg: Vec<f32> = danger.iter().map(|d| -d).collect();
        let mean = neg.iter().sum::<f32>() / 9.0;
        let var = neg.iter().map(|v| (v - mean) * (v - mean)).sum::<f32>() / 8.0;
        let spread = var.sqrt().max(1e-3);
        let t = self.log_temperature.exp();
        let logits: Vec<f32> = neg.iter().map(|v| (v - mean) / spread * t).collect();
        let lse = {
            let m = logits.iter().cloned().fold(f32::NEG_INFINITY, f32::max);
            m + logits.iter().map(|l| (l - m).exp()).sum::<f32>().ln()
        };
        let mut log_pmf = [0.0f32; 9];
        let mut action = 0;
        for a in 0..9 {
            log_pmf[a] = logits[a] - lse;
            if log_pmf[a] > log_pmf[action] {
                action = a;
            }
        }

        // --- critic ---
        let senses = senses(&planes, coords);
        let mut inputs = Vec::with_capacity(170);
        for c in 0..32 {
            inputs.push(pooled[c * 16..(c + 1) * 16].iter().sum::<f32>() / 16.0);
        }
        inputs.extend(conv(&self.vpool, &pooled, 4, 4, 1, false));
        inputs.extend_from_slice(coords);
        inputs.extend_from_slice(&senses);
        let h = linear(&self.v0w, &self.v0b, &inputs, true);
        let h = linear(&self.v2w, &self.v2b, &h, true);
        let mut latent = neg.clone();
        latent.extend(h);
        let h = linear(&self.m0w, &self.m0b, &latent, true);
        let value = linear(&self.vw, &self.vb, &h, false)[0];

        Output { field, danger, log_pmf, value, action }
    }
}

/// grid_sample, bilinear, border padding, align_corners=False, at pixel (x, y).
fn sample(plane: &[f32], x: f32, y: f32) -> f32 {
    let n = GRID as f32;
    let gx = x / 64.0 - 1.0;
    let gy = y / 64.0 - 1.0;
    let ix = (((gx + 1.0) * n - 1.0) / 2.0).clamp(0.0, n - 1.0);
    let iy = (((gy + 1.0) * n - 1.0) / 2.0).clamp(0.0, n - 1.0);
    let x0 = ix.floor();
    let y0 = iy.floor();
    let (tx, ty) = (ix - x0, iy - y0);
    let at = |cx: f32, cy: f32| -> f32 {
        if cx < 0.0 || cy < 0.0 || cx > n - 1.0 || cy > n - 1.0 {
            0.0
        } else {
            plane[cy as usize * GRID + cx as usize]
        }
    };
    (1.0 - tx) * (1.0 - ty) * at(x0, y0)
        + tx * (1.0 - ty) * at(x0 + 1.0, y0)
        + (1.0 - tx) * ty * at(x0, y0 + 1.0)
        + tx * ty * at(x0 + 1.0, y0 + 1.0)
}

/// `_sense_features`: player velocity, nearest lethal cell offset, distance,
/// closing speed.
fn senses(planes: &[f32], coords: &[f32]) -> [f32; 6] {
    let scale = 127.0f32 / 4.0;
    let (px, py) = (coords[0] * scale, coords[1] * scale);
    let (pvx, pvy) = (coords[2], coords[3]);
    let beyond = (GRID * GRID * 16) as f32;
    let mut best = f32::INFINITY;
    let mut index = 0;
    for cell in 0..CELLS {
        let lethal = [0usize, 1, 2, 7].iter().any(|&c| planes[c * CELLS + cell] > 0.0);
        let (col, row) = ((cell % GRID) as f32, (cell / GRID) as f32);
        let sq = if lethal { (col - px).powi(2) + (row - py).powi(2) } else { beyond };
        if sq < best {
            best = sq;
            index = cell;
        }
    }
    if best >= beyond {
        return [pvx, pvy, 0.0, 0.0, 4.0, 0.0];
    }
    let distance = best.min(beyond - 1.0).sqrt() / GRID as f32;
    let nx = (index % GRID) as f32 - px;
    let ny = (index / GRID) as f32 - py;
    let rx = planes[9 * CELLS + index] - pvx;
    let ry = planes[10 * CELLS + index] - pvy;
    let length = (nx * nx + ny * ny).sqrt().max(1e-6);
    let closing = -(rx * nx + ry * ny) / length;
    [pvx, pvy, nx / GRID as f32, ny / GRID as f32, distance, closing]
}
