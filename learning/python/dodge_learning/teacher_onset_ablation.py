"""One fixed-budget comparison of oracle and learned-policy state coverage.

The original oracle samples are shared between arms. Only the extra training
states change. Onset tags use the immediately preceding native frame, even
when that frame is not retained. This is a teacher diagnostic, not formal
qualification, and it neither runs PPO nor changes the architecture.
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Callable

import numpy as np
import torch
from torch.nn import functional as F

from .entity_teacher import EncodedEntities, EntityActorCritic, EntityTeacherConfig
from .policies import ACTION_NAMES, AvoidancePolicy, make_policy
from .seeds import manifest_hash, seed_manifest
from .teacher_representation_ablation import (
    AblationTimeout, FixedDataset, MAX_DATASET_BYTES, _check_provenance,
    _estimated_state_bytes, _logits, _peak_rss_bytes,
)

TRAIN_SEEDS = tuple(seed_manifest()["train"])
SMOKE_SEEDS = tuple(seed_manifest()["smoke"])
RELATIVE_CONFIG = EntityTeacherConfig(relative_geometry=True, kind_embedding_scale=0.02)
ARRAY_FIELDS = ("globals", "features", "kinds", "bounds", "spatial", "capture_bounds")
SAMPLING_CAVEAT = (
    "Control extras use frames 5,25,...485. Learned-policy extras use 25 unique "
    "evenly spaced candidates per episode from positive multiples of 5, including "
    "the first and last candidate. Early deaths prevent matching the frame stride. "
    "The comparison changes visited states and within-episode sampling density; "
    "it does not isolate those effects. Neither arm pads or repeats candidate "
    "row indices; exact input overlap with the base is retained and reported."
)


@dataclass(frozen=True)
class OnsetConfig:
    epochs: int = 8
    batch_size: int = 64
    seed: int = 7
    learning_rate: float = 3e-4
    max_seconds: float = 1200.0
    arm_seconds: float = 300.0
    episode_frames: int = 500
    gameplay_frames: int = 1000
    extra_per_seed: int = 25
    dataset_max_bytes: int = MAX_DATASET_BYTES
    torch_threads: int = 1
    train_seeds: tuple[int, ...] = TRAIN_SEEDS
    smoke_seeds: tuple[int, ...] = SMOKE_SEEDS

    def __post_init__(self) -> None:
        for name, lower, upper in (
            ("epochs", 1, 64), ("batch_size", 1, 256), ("seed", 0, 0xFFFF_FFFF),
            ("episode_frames", 1, 500), ("gameplay_frames", 1, 1000),
            ("extra_per_seed", 1, 25), ("dataset_max_bytes", 1, MAX_DATASET_BYTES),
            ("torch_threads", 1, 1),
        ):
            value = getattr(self, name)
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"{name} must be an integer from {lower} to {upper}")
        for name, upper in (("learning_rate", 1), ("max_seconds", 1200), ("arm_seconds", 300)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= upper:
                raise ValueError(f"{name} must be finite and in (0, {upper}]")
        for name, expected in (("train_seeds", TRAIN_SEEDS), ("smoke_seeds", SMOKE_SEEDS)):
            actual = getattr(self, name)
            if not isinstance(actual, (list, tuple)) or any(type(value) is not int for value in actual) or tuple(actual) != expected:
                raise ValueError(f"{name} must match the complete frozen sequence")
            object.__setattr__(self, name, tuple(actual))


@dataclass(frozen=True)
class TaggedDataset:
    data: FixedDataset
    tags: tuple[dict[str, Any], ...]


@dataclass
class FitResult:
    model: EntityActorCritic
    optimizer_state: dict[str, Any]
    metrics: dict[str, Any]
    config: OnsetConfig


def _expired(deadline: float, clock: Callable[[], float]) -> None:
    if clock() >= deadline:
        raise AblationTimeout("onset comparison exhausted its wall-time budget")


def _digest_row(identity: Any, state: EncodedEntities, sample_id: tuple[int, int], label: int) -> None:
    identity.update(json.dumps([*sample_id, label], separators=(",", ":")).encode())
    for name in ARRAY_FIELDS:
        values = getattr(state, name)
        identity.update(str(values.shape).encode())
        identity.update(values.tobytes())


def _dataset(rows: list[tuple[EncodedEntities, int, tuple[int, int], dict[str, Any]]], receipt: dict[str, Any]) -> TaggedDataset:
    identity = hashlib.sha256()
    tag_identity = hashlib.sha256()
    for state, label, sample_id, tags in rows:
        _digest_row(identity, state, sample_id, label)
        tag_identity.update(json.dumps([*sample_id, tags], sort_keys=True, separators=(",", ":")).encode())
    labels = np.frombuffer(np.asarray([row[1] for row in rows], dtype=np.int64).tobytes(), dtype=np.int64)
    body = {
        **copy.deepcopy(receipt), "samples": len(rows),
        "state_identity_sha256": identity.hexdigest(), "tags_identity_sha256": tag_identity.hexdigest(),
        "estimated_memory_bytes": sum(_estimated_state_bytes(row[0]) + 512 for row in rows),
        "action_counts": {name: int((labels == index).sum()) for index, name in enumerate(ACTION_NAMES)},
        "sample_ids": [list(row[2]) for row in rows],
    }
    return TaggedDataset(FixedDataset(tuple(row[0] for row in rows), labels, tuple(row[2] for row in rows), body), tuple(row[3] for row in rows))


def _tags(observation: dict[str, Any], label: int, previous_label: int | None) -> dict[str, Any]:
    player = observation["train_only_state"]["player"]
    at_rest = abs(float(player["vx"])) <= 1e-6 and abs(float(player["vy"])) <= 1e-6
    near_rest = abs(float(player["vx"])) < .05 and abs(float(player["vy"])) < .05
    onset = previous_label is not None and label != previous_label
    return {
        "label_changed_vs_previous_frame": onset,
        "previous_oracle_label": previous_label,
        "at_rest": at_rest,
        "near_rest": near_rest,
        "nonneutral_from_rest": label != 0 and at_rest,
        "nonneutral_from_near_rest": label != 0 and near_rest,
        "nonneutral_onset": label != 0 and onset,
        "nonneutral_continuation": label != 0 and previous_label == label,
    }


def evenly_spaced_indices(length: int, count: int) -> tuple[int, ...]:
    """Select unique order-preserving quantiles, without replacement or padding."""
    if type(length) is not int or type(count) is not int or count < 1 or length < count:
        raise ValueError("not enough unique learned-policy candidates for the declared per-seed count")
    if count == 1:
        return (length - 1,)
    return tuple(index * (length - 1) // (count - 1) for index in range(count))


def collect_tagged(
    config: OnsetConfig, mode: str, *, learned_policy: Any | None = None,
    environment_factory: Callable[..., Any] | None = None,
    clock: Callable[[], float] = time.monotonic, deadline: float,
    memory_budget: int | None = None, progress: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[TaggedDataset, TaggedDataset | None]:
    """Collect oracle base/extras, smoke records, or frozen-policy extras.

    Learned actions are executed; avoidance supplies labels only. Oracle onset
    on these paths describes a change in the hypothetical oracle recommendation,
    not a change in the executed learned action. From-rest tags are separate.
    """
    if mode not in ("oracle_train", "learned_train", "oracle_smoke"):
        raise ValueError("unsupported tagged collection mode")
    if mode == "learned_train" and learned_policy is None:
        raise ValueError("learned collection requires the frozen policy")
    if environment_factory is None:
        from .env import NativeEnvironment
        environment_factory = NativeEnvironment
    budget = config.dataset_max_bytes if memory_budget is None else memory_budget
    if type(budget) is not int or not 1 <= budget <= config.dataset_max_bytes:
        raise ValueError("collection memory budget must fit the dataset cap")
    seeds = config.smoke_seeds if mode == "oracle_smoke" else config.train_seeds
    rows, extra_rows = [], []
    episodes = []
    provenance = None
    frames = queries = kept_bytes = 0
    started = clock()
    oracle = AvoidancePolicy()
    with environment_factory(seed=seeds[0], max_episode_frames=config.episode_frames, action_repeat=1, discount=.99) as environment:
        for seed in seeds:
            _expired(deadline, clock)
            observation = environment.reset(seed)
            provenance = _check_provenance(observation, provenance)
            previous_label = None
            candidates = []
            candidate_bytes = 0
            first_non_neutral = None
            episode_frames = 0
            while not (observation["info"]["terminated"] or observation["info"]["truncated"]):
                _expired(deadline, clock)
                _check_provenance(observation, provenance)
                frame = observation["info"]["episode_frames"]
                if type(frame) is not int or frame != episode_frames or frame >= config.episode_frames:
                    raise RuntimeError("tagged collection pre-action frame count is invalid")
                label = oracle.act(observation)
                queries += 1
                if type(label) is not int or not 0 <= label < len(ACTION_NAMES):
                    raise RuntimeError("oracle returned an invalid action")
                if label and first_non_neutral is None:
                    first_non_neutral = frame
                tags = _tags(observation, label, previous_label)
                retain_base = mode == "oracle_train" and frame % 10 == 0
                retain_extra = mode == "oracle_train" and frame >= 5 and (frame - 5) % 20 == 0 and (frame - 5) // 20 < config.extra_per_seed
                retain_smoke = mode == "oracle_smoke" and frame % 5 == 0
                retain_candidate = mode == "learned_train" and frame >= 5 and frame % 5 == 0
                row = None
                if retain_base or retain_extra or retain_smoke or retain_candidate:
                    from .entity_teacher import encode_entities
                    encoded = encode_entities(observation["privileged_state"])
                    size = _estimated_state_bytes(encoded) + 512
                    if kept_bytes + candidate_bytes + size > budget:
                        raise MemoryError("tagged teacher dataset exceeds its memory budget")
                    row = (encoded, label, (seed, frame), tags)
                action = learned_policy.act(observation) if mode == "learned_train" else label
                if type(action) is not int or not 0 <= action < len(ACTION_NAMES):
                    raise RuntimeError("state collector returned an invalid action")
                _expired(deadline, clock)
                following = environment.step(action)
                _check_provenance(following, provenance)
                info = following["info"]
                if type(info["elapsed_native_frames"]) is not int or info["elapsed_native_frames"] != 1:
                    raise RuntimeError("tagged collection requires one native frame per action")
                if type(info["terminated"]) is not bool or type(info["truncated"]) is not bool or (info["terminated"] and info["truncated"]):
                    raise RuntimeError("tagged collection received invalid end flags")
                episode_frames += 1
                frames += 1
                if info["episode_frames"] != episode_frames or episode_frames > config.episode_frames:
                    raise RuntimeError("tagged collection native frame count disagrees")
                if episode_frames == config.episode_frames and not (info["terminated"] or info["truncated"]):
                    raise RuntimeError("tagged collection exceeded its episode cap")
                if row is not None:
                    if retain_candidate:
                        candidates.append(row)
                        candidate_bytes += size
                    elif retain_extra:
                        extra_rows.append(row)
                        kept_bytes += size
                    else:
                        rows.append(row)
                        kept_bytes += size
                previous_label = label
                observation = following
            if mode == "learned_train":
                selected = evenly_spaced_indices(len(candidates), config.extra_per_seed)
                for index in selected:
                    rows.append(candidates[index])
                    kept_bytes += _estimated_state_bytes(candidates[index][0]) + 512
            episodes.append({
                "seed": seed, "native_frames": episode_frames,
                "terminated": observation["info"]["terminated"], "truncated": observation["info"]["truncated"],
                "first_non_neutral_oracle_frame": first_non_neutral,
                "candidate_count": len(candidates) if mode == "learned_train" else None,
            })
            if progress:
                progress({"phase": mode, "episodes": len(episodes), "native_frames": frames, "samples": len(rows), "extra_samples": len(extra_rows)})
    receipt = {
        "split": "smoke" if mode == "oracle_smoke" else "train", "collection_mode": mode,
        "seed_sequence": list(seeds), "native_frames": frames, "native_frames_exclude_startup": True,
        "heuristic_queries": queries, "episode_frame_cap": config.episode_frames,
        "provenance": provenance, "episodes": episodes, "complete": True,
        "elapsed_seconds": max(0., clock() - started), "sampling_caveat": SAMPLING_CAVEAT,
    }
    result = _dataset(rows, receipt)
    extra = _dataset(extra_rows, {**receipt, "collection_mode": "oracle_extra"}) if mode == "oracle_train" else None
    if mode == "oracle_train" and len(extra_rows) != len(seeds) * config.extra_per_seed:
        raise RuntimeError("oracle collection did not produce the complete declared extra sample count")
    return result, extra


def combine_datasets(base: TaggedDataset, extra: TaggedDataset, name: str) -> TaggedDataset:
    if base.data.receipt["split"] != "train" or extra.data.receipt["split"] != "train":
        raise ValueError("smoke records must never enter optimization")
    if base.data.receipt["provenance"] != extra.data.receipt["provenance"]:
        raise RuntimeError("training native provenance differs")
    rows = [(state, int(label), sample_id, tag) for part in (base, extra) for state, label, sample_id, tag in zip(part.data.states, part.data.labels, part.data.sample_ids, part.tags)]
    return _dataset(rows, {
        "split": "train", "arm": name, "provenance": base.data.receipt["provenance"],
        "native_frames": base.data.receipt["native_frames"] + (extra.data.receipt["native_frames"] if extra.data.receipt["collection_mode"] == "learned_train" else 0),
        "complete": True, "base_identity_sha256": base.data.receipt["state_identity_sha256"],
        "extra_identity_sha256": extra.data.receipt["state_identity_sha256"],
        "base_extra_overlap": dataset_overlap(base, extra),
    })


def dataset_overlap(base: TaggedDataset, extra: TaggedDataset) -> dict[str, Any]:
    """Distinguish replayed native inputs from matching seed/frame identifiers."""
    def fingerprints(part):
        result = Counter()
        for state, label in zip(part.data.states, part.data.labels):
            identity = hashlib.sha256()
            identity.update(str(int(label)).encode())
            for name in ARRAY_FIELDS:
                values = getattr(state, name)
                identity.update(str(values.shape).encode())
                identity.update(values.tobytes())
            result[identity.hexdigest()] += 1
        return result
    base_states, extra_states = fingerprints(base), fingerprints(extra)
    common = sorted(set(base_states) & set(extra_states))
    base_ids = set(base.data.sample_ids)
    return {
        "exact_state_and_label_common_unique_hashes": len(common),
        "extra_samples_matching_any_base_state_and_label": sum(extra_states[key] for key in common),
        "state_and_label_multiset_intersection_count": sum(min(base_states[key], extra_states[key]) for key in common),
        "common_hashes_sha256": hashlib.sha256(json.dumps(common, separators=(",", ":")).encode()).hexdigest(),
        "extra_samples_with_same_seed_frame_as_base": sum(sample_id in base_ids for sample_id in extra.data.sample_ids),
        "definition": "SHA256 over oracle label and every encoded entity array, excluding seed/frame; identifier overlap is reported separately. Duplicate rows are retained without reselection.",
    }


def subset_metrics(model: EntityActorCritic, dataset: TaggedDataset, *, deadline: float, clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Report exact-label recall with denominators, including absent subsets."""
    data = dataset.data
    if not data.states or len(data.states) != len(dataset.tags):
        raise ValueError("tagged evaluation requires aligned nonempty records")
    predicted = []
    target_probability = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(data.states), 32):
            _expired(deadline, clock)
            logits, _ = _logits(model, data.states[start:start + 32])
            predicted.extend(logits.argmax(-1).tolist())
            targets = torch.from_numpy(data.labels[start:start + 32].copy())
            target_probability.extend(logits.softmax(-1).gather(1, targets[:, None]).squeeze(1).tolist())
    predictions = np.asarray(predicted)
    matches = predictions == data.labels
    subsets = {"all": np.ones(len(matches), dtype=bool), "nonneutral": data.labels != 0}
    for key in ("at_rest", "near_rest", "nonneutral_from_rest", "nonneutral_from_near_rest", "nonneutral_onset", "nonneutral_continuation", "label_changed_vs_previous_frame"):
        subsets[key] = np.asarray([tag[key] for tag in dataset.tags], dtype=bool)
    metrics = {}
    for name, mask in subsets.items():
        count = int(mask.sum())
        correct = int(matches[mask].sum())
        metrics[name] = {"count": count, "correct": correct, "recall": correct / count if count else None,
                         "mean_target_probability": float(np.asarray(target_probability)[mask].mean()) if count else None}
    return {"dataset_identity_sha256": data.receipt["state_identity_sha256"], "tags_identity_sha256": data.receipt["tags_identity_sha256"], "subsets": metrics,
            "rest_definition": "at_rest: abs(raw vx),abs(raw vy)<=1e-6; near_rest: both abs(raw velocities)<0.05; raw native units, not normalized entity feature units",
            "target_counts": data.receipt["action_counts"], "prediction_counts": {name: int((predictions == index).sum()) for index, name in enumerate(ACTION_NAMES)}}


def _weights_digest(model: EntityActorCritic) -> str:
    identity = hashlib.sha256()
    for name, value in sorted(model.state_dict().items()):
        identity.update(name.encode())
        identity.update(value.detach().cpu().numpy().tobytes())
    return identity.hexdigest()


def fit_arm(config: OnsetConfig, name: str, train: TaggedDataset, *, deadline: float,
            model_factory: Callable[[EntityTeacherConfig], EntityActorCritic] = EntityActorCritic,
            clock: Callable[[], float] = time.monotonic, progress: Callable[[dict[str, Any]], None] | None = None) -> FitResult:
    if train.data.receipt["split"] != "train" or not train.data.receipt["complete"] or not train.data.states:
        raise ValueError("fit requires complete nonempty training records")
    started = clock()
    order_hash = hashlib.sha256()
    with torch.random.fork_rng(devices=[]):
        torch.random.default_generator.manual_seed(config.seed)
        model = model_factory(RELATIVE_CONFIG).cpu().train()
        if not isinstance(model, EntityActorCritic) or any(getattr(model.config, key) != getattr(RELATIVE_CONFIG, key) for key in ("relative_geometry", "kind_embedding_scale", "attention_prior", "dropout")):
            raise ValueError("model factory must preserve relative representation settings")
        initial_digest = _weights_digest(model)
        value_flags = [parameter.requires_grad for parameter in model.value.parameters()]
        model.value.requires_grad_(False)
        parameters = [value for value in model.parameters() if value.requires_grad]
        optimizer = torch.optim.Adam(parameters, lr=config.learning_rate)
        rng = np.random.default_rng(config.seed)
        metrics = {
            "method": "teacher_onset_ablation_supervised", "architecture": "entity_transformer", "arm": name,
            "provenance": copy.deepcopy(train.data.receipt["provenance"]), "device": "cpu",
            "frames_collected": train.data.receipt["native_frames"], "training_samples": len(train.data.states),
            "training_dataset_identity_sha256": train.data.receipt["state_identity_sha256"],
            "initial_weights_sha256": initial_digest, "optimizer_steps": 0, "samples_optimized": 0,
            "epochs_completed": 0, "stop_reason": "epoch_budget", "teacher_qualified": False,
            "student_collection_allowed": False, "model_config": asdict(model.config),
            "model_parameters": sum(parameter.numel() for parameter in model.parameters()),
        }
        loss_sum = correct = 0
        try:
            for epoch in range(config.epochs):
                completed = True
                order = rng.permutation(len(train.data.states))
                for start in range(0, len(order), config.batch_size):
                    if clock() >= deadline:
                        completed = False
                        metrics["stop_reason"] = "time_budget"
                        break
                    indices = order[start:start + config.batch_size]
                    logits, _ = _logits(model, [train.data.states[int(index)] for index in indices])
                    targets = torch.from_numpy(train.data.labels[indices].copy())
                    loss = F.cross_entropy(logits, targets)
                    if not bool(torch.isfinite(loss)):
                        raise RuntimeError("onset comparison loss is nonfinite")
                    optimizer.zero_grad(set_to_none=True)
                    loss.backward()
                    norm = torch.nn.utils.clip_grad_norm_(parameters, .5, error_if_nonfinite=True)
                    if clock() >= deadline:
                        optimizer.zero_grad(set_to_none=True)
                        completed = False
                        metrics["stop_reason"] = "time_budget"
                        break
                    optimizer.step()
                    if any(not bool(torch.isfinite(parameter).all()) for parameter in parameters):
                        raise RuntimeError("onset comparison produced nonfinite weights")
                    order_hash.update(indices.astype("<i8", copy=False).tobytes())
                    count = len(indices)
                    loss_sum += float(loss.detach()) * count
                    correct += int((logits.detach().argmax(-1) == targets).sum())
                    metrics["optimizer_steps"] += 1
                    metrics["samples_optimized"] += count
                    metrics["last_grad_norm"] = float(norm.detach())
                if completed:
                    metrics["epochs_completed"] += 1
                if progress:
                    progress({"phase": "fit", "arm": name, "epoch": epoch + 1, "optimizer_steps": metrics["optimizer_steps"], "samples_optimized": metrics["samples_optimized"], "elapsed_seconds": clock() - started})
                if not completed:
                    break
            metrics.update({"minibatch_order_sha256": order_hash.hexdigest(), "elapsed_seconds": max(0., clock() - started),
                            "online_training_accuracy": correct / metrics["samples_optimized"] if metrics["samples_optimized"] else None,
                            "classification_loss": loss_sum / metrics["samples_optimized"] if metrics["samples_optimized"] else None})
            return FitResult(model, optimizer.state_dict(), metrics, config)
        finally:
            for parameter, required in zip(model.value.parameters(), value_flags):
                parameter.requires_grad_(required)
            model.eval()


def greedy_smoke(config: OnsetConfig, policy_factory: Callable[[int], Any], *, provenance: dict[str, Any], deadline: float,
                 environment_factory: Callable[..., Any] | None = None, clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    from .teacher_eval import _match_provenance
    if environment_factory is None:
        from .env import NativeEnvironment
        environment_factory = NativeEnvironment
    episodes = []
    with environment_factory(seed=config.smoke_seeds[0], max_episode_frames=config.gameplay_frames, action_repeat=1, discount=.99) as environment:
        for seed in config.smoke_seeds:
            _expired(deadline, clock)
            observation = environment.reset(seed)
            policy = policy_factory(seed)
            first_action = first_oracle = None
            action_counts = [0] * 9
            return_sum = 0.0
            while not (observation["info"]["terminated"] or observation["info"]["truncated"]):
                _expired(deadline, clock)
                _match_provenance(observation["info"]["provenance"], provenance)
                frame = observation["info"]["episode_frames"]
                oracle_label = AvoidancePolicy().act(observation)
                action = policy.act(observation)
                if type(action) is not int or not 0 <= action < 9:
                    raise RuntimeError("smoke policy returned an invalid action")
                if action and first_action is None:
                    first_action = frame
                if oracle_label and first_oracle is None:
                    first_oracle = frame
                action_counts[action] += 1
                observation = environment.step(action)
                _expired(deadline, clock)
                info = observation["info"]
                if type(info["terminated"]) is not bool or type(info["truncated"]) is not bool or (info["terminated"] and info["truncated"]):
                    raise RuntimeError("smoke evaluation received invalid end flags")
                if type(info["elapsed_native_frames"]) is not int or info["elapsed_native_frames"] != 1 or info["episode_frames"] != frame + 1 or info["episode_frames"] > config.gameplay_frames:
                    raise RuntimeError("smoke evaluation native frame cadence changed")
                reward = float(observation["reward_sum"])
                if not math.isfinite(reward) or reward not in (0., 1.):
                    raise RuntimeError("unexpected native survival reward")
                return_sum += reward
                if info["episode_frames"] == config.gameplay_frames and not (info["terminated"] or info["truncated"]):
                    raise RuntimeError("smoke evaluation exceeded its episode cap")
            _match_provenance(observation["info"]["provenance"], provenance)
            episodes.append({"seed": seed, "frames_survived": int(return_sum), "return": return_sum,
                             "executed_native_frames": observation["info"]["episode_frames"],
                             "terminated": observation["info"]["terminated"], "truncated": observation["info"]["truncated"],
                             "first_non_neutral_frame": first_action, "first_oracle_non_neutral_on_visited_path": first_oracle,
                             "action_counts": dict(zip(ACTION_NAMES, action_counts)),
                             "pattern_completions": observation["info"].get("pattern_completions")})
    return {"episodes": episodes, "mean_survival_frames": sum(row["frames_survived"] for row in episodes) / len(episodes),
            "native_frames": sum(row["executed_native_frames"] for row in episodes), "teacher_qualified": False,
            "survival_definition": "sum of native reward_sum; terminal death frame executes but contributes zero survival reward, matching the existing evaluator",
            "first_action_frame_convention": "zero-based pre-action native episode frame"}


def load_collector(path: Path):
    from .checkpoints import load_teacher_checkpoint
    from .teacher_eval import _verify_source_identity, _require_default_benchmark
    loaded = load_teacher_checkpoint(path)
    if not isinstance(loaded.model, EntityActorCritic) or loaded.model.config != RELATIVE_CONFIG:
        raise ValueError("collector checkpoint must use the unchanged relative entity configuration")
    if manifest_hash(loaded.metadata["seed_manifest"]) != manifest_hash(seed_manifest()):
        raise ValueError("collector seed manifest must match the frozen recipe")
    _, verified = _verify_source_identity(loaded.metadata["source_manifest"])
    if not verified:
        raise ValueError("collector requires complete matching runtime source fingerprints")
    package = Path(__file__).resolve().parent
    # This checkpoint supplies inference actions only, never a warm start.
    # Historical optimizer/training sources are retained in its metadata but
    # need not match a new experiment. Actor/native identity remains strict.
    for name in ("policies.py", "seeds.py"):
        key = f"python/dodge_learning/{name}"
        if loaded.metadata["source_manifest"]["files"].get(key) != hashlib.sha256((package / name).read_bytes()).hexdigest():
            raise ValueError(f"collector policy/seed source fingerprint mismatch: {key}")
    _require_default_benchmark(loaded.metadata["metrics"]["provenance"])
    return loaded


def run_onset_ablation(config: OnsetConfig, output_dir: Path, collector_checkpoint: Path, *,
                      environment_factory: Callable[..., Any] | None = None,
                      clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    from .checkpoints import save_teacher_checkpoint
    from .teacher_eval import GreedyTeacherPolicy, _match_provenance
    from .teacher_run import source_manifest, write_json
    output = Path(output_dir).expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    started = clock()
    deadline = started + config.max_seconds
    previous_threads = torch.get_num_threads()
    torch.set_num_threads(config.torch_threads)
    report: dict[str, Any] = {"schema_version": 1, "method": "teacher_onset_ablation_supervised", "arms": [],
                              "started_at_utc": datetime.now(timezone.utc).isoformat(), "teacher_qualified": False,
                              "student_collection_allowed": False, "sampling_caveat": SAMPLING_CAVEAT,
                              "dataset_storage": "memory_only_no_images"}
    try:
        sources = source_manifest()
        write_json(output / "source.json", sources)
        write_json(output / "config.json", asdict(config))
        write_json(output / "seeds.json", seed_manifest())
        loaded = load_collector(collector_checkpoint)
        report["collector_checkpoint"] = {"path": str(Path(collector_checkpoint).resolve()), "sha256": loaded.sha256,
                                          "role": "fixed_greedy_state_collector_and_pretraining_reference_only", "warm_start": False,
                                          "historical_training_source_manifest": loaded.metadata["source_manifest"],
                                          "current_inference_source_manifest": sources,
                                          "source_check_scope": "strict runtime model/encoder/wrapper/native plus policy and seed sources; historical optimizer/training code is not used for inference"}
        write_json(output / "collector.json", report["collector_checkpoint"])

        def progress(row):
            with (output / "progress.jsonl").open("a") as stream:
                stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")

        base, oracle_extra = collect_tagged(config, "oracle_train", environment_factory=environment_factory, deadline=deadline, clock=clock, progress=progress)
        write_json(output / "base-dataset.json", base.data.receipt)
        write_json(output / "oracle-extra-dataset.json", oracle_extra.data.receipt)
        _match_provenance(base.data.receipt["provenance"], loaded.metadata["metrics"]["provenance"])
        expected_base_hash = loaded.metadata["metrics"].get("training_dataset_identity_sha256")
        if expected_base_hash is not None and expected_base_hash != base.data.receipt["state_identity_sha256"]:
            raise RuntimeError("original oracle dataset identity differs from the frozen collector's training dataset")
        report["original_training_dataset_identity_matched"] = expected_base_hash is not None
        report["pretraining_base_subsets"] = subset_metrics(loaded.model, base, deadline=deadline, clock=clock)
        write_json(output / "pretraining-base-subsets.json", report["pretraining_base_subsets"])
        memory_used = base.data.receipt["estimated_memory_bytes"] + oracle_extra.data.receipt["estimated_memory_bytes"]
        collector = GreedyTeacherPolicy(loaded.model, loaded.metadata["metrics"]["provenance"])
        learned_extra, _ = collect_tagged(config, "learned_train", learned_policy=collector, environment_factory=environment_factory,
                                         deadline=deadline, clock=clock, memory_budget=config.dataset_max_bytes - memory_used, progress=progress)
        memory_used += learned_extra.data.receipt["estimated_memory_bytes"]
        write_json(output / "learned-extra-dataset.json", learned_extra.data.receipt)
        smoke, _ = collect_tagged(config, "oracle_smoke", environment_factory=environment_factory, deadline=deadline, clock=clock,
                                 memory_budget=config.dataset_max_bytes - memory_used, progress=progress)
        memory_used += smoke.data.receipt["estimated_memory_bytes"]
        write_json(output / "smoke-dataset.json", smoke.data.receipt)
        if smoke.data.receipt["provenance"] != base.data.receipt["provenance"] or learned_extra.data.receipt["provenance"] != base.data.receipt["provenance"]:
            raise RuntimeError("collection native provenance changed")
        report["datasets"] = {"base": base.data.receipt, "oracle_extra": oracle_extra.data.receipt,
                              "learned_extra": learned_extra.data.receipt, "smoke": smoke.data.receipt}
        report["estimated_dataset_memory_bytes"] = memory_used
        report["dataset_memory_cap_bytes"] = config.dataset_max_bytes
        report["pretraining_smoke_subsets"] = subset_metrics(loaded.model, smoke, deadline=deadline, clock=clock)
        write_json(output / "pretraining-smoke-subsets.json", report["pretraining_smoke_subsets"])
        if source_manifest() != sources:
            raise RuntimeError("source identity changed during data collection")
        for name, extra in (("oracle_control", oracle_extra), ("learned_state_relabel", learned_extra)):
            _expired(deadline, clock)
            arm_started = clock()
            train = combine_datasets(base, extra, name)
            write_json(output / f"{name}-training-dataset.json", train.data.receipt)
            arm_deadline = min(deadline, arm_started + config.arm_seconds)
            result = fit_arm(config, name, train, deadline=arm_deadline - min(45., config.arm_seconds * .2), clock=clock, progress=progress)
            checkpoint = save_teacher_checkpoint(output / f"{name}.pt", result, seed_manifest=seed_manifest(), source_manifest=sources)
            arm = {"name": name, "checkpoint": checkpoint, "metrics": result.metrics}
            report["arms"].append(arm)
            write_json(output / f"{name}-fit.json", arm)
            if result.metrics["epochs_completed"] != config.epochs:
                raise AblationTimeout("arm did not complete its declared optimization budget; partial checkpoint retained")
            arm["train_subsets"] = subset_metrics(result.model, train, deadline=arm_deadline, clock=clock)
            arm["original_base_subsets"] = subset_metrics(result.model, base, deadline=arm_deadline, clock=clock)
            arm["smoke_subsets"] = subset_metrics(result.model, smoke, deadline=arm_deadline, clock=clock)
            arm["gameplay"] = greedy_smoke(config, lambda seed: GreedyTeacherPolicy(result.model, train.data.receipt["provenance"]),
                                           provenance=train.data.receipt["provenance"], deadline=arm_deadline,
                                           environment_factory=environment_factory, clock=clock)
            arm["oracle_first_onset_reference"] = [{"seed": row["seed"], "frame": row["first_non_neutral_oracle_frame"]} for row in smoke.data.receipt["episodes"]]
            if source_manifest() != sources:
                raise RuntimeError("source identity changed during teacher comparison")
            _expired(arm_deadline, clock)
            arm["total_arm_elapsed_seconds"] = max(0., clock() - arm_started)
            write_json(output / f"{name}.json", arm)
        report["baselines"] = {}
        for name in ("neutral", "random", "avoidance"):
            report["baselines"][name] = greedy_smoke(config, lambda seed, policy=name: make_policy(policy, seed),
                                                    provenance=base.data.receipt["provenance"], deadline=deadline,
                                                    environment_factory=environment_factory, clock=clock)
            write_json(output / f"{name}-smoke.json", report["baselines"][name])
        metrics = [arm["metrics"] for arm in report["arms"]]
        report["matched_initialization"] = len({row["initial_weights_sha256"] for row in metrics}) == 1
        report["matched_training_budget"] = len({(row["training_samples"], row["epochs_completed"], row["optimizer_steps"], row["samples_optimized"], row["minibatch_order_sha256"]) for row in metrics}) == 1
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["elapsed_seconds"] = max(0., clock() - started)
        report["peak_process_rss_bytes"] = _peak_rss_bytes()
        report["interpretation"] = "Exploratory single-initialization matched-budget data-collection comparison. Density, episode horizon, label frequencies, and visited-state distribution change together; the result cannot isolate covariate shift from onset rarity or cadence. Duplicate rows are reported and retained. Smoke metrics do not qualify a teacher; no PPO or student collection follows automatically."
        if source_manifest() != sources:
            raise RuntimeError("source identity changed before report publication")
        write_json(output / "run.json", report)
        return report
    except Exception as error:
        write_json(output / "failure.json", {"error_type": type(error).__name__, "error": str(error), "elapsed_seconds": max(0., clock() - started),
                                            "completed_arms": [row["name"] for row in report["arms"]], "teacher_qualified": False})
        write_json(output / "partial-run.json", report)
        raise
    finally:
        torch.set_num_threads(previous_threads)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--collector-checkpoint", required=True, type=Path)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--max-seconds", type=float, default=1200)
    parser.add_argument("--arm-seconds", type=float, default=300)
    arguments = parser.parse_args(argv)
    try:
        config = OnsetConfig(epochs=arguments.epochs, max_seconds=arguments.max_seconds, arm_seconds=arguments.arm_seconds)
        report = run_onset_ablation(config, arguments.output_dir, arguments.collector_checkpoint)
    except (ValueError, TypeError, RuntimeError, OSError, ImportError, MemoryError) as error:
        parser.exit(2, f"teacher onset comparison failed: {error}\n")
    print(json.dumps({"output_dir": str(arguments.output_dir), "matched_training_budget": report["matched_training_budget"],
                      "matched_initialization": report["matched_initialization"], "teacher_qualified": False,
                      "arms": [{"name": arm["name"], "mean_survival_frames": arm["gameplay"]["mean_survival_frames"]} for arm in report["arms"]]}, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
