"""Dodge on dodge_rl: the only module that imports the binding.

Everything that talks to the engine goes through here:

* `make_engine` builds the batched `dodge_rl._native.VecDodgeEnv` the trainer
  and evaluator run on (VelocityFlow observation, optional critic features);
* `Engine` is one game held a frame per step, which is what the bots in
  dodge.heuristics were written against: read `lane_state(0)` every frame, step
  with one action, restart on death;
* the critic constants and the binary's path for checkpoint provenance.
"""

import os

import numpy as np

try:
    from dodge_rl import _native
    from dodge_rl._native import VecDodgeEnv
except ImportError:  # the binding is optional until an engine is built
    _native = None
    VecDodgeEnv = None

INSTALL_HINT = ("dodge_rl is not installed: run `pip install ./crates/dodge-rl-env` "
                "(or `maturin develop` there) from the repository root")

# dodge-core's Action::ALL: neutral, L, R, U, D, UL, UR, DL, DR.
NEUTRAL = 0
DIFFICULTIES = {"easy": 1, "normal": 2, "hard": 3}


MAX_ACTION_REPEAT = 5
SPAWN_RATE_PERCENT_MIN = 50
SPAWN_RATE_PERCENT_MAX = 150
UNCAPPED = 2**32 - 1

# The critic's extra columns, which a checkpoint records and checks on load. A
# missing binding reports no critic features at all.
CRITIC_FEATURE_VERSION = getattr(_native, "CRITIC_FEATURE_VERSION", 0)
CRITIC_FEATURE_COUNT = getattr(_native, "CRITIC_FEATURE_COUNT", 0)
CRITIC_GROUPS = dict(getattr(_native, "CRITIC_GROUPS", {}))


def available():
    return VecDodgeEnv is not None


def binary_path():
    """The installed dodge_rl extension's file, or None without the binding."""
    return getattr(_native, "__file__", None)


def validate_spawn_rate_percent(value):
    """Return an integer spawn percentage in the supported curriculum range."""
    try:
        numeric = float(value)
        integer = int(numeric)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("spawn rate must be an integer percentage") from None
    if numeric != integer:
        raise ValueError("spawn rate must be an integer percentage")
    if not SPAWN_RATE_PERCENT_MIN <= integer <= SPAWN_RATE_PERCENT_MAX:
        raise ValueError(f"spawn rate must be between {SPAWN_RATE_PERCENT_MIN}% "
                         f"and {SPAWN_RATE_PERCENT_MAX}%")
    return integer


def make_engine(batch_size, *, step_frames=1, difficulty=1, patterns=False,
                powerups=False, normal_enemies=True, kamikaze_enemies=True,
                spawn_rate_percent=100, lives=0, execution="parallel",
                max_frames=None, critic_features=False, trace=False):
    """A VelocityFlow batch of `batch_size` games with the settings applied.

    Each step holds the action for `step_frames` frames, stopping a slot early
    at the frame it dies or reaches `max_frames` (None: no cap), which ends it
    as truncated. The batch fixes its size here and starts every game on seeds
    of its own; callers restart them with `reset_all(seeds=...)` and, for slots
    that have ended, `reset_done(indices, seeds=...)`.
    """
    if VecDodgeEnv is None:
        raise RuntimeError(INSTALL_HINT)
    if int(difficulty) not in (1, 2, 3):
        raise ValueError("difficulty must be 1 (easy), 2 (normal), or 3 (hard)")
    if not 1 <= step_frames <= MAX_ACTION_REPEAT:
        raise ValueError(f"action_repeat must be between 1 and {MAX_ACTION_REPEAT}")
    if lives < 0:
        raise ValueError("lives cannot be negative")
    if max_frames is not None and not 1 <= max_frames <= UNCAPPED:
        raise ValueError("max_frames must be positive or None")
    threads = 1 if execution == "serial" else max(1, min(batch_size, os.cpu_count() or 1))
    return VecDodgeEnv(
        batch_size=int(batch_size),
        action_repeat=int(step_frames),
        difficulty=int(difficulty),
        patterns_enabled=bool(patterns),
        powerups_enabled=bool(powerups),
        raw_frame_cap=UNCAPPED if max_frames is None else int(max_frames),
        num_threads=threads,
        normal_enemies=bool(normal_enemies),
        kamikaze_enemies=bool(kamikaze_enemies),
        spawn_rate_percent=validate_spawn_rate_percent(spawn_rate_percent),
        lives=int(lives),
        observation="velocity_flow",
        critic_features=bool(critic_features),
        step_info="none",
        trace=bool(trace),
    )


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
