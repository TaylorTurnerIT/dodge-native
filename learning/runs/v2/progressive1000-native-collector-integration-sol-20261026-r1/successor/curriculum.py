"""Preparation-only native cutoff integration; no native import or runner CLI.

The only supported update entry point is PreparedUpdates.update_once(). It owns
collection, PPO, and the post-PPO scheduler boundary as one consumed operation.
An exception poisons the instance: partial environment/optimizer work is never
silently replayed. Telemetry remains external to RolloutBatch/model inputs.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from collections.abc import Mapping

import numpy as np
import torch

from . import ppo
from .scheduler_reference import Completion, Scheduler

# Required historical exclusions are a floor, not a freshness assertion. The
# parent's future exhaustive union must be explicitly injected before creation.
HISTORICAL_RANGES = tuple(sorted(((0xB0000000, 0xB00003E7),
    (0xD0000000, 0xD000007F), (0xE0000000, 0xE00003E7),
    (3506438144, 3506439167), (3523215360, 3523217407))))
PINNED_PPO = ppo.PPOConfig(learning_rate=3e-5)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_seed_union(ranges):
    """Validate an explicit canonical inclusive union, without reserving seeds.

    Call this before future environment construction. Validation proves shape
    and historical coverage only; parent ancestry/cohort review is still needed.
    This successor helper does not modify the frozen five-range validator.
    """
    require(isinstance(ranges, (list, tuple)) and bool(ranges),
            "explicit parent-owned seed union required")
    normalized = []
    for row in ranges:
        require(isinstance(row, (list, tuple)) and len(row) == 2,
                "seed union rows must be integer pairs")
        low, high = row
        require(type(low) is int and type(high) is int
                and 0 <= low <= high <= 2**32 - 1, "invalid seed union bounds")
        normalized.append((low, high))
    normalized = tuple(normalized)
    require(normalized == tuple(sorted(normalized)), "seed union must be sorted")
    require(all(left[1] + 1 < right[0]
                for left, right in zip(normalized, normalized[1:])),
            "seed union must be disjoint and merged")
    require(normalized != ((0, 2**32 - 1),), "seed union exhausts u32")
    require(all(any(low <= a and high >= b for low, high in normalized)
                for a, b in HISTORICAL_RANGES), "historical exclusions missing")
    return normalized


def equal(left, right):
    """Exact recursive comparison, including all diagnostic/observation fields."""
    if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
        return (isinstance(left, np.ndarray) and isinstance(right, np.ndarray)
                and left.dtype == right.dtype and left.shape == right.shape
                and np.array_equal(left, right))
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return left.keys() == right.keys() and all(equal(left[k], right[k]) for k in left)
    if isinstance(left, (tuple, list)) and isinstance(right, (tuple, list)):
        return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right))
    return type(left) is type(right) and left == right


@dataclass(frozen=True)
class Assignment:
    generation: int | None
    horizon: int
    ordinal: int | None


class CurriculumAdapter:
    """Persistent per-run assignments and external raw-frame telemetry.

    Construct once against normal-start episodes, retain across rollouts.
    Control uses this same collector/adapter with enabled=False and no Scheduler.
    The native method is mandatory for live practice boundaries; there is no
    flag-only fallback. All post-call checks are fail-closed, not rollback.
    """
    def __init__(self, env, *, enabled, digest, replica, exclusion_ranges):
        require(type(enabled) is bool, "enabled must be boolean")
        require(type(replica) is int and 1 <= replica <= 3, "replica must be integer1..3")
        self.replica = replica
        self.arm = "progressive_curriculum" if enabled else "matched_control"
        self.exclusions = validate_seed_union(exclusion_ranges)
        self.env, self.enabled = env, enabled
        self.scheduler = Scheduler(digest) if enabled else None
        self.completed_updates = 0
        self.pending_update = None
        self.rows = []
        self.assignments = {}
        self.assignment_seeds = {}
        self.assignment_events, self.completions, self.boundaries = [], [], []
        self.intervals, self.update_exposure = {}, {}
        self.gameplay_frames = self.reset_startup_frames = 0
        self.observed_native_frames = 0
        self.observed_native_steps = 0
        self.returned_reset_startup_frames = 0
        self.returned_resets = []
        self.expected_reset = []
        self.last_infos = None
        self.reset_count = 0
        metadata = env.batch_info()
        self.batch_size = metadata["batch_size"]
        require(type(self.batch_size) is int and 1 <= self.batch_size <= 64,
                "preparation adapter supports slots 1..64")
        require(metadata["action_repeat"] == 4 and metadata["raw_frame_cap"] == 18000,
                "requires action_repeat4 and ordinary cap18000")
        require(metadata["seed_mode"]["mode"] == "training", "training stream required")
        require(tuple(tuple(row) for row in metadata["effective_excluded_seed_ranges"])
                == self.exclusions, "environment seed union differs from explicit union")
        infos = env.episode_info()
        require(len(infos) == self.batch_size, "initial episode metadata incomplete")
        for slot, info in enumerate(infos):
            self._validate_active(info, slot)
            require(info["gameplay_frames"] == info["alive_frames"] == 0,
                    "initial assignments require normal starts at frame0")
            self._assign(slot, info, 0, -1)
        self.initial_startup_frames = 13 * self.batch_size
        self.last_decision = -1

    def _seed(self, info):
        seed = info["seed"]["actual_seed"]
        require(type(seed) is int and 0 <= seed <= 2**32 - 1
                and not any(low <= seed <= high for low, high in self.exclusions),
                "episode seed collides with explicit union")

    def _validate_active(self, info, slot):
        ppo._audit_episode(info, 18000)
        self._seed(info)
        require(info["seed"]["slot"] == slot and not info["terminated"]
                and not info["truncated"], "active slot identity/boundary differs")
        require(type(info["gameplay_frames"]) is int
                and info["gameplay_frames"] % 4 == 0, "misaligned live episode")

    def _assign(self, slot, info, update, decision):
        if self.enabled:
            generation, horizon, ordinal = self.scheduler.assign()
            assignment = Assignment(generation, horizon, ordinal)
        else:
            assignment = Assignment(None, 18000, None)
        self.assignments[slot] = assignment
        self.assignment_seeds[slot] = copy.deepcopy(info["seed"])
        self.assignment_events.append({"update": update, "decision": decision,
            "slot": slot, **asdict(assignment), "seed": copy.deepcopy(info["seed"]),
            "block": None if assignment.ordinal is None else assignment.ordinal // 100,
            "position": None if assignment.ordinal is None else assignment.ordinal % 100,
            "vector_hash": None if self.scheduler is None else self.scheduler.digest})

    def begin_update(self, update):
        require(self.pending_update is None, "previous collection has no successful PPO finish")
        require(type(update) is int and update == self.completed_updates + 1 and update <= 60,
                "global updates must complete once in order1..60")
        self.pending_update = update
        self.rows = []
        self.last_decision = -1

    def before_step(self, previous, decision):
        require(self.pending_update is not None and decision == self.last_decision + 1
                and 0 <= decision < 256, "decision order differs")
        require(not self.expected_reset, "combined ended-slot reset still pending")
        require(len(previous) == self.batch_size, "previous metadata incomplete")
        for slot, info in enumerate(previous):
            self._validate_active(info, slot)
            horizon = self.assignments[slot].horizon
            require(info["gameplay_frames"] + 4 <= horizon,
                    "practice horizon overshoot/misalignment before simulation")

    def observe_returned_step(self, result):
        """Count returned native work before a post-step guard/audit can fail.

        This counter is deliberately unaudited until record_step succeeds.
        Native exceptions with no returned result need future native receipts.
        """
        self.observed_native_frames += sum(int(value) for value in result["elapsed_raw_frames"])
        self.observed_native_steps += 1

    def observe_returned_reset(self, indices, reset):
        """Retain startup work even when a later reset guard/audit fails."""
        self.returned_reset_startup_frames += sum(int(info["startup_frames"]) for info in reset["info"])
        self.returned_resets.append({"update": self.pending_update,
            "decision": self.last_decision, "indices": list(indices),
            "info": copy.deepcopy(reset["info"])})

    def reconcile(self, result, previous, decision):
        """After actual step, before audit/storage/value/reset; replace only cutoffs."""
        require(self.pending_update is not None and decision == self.last_decision + 1,
                "reconcile outside active ordered collection")
        # Boundary prevalidation only; the inherited reward/episode/step audit
        # runs after native cutoff and reconciliation, before buffer storage.
        audited = {name: ppo._integer_vector(result[name], self.batch_size, name)
                   for name in ("elapsed_raw_frames", "alive_raw_frames", "score_delta_raw_fixed")}
        flags = {name: ppo._boolean_vector(result[name], self.batch_size, name)
                 for name in ("terminated", "truncated")}
        require(len(result["info"]) == self.batch_size, "step metadata incomplete")
        selected = []
        for slot, info in enumerate(result["info"]):
            self._seed(info)
            require(info["terminated"] == bool(flags["terminated"][slot])
                    and info["truncated"] == bool(flags["truncated"][slot])
                    and not (info["terminated"] and info["truncated"]),
                    "unreconciled native boundary flags differ")
            old = previous[slot]
            require(info["seed"] == old["seed"], "step slot identity changed")
            require(info["gameplay_frames"] == old["gameplay_frames"]
                    + int(audited["elapsed_raw_frames"][slot])
                    and info["alive_frames"] == old["alive_frames"]
                    + int(audited["alive_raw_frames"][slot])
                    and info["score_raw_fixed"] == old["score_raw_fixed"]
                    + int(audited["score_delta_raw_fixed"][slot]),
                    "step cumulative counters differ")
            horizon = self.assignments[slot].horizon
            require(info["gameplay_frames"] <= horizon, "practice horizon overshoot")
            if info["terminated"] or info["truncated"]:
                require(not info["truncated"] or info["gameplay_frames"] == 18000,
                        "unexpected preexisting native truncation")
                continue  # Death (including death on H) and ordinary cap win.
            require(info["gameplay_frames"] % 4 == 0, "misaligned live step")
            if self.enabled and horizon < 18000 and info["gameplay_frames"] == horizon:
                selected.append(slot)
        if not selected:
            return
        before = copy.deepcopy(result)
        require(equal(self.env.episode_info(), before["info"]),
                "step info differs from current native episodes")
        native_infos = self.env.truncate_practice(
            selected, [self.assignments[slot].horizon for slot in selected])
        require(isinstance(native_infos, list) and len(native_infos) == len(selected),
                "native cutoff returned incomplete owned EpisodeInfo list")
        expected_infos = copy.deepcopy(before["info"])
        for slot, info in zip(selected, native_infos, strict=True):
            expected = copy.deepcopy(before["info"][slot])
            expected["truncated"] = True
            expected["terminated"] = False
            require(equal(info, expected), "native cutoff changed EpisodeInfo beyond boundary flag")
            expected_infos[slot] = expected
        require(equal(self.env.episode_info(), expected_infos),
                "native cutoff mutated other slots or returned inconsistent episode_info")
        require(equal(self.env.observations(), before["observations"]),
                "native cutoff changed final observation/history payload")
        require(equal(result, before), "native cutoff mutated owned step result")
        # No mutation until native result and preservation checks have succeeded.
        result["truncated"] = result["truncated"].copy()
        result["info"] = list(result["info"])
        for slot, info in zip(selected, native_infos, strict=True):
            result["truncated"][slot] = True
            result["info"][slot] = copy.deepcopy(info)

    def record_step(self, result, previous, decision):
        """Record executed frames and frozen completion tags after collector audit."""
        generation = None if self.scheduler is None else self.scheduler.generation
        for slot, info in enumerate(result["info"]):
            assignment = self.assignments[slot]
            old, new = previous[slot]["gameplay_frames"], info["gameplay_frames"]
            self.gameplay_frames += new - old  # Includes the fatal frame.
            exposure_key = (self.pending_update, assignment.generation, assignment.horizon, generation)
            self.update_exposure[exposure_key] = self.update_exposure.get(exposure_key, 0) + new - old
            for low in range(0, new, 1000):
                high = low + 1000
                frames = max(0, min(new, high) - max(old, low))
                if not frames:
                    continue
                key = (assignment.generation, assignment.horizon, generation, low, high)
                row = self.intervals.setdefault(key, dict(executed_gameplay_frames=0,
                    interval_entries=0, boundary_reaches=0, alive_through=0))
                row["executed_gameplay_frames"] += frames
                row["interval_entries"] += int(old <= low < new)
                row["boundary_reaches"] += int(old < high <= new)
                row["alive_through"] += int(previous[slot]["alive_frames"] < high <= info["alive_frames"])
            if info["terminated"] or info["truncated"]:
                success = info["alive_frames"] >= assignment.horizon
                self.completions.append({"update": self.pending_update, "decision": decision,
                    "slot": slot, **asdict(assignment), "success": success,
                    "scheduler_generation": generation, "native_info": copy.deepcopy(info)})
                if self.enabled:
                    self.rows.append(Completion(decision, slot, assignment.generation,
                                                assignment.horizon, success))
        self.expected_reset = [slot for slot, info in enumerate(result["info"])
                               if info["terminated"] or info["truncated"]]
        self.last_infos = copy.deepcopy(result["info"])
        self.last_decision = decision

    def record_reset(self, indices, infos, decision):
        require(indices == self.expected_reset, "reset differs from complete ended-slot set")
        require(indices == sorted(set(indices)) and len(indices) == len(infos),
                "subset resets require complete stable slot order")
        expected = copy.deepcopy(self.last_infos)
        for slot, info in zip(indices, infos, strict=True):
            expected[slot] = copy.deepcopy(info)
        require(equal(self.env.episode_info(), expected),
                "subset reset changed unselected episode identity/counters")
        for slot, info in zip(indices, infos, strict=True):
            self._validate_active(info, slot)
            self._assign(slot, info, self.pending_update, decision)
            self.reset_count += 1
            self.reset_startup_frames += info["startup_frames"]
        self.expected_reset = []

    def _finish_after_ppo(self):
        """Private to PreparedUpdates: collection alone never advances mastery."""
        require(self.pending_update is not None and self.last_decision == 255
                and not self.expected_reset,
                "finish requires all256 decisions and successful PPO")
        update = self.pending_update
        boundary = (self.scheduler.finish_update(update, self.rows) if self.enabled else
                    {"completed_update": update, "promoted": False,
                     "generation_after_boundary": None})
        self.boundaries.append(copy.deepcopy(boundary))
        self.completed_updates = update
        self.pending_update = None
        return boundary

    def _in_flight(self):
        """Join an assignment only to the exact episode that received it.

        A returned reset can precede a failed guard or metadata audit. Retain
        that live episode as unassigned; snapshotting never assigns or retries.
        """
        rows = []
        for slot, info in enumerate(self.env.episode_info()):
            if info["terminated"] or info["truncated"]:
                continue
            matched = equal(self.assignment_seeds.get(slot), info["seed"])
            assignment = (asdict(self.assignments[slot]) if matched else
                          {"generation": None, "horizon": None, "ordinal": None})
            rows.append({"slot": slot, **assignment,
                         "assignment_status": "assigned" if matched else "unassigned_unaudited",
                         "native_info": copy.deepcopy(info)})
        return rows

    def snapshot(self):
        """No stepping/draining; preserve terminal or failed in-flight exposure."""
        return {"preparation_only": True, "replica": self.replica, "arm": self.arm,
            "completed_updates": self.completed_updates,
            "pending_update": self.pending_update,
            "returned_native_gameplay_frames_unaudited": self.observed_native_frames,
            "returned_native_vector_steps": self.observed_native_steps,
            "returned_work_not_accepted_by_audit": self.observed_native_frames - self.gameplay_frames,
            "gameplay_frames_including_fatal": self.gameplay_frames,
            "initial_construction_startup_frames": self.initial_startup_frames,
            "normal_reset_count": self.reset_count,
            "returned_reset_startup_frames_unaudited": self.returned_reset_startup_frames,
            "returned_resets": copy.deepcopy(self.returned_resets),
            "reset_startup_frames": self.reset_startup_frames,
            "raw_frames_total_including_returned_unaudited_work": (self.observed_native_frames
                + self.initial_startup_frames + self.returned_reset_startup_frames),
            "accepted_raw_frames_total": self.gameplay_frames + self.initial_startup_frames + self.reset_startup_frames,
            "assignments": copy.deepcopy(self.assignment_events),
            "completions": copy.deepcopy(self.completions),
            "boundaries": copy.deepcopy(self.boundaries),
            "interval_exposure": [{"generation": key[0], "horizon": key[1],
                "scheduler_generation": key[2], "low": key[3], "high": key[4], **row}
                for key, row in self.intervals.items()],
            "update_exposure": [{"update": key[0], "generation": key[1],
                "horizon": key[2], "scheduler_generation": key[3], "raw_frames": frames}
                for key, frames in self.update_exposure.items()],
            "in_flight": self._in_flight(),
            "scheduler": None if self.scheduler is None else asdict(self.scheduler)}


class PreparedUpdates:
    """Bounded CPU source prototype, not a registered runner or identity gate.

    update_once() is the complete call contract. Never call collect_rollout and
    finish separately in a future runner. Keep this instance for all60 updates.
    A failed collection/PPO/boundary consumes the session and preserves telemetry.
    No checkpoint restore/save, evaluator, environment construction, or seeds are
    implemented here. Future integration must bind and qualify all those gates.
    """
    def __init__(self, model, optimizer, adapter, *, config=PINNED_PPO):
        require(asdict(config) == asdict(PINNED_PPO), "full pinned PPO config required")
        require(adapter.batch_size == 64, "shared runner contract requires64 slots")
        require(all(parameter.device.type == "cpu" for parameter in model.parameters()),
                "source prototype supports synthetic CPU only")
        self.model, self.optimizer, self.adapter = model, optimizer, adapter
        self.config, self.observation = config, None
        self.state = "ready"
        self.actual_optimizer_steps = 0
        self.metrics = []
        self.progress = {}
        self._optimizer_contract()

    def _optimizer_contract(self):
        require(bool(self.optimizer.param_groups) and all(
            group["lr"] == self.config.learning_rate and group["eps"] == self.config.adam_eps
            for group in self.optimizer.param_groups), "constant Adam LR/epsilon differs")

    def snapshot(self):
        return {"state": self.state, "completed_optimizer_steps": self.actual_optimizer_steps,
                "last_update_progress": copy.deepcopy(self.progress),
                "metrics": copy.deepcopy(self.metrics), "environment": self.adapter.snapshot()}

    def update_once(self, *, check_guard=None):
        require(self.state == "ready", "update session consumed or failed")
        require(self.adapter.completed_updates < 60, "terminal global60; no drain or update61")
        self.state = "in_update"
        try:
            self._optimizer_contract()
            self.adapter.begin_update(self.adapter.completed_updates + 1)
            collection = ppo.collect_rollout(self.model, self.adapter.env, 256, "cpu",
                observation=self.observation, config=self.config, check_guard=check_guard,
                boundary_adapter=self.adapter)
            self.observation = collection.observations
            metrics = ppo.ppo_update(self.model, self.optimizer, collection.batch,
                self.config, check_guard=check_guard, progress=self.progress)
            self._optimizer_contract()
            boundary = self.adapter._finish_after_ppo()
            self.actual_optimizer_steps += metrics["optimizer_steps"]
            self.metrics.append(copy.deepcopy(metrics))
            self.state = "ready"
            return collection, metrics, boundary
        except BaseException:
            self.state = "failed"
            raise
