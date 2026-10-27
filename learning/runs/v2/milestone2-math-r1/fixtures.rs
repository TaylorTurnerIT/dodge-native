#![forbid(unsafe_code)]
#![deny(warnings)]

#[path = "../../../../crates/dodge-rl-env/src/geometry.rs"]
pub mod geometry;
#[path = "../../../../crates/dodge-rl-env/src/raster.rs"]
pub mod raster;

use geometry::{
    PixelFootprint, PlayerBoxKind, RawAabb, RawInterval, RelativeVelocityRaw, SegmentError,
    WarningSegment, enemy_box, enemy_footprint, floor_raw_q16, half_raw_to_pixels, player_box,
    powerup_box, powerup_footprint, raw_to_pixels, rectangle_box, rectangle_footprint,
    round_raw_q16, slab_contact,
};
use raster::{AuxRaster, CELL_RAW, Channel, RasterFlags, ceil_cell, floor_cell, interval_patches};

const Q: i32 = 1 << 16;

const fn q(pixels: i32) -> i32 {
    pixels * Q
}

fn box_px(x0: i32, y0: i32, x1: i32, y1: i32) -> RawAabb {
    RawAabb::from_raw_q16(q(x0), q(y0), q(x1), q(y1))
}

fn velocity(x: f64, y: f64) -> RelativeVelocityRaw {
    RelativeVelocityRaw {
        x: x * f64::from(Q),
        y: y * f64::from(Q),
    }
}

fn occupied(raster: &AuxRaster, channel: Channel) -> Vec<(usize, usize)> {
    raster
        .channel(channel)
        .iter()
        .enumerate()
        .flat_map(|(y, row)| {
            row.iter()
                .enumerate()
                .filter(|(_, cell)| **cell == 1.0)
                .map(move |(x, _)| (x, y))
        })
        .collect()
}

fn enemy_flags() -> RasterFlags {
    RasterFlags {
        lethal_now: true,
        enemy: true,
        ..RasterFlags::default()
    }
}

fn warning_flags() -> RasterFlags {
    RasterFlags {
        lethal_soon: true,
        ..RasterFlags::default()
    }
}

#[test]
fn type_specific_player_half_sizes_and_literal_entity_offsets() {
    for (size, half_enemy, half_powerup, half_rectangle) in [(4, 3, 4, 2), (2, 1, 2, 0)] {
        for (kind, half) in [
            (PlayerBoxKind::EnemyFamily, half_enemy),
            (PlayerBoxKind::Powerup, half_powerup),
            (PlayerBoxKind::Rectangle, half_rectangle),
        ] {
            assert_eq!(
                player_box(q(10), q(20), q(size), kind),
                box_px(10 - half, 20 - half, 10 + half, 20 + half)
            );
        }
    }
    assert_eq!(enemy_box(q(10), q(20), q(3)), box_px(10, 20, 13, 23));
    assert_eq!(powerup_box(q(10), q(20)), box_px(6, 16, 14, 24));
    assert_eq!(
        rectangle_box(q(10), q(20), q(3), q(4)),
        box_px(10, 20, 12, 23)
    );
}

#[test]
fn strict_type_edges_are_not_contact_collisions() {
    for kind in [
        PlayerBoxKind::EnemyFamily,
        PlayerBoxKind::Powerup,
        PlayerBoxKind::Rectangle,
    ] {
        let player = player_box(q(10), q(10), q(4), kind);
        let edge = player.x.max_raw() as i32;
        let touch = RawAabb::from_raw_q16(edge, q(9), edge + Q, q(11));
        let inside = RawAabb::from_raw_q16(edge - 1, q(9), edge + Q, q(11));
        assert!(!touch.strictly_overlaps(player), "kind={kind:?}");
        assert!(inside.strictly_overlaps(player), "kind={kind:?}");
        assert_eq!(touch.signed_gaps(player).0, 0);
        assert_eq!(inside.signed_gaps(player).0, -1);
    }
}

#[test]
fn point_player_inside_touching_and_outside_rectangle() {
    let point = player_box(q(10), q(10), q(2), PlayerBoxKind::Rectangle);
    assert_eq!(point, box_px(10, 10, 10, 10));
    let inside = rectangle_box(q(9), q(9), q(3), q(3));
    assert!(inside.strictly_overlaps(point));
    assert_eq!(inside.signed_gaps(point), (-i64::from(Q), -i64::from(Q)));
    for rect in [
        rectangle_box(q(10), q(9), q(3), q(3)),
        rectangle_box(q(11), q(9), q(3), q(3)),
    ] {
        assert!(!rect.strictly_overlaps(point));
    }
}

#[test]
fn zero_explosion_collides_inside_nonzero_player_but_not_at_edge() {
    let player = player_box(q(8), q(8), q(2), PlayerBoxKind::EnemyFamily);
    assert!(enemy_box(q(8), q(8), 0).strictly_overlaps(player));
    assert!(!enemy_box(q(9), q(8), 0).strictly_overlaps(player));
    assert!(!enemy_box(q(10), q(8), 0).strictly_overlaps(player));
}

#[test]
fn half_raw_centers_and_signed_extents_remain_exact() {
    let tiny = RawAabb::from_raw_q16(0, -2, 1, -1).measures();
    assert_eq!(tiny.center_x_twice_raw, 1);
    assert_eq!(tiny.center_y_twice_raw, -3);
    assert_eq!(tiny.half_x_twice_raw, 1);
    assert_eq!(tiny.half_y_twice_raw, 1);
    assert_eq!(half_raw_to_pixels(1), 0.5 / f64::from(Q));
    assert_eq!(raw_to_pixels(-i64::from(Q)), -1.0);
    let inverted = RawInterval::from_raw_q16(4, 1);
    assert_eq!(inverted.center_twice_raw(), 5);
    assert_eq!(inverted.half_extent_twice_raw(), -3);
}

#[test]
fn rectangle_width_one_is_point_and_zero_is_inverted_literal() {
    let point = rectangle_box(q(10), q(20), q(1), q(1));
    assert_eq!(point, box_px(10, 20, 10, 20));
    let inverted = rectangle_box(q(10), q(20), 0, 0);
    assert_eq!(inverted, box_px(10, 20, 9, 19));
    assert!(inverted.x.is_inverted());
    // The native inequalities can still pass when the player contains both
    // inverted endpoints. Occupancy intentionally remains empty (tested below).
    let player = box_px(7, 17, 12, 22);
    assert!(inverted.strictly_overlaps(player));
    assert_eq!(
        inverted.signed_gaps(player),
        (-2 * i64::from(Q), -2 * i64::from(Q))
    );
    assert!(slab_contact(inverted, player, velocity(0.0, 0.0)).contact_within_horizon);
}

#[test]
fn native_endpoint_operations_wrap_before_widening() {
    assert_eq!(
        enemy_box(i32::MAX, i32::MIN, 1).x.max_raw(),
        i64::from(i32::MIN)
    );
    assert_eq!(
        rectangle_box(i32::MAX, 0, 1, 0).x.max_raw(),
        i64::from(i32::MIN.wrapping_sub(Q))
    );
    for (x, size) in [(i32::MAX, i32::MIN), (i32::MIN, i32::MAX), (0, i32::MIN)] {
        let enemy = player_box(x, x, size, PlayerBoxKind::EnemyFamily);
        assert_eq!(
            enemy.x.min_raw(),
            i64::from(x.wrapping_sub(size).wrapping_add(Q))
        );
        assert_eq!(
            enemy.x.max_raw(),
            i64::from(x.wrapping_add(size).wrapping_sub(Q))
        );
        let rect = player_box(x, x, size, PlayerBoxKind::Rectangle);
        assert_eq!(
            rect.x.min_raw(),
            i64::from(x.wrapping_add(2 * Q).wrapping_sub(size))
        );
        assert_eq!(
            rect.x.max_raw(),
            i64::from(x.wrapping_sub(2 * Q).wrapping_add(size))
        );
    }
}

#[test]
fn signed_gaps_use_widened_subtraction_at_native_extremes() {
    let low = RawInterval::from_raw_q16(i32::MIN, i32::MIN);
    let high = RawInterval::from_raw_q16(i32::MAX, i32::MAX);
    assert_eq!(low.signed_gap(high), 4_294_967_295);
    assert_eq!(high.signed_gap(low), 4_294_967_295);
    assert_eq!(
        RawInterval::from_raw_q16(i32::MIN, i32::MAX).half_extent_twice_raw(),
        4_294_967_295
    );
}

#[test]
fn slab_axis_parallel_hit_and_stationary_axis_miss() {
    let player = box_px(0, 0, 1, 1);
    let hit = slab_contact(box_px(3, 0, 4, 1), player, velocity(-1.0, 0.0));
    assert_eq!(hit.frames, 2.0);
    assert!(hit.contact_within_horizon);
    assert!(!hit.strict_overlap_now);
    let miss = slab_contact(box_px(3, 2, 4, 3), player, velocity(-1.0, 0.0));
    assert_eq!(miss.frames, 120.0);
    assert!(!miss.contact_within_horizon);
}

#[test]
fn slab_corner_contact_and_disjoint_time_windows() {
    let player = box_px(0, 0, 1, 1);
    let corner = slab_contact(box_px(3, 3, 4, 4), player, velocity(-1.0, -1.0));
    assert_eq!(corner.frames, 2.0);
    assert!(corner.contact_within_horizon);
    let tangent = slab_contact(box_px(3, 5, 4, 6), player, velocity(-1.0, -1.0));
    assert_eq!(tangent.frames, 4.0);
    assert!(tangent.contact_within_horizon);
    assert!(!slab_contact(box_px(3, 6, 4, 7), player, velocity(-1.0, -1.0)).contact_within_horizon);
}

#[test]
fn slab_contact_zero_is_distinct_from_strict_overlap() {
    let player = box_px(0, 0, 1, 1);
    let touching = slab_contact(box_px(1, 0, 2, 1), player, velocity(0.0, 0.0));
    assert_eq!(touching.frames, 0.0);
    assert!(touching.contact_within_horizon);
    assert!(!touching.strict_overlap_now);
    let overlap = slab_contact(player, player, velocity(0.0, 0.0));
    assert_eq!(overlap.frames, 0.0);
    assert!(overlap.strict_overlap_now);
    assert!(!slab_contact(box_px(3, 0, 4, 1), player, velocity(1.0, 0.0)).contact_within_horizon);
}

#[test]
fn slab_exact_horizon_and_beyond_are_distinguishable() {
    let player = box_px(0, 0, 1, 1);
    let at_horizon = slab_contact(box_px(121, 0, 122, 1), player, velocity(-1.0, 0.0));
    let beyond = slab_contact(box_px(122, 0, 123, 1), player, velocity(-1.0, 0.0));
    assert_eq!(at_horizon.frames, 120.0);
    assert!(at_horizon.contact_within_horizon);
    assert_eq!(beyond.frames, 120.0);
    assert!(!beyond.contact_within_horizon);
}

#[test]
fn slab_half_raw_velocity_and_nonfinite_policy() {
    let player = RawAabb::from_raw_q16(0, 0, 1, 1);
    let entity = RawAabb::from_raw_q16(3, 0, 4, 1);
    let contact = slab_contact(entity, player, RelativeVelocityRaw { x: -0.5, y: 0.0 });
    assert_eq!(contact.frames, 4.0);
    assert!(contact.contact_within_horizon);
    for value in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
        let invalid = slab_contact(player, player, RelativeVelocityRaw { x: value, y: 0.0 });
        assert_eq!(invalid.frames, 120.0);
        assert!(!invalid.contact_within_horizon);
        assert!(invalid.strict_overlap_now);
    }
}

#[test]
fn slab_point_players_and_points_preserve_closed_contact() {
    let point = box_px(1, 1, 1, 1);
    let outer = box_px(0, 0, 2, 2);
    assert!(slab_contact(outer, point, velocity(0.0, 0.0)).strict_overlap_now);
    let same_point = slab_contact(point, point, velocity(0.0, 0.0));
    assert!(same_point.contact_within_horizon);
    assert!(!same_point.strict_overlap_now);
    let inverted = box_px(2, 2, 1, 1);
    assert!(!slab_contact(inverted, point, velocity(-1.0, -1.0)).contact_within_horizon);
}

#[test]
fn visual_floor_differs_from_truncation_for_negative_coordinates() {
    assert_eq!(floor_raw_q16(-1), -1);
    assert_eq!(floor_raw_q16(-Q - 1), -2);
    let footprint = enemy_footprint(-1, -1, 0);
    assert_eq!(
        footprint,
        PixelFootprint {
            min_x: -1,
            min_y: -1,
            max_x: -1,
            max_y: 0
        }
    );
    assert!(!footprint.intersects_world());
    assert!(enemy_footprint(0, -1, 0).intersects_world());
}

#[test]
fn negative_explosion_collision_is_inverted_but_visual_size_is_clamped() {
    let collision = enemy_box(0, 0, -q(2));
    assert_eq!(collision, box_px(0, 0, -2, -2));
    assert_eq!(
        enemy_footprint(0, 0, -q(2)),
        PixelFootprint {
            min_x: 0,
            min_y: 0,
            max_x: 0,
            max_y: 1
        }
    );
    assert!(!enemy_footprint(q(129), 0, -q(5)).intersects_world());
    assert!(enemy_footprint(0, 0, 0).intersects_world());
}

#[test]
fn native_round_handles_negative_half_ties_and_top_edge_wrap() {
    for (raw, expected) in [
        (-3 * Q / 2, -1),
        (-Q / 2, 0),
        (-Q / 2 - 1, -1),
        (Q / 2, 1),
        (Q / 2 - 1, 0),
        (i32::MAX, -32768),
    ] {
        assert_eq!(round_raw_q16(raw), expected, "raw={raw}");
    }
}

#[test]
fn rectangle_visual_normalization_does_not_change_collision() {
    assert_eq!(
        rectangle_footprint(-Q / 2, -3 * Q / 2, -3 * Q / 2, q(2)),
        PixelFootprint {
            min_x: -1,
            min_y: -1,
            max_x: 0,
            max_y: 2
        }
    );
    let collision = rectangle_box(0, 0, -q(2), q(1));
    assert_eq!(collision.x.min_raw(), 0);
    assert_eq!(collision.x.max_raw(), -3 * i64::from(Q));
    assert!(rectangle_footprint(0, 0, -q(2), q(1)).intersects_world());
}

#[test]
fn admission_keeps_partly_offscreen_unclipped_geometry() {
    let bounds = enemy_box(q(-2), q(126), q(4));
    let original = bounds;
    assert!(enemy_footprint(q(-2), q(126), q(4)).intersects_world());
    assert_eq!(bounds, original);
    assert_eq!(bounds.x.min_raw(), -2 * i64::from(Q));
    assert_eq!(bounds.y.max_raw(), 130 * i64::from(Q));
    assert!(!enemy_footprint(q(-2), 0, 0).intersects_world());
    assert!(enemy_footprint(q(127), 0, 0).intersects_world());
    assert!(!enemy_footprint(q(128), 0, 0).intersects_world());
}

#[test]
fn powerup_admission_includes_body_and_shadow_envelope() {
    assert_eq!(
        powerup_footprint(-1, 0),
        PixelFootprint {
            min_x: -5,
            min_y: -4,
            max_x: 3,
            max_y: 5
        }
    );
    assert!(powerup_footprint(q(-4), q(20)).intersects_world());
    assert!(!powerup_footprint(q(-5), q(20)).intersects_world());
    assert!(powerup_footprint(q(20), q(-5)).intersects_world());
    assert!(!powerup_footprint(q(20), q(-6)).intersects_world());
}

#[test]
fn offscreen_control_is_excluded_by_footprint_without_catalog_input() {
    assert!(!rectangle_footprint(q(-50), q(-50), 0, 0).intersects_world());
    assert!(rectangle_footprint(0, 0, 0, 0).intersects_world());
}

#[test]
fn warning_admission_checks_rounded_main_and_shadow() -> Result<(), SegmentError> {
    let shadow_only = WarningSegment::from_raw_q16(0, -Q, q(8), -Q)?;
    assert!(!shadow_only.main_footprint().intersects_world());
    assert!(shadow_only.shadow_footprint().intersects_world());
    assert!(shadow_only.intersects_world());
    assert!(!WarningSegment::from_raw_q16(-Q, 0, -Q, q(127))?.intersects_world());
    assert!(WarningSegment::from_raw_q16(-Q / 2, 0, -Q / 2, q(127))?.intersects_world());
    Ok(())
}

#[test]
fn warning_rejects_diagonal_instead_of_filling_enclosing_box() {
    assert_eq!(
        WarningSegment::from_raw_q16(q(-2), 0, 0, q(-2)),
        Err(SegmentError::NonAxisAligned)
    );
}

#[test]
fn cell_floor_and_ceil_are_signed_and_exact_at_extremes() {
    for (raw, floor, ceil) in [
        (-CELL_RAW - 1, -2, -1),
        (-CELL_RAW, -1, -1),
        (-1, -1, 0),
        (0, 0, 0),
        (1, 0, 1),
        (CELL_RAW - 1, 0, 1),
        (CELL_RAW, 1, 1),
    ] {
        assert_eq!(floor_cell(raw), floor);
        assert_eq!(ceil_cell(raw), ceil);
    }
    assert_eq!(ceil_cell(i64::MIN), i64::MIN >> 19);
    assert_eq!(ceil_cell(i64::MAX), (i64::MAX >> 19) + 1);
}

#[test]
fn positive_intervals_are_half_open_and_points_choose_floor_cell() {
    let span = interval_patches(RawInterval::from_raw_q16(0, q(8)));
    assert_eq!(span, Some(raster::PatchSpan { first: 0, last: 0 }));
    assert_eq!(
        interval_patches(RawInterval::from_raw_q16(q(8), q(8))),
        Some(raster::PatchSpan { first: 1, last: 1 })
    );
    assert_eq!(interval_patches(RawInterval::from_raw_q16(-q(8), 0)), None);
    assert_eq!(
        interval_patches(RawInterval::from_raw_q16(-1, 1)),
        Some(raster::PatchSpan { first: 0, last: 0 })
    );
    assert_eq!(interval_patches(RawInterval::from_raw_q16(-1, -1)), None);
    assert_eq!(
        interval_patches(RawInterval::from_raw_q16(q(128), q(128))),
        None
    );
}

#[test]
fn zero_explosion_at_exact_patch_boundary_remains_one_patch() {
    let mut raster = AuxRaster::default();
    raster.paint_box(enemy_box(q(8), q(8), 0), enemy_flags());
    assert_eq!(occupied(&raster, Channel::Enemy), vec![(1, 1)]);
    assert_eq!(occupied(&raster, Channel::LethalNow), vec![(1, 1)]);
    assert!(occupied(&raster, Channel::LethalSoon).is_empty());
}

#[test]
fn negative_boundary_points_and_partly_offscreen_boxes_follow_patch_rule() {
    let mut raster = AuxRaster::default();
    raster.paint_box(RawAabb::from_raw_q16(-1, q(8), 0, q(8)), enemy_flags());
    assert!(occupied(&raster, Channel::Enemy).is_empty());
    raster.paint_box(RawAabb::from_raw_q16(-1, q(8), 1, q(8)), enemy_flags());
    assert_eq!(occupied(&raster, Channel::Enemy), vec![(0, 1)]);
    let partly_offscreen = box_px(-4, 120, 132, 132);
    raster.paint_box(partly_offscreen, enemy_flags());
    assert_eq!(partly_offscreen, box_px(-4, 120, 132, 132));
    assert_eq!(occupied(&raster, Channel::Enemy).len(), 17);
}

#[test]
fn full_width_wall_fills_all_sixteen_columns_even_with_point_height() {
    let mut raster = AuxRaster::default();
    raster.paint_box(rectangle_box(0, q(8), q(128), q(1)), enemy_flags());
    assert_eq!(
        occupied(&raster, Channel::LethalNow),
        (0..16).map(|x| (x, 1)).collect::<Vec<_>>()
    );
}

#[test]
fn inverted_boxes_cover_nothing_and_count_axes_without_normalizing() {
    let mut raster = AuxRaster::default();
    raster.paint_box(rectangle_box(q(8), q(8), 0, q(1)), enemy_flags());
    raster.paint_box(enemy_box(q(8), q(8), -1), enemy_flags());
    assert!(occupied(&raster, Channel::Enemy).is_empty());
    assert_eq!(
        raster.diagnostics(),
        raster::RasterDiagnostics {
            inverted_boxes: 2,
            inverted_axes: 3
        }
    );
    raster.paint_box(rectangle_box(q(8), q(8), q(1), q(1)), enemy_flags());
    assert_eq!(occupied(&raster, Channel::Enemy), vec![(1, 1)]);
    assert_eq!(raster.diagnostics().inverted_boxes, 2);
}

#[test]
fn warning_inclusive_endpoint_and_shadow_cross_patch_boundary() -> Result<(), SegmentError> {
    let mut raster = AuxRaster::default();
    raster.paint_warning(
        WarningSegment::from_raw_q16(0, q(7), q(8), q(7))?,
        warning_flags(),
    );
    assert_eq!(
        occupied(&raster, Channel::LethalSoon),
        vec![(0, 0), (1, 0), (0, 1), (1, 1)]
    );
    assert!(occupied(&raster, Channel::LethalNow).is_empty());
    assert!(occupied(&raster, Channel::Enemy).is_empty());
    Ok(())
}

#[test]
fn warning_vertical_and_reversed_segments_keep_exact_pixel_cells() -> Result<(), SegmentError> {
    let mut raster = AuxRaster::default();
    raster.paint_warning(
        WarningSegment::from_raw_q16(q(8), q(127), q(8), 0)?,
        warning_flags(),
    );
    assert_eq!(
        occupied(&raster, Channel::LethalSoon),
        (0..16).map(|y| (1, y)).collect::<Vec<_>>()
    );
    Ok(())
}

#[test]
fn warning_negative_boundary_shadow_and_point_rules_are_inclusive() -> Result<(), SegmentError> {
    let mut raster = AuxRaster::default();
    raster.paint_warning(
        WarningSegment::from_raw_q16(-q(8), -Q, 0, -Q)?,
        warning_flags(),
    );
    assert_eq!(occupied(&raster, Channel::LethalSoon), vec![(0, 0)]);
    raster.paint_warning(
        WarningSegment::from_raw_q16(q(8), q(8), q(8), q(8))?,
        warning_flags(),
    );
    assert_eq!(occupied(&raster, Channel::LethalSoon), vec![(0, 0), (1, 1)]);
    Ok(())
}

#[test]
fn player_channel_uses_widest_powerup_box() {
    let mut raster = AuxRaster::default();
    raster.paint_box(
        player_box(q(4), q(4), q(4), PlayerBoxKind::Powerup),
        RasterFlags {
            player: true,
            ..RasterFlags::default()
        },
    );
    assert_eq!(occupied(&raster, Channel::Player), vec![(0, 0)]);
    let point = player_box(q(8), q(8), q(2), PlayerBoxKind::Rectangle);
    assert_eq!(point, box_px(8, 8, 8, 8));
    assert_eq!(
        player_box(q(8), q(8), q(2), PlayerBoxKind::Powerup),
        box_px(6, 6, 10, 10)
    );
}

#[test]
fn overlapping_channels_are_independent_binary_unions() {
    let mut raster = AuxRaster::default();
    let bounds = enemy_box(q(8), q(8), 0);
    raster.paint_box(bounds, enemy_flags());
    raster.paint_box(
        bounds,
        RasterFlags {
            powerup: true,
            player: true,
            ..RasterFlags::default()
        },
    );
    assert!(occupied(&raster, Channel::LethalSoon).is_empty());
    raster.paint_box(bounds, warning_flags());
    raster.paint_box(bounds, enemy_flags());
    for channel in [
        Channel::LethalNow,
        Channel::LethalSoon,
        Channel::Enemy,
        Channel::Powerup,
        Channel::Player,
    ] {
        assert_eq!(occupied(&raster, channel), vec![(1, 1)]);
    }
    assert!(
        raster
            .channels()
            .iter()
            .flatten()
            .flatten()
            .all(|value| *value == 0.0 || *value == 1.0)
    );
    assert_eq!(raster.clone().into_channels(), *raster.channels());
}

#[test]
fn geometric_overlap_alone_does_not_assign_hazard_labels() {
    let mut raster = AuxRaster::default();
    let bounds = box_px(0, 0, 8, 8);
    raster.paint_box(
        bounds,
        RasterFlags {
            enemy: true,
            ..RasterFlags::default()
        },
    );
    raster.paint_box(
        bounds,
        RasterFlags {
            player: true,
            ..RasterFlags::default()
        },
    );
    assert_eq!(occupied(&raster, Channel::Enemy), vec![(0, 0)]);
    assert_eq!(occupied(&raster, Channel::Player), vec![(0, 0)]);
    assert!(occupied(&raster, Channel::LethalNow).is_empty());
    assert!(occupied(&raster, Channel::LethalSoon).is_empty());
}
