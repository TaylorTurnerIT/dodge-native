"""Prospective survival-only gates; frozen v2 runners keep their original policy.

Callers must validate episode rows, seeds and summary arithmetic before passing
summaries here. These predicates do not grant experiment or checkpoint acceptance.
"""
from __future__ import annotations

import math


POLICY_VERSION = "teacher_qualification_v3_survival_only"


def _alive(evaluations: dict, stage: str) -> float:
    result = evaluations[stage]
    if (result.get("complete") is not True or result.get("stage") != stage
            or result.get("episodes") != 64):
        raise ValueError("A complete validated 64-episode development summary is required")
    value = result["mean_alive_frames"]
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Mean alive frames must be finite and nonnegative")
    return value


def progress_passed(phase: str, evaluations: dict) -> bool:
    """Apply v3 development thresholds, with no score pass/fail condition."""
    if phase == "D1":
        return _alive(evaluations, "D1") >= 1500
    if phase == "D2":
        return _alive(evaluations, "D2") >= 3060
    if phase == "D3":
        d2, d3 = _alive(evaluations, "D2"), _alive(evaluations, "D3")
        return d2 >= 6726.0523 and d3 >= 4433.0418
    raise ValueError("Unknown curriculum phase")


def qualification_passed(ratios: dict) -> bool:
    """Apply both survival ratios after independent paired-evaluation validation.

    This does not compute confidence bounds or validate held-out evidence. An absent
    difficulty or invalid bound is rejected rather than treated as a pass.
    """
    passed = True
    for stage in ("D2", "D3"):
        point = ratios[stage]["alive_frame_ratio_point"]
        lower = ratios[stage]["alive_frame_ratio_lower_bound"]
        for value in (point, lower):
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("Survival ratios must be finite and nonnegative")
        passed = passed and point >= 1.1 and lower > 1.0
    return passed
