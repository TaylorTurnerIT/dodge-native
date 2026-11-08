"""Replay one recorded pattern appearance as the real game picture.

A game is a function of its settings, its seed and its decisions, so an
appearance is re-simulated rather than stored: a one-lane engine starts the
seed, plays the recorded decisions without rendering up to the appearance,
then renders every frame of it. The re-simulated game is checked against the
recording (the pattern starts when it did, and ends or kills the player when
it did); a replay that does not match says so instead of showing another game.
"""

from dataclasses import dataclass

import numpy as np

from .death_paths import KINDS, NO_PATTERN
from .env import make_engine

# Frames shown before a death outside any pattern: five seconds.
LOOSE_FRAMES = 300


@dataclass
class Replay:
    frames: np.ndarray   # (n, 128, 128) uint8 PICO-8 palette indices
    samples: list        # one per frame: {"frame", "st", "enemies", "enemy_gap", "rect_gap"}
    matched: bool
    reason: str | None


def _sample(sample):
    if sample["pattern_id"] is None:
        state = 0
    else:
        state = 2 if sample["lethal_rect_gap"] is not None else 1
    return {"frame": sample["frame"], "st": state, "enemies": sample["enemies"],
            "enemy_gap": sample["enemy_gap"], "rect_gap": sample["lethal_rect_gap"]}


def _window(appearance):
    if appearance["pid"] == NO_PATTERN:
        return max(1, appearance["end"] - LOOSE_FRAMES + 1), appearance["end"]
    return appearance["start"], appearance["end"]


def _mismatch(appearance, trace, frame, dead):
    """Why the re-simulated game is not the recorded one, or None."""
    outcome, start, end = appearance["outcome"], appearance["start"], appearance["end"]
    death = trace["death"]
    if outcome == "died":
        if death is None:
            return f"the replayed game was still alive at frame {frame}"
        if death["frame"] != end:
            return f"the replayed game died at frame {death['frame']}, not {end}"
        if KINDS.get(death["cause"], "unknown") != appearance["kind"]:
            return f"the replayed game died to {KINDS.get(death['cause'])}, not {appearance['kind']}"
    elif dead or frame < end:
        return f"the replayed game ended at frame {frame}, before frame {end}"
    if appearance["pid"] == NO_PATTERN:
        if death["active_pattern"] is not None:
            return f"the replayed game died in pattern {death['active_pattern']['id']}"
        return None
    span = next((s for s in trace["patterns"] if s["start"] == start), None)
    if span is None or span["id"] != appearance["pid"]:
        return f"pattern {appearance['pid']} did not start at frame {start} in the replay"
    expected = end if outcome == "survived" else None
    if span["end"] != expected:
        return f"pattern {appearance['pid']} ended at frame {span['end']}, not {expected}"
    return None


def replay(recording, appearance_id):
    """Re-simulate appearance `appearance_id` of `recording`, rendering its window."""
    appearance = recording.appearances[appearance_id]
    settings = {key: value for key, value in recording.settings.items() if key != "frame_cap"}
    repeat = int(settings.pop("step_frames", 1))
    engine = make_engine(1, trace=True, execution="serial", step_frames=1, **settings)
    engine.reset_all(seeds=np.array([appearance["seed"]], dtype=np.uint32))
    first, last = _window(appearance)
    frames, samples = [], []
    frame, dead = 0, False
    for decision in recording.actions[appearance["seed"]]:
        action = np.array([decision], dtype=np.uint8)
        # The recording held each decision for `repeat` frames, stopping at death.
        for _ in range(repeat):
            stepped = engine.step(action)
            frame += int(stepped["elapsed_raw_frames"][0])
            dead = bool(stepped["terminated"][0] or stepped["truncated"][0])
            # Frames before the window are only simulated; the window is drawn,
            # the death frame included.
            if first <= frame <= last:
                sample = engine.slot_sample(0)
                if sample is not None:
                    frames.append(engine.render([0])[0].copy())
                    samples.append(_sample(sample))
            if dead or frame >= last:
                break
        if dead or frame >= last:
            break
    reason = _mismatch(appearance, engine.slot_trace(0), frame, dead)
    pixels = np.stack(frames) if frames else np.zeros((0, 128, 128), dtype=np.uint8)
    return Replay(frames=pixels, samples=samples, matched=reason is None, reason=reason)
