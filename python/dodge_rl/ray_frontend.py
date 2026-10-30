"""Batched CPU float64 R0 geometry; transfer only 46 scalars with neural inputs.

CPU source arrays stay on CPU until this deterministic derivation finishes.
This avoids device-to-host copies and preserves literal decoded geometry on
MPS, which does not support float64. The learned branch runs with the teacher.
"""

import math

import torch

from .clearance_rays import DIRECTIONS, HORIZON_PIXELS
from .models.teacher import OmniscientEntityTeacher


@torch.no_grad()
def batched_clearance_rays(global_feats, entity_feats, entity_types, entity_mask):
    OmniscientEntityTeacher._validate_inputs(global_feats, entity_feats, entity_types, entity_mask)
    if global_feats.device.type != "cpu":
        raise ValueError("R0 geometry requires original CPU arrays, not device roundtrips")
    e = entity_feats.masked_fill(~entity_mask.unsqueeze(-1), 0).double()
    kinds = entity_types.masked_fill(~entity_mask, 0)
    g = global_feats[:, 0].double()
    if not bool(torch.isfinite(g).all() and torch.isfinite(e).all()):
        raise ValueError("Valid input scalars must be finite")
    if bool((entity_mask & ((kinds < 1) | (kinds > 8))).any()):
        raise ValueError("Valid entity types must be in 1..8")
    if bool((entity_mask & (e[:, :, 15] != 0) & (e[:, :, 15] != 1)).any()):
        raise ValueError("lethal_now must be binary")
    p, size = 64 + 64*g[:, :2], 4*g[:, 4]
    if bool(((p < 2) | (p > 125)).any() or ((size < 2) | (size > 4)).any()):
        raise ValueError("Player center/size outside admitted physics range")
    rect = entity_mask & ((kinds == 7) | (kinds == 8))
    enemies = entity_mask & ~rect
    counts_e, counts_b = enemies.sum(1), rect.sum(1)
    if bool((counts_e > 64).any() or (counts_b > 16).any()):
        raise ValueError("Represented family counts exceed admitted caps")
    hazard = entity_mask & ~((kinds >= 4) & (kinds <= 6))
    lethal = hazard & (e[:, :, 15] == 1)
    center, half = 64 + 128*e[:, :, :2], 64*e[:, :, 2:4]
    radius = size[:, None] - torch.where(rect, 2., 1.)
    low, high = center-half-radius[:, :, None], center+half+radius[:, :, None]
    d = torch.tensor(DIRECTIONS, dtype=torch.float64)
    denominator = torch.where(d == 0, 1., d)
    wall_axis = (torch.where(d > 0, 125., 2.)[None] - p[:, None]) / denominator
    walls = wall_axis.masked_fill(d[None] == 0, math.inf).amin(-1)
    lo = (low[:, :, None] - p[:, None, None]) / denominator[None, None]
    hi = (high[:, :, None] - p[:, None, None]) / denominator[None, None]
    inside = (low < p[:, None]) & (p[:, None] < high)
    zero_ok = ((d[None, None] != 0) | inside[:, :, None]).all(-1)
    nonempty = (low < high).all(-1)[:, :, None]
    entry = torch.minimum(lo, hi).masked_fill(d[None, None] == 0, -math.inf).amax(-1)
    leave = torch.maximum(lo, hi).masked_fill(d[None, None] == 0, math.inf).amin(-1)
    first = entry.clamp_min(0)
    last = torch.minimum(leave, walls[:, None])
    overlap = inside.all(-1)
    hits = nonempty & zero_ok & ((first < last) | ((walls[:, None] == 0) & overlap[:, :, None]))
    overlap_l = (overlap & lethal).any(1)
    overlap_b = (overlap & rect).any(1)
    distances, hit_masks = [], []
    for eligible in (lethal, rect):
        distance = first.masked_fill(~(hits & eligible[:, :, None]), math.inf).amin(1)
        hit = torch.isfinite(distance)
        distances.append(torch.where(hit, distance/HORIZON_PIXELS, 1.))
        hit_masks.append(hit.double())
    extras = torch.stack((overlap_l, overlap_b, counts_e/64, counts_b/16,
                          counts_e == 64, (hazard & (half < 0).any(-1)).any(1)), 1)
    return torch.cat((walls/HORIZON_PIXELS, *distances, *hit_masks, extras), 1).float()
