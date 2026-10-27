"""Bounded checkpoint evaluation and a separate held-out teacher qualification gate."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import platform
import statistics
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .evaluate import EvaluationTimeout, MAX_EPISODE_FRAMES, evaluate
from .policies import ACTION_MASKS, ACTION_NAMES
from .seeds import manifest_hash, seed_manifest, validate_manifest
from .teacher import (
    REQUIRED_NATIVE_FEATURE_SCHEMA_VERSION,
    StateActorCritic,
    batch_states,
    encode_state,
)
from .entity_teacher import EntityActorCritic, batch_entities, encode_entities, REQUIRED_PRIVILEGED_SCHEMA_VERSION

BASELINE_NAMES = ("neutral", "random", "avoidance")
QUALIFICATION_SEEDS = 100
MIN_COMPLETED_PATTERN_EPISODES = 25
BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_SEED = 20261023
PROVENANCE_KEYS = (
    "adapter_version", "feature_schema_version", "core_schema_version",
    "snapshot_wire_version", "cartridge_sha256", "game_revision", "core_source_dirty",
    "action_names", "action_masks", "action_repeat", "difficulty", "patterns_enabled",
    "powerups_enabled", "theme_background", "theme_shadow",
)
CONFIG_KEYS = (
    "difficulty", "patterns_enabled", "powerups_enabled", "theme_background", "theme_shadow",
)
FROZEN_BENCHMARK_CONFIG = {
    "difficulty": 2,
    "patterns_enabled": True,
    "powerups_enabled": True,
    "theme_background": 12,
    "theme_shadow": 1,
}
ALLOWED_PROVENANCE_DIFFERENCES = ("max_episode_frames", "discount")
SOURCE_IDENTITY_KEYS = (
    "native_extension_sha256",
    "python/dodge_learning/teacher.py",
    "python/dodge_learning/env.py",
    "python/dodge_learning/entity_teacher.py",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _require_frozen_recipe(manifest: dict[str, Any]) -> None:
    if manifest_hash(manifest) != manifest_hash(seed_manifest()):
        raise ValueError("formal qualification requires the exact frozen seed recipe across all four splits")


def _require_default_benchmark(provenance: Mapping[str, Any]) -> None:
    for key, expected in FROZEN_BENCHMARK_CONFIG.items():
        actual = provenance.get(key)
        if type(actual) is not type(expected) or actual != expected:
            raise ValueError(f"formal qualification requires default benchmark {key}={expected!r}")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _runtime_source_identity() -> dict[str, str]:
    modules = (
        (SOURCE_IDENTITY_KEYS[0], "dodge_learning._native"),
        (SOURCE_IDENTITY_KEYS[1], "dodge_learning.teacher"),
        (SOURCE_IDENTITY_KEYS[2], "dodge_learning.env"),
        (SOURCE_IDENTITY_KEYS[3], "dodge_learning.entity_teacher"),
    )
    return {
        key: hashlib.sha256(Path(importlib.import_module(module).__file__).read_bytes()).hexdigest()
        for key, module in modules
    }


def _verify_source_identity(source_manifest: Any) -> tuple[dict[str, str], bool]:
    """Reject changed recorded artifacts; missing fingerprints remain diagnostic evidence."""

    if not isinstance(source_manifest, Mapping):
        raise ValueError("checkpoint source_manifest must be a mapping")
    files = source_manifest.get("files", {})
    if not isinstance(files, Mapping):
        raise ValueError("checkpoint source_manifest.files must be a mapping")
    actual = _runtime_source_identity()
    expected = {
        SOURCE_IDENTITY_KEYS[0]: source_manifest.get(SOURCE_IDENTITY_KEYS[0]),
        SOURCE_IDENTITY_KEYS[1]: files.get(SOURCE_IDENTITY_KEYS[1]),
        SOURCE_IDENTITY_KEYS[2]: files.get(SOURCE_IDENTITY_KEYS[2]),
        SOURCE_IDENTITY_KEYS[3]: files.get(SOURCE_IDENTITY_KEYS[3]),
    }
    for key, fingerprint in expected.items():
        present = key in source_manifest if key == SOURCE_IDENTITY_KEYS[0] else key in files
        if present:
            if not _is_sha256(fingerprint):
                raise ValueError(f"checkpoint source fingerprint is invalid: {key}")
            if fingerprint != actual[key]:
                raise ValueError(f"checkpoint/runtime source fingerprint mismatch: {key}")
    return actual, all(expected[key] is not None for key in SOURCE_IDENTITY_KEYS)


def _qualified_source_identity(report: Mapping[str, Any]) -> Mapping[str, str]:
    identity = report.get("source_identity")
    if report.get("source_identity_verified") is not True:
        raise ValueError("qualification requires verified runtime source identity")
    if (
        not isinstance(identity, Mapping) or set(identity) != set(SOURCE_IDENTITY_KEYS)
        or not all(_is_sha256(identity[key]) for key in SOURCE_IDENTITY_KEYS)
    ):
        raise ValueError("qualification requires every runtime source fingerprint")
    return identity


def _validate_provenance(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(key not in value for key in PROVENANCE_KEYS):
        raise ValueError("evaluation requires complete native training provenance")
    if type(value["feature_schema_version"]) is not int or value["feature_schema_version"] != REQUIRED_NATIVE_FEATURE_SCHEMA_VERSION:
        raise ValueError("teacher evaluation requires native feature schema 2")
    if _canonical(value["action_names"]) != _canonical(list(ACTION_NAMES)) or _canonical(value["action_masks"]) != _canonical(list(ACTION_MASKS)):
        raise ValueError("teacher evaluation requires the declared nine-action order")
    if type(value["action_repeat"]) is not int or value["action_repeat"] != 1:
        raise ValueError("teacher evaluation requires the checkpoint's action repeat to be 1")
    _canonical(dict(value))
    return value


def _match_provenance(actual: Any, expected: Mapping[str, Any]) -> None:
    current = _validate_provenance(actual)
    for key in PROVENANCE_KEYS:
        if _canonical(current[key]) != _canonical(expected[key]):
            raise ValueError(f"checkpoint/native provenance mismatch: {key}")
    # Reject an unreviewed new provenance field rather than silently allowing
    # it to change. Caps and discount are the only permitted differences.
    extra_keys = (set(current) | set(expected)) - set(PROVENANCE_KEYS) - set(ALLOWED_PROVENANCE_DIFFERENCES)
    for key in extra_keys:
        if key not in current or key not in expected or _canonical(current[key]) != _canonical(expected[key]):
            raise ValueError(f"checkpoint/native provenance mismatch: {key}")


class GreedyTeacherPolicy:
    """CPU evaluation wrapper; only encoded actor features enter the model."""

    def __init__(
        self, model: StateActorCritic | EntityActorCritic, expected_provenance: Mapping[str, Any] | None = None,
    ) -> None:
        if not isinstance(model, (StateActorCritic, EntityActorCritic)):
            raise TypeError("model must be a supported teacher")
        self.model = model.cpu().eval()
        self.expected_provenance = (
            dict(_validate_provenance(expected_provenance))
            if expected_provenance is not None else None
        )

    def act(self, observation: Mapping[str, Any]) -> int:
        provenance = observation["info"]["provenance"]
        _validate_provenance(provenance)
        if self.expected_provenance is not None:
            _match_provenance(provenance, self.expected_provenance)
        if isinstance(self.model, EntityActorCritic):
            if type(provenance.get("privileged_schema_version")) is not int or provenance["privileged_schema_version"] != REQUIRED_PRIVILEGED_SCHEMA_VERSION:
                raise ValueError("entity teacher requires native privileged schema 1")
            encoded = encode_entities(observation["privileged_state"])
            batch = batch_entities([encoded], device="cpu")
        else:
            encoded = encode_state(observation["train_only_state"])
            batch = batch_states([encoded], device="cpu")
        with torch.no_grad():
            logits, _ = self.model(batch)
        if tuple(logits.shape) != (1, 9) or not bool(torch.isfinite(logits).all()):
            raise RuntimeError("teacher produced invalid nine-action logits")
        return int(logits.argmax(dim=-1).item())


def _smoke_qualification() -> dict[str, Any]:
    return {
        "status": "not_evaluated_smoke_only",
        "student_collection_allowed": False,
        "reason": "Smoke evaluation does not satisfy the 100-seed held-out qualification protocol.",
    }


def _report_values(report: Any, seeds: list[int], *, learned: bool) -> tuple[list[int], int | None]:
    if not isinstance(report, Mapping) or report.get("learned_policy") is not learned:
        raise ValueError("qualification requires a learned teacher and nonlearned baselines")
    _qualified_source_identity(report)
    if type(report.get("max_episode_frames")) is not int or report["max_episode_frames"] != MAX_EPISODE_FRAMES:
        raise ValueError("qualification requires an 18,000-native-frame episode cap")
    if type(report.get("action_repeat")) is not int or report["action_repeat"] != 1:
        raise ValueError("qualification requires action repeat 1")
    if _canonical(report.get("action_names")) != _canonical(list(ACTION_NAMES)) or _canonical(report.get("action_masks")) != _canonical(list(ACTION_MASKS)):
        raise ValueError("qualification action order does not match the native action contract")
    native_provenance = _validate_provenance(report.get("provenance"))
    _require_default_benchmark(native_provenance)
    if type(native_provenance.get("max_episode_frames")) is not int or native_provenance["max_episode_frames"] != MAX_EPISODE_FRAMES:
        raise ValueError("qualification native provenance must declare the 18,000-frame cap")
    episodes = report.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != QUALIFICATION_SEEDS:
        raise ValueError("qualification requires exactly 100 completed validation episodes")
    if any(not isinstance(episode, Mapping) for episode in episodes):
        raise ValueError("qualification episodes must be records")
    if any(type(episode.get("seed")) is not int for episode in episodes) or [episode["seed"] for episode in episodes] != seeds:
        raise ValueError("qualification episode seeds must exactly match the validation manifest")
    values = []
    completed_pattern_episodes = 0
    coverage_available = True
    for episode in episodes:
        native_frames = episode.get("native_frames")
        terminated, truncated = episode.get("terminated"), episode.get("truncated")
        if type(native_frames) is not int or not 1 <= native_frames <= MAX_EPISODE_FRAMES:
            raise ValueError("qualification native frames must be bounded positive integers")
        if type(terminated) is not bool or type(truncated) is not bool or terminated == truncated:
            raise ValueError("qualification requires completed episodes with exactly one end flag")
        if truncated and native_frames != MAX_EPISODE_FRAMES:
            raise ValueError("qualification truncation must occur at the declared episode cap")
        survival = episode.get("survival_frames")
        if type(survival) is not int or not 0 <= survival <= native_frames:
            raise ValueError("qualification survival must be a bounded integer native-frame count")
        values.append(survival)
        completions = episode.get("pattern_completions")
        if completions is None:
            coverage_available = False
        elif type(completions) is not int or not 0 <= completions <= MAX_EPISODE_FRAMES:
            raise ValueError("qualification pattern completions must be bounded integers")
        else:
            completed_pattern_episodes += completions > 0
    return values, completed_pattern_episodes if coverage_available else None


def qualify_teacher(
    teacher_report: Mapping[str, Any],
    baseline_reports: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Compare paired capped survival and require measured pattern completion.

    Malformed or mismatched campaigns raise an error. Valid campaigns return a
    performance pass/fail. Smoke evidence can never authorize student collection.
    """

    validate_manifest(manifest)
    if teacher_report.get("split") == "smoke":
        if teacher_report.get("learned_policy") is not True:
            raise ValueError("qualification requires a learned teacher")
        episodes = teacher_report.get("episodes", [])
        seeds = [episode.get("seed") for episode in episodes]
        if not seeds or any(type(seed) is not int for seed in seeds) or len(set(seeds)) != len(seeds) or any(seed not in manifest["smoke"] for seed in seeds):
            raise ValueError("smoke report must use distinct manifest smoke seeds")
        return _smoke_qualification()
    if teacher_report.get("split", "validation") != "validation":
        raise ValueError("only validation reports can qualify a teacher; final test seeds are reserved")
    _require_frozen_recipe(manifest)
    seeds = manifest["validation"]
    if len(seeds) != QUALIFICATION_SEEDS:
        raise ValueError("qualification manifest must contain exactly 100 validation seeds")
    teacher_values, coverage = _report_values(teacher_report, seeds, learned=True)
    source_identity = _qualified_source_identity(teacher_report)
    reports = list(baseline_reports.values()) if isinstance(baseline_reports, Mapping) else list(baseline_reports)
    if len(reports) != len(BASELINE_NAMES) or {report.get("policy") for report in reports} != set(BASELINE_NAMES):
        raise ValueError("qualification requires neutral, random, and avoidance baseline reports")
    candidates = []
    for report in reports:
        values, _ = _report_values(report, seeds, learned=False)
        if _canonical(report["provenance"]) != _canonical(teacher_report["provenance"]):
            raise ValueError("teacher and baseline qualification provenance/configuration must match")
        if _canonical(report["source_identity"]) != _canonical(source_identity):
            raise ValueError("teacher and baseline qualification source identity must match")
        if report.get("split", "validation") != "validation":
            raise ValueError("qualification baselines must use the validation split")
        candidates.append((statistics.mean(values), report["policy"], values))
    best_mean, best_name, baseline_values = max(candidates, key=lambda item: item[0])
    differences = np.asarray(teacher_values, dtype=np.float64) - np.asarray(baseline_values, dtype=np.float64)
    # This private generator neither consumes nor changes NumPy's global RNG.
    generator = np.random.default_rng(BOOTSTRAP_SEED)
    indexes = generator.integers(0, len(seeds), size=(BOOTSTRAP_SAMPLES, len(seeds)))
    samples = differences[indexes].mean(axis=1)
    lower, upper = (float(value) for value in np.quantile(samples, [0.025, 0.975]))
    improvement_pass = lower > 0
    coverage_pass = coverage is not None and coverage >= MIN_COMPLETED_PATTERN_EPISODES
    passed = improvement_pass and coverage_pass
    return {
        "status": "pass" if passed else "fail",
        "student_collection_allowed": passed,
        "source_identity": dict(source_identity),
        "source_identity_verified": True,
        "seed_manifest_hash": manifest_hash(manifest),
        "validation_episodes": len(seeds),
        "max_episode_frames": MAX_EPISODE_FRAMES,
        "best_baseline": best_name,
        "best_baseline_mean_capped_survival": best_mean,
        "teacher_mean_capped_survival": statistics.mean(teacher_values),
        "mean_paired_survival_improvement": float(differences.mean()),
        "paired_improvement_ci95": [lower, upper],
        "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "improvement_lower_bound_positive": improvement_pass,
        "completed_pattern_episodes": coverage,
        "required_completed_pattern_episodes": MIN_COMPLETED_PATTERN_EPISODES,
        "pattern_coverage_pass": coverage_pass,
    }


def evaluate_checkpoint(
    path: str | Path, *, split: str = "smoke", max_frames: int = 1000,
    seed_count: int | None = None, compare_baselines: bool = True,
    qualify: bool = False, max_seconds: float = 300,
) -> dict[str, Any]:
    """Evaluate a saved teacher without exposing final test seeds or writing files."""

    if split not in ("smoke", "validation"):
        raise ValueError("split must be smoke or validation; final test seeds remain reserved")
    if type(max_frames) is not int or not 1 <= max_frames <= MAX_EPISODE_FRAMES:
        raise ValueError("max_frames must be an integer from 1 to 18000")
    if seed_count is not None and (type(seed_count) is not int or not 1 <= seed_count <= QUALIFICATION_SEEDS):
        raise ValueError("seed_count must be a positive integer no greater than 100")
    if type(compare_baselines) is not bool or type(qualify) is not bool:
        raise ValueError("compare_baselines and qualify must be booleans")
    if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)):
        raise ValueError("max_seconds must be a finite positive number")
    try:
        valid_seconds = math.isfinite(max_seconds) and max_seconds > 0
    except OverflowError:
        valid_seconds = False
    if not valid_seconds:
        raise ValueError("max_seconds must be a finite positive number")
    if qualify and (split != "validation" or max_frames != MAX_EPISODE_FRAMES or seed_count not in (None, QUALIFICATION_SEEDS) or not compare_baselines):
        raise ValueError("qualification requires all 100 validation seeds, cap 18000, and all baselines")
    started = time.perf_counter()

    def remaining_seconds() -> float:
        remaining = max_seconds - (time.perf_counter() - started)
        if remaining <= 0:
            raise EvaluationTimeout("checkpoint evaluation exceeded its shared wall-time budget")
        return remaining

    from .checkpoints import load_teacher_checkpoint
    from .env import NativeEnvironment

    loaded = load_teacher_checkpoint(path)
    metadata = loaded.metadata
    manifest = metadata["seed_manifest"]
    validate_manifest(manifest)
    seed_hash = manifest_hash(manifest)
    if metadata.get("seed_manifest_hash") != seed_hash:
        raise ValueError("checkpoint seed manifest hash does not match its declared splits")
    if qualify:
        _require_frozen_recipe(manifest)
    training_provenance = dict(_validate_provenance(metadata["metrics"]["provenance"]))
    if qualify:
        _require_default_benchmark(training_provenance)
    source_identity, source_identity_verified = _verify_source_identity(metadata["source_manifest"])
    if qualify and not source_identity_verified:
        raise ValueError("qualification requires checkpoint fingerprints for the native extension, teacher, and environment")
    runtime = {
        "python_version": platform.python_version(),
        "torch_version": str(torch.__version__),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "torch_threads": torch.get_num_threads(),
    }
    selected = list(manifest[split])
    if seed_count is not None:
        if seed_count > len(selected):
            raise ValueError("seed_count exceeds the selected manifest split")
        selected = selected[:seed_count]
    if qualify and len(selected) != QUALIFICATION_SEEDS:
        raise ValueError("qualification requires exactly 100 manifest validation seeds")
    configuration = {key: training_provenance[key] for key in CONFIG_KEYS}

    class CheckedEnvironment:
        def __init__(self, **kwargs: Any) -> None:
            self.inner = NativeEnvironment(**kwargs, **configuration)

        def __enter__(self) -> CheckedEnvironment:
            self.inner.__enter__()
            return self

        def __exit__(self, *args: Any) -> None:
            self.inner.__exit__(*args)

        def checked(self, observation: dict[str, Any]) -> dict[str, Any]:
            _match_provenance(observation["info"]["provenance"], training_provenance)
            return observation

        def reset(self, **kwargs: Any) -> dict[str, Any]:
            return self.checked(self.inner.reset(**kwargs))

        def step(self, action: int) -> dict[str, Any]:
            return self.checked(self.inner.step(action))

    teacher_policy = GreedyTeacherPolicy(loaded.model, training_provenance)
    teacher_report = evaluate(
        policy="entity_transformer_teacher" if isinstance(loaded.model, EntityActorCritic) else "legacy_mlp_teacher", seeds=selected, max_frames=max_frames,
        environment_factory=CheckedEnvironment, policy_factory=lambda _: teacher_policy,
        learned_policy=True, max_seconds=remaining_seconds(), clock=time.perf_counter,
    )
    teacher_report["split"] = split
    teacher_report["seed_manifest_hash"] = seed_hash
    teacher_report["source_identity"] = dict(source_identity)
    teacher_report["source_identity_verified"] = source_identity_verified
    teacher_report["summary"]["runtime"] = dict(runtime)
    baseline_reports = []
    if compare_baselines:
        for name in BASELINE_NAMES:
            report = evaluate(
                policy=name, seeds=selected, max_frames=max_frames,
                environment_factory=CheckedEnvironment,
                max_seconds=remaining_seconds(), clock=time.perf_counter,
            )
            report["split"] = split
            report["seed_manifest_hash"] = seed_hash
            report["source_identity"] = dict(source_identity)
            report["source_identity_verified"] = source_identity_verified
            report["summary"]["runtime"] = dict(runtime)
            baseline_reports.append(report)
    qualification = qualify_teacher(teacher_report, baseline_reports, manifest) if qualify else _smoke_qualification()
    remaining_seconds()
    result = {
        "schema_version": 1,
        "checkpoint": {"path": str(path), "sha256": loaded.sha256, "seed_manifest_hash": seed_hash},
        "source_identity": source_identity,
        "source_identity_verified": source_identity_verified,
        "runtime": runtime,
        "split": split,
        "seeds": selected,
        "max_episode_frames": max_frames,
        "evaluation_config": configuration,
        "allowed_provenance_differences": list(ALLOWED_PROVENANCE_DIFFERENCES),
        "teacher": teacher_report,
        "baselines": baseline_reports,
        "qualification": qualification,
        "elapsed_seconds": max(0.0, time.perf_counter() - started),
    }
    _canonical(result)
    return result
