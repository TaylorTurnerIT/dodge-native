"""Bounded, image-storage-free evaluation of nonlearned native baselines."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .policies import ACTION_NAMES, ACTION_MASKS, make_policy

MAX_SEEDS = 1_000
MAX_EPISODE_FRAMES = 18_000


class EvaluationTimeout(RuntimeError):
    """The evaluation exceeded its explicit shared wall-time budget."""


def unique_seeds(values: Iterable[int]) -> list[int]:
    """Preserve order while merging duplicate seeds and the 0/1 RNG alias."""
    seeds: list[int] = []
    streams: set[int] = set()
    for index, seed in enumerate(values):
        if index >= MAX_SEEDS:
            raise ValueError(f"provide at most {MAX_SEEDS} seeds, including duplicates")
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 0xFFFFFFFF:
            raise ValueError("seeds must be unsigned 32-bit integers")
        stream = 1 if seed == 0 else seed
        if stream not in streams:
            seeds.append(seed)
            streams.add(stream)
    if not seeds:
        raise ValueError("provide at least one seed")
    return seeds


def parse_seeds(value: str) -> list[int]:
    try:
        # Check the input count before allocating an arbitrarily large split list.
        if value.count(",") >= MAX_SEEDS:
            raise ValueError(f"provide at most {MAX_SEEDS} seeds")
        return unique_seeds(int(item.strip()) for item in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _percentile(values: list[int], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _native_count(value: Any, name: str, upper_bound: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= upper_bound:
        raise RuntimeError(f"{name} must be a nonnegative integer no greater than {upper_bound}")
    return value


def _pattern_metrics(
    info: dict[str, Any], episode_frames: int,
) -> tuple[list[dict[str, int]] | None, int | None]:
    """Copy native counters without treating unavailable exposure as measured zero."""
    completions = info.get("pattern_completions")
    if completions is not None:
        completions = _native_count(completions, "pattern_completions", episode_frames)
    metrics = info.get("pattern_metrics")
    if metrics is None:
        return None, completions
    if not isinstance(metrics, list) or len(metrics) > 256:
        raise RuntimeError("pattern_metrics must be a list of at most 256 pattern counters")
    result = []
    seen = set()
    for counters in metrics:
        if not isinstance(counters, dict):
            raise RuntimeError("pattern_metrics entries must be dictionaries")
        if any(key not in counters for key in ("id", "encounters", "exposure_frames", "completions")):
            raise RuntimeError("pattern_metrics entry is missing a required counter")
        identity = _native_count(counters["id"], "pattern ID", 255)
        if identity in seen:
            raise RuntimeError("pattern_metrics contains duplicate pattern IDs")
        seen.add(identity)
        counts = {
            name: _native_count(counters[name], f"pattern {name}", episode_frames)
            for name in ("encounters", "exposure_frames", "completions")
        }
        if not counts["completions"] <= counts["encounters"] <= counts["exposure_frames"]:
            raise RuntimeError("pattern counters require completions <= encounters <= exposure_frames")
        result.append({"id": identity, **counts})
    if sum(record["exposure_frames"] for record in result) > episode_frames:
        raise RuntimeError("total pattern exposure exceeds the episode's native frames")
    measured_completions = sum(record["completions"] for record in result)
    if completions is not None and completions != measured_completions:
        raise RuntimeError("pattern completion total disagrees with per-pattern counters")
    return sorted(result, key=lambda record: record["id"]), measured_completions


def _aggregate_patterns(episodes: list[dict[str, Any]]) -> tuple[
    list[dict[str, int]] | None, dict[str, int] | None,
]:
    if any(episode["pattern_metrics"] is None for episode in episodes):
        return None, None
    counters: dict[int, dict[str, int]] = {}
    for episode in episodes:
        for record in episode["pattern_metrics"]:
            total = counters.setdefault(record["id"], {
                "id": record["id"], "encounters": 0, "exposure_frames": 0, "completions": 0,
            })
            for name in ("encounters", "exposure_frames", "completions"):
                total[name] += record[name]
    metrics = [counters[identity] for identity in sorted(counters)]
    totals = {
        name: sum(record[name] for record in metrics)
        for name in ("encounters", "exposure_frames", "completions")
    }
    return metrics, totals


def evaluate(
    *, policy: str = "neutral", seeds: Iterable[int] = (42,),
    max_frames: int = MAX_EPISODE_FRAMES,
    environment_factory: Callable[..., Any] | None = None,
    clock: Callable[[], float] = time.perf_counter,
    policy_factory: Callable[[int], Any] | None = None,
    learned_policy: bool = False,
    max_seconds: float | None = None,
) -> dict[str, Any]:
    """Evaluate one baseline. Tests may supply a small fake environment factory."""
    selected = unique_seeds(seeds)
    if isinstance(max_frames, bool) or not isinstance(max_frames, int) or not 1 <= max_frames <= MAX_EPISODE_FRAMES:
        raise ValueError(f"max_frames must be between 1 and {MAX_EPISODE_FRAMES}")
    if not isinstance(learned_policy, bool):
        raise ValueError("learned_policy must be a boolean")
    if max_seconds is not None:
        if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)):
            raise ValueError("max_seconds must be a finite positive number")
        try:
            valid_seconds = math.isfinite(max_seconds) and max_seconds > 0
        except OverflowError:
            valid_seconds = False
        if not valid_seconds:
            raise ValueError("max_seconds must be a finite positive number")
    if policy_factory is None:
        make_policy(policy)  # Validate before importing or creating the native environment.
        if learned_policy:
            raise ValueError("learned evaluation requires a policy factory")
    elif not callable(policy_factory) or not isinstance(policy, str) or not policy:
        raise ValueError("custom evaluation requires a callable factory and a policy name")
    if environment_factory is None:
        from .env import NativeEnvironment

        environment_factory = NativeEnvironment

    episodes = []
    provenance = None
    total_native_frames = 0
    started = clock()

    def check_time_budget() -> None:
        if max_seconds is not None and clock() - started >= max_seconds:
            raise EvaluationTimeout("evaluation exceeded max_seconds wall-time budget")

    for seed in selected:
        check_time_budget()
        baseline = make_policy(policy, seed) if policy_factory is None else policy_factory(seed)
        episode_started = clock()
        with environment_factory(seed=seed, max_episode_frames=max_frames, action_repeat=1) as env:
            observation = env.reset(seed=seed)
            initial_provenance = observation["info"]["provenance"]
            if provenance is None:
                provenance = initial_provenance
            elif initial_provenance != provenance:
                raise ValueError("native provenance changed between evaluation episodes")
            return_sum = 0.0
            episode_native_frames = 0
            decisions = 0
            while not (observation["info"]["terminated"] or observation["info"]["truncated"]):
                check_time_budget()
                if decisions >= max_frames:
                    raise RuntimeError("environment did not finish within the configured frame budget")
                observation = env.step(baseline.act(observation))
                check_time_budget()
                elapsed = observation["info"]["elapsed_native_frames"]
                if isinstance(elapsed, bool) or not isinstance(elapsed, int) or elapsed != 1:
                    raise RuntimeError("baseline evaluation requires exactly one native frame per decision")
                episode_native_frames += elapsed
                if episode_native_frames > max_frames:
                    raise RuntimeError("environment exceeded the configured frame budget")
                decisions += 1
                reward = float(observation["reward_sum"])
                if not math.isfinite(reward) or reward not in (0.0, 1.0):
                    raise RuntimeError("unexpected native survival reward")
                return_sum += reward

            info = observation["info"]
            if info["terminated"] and info["truncated"]:
                raise RuntimeError("death must take precedence over truncation")
            if info["episode_frames"] != episode_native_frames:
                raise RuntimeError("episode frame count disagrees with step results")
            pattern_metrics, pattern_completions = _pattern_metrics(info, episode_native_frames)
            elapsed_seconds = max(0.0, clock() - episode_started)
            episodes.append({
                "seed": seed,
                "native_frames": episode_native_frames,
                "survival_frames": int(return_sum),
                "return": return_sum,
                "score": info["score"],
                "terminated": info["terminated"],
                "truncated": info["truncated"],
                "pattern_completions": pattern_completions,
                "pattern_metrics": pattern_metrics,
                "final_frame": info["frame"],
                "state_hash": info["state_hash"],
                "pixel_hash": info["pixel_hash"],
                "elapsed_seconds": elapsed_seconds,
                "native_frames_per_second": episode_native_frames / elapsed_seconds if elapsed_seconds else None,
            })
            total_native_frames += episode_native_frames

    check_time_budget()
    elapsed_seconds = max(0.0, clock() - started)
    survival = [episode["survival_frames"] for episode in episodes]
    pattern_counts = [episode["pattern_completions"] for episode in episodes]
    completed_pattern_episodes = (
        sum(count > 0 for count in pattern_counts)
        if all(count is not None for count in pattern_counts) else None
    )
    pattern_metrics, pattern_totals = _aggregate_patterns(episodes)
    return {
        "schema_version": 1,
        "policy": policy,
        "learned_policy": learned_policy,
        "action_names": list(ACTION_NAMES),
        "action_masks": list(ACTION_MASKS),
        "action_repeat": 1,
        "max_episode_frames": max_frames,
        "provenance": provenance,
        "episodes": episodes,
        "summary": {
            "episodes": len(episodes),
            "mean_survival_frames": statistics.mean(survival),
            "median_survival_frames": statistics.median(survival),
            "tenth_percentile_survival_frames": _percentile(survival, 0.1),
            "mean_score": statistics.mean(episode["score"] for episode in episodes),
            "death_rate": statistics.mean(int(episode["terminated"]) for episode in episodes),
            "cap_hit_rate": statistics.mean(int(episode["truncated"]) for episode in episodes),
            "completed_pattern_episodes": completed_pattern_episodes,
            "pattern_metrics": pattern_metrics,
            "pattern_totals": pattern_totals,
            "native_frames": total_native_frames,
            "elapsed_seconds": elapsed_seconds,
            "native_frames_per_second": total_native_frames / elapsed_seconds if elapsed_seconds else None,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", choices=("neutral", "random", "avoidance"), default="neutral")
    parser.add_argument("--seeds", type=parse_seeds, default=[42], help="comma-separated unsigned 32-bit seeds")
    parser.add_argument("--max-frames", type=int, default=MAX_EPISODE_FRAMES)
    parser.add_argument("--output", type=Path, help="write JSON to this path instead of stdout")
    arguments = parser.parse_args(argv)
    try:
        report = evaluate(policy=arguments.policy, seeds=arguments.seeds, max_frames=arguments.max_frames)
    except (ValueError, RuntimeError) as error:
        parser.error(str(error))
    body = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if arguments.output is None:
        print(body, end="")
    else:
        arguments.output.write_text(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
