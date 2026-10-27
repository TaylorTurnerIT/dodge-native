"""Test additional optimizer updates on one reproduced teacher dataset.

The collector, examples, architecture, optimizer and update order are fixed.
A continuous fresh fit is measured at four budgets. Epoch eight must reproduce
both the old model tensors and its optimizer state before higher budgets run.
No visual data, PPO, formal qualification, or new policy-state collection is used.
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import time
from typing import Any, Callable

import numpy as np
import torch
from torch.nn import functional as F

from .entity_teacher import EntityActorCritic, EntityTeacherConfig
from .policies import ACTION_NAMES, AvoidancePolicy
from .seeds import seed_manifest
from .teacher_onset_ablation import (
    OnsetConfig, RELATIVE_CONFIG, SMOKE_SEEDS, TRAIN_SEEDS, TaggedDataset,
    _tags, _weights_digest, collect_tagged, combine_datasets, greedy_smoke,
    load_collector,
)
from .teacher_representation_ablation import AblationTimeout, MAX_DATASET_BYTES, _logits, _peak_rss_bytes

COLLECTOR_SHA256 = "12a6ec4f568ec50250cdca8e23597ffe6ddefbe38c8e3e52219fdf4778e46a25"
REFERENCE_SHA256 = "5d5cff94117a88495c9760c3975dd8b6f87ed3a932d9a2fb3b8ff1e3a510a131"
BASE_SHA256 = "378bddc8591f490b8e1ebb0db6bb84445ca8d3666aababb6c94694f39a156632"
TRAIN_SHA256 = "08ffb7335ae8841d05c0a9197a741b036523d2847047a3079211e61fae364d05"
SMOKE_SHA256 = "e853d12dc483f1e2c3a7996e3d8bd33186a9d58afeac8543025939ed67f66abc"
BASE_TAGS_SHA256 = "40147406fef76bef049ad27fbb6d45727ef9de19c98a12fc68333c85954ecf3c"
TRAIN_TAGS_SHA256 = "709ca6ea5806a9c3912a5a0b01f8ee680112bbe835c1b4ae24a183bd653b6fc1"
SMOKE_TAGS_SHA256 = "43b0de29b0661a407d76fea3857b513b1ab7ddd2189a252923a4b92b41eb46f8"
INITIAL_WEIGHTS_SHA256 = "cd421c946116efbe2162098bde29f932e48c6be39284427f35c827180e5e4abb"
EPOCH8_ORDER_SHA256 = "61ff733b3c671590f9d37877a3931597981bd594e30bc41bc4ee9c956afa62a9"
MAX_RSS_BYTES = 6 * 1024 ** 3


@dataclass(frozen=True)
class FitBudgetConfig:
    epochs: int = 64
    milestones: tuple[int, ...] = (8, 16, 32, 64)
    reproduction_epoch: int = 8
    batch_size: int = 64
    seed: int = 7
    learning_rate: float = 3e-4
    max_seconds: float = 1800.0
    max_rss_bytes: int = MAX_RSS_BYTES
    dataset_max_bytes: int = MAX_DATASET_BYTES
    torch_threads: int = 1
    train_seeds: tuple[int, ...] = TRAIN_SEEDS
    smoke_seeds: tuple[int, ...] = SMOKE_SEEDS

    def __post_init__(self) -> None:
        for name, lower, upper in (("epochs", 1, 64), ("reproduction_epoch", 1, 64),
                                   ("batch_size", 1, 256), ("seed", 0, 0xFFFF_FFFF),
                                   ("max_rss_bytes", 1, MAX_RSS_BYTES),
                                   ("dataset_max_bytes", 1, MAX_DATASET_BYTES), ("torch_threads", 1, 1)):
            value = getattr(self, name)
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"{name} must be an integer from {lower} to {upper}")
        if (not isinstance(self.milestones, tuple) or not self.milestones
                or any(type(value) is not int for value in self.milestones)
                or tuple(sorted(set(self.milestones))) != self.milestones
                or self.milestones[0] != self.reproduction_epoch or self.milestones[-1] != self.epochs):
            raise ValueError("milestones must be increasing, begin at reproduction_epoch, and end at epochs")
        for name, upper in (("learning_rate", 1), ("max_seconds", 1800)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= upper:
                raise ValueError(f"{name} must be finite and in (0, {upper}]")
        for name, frozen in (("train_seeds", TRAIN_SEEDS), ("smoke_seeds", SMOKE_SEEDS)):
            if (not isinstance(getattr(self, name), tuple)
                    or any(type(value) is not int for value in getattr(self, name))
                    or getattr(self, name) != frozen):
                raise ValueError(f"{name} must match the complete frozen sequence")

    def require_production_recipe(self) -> None:
        if (self.epochs, self.milestones, self.reproduction_epoch, self.batch_size,
                self.seed, self.learning_rate) != (64, (8, 16, 32, 64), 8, 64, 7, 3e-4):
            raise ValueError("the native runner requires the frozen fit-budget recipe")


@dataclass
class FitState:
    model: EntityActorCritic
    optimizer_state: dict[str, Any]
    metrics: dict[str, Any]
    config: FitBudgetConfig


@dataclass(frozen=True)
class ReproductionReference:
    model_state: dict[str, torch.Tensor]
    optimizer_state: dict[str, Any]
    metrics: dict[str, Any]


class ResourceBudget:
    """Cooperative checks; individual native/Torch calls are not preempted."""

    def __init__(self, config: FitBudgetConfig, *, clock: Callable[[], float] = time.monotonic,
                 rss: Callable[[], int] = _peak_rss_bytes):
        self.clock, self.rss = clock, rss
        self.started = clock()
        self.deadline = self.started + config.max_seconds
        self.max_rss_bytes = config.max_rss_bytes

    def check(self) -> float:
        now = self.clock()
        if now >= self.deadline:
            raise AblationTimeout("fixed-data fit exhausted its wall-time budget")
        if self.rss() > self.max_rss_bytes:
            raise MemoryError("fixed-data fit exceeded its cooperative peak-RSS cap")
        return now


def tree_digest(value: Any) -> str:
    """Hash optimizer values, preserving tensor dtype, shape and exact bytes."""
    identity = hashlib.sha256()

    def add(item: Any) -> None:
        identity.update(type(item).__name__.encode() + b":")
        if isinstance(item, torch.Tensor):
            identity.update(str(item.dtype).encode())
            identity.update(str(tuple(item.shape)).encode())
            identity.update(item.detach().cpu().contiguous().numpy().tobytes())
        elif isinstance(item, dict):
            for key in sorted(item, key=lambda key: (type(key).__name__, str(key))):
                add(key)
                add(item[key])
        elif isinstance(item, (list, tuple)):
            identity.update(str(len(item)).encode())
            for child in item:
                add(child)
        elif item is None or type(item) in (str, int, float, bool):
            identity.update(repr(item).encode())
        else:
            raise TypeError(f"unsupported optimizer/RNG value: {type(item).__name__}")
        identity.update(b";")

    add(value)
    return identity.hexdigest()


def verify_reproduction(state: FitState, reference: ReproductionReference) -> dict[str, Any]:
    model_equal = tree_digest(dict(state.model.state_dict())) == tree_digest(reference.model_state)
    optimizer_equal = tree_digest(state.optimizer_state) == tree_digest(reference.optimizer_state)
    keys = ("initial_weights_sha256", "minibatch_order_sha256", "training_dataset_identity_sha256",
            "optimizer_steps", "samples_optimized", "epochs_completed", "training_samples")
    controls_equal = all(state.metrics[key] == reference.metrics[key] for key in keys)
    if not (model_equal and optimizer_equal and controls_equal):
        raise RuntimeError("epoch-eight reproduction failed: model tensors, optimizer, or update controls differ")
    return {"exact_model_tensors": model_equal, "exact_optimizer_values": optimizer_equal,
            "update_controls_match": controls_equal,
            "model_weights_sha256": _weights_digest(state.model),
            "optimizer_values_sha256": tree_digest(state.optimizer_state),
            "comparison": "tensor values and optimizer tree; new checkpoint file bytes need not match historical metadata"}


def evaluate_fixed(model: EntityActorCritic, dataset: TaggedDataset, budget: ResourceBudget) -> dict[str, Any]:
    """Measure this final model, including loss, without accumulating online predictions."""
    data = dataset.data
    if not data.states or len(dataset.tags) != len(data.states):
        raise ValueError("fixed evaluation requires nonempty aligned states and tags")
    predictions, losses, probabilities = [], [], []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(data.states), 32):
            budget.check()
            logits, _ = _logits(model, data.states[start:start + 32])
            targets = torch.from_numpy(data.labels[start:start + 32].copy())
            nll = -logits.log_softmax(-1).gather(1, targets[:, None]).squeeze(1)
            if not bool(torch.isfinite(nll).all()):
                raise RuntimeError("final-model classification loss is nonfinite")
            predictions.extend(logits.argmax(-1).tolist())
            losses.extend(nll.tolist())
            probabilities.extend(logits.softmax(-1).gather(1, targets[:, None]).squeeze(1).tolist())
            budget.check()
    predicted, loss, probability = np.asarray(predictions), np.asarray(losses), np.asarray(probabilities)
    matches = predicted == data.labels
    masks = {"all": np.ones(len(matches), dtype=bool), "nonneutral": data.labels != 0}
    for key in ("at_rest", "near_rest", "nonneutral_from_rest", "nonneutral_from_near_rest",
                "nonneutral_onset", "nonneutral_continuation", "label_changed_vs_previous_frame"):
        masks[key] = np.asarray([tag[key] for tag in dataset.tags], dtype=bool)
    subsets = {}
    for key, mask in masks.items():
        count = int(mask.sum())
        correct = int(matches[mask].sum())
        subsets[key] = {"count": count, "correct": correct, "recall": correct / count if count else None,
                        "final_ce_loss": float(loss[mask].mean()) if count else None,
                        "mean_target_probability": float(probability[mask].mean()) if count else None}
    return {"dataset_identity_sha256": data.receipt["state_identity_sha256"],
            "tags_identity_sha256": data.receipt["tags_identity_sha256"], "subsets": subsets,
            "final_ce_loss": float(loss.mean()), "loss_definition": "mean cross entropy of this fixed final model",
            "prediction_counts": {name: int((predicted == index).sum()) for index, name in enumerate(ACTION_NAMES)},
            "target_counts": data.receipt["action_counts"]}


def fit_gate(metrics: dict[str, Any]) -> bool:
    subsets = metrics["subsets"]
    thresholds = {"all": .99, "nonneutral_onset": .90, "nonneutral_continuation": .95}
    return all(subsets[key]["recall"] is not None and subsets[key]["recall"] >= value for key, value in thresholds.items())


def fit_dose(config: FitBudgetConfig, train: TaggedDataset, reference: ReproductionReference,
             *, budget: ResourceBudget, snapshot: Callable[[FitState], bool],
             progress: Callable[[dict[str, Any]], None] | None = None,
             partial: Callable[[FitState], None] | None = None,
             model_factory: Callable[[EntityTeacherConfig], EntityActorCritic] = EntityActorCritic) -> FitState:
    """Keep one optimizer alive; snapshots cannot mutate weights or RNG streams."""
    if train.data.receipt["split"] != "train" or not train.data.receipt["complete"] or not train.data.states:
        raise ValueError("fit requires complete nonempty training records")
    order_hash = hashlib.sha256()
    with torch.random.fork_rng(devices=[]):
        torch.random.default_generator.manual_seed(config.seed)
        model = model_factory(RELATIVE_CONFIG).cpu().train()
        if not isinstance(model, EntityActorCritic) or any(getattr(model.config, key) != getattr(RELATIVE_CONFIG, key)
                                                         for key in ("relative_geometry", "kind_embedding_scale", "attention_prior", "dropout")):
            raise ValueError("model factory must preserve the fixed relative representation")
        value_flags = [parameter.requires_grad for parameter in model.value.parameters()]
        model.value.requires_grad_(False)
        parameters = [value for value in model.parameters() if value.requires_grad]
        optimizer = torch.optim.Adam(parameters, lr=config.learning_rate)
        rng = np.random.default_rng(config.seed)
        metrics = {"method": "teacher_fit_budget_supervised", "architecture": "entity_transformer",
                   "provenance": copy.deepcopy(train.data.receipt["provenance"]), "device": "cpu",
                   "frames_collected": train.data.receipt["native_frames"], "training_samples": len(train.data.states),
                   "training_dataset_identity_sha256": train.data.receipt["state_identity_sha256"],
                   "initial_weights_sha256": _weights_digest(model), "optimizer_steps": 0, "samples_optimized": 0,
                   "epochs_completed": 0, "stop_reason": "epoch_budget", "teacher_qualified": False,
                   "student_collection_allowed": False, "model_config": asdict(model.config),
                   "model_parameters": sum(parameter.numel() for parameter in model.parameters())}
        loss_sum = correct = 0

        def state() -> FitState:
            metrics["minibatch_order_sha256"] = order_hash.hexdigest()
            metrics["online_training_accuracy"] = correct / metrics["samples_optimized"] if metrics["samples_optimized"] else None
            metrics["online_classification_loss"] = loss_sum / metrics["samples_optimized"] if metrics["samples_optimized"] else None
            metrics["elapsed_seconds"] = max(0., budget.clock() - budget.started)
            metrics["elapsed_seconds_definition"] = "campaign wall time including collection and earlier snapshots, not optimizer-only time"
            return FitState(model, copy.deepcopy(optimizer.state_dict()), copy.deepcopy(metrics), config)

        try:
            budget.check()
            for epoch in range(config.epochs):
                order = rng.permutation(len(train.data.states))
                for start in range(0, len(order), config.batch_size):
                    budget.check()
                    indices = order[start:start + config.batch_size]
                    logits, _ = _logits(model, [train.data.states[int(index)] for index in indices])
                    targets = torch.from_numpy(train.data.labels[indices].copy())
                    loss = F.cross_entropy(logits, targets)
                    if not bool(torch.isfinite(loss)):
                        raise RuntimeError("fixed-data fit loss is nonfinite")
                    optimizer.zero_grad(set_to_none=True)
                    loss.backward()
                    norm = torch.nn.utils.clip_grad_norm_(parameters, .5, error_if_nonfinite=True)
                    budget.check()
                    optimizer.step()
                    if any(not bool(torch.isfinite(parameter).all()) for parameter in parameters):
                        raise RuntimeError("fixed-data fit produced nonfinite weights")
                    order_hash.update(indices.astype("<i8", copy=False).tobytes())
                    count = len(indices)
                    loss_sum += float(loss.detach()) * count
                    correct += int((logits.detach().argmax(-1) == targets).sum())
                    metrics["optimizer_steps"] += 1
                    metrics["samples_optimized"] += count
                    metrics["last_grad_norm"] = float(norm.detach())
                    budget.check()
                metrics["epochs_completed"] += 1
                if progress:
                    progress({"phase": "fit", "epoch": epoch + 1, "optimizer_steps": metrics["optimizer_steps"],
                              "samples_optimized": metrics["samples_optimized"], "elapsed_seconds": budget.clock() - budget.started})
                if epoch + 1 in config.milestones:
                    current = state()
                    if epoch + 1 == config.reproduction_epoch:
                        metrics["reproduction"] = verify_reproduction(current, reference)
                        current.metrics["reproduction"] = copy.deepcopy(metrics["reproduction"])
                    before_weights, before_optimizer = _weights_digest(model), tree_digest(optimizer.state_dict())
                    before_torch, before_order_rng = torch.random.get_rng_state().clone(), copy.deepcopy(rng.bit_generator.state)
                    training = model.training
                    try:
                        stop = snapshot(current)
                    finally:
                        model.train(training)
                    if (_weights_digest(model) != before_weights or tree_digest(optimizer.state_dict()) != before_optimizer
                            or not torch.equal(torch.random.get_rng_state(), before_torch)
                            or rng.bit_generator.state != before_order_rng):
                        raise RuntimeError("snapshot changed model, optimizer, or training RNG state")
                    budget.check()
                    if stop:
                        metrics["stop_reason"] = "early_fit_gate"
                        metrics["early_stop_epoch"] = epoch + 1
                        break
            return state()
        except Exception:
            metrics["stop_reason"] = "failure"
            if partial is not None:
                partial(state())
            raise
        finally:
            for parameter, required in zip(model.value.parameters(), value_flags):
                parameter.requires_grad_(required)
            model.eval()


class TrackedPolicy:
    """Observe model-visited decisions without changing their executed actions."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.previous_label = None
        self.previous_action = None
        self.run = self.longest = 0
        self.longest_by_action = Counter()
        self.correct = Counter()
        self.count = Counter()
        self.actions = hashlib.sha256()

    def act(self, observation: dict[str, Any]) -> int:
        label = AvoidancePolicy().act(observation)
        action = self.inner.act(observation)
        self.actions.update(bytes([action]))
        tags = _tags(observation, label, self.previous_label)
        for key, include in {"all": True, "nonneutral": label != 0,
                             "nonneutral_onset": tags["nonneutral_onset"],
                             "nonneutral_continuation": tags["nonneutral_continuation"]}.items():
            if include:
                self.count[key] += 1
                self.correct[key] += int(action == label)
        self.run = self.run + 1 if action != 0 and action == self.previous_action else int(action != 0)
        self.longest = max(self.longest, self.run)
        if action:
            self.longest_by_action[ACTION_NAMES[action]] = max(self.longest_by_action[ACTION_NAMES[action]], self.run)
        self.previous_action, self.previous_label = action, label
        return action

    def report(self) -> dict[str, Any]:
        return {"longest_same_nonneutral_action_run": self.longest, "longest_run_by_action": dict(self.longest_by_action),
                "action_sequence_sha256": self.actions.hexdigest(),
                "visited_path_oracle_agreement": {key: {"count": self.count[key], "correct": self.correct[key],
                                                         "recall": self.correct[key] / self.count[key] if self.count[key] else None}
                                                   for key in ("all", "nonneutral", "nonneutral_onset", "nonneutral_continuation")},
                "definition": "Run lengths count executed actions, including the death action; action sequence hashes do not establish trajectory equivalence or statistical independence."}


def evaluate_gameplay(model: EntityActorCritic, provenance: dict[str, Any], budget: ResourceBudget,
                      *, environment_factory: Callable[..., Any] | None = None) -> dict[str, Any]:
    from .teacher_eval import GreedyTeacherPolicy
    trackers = {}

    def factory(seed):
        trackers[seed] = TrackedPolicy(GreedyTeacherPolicy(model, provenance))
        return trackers[seed]

    report = greedy_smoke(OnsetConfig(), factory, provenance=provenance, deadline=budget.deadline,
                          environment_factory=environment_factory, clock=budget.check)
    for episode in report["episodes"]:
        episode.update(trackers[episode["seed"]].report())
    report["unique_action_sequences"] = len({row["action_sequence_sha256"] for row in report["episodes"]})
    return report


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen_inputs(collector_path: Path, reference_path: Path):
    if _file_hash(collector_path) != COLLECTOR_SHA256:
        raise ValueError("collector hash mismatch: use the original stationary relative checkpoint")
    if _file_hash(reference_path) != REFERENCE_SHA256:
        raise ValueError("epoch-eight reference checkpoint hash mismatch")
    collector, reference = load_collector(collector_path), load_collector(reference_path)
    if collector.sha256 != COLLECTOR_SHA256 or reference.sha256 != REFERENCE_SHA256:
        raise ValueError("frozen checkpoint changed while loading")
    if reference.metadata["metrics"]["training_dataset_identity_sha256"] != TRAIN_SHA256:
        raise ValueError("reference training dataset identity differs")
    serialized = reference_path.read_bytes()
    if hashlib.sha256(serialized).hexdigest() != REFERENCE_SHA256:
        raise ValueError("reference checkpoint changed before optimizer loading")
    payload = torch.load(io.BytesIO(serialized), map_location="cpu", weights_only=True)
    reproduction = ReproductionReference(dict(reference.model.state_dict()), payload["optimizer_state"], reference.metadata["metrics"])
    return collector, reference, reproduction


def require_identity(dataset: TaggedDataset, expected_data: str, expected_tags: str, name: str) -> None:
    if (dataset.data.receipt["state_identity_sha256"] != expected_data
            or dataset.data.receipt["tags_identity_sha256"] != expected_tags):
        raise RuntimeError(f"{name} dataset or onset-tag identity differs from the frozen experiment")


def collect_fixed_data(config: FitBudgetConfig, collector: Any, budget: ResourceBudget,
                       *, progress: Callable[[dict[str, Any]], None] | None = None,
                       environment_factory: Callable[..., Any] | None = None):
    from .teacher_eval import GreedyTeacherPolicy, _match_provenance
    collection = OnsetConfig(dataset_max_bytes=config.dataset_max_bytes)
    kwargs = {"environment_factory": environment_factory, "deadline": budget.deadline, "clock": budget.check, "progress": progress}
    base, unused_extra = collect_tagged(collection, "oracle_train", **kwargs)
    require_identity(base, BASE_SHA256, BASE_TAGS_SHA256, "base")
    _match_provenance(base.data.receipt["provenance"], collector.metadata["metrics"]["provenance"])
    del unused_extra
    used = base.data.receipt["estimated_memory_bytes"]
    extra, _ = collect_tagged(collection, "learned_train", learned_policy=GreedyTeacherPolicy(collector.model, collector.metadata["metrics"]["provenance"]),
                              memory_budget=config.dataset_max_bytes - used, **kwargs)
    used += extra.data.receipt["estimated_memory_bytes"]
    train = combine_datasets(base, extra, "learned_state_relabel")
    require_identity(train, TRAIN_SHA256, TRAIN_TAGS_SHA256, "training")
    smoke, _ = collect_tagged(collection, "oracle_smoke", memory_budget=config.dataset_max_bytes - used, **kwargs)
    require_identity(smoke, SMOKE_SHA256, SMOKE_TAGS_SHA256, "smoke")
    _match_provenance(smoke.data.receipt["provenance"], base.data.receipt["provenance"])
    _match_provenance(extra.data.receipt["provenance"], base.data.receipt["provenance"])
    budget.check()
    return base, extra, train, smoke


def run_fit_budget(config: FitBudgetConfig, output_dir: Path, collector_path: Path, reference_path: Path, *,
                   environment_factory: Callable[..., Any] | None = None,
                   clock: Callable[[], float] = time.monotonic,
                   rss: Callable[[], int] = _peak_rss_bytes) -> dict[str, Any]:
    from .checkpoints import save_teacher_checkpoint
    from .teacher_run import source_manifest, write_json
    config.require_production_recipe()
    output = Path(output_dir).expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    budget = ResourceBudget(config, clock=clock, rss=rss)
    previous_threads = torch.get_num_threads()
    torch.set_num_threads(config.torch_threads)
    report = {"schema_version": 1, "method": "teacher_fit_budget_supervised", "snapshots": [],
              "started_at_utc": datetime.now(timezone.utc).isoformat(), "teacher_qualified": False,
              "student_collection_allowed": False, "warm_start": False,
              "resource_checks": "cooperative before/after operations; calls are not preempted; retention may run after a cap",
              "rss_cap_bytes": config.max_rss_bytes, "dataset_memory_cap_bytes": config.dataset_max_bytes}
    try:
        sources = source_manifest()
        write_json(output / "source.json", sources)
        write_json(output / "config.json", asdict(config))
        write_json(output / "seeds.json", seed_manifest())
        budget.check()
        collector, reference, reproduction = load_frozen_inputs(collector_path, reference_path)
        report["inputs"] = {"collector": {"path": str(collector_path.resolve()), "sha256": collector.sha256},
                            "reference": {"path": str(reference_path.resolve()), "sha256": reference.sha256},
                            "roles": "original stationary collector regenerates fixed states; old moving teacher supplies reproduction tensors only"}
        write_json(output / "inputs.json", report["inputs"])

        def progress(row):
            budget.check()
            with (output / "progress.jsonl").open("a") as stream:
                stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")

        base, extra, train, smoke = collect_fixed_data(config, collector, budget, progress=progress, environment_factory=environment_factory)
        report["datasets"] = {name: part.data.receipt for name, part in (("base", base), ("extra", extra), ("train", train), ("smoke", smoke))}
        report["estimated_dataset_memory_bytes"] = sum(part.data.receipt["estimated_memory_bytes"] for part in (base, extra, smoke))
        for name, receipt in report["datasets"].items():
            write_json(output / f"{name}-dataset.json", receipt)
        if source_manifest() != sources:
            raise RuntimeError("source identity changed during fixed data collection")

        def snapshot(state: FitState) -> bool:
            budget.check()
            if source_manifest() != sources:
                raise RuntimeError("source identity changed before snapshot")
            epoch = state.metrics["epochs_completed"]
            prefix = f"epoch-{epoch:03d}"
            record = {"epoch": epoch, "metrics": state.metrics}
            report["snapshots"].append(record)
            record["train"] = evaluate_fixed(state.model, train, budget)
            record["early_fit_gate"] = fit_gate(record["train"])
            state.metrics["final_training_ce_loss"] = record["train"]["final_ce_loss"]
            record["checkpoint"] = save_teacher_checkpoint(output / f"{prefix}.pt", state, seed_manifest=seed_manifest(), source_manifest=sources)
            write_json(output / f"{prefix}-fit.json", record)
            record["original_base"] = evaluate_fixed(state.model, base, budget)
            record["smoke"] = evaluate_fixed(state.model, smoke, budget)
            record["gameplay"] = evaluate_gameplay(state.model, train.data.receipt["provenance"], budget, environment_factory=environment_factory)
            record["oracle_first_onset_reference"] = [{"seed": row["seed"], "frame": row["first_non_neutral_oracle_frame"]} for row in smoke.data.receipt["episodes"]]
            budget.check()
            if source_manifest() != sources:
                raise RuntimeError("source identity changed during snapshot")
            write_json(output / f"{prefix}.json", record)
            progress({"phase": "snapshot", "epoch": epoch, "train_ce": record["train"]["final_ce_loss"],
                      "mean_survival_frames": record["gameplay"]["mean_survival_frames"]})
            return record["early_fit_gate"]

        def partial(state: FitState) -> None:
            receipt = save_teacher_checkpoint(output / "partial-teacher.pt", state, seed_manifest=seed_manifest(), source_manifest=sources)
            report["partial_checkpoint"] = receipt
            report["partial_metrics"] = state.metrics

        result = fit_dose(config, train, reproduction, budget=budget, snapshot=snapshot, progress=progress, partial=partial)
        report["metrics"] = result.metrics
        report["status"] = "completed_diagnostic"
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["peak_process_rss_bytes"] = rss()
        report["interpretation"] = "A single-initialization fixed-data fit-budget diagnostic. Training fit, held-out imitation and closed-loop survival are separate results; thresholds are exploratory, not qualification criteria. No PPO, student collection or architecture changes follow automatically."
        if source_manifest() != sources:
            raise RuntimeError("source identity changed before final publication")
        report["elapsed_seconds"] = budget.check() - budget.started
        write_json(output / "run.json", report)
        return report
    except Exception as error:
        write_json(output / "failure.json", {"error_type": type(error).__name__, "error": str(error),
                                            "elapsed_seconds": max(0., clock() - budget.started),
                                            "snapshots_started": [row["epoch"] for row in report["snapshots"]],
                                            "teacher_qualified": False})
        write_json(output / "partial-run.json", report)
        raise
    finally:
        torch.set_num_threads(previous_threads)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--collector-checkpoint", required=True, type=Path)
    parser.add_argument("--reference-checkpoint", required=True, type=Path)
    parser.add_argument("--max-seconds", type=float, default=1800)
    arguments = parser.parse_args(argv)
    try:
        report = run_fit_budget(FitBudgetConfig(max_seconds=arguments.max_seconds), arguments.output_dir,
                                arguments.collector_checkpoint, arguments.reference_checkpoint)
    except (ValueError, TypeError, RuntimeError, OSError, ImportError, MemoryError) as error:
        parser.exit(2, f"teacher fit-budget diagnostic failed: {error}\n")
    print(json.dumps({"output_dir": str(arguments.output_dir), "teacher_qualified": False,
                      "snapshots": [{"epoch": row["epoch"], "train_ce": row["train"]["final_ce_loss"],
                                     "mean_survival_frames": row["gameplay"]["mean_survival_frames"]} for row in report["snapshots"]]}, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
