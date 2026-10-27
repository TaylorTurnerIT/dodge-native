//! Explicit teacher features. Snapshot metadata and future state stay outside this type.

use dodge_core::{FullState, PicoFixed, RenderState, Snapshot};

// Version 2 corrects moving-pattern lethality during expansion.
pub const FEATURE_SCHEMA_VERSION: u32 = 2;

#[derive(Clone, Debug, PartialEq)]
pub struct PlayerFeatures {
    pub x: f32,
    pub y: f32,
    pub vx: f32,
    pub vy: f32,
    pub size: f32,
}

#[derive(Clone, Debug, PartialEq)]
pub struct EnemyFeatures {
    pub x: f32,
    pub y: f32,
    pub vx: f32,
    pub vy: f32,
    pub size: f32,
    pub kind: i8,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RectangleFeatures {
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
    pub dx: f32,
    pub dy: f32,
    /// Whether the native player-collision check treats this rectangle as lethal.
    pub solid: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub struct WarningFeatures {
    pub x0: f32,
    pub y0: f32,
    pub x1: f32,
    pub y1: f32,
}

#[derive(Clone, Debug, PartialEq)]
pub struct TeacherFeatures {
    pub player: PlayerFeatures,
    pub speed: f32,
    pub freeze_rate: f32,
    pub freeze_active: bool,
    pub enemies: Vec<EnemyFeatures>,
    pub rectangles: Vec<RectangleFeatures>,
    pub warnings: Vec<WarningFeatures>,
}

impl TeacherFeatures {
    /// Coordinates use game pixels, velocities use native game units. Native
    /// `pget` capture cancels camera translation but retains its clipped edges.
    /// These are current-state features, not claims of same-frame observability.
    pub fn from_snapshot(snapshot: &Snapshot) -> Self {
        Self::from_parts(snapshot.logical_state(), snapshot.render_state())
    }

    fn from_parts(state: &FullState, render: &RenderState) -> Self {
        let camera_x = camera_offset(render.camera_x);
        let camera_y = camera_offset(render.camera_y);
        let visible = |x0: f32, y0: f32, x1: f32, y1: f32| {
            let min_x = (camera_x + i32::from(render.clip_x)).max(0) as f32;
            let min_y = (camera_y + i32::from(render.clip_y)).max(0) as f32;
            let max_x = (camera_x + i32::from(render.clip_x) + i32::from(render.clip_width) - 1)
                .min(127) as f32;
            let max_y = (camera_y + i32::from(render.clip_y) + i32::from(render.clip_height) - 1)
                .min(127) as f32;
            x0.min(x1) <= max_x && x0.max(x1) >= min_x && y0.min(y1) <= max_y && y0.max(y1) >= min_y
        };
        let enemies = state
            .enemies
            .iter()
            .filter_map(|enemy| {
                let x = enemy.x.to_f32();
                let y = enemy.y.to_f32();
                let size = enemy.size.to_f32();
                let radius = if enemy.personality >= 2 { 4.0 } else { 0.0 };
                let extent = if enemy.personality >= 2 {
                    4.0
                } else {
                    size.floor().max(0.0)
                };
                if !visible(
                    x.floor() - radius,
                    y.floor() - radius,
                    x.floor() + extent,
                    y.floor() + extent + 1.0,
                ) {
                    return None;
                }
                Some(EnemyFeatures {
                    x,
                    y,
                    vx: enemy.vx.to_f32(),
                    vy: enemy.vy.to_f32(),
                    size,
                    kind: enemy.personality,
                })
            })
            .collect();
        let mut rectangles = Vec::new();
        let mut warnings = Vec::new();
        if let Some(pattern) = state
            .active_pattern
            .and_then(|index| state.patterns.get(index))
        {
            for rect in &pattern.rects {
                let x = rect.x.to_f32();
                let y = rect.y.to_f32();
                let width = rect.width.to_f32();
                let height = rect.height.to_f32();
                if visible(
                    rect.x.round().to_f32(),
                    rect.y.round().to_f32(),
                    rect.x.round().to_f32() + rect.width.round().to_f32(),
                    rect.y.round().to_f32() + rect.height.round().to_f32() + 1.0,
                ) {
                    rectangles.push(RectangleFeatures {
                        x,
                        y,
                        width,
                        height,
                        dx: rect.dx.to_f32(),
                        dy: rect.dy.to_f32(),
                        solid: pattern.pattern_type == 1 || rect.sh == PicoFixed::from_int(2),
                    });
                }
                if !(rect.sh < PicoFixed::from_int(2) && pattern.pattern_type == 0)
                    && pattern.timer < PicoFixed::from_int(125)
                {
                    for line in &rect.warnings {
                        let (x0, y0, x1, y1) = (
                            line.x0.to_f32(),
                            line.y0.to_f32(),
                            line.x1.to_f32(),
                            line.y1.to_f32(),
                        );
                        if visible(x0, y0, x1, y1 + 1.0) {
                            warnings.push(WarningFeatures { x0, y0, x1, y1 });
                        }
                    }
                }
            }
        }
        Self {
            player: PlayerFeatures {
                x: state.player.x.to_f32(),
                y: state.player.y.to_f32(),
                vx: state.player.vx.to_f32(),
                vy: state.player.vy.to_f32(),
                size: state.player.size.to_f32(),
            },
            speed: state.speed.to_f32(),
            freeze_rate: state.freeze_rate.to_f32(),
            freeze_active: state.freeze_active,
            enemies,
            rectangles,
            warnings,
        }
    }
}

fn camera_offset(value: PicoFixed) -> i32 {
    let raw = i64::from(value.raw());
    if raw >= 0 {
        ((raw + (1 << 15)) / (1 << 16)) as i32
    } else {
        -(((-raw + (1 << 15)) / (1 << 16)) as i32)
    }
}

#[cfg(test)]
mod tests {
    use super::TeacherFeatures;
    use crate::{EnvironmentConfig, LearningEnv};
    use dodge_core::{EnemyState, PicoFixed};

    #[test]
    fn metadata_and_invisible_entities_do_not_enter_actor_features()
    -> Result<(), Box<dyn std::error::Error>> {
        let env = LearningEnv::new(EnvironmentConfig::default())?;
        let before = TeacherFeatures::from_snapshot(&env.current().snapshot);
        let mut state = env.current().snapshot.logical_state().clone();
        state.seed = 1234;
        state.highscores[0] = PicoFixed::from_int(100);
        state.rng.front = (state.rng.front + 1) % 31;
        state.patterns[0].mins = PicoFixed::from_int(999);
        state.enemies.push(EnemyState::normal(
            PicoFixed::from_int(-100),
            PicoFixed::from_int(-100),
            PicoFixed::from_int(3),
        ));
        assert_eq!(
            before,
            TeacherFeatures::from_parts(&state, env.current().snapshot.render_state())
        );
        Ok(())
    }

    #[test]
    fn offscreen_powerups_rectangles_and_warnings_are_filtered()
    -> Result<(), Box<dyn std::error::Error>> {
        let env = LearningEnv::new(EnvironmentConfig::default())?;
        let mut state = env.current().snapshot.logical_state().clone();
        let render = env.current().snapshot.render_state();
        let mut powerup = EnemyState::normal(
            PicoFixed::from_int(1000),
            PicoFixed::from_int(1000),
            PicoFixed::from_int(3),
        );
        powerup.personality = 2;
        state.enemies.push(powerup);
        state.active_pattern = Some(0);
        let pattern = &mut state.patterns[0];
        pattern.pattern_type = 1;
        pattern.timer = PicoFixed::ZERO;
        for rect in &mut pattern.rects {
            rect.x = PicoFixed::from_int(1000);
            rect.y = PicoFixed::from_int(1000);
            rect.sh = PicoFixed::from_int(2);
            rect.warnings = vec![dodge_core::WarningLine {
                x0: PicoFixed::from_int(1000),
                y0: PicoFixed::from_int(1000),
                x1: PicoFixed::from_int(1010),
                y1: PicoFixed::from_int(1010),
            }];
        }
        let hidden = TeacherFeatures::from_parts(&state, render);
        assert!(hidden.enemies.is_empty());
        assert!(hidden.rectangles.is_empty());
        assert!(hidden.warnings.is_empty());

        state.enemies[0].x = PicoFixed::from_int(64);
        state.enemies[0].y = PicoFixed::from_int(64);
        let rect = &mut state.patterns[0].rects[0];
        rect.x = PicoFixed::from_int(40);
        rect.y = PicoFixed::from_int(40);
        rect.warnings[0].x0 = PicoFixed::from_int(40);
        rect.warnings[0].y0 = PicoFixed::from_int(40);
        rect.warnings[0].x1 = PicoFixed::from_int(60);
        rect.warnings[0].y1 = PicoFixed::from_int(60);
        let visible = TeacherFeatures::from_parts(&state, render);
        assert_eq!(visible.enemies.len(), 1);
        assert_eq!(visible.rectangles.len(), 1);
        assert_eq!(visible.warnings.len(), 1);
        assert_eq!(visible.enemies[0].kind, 2);
        Ok(())
    }

    #[test]
    fn rectangle_solidity_matches_static_and_moving_player_collision_phases()
    -> Result<(), Box<dyn std::error::Error>> {
        let env = LearningEnv::new(EnvironmentConfig::default())?;
        let mut state = env.current().snapshot.logical_state().clone();
        let render = env.current().snapshot.render_state();
        state.active_pattern = Some(0);
        let pattern = state
            .patterns
            .first_mut()
            .ok_or("missing fixture pattern")?;
        pattern.rects.truncate(1);
        let rect = pattern
            .rects
            .first_mut()
            .ok_or("missing fixture rectangle")?;
        rect.x = PicoFixed::from_int(40);
        rect.y = PicoFixed::from_int(40);
        rect.width = PicoFixed::from_int(10);
        rect.height = PicoFixed::from_int(10);

        for (pattern_type, phase, expected) in [
            (0, 0, false),
            (0, 1, false),
            (0, 2, true),
            (1, 0, true),
            (1, 1, true),
            (1, 2, true),
        ] {
            state.patterns[0].pattern_type = pattern_type;
            state.patterns[0].rects[0].sh = PicoFixed::from_int(phase);
            let features = TeacherFeatures::from_parts(&state, render);
            assert_eq!(features.rectangles.len(), 1);
            let rect = features
                .rectangles
                .first()
                .ok_or("missing visible rectangle")?;
            assert_eq!(
                rect.solid, expected,
                "pattern_type={pattern_type}, phase={phase}"
            );
        }
        Ok(())
    }
}
