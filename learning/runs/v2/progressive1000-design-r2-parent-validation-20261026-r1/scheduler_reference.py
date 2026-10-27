"""Source/synthetic scheduler specification only; no runtime, RNG or launch API."""

from dataclasses import dataclass, field
import hashlib
import json

DOMAIN = "dodge.progressive1000.assignment.v2"
SEED_BOUNDS = {
    "constructor_init_seed": (1, 2**32 - 1),
    "python_random_seed": (1, 2**63 - 1),
    "numpy_global_seed": (0, 2**32 - 1),
    "torch_cpu_global_seed": (1, 2**63 - 1),
    "action_sampler_torch_mps_seed": (1, 2**63 - 1),
    "env_master_seed": (1, 2**64 - 1),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def vector_hash(study_id, replica, seeds):
    if not isinstance(study_id, str) or not study_id:
        raise ValueError("study_id must be nonempty")
    if type(replica) is not int or not 0 <= replica < 3:
        raise ValueError("replica must be integer0..2")
    if not isinstance(seeds, dict) or set(seeds) != set(SEED_BOUNDS):
        raise ValueError("exactly six seed fields required")
    for name, (low, high) in SEED_BOUNDS.items():
        if type(seeds[name]) is not int or not low <= seeds[name] <= high:
            raise ValueError("invalid seed: " + name)
    return hashlib.sha256(canonical(
        {"study_id": study_id, "replica": replica, "seeds": seeds})).hexdigest()


def assignment_block(digest, generation, block):
    """Return the100 ordered horizons; each item consumes one normal reset."""
    if (not isinstance(digest, str) or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)):
        raise ValueError("lowercase SHA256 required")
    if type(generation) is not int or not 0 <= generation <= 17:
        raise ValueError("generation must be integer0..17")
    if type(block) is not int or block < 0:
        raise ValueError("block must be a nonnegative integer")
    if generation == 0:
        return (1000,) * 100
    horizon = 1000 * (generation + 1)
    q, r = divmod(30, generation)
    extra = {(block * r + j) % generation for j in range(r)}
    base = [horizon] * 70
    for i in range(generation):
        base.extend([1000 * (i + 1)] * (q + (i in extra)))
    keys = [(hashlib.sha256(canonical(
        [DOMAIN, digest, generation, block, i])).digest(), i) for i in range(100)]
    return tuple(base[i] for _, i in sorted(keys))


@dataclass(frozen=True)
class Completion:
    """An already-audited completion, tagged with its frozen episode assignment."""

    decision: int
    slot: int
    generation: int
    horizon: int
    success: bool


@dataclass
class Scheduler:
    """Call finish_update once after a fully completed rollout/PPO update.

    This is an inert ledger, not an environment or training implementation.
    The caller records/resets ended slots during the rollout in stable slot
    order. All such resets use the old generation until finish_update returns.
    """

    digest: str
    update: int = 0
    generation: int = 0
    stage_updates: int = 0
    target_episodes: int = 0
    partial: list = field(default_factory=list)
    streak: int = 0
    stage_mastered: bool = False
    assignment_ordinal: int = 0
    mastered: list = field(default_factory=list)

    def __post_init__(self):
        assignment_block(self.digest, 0, 0)

    @property
    def horizon(self):
        return 1000 * (self.generation + 1)

    def assign(self):
        """Stable initial/reset order is a caller contract; no forced resets."""
        if self.update >= 60:
            raise ValueError("terminal pilot; no new assignments")
        ordinal = self.assignment_ordinal
        block, position = divmod(ordinal, 100)
        horizon = assignment_block(self.digest, self.generation, block)[position]
        self.assignment_ordinal += 1
        return self.generation, horizon, ordinal

    def finish_update(self, update, rows):
        """Validate all rows, process the whole update, then promote at most once."""
        if type(update) is not int or update != self.update + 1 or update > 60:
            raise ValueError("updates must be completed once in order1..60")
        rows = tuple(rows)
        seen = set()
        for row in rows:
            if not isinstance(row, Completion):
                raise ValueError("Completion required")
            if (type(row.decision) is not int or not 0 <= row.decision < 256
                    or type(row.slot) is not int or not 0 <= row.slot < 64
                    or type(row.generation) is not int
                    or not 0 <= row.generation <= self.generation
                    or type(row.horizon) is not int
                    or row.horizon % 1000 or not 1000 <= row.horizon
                    <= 1000 * (row.generation + 1)
                    or type(row.success) is not bool):
                raise ValueError("invalid completion fields")
            key = row.decision, row.slot
            if key in seen:
                raise ValueError("duplicate decision/slot completion")
            seen.add(key)
        rows = sorted(rows, key=lambda row: (row.decision, row.slot))
        windows = []
        for row in rows:
            if row.generation != self.generation or row.horizon != self.horizon:
                continue
            self.target_episodes += 1
            self.partial.append(row.success)
            if len(self.partial) == 100:
                passed = sum(self.partial) >= 90
                windows.append(passed)
                self.streak = self.streak + 1 if passed else 0
                self.partial.clear()
        self.stage_updates += 1
        self.update = update
        mastered_now = (not self.stage_mastered and self.stage_updates >= 10
                        and self.target_episodes >= 200 and self.streak >= 2)
        promoted = False
        if mastered_now:
            self.stage_mastered = True
            self.mastered.append((self.horizon, update))
            if self.generation < 17:
                self.generation += 1
                self.stage_updates = self.target_episodes = self.streak = 0
                self.assignment_ordinal = 0
                self.partial.clear()
                self.stage_mastered = False
                promoted = True
        return {"completed_update": update, "window_results": windows,
                "mastered_now": mastered_now, "promoted": promoted,
                "generation_after_boundary": self.generation}
