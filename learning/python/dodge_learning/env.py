"""Persistent in-process environment; image policies must receive pixels alone."""

from __future__ import annotations

import math
import operator
from numbers import Real
from typing import Any


def _integer(value: int, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    try:
        converted = operator.index(value)
    except TypeError as error:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}") from error
    if not minimum <= converted <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return converted


class NativeEnvironment:
    """Own a native simulator with independent seeded episodes.

    Results separate ``pixels`` from ``train_only_state`` and diagnostic ``info``.
    The caller decides when to reset; stepping never performs an automatic reset.
    """

    def __init__(
        self,
        seed: int = 42,
        max_episode_frames: int = 18_000,
        action_repeat: int = 1,
        discount: float = 0.99,
        difficulty: int = 2,
        patterns_enabled: bool = True,
        powerups_enabled: bool = True,
        theme_background: int = 12,
        theme_shadow: int = 1,
    ) -> None:
        seed = _integer(seed, "seed", 0, 0xFFFFFFFF)
        max_episode_frames = _integer(max_episode_frames, "max_episode_frames", 1, 0xFFFFFFFF)
        action_repeat = _integer(action_repeat, "action_repeat", 1, 0xFFFFFFFF)
        difficulty = _integer(difficulty, "difficulty", 1, 3)
        theme_background = _integer(theme_background, "theme_background", 0, 15)
        theme_shadow = _integer(theme_shadow, "theme_shadow", 0, 15)
        if isinstance(discount, bool) or not isinstance(discount, Real):
            raise ValueError("discount must be finite and in (0, 1]")
        if not 0 < discount <= 1 or not math.isfinite(discount):
            raise ValueError("discount must be finite and in (0, 1]")
        for name, value in (("patterns_enabled", patterns_enabled), ("powerups_enabled", powerups_enabled)):
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be a boolean")
        try:
            from ._native import NativeEnvironment as Backend
        except ImportError as error:
            raise ImportError(
                "Build the optional native bridge first: cd learning && uv pip install -e ."
            ) from error
        self._backend = Backend(
            seed=seed,
            max_episode_frames=max_episode_frames,
            action_repeat=action_repeat,
            discount=discount,
            difficulty=difficulty,
            patterns_enabled=patterns_enabled,
            powerups_enabled=powerups_enabled,
            theme_background=theme_background,
            theme_shadow=theme_shadow,
        )

    def reset(self, seed: int | None = None) -> dict[str, Any]:
        if seed is not None:
            seed = _integer(seed, "seed", 0, 0xFFFFFFFF)
        return self._backend.reset(seed)

    def current(self) -> dict[str, Any]:
        """Read the latest successful reset/step result without changing it."""
        return self._backend.current()

    def student_observation(self) -> bytes:
        """Return pixels alone, without constructing privileged Python records."""
        return self._backend.student_observation()

    def step(self, action_id: int) -> dict[str, Any]:
        action = _integer(action_id, "action_id", 0, 8)
        return self._backend.step(action)

    def close(self) -> None:
        """No child process or graphics device requires cleanup."""

    def __enter__(self) -> NativeEnvironment:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
