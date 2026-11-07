//! A learned potential `V` and the controller that rolls down it.
//!
//! The network sees only what the player sees: where each enemy is, how it moves,
//! how big it is, which kind it is, the active pattern rectangles, and the player's
//! own position and velocity. It never sees a rollout or an arrival time.
//!
//! `V(q) = sum over enemies of k(enemy features relative to q)
//!       + sum over pattern rectangles of r(rectangle features relative to q)
//!       + b(q, player velocity)`
//!
//! Each of `k`, `r` and `b` is a small tanh network trained offline (see `hnn/train.py`).
//! The controller takes the slope of `V` in the nine action directions and plays the
//! steepest descent. The slope is a central difference here and exact autograd in training.
//! Feature definitions must match `hnn/features.py`.

use std::sync::OnceLock;

use dodge_core::{Action, NativeGame};
use serde::Deserialize;

/// Step for the central difference, in pixels.
const FD_STEP: f64 = 0.25;

#[derive(Clone, Debug, Deserialize)]
struct Layer {
    /// `weights[out][in]`
    weights: Vec<Vec<f64>>,
    bias: Vec<f64>,
}

#[derive(Clone, Debug, Deserialize)]
struct Mlp {
    layers: Vec<Layer>,
}

impl Mlp {
    fn forward(&self, input: &[f64]) -> f64 {
        let mut current: Vec<f64> = input.to_vec();
        let last = self.layers.len().saturating_sub(1);
        for (index, layer) in self.layers.iter().enumerate() {
            let mut next = Vec::with_capacity(layer.bias.len());
            for (row, bias) in layer.weights.iter().zip(&layer.bias) {
                let mut sum = *bias;
                for (weight, value) in row.iter().zip(&current) {
                    sum += weight * value;
                }
                next.push(if index == last { sum } else { sum.tanh() });
            }
            current = next;
        }
        current.first().copied().unwrap_or(0.0)
    }
}

#[derive(Clone, Debug, Deserialize)]
pub struct Model {
    entity: Mlp,
    rect: Mlp,
    base: Mlp,
    /// Logit scale: `logit = -beta * slope`.
    beta: f64,
    /// Logit bonus for each axis the action holds still (neutral holds two, a cardinal move one).
    axis_bias: f64,
}

/// What the player can see on one frame.
#[derive(Clone, Debug, Default)]
pub struct Observation {
    /// Player x, y, vx, vy, size.
    pub player: [f64; 5],
    /// Enemy x, y, vx, vy (pixels per frame), size, personality.
    pub enemies: Vec<[f64; 6]>,
    /// Pattern rectangle x, y, width, height, lethal flag.
    pub rects: Vec<[f64; 5]>,
}

impl Observation {
    pub fn from_game(game: &NativeGame) -> Self {
        let view = game.privileged_view();
        let step = view.speed.to_double() * view.freeze_rate.to_double();
        let player = game.player();
        let enemies = game
            .enemies()
            .iter()
            .map(|enemy| {
                let rate = step * enemy.speed.to_double();
                [
                    enemy.x.to_double(),
                    enemy.y.to_double(),
                    enemy.vx.to_double() * rate,
                    enemy.vy.to_double() * rate,
                    enemy.size.to_double(),
                    f64::from(enemy.personality),
                ]
            })
            .collect();
        let mut rects = Vec::new();
        if let Some(pattern) = view.active_pattern {
            let lethal_pattern = pattern.pattern_type == 1;
            for rect in pattern.rects {
                let lethal = lethal_pattern || rect.sh.to_double() == 2.0;
                rects.push([
                    rect.x.to_double(),
                    rect.y.to_double(),
                    rect.width.to_double(),
                    rect.height.to_double(),
                    if lethal { 1.0 } else { 0.0 },
                ]);
            }
        }
        Self {
            player: [
                player.x.to_double(),
                player.y.to_double(),
                player.vx.to_double(),
                player.vy.to_double(),
                player.size.to_double(),
            ],
            enemies,
            rects,
        }
    }
}

/// One-hot slot for an enemy personality: normal, kamikaze, blast, bomb, bonus.
fn kind_slot(personality: f64) -> usize {
    match personality as i32 {
        1 => 1,
        -1 => 2,
        2 => 3,
        3 | 4 => 4,
        _ => 0,
    }
}

const DIRECTIONS: [(f64, f64); 9] = [
    (0.0, 0.0),
    (-1.0, 0.0),
    (1.0, 0.0),
    (0.0, -1.0),
    (0.0, 1.0),
    (-1.0, -1.0),
    (1.0, -1.0),
    (-1.0, 1.0),
    (1.0, 1.0),
];

impl Model {
    pub fn from_json(text: &str) -> Result<Self, String> {
        serde_json::from_str(text).map_err(|error| format!("could not parse model: {error}"))
    }

    /// `V` at the query point `(qx, qy)` for this observation.
    pub fn value(&self, view: &Observation, qx: f64, qy: f64) -> f64 {
        let [_, _, pvx, pvy, psize] = view.player;
        let mut total = 0.0;

        for enemy in &view.enemies {
            let mut features = [0.0; 11];
            features[kind_slot(enemy[5])] = 1.0;
            features[5] = (enemy[0] - qx) / 32.0;
            features[6] = (enemy[1] - qy) / 32.0;
            features[7] = (enemy[2] - pvx) / 3.0;
            features[8] = (enemy[3] - pvy) / 3.0;
            features[9] = enemy[4] / 8.0;
            features[10] = psize / 8.0;
            total += self.entity.forward(&features);
        }

        for rect in &view.rects {
            let nearest_x = qx.clamp(rect[0], rect[0] + rect[2]);
            let nearest_y = qy.clamp(rect[1], rect[1] + rect[3]);
            let features = [
                rect[4],
                (nearest_x - qx) / 32.0,
                (nearest_y - qy) / 32.0,
                rect[2] / 64.0,
                rect[3] / 64.0,
            ];
            total += self.rect.forward(&features);
        }

        total
            + self
                .base
                .forward(&[qx / 64.0 - 1.0, qy / 64.0 - 1.0, pvx / 3.0, pvy / 3.0])
    }

    /// Slope of `V` at the player.
    pub fn gradient(&self, view: &Observation) -> (f64, f64) {
        let [x, y, ..] = view.player;
        let gx =
            (self.value(view, x + FD_STEP, y) - self.value(view, x - FD_STEP, y)) / (2.0 * FD_STEP);
        let gy =
            (self.value(view, x, y + FD_STEP) - self.value(view, x, y - FD_STEP)) / (2.0 * FD_STEP);
        (gx, gy)
    }

    /// The nine action logits and the steepest-descent action.
    pub fn choose(&self, view: &Observation) -> (Action, [f64; 9]) {
        let (gx, gy) = self.gradient(view);
        let mut logits = [0.0; 9];
        let mut best = 0;
        for (index, (dx, dy)) in DIRECTIONS.iter().enumerate() {
            let held = f64::from(u8::from(*dx == 0.0) + u8::from(*dy == 0.0));
            logits[index] = -self.beta * (gx * dx + gy * dy) + self.axis_bias * held;
            if logits[index] > logits[best] {
                best = index;
            }
        }
        let action = Action::ALL.get(best).copied().unwrap_or(Action::Neutral);
        (action, logits)
    }
}

static MODEL: OnceLock<Model> = OnceLock::new();

/// Install the model that `PolicyKind::Learned` and `--drive-model` use. One per process.
pub fn install(model: Model) -> Result<(), String> {
    MODEL
        .set(model)
        .map_err(|_| "a learned model is already installed".to_owned())
}

pub fn installed() -> Option<&'static Model> {
    MODEL.get()
}
