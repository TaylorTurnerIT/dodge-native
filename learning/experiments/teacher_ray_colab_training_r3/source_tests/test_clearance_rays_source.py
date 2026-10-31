"""Synthetic admitted-array fixtures; no native engine or game-seed cohort."""

import copy
from fractions import Fraction
import inspect
import math
import random
import struct

import pytest

from dodge_rl.clearance_rays import (
    DIRECTIONS, FEATURE_NAMES, HORIZON_PIXELS, clearance_ray_features,
)


def scene(p=(64, 64), size=4, boxes=()):
    g = [0.0] * 14
    g[0], g[1], g[4] = (p[0] - 64) / 64, (p[1] - 64) / 64, size / 4
    g[10:14] = [(p[0] - 2) / 123, (125 - p[0]) / 123,
                (p[1] - 2) / 123, (125 - p[1]) / 123]
    rows, types, mask = [[0.0] * 16 for _ in range(80)], [0] * 80, [False] * 80
    for i, (kind, x0, y0, x1, y1, lethal) in enumerate(boxes):
        rows[i][0:4] = [((x0 + x1) / 2 - 64) / 128,
                        ((y0 + y1) / 2 - 64) / 128,
                        (x1 - x0) / 128, (y1 - y0) / 128]
        rows[i][14:16] = [float(kind in (4, 5, 6)), float(lethal)]
        types[i], mask[i] = kind, True
    return [[[g]], [rows], [types], [mask]]


def features(data):
    return clearance_ray_features(*data)[0]


@pytest.mark.parametrize("p", [(2, 2), (125, 125), (2, 125), (125, 2), (63.5, 63.5)])
def test_empty_scene_clamp_faces_corners_and_size_independence(p):
    f = features(scene(p))
    assert len(f) == len(FEATURE_NAMES) == 46
    assert f == features(scene(p, size=2))
    expected = [125-p[0], min(125-p[0], 125-p[1])*math.sqrt(2),
                125-p[1], min(p[0]-2, 125-p[1])*math.sqrt(2), p[0]-2,
                min(p[0]-2, p[1]-2)*math.sqrt(2), p[1]-2,
                min(125-p[0], p[1]-2)*math.sqrt(2)]
    assert f[:8] == pytest.approx([v/HORIZON_PIXELS for v in expected])
    assert f[8:24] == (1.0,) * 16
    assert f[24:] == (0.0,) * 22


@pytest.mark.parametrize("kind,size,expected", [(1, 4, 3), (7, 4, 4), (7, 2, 6)])
def test_family_specific_player_clearance(kind, size, expected):
    f = features(scene(size=size, boxes=[(kind, 70, 60, 75, 68, True)]))
    assert f[8] * HORIZON_PIXELS == pytest.approx(expected)
    assert f[24] == 1
    assert f[32] == float(kind == 7)


def test_touch_entry_exit_tangent_and_point_player():
    touching = features(scene(boxes=[(1, 67, 60, 70, 68, True)]))
    assert touching[8] == 0 and touching[24] == 1 and touching[40] == 0
    assert touching[28] == 0  # Moving west leaves a touching box.
    # SE hits only the common boundary of x-entry and y-exit: no strict interior.
    tangent = features(scene(boxes=[(7, 70, 60, 74, 66, True)]))
    assert tangent[25] == 0
    point = features(scene(size=2, boxes=[(7, 64, 60, 64, 68, True)]))
    assert point[24:40] == (0.0,) * 16
    point_hazard = features(scene(boxes=[(7, 64, 64, 64, 64, True)]))
    assert point_hazard[24:40] == (1.0,) * 16
    assert point_hazard[40:42] == (1.0, 1.0)


def test_literal_inverted_boxes_can_collide_without_sorting():
    wide = features(scene(boxes=[(7, 65, 60, 63, 68, True)]))
    assert wide[40:42] == (1, 1) and wide[45] == 1
    narrow = features(scene(size=2, boxes=[(7, 65, 60, 63, 68, True)]))
    assert narrow[24:40] == (0.0,) * 16 and narrow[45] == 1
    empty = features(scene(boxes=[(7, 66, 60, 62, 68, True)]))
    assert empty[24:40] == (0.0,) * 16  # Equal expanded bounds stay strictly empty.


def test_zero_wall_domain_overlap_and_no_off_arena_ray():
    f = features(scene(p=(125, 64), boxes=[(1, 124, 62, 126, 66, True)]))
    assert f[0] == f[8] == 0 and f[24] == f[40] == 1
    # Literal offscreen bounds can overlap the player, but a distant box beyond
    # the clamp cannot certify a hit along a center translation that stops there.
    far = features(scene(boxes=[(1, 129, 60, 131, 68, True)]))
    assert far[24] == 0
    partial = features(scene(p=(2, 64), boxes=[(1, -2, 62, 0, 66, True)]))
    assert partial[40] == 1


def test_beneficial_rows_and_benign_rectangle_channel():
    pickups = features(scene(boxes=[(4, 63, 63, 65, 65, False)]))
    assert pickups[24:42] == (0.0,) * 18 and pickups[42] == 1/64
    benign = features(scene(boxes=[(7, 70, 60, 75, 68, False)]))
    assert benign[24] == 0 and benign[32] == 1
    assert benign[16] * HORIZON_PIXELS == pytest.approx(4)


def test_padding_permutation_no_mutation_and_no_metadata_parameter():
    data = scene(boxes=[(1, 70, 60, 75, 68, True), (7, 60, 70, 68, 75, False)])
    original = copy.deepcopy(data)
    expected = features(data)
    assert data == original
    data[1][0][79] = [float("nan")] * 16
    data[2][0][79] = 999
    assert features(data) == expected
    data[1][0][79] = [float("inf")] * 16
    assert features(data) == expected
    for array in data[1:]:
        array[0].reverse()
    assert features(data) == expected
    assert tuple(inspect.signature(clearance_ray_features).parameters) == (
        "global_feats", "entity_feats", "entity_types", "entity_mask",
    )
    with pytest.raises(TypeError):
        clearance_ray_features(*data, diagnostics={"hidden_valid": True})


def test_static_output_ignores_measured_motion_and_charge_estimate():
    data = scene(boxes=[(7, 70, 60, 75, 68, False)])
    before = features(data)
    data[1][0][0][6:14] = [0.25, -0.5, 0.1, -0.1, 0, 0, 0.2, 0.05]
    data[0][0][0][2:4] = [0.4, -0.2]
    assert features(data) == before


def test_float32_boundary_neighbors_remain_decoded_geometry_not_native_claim():
    data = scene(boxes=[(1, 67, 60, 70, 68, True)])
    center = data[1][0][0][0]
    bits = struct.unpack("I", struct.pack("f", center))[0]
    lower = copy.deepcopy(data)
    upper = copy.deepcopy(data)
    lower[1][0][0][0] = struct.unpack("f", struct.pack("I", bits-1))[0]
    upper[1][0][0][0] = struct.unpack("f", struct.pack("I", bits+1))[0]
    assert features(data)[40] == 0  # Exact decoded touch, not strict overlap.
    assert features(lower)[40] == 1
    assert features(upper)[40] == 0 and features(upper)[8] > 0
    assert features(upper)[8] * HORIZON_PIXELS < 1/65536
    # Distinct decoded cases can be less than one native Q16.16 unit apart.


def test_empty_and_mismatched_batches_rejected():
    with pytest.raises(ValueError, match="batch"):
        clearance_ray_features([], [], [], [])
    data = scene()
    data[3].append(data[3][0][:])
    with pytest.raises(ValueError, match="batch"):
        clearance_ray_features(*data)


def test_saturation_means_count_not_hidden_overflow():
    data = scene(boxes=[(4, 60, 60, 68, 68, False)] * 64)
    assert features(data)[42:45] == (1.0, 0.0, 1.0)
    data[1][0][64] = data[1][0][0][:]
    data[2][0][64], data[3][0][64] = 4, True
    with pytest.raises(ValueError, match="caps"):
        features(data)


@pytest.mark.parametrize("change", ["nan", "type", "flag", "mask", "player", "shape"])
def test_invalid_valid_rows_and_layout_fail_closed(change):
    data = scene(boxes=[(1, 70, 60, 75, 68, True)])
    if change == "nan":
        data[1][0][0][7] = float("nan")
    elif change == "type":
        data[2][0][0] = 9
    elif change == "flag":
        data[1][0][0][15] = 0.3
    elif change == "mask":
        data[3][0][0] = 1
    elif change == "player":
        data[0][0][0][0] = -1.0
    else:
        data[1][0].pop()
    with pytest.raises(ValueError):
        features(data)


def literal_event_oracle(p, size, boxes, direction, rectangle_only=False):
    """Rational event sweep tests original four strict collision inequalities.

    Directions use unnormalized integer axes, so all event positions and strict
    tests are exact fractions. This avoids reproducing production slab math or
    importing the native engine as an oracle.
    """
    dx, dy = direction
    end = min(Fraction((125 if delta > 0 else 2) - p[a], delta)
              for a, delta in enumerate(direction) if delta)
    events = {Fraction(0), end}
    eligible = [b for b in boxes if (b[0] in (7, 8) if rectangle_only
                                   else b[0] in (1, 2, 3, 7, 8) and b[5])]
    for kind, x0, y0, x1, y1, _ in eligible:
        r = size - (2 if kind in (7, 8) else 1)
        for a, (low, high, delta) in enumerate(((x0, x1, dx), (y0, y1, dy))):
            if delta:
                for endpoint in (low - r, high + r):
                    event = Fraction(endpoint - p[a]) / delta
                    if 0 <= event <= end:
                        events.add(event)

    def collision(t):
        x, y = p[0] + dx*t, p[1] + dy*t
        for kind, x0, y0, x1, y1, _ in eligible:
            r = size - (2 if kind in (7, 8) else 1)
            if x+r > x0 and x-r < x1 and y+r > y0 and y-r < y1:
                return True
        return False

    if collision(Fraction(0)):
        return 0.0
    events = sorted(events)
    for left, right in zip(events, events[1:]):
        if collision((left+right)/2):
            return float(left) * math.hypot(dx, dy)
    return None


def test_randomized_rational_event_oracle_and_batch_isolation():
    rng = random.Random(1729)  # Synthetic fixture RNG, never game seeds.
    directions = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    scenes, expected = [], []
    for _ in range(50):
        p = (rng.choice([2, 20, 64, 125]), rng.choice([2, 35, 64, 125]))
        size = rng.choice([2, Fraction(5, 2), 4])
        boxes = []
        for kind in (1, 3, 4, 7, 8):
            x, y = rng.randrange(-8, 135), rng.randrange(-8, 135)
            boxes.append((kind, x, y, x+rng.randrange(-5, 20),
                          y+rng.randrange(-5, 20), kind != 4 and rng.choice([True, False])))
        data = scene(p, size, boxes)
        scenes.append(data)
        f = features(data)
        expected.append(f)
        for i, d in enumerate(directions):
            for group, only_rect in ((0, False), (1, True)):
                hit = literal_event_oracle(p, size, boxes, d, only_rect)
                assert f[24+group*8+i] == float(hit is not None)
                assert f[8+group*8+i] == pytest.approx(1 if hit is None else hit/HORIZON_PIXELS)
    batched = [[data[a][0] for data in scenes] for a in range(4)]
    assert clearance_ray_features(*batched) == tuple(expected)


@pytest.mark.parametrize("transform", ["reflect", "rotate"])
def test_derived_geometry_d4_uses_axis_63_5(transform):
    p, size = (23, 91), 4
    boxes = [(1, 29, 80, 35, 96, True), (7, 17, 93, 34, 98, False),
             (8, 90, 70, 88, 76, True)]
    before = features(scene(p, size, boxes))
    if transform == "reflect":
        next_p = (127-p[0], p[1])
        next_boxes = [(k, 127-x1, y0, 127-x0, y1, lethal)
                      for k, x0, y0, x1, y1, lethal in boxes]
        permutation = [4, 3, 2, 1, 0, 7, 6, 5]
    else:
        next_p = (127-p[1], p[0])
        next_boxes = [(k, 127-y1, x0, 127-y0, x1, lethal)
                      for k, x0, y0, x1, y1, lethal in boxes]
        permutation = [6, 7, 0, 1, 2, 3, 4, 5]
    after = features(scene(next_p, size, next_boxes))
    for group in range(5):
        assert after[group*8:(group+1)*8] == pytest.approx(
            [before[group*8+i] for i in permutation])
    assert after[40:] == before[40:]
