"""Pure reference for adaptive assignment policy; no env, model, RNG, or launch API."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math

DOMAIN = "dodge.progressive1000.adaptive-frame-floor.assignment.v1"
FULL_GAME_HORIZON = 18000
STAGE_QUOTA_PERCENT = 30
FULL_GAME_FRAME_FLOOR = 0.70


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def assignment_block(digest: str, generation: int, update: int, block: int,
                     stage_quota_percent: int) -> tuple[int, ...]:
    """Return exactly100 deterministic horizon assignments for one update block."""
    if (not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)):
        raise ValueError("lowercase SHA256 required")
    if type(generation) is not int or not 0 <= generation <= 17:
        raise ValueError("generation must be integer0..17")
    for name, value, low in (("update", update, 1), ("block", block, 0)):
        if type(value) is not int or value < low:
            raise ValueError(name + " must be nonnegative integer in range")
    if type(stage_quota_percent) is not int or stage_quota_percent not in (0, 30):
        raise ValueError("stage quota must be0 or30 percent")
    stage = 1000 * (generation + 1)
    base = [stage] * stage_quota_percent + [FULL_GAME_HORIZON] * (100 - stage_quota_percent)
    keys = [(hashlib.sha256(_canonical(
        [DOMAIN, digest, generation, update, block, i])).digest(), i) for i in range(100)]
    return tuple(base[i] for _, i in sorted(keys))


@dataclass(frozen=True)
class Completion:
    decision: int
    slot: int
    generation: int
    horizon: int
    success: bool


@dataclass
class AdaptiveExposureScheduler:
    """Boundary-only rule; exposure target is feedback, not a hard guarantee.

    Start with all new assignments full-game. After each successful update,
    allow a30/70 stage/full-game episode mix only if cumulative realized frames
    from full-game-assigned episodes are at least70%; otherwise suspend short
    horizons until the measured share recovers. Existing episodes stay frozen.
    """
    digest: str
    update: int = 0
    generation: int = 0
    stage_updates: int = 0
    target_episodes: int = 0
    partial: list[bool] = field(default_factory=list)
    passing_streak: int = 0
    stage_mastered: bool = False
    next_stage_quota_percent: int = 0
    total_full_game_frames: int = 0
    total_stage_frames: int = 0
    assignment_counts: dict[int, int] = field(default_factory=dict)
    mastered: list[tuple[int, int]] = field(default_factory=list)

    def __post_init__(self):
        assignment_block(self.digest, 0, 1, 0, 0)

    @property
    def horizon(self):
        return 1000 * (self.generation + 1)

    @property
    def realized_full_game_frame_share(self):
        total = self.total_full_game_frames + self.total_stage_frames
        return None if total == 0 else self.total_full_game_frames / total

    def assign(self, update: int) -> tuple[int, int, int, int]:
        if type(update) is not int or update != self.update + 1 or update > 60:
            raise ValueError("assignments allowed only for next update1..60")
        ordinal = self.assignment_counts.get(update, 0)
        block, position = divmod(ordinal, 100)
        horizon = assignment_block(self.digest, self.generation, update, block,
                                   self.next_stage_quota_percent)[position]
        self.assignment_counts[update] = ordinal + 1
        return self.generation, horizon, ordinal, self.next_stage_quota_percent

    def finish_update(self, update: int, rows, *, full_game_frames: int,
                      stage_frames: int) -> dict:
        if type(update) is not int or update != self.update + 1 or update > 60:
            raise ValueError("updates must complete once in order1..60")
        for name, value in (("full_game_frames", full_game_frames), ("stage_frames", stage_frames)):
            if type(value) is not int or value < 0:
                raise ValueError(name + " must be a nonnegative integer")
        rows = tuple(rows)
        seen = set()
        for row in rows:
            if not isinstance(row, Completion) or type(row.success) is not bool:
                raise ValueError("audited Completion row required")
            if (type(row.decision) is not int or not 0 <= row.decision < 256
                    or type(row.slot) is not int or not 0 <= row.slot < 64
                    or type(row.generation) is not int or not 0 <= row.generation <= self.generation
                    or type(row.horizon) is not int or row.horizon % 1000
                    or not (1000 <= row.horizon <= 1000 * (row.generation + 1)
                            or row.horizon == FULL_GAME_HORIZON)):
                raise ValueError("invalid completion fields")
            key = (row.decision, row.slot)
            if key in seen:
                raise ValueError("duplicate completion")
            seen.add(key)
        before_generation = self.generation
        windows = []
        for row in sorted(rows, key=lambda r: (r.decision, r.slot)):
            if row.generation != self.generation or row.horizon != self.horizon:
                continue
            self.target_episodes += 1
            self.partial.append(row.success)
            if len(self.partial) == 100:
                passed = sum(self.partial) >= 90
                windows.append(passed)
                self.passing_streak = self.passing_streak + 1 if passed else 0
                self.partial.clear()
        self.stage_updates += 1
        self.total_full_game_frames += full_game_frames
        self.total_stage_frames += stage_frames
        self.update = update
        mastered_now = (not self.stage_mastered and self.stage_updates >= 10
                        and self.target_episodes >= 200 and self.passing_streak >= 2)
        promoted = False
        if mastered_now:
            self.stage_mastered = True
            self.mastered.append((self.horizon, update))
            if self.generation < 17:
                self.generation += 1
                self.stage_updates = self.target_episodes = self.passing_streak = 0
                self.stage_mastered = False
                self.partial.clear()
                promoted = True
        share = self.realized_full_game_frame_share
        self.next_stage_quota_percent = (STAGE_QUOTA_PERCENT
            if share is not None and share >= FULL_GAME_FRAME_FLOOR else 0)
        return {"completed_update": update, "generation_before": before_generation,
                "generation_after": self.generation, "windows": windows,
                "mastered_now": mastered_now, "promoted": promoted,
                "full_game_frames_total": self.total_full_game_frames,
                "stage_frames_total": self.total_stage_frames,
                "realized_full_game_frame_share": share,
                "next_update_stage_assignment_percent": self.next_stage_quota_percent}
