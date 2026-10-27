"""Nonlearned baselines over the existing nine-action space."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from typing import Any

ACTION_NAMES = (
    "neutral", "left", "right", "up", "down",
    "up_left", "up_right", "down_left", "down_right",
)
ACTION_MASKS = (0, 1, 2, 4, 8, 5, 6, 9, 10)
_DIRECTIONS = ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1),
               (-1, -1), (1, -1), (-1, 1), (1, 1))


class NeutralPolicy:
    def act(self, observation: Mapping[str, Any]) -> int:
        return 0


class RandomPolicy:
    """Uniform actions from a private RNG, independent of simulator/global RNG."""

    def __init__(self, seed: int = 0):
        self._rng = random.Random(seed)

    def act(self, observation: Mapping[str, Any]) -> int:
        return self._rng.randrange(len(ACTION_NAMES))


def _box_clearance(x: float, y: float, left: float, top: float,
                   width: float, height: float) -> float:
    right = left + max(width, 0.0)
    bottom = top + max(height, 0.0)
    outside = math.hypot(max(left - x, 0.0, x - right),
                         max(top - y, 0.0, y - bottom))
    if outside:
        return outside
    return -min(x - left, right - x, y - top, bottom - y)


def _segment_distance(x: float, y: float, line: Mapping[str, Any]) -> float:
    x0, y0, x1, y1 = (float(line[key]) for key in ("x0", "y0", "x1", "y1"))
    dx, dy = x1 - x0, y1 - y0
    denominator = dx * dx + dy * dy
    fraction = 0.0 if denominator == 0 else max(
        0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / denominator)
    )
    return math.hypot(x - x0 - fraction * dx, y - y0 - fraction * dy)


class AvoidancePolicy:
    """Short-horizon state heuristic; neither a learned nor an optimal teacher.

    Only the explicit training-state projection is read. Approximate enemy
    extrapolation and rectangular clearance do not reproduce the simulator's
    collision, bounce, pattern, or powerup dynamics.
    """

    def act(self, observation: Mapping[str, Any]) -> int:
        state = observation["train_only_state"]
        player = state["player"]
        dynamics = state["globals"]
        enemy_scale = float(dynamics["speed"]) * float(dynamics["freeze_rate"])
        player_extent = max(0.0, float(player["size"]) - 2.0)

        def cost(action_id: int) -> float:
            x, y = float(player["x"]), float(player["y"])
            vx, vy = float(player["vx"]), float(player["vy"])
            dx, dy = _DIRECTIONS[action_id]
            total = 0.0
            for horizon in range(1, 9):
                vx, vy = vx * 0.8 + dx * 0.5, vy * 0.8 + dy * 0.5
                x, y = max(2.0, min(125.0, x + vx)), max(2.0, min(125.0, y + vy))
                if horizon not in (1, 4, 8):
                    continue
                weight = 1.0 / horizon
                total += weight * 0.003 * ((x - 64.0) ** 2 + (y - 64.0) ** 2)
                for enemy in state["enemies"]:
                    if int(enemy["kind"]) >= 2:
                        continue
                    clearance = _box_clearance(
                        x, y,
                        float(enemy["x"]) + float(enemy["vx"]) * enemy_scale * horizon,
                        float(enemy["y"]) + float(enemy["vy"]) * enemy_scale * horizon,
                        float(enemy["size"]), float(enemy["size"]),
                    ) - player_extent
                    total += weight * self._risk(clearance)
                for rectangle in state["rectangles"]:
                    clearance = _box_clearance(
                        x, y,
                        float(rectangle["x"]) + float(rectangle["dx"]) * horizon,
                        float(rectangle["y"]) + float(rectangle["dy"]) * horizon,
                        float(rectangle["width"]), float(rectangle["height"]),
                    ) - player_extent
                    total += weight * self._risk(clearance)
                for line in state["warnings"]:
                    total += weight * 10.0 / (_segment_distance(x, y, line) + 2.0)
            return total

        return min(range(len(ACTION_NAMES)), key=cost)

    @staticmethod
    def _risk(clearance: float) -> float:
        if clearance <= 0:
            return 1_000.0 - 100.0 * clearance
        return 40.0 / (clearance + 2.0)


def make_policy(name: str, seed: int = 0):
    if name == "neutral":
        return NeutralPolicy()
    if name == "random":
        return RandomPolicy(seed)
    if name == "avoidance":
        return AvoidancePolicy()
    raise ValueError(f"unknown baseline policy: {name}")
