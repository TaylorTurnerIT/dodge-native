"""One Dodge game on dodge_rl, shaped the way the heuristics expect.

The bots in dodge.heuristics were written against a single-lane engine: read
`lane_state(0)` every frame, step with one action, restart on death. This wraps
a one-slot `dodge_rl._native.VecDodgeEnv` to give them exactly that, so the bots
themselves need no changes.
"""

import numpy as np

try:
    from dodge_rl._native import VecDodgeEnv
except ImportError:  # the binding is optional until an engine is built
    VecDodgeEnv = None

INSTALL_HINT = ("dodge_rl is not installed: run `pip install ./crates/dodge-rl-env` "
                "(or `maturin develop` there) from the repository root")

# dodge-core's Action::ALL: neutral, L, R, U, D, UL, UR, DL, DR.
NEUTRAL = 0
DIFFICULTIES = {"easy": 1, "normal": 2, "hard": 3}


def available():
    return VecDodgeEnv is not None


class Engine:
    """A single game, held one frame per step, with exact state and rendering."""

    def __init__(self, *, seed, difficulty=3, patterns=False, powerups=True,
                 normal_enemies=True, kamikaze_enemies=True, spawn_rate_percent=100,
                 lives=0):
        if VecDodgeEnv is None:
            raise RuntimeError(INSTALL_HINT)
        self._env = VecDodgeEnv(
            batch_size=1, action_repeat=1, difficulty=int(difficulty),
            patterns_enabled=bool(patterns), powerups_enabled=bool(powerups),
            # the bot lives until it dies: never truncate the game
            raw_frame_cap=2**32 - 1,
            normal_enemies=bool(normal_enemies), kamikaze_enemies=bool(kamikaze_enemies),
            spawn_rate_percent=int(spawn_rate_percent), lives=int(lives),
            observation="entity", step_info="none",
        )
        self.reset(seed)

    def reset(self, seed):
        """Start a new game on this seed."""
        self._env.reset_all(seeds=[int(seed)])

    def lane_state(self, lane=0):
        """The game's raw state dict (px, py, enemies, cp, ...) for the bots."""
        return self._env.slot_state(lane)

    def frame(self):
        """The current screen as a (128, 128) uint8 array of palette indices."""
        return self._env.render([0])[0]

    def step(self, action):
        """Advance one frame; True when that frame ended the game."""
        out = self._env.step(np.array([int(action)], dtype=np.uint8))
        return bool(out["terminated"][0] or out["truncated"][0])
