use dodge_core::{EnemySerial, EnemyState, PicoFixed, PrivilegedView, WarningLine};

use crate::EnvError;
use crate::geometry::{
    self, PlayerBoxKind, RawAabb, RawBoxMeasures, RelativeVelocityRaw, WarningSegment,
};
use crate::raster::{AuxRaster, RasterChannels, RasterFlags};

pub const GLOBAL_DIM: usize = 14;
pub const ENTITY_DIM: usize = 16;
pub const ENEMY_SLOTS: usize = 64;
pub const RECT_SLOTS: usize = 16;
pub const ENTITY_SLOTS: usize = ENEMY_SLOTS + RECT_SLOTS;
pub const MOTION_VERSION: &str = "measured_center_delta_v1";

/// Metadata only. None of these values is appended to neural arrays.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Diagnostics {
    pub raw_history_samples: u64,
    pub unknown_enemy_samples: u64,
    pub unknown_rectangle_samples: u64,
    pub unknown_phase_samples: u64,
    pub admitted_enemies: usize,
    pub admitted_rectangles: usize,
    pub onscreen_warnings: usize,
    pub dropped_enemies: usize,
    pub dropped_enemy_total: u64,
    pub inverted_boxes: u64,
    pub inverted_axes: u64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Observation {
    pub global_feats: [[f32; GLOBAL_DIM]; 1],
    pub entity_feats: [[f32; ENTITY_DIM]; ENTITY_SLOTS],
    pub entity_types: [i64; ENTITY_SLOTS],
    pub entity_mask: [bool; ENTITY_SLOTS],
    /// Oldest to newest, contiguous [4,128,128].
    pub pixels: Option<Vec<u8>>,
    pub auxiliary: Option<Box<RasterChannels>>,
    pub pixel_valid: bool,
    /// False if either member is absent, or pixels precede terminal state.
    pub pixel_aux_pair_valid: bool,
    pub diagnostics: Diagnostics,
}

/// Contiguous row-major arrays, owned by this return value. `indices` defines
/// the row-to-stable-slot mapping, including caller-ordered partial resets.
#[derive(Clone, Debug, PartialEq)]
pub struct ObservationBatch {
    pub indices: Vec<usize>,
    pub global_feats: Vec<f32>,
    pub entity_feats: Vec<f32>,
    pub entity_types: Vec<i64>,
    pub entity_mask: Vec<bool>,
    pub pixels: Option<Vec<u8>>,
    pub auxiliary: Option<Vec<f32>>,
    pub pixel_valid: Vec<bool>,
    pub pixel_aux_pair_valid: Vec<bool>,
    pub diagnostics: Vec<Diagnostics>,
}

impl ObservationBatch {
    pub(crate) fn collect<'a>(
        indices: Vec<usize>,
        rows: impl Iterator<Item = &'a Observation>,
        pixels: bool,
        auxiliary: bool,
    ) -> Self {
        let mut batch = Self {
            indices,
            global_feats: Vec::new(),
            entity_feats: Vec::new(),
            entity_types: Vec::new(),
            entity_mask: Vec::new(),
            pixels: pixels.then(Vec::new),
            auxiliary: auxiliary.then(Vec::new),
            pixel_valid: Vec::new(),
            pixel_aux_pair_valid: Vec::new(),
            diagnostics: Vec::new(),
        };
        for row in rows {
            batch.global_feats.extend_from_slice(&row.global_feats[0]);
            batch
                .entity_feats
                .extend(row.entity_feats.iter().flatten().copied());
            batch.entity_types.extend_from_slice(&row.entity_types);
            batch.entity_mask.extend_from_slice(&row.entity_mask);
            if let (Some(out), Some(input)) = (&mut batch.pixels, &row.pixels) {
                out.extend_from_slice(input);
            }
            if let (Some(out), Some(input)) = (&mut batch.auxiliary, &row.auxiliary) {
                out.extend(input.iter().flatten().flatten().copied());
            }
            batch.pixel_valid.push(row.pixel_valid);
            batch.pixel_aux_pair_valid.push(row.pixel_aux_pair_valid);
            batch.diagnostics.push(row.diagnostics);
        }
        batch
    }

    pub fn batch_size(&self) -> usize {
        self.indices.len()
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct Motion {
    /// Raw Q16.16 units; halves remain representable in f64.
    dx: f64,
    dy: f64,
    dhx: f64,
    dhy: f64,
}

impl Motion {
    fn measured(now: RawBoxMeasures, old: RawBoxMeasures) -> Self {
        Self {
            dx: (now.center_x_twice_raw - old.center_x_twice_raw) as f64 / 2.0,
            dy: (now.center_y_twice_raw - old.center_y_twice_raw) as f64 / 2.0,
            dhx: (now.half_x_twice_raw - old.half_x_twice_raw) as f64 / 2.0,
            dhy: (now.half_y_twice_raw - old.half_y_twice_raw) as f64 / 2.0,
        }
    }
}

#[derive(Clone, Copy, Debug)]
struct MeasuredEntity {
    bounds: RawAabb,
    motion: Motion,
    type_id: i64,
    admitted: bool,
    lethal_now: bool,
    charging: bool,
    until_lethal: f64,
}

#[derive(Clone, Copy, Debug)]
struct EnemyHistory {
    serial: EnemySerial,
    measures: RawBoxMeasures,
}

#[derive(Clone, Copy, Debug)]
struct RectHistory {
    measures: RawBoxMeasures,
    sh: PicoFixed,
}

/// Only selected geometry and observed charge are retained. A None-pattern raw
/// frame clears rectangle history even if another activation appears within K.
#[derive(Default)]
pub(crate) struct History {
    enemies: Vec<EnemyHistory>,
    rectangles: Vec<RectHistory>,
    current_enemies: Vec<(EnemySerial, MeasuredEntity)>,
    current_rectangles: Vec<MeasuredEntity>,
    pattern_present: bool,
    diagnostics: Diagnostics,
}

fn enemy_geometry(enemy: &EnemyState) -> Result<(RawAabb, bool, i64), EnvError> {
    let x = enemy.x.raw();
    let y = enemy.y.raw();
    let s = enemy.size.raw();
    let type_id = match enemy.personality {
        0 => 1,
        1 => 2,
        -1 => 3,
        2 => 4,
        3 => 5,
        4 => 6,
        _ => return Err(EnvError::Contract("unsupported enemy personality")),
    };
    let beneficial = (4..=6).contains(&type_id);
    let (bounds, footprint) = if beneficial {
        (
            geometry::powerup_box(x, y),
            geometry::powerup_footprint(x, y),
        )
    } else {
        (
            geometry::enemy_box(x, y, s),
            geometry::enemy_footprint(x, y, s),
        )
    };
    Ok((bounds, footprint.intersects_world(), type_id))
}

impl History {
    pub(crate) fn cumulative_diagnostics(&self) -> Diagnostics {
        self.diagnostics
    }

    pub(crate) fn observe_raw(
        &mut self,
        view: PrivilegedView<'_>,
        serials: Option<&[EnemySerial]>,
    ) -> Result<(), EnvError> {
        let serials = serials.ok_or(EnvError::Contract("enemy identity metadata unavailable"))?;
        if serials.len() != view.enemies.len() || !serials.windows(2).all(|w| w[0] < w[1]) {
            return Err(EnvError::Contract("enemy identity length/order mismatch"));
        }
        self.diagnostics.raw_history_samples =
            self.diagnostics.raw_history_samples.saturating_add(1);
        let mut old_index = 0;
        let mut next = Vec::with_capacity(serials.len());
        self.current_enemies.clear();
        for (&serial, enemy) in serials.iter().zip(view.enemies) {
            while self
                .enemies
                .get(old_index)
                .is_some_and(|old| old.serial < serial)
            {
                old_index += 1;
            }
            let (bounds, admitted, type_id) = enemy_geometry(enemy)?;
            let measures = bounds.measures();
            let motion = if let Some(old) = self
                .enemies
                .get(old_index)
                .filter(|old| old.serial == serial)
            {
                Motion::measured(measures, old.measures)
            } else {
                self.diagnostics.unknown_enemy_samples =
                    self.diagnostics.unknown_enemy_samples.saturating_add(1);
                Motion::default()
            };
            let beneficial = (4..=6).contains(&type_id);
            next.push(EnemyHistory { serial, measures });
            self.current_enemies.push((
                serial,
                MeasuredEntity {
                    bounds,
                    motion,
                    type_id,
                    admitted,
                    lethal_now: !beneficial,
                    charging: false,
                    until_lethal: if beneficial { 1.0 } else { 0.0 },
                },
            ));
        }
        self.enemies = next;
        self.current_rectangles.clear();
        if let Some(pattern) = view.active_pattern {
            if pattern.pattern_type > 1 {
                return Err(EnvError::Contract("unsupported pattern type"));
            }
            let mut next = Vec::with_capacity(pattern.rects.len());
            for (index, rect) in pattern.rects.iter().enumerate() {
                let bounds = geometry::rectangle_box(
                    rect.x.raw(),
                    rect.y.raw(),
                    rect.width.raw(),
                    rect.height.raw(),
                );
                let measures = bounds.measures();
                let old = self
                    .pattern_present
                    .then(|| self.rectangles.get(index))
                    .flatten();
                let motion = old.map_or_else(
                    || {
                        self.diagnostics.unknown_rectangle_samples =
                            self.diagnostics.unknown_rectangle_samples.saturating_add(1);
                        Motion::default()
                    },
                    |old| Motion::measured(measures, old.measures),
                );
                let sh_delta = old.map(|old| i64::from(rect.sh.raw()) - i64::from(old.sh.raw()));
                let lethal_now = pattern.pattern_type == 1 || rect.sh == PicoFixed::from_int(2);
                let charging = !lethal_now
                    && rect.sh < PicoFixed::from_int(2)
                    && sh_delta.is_some_and(|d| d > 0);
                let until_lethal = if lethal_now {
                    0.0
                } else if charging {
                    ((f64::from(PicoFixed::from_int(2).raw()) - f64::from(rect.sh.raw()))
                        / sh_delta.unwrap_or(1) as f64)
                        .clamp(0.0, 120.0)
                        / 120.0
                } else {
                    1.0
                };
                if pattern.pattern_type == 0 && !lethal_now && sh_delta.is_none() {
                    self.diagnostics.unknown_phase_samples =
                        self.diagnostics.unknown_phase_samples.saturating_add(1);
                }
                self.current_rectangles.push(MeasuredEntity {
                    bounds,
                    motion,
                    type_id: if pattern.pattern_type == 0 { 7 } else { 8 },
                    admitted: geometry::rectangle_footprint(
                        rect.x.raw(),
                        rect.y.raw(),
                        rect.width.raw(),
                        rect.height.raw(),
                    )
                    .intersects_world(),
                    lethal_now,
                    charging,
                    until_lethal,
                });
                next.push(RectHistory {
                    measures,
                    sh: rect.sh,
                });
            }
            self.rectangles = next;
            self.pattern_present = true;
        } else {
            self.rectangles.clear();
            self.pattern_present = false;
        }
        Ok(())
    }

    pub(crate) fn observation<'a>(
        &mut self,
        view: PrivilegedView<'_>,
        warnings: impl Iterator<Item = &'a WarningLine>,
        auxiliary: bool,
    ) -> Result<Observation, EnvError> {
        let rects: Vec<_> = self
            .current_rectangles
            .iter()
            .filter(|e| e.admitted)
            .copied()
            .collect();
        if rects.len() > RECT_SLOTS {
            return Err(EnvError::RectangleOverflow(rects.len()));
        }
        let mut raster = AuxRaster::default();
        let mut onscreen_warnings = 0;
        for warning in warnings {
            let segment = WarningSegment::from_raw_q16(
                warning.x0.raw(),
                warning.y0.raw(),
                warning.x1.raw(),
                warning.y1.raw(),
            )
            .map_err(|_| EnvError::Contract("non-axis-aligned drawn warning"))?;
            if segment.intersects_world() {
                onscreen_warnings += 1;
                if auxiliary {
                    raster.paint_warning(
                        segment,
                        RasterFlags {
                            lethal_soon: true,
                            ..RasterFlags::default()
                        },
                    );
                }
            }
        }
        let mut enemies: Vec<_> = self
            .current_enemies
            .iter()
            .filter(|(_, e)| e.admitted)
            .map(|(serial, e)| {
                (
                    *serial,
                    *e,
                    entity_features(*e, view),
                    slab_frames(*e, view),
                )
            })
            .collect();
        let admitted_enemies = enemies.len();
        // Auxiliary targets include all admitted geometry, even a token dropped
        // by enemy overflow. The target is the current visible scene occupancy.
        for e in enemies.iter().map(|(_, e, _, _)| e).chain(rects.iter()) {
            let flags = RasterFlags {
                lethal_now: e.lethal_now,
                lethal_soon: e.charging,
                enemy: (1..=3).contains(&e.type_id),
                powerup: (4..=6).contains(&e.type_id),
                player: false,
            };
            // Paint even when targets are disabled to retain inverted diagnostics.
            raster.paint_box(e.bounds, flags);
        }
        if auxiliary {
            raster.paint_box(
                geometry::player_box(
                    view.player.x.raw(),
                    view.player.y.raw(),
                    view.player.size.raw(),
                    PlayerBoxKind::Powerup,
                ),
                RasterFlags {
                    player: true,
                    ..RasterFlags::default()
                },
            );
        }
        let dropped = admitted_enemies.saturating_sub(ENEMY_SLOTS);
        if dropped > 0 {
            enemies.sort_by(|a, b| a.3.total_cmp(&b.3).then(a.0.cmp(&b.0)));
            enemies.truncate(ENEMY_SLOTS);
        }
        self.diagnostics.dropped_enemy_total = self
            .diagnostics
            .dropped_enemy_total
            .saturating_add(dropped as u64);
        let raster_diagnostics = raster.diagnostics();
        let diagnostics = Diagnostics {
            admitted_enemies,
            admitted_rectangles: rects.len(),
            onscreen_warnings,
            dropped_enemies: dropped,
            inverted_boxes: raster_diagnostics.inverted_boxes,
            inverted_axes: raster_diagnostics.inverted_axes,
            ..self.diagnostics
        };
        let mut out = Observation {
            global_feats: [global_features(
                view,
                !rects.is_empty() || onscreen_warnings > 0,
            )],
            entity_feats: [[0.0; ENTITY_DIM]; ENTITY_SLOTS],
            entity_types: [0; ENTITY_SLOTS],
            entity_mask: [false; ENTITY_SLOTS],
            pixels: None,
            auxiliary: auxiliary.then(|| Box::new(raster.into_channels())),
            pixel_valid: false,
            pixel_aux_pair_valid: false,
            diagnostics,
        };
        for (i, (_, e, features, _)) in enemies.into_iter().enumerate() {
            out.entity_feats[i] = features;
            out.entity_types[i] = e.type_id;
            out.entity_mask[i] = true;
        }
        for (i, e) in rects.into_iter().enumerate() {
            let i = ENEMY_SLOTS + i;
            out.entity_feats[i] = entity_features(e, view);
            out.entity_types[i] = e.type_id;
            out.entity_mask[i] = true;
        }
        if !out
            .global_feats
            .iter()
            .flatten()
            .chain(out.entity_feats.iter().flatten())
            .all(|v| v.is_finite())
        {
            return Err(EnvError::Contract("nonfinite neural feature"));
        }
        Ok(out)
    }
}

fn global_features(view: PrivilegedView<'_>, pattern_visible: bool) -> [f32; GLOBAL_DIM] {
    let p = view.player;
    let x = p.x.to_double();
    let y = p.y.to_double();
    [
        ((x - 64.0) / 64.0) as f32,
        ((y - 64.0) / 64.0) as f32,
        (p.vx.to_double() / 2.5) as f32,
        (p.vy.to_double() / 2.5) as f32,
        (p.size.to_double() / 4.0) as f32,
        view.freeze_rate.to_f32(),
        (view.speed.to_double() / 3.0) as f32,
        (view.enemy_est.to_double() / 2.0) as f32,
        (view.score.to_double() / 50.0).tanh() as f32,
        f32::from(pattern_visible),
        ((x - 2.0) / 123.0) as f32,
        ((125.0 - x) / 123.0) as f32,
        ((y - 2.0) / 123.0) as f32,
        ((125.0 - y) / 123.0) as f32,
    ]
}

fn entity_features(e: MeasuredEntity, view: PrivilegedView<'_>) -> [f32; ENTITY_DIM] {
    let measures = e.bounds.measures();
    let cx = geometry::half_raw_to_pixels(measures.center_x_twice_raw);
    let cy = geometry::half_raw_to_pixels(measures.center_y_twice_raw);
    let kind = match e.type_id {
        4..=6 => PlayerBoxKind::Powerup,
        7..=8 => PlayerBoxKind::Rectangle,
        _ => PlayerBoxKind::EnemyFamily,
    };
    let player = geometry::player_box(
        view.player.x.raw(),
        view.player.y.raw(),
        view.player.size.raw(),
        kind,
    );
    let (gx, gy) = e.bounds.signed_gaps(player);
    let contact = geometry::slab_contact(
        e.bounds,
        player,
        RelativeVelocityRaw {
            x: e.motion.dx - f64::from(view.player.vx.raw()),
            y: e.motion.dy - f64::from(view.player.vy.raw()),
        },
    );
    let velocity_scale = f64::from(geometry::ONE_RAW) * 4.0;
    [
        ((cx - 64.0) / 128.0) as f32,
        ((cy - 64.0) / 128.0) as f32,
        (geometry::half_raw_to_pixels(measures.half_x_twice_raw) / 64.0) as f32,
        (geometry::half_raw_to_pixels(measures.half_y_twice_raw) / 64.0) as f32,
        ((cx - view.player.x.to_double()) / 128.0) as f32,
        ((cy - view.player.y.to_double()) / 128.0) as f32,
        (e.motion.dx / velocity_scale) as f32,
        (e.motion.dy / velocity_scale) as f32,
        (e.motion.dhx / velocity_scale) as f32,
        (e.motion.dhy / velocity_scale) as f32,
        (geometry::raw_to_pixels(gx) / 64.0) as f32,
        (geometry::raw_to_pixels(gy) / 64.0) as f32,
        (contact.frames / 120.0) as f32,
        e.until_lethal as f32,
        f32::from((4..=6).contains(&e.type_id)),
        f32::from(e.lethal_now),
    ]
}

fn slab_frames(e: MeasuredEntity, view: PrivilegedView<'_>) -> f64 {
    let kind = match e.type_id {
        4..=6 => PlayerBoxKind::Powerup,
        7..=8 => PlayerBoxKind::Rectangle,
        _ => PlayerBoxKind::EnemyFamily,
    };
    let player = geometry::player_box(
        view.player.x.raw(),
        view.player.y.raw(),
        view.player.size.raw(),
        kind,
    );
    geometry::slab_contact(
        e.bounds,
        player,
        RelativeVelocityRaw {
            x: e.motion.dx - f64::from(view.player.vx.raw()),
            y: e.motion.dy - f64::from(view.player.vy.raw()),
        },
    )
    .frames
}
