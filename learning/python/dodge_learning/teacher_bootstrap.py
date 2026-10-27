"""Bounded heuristic warmup for the privileged entity-transformer teacher.

The heuristic controls native episodes and labels the state before each action.
Classification updates consume only full privileged records. No image dataset,
vision policy, or qualification claim is produced. PPO fine-tuning remains a
separate, explicitly recorded stage.
"""

from __future__ import annotations

import argparse
from collections import deque
import copy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from typing import Any, Callable

import numpy as np
import torch
from torch.nn import functional as F

from .entity_teacher import EntityActorCritic, EntityTeacherConfig, batch_entities, encode_entities
from .policies import ACTION_NAMES, AvoidancePolicy
from .seeds import seed_manifest

FROZEN_TRAIN_SEEDS = tuple(seed_manifest()["train"])
CLASS_WEIGHT_CAP = 4.0
CLASS_BALANCE_MODES = ("none", "sqrt_inverse_frequency")


@dataclass(frozen=True)
class BootstrapConfig:
    total_frames: int = 10_000
    max_seconds: float = 600.0
    max_episode_frames: int = 1_000
    batch_size: int = 64
    replay_capacity: int = 2_048
    class_balance: str = "none"
    attention_prior: float = 1.0
    relative_geometry: bool = False
    kind_embedding_scale: float = 1.0
    epochs: int = 2
    learning_rate: float = 3e-4
    seed: int = 7
    torch_threads: int = 1
    train_seeds: tuple[int, ...] = FROZEN_TRAIN_SEEDS

    def __post_init__(self) -> None:
        EntityTeacherConfig(
            attention_prior=self.attention_prior,
            relative_geometry=self.relative_geometry,
            kind_embedding_scale=self.kind_embedding_scale,
        )
        for name, lower, upper in (
            ("total_frames", 1, 10_000), ("max_episode_frames", 1, 1_000),
            ("batch_size", 1, 256), ("epochs", 1, 8), ("seed", 0, 0xFFFF_FFFF),
            ("replay_capacity", 1, 4_096),
        ):
            value = getattr(self, name)
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"{name} must be an integer from {lower} to {upper}")
        if self.replay_capacity < self.batch_size:
            raise ValueError("replay_capacity must be at least batch_size")
        if self.class_balance not in CLASS_BALANCE_MODES:
            raise ValueError("class_balance must be none or sqrt_inverse_frequency")
        for name, upper in (("max_seconds", 600), ("learning_rate", 1)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= upper:
                raise ValueError(f"{name} must be finite and in (0, {upper}]")
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite and in (0, {upper}]")
        if type(self.torch_threads) is not int or self.torch_threads != 1:
            raise ValueError("bootstrap uses exactly one PyTorch CPU thread")
        if (
            not isinstance(self.train_seeds, (tuple, list))
            or any(type(seed) is not int for seed in self.train_seeds)
            or tuple(self.train_seeds) != FROZEN_TRAIN_SEEDS
        ):
            raise ValueError("train_seeds must be the complete frozen training sequence")
        object.__setattr__(self, "train_seeds", tuple(self.train_seeds))


@dataclass
class BootstrapResult:
    model: EntityActorCritic
    optimizer_state: dict[str, Any]
    metrics: dict[str, Any]
    config: BootstrapConfig


def _class_weights(counts: np.ndarray, mode: str) -> torch.Tensor | None:
    """Return replay-frequency weights; absent actions never divide by zero."""
    if mode not in CLASS_BALANCE_MODES:
        raise ValueError("class_balance must be none or sqrt_inverse_frequency")
    if not isinstance(counts, np.ndarray) or counts.shape != (len(ACTION_NAMES),) or counts.dtype.kind not in "iu":
        raise ValueError("class counts must be a nine-element integer array")
    if bool((counts < 0).any()):
        raise ValueError("class counts must be nonnegative")
    if mode == "none":
        return None
    weights = np.ones(len(ACTION_NAMES), dtype=np.float32)
    present = counts > 0
    if bool(present.any()):
        weights[present] = np.minimum(CLASS_WEIGHT_CAP, np.sqrt(counts.max() / counts[present]))
    return torch.from_numpy(weights)


def _encoded(observation: dict[str, Any], provenance: dict[str, Any] | None):
    actual = observation["info"]["provenance"]
    for key, expected in (("feature_schema_version", 2), ("privileged_schema_version", 1)):
        if type(actual.get(key)) is not int or actual[key] != expected:
            raise RuntimeError(f"bootstrap requires native {key}={expected}")
    if provenance is not None and actual != provenance:
        raise RuntimeError("native provenance changed during teacher bootstrap")
    return encode_entities(observation["privileged_state"])


def _pattern_rows(info: dict[str, Any]) -> list[dict[str, int]]:
    rows = info.get("pattern_metrics", [])
    if not isinstance(rows, list):
        raise RuntimeError("native pattern metrics must be a list")
    result = []
    seen = set()
    for row in rows:
        keys = ("id", "encounters", "exposure_frames", "completions")
        if not isinstance(row, dict) or any(type(row.get(key)) is not int or row[key] < 0 for key in keys):
            raise RuntimeError("native pattern metrics must contain nonnegative integer counters")
        if row["id"] in seen:
            raise RuntimeError("native pattern metrics must not duplicate pattern IDs")
        seen.add(row["id"])
        result.append({key: row[key] for key in keys})
    return result


def train_bootstrap(
    config: BootstrapConfig, *, model: EntityActorCritic | None = None,
    environment_factory: Callable[..., Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> BootstrapResult:
    """Warm up a teacher within frame/time caps and bounded in-memory replay.

    ``samples_optimized`` counts epoch visits; ``unique_samples_optimized``
    counts distinct executed native frames. Accuracy is measured on optimization
    batches before each update, not on held-out episodes. The value head is
    unchanged and re-enabled before the returned model can enter PPO.
    Epoch zero visits every new batch row once. Later epochs sample uniformly
    without replacement from the bounded replay, including earlier batches.
    """
    if not isinstance(config, BootstrapConfig):
        raise TypeError("config must be a BootstrapConfig")
    if model is not None and not isinstance(model, EntityActorCritic):
        raise TypeError("model must be an EntityActorCritic")
    representation = {
        "attention_prior": config.attention_prior,
        "relative_geometry": config.relative_geometry,
        "kind_embedding_scale": config.kind_embedding_scale,
    }
    if model is not None and any(getattr(model.config, key) != value for key, value in representation.items()):
        raise ValueError("supplied model representation settings must match the bootstrap configuration")
    started = time.monotonic()
    previous_threads = torch.get_num_threads()
    torch.set_num_threads(config.torch_threads)
    value_flags = None
    try:
        # This fork covers dropout as well as initialization. Caller RNG state
        # survives even if a caller supplies a teacher with nonzero dropout.
        with torch.random.fork_rng(devices=[]):
            torch.random.default_generator.manual_seed(config.seed)
            if model is None:
                model = EntityActorCritic(EntityTeacherConfig(**representation))
            all_parameters = list(model.parameters())
            if any(value.device.type != "cpu" for value in [*all_parameters, *model.buffers()]):
                raise ValueError("bootstrap teacher parameters and buffers must be on CPU")
            if any(not bool(torch.isfinite(value).all()) for value in all_parameters):
                raise ValueError("bootstrap teacher parameters must be finite")
            value_flags = [parameter.requires_grad for parameter in model.value.parameters()]
            model.value.requires_grad_(False)
            parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
            if not parameters:
                raise ValueError("bootstrap teacher must have trainable policy parameters")
            optimizer = torch.optim.Adam(parameters, lr=config.learning_rate)
            permutation_rng = np.random.default_rng(config.seed)
            model.train()
            metrics: dict[str, Any] = {
                "method": "heuristic_bootstrap", "architecture": "entity_transformer",
                "model_config": asdict(model.config),
                "label_policy": "avoidance", "device": "cpu", "frames_collected": 0,
                "heuristic_queries": 0, "updates": 0, "optimizer_steps": 0,
                "samples_optimized": 0, "unique_samples_optimized": 0,
                "replay_capacity": config.replay_capacity, "replay_rows": 0,
                "replay_samples_optimized": 0,
                "class_balance": config.class_balance, "class_weight_cap": CLASS_WEIGHT_CAP,
                "class_weights": [1.0] * len(ACTION_NAMES),
                "unoptimized_frames": 0, "episodes_started": 0, "episodes_completed": 0,
                "terminal_episodes": 0, "truncated_episodes": 0,
                "completed_pattern_episodes": 0, "pattern_completions": 0,
                "partial_episode_frames": 0, "partial_episode_return": 0.0,
                "partial_episode_pattern_metrics": [], "episodes": [],
                "action_histogram": {name: 0 for name in ACTION_NAMES},
                "classification_loss": None, "training_accuracy": None,
                "grad_norm": None, "stop_reason": "frame_budget", "elapsed_seconds": 0.0,
                "provenance": None, "teacher_qualified": False,
            }
            weighted_loss = 0.0
            correct = 0

            def expired() -> bool:
                return time.monotonic() - started >= config.max_seconds

            if environment_factory is None:
                from .env import NativeEnvironment

                environment_factory = NativeEnvironment
            if expired():
                metrics["stop_reason"] = "time_budget"
                metrics["elapsed_seconds"] = max(0.0, time.monotonic() - started)
                return BootstrapResult(model, optimizer.state_dict(), metrics, config)
            policy = AvoidancePolicy()
            states, labels = [], []
            replay = deque(maxlen=config.replay_capacity)
            replay_counts = np.zeros(len(ACTION_NAMES), dtype=np.int64)

            def optimize() -> None:
                nonlocal weighted_loss, correct
                count = len(states)
                if not count:
                    return
                class_weights = _class_weights(replay_counts, config.class_balance)
                metrics["class_weights"] = class_weights.tolist() if class_weights is not None else [1.0] * len(ACTION_NAMES)
                touched = False
                for epoch in range(config.epochs):
                    if expired():
                        metrics["stop_reason"] = "time_budget"
                        break
                    if epoch == 0:
                        order = permutation_rng.permutation(count)
                        selected = [(states[int(index)], labels[int(index)]) for index in order]
                    else:
                        order = permutation_rng.choice(len(replay), size=count, replace=False)
                        selected = [replay[int(index)] for index in order]
                    batch = batch_entities([state for state, _ in selected])
                    targets = torch.tensor([label for _, label in selected], dtype=torch.long)
                    logits, _ = model(batch)
                    if logits.shape != (count, 9) or not bool(torch.isfinite(logits).all()):
                        raise RuntimeError("bootstrap teacher produced invalid nine-action logits")
                    loss = F.cross_entropy(logits, targets, weight=class_weights)
                    if not bool(torch.isfinite(loss)):
                        raise RuntimeError("bootstrap classification loss is nonfinite")
                    optimizer.zero_grad(set_to_none=True)
                    loss.backward()
                    norm = torch.nn.utils.clip_grad_norm_(parameters, 0.5, error_if_nonfinite=True)
                    if expired():
                        optimizer.zero_grad(set_to_none=True)
                        metrics["stop_reason"] = "time_budget"
                        break
                    optimizer.step()
                    if any(not bool(torch.isfinite(parameter).all()) for parameter in parameters):
                        raise RuntimeError("bootstrap produced nonfinite teacher weights")
                    weighted_loss += float(loss.detach()) * count
                    correct += int((logits.detach().argmax(dim=-1) == targets).sum())
                    metrics["optimizer_steps"] += 1
                    metrics["samples_optimized"] += count
                    if epoch:
                        metrics["replay_samples_optimized"] += count
                    metrics["grad_norm"] = float(norm.detach())
                    if not touched:
                        metrics["unique_samples_optimized"] += count
                        touched = True
                if touched:
                    metrics["updates"] += 1
                    metrics["classification_loss"] = weighted_loss / metrics["samples_optimized"]
                    metrics["training_accuracy"] = correct / metrics["samples_optimized"]
                metrics["unoptimized_frames"] = metrics["frames_collected"] - metrics["unique_samples_optimized"]
                metrics["elapsed_seconds"] = max(0.0, time.monotonic() - started)
                if touched and progress_callback is not None:
                    progress_callback(copy.deepcopy(metrics))
                states.clear()
                labels.clear()

            with environment_factory(
                seed=config.train_seeds[0], max_episode_frames=config.max_episode_frames,
                action_repeat=1, discount=0.99,
            ) as environment:
                observation = None
                need_reset = True
                seed_index = 0
                episode_seed = config.train_seeds[0]
                cached_encoded = None
                while metrics["frames_collected"] < config.total_frames:
                    if expired():
                        metrics["stop_reason"] = "time_budget"
                        break
                    if need_reset:
                        episode_seed = config.train_seeds[seed_index % len(config.train_seeds)]
                        observation = environment.reset(seed=episode_seed)
                        seed_index += 1
                        metrics["episodes_started"] += 1
                        if observation["info"]["terminated"] or observation["info"]["truncated"]:
                            raise RuntimeError("fresh bootstrap reset returned a finished episode")
                        need_reset = False
                        cached_encoded = None
                    encoded = cached_encoded if cached_encoded is not None else _encoded(observation, metrics["provenance"])
                    if metrics["provenance"] is None:
                        metrics["provenance"] = copy.deepcopy(observation["info"]["provenance"])
                    # Both the privileged features and heuristic label belong
                    # to the observation before the following native step.
                    label = policy.act(observation)
                    metrics["heuristic_queries"] += 1
                    if type(label) is not int or not 0 <= label < len(ACTION_NAMES):
                        raise RuntimeError("heuristic produced an invalid native action")
                    if expired():
                        metrics["stop_reason"] = "time_budget"
                        break
                    following = environment.step(label)
                    info = following["info"]
                    if type(info["elapsed_native_frames"]) is not int or info["elapsed_native_frames"] != 1:
                        raise RuntimeError("bootstrap requires one native frame per decision")
                    terminated, truncated = info["terminated"], info["truncated"]
                    if type(terminated) is not bool or type(truncated) is not bool or (terminated and truncated):
                        raise RuntimeError("native bootstrap episode flags are invalid")
                    following_encoded = _encoded(following, metrics["provenance"])
                    reward = following["reward_sum"]
                    if isinstance(reward, bool) or not isinstance(reward, (int, float)) or reward not in (0., 1.):
                        raise RuntimeError("bootstrap requires native raw survival rewards")
                    states.append(encoded)
                    labels.append(label)
                    if len(replay) == config.replay_capacity:
                        replay_counts[replay[0][1]] -= 1
                    replay.append((encoded, label))
                    replay_counts[label] += 1
                    metrics["replay_rows"] = len(replay)
                    metrics["frames_collected"] += 1
                    metrics["partial_episode_frames"] += 1
                    metrics["partial_episode_return"] += float(reward)
                    metrics["action_histogram"][ACTION_NAMES[label]] += 1
                    if info["episode_frames"] != metrics["partial_episode_frames"]:
                        raise RuntimeError("native frame count disagrees with bootstrap accounting")
                    if info["episode_frames"] >= config.max_episode_frames and not (terminated or truncated):
                        raise RuntimeError("native bootstrap episode exceeded its frame limit")
                    rows = _pattern_rows(info)
                    metrics["partial_episode_pattern_metrics"] = rows
                    observation = following
                    cached_encoded = following_encoded
                    if terminated or truncated:
                        completions = info.get("pattern_completions", 0)
                        if type(completions) is not int or not 0 <= completions <= info["episode_frames"]:
                            raise RuntimeError("native pattern completion count is invalid")
                        metrics["episodes"].append({
                            "seed": episode_seed, "native_frames": info["episode_frames"],
                            "survival_return": metrics["partial_episode_return"],
                            "terminated": terminated, "truncated": truncated,
                            "pattern_completions": completions, "pattern_metrics": rows,
                        })
                        metrics["episodes_completed"] += 1
                        metrics["terminal_episodes"] += int(terminated)
                        metrics["truncated_episodes"] += int(truncated)
                        metrics["completed_pattern_episodes"] += int(completions > 0)
                        metrics["pattern_completions"] += completions
                        metrics["partial_episode_frames"] = 0
                        metrics["partial_episode_return"] = 0.0
                        metrics["partial_episode_pattern_metrics"] = []
                        need_reset = True
                    if len(states) >= config.batch_size:
                        optimize()
                    if metrics["stop_reason"] == "time_budget":
                        break
                optimize()
            metrics["unoptimized_frames"] = metrics["frames_collected"] - metrics["unique_samples_optimized"]
            metrics["elapsed_seconds"] = max(0.0, time.monotonic() - started)
            return BootstrapResult(model, optimizer.state_dict(), metrics, config)
    finally:
        if model is not None and value_flags is not None:
            for parameter, required in zip(model.value.parameters(), value_flags):
                parameter.requires_grad_(required)
            model.eval()
        torch.set_num_threads(previous_threads)


def run_training(arguments: argparse.Namespace) -> dict[str, Any]:
    from .checkpoints import save_teacher_checkpoint
    from .teacher_run import source_manifest, write_json

    config = BootstrapConfig(
        total_frames=arguments.frames, max_seconds=arguments.max_seconds,
        max_episode_frames=arguments.episode_frames, batch_size=arguments.batch_size,
        replay_capacity=arguments.replay_capacity, class_balance=arguments.class_balance,
        attention_prior=getattr(arguments, "attention_prior", 1.0),
        relative_geometry=getattr(arguments, "relative_geometry", False),
        kind_embedding_scale=getattr(arguments, "kind_embedding_scale", 1.0),
        epochs=arguments.epochs, seed=arguments.seed,
    )
    output = arguments.output_dir.expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    try:
        sources = source_manifest()
        manifest = seed_manifest()
        write_json(output / "config.json", asdict(config))
        write_json(output / "source.json", sources)
        write_json(output / "seeds.json", manifest)

        def progress(metrics: dict[str, Any]) -> None:
            with (output / "progress.jsonl").open("a") as stream:
                stream.write(json.dumps(metrics, sort_keys=True, allow_nan=False) + "\n")

        result = train_bootstrap(config, progress_callback=progress)
        if result.metrics["unique_samples_optimized"] == 0:
            raise RuntimeError("bootstrap exhausted its budget without an optimized sample")
        checkpoint = save_teacher_checkpoint(
            output / "teacher.pt", result, seed_manifest=manifest, source_manifest=sources,
        )
        report = {
            "schema_version": 1, "kind": "entity_teacher_heuristic_bootstrap",
            "method": "heuristic_bootstrap", "started_at_utc": started,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "checkpoint": checkpoint, "metrics": result.metrics,
            "qualification": "not_evaluated", "teacher_qualified": False,
        }
        write_json(output / "run.json", report)
        return report
    except Exception as error:
        write_json(output / "failure.json", {
            "started_at_utc": started, "error_type": type(error).__name__,
            "error": str(error), "teacher_qualified": False,
        })
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=10_000)
    parser.add_argument("--max-seconds", type=float, default=600)
    parser.add_argument("--episode-frames", type=int, default=1_000)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--replay-capacity", type=int, default=2_048)
    parser.add_argument("--class-balance", choices=CLASS_BALANCE_MODES, default="none")
    parser.add_argument("--attention-prior", type=float, default=1.0)
    parser.add_argument("--relative-geometry", action="store_true")
    parser.add_argument("--kind-embedding-scale", type=float, default=1.0)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--seed", type=int, default=7)
    arguments = parser.parse_args(argv)
    try:
        report = run_training(arguments)
    except (ValueError, RuntimeError, TypeError, OSError, ImportError) as error:
        parser.exit(2, f"teacher bootstrap failed: {error}\n")
    print(json.dumps({"output_dir": str(arguments.output_dir), "metrics": report["metrics"],
                      "qualification": report["qualification"]}, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
