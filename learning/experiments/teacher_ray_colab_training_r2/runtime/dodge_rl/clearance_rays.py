"""Stateless R0 reference geometry from the four admitted arrays only.

This stdlib CPU implementation is not a qualified rollout frontend. Distances
describe the represented static scene, never certified free space or a future
trajectory. No history, engine access, metadata, or auxiliary raster is read.
"""

from __future__ import annotations

import math
from numbers import Real
from collections.abc import Sequence

from .player_geometry import validate_player


RAY_SCHEMA = "admitted_static_clearance_r0_v2_reachable_player_size"
HORIZON_PIXELS = 123.0 * math.sqrt(2.0)
_DIAGONAL = 1.0 / math.sqrt(2.0)
DIRECTIONS = (
    (1.0, 0.0), (_DIAGONAL, _DIAGONAL), (0.0, 1.0),
    (-_DIAGONAL, _DIAGONAL), (-1.0, 0.0),
    (-_DIAGONAL, -_DIAGONAL), (0.0, -1.0), (_DIAGONAL, -_DIAGONAL),
)
FEATURE_NAMES = tuple(
    f"{group}_{direction}"
    for group in ("wall", "lethal", "rectangle", "hit_lethal", "hit_rectangle")
    for direction in ("E", "SE", "S", "SW", "W", "NW", "N", "NE")
) + (
    "overlap_lethal", "overlap_rectangle", "enemy_count_fraction",
    "rectangle_count_fraction", "enemy_saturated", "inverted_hazard",
)
RAY_FEATURE_DIM = len(FEATURE_NAMES)


def _finite_row(row: Sequence[Real], length: int, name: str) -> tuple[float, ...]:
    if len(row) != length:
        raise ValueError(f"{name} must have length {length}")
    if any(isinstance(value, bool) or not isinstance(value, Real)
           or not math.isfinite(value) for value in row):
        raise ValueError(f"{name} must contain finite real scalars")
    return tuple(float(value) for value in row)


def _overlaps(p, low, high):
    return all(low[a] < p[a] < high[a] for a in (0, 1))


def _first_hit(p, d, low, high, wall):
    """Infimum of strict collision translations on closed domain [0, wall]."""
    enter, leave = -math.inf, math.inf
    for a in (0, 1):
        if low[a] >= high[a]:
            return None
        if d[a] == 0:
            if not low[a] < p[a] < high[a]:
                return None
        else:
            first = (low[a] - p[a]) / d[a]
            second = (high[a] - p[a]) / d[a]
            enter = max(enter, min(first, second))
            leave = min(leave, max(first, second))
    first, last = max(0.0, enter), min(wall, leave)
    if first < last:
        return first
    # Only a zero-length *domain* can leave a singleton strict collision.
    # Never round a tangent back into the open interval by recomputing it.
    if wall == 0.0 and _overlaps(p, low, high):
        return 0.0
    return None


def clearance_ray_features(
    global_feats: Sequence[Sequence[Sequence[Real]]],
    entity_feats: Sequence[Sequence[Sequence[Real]]],
    entity_types: Sequence[Sequence[int]],
    entity_mask: Sequence[Sequence[bool]],
) -> tuple[tuple[float, ...], ...]:
    """Return B×46 R0 scalars, accepting only four batched array-like values.

    Callers using tensors must enforce float32/int64/bool and CPU layout. This
    pure reference validates shape, valid-row finiteness/types and player range.
    Masked row contents and IDs are never inspected, including bad sentinels.
    Counts follow types, not row identities, so permutations are harmless.
    """
    batch = len(global_feats)
    if not batch or any(len(array) != batch for array in
                        (entity_feats, entity_types, entity_mask)):
        raise ValueError("Four arrays must share a nonempty batch")
    output = []
    for batch_row, (globals_row, rows, types, mask) in enumerate(zip(
        global_feats, entity_feats, entity_types, entity_mask, strict=True
    )):
        if len(globals_row) != 1:
            raise ValueError("global_feats must have shape [B,1,14]")
        raw_g=globals_row[0]
        if len(raw_g)==14 and all(isinstance(raw_g[i],Real) and not isinstance(raw_g[i],bool) for i in (0,1,4)):
            validate_player(batch_row,64+64*float(raw_g[0]),64+64*float(raw_g[1]),4*float(raw_g[4]))
        g = _finite_row(raw_g, 14, "global_feats")
        if len(rows) != 80 or len(types) != 80 or len(mask) != 80:
            raise ValueError("Entity arrays must have 80 rows")
        if any(type(valid) is not bool for valid in mask):
            raise ValueError("entity_mask must contain booleans")
        p = (64.0 + 64.0 * g[0], 64.0 + 64.0 * g[1])
        size = 4.0 * g[4]
        validate_player(batch_row,*p,size)
        walls = tuple(min(
            ((125.0 if delta > 0 else 2.0) - p[a]) / delta
            for a, delta in enumerate(d) if delta != 0
        ) for d in DIRECTIONS)
        lethal, rectangles = [None] * 8, [None] * 8
        overlap_l = overlap_b = inverted = False
        enemy_count = rect_count = 0
        for row, kind, valid in zip(rows, types, mask, strict=True):
            if not valid:
                continue
            e = _finite_row(row, 16, "valid entity_feats")
            if type(kind) is not int or not 1 <= kind <= 8:
                raise ValueError("Valid entity type must be an integer in 1..8")
            if e[15] not in (0.0, 1.0):
                raise ValueError("lethal_now must be binary")
            rectangle = kind in (7, 8)
            enemy_count += not rectangle
            rect_count += rectangle
            if kind in (4, 5, 6):
                continue
            radius = size - (2.0 if rectangle else 1.0)
            center = (64.0 + 128.0 * e[0], 64.0 + 128.0 * e[1])
            half = (64.0 * e[2], 64.0 * e[3])
            low = tuple(center[a] - half[a] - radius for a in (0, 1))
            high = tuple(center[a] + half[a] + radius for a in (0, 1))
            if not all(math.isfinite(v) for v in (*low, *high)):
                raise ValueError("Decoded geometry must remain finite")
            inverted |= any(value < 0 for value in half)
            is_lethal = e[15] == 1.0
            overlap = _overlaps(p, low, high)
            overlap_l |= is_lethal and overlap
            overlap_b |= rectangle and overlap
            if not (is_lethal or rectangle):
                continue
            for i, (d, wall) in enumerate(zip(DIRECTIONS, walls, strict=True)):
                hit = _first_hit(p, d, low, high, wall)
                if hit is not None:
                    if is_lethal and (lethal[i] is None or hit < lethal[i]):
                        lethal[i] = hit
                    if rectangle and (rectangles[i] is None or hit < rectangles[i]):
                        rectangles[i] = hit
        if enemy_count > 64 or rect_count > 16:
            raise ValueError("Represented family counts exceed admitted caps")
        features = [v / HORIZON_PIXELS for v in walls]
        for hits in (lethal, rectangles):
            features.extend(1.0 if hit is None else hit / HORIZON_PIXELS for hit in hits)
        for hits in (lethal, rectangles):
            features.extend(float(hit is not None) for hit in hits)
        features.extend((float(overlap_l), float(overlap_b), enemy_count / 64.0,
                         rect_count / 16.0, float(enemy_count == 64), float(inverted)))
        output.append(tuple(features))
    return tuple(output)
