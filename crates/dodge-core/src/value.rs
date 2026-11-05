//! Small CPU inference model for fair-planner search leaves.
//!
//! Inputs are privileged full-state values. They are not screen-observable.

use crate::NativeGame;

pub const FEATURE_COUNT: usize = 32;
pub const FEATURE_SCHEMA: &str = "fair-planner-value-v1";

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ValueFeatures(pub [f32; FEATURE_COUNT]);

/// Standardized 32-32-16-1 MLP with ReLU hidden layers.
#[derive(Clone, Debug, PartialEq)]
pub struct ValueModel {
    pub mean: [f32; FEATURE_COUNT],
    pub scale: [f32; FEATURE_COUNT],
    pub w1: [[f32; FEATURE_COUNT]; 32],
    pub b1: [f32; 32],
    pub w2: [[f32; 32]; 16],
    pub b2: [f32; 16],
    pub w3: [f32; 16],
    pub b3: f32,
}

impl ValueModel {
    /// Predict future survival frames from one state. This function reads no
    /// seed or RNG field and does not mutate or advance the game.
    pub fn predict(&self, features: ValueFeatures) -> f64 {
        let mut h1 = [0.0_f32; 32];
        for (i, output) in h1.iter_mut().enumerate() {
            let mut sum = self.b1[i];
            for j in 0..FEATURE_COUNT {
                let scale = self.scale[j].abs().max(1.0e-6);
                sum += self.w1[i][j] * ((features.0[j] - self.mean[j]) / scale);
            }
            *output = sum.max(0.0);
        }
        let mut h2 = [0.0_f32; 16];
        for (i, output) in h2.iter_mut().enumerate() {
            let mut sum = self.b2[i];
            for (j, value) in h1.iter().enumerate() {
                sum += self.w2[i][j] * value;
            }
            *output = sum.max(0.0);
        }
        let mut result = self.b3;
        for (weight, value) in self.w3.iter().zip(h2) {
            result += weight * value;
        }
        f64::from(result)
    }
}

/// Extract the fixed feature allowlist. Enemy rows are ordered by squared
/// distance, then x/y, so equal-distance rows have deterministic order.
pub fn value_features(game: &NativeGame) -> ValueFeatures {
    let mut values = [0.0_f32; FEATURE_COUNT];
    let mut cursor = 0;
    let player = game.player();
    for value in [player.x, player.y, player.vx, player.vy, player.size] {
        values[cursor] = value.to_f32();
        cursor += 1;
    }
    let mut enemies = game.enemies().iter().collect::<Vec<_>>();
    enemies.sort_by(|a, b| {
        let ax = a.x.to_f32() - player.x.to_f32();
        let ay = a.y.to_f32() - player.y.to_f32();
        let bx = b.x.to_f32() - player.x.to_f32();
        let by = b.y.to_f32() - player.y.to_f32();
        (ax * ax + ay * ay)
            .total_cmp(&(bx * bx + by * by))
            .then_with(|| a.x.to_f32().total_cmp(&b.x.to_f32()))
            .then_with(|| a.y.to_f32().total_cmp(&b.y.to_f32()))
    });
    for index in 0..3 {
        if let Some(enemy) = enemies.get(index) {
            values[cursor] = enemy.x.to_f32() - player.x.to_f32();
            values[cursor + 1] = enemy.y.to_f32() - player.y.to_f32();
            values[cursor + 2] = enemy.vx.to_f32();
            values[cursor + 3] = enemy.vy.to_f32();
            values[cursor + 4] = enemy.size.to_f32();
            values[cursor + 5] = 1.0;
        }
        cursor += 6;
    }
    values[cursor] = game.enemies().len() as f32;
    values[cursor + 1] = if game.value_pattern_active() {
        1.0
    } else {
        0.0
    };
    values[cursor + 2] = game.value_pattern_timer() as f32;
    values[cursor + 3] = f32::from(game.value_difficulty());
    values[cursor + 4] = game.value_speed().to_f32();
    values[cursor + 5] = game.survival_frames() as f32;
    values[cursor + 6] = game.score().to_f32();
    values[cursor + 7] = game.value_enemy_est().to_f32();
    values[cursor + 8] = game.value_freeze_rate().to_f32();
    ValueFeatures(values)
}

#[cfg(test)]
mod tests {
    use super::{FEATURE_COUNT, ValueFeatures, ValueModel, value_features};
    use crate::{BUTTON_X_MASK, NativeConfig, NativeGame};

    #[test]
    fn features_are_fixed_width_and_exclude_seed_and_rng() -> Result<(), crate::CoreError> {
        let mut game = NativeGame::new(NativeConfig::new(17));
        game.advance_frame(BUTTON_X_MASK)?;
        let before_rng = game.rng_checkpoint();
        let before = value_features(&game);
        let mut reseeded = game.clone();
        reseeded.reseed_rng_for_planner(991);
        assert_eq!(before.0.len(), FEATURE_COUNT);
        assert_eq!(before, value_features(&reseeded));
        assert_eq!(before_rng, game.rng_checkpoint());
        assert_eq!(before, value_features(&game));
        Ok(())
    }

    #[test]
    fn model_inference_is_finite_and_does_not_mutate_game() -> Result<(), crate::CoreError> {
        let mut game = NativeGame::new(NativeConfig::new(31));
        game.advance_frame(BUTTON_X_MASK)?;
        let rng = game.rng_checkpoint();
        let snapshot = game.snapshot().canonical_bytes();
        let model = ValueModel {
            mean: [0.0; FEATURE_COUNT],
            scale: [1.0; FEATURE_COUNT],
            w1: [[0.0; FEATURE_COUNT]; 32],
            b1: [0.0; 32],
            w2: [[0.0; 32]; 16],
            b2: [0.0; 16],
            w3: [0.0; 16],
            b3: 12.0,
        };
        assert_eq!(model.predict(ValueFeatures([0.0; FEATURE_COUNT])), 12.0);
        let _ = model.predict(value_features(&game));
        assert_eq!(rng, game.rng_checkpoint());
        assert_eq!(snapshot, game.snapshot().canonical_bytes());
        Ok(())
    }
}
