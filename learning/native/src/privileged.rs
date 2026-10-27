//! Versioned, unfiltered gameplay projection for the entity-transformer teacher.
//!
//! No object is discarded for being offscreen, inactive, or not yet rendered.
//! The `spatial` flag only selects geometry eligible for the image-attention
//! bridge. Bounds are half-open native-pixel intervals; model features are
//! normalized separately. This is a structured gameplay projection, not a
//! byte-complete snapshot: framebuffer bytes are supplied through `pixels`.

use dodge_core::{FullState, Mode, PatternTarget, PicoFixed, RenderState, Snapshot};

pub const PRIVILEGED_SCHEMA_VERSION: u32 = 1;
pub const PRIVILEGED_GLOBAL_DIM: usize = 64;
pub const PRIVILEGED_ENTITY_DIM: usize = 32;

/// Stable token kinds. Kind 9 is reserved because lifecycle state fits globals.
/// 0 player, 1 enemy/powerup, 2 rectangle, 3 warning, 4 pattern,
/// 5 queued target, 6 current spawn, 7 particle, 8 RNG word, 10 settings,
/// 11 highscores, 12 render-palette entry, 13 queued target spawn, 14 variant.
#[derive(Clone, Debug, PartialEq)]
pub struct PrivilegedEntity {
    pub features: [f32; PRIVILEGED_ENTITY_DIM],
    pub kind: u8,
    pub bounds: [f32; 4],
    pub spatial: bool,
}

impl PrivilegedEntity {
    fn new(kind: u8, values: &[f32]) -> Self {
        let mut features = [0.0; PRIVILEGED_ENTITY_DIM];
        features[..values.len()].copy_from_slice(values);
        Self {
            features,
            kind,
            bounds: [0.0; 4],
            spatial: false,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct PrivilegedFeatures {
    pub globals: [f32; PRIVILEGED_GLOBAL_DIM],
    pub entities: Vec<PrivilegedEntity>,
    pub capture_bounds: [f32; 4],
}

impl PrivilegedFeatures {
    pub fn from_snapshot(snapshot: &Snapshot) -> Self {
        Self::from_parts(snapshot.logical_state(), snapshot.render_state())
    }

    fn from_parts(state: &FullState, render: &RenderState) -> Self {
        let mut entities = Vec::new();
        // Player is always first. Kinematic first five slots are x/128,
        // y/128, vx/4, vy/4, size/8 for player and enemy tokens.
        entities.push(PrivilegedEntity::new(
            0,
            &[
                state.player.x.to_f32() / 128.0,
                state.player.y.to_f32() / 128.0,
                state.player.vx.to_f32() / 4.0,
                state.player.vy.to_f32() / 4.0,
                state.player.size.to_f32() / 8.0,
            ],
        ));
        // Both direct gameplay render branches call render_game. Dead game
        // states render the game-over overlay and must not supply hazard maps.
        let live =
            matches!(state.lifecycle.mode, Mode::Game | Mode::Terminal) && !state.lifecycle.dead;
        append_enemies(state, live, &mut entities);
        append_patterns(state, live, &mut entities);
        append_misc(state, render, &mut entities);

        // Drawing clips in physical-screen coordinates, and canonical pget
        // capture maps those coordinates back through the current camera.
        // Intersect the screen first: a clip can extend past either edge.
        let camera_x = camera_offset(render.camera_x);
        let camera_y = camera_offset(render.camera_y);
        let clip_x = i32::from(render.clip_x);
        let clip_y = i32::from(render.clip_y);
        let screen_x0 = clip_x.clamp(0, 128);
        let screen_y0 = clip_y.clamp(0, 128);
        let screen_x1 = (clip_x + i32::from(render.clip_width)).clamp(0, 128);
        let screen_y1 = (clip_y + i32::from(render.clip_height)).clamp(0, 128);
        let capture_bounds = [
            (camera_x + screen_x0).clamp(0, 128) as f32,
            (camera_y + screen_y0).clamp(0, 128) as f32,
            (camera_x + screen_x1).clamp(0, 128) as f32,
            (camera_y + screen_y1).clamp(0, 128) as f32,
        ];
        Self {
            globals: globals(state, render),
            entities,
            capture_bounds,
        }
    }
}

fn flag(value: bool) -> f32 {
    f32::from(u8::from(value))
}

fn low(value: u32) -> f32 {
    (value & 0xffff) as f32 / 65_535.0
}

fn high(value: u32) -> f32 {
    (value >> 16) as f32 / 65_535.0
}

fn mode(value: Mode) -> f32 {
    (match value {
        Mode::Menu => 0.0,
        Mode::TransitionToGame => 1.0,
        Mode::Game => 2.0,
        Mode::Terminal => 3.0,
        Mode::Settings => 4.0,
        Mode::TransitionToSettings => 5.0,
        Mode::TransitionToMenu => 6.0,
    }) / 6.0
}

/// Global slots are fixed in schema 1. Time/count fields use 18,000 frames;
/// positions use 128 pixels; velocities and bounce limits use four units.
fn globals(state: &FullState, render: &RenderState) -> [f32; PRIVILEGED_GLOBAL_DIM] {
    [
        state.speed.to_f32() / 4.0,            // 0
        state.freeze_rate.to_f32(),            // 1
        flag(state.freeze_active),             // 2
        state.enemy_timer.to_f32() / 18_000.0, // 3
        state.enemy_est.to_f32() / 4096.0,     // 4
        state.enemy_stats[0].to_f32() / 128.0, // 5
        state.enemy_stats[1].to_f32() / 128.0,
        state.enemy_stats[2].to_f32() / 128.0,
        state.enemy_stats[3].to_f32() / 128.0,
        state.enemy_stats[4].to_f32() / 128.0,            // 9
        state.friendly_timer as f32 / 18_000.0,           // 10
        flag(state.friendly_enabled),                     // 11
        state.enemy_max_size.to_f32() / 8.0,              // 12
        state.freeze_timer as f32 / 18_000.0,             // 13
        state.size_timer.to_f32() / 18_000.0,             // 14
        flag(state.patterns_enabled),                     // 15
        flag(state.powerups_enabled),                     // 16
        state.pattern_timer as f32 / 18_000.0,            // 17
        state.pattern_delay_frames as f32 / 18_000.0,     // 18
        flag(state.pattern_active),                       // 19
        flag(state.active_pattern.is_some()),             // 20
        state.active_pattern.unwrap_or(0) as f32 / 128.0, // 21
        flag(state.new_highscore),                        // 22
        flag(state.can_click),                            // 23
        flag(state.has_played),                           // 24
        flag(state.should_collide),                       // 25
        flag(state.enemy_should_collide),                 // 26
        state.bounce_cap_static.to_f32() / 4.0,           // 27
        state.bounce_cap_moving.to_f32() / 4.0,           // 28
        state.bounce_cap.to_f32() / 4.0,                  // 29
        state.score.to_f32() / 18_000.0,                  // 30
        state.survival_frames as f32 / 18_000.0,          // 31
        state.shake.to_f32() / 128.0,                     // 32
        state.camera_x.to_f32() / 128.0,                  // 33
        state.camera_y.to_f32() / 128.0,                  // 34
        f32::from(state.transition_render_y) / 128.0,     // 35
        mode(state.transition_from),                      // 36
        low(state.seed),                                  // 37
        high(state.seed),                                 // 38
        low(state.rng.seed),                              // 39
        high(state.rng.seed),                             // 40
        f32::from(state.rng.front) / 31.0,                // 41
        f32::from(state.rng.rear) / 31.0,                 // 42
        state.lifecycle.frame as f32 / 18_000.0,          // 43
        mode(state.lifecycle.mode),                       // 44
        f32::from(state.lifecycle.transition_y) / 128.0,  // 45
        flag(state.lifecycle.started),                    // 46
        flag(state.lifecycle.game_ready),                 // 47
        flag(state.lifecycle.dead),                       // 48
        f32::from(state.input.current_mask()) / 63.0,     // 49
        f32::from(state.input.previous_mask()) / 63.0,    // 50
        flag(state.input.source_input_mode()),            // 51
        f32::from(render.draw_color) / 15.0,              // 52
        f32::from(render.fill_pattern) / 65_535.0,        // 53
        render.camera_x.to_f32() / 128.0,                 // 54
        render.camera_y.to_f32() / 128.0,                 // 55
        f32::from(render.clip_x) / 128.0,                 // 56
        f32::from(render.clip_y) / 128.0,                 // 57
        f32::from(render.clip_width) / 128.0,             // 58
        f32::from(render.clip_height) / 128.0,            // 59
        f32::from(render.transition_y) / 128.0,           // 60
        state.patterns.len() as f32 / 128.0,              // 61
        state.enemies.len() as f32 / 4096.0,              // 62
        state.particles.len() as f32 / 16_384.0,          // 63
    ]
}

fn append_enemies(state: &FullState, live: bool, out: &mut Vec<PrivilegedEntity>) {
    for enemy in &state.enemies {
        // Beyond shared kinematics: max_size/8, personality/4, speed/4,
        // inside, is_dying, isizing, life-present, life/18,000.
        let mut entity = PrivilegedEntity::new(
            1,
            &[
                enemy.x.to_f32() / 128.0,
                enemy.y.to_f32() / 128.0,
                enemy.vx.to_f32() / 4.0,
                enemy.vy.to_f32() / 4.0,
                enemy.size.to_f32() / 8.0,
                enemy.max_size.to_f32() / 8.0,
                f32::from(enemy.personality) / 4.0,
                enemy.speed.to_f32() / 4.0,
                flag(enemy.inside),
                flag(enemy.is_dying),
                flag(enemy.isizing),
                flag(enemy.life.is_some()),
                enemy.life.unwrap_or(PicoFixed::ZERO).to_f32() / 18_000.0,
            ],
        );
        // Match raster integer extraction before any potentially lossy f32
        // conversion (raw fixed-point values close to large integers round).
        let x = (enemy.x.raw() >> 16) as f32;
        let y = (enemy.y.raw() >> 16) as f32;
        entity.bounds = if enemy.personality >= 2 {
            [x - 4.0, y - 4.0, x + 5.0, y + 6.0]
        } else {
            let size = (enemy.size.raw() >> 16).max(0) as f32;
            [x, y, x + size + 1.0, y + size + 2.0]
        };
        entity.spatial = live;
        out.push(entity);
    }
}

fn append_patterns(state: &FullState, live: bool, out: &mut Vec<PrivilegedEntity>) {
    for (pi, pattern) in state.patterns.iter().enumerate() {
        let active = state.active_pattern == Some(pi);
        let pi = pi as f32 / 128.0;
        // Pattern slots: id/255, index/128, mins/18000, maxs/18000,
        // probability/16, smooth, pattern_type, bounce_cap, spawn_enabled,
        // automatic_variant-present, automatic_variant/255, special/128,
        // counter/18000, timer/18000, rect_count/4096, variant_count/256, active.
        out.push(PrivilegedEntity::new(
            4,
            &[
                f32::from(pattern.id) / 255.0,
                pi,
                pattern.mins.to_f32() / 18_000.0,
                pattern.maxs.to_f32() / 18_000.0,
                pattern.probability.to_f32() / 16.0,
                flag(pattern.smooth),
                f32::from(pattern.pattern_type),
                flag(pattern.bounce_cap),
                flag(pattern.spawn_enabled),
                flag(pattern.automatic_variant.is_some()),
                f32::from(pattern.automatic_variant.unwrap_or(0)) / 255.0,
                pattern.special.to_f32() / 128.0,
                pattern.counter as f32 / 18_000.0,
                pattern.timer.to_f32() / 18_000.0,
                pattern.rects.len() as f32 / 4096.0,
                pattern.variants.len() as f32 / 256.0,
                flag(active),
            ],
        ));
        for (vi, variant) in pattern.variants.iter().enumerate() {
            out.push(PrivilegedEntity::new(
                14,
                &[pi, vi as f32 / 256.0, f32::from(*variant) / 255.0],
            ));
        }
        for (ri, rect) in pattern.rects.iter().enumerate() {
            let ri = ri as f32 / 4096.0;
            let solid = pattern.pattern_type == 1 || rect.sh == PicoFixed::from_int(2);
            // Rectangle slots after kinematics: width/128, height/128,
            // speed/16, target_index/256, wait/18000, shown, sh/2,
            // collision_done, finished, pattern index, rect index, active, solid.
            let mut entity = PrivilegedEntity::new(
                2,
                &[
                    rect.x.to_f32() / 128.0,
                    rect.y.to_f32() / 128.0,
                    rect.dx.to_f32() / 4.0,
                    rect.dy.to_f32() / 4.0,
                    rect.width.to_f32().max(rect.height.to_f32()) / 8.0,
                    rect.width.to_f32() / 128.0,
                    rect.height.to_f32() / 128.0,
                    rect.speed.to_f32() / 16.0,
                    rect.target_index as f32 / 256.0,
                    rect.wait.to_f32() / 18_000.0,
                    flag(rect.shown),
                    rect.sh.to_f32() / 2.0,
                    flag(rect.collision_done),
                    flag(rect.finished),
                    pi,
                    ri,
                    flag(active),
                    flag(solid),
                ],
            );
            let x = rect.x.round().to_f32();
            let y = rect.y.round().to_f32();
            let x1 = x + rect.width.round().to_f32();
            let y1 = y + rect.height.round().to_f32();
            entity.bounds = [x.min(x1), y.min(y1), x.max(x1) + 1.0, y.max(y1) + 2.0];
            entity.spatial = live && active;
            out.push(entity);
            let warnings_shown = !(rect.sh < PicoFixed::from_int(2) && pattern.pattern_type == 0)
                && pattern.timer < PicoFixed::from_int(125);
            for (wi, warning) in rect.warnings.iter().enumerate() {
                // Warning slots: endpoints/128, pattern, rectangle, warning
                // indices, and renderer's warning-visible phase flag.
                let mut entity = PrivilegedEntity::new(
                    3,
                    &[
                        warning.x0.to_f32() / 128.0,
                        warning.y0.to_f32() / 128.0,
                        warning.x1.to_f32() / 128.0,
                        warning.y1.to_f32() / 128.0,
                        pi,
                        ri,
                        wi as f32 / 256.0,
                        flag(warnings_shown),
                    ],
                );
                let x0 = warning.x0.round().to_f32();
                let y0 = warning.y0.round().to_f32();
                let x1 = warning.x1.round().to_f32();
                let y1 = warning.y1.round().to_f32();
                entity.bounds = [x0.min(x1), y0.min(y1), x0.max(x1) + 1.0, y0.max(y1) + 2.0];
                entity.spatial = live && active && warnings_shown;
                out.push(entity);
            }
            for (ti, target) in rect.targets.iter().enumerate() {
                // Target slots: pattern, rectangle, target indices; tag
                // (0 Move, 1 Wait, 2 SetFyou, 3 SetSpawns); then variant data.
                let mut values = [0.0; 12];
                values[0] = pi;
                values[1] = ri;
                values[2] = ti as f32 / 256.0;
                match target {
                    PatternTarget::Move {
                        x,
                        y,
                        width,
                        height,
                    } => {
                        values[4] = x.to_f32() / 128.0;
                        values[5] = y.to_f32() / 128.0;
                        values[6] = width.to_f32() / 128.0;
                        values[7] = height.to_f32() / 128.0;
                    }
                    PatternTarget::Wait(wait) => {
                        values[3] = 1.0;
                        values[4] = wait.to_f32() / 18_000.0;
                    }
                    PatternTarget::SetFyou(enabled) => {
                        values[3] = 2.0;
                        values[4] = flag(*enabled);
                    }
                    PatternTarget::SetSpawns(spawns) => {
                        values[3] = 3.0;
                        values[4] = spawns.len() as f32 / 256.0;
                        for (si, spawn) in spawns.iter().enumerate() {
                            out.push(PrivilegedEntity::new(
                                13,
                                &[
                                    spawn.x.to_f32() / 128.0,
                                    spawn.y.to_f32() / 128.0,
                                    pi,
                                    ri,
                                    ti as f32 / 256.0,
                                    si as f32 / 256.0,
                                ],
                            ));
                        }
                    }
                }
                out.push(PrivilegedEntity::new(5, &values));
            }
        }
    }
}

fn append_misc(state: &FullState, render: &RenderState, out: &mut Vec<PrivilegedEntity>) {
    for spawn in &state.spawns {
        out.push(PrivilegedEntity::new(
            6,
            &[spawn.x.to_f32() / 128.0, spawn.y.to_f32() / 128.0],
        ));
    }
    for particle in &state.particles {
        // Particle slots: x/128, y/128, dx/4, dy/4, radius/8, kind,
        // max_age/18000, age/18000, color/15, colors[3]/15, color_count/3.
        // Cosmetic particles never enter the hazard-attention target.
        out.push(PrivilegedEntity::new(
            7,
            &[
                particle.x.to_f32() / 128.0,
                particle.y.to_f32() / 128.0,
                particle.dx.to_f32() / 4.0,
                particle.dy.to_f32() / 4.0,
                particle.radius.to_f32() / 8.0,
                f32::from(particle.kind),
                particle.max_age.to_f32() / 18_000.0,
                particle.age as f32 / 18_000.0,
                f32::from(particle.color) / 15.0,
                f32::from(particle.colors[0]) / 15.0,
                f32::from(particle.colors[1]) / 15.0,
                f32::from(particle.colors[2]) / 15.0,
                f32::from(particle.color_count) / 3.0,
            ],
        ));
    }
    // Split u32 words into two exactly representable 16-bit chunks before
    // normalization, avoiding loss of low RNG bits through a direct f32 cast.
    for (index, word) in state.rng.state.iter().enumerate() {
        out.push(PrivilegedEntity::new(
            8,
            &[index as f32 / 31.0, low(*word), high(*word)],
        ));
    }
    let settings = state.settings;
    // Settings slots: theme_index/16, background/15, shadow/15, difficulty/3,
    // patterns_enabled, powerups_enabled, cursor/16, message_timer/255,
    // message_sprite/255, message_x/128, message_y/128.
    out.push(PrivilegedEntity::new(
        10,
        &[
            f32::from(settings.theme_index) / 16.0,
            f32::from(settings.theme_background) / 15.0,
            f32::from(settings.theme_shadow) / 15.0,
            f32::from(settings.difficulty) / 3.0,
            flag(settings.patterns_enabled),
            flag(settings.powerups_enabled),
            f32::from(settings.cursor) / 16.0,
            f32::from(settings.message_timer) / 255.0,
            f32::from(settings.message_sprite) / 255.0,
            f32::from(settings.message_x) / 128.0,
            f32::from(settings.message_y) / 128.0,
        ],
    ));
    // Highscore slots 0..12 preserve the complete fixed-size table.
    out.push(PrivilegedEntity::new(
        11,
        &state.highscores.map(|score| score.to_f32() / 18_000.0),
    ));
    for index in 0..16 {
        // Render token: palette index/15, draw mapping/15, screen mapping/15,
        // transparency. Camera/clip/fill state already lives in globals.
        out.push(PrivilegedEntity::new(
            12,
            &[
                index as f32 / 15.0,
                f32::from(render.draw_palette[index]) / 15.0,
                f32::from(render.screen_palette[index]) / 15.0,
                flag(render.transparent[index]),
            ],
        ));
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
    use super::*;
    use crate::{EnvironmentConfig, LearningEnv, observation::TeacherFeatures};
    use dodge_core::EnemyState;

    #[test]
    fn offscreen_enemies_are_preserved_without_changing_student_pixels()
    -> Result<(), Box<dyn std::error::Error>> {
        let env = LearningEnv::new(EnvironmentConfig::default())?;
        let snapshot = &env.current().snapshot;
        let pixels_before = *snapshot.pixels();
        let mut state = snapshot.logical_state().clone();
        let before = PrivilegedFeatures::from_parts(&state, snapshot.render_state());
        state.enemies.push(EnemyState::normal(
            PicoFixed::from_int(-100),
            PicoFixed::from_int(1000),
            PicoFixed::from_int(3),
        ));
        let after = PrivilegedFeatures::from_parts(&state, snapshot.render_state());
        let enemies: Vec<_> = after.entities.iter().filter(|row| row.kind == 1).collect();
        assert_eq!(enemies.len(), 1);
        assert_eq!(enemies[0].features[0], -100.0 / 128.0);
        assert_eq!(enemies[0].features[1], 1000.0 / 128.0);
        assert_ne!(before, after);
        assert_eq!(*snapshot.pixels(), pixels_before);
        assert!(TeacherFeatures::from_snapshot(snapshot).enemies.is_empty());
        Ok(())
    }

    #[test]
    fn hidden_timers_targets_and_rng_change_privileged_projection()
    -> Result<(), Box<dyn std::error::Error>> {
        let env = LearningEnv::new(EnvironmentConfig::default())?;
        let snapshot = &env.current().snapshot;
        let mut state = snapshot.logical_state().clone();
        let before = PrivilegedFeatures::from_parts(&state, snapshot.render_state());
        state.freeze_timer += 1;
        let timer = PrivilegedFeatures::from_parts(&state, snapshot.render_state());
        assert_ne!(before.globals, timer.globals);
        let rect = state
            .patterns
            .first_mut()
            .and_then(|p| p.rects.first_mut())
            .ok_or("missing test pattern rectangle")?;
        rect.targets
            .push(PatternTarget::Wait(PicoFixed::from_int(123)));
        let queued = PrivilegedFeatures::from_parts(&state, snapshot.render_state());
        assert!(queued.entities.len() > timer.entities.len());
        assert!(
            queued
                .entities
                .iter()
                .any(|row| row.kind == 5 && row.features[4] == 123.0 / 18_000.0)
        );
        assert!(
            queued
                .entities
                .iter()
                .filter(|row| row.kind == 2)
                .all(|row| !row.spatial)
        );
        state.rng.state[0] ^= 1;
        let rng = PrivilegedFeatures::from_parts(&state, snapshot.render_state());
        let first_rng = |features: &PrivilegedFeatures| {
            features.entities.iter().find(|row| row.kind == 8).cloned()
        };
        assert_ne!(first_rng(&queued), first_rng(&rng));
        Ok(())
    }

    #[test]
    fn active_geometry_has_half_open_bounds_and_query_is_pure()
    -> Result<(), Box<dyn std::error::Error>> {
        let env = LearningEnv::new(EnvironmentConfig::default())?;
        let snapshot = &env.current().snapshot;
        let canonical = snapshot.canonical_bytes();
        let features = PrivilegedFeatures::from_snapshot(snapshot);
        assert_eq!(features.entities[0].kind, 0);
        assert_eq!(
            features.entities[0].features[0],
            snapshot.logical_state().player.x.to_f32() / 128.0
        );
        assert_eq!(features.capture_bounds, [0.0, 0.0, 128.0, 128.0]);
        assert_eq!(snapshot.canonical_bytes(), canonical);
        assert!(features.globals.iter().all(|value| value.is_finite()));
        assert!(
            features
                .entities
                .iter()
                .flat_map(|row| row.features)
                .all(f32::is_finite)
        );
        let mut state = snapshot.logical_state().clone();
        state.active_pattern = Some(0);
        let active = PrivilegedFeatures::from_parts(&state, snapshot.render_state());
        assert!(
            active
                .entities
                .iter()
                .any(|row| row.kind == 2 && row.spatial)
        );
        assert!(
            active
                .entities
                .iter()
                .filter(|row| row.spatial)
                .all(|row| row.bounds[0] < row.bounds[2] && row.bounds[1] < row.bounds[3])
        );
        let mut render = snapshot.render_state().clone();
        render.camera_x = PicoFixed::from_int(3);
        render.clip_x = 2;
        render.clip_width = 10;
        let clipped = PrivilegedFeatures::from_parts(&state, &render);
        assert_eq!(clipped.capture_bounds, [5.0, 0.0, 15.0, 128.0]);
        Ok(())
    }

    #[test]
    fn capture_bounds_intersect_physical_screen_before_camera_projection()
    -> Result<(), Box<dyn std::error::Error>> {
        let env = LearningEnv::new(EnvironmentConfig::default())?;
        let snapshot = &env.current().snapshot;
        let mut render = snapshot.render_state().clone();
        render.camera_x = PicoFixed::from_int(-3);
        render.camera_y = PicoFixed::from_int(4);
        render.clip_x = 20;
        render.clip_y = -8;
        // The clip extends beyond the physical screen on both axes.
        render.clip_width = 128;
        render.clip_height = 128;
        let features = PrivilegedFeatures::from_parts(snapshot.logical_state(), &render);
        assert_eq!(features.capture_bounds, [17.0, 4.0, 125.0, 124.0]);

        render.clip_x = -20;
        render.clip_y = 0;
        render.camera_x = PicoFixed::from_f32(0.5);
        render.camera_y = PicoFixed::from_f32(-0.5);
        let features = PrivilegedFeatures::from_parts(snapshot.logical_state(), &render);
        assert_eq!(features.capture_bounds, [1.0, 0.0, 109.0, 127.0]);
        Ok(())
    }

    #[test]
    fn spatial_phase_flags_match_pattern_renderer_even_when_shown_is_false()
    -> Result<(), Box<dyn std::error::Error>> {
        let env = LearningEnv::new(EnvironmentConfig::default())?;
        let snapshot = &env.current().snapshot;
        let mut state = snapshot.logical_state().clone();
        state.active_pattern = Some(0);
        state.patterns[0].rects.truncate(1);
        let rect = state.patterns[0]
            .rects
            .first_mut()
            .ok_or("missing test rectangle")?;
        rect.shown = false; // render_pattern does not branch on this field.
        rect.x = PicoFixed::from_int(40);
        rect.y = PicoFixed::from_int(50);
        rect.width = PicoFixed::from_int(10);
        rect.height = PicoFixed::from_int(20);
        rect.warnings = vec![dodge_core::WarningLine {
            x0: PicoFixed::from_int(1),
            y0: PicoFixed::from_int(2),
            x1: PicoFixed::from_int(10),
            y1: PicoFixed::from_int(20),
        }];
        for (pattern_type, phase, timer, expected_warning) in [
            (0, 0, 124, false),
            (0, 1, 124, false),
            (0, 2, 124, true),
            (0, 2, 125, false),
            (1, 0, 124, true),
            (1, 1, 124, true),
            (1, 2, 125, false),
        ] {
            state.patterns[0].pattern_type = pattern_type;
            state.patterns[0].timer = PicoFixed::from_int(timer);
            state.patterns[0].rects[0].sh = PicoFixed::from_int(phase);
            let features = PrivilegedFeatures::from_parts(&state, snapshot.render_state());
            let rectangle = features
                .entities
                .iter()
                .find(|row| row.kind == 2)
                .ok_or("missing rectangle token")?;
            let warning = features
                .entities
                .iter()
                .find(|row| row.kind == 3)
                .ok_or("missing warning token")?;
            assert!(rectangle.spatial);
            assert_eq!(rectangle.bounds, [40.0, 50.0, 51.0, 72.0]);
            assert_eq!(warning.spatial, expected_warning);
            assert_eq!(warning.bounds, [1.0, 2.0, 11.0, 22.0]);
        }

        for (mode, dead, expected) in [
            (Mode::Game, false, true),
            (Mode::Terminal, false, true),
            (Mode::Game, true, false),
            (Mode::Terminal, true, false),
            (Mode::Menu, false, false),
            (Mode::Settings, false, false),
        ] {
            state.lifecycle.mode = mode;
            state.lifecycle.dead = dead;
            let features = PrivilegedFeatures::from_parts(&state, snapshot.render_state());
            let rectangle = features
                .entities
                .iter()
                .find(|row| row.kind == 2)
                .ok_or("missing rectangle token")?;
            assert_eq!(rectangle.spatial, expected);
            if !expected {
                assert!(features.entities.iter().all(|row| !row.spatial));
            }
        }
        Ok(())
    }

    #[test]
    fn enemy_bounds_extract_fixed_integer_before_float_conversion()
    -> Result<(), Box<dyn std::error::Error>> {
        let env = LearningEnv::new(EnvironmentConfig::default())?;
        let snapshot = &env.current().snapshot;
        let mut state = snapshot.logical_state().clone();
        let mut enemy = EnemyState::normal(
            PicoFixed::from_raw(i32::MAX),
            PicoFixed::from_f32(-1.25),
            PicoFixed::from_int(3),
        );
        enemy.size = PicoFixed::from_int(3);
        state.enemies.push(enemy);
        let features = PrivilegedFeatures::from_parts(&state, snapshot.render_state());
        let row = features
            .entities
            .iter()
            .find(|row| row.kind == 1)
            .ok_or("missing enemy token")?;
        assert_eq!(row.bounds, [32767.0, -2.0, 32771.0, 3.0]);
        Ok(())
    }
}
