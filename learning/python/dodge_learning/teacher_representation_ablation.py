"""Fixed-data, teacher-only tests of entity geometry and attention routing.

All arms use the same privileged records, labels, initialization seed, and
minibatch order. The held-out smoke records never enter optimization. These
supervised diagnostics are prerequisites to further experiments, not a game
qualification result. No images or visual-policy modules are used.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import resource
import time
from typing import Any, Callable

import numpy as np
import torch
from torch.nn import functional as F

from .entity_teacher import EncodedEntities, EntityActorCritic, EntityTeacherConfig, batch_entities, encode_entities
from .policies import ACTION_NAMES, AvoidancePolicy
from .seeds import seed_manifest

FROZEN_TRAIN_SEEDS = tuple(seed_manifest()["train"])
FROZEN_SMOKE_SEEDS = tuple(seed_manifest()["smoke"])
MAX_DATASET_BYTES = 2 * 1024 ** 3
ARMS = (
    ("baseline", {"attention_prior": 1.0, "relative_geometry": False, "kind_embedding_scale": 1.0}),
    ("prior", {"attention_prior": 512.0, "relative_geometry": False, "kind_embedding_scale": 1.0}),
    ("relative", {"attention_prior": 1.0, "relative_geometry": True, "kind_embedding_scale": 0.02}),
    ("combined", {"attention_prior": 512.0, "relative_geometry": True, "kind_embedding_scale": 0.02}),
)


@dataclass(frozen=True)
class AblationConfig:
    epochs: int = 8
    batch_size: int = 64
    max_seconds: float = 1200.0
    arm_seconds: float = 300.0
    episode_frames: int = 500
    train_stride: int = 10
    smoke_stride: int = 5
    counterfactual_samples: int = 40
    learning_rate: float = 3e-4
    seed: int = 7
    torch_threads: int = 1
    dataset_max_bytes: int = MAX_DATASET_BYTES
    train_seeds: tuple[int, ...] = FROZEN_TRAIN_SEEDS
    smoke_seeds: tuple[int, ...] = FROZEN_SMOKE_SEEDS

    def __post_init__(self) -> None:
        for name, low, high in (
            ("epochs", 1, 64), ("batch_size", 1, 256), ("episode_frames", 1, 500),
            ("train_stride", 1, 500), ("smoke_stride", 1, 500),
            ("counterfactual_samples", 1, 256), ("seed", 0, 0xFFFF_FFFF),
            ("dataset_max_bytes", 1, MAX_DATASET_BYTES),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer from {low} to {high}")
        for name, high in (("max_seconds", 1200), ("arm_seconds", 300), ("learning_rate", 1)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= high or not math.isfinite(value):
                raise ValueError(f"{name} must be finite and in (0, {high}]")
        if type(self.torch_threads) is not int or self.torch_threads != 1:
            raise ValueError("fixed-data ablation uses exactly one CPU thread")
        for name, frozen in (("train_seeds", FROZEN_TRAIN_SEEDS), ("smoke_seeds", FROZEN_SMOKE_SEEDS)):
            values = getattr(self, name)
            if not isinstance(values, (list, tuple)) or any(type(value) is not int for value in values) or tuple(values) != frozen:
                raise ValueError(f"{name} must match the complete frozen sequence")
            object.__setattr__(self, name, tuple(values))


@dataclass(frozen=True)
class FixedDataset:
    states: tuple[EncodedEntities, ...]
    labels: np.ndarray
    sample_ids: tuple[tuple[int, int], ...]
    receipt: dict[str, Any]


@dataclass
class ArmResult:
    model: EntityActorCritic
    optimizer_state: dict[str, Any]
    metrics: dict[str, Any]
    config: AblationConfig


class AblationTimeout(RuntimeError):
    pass


def _check_provenance(observation: dict[str, Any], expected: dict[str, Any] | None) -> dict[str, Any]:
    actual = observation["info"]["provenance"]
    for key, version in (("feature_schema_version", 2), ("privileged_schema_version", 1)):
        if type(actual.get(key)) is not int or actual[key] != version:
            raise RuntimeError(f"ablation requires native {key}={version}")
    if actual.get("action_repeat") != 1 or type(actual.get("action_repeat")) is not int:
        raise RuntimeError("ablation requires action repeat 1")
    if expected is not None and actual != expected:
        raise RuntimeError("native provenance changed during fixed-data collection")
    return actual


def _estimated_state_bytes(state: EncodedEntities) -> int:
    # Include a conservative fixed allowance for the dataclass, array views,
    # immutable backing stores, labels, and sample identity bookkeeping.
    return 2048 + sum(getattr(state, name).nbytes for name in (
        "globals", "features", "kinds", "bounds", "spatial", "capture_bounds",
    ))


def collect_dataset(
    config: AblationConfig, split: str, *, environment_factory: Callable[..., Any] | None = None,
    clock: Callable[[], float] = time.monotonic, deadline: float | None = None,
    memory_budget: int | None = None, progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> FixedDataset:
    """Label pre-action states on fixed heuristic trajectories, without images.

    Every executed frame queries the same avoidance controller. Only the
    declared stride is retained. A deadline returns a clearly incomplete
    collection; the runner will not fit any arm on that partial dataset.
    """
    if not isinstance(config, AblationConfig):
        raise TypeError("config must be an AblationConfig")
    if split not in ("train", "smoke"):
        raise ValueError("ablation collection supports only train and smoke")
    if environment_factory is None:
        from .env import NativeEnvironment
        environment_factory = NativeEnvironment
    if memory_budget is None:
        memory_budget = config.dataset_max_bytes
    if type(memory_budget) is not int or not 1 <= memory_budget <= config.dataset_max_bytes:
        raise ValueError("memory budget must fit the configured dataset cap")
    seeds = config.train_seeds if split == "train" else config.smoke_seeds
    stride = config.train_stride if split == "train" else config.smoke_stride
    started = clock()
    deadline = started + config.max_seconds if deadline is None else deadline
    states: list[EncodedEntities] = []
    labels: list[int] = []
    sample_ids: list[tuple[int, int]] = []
    episodes = []
    identity = hashlib.sha256()
    memory_bytes = frames = queries = 0
    provenance = None
    completed = True
    controller = AvoidancePolicy()

    with environment_factory(seed=seeds[0], max_episode_frames=config.episode_frames, action_repeat=1, discount=0.99) as environment:
        for seed in seeds:
            if clock() >= deadline:
                completed = False
                break
            observation = environment.reset(seed=seed)
            actual = _check_provenance(observation, provenance)
            if provenance is None:
                provenance = copy.deepcopy(actual)
            info = observation["info"]
            if info["terminated"] or info["truncated"] or info["episode_frames"] != 0:
                raise RuntimeError("fresh collection reset must return an unfinished frame-zero episode")
            episode_frames = 0
            while not (observation["info"]["terminated"] or observation["info"]["truncated"]):
                if clock() >= deadline:
                    completed = False
                    break
                _check_provenance(observation, provenance)
                pre_frame = observation["info"]["episode_frames"]
                retain = pre_frame % stride == 0
                encoded = encode_entities(observation["privileged_state"]) if retain else None
                label = controller.act(observation)
                queries += 1
                if type(label) is not int or not 0 <= label < len(ACTION_NAMES):
                    raise RuntimeError("avoidance controller returned an invalid action")
                if clock() >= deadline:
                    completed = False
                    break
                following = environment.step(label)
                following_info = following["info"]
                _check_provenance(following, provenance)
                if type(following_info["elapsed_native_frames"]) is not int or following_info["elapsed_native_frames"] != 1:
                    raise RuntimeError("fixed-data collection requires one native frame per action")
                terminated, truncated = following_info["terminated"], following_info["truncated"]
                if type(terminated) is not bool or type(truncated) is not bool or (terminated and truncated):
                    raise RuntimeError("native collection end flags are invalid")
                episode_frames += 1
                frames += 1
                if following_info["episode_frames"] != episode_frames or episode_frames > config.episode_frames:
                    raise RuntimeError("native frame count disagrees with fixed-data collection")
                if episode_frames == config.episode_frames and not (terminated or truncated):
                    raise RuntimeError("native collection exceeded its episode frame cap")
                if encoded is not None:
                    estimated = _estimated_state_bytes(encoded)
                    if memory_bytes + estimated > memory_budget:
                        raise MemoryError("fixed teacher dataset exceeds its configured memory budget")
                    memory_bytes += estimated
                    states.append(encoded)
                    labels.append(label)
                    sample_ids.append((seed, pre_frame))
                    identity.update(json.dumps([seed, pre_frame, label], separators=(",", ":")).encode())
                    for name in ("globals", "features", "kinds", "bounds", "spatial", "capture_bounds"):
                        values = getattr(encoded, name)
                        identity.update(str(values.shape).encode())
                        identity.update(values.tobytes())
                observation = following
            episodes.append({
                "seed": seed, "native_frames": episode_frames,
                "terminated": observation["info"]["terminated"], "truncated": observation["info"]["truncated"],
                "pattern_completions": observation["info"].get("pattern_completions", 0),
            })
            if progress_callback is not None:
                progress_callback({"phase": f"collect_{split}", "episodes": len(episodes), "frames": frames, "queries": queries, "samples": len(states), "estimated_memory_bytes": memory_bytes})
            if not completed:
                break
    frozen_labels = np.frombuffer(np.asarray(labels, dtype=np.int64).tobytes(), dtype=np.int64)
    receipt = {
        "split": split, "seed_sequence": list(seeds), "seeds_started": [row["seed"] for row in episodes],
        "episode_frame_cap": config.episode_frames, "sample_stride": stride,
        "native_frames": frames, "native_frames_exclude_startup": True,
        "heuristic_queries": queries, "samples": len(states),
        "state_identity_sha256": identity.hexdigest(), "estimated_memory_bytes": memory_bytes,
        "memory_budget_bytes": memory_budget, "complete": completed,
        "stop_reason": "complete" if completed else "time_budget", "provenance": provenance,
        "episodes": episodes, "action_counts": {name: labels.count(index) for index, name in enumerate(ACTION_NAMES)},
        "elapsed_seconds": max(0.0, clock() - started),
    }
    return FixedDataset(tuple(states), frozen_labels, tuple(sample_ids), receipt)


def _logits(model: EntityActorCritic, states: tuple[EncodedEntities, ...] | list[EncodedEntities]) -> tuple[torch.Tensor, torch.Tensor]:
    outputs = model.distillation_outputs(batch_entities(states))
    if outputs.logits.shape != (len(states), 9) or not bool(torch.isfinite(outputs.logits).all()) or not bool(torch.isfinite(outputs.latent).all()):
        raise RuntimeError("entity teacher produced invalid action or latent outputs")
    return outputs.logits, outputs.latent


def _enemy_counterfactual(state: EncodedEntities) -> EncodedEntities | None:
    indices = np.flatnonzero((state.kinds == 1) & (state.features[:, 6] < 0.5))
    if not len(indices):
        return None
    index = int(indices[0])
    features = state.features.copy()
    bounds = state.bounds.copy()
    player_x, player_y = state.features[0, :2] * 128
    offset = 8.0 if player_x <= 117.0 else -8.0
    enemy_x, enemy_y = float(player_x + offset), float(player_y)
    features[index, :4] = [enemy_x / 128, enemy_y / 128, -math.copysign(0.5, offset), 0.0]
    size = max(0.0, math.floor(float(features[index, 4]) * 8))
    x, y = math.floor(enemy_x), math.floor(enemy_y)
    bounds[index] = [x, y, x + size + 1, y + size + 2]
    return EncodedEntities(state.globals, features, state.kinds, bounds, state.spatial, state.capture_bounds)


def evaluate_representation(
    model: EntityActorCritic, dataset: FixedDataset, *, counterfactual_samples: int = 40,
    batch_size: int = 16, deadline: float | None = None, clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Measure held-out classification and response to a synthetic nearby enemy."""
    if not dataset.states:
        raise ValueError("held-out dataset must not be empty")
    model.eval()
    logits_rows, latent_rows = [], []
    with torch.no_grad():
        for start in range(0, len(dataset.states), batch_size):
            if deadline is not None and clock() >= deadline:
                raise AblationTimeout("arm budget exhausted during held-out evaluation")
            logits, latent = _logits(model, dataset.states[start:start + batch_size])
            logits_rows.append(logits)
            latent_rows.append(latent)
        logits = torch.cat(logits_rows)
        latents = torch.cat(latent_rows)
        probabilities = logits.softmax(dim=-1)
        predicted = probabilities.argmax(dim=-1).numpy()
        confusion = np.zeros((9, 9), dtype=np.int64)
        for label, prediction in zip(dataset.labels, predicted):
            confusion[int(label), int(prediction)] += 1
        support = confusion.sum(axis=1)
        recalls = [float(confusion[index, index] / count) if count else None for index, count in enumerate(support)]
        changes = []
        changed_indices = []
        for index, state in enumerate(dataset.states):
            if len(changes) >= counterfactual_samples:
                break
            changed = _enemy_counterfactual(state)
            if changed is None:
                continue
            if deadline is not None and clock() >= deadline:
                raise AblationTimeout("arm budget exhausted during enemy counterfactual evaluation")
            changed_logits, _ = _logits(model, [changed])
            tv = 0.5 * (probabilities[index] - changed_logits.softmax(dim=-1)[0]).abs().sum()
            changes.append(float(tv))
            changed_indices.append(index)
    accuracy = float(np.mean(predicted == dataset.labels))
    present_recalls = [value for value in recalls if value is not None]
    latent_scale = float(latents.norm(dim=-1).mean())
    return {
        "split": dataset.receipt["split"], "samples": len(dataset.states),
        "dataset_identity_sha256": dataset.receipt["state_identity_sha256"],
        "accuracy": accuracy, "balanced_accuracy": sum(present_recalls) / len(present_recalls),
        "per_action_recall": dict(zip(ACTION_NAMES, recalls)),
        "confusion_target_rows_prediction_columns": confusion.tolist(),
        "target_counts": dict(zip(ACTION_NAMES, support.tolist())),
        "prediction_counts": {name: int((predicted == index).sum()) for index, name in enumerate(ACTION_NAMES)},
        "logit_std_max": float(logits.std(dim=0, unbiased=False).max()),
        "probability_std_max": float(probabilities.std(dim=0, unbiased=False).max()),
        "latent_variation_over_norm": float(latents.std(dim=0, unbiased=False).norm()) / max(latent_scale, 1e-12),
        "enemy_counterfactual": {
            "definition": "First normal-enemy record moved horizontally eight pixels from the unchanged player, velocity two pixels per native unit toward player; other privileged records unchanged. Synthetic diagnostic, not an executed native snapshot.",
            "samples": len(changes), "dataset_indices": changed_indices,
            "total_variation_mean": sum(changes) / len(changes) if changes else None,
            "total_variation_max": max(changes) if changes else None,
        },
        "supervised_precondition_passed": accuracy >= 0.90 and bool(changes) and max(changes) >= 0.20,
        "teacher_qualified": False, "gameplay_evaluated": False,
    }


def _train_arm(
    config: AblationConfig, name: str, flags: dict[str, Any], train: FixedDataset,
    smoke: FixedDataset, *, deadline: float, clock: Callable[[], float],
    model_factory: Callable[[EntityTeacherConfig], EntityActorCritic], progress_callback: Callable[[dict[str, Any]], None] | None,
) -> ArmResult:
    started = clock()
    # Leave a bounded part of the arm budget for held-out probes/checkpointing.
    training_deadline = deadline - min(30.0, max(0.0, deadline - started) * 0.2)
    order_hash = hashlib.sha256()
    with torch.random.fork_rng(devices=[]):
        torch.random.default_generator.manual_seed(config.seed)
        model = model_factory(EntityTeacherConfig(**flags))
        if not isinstance(model, EntityActorCritic) or any(getattr(model.config, key) != value for key, value in flags.items()):
            raise ValueError("model factory must preserve the declared entity-teacher arm flags")
        model.cpu().train()
        value_flags = [parameter.requires_grad for parameter in model.value.parameters()]
        model.value.requires_grad_(False)
        parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
        optimizer = torch.optim.Adam(parameters, lr=config.learning_rate)
        permutation_rng = np.random.default_rng(config.seed)
        metrics = {
            "method": "representation_ablation_supervised", "architecture": "entity_transformer",
            "arm": name, "model_config": asdict(model.config), "device": "cpu",
            "frames_collected": train.receipt["native_frames"], "training_samples": len(train.states),
            "training_dataset_identity_sha256": train.receipt["state_identity_sha256"],
            "held_out_dataset_identity_sha256": smoke.receipt["state_identity_sha256"],
            "provenance": copy.deepcopy(train.receipt["provenance"]),
            "optimizer_steps": 0, "samples_optimized": 0, "epochs_completed": 0,
            "classification_loss": None, "training_accuracy": None, "grad_norm": None,
            "stop_reason": "epoch_budget", "teacher_qualified": False,
            "student_collection_allowed": False, "elapsed_seconds": 0.0,
        }
        loss_sum = correct = 0
        try:
            for epoch in range(config.epochs):
                if clock() >= training_deadline:
                    metrics["stop_reason"] = "time_budget"
                    break
                order = permutation_rng.permutation(len(train.states))
                completed_epoch = True
                for start in range(0, len(order), config.batch_size):
                    if clock() >= training_deadline:
                        completed_epoch = False
                        metrics["stop_reason"] = "time_budget"
                        break
                    indices = order[start:start + config.batch_size]
                    logits, _ = _logits(model, [train.states[int(index)] for index in indices])
                    targets = torch.from_numpy(train.labels[indices].copy())
                    loss = F.cross_entropy(logits, targets)
                    if not bool(torch.isfinite(loss)):
                        raise RuntimeError("fixed-data classification loss is nonfinite")
                    optimizer.zero_grad(set_to_none=True)
                    loss.backward()
                    norm = torch.nn.utils.clip_grad_norm_(parameters, 0.5, error_if_nonfinite=True)
                    if clock() >= training_deadline:
                        optimizer.zero_grad(set_to_none=True)
                        completed_epoch = False
                        metrics["stop_reason"] = "time_budget"
                        break
                    optimizer.step()
                    if any(not bool(torch.isfinite(parameter).all()) for parameter in parameters):
                        raise RuntimeError("fixed-data training produced nonfinite weights")
                    count = len(indices)
                    order_hash.update(indices.astype("<i8", copy=False).tobytes())
                    loss_sum += float(loss.detach()) * count
                    correct += int((logits.detach().argmax(dim=-1) == targets).sum())
                    metrics["optimizer_steps"] += 1
                    metrics["samples_optimized"] += count
                    metrics["grad_norm"] = float(norm.detach())
                if completed_epoch:
                    metrics["epochs_completed"] += 1
                if metrics["samples_optimized"]:
                    metrics["classification_loss"] = loss_sum / metrics["samples_optimized"]
                    metrics["training_accuracy"] = correct / metrics["samples_optimized"]
                if progress_callback is not None:
                    progress_callback({"phase": "fit", "arm": name, "epoch": epoch + 1, "optimizer_steps": metrics["optimizer_steps"], "samples_optimized": metrics["samples_optimized"], "classification_loss": metrics["classification_loss"], "elapsed_seconds": clock() - started})
                if not completed_epoch:
                    break
            metrics["minibatch_order_sha256"] = order_hash.hexdigest()
            metrics["evaluation"] = evaluate_representation(model, smoke, counterfactual_samples=config.counterfactual_samples, deadline=deadline, clock=clock)
            metrics["elapsed_seconds"] = max(0.0, clock() - started)
            metrics["model_parameters"] = sum(parameter.numel() for parameter in model.parameters())
            return ArmResult(model, optimizer.state_dict(), metrics, config)
        finally:
            for parameter, required in zip(model.value.parameters(), value_flags):
                parameter.requires_grad_(required)
            model.eval()


def _peak_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if platform.system() == "Darwin" else value * 1024)


def run_ablation(
    config: AblationConfig, output_dir: Path, *, environment_factory: Callable[..., Any] | None = None,
    model_factory: Callable[[EntityTeacherConfig], EntityActorCritic] = EntityActorCritic,
    source_manifest_factory: Callable[[], dict[str, Any]] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Collect once and fit four arms sequentially inside explicit resource caps."""
    from .checkpoints import save_teacher_checkpoint
    from .teacher_run import source_manifest, write_json

    if not isinstance(config, AblationConfig):
        raise TypeError("config must be an AblationConfig")
    output = Path(output_dir).expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    started = clock()
    deadline = started + config.max_seconds
    previous_threads = torch.get_num_threads()
    torch.set_num_threads(config.torch_threads)
    report: dict[str, Any] = {
        "schema_version": 1, "method": "representation_ablation_supervised",
        "started_at_utc": datetime.now(timezone.utc).isoformat(), "arms": [],
        "teacher_qualified": False, "student_collection_allowed": False,
        "qualification": "not_evaluated", "dataset_storage": "memory_only_no_images",
    }
    try:
        sources = (source_manifest_factory or source_manifest)()
        write_json(output / "source.json", sources)
        write_json(output / "config.json", asdict(config))
        write_json(output / "seeds.json", seed_manifest())

        def progress(row: dict[str, Any]) -> None:
            with (output / "progress.jsonl").open("a") as stream:
                stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")

        train = collect_dataset(config, "train", environment_factory=environment_factory, clock=clock, deadline=deadline, progress_callback=progress)
        write_json(output / "train-dataset.json", train.receipt)
        if not train.receipt["complete"] or not train.states:
            raise AblationTimeout("training dataset collection did not complete")
        remaining_memory = config.dataset_max_bytes - train.receipt["estimated_memory_bytes"]
        if remaining_memory <= 0:
            raise MemoryError("training data leaves no capacity for held-out records")
        smoke = collect_dataset(config, "smoke", environment_factory=environment_factory, clock=clock, deadline=deadline, memory_budget=remaining_memory, progress_callback=progress)
        write_json(output / "smoke-dataset.json", smoke.receipt)
        if not smoke.receipt["complete"] or not smoke.states:
            raise AblationTimeout("held-out dataset collection did not complete")
        if train.receipt["provenance"] != smoke.receipt["provenance"]:
            raise RuntimeError("training and held-out native provenance differ")
        report["train_dataset"] = train.receipt
        report["smoke_dataset"] = smoke.receipt
        report["estimated_dataset_memory_bytes"] = train.receipt["estimated_memory_bytes"] + smoke.receipt["estimated_memory_bytes"]
        report["dataset_memory_cap_bytes"] = config.dataset_max_bytes
        for name, flags in ARMS:
            if clock() >= deadline:
                raise AblationTimeout("global budget exhausted before the next arm")
            arm_deadline = min(deadline, clock() + config.arm_seconds)
            result = _train_arm(config, name, flags, train, smoke, deadline=arm_deadline, clock=clock, model_factory=model_factory, progress_callback=progress)
            if clock() >= deadline:
                raise AblationTimeout("global budget exhausted before checkpoint publication")
            checkpoint = save_teacher_checkpoint(output / f"{name}.pt", result, seed_manifest=seed_manifest(), source_manifest=sources)
            arm = {"name": name, "checkpoint": checkpoint, "metrics": result.metrics}
            report["arms"].append(arm)
            write_json(output / f"{name}.json", arm)
        reports = [arm["metrics"] for arm in report["arms"]]
        report["matched_training_budget"] = all(row["epochs_completed"] == config.epochs for row in reports) and len({row["minibatch_order_sha256"] for row in reports}) == 1
        report["matched_parameter_counts"] = len({row["model_parameters"] for row in reports}) == 1
        report["paired_initialization_seed"] = config.seed
        report["fixed_training_identity_for_all_arms"] = all(row["training_dataset_identity_sha256"] == train.receipt["state_identity_sha256"] for row in reports)
        report["fixed_held_out_identity_for_all_arms"] = all(row["held_out_dataset_identity_sha256"] == smoke.receipt["state_identity_sha256"] for row in reports)
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["elapsed_seconds"] = max(0.0, clock() - started)
        report["peak_process_rss_bytes"] = _peak_rss_bytes()
        report["interpretation"] = "Held-out classification and synthetic enemy sensitivity are diagnostic prerequisites. They do not qualify a teacher or establish game-playing survival. Unequal epoch/order budgets weaken causal arm comparisons."
        write_json(output / "run.json", report)
        return report
    except Exception as error:
        write_json(output / "failure.json", {
            "error_type": type(error).__name__, "error": str(error),
            "elapsed_seconds": max(0.0, clock() - started), "completed_arms": [arm["name"] for arm in report["arms"]],
            "teacher_qualified": False, "student_collection_allowed": False,
        })
        raise
    finally:
        torch.set_num_threads(previous_threads)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--max-seconds", type=float, default=1200)
    parser.add_argument("--arm-seconds", type=float, default=300)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=7)
    arguments = parser.parse_args(argv)
    try:
        config = AblationConfig(epochs=arguments.epochs, max_seconds=arguments.max_seconds, arm_seconds=arguments.arm_seconds, batch_size=arguments.batch_size, seed=arguments.seed)
        report = run_ablation(config, arguments.output_dir)
    except (ValueError, RuntimeError, TypeError, OSError, ImportError, MemoryError) as error:
        parser.exit(2, f"teacher representation ablation failed: {error}\n")
    print(json.dumps({"output_dir": str(arguments.output_dir), "matched_training_budget": report["matched_training_budget"], "arms": [{"name": arm["name"], "accuracy": arm["metrics"]["evaluation"]["accuracy"], "enemy_tv_max": arm["metrics"]["evaluation"]["enemy_counterfactual"]["total_variation_max"], "supervised_precondition_passed": arm["metrics"]["evaluation"]["supervised_precondition_passed"]} for arm in report["arms"]], "teacher_qualified": False}, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
