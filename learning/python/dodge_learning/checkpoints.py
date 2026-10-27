"""Versioned, atomic checkpoints for the CPU state teacher.

Optimizer state is retained for inspection and future work. These files do not
promise exact training continuation: rollout buffers and RNG states are absent.
Import this module explicitly after installing the optional models extra.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields, is_dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import tempfile
from typing import Any

import torch
from torch import Tensor

from .policies import ACTION_MASKS, ACTION_NAMES
from .seeds import manifest_hash, validate_manifest
from .teacher import (
    REQUIRED_NATIVE_FEATURE_SCHEMA_VERSION,
    TEACHER_SCHEMA_VERSION,
    StateActorCritic,
    TeacherConfig,
)
from .entity_teacher import (
    ENTITY_TEACHER_SCHEMA_VERSION,
    LEGACY_ENTITY_TEACHER_SCHEMA_VERSION,
    REQUIRED_PRIVILEGED_SCHEMA_VERSION,
    EntityActorCritic,
    EntityTeacherConfig,
)

CHECKPOINT_FORMAT_VERSION = 1
CHECKPOINT_KIND = "dodge_state_teacher"
ENTITY_CHECKPOINT_KIND = "dodge_entity_transformer_teacher"
ENTITY_CHECKPOINT_FORMAT_VERSION = 2
LEGACY_ENTITY_MODEL_FIELDS = frozenset(("embed_dim", "depth", "num_heads", "mlp_ratio", "dropout"))
LEGACY_ENTITY_REPRESENTATION = {
    "attention_prior": 1.0,
    "relative_geometry": False,
    "kind_embedding_scale": 1.0,
}


@dataclass(frozen=True)
class LoadedTeacher:
    model: StateActorCritic | EntityActorCritic
    metadata: dict[str, Any]
    sha256: str


def _json_copy(value: Any, name: str) -> Any:
    """Own a JSON-safe snapshot, rejecting nonfinite and tensor metadata."""

    try:
        return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must contain finite JSON-safe data") from error


def _cpu_tree(value: Any, name: str) -> Any:
    """Copy tensors to CPU and restrict optimizer data to weights-only types."""

    if isinstance(value, Tensor):
        if not bool(torch.isfinite(value.detach()).all()):
            raise ValueError(f"{name} contains a nonfinite tensor")
        return value.detach().to(device="cpu").clone()
    if isinstance(value, dict):
        if not all(type(key) in (str, int) for key in value):
            raise ValueError(f"{name} dictionary keys must be strings or integers")
        return {key: _cpu_tree(child, f"{name}.{key}") for key, child in value.items()}
    if isinstance(value, list):
        return [_cpu_tree(child, name) for child in value]
    if isinstance(value, tuple):
        return tuple(_cpu_tree(child, name) for child in value)
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError(f"{name} contains unsupported or nonfinite optimizer data")


def _training_seeds(training_config: dict[str, Any], seeds: dict[str, Any]) -> None:
    actual = training_config.get("train_seeds")
    if (
        not isinstance(actual, list)
        or not actual
        or not all(type(seed) is int and 0 <= seed <= 0xFFFF_FFFF for seed in actual)
        or len(set(actual)) != len(actual)
        or (0 in actual and 1 in actual)
    ):
        raise ValueError("training_config.train_seeds must contain distinct nonempty uint32 seeds")
    if not set(actual) <= set(seeds["train"]):
        raise ValueError("actual training seeds must be a subset of the manifest's train split")


def _metadata_and_model(payload: Any) -> tuple[dict[str, Any], StateActorCritic | EntityActorCritic]:
    if not isinstance(payload, dict):
        raise ValueError("teacher checkpoint must be a dictionary")
    required = {
        "format_version", "kind", "teacher_schema_version", "native_feature_schema_version",
        "action_names", "action_masks", "model_config", "model_state", "optimizer_state",
        "training_config", "metrics", "seed_manifest", "seed_manifest_hash",
        "source_manifest", "python_version", "torch_version",
    }
    is_entity = payload.get("kind") == ENTITY_CHECKPOINT_KIND
    if is_entity:
        required.add("privileged_schema_version")
    if set(payload) != required:
        raise ValueError("teacher checkpoint fields do not match the declared architecture format")
    for key, expected in (
        ("format_version", ENTITY_CHECKPOINT_FORMAT_VERSION if is_entity else CHECKPOINT_FORMAT_VERSION),
        ("native_feature_schema_version", REQUIRED_NATIVE_FEATURE_SCHEMA_VERSION),
    ):
        if type(payload[key]) is not int or payload[key] != expected:
            raise ValueError(f"unsupported checkpoint {key}")
    if payload["kind"] not in (CHECKPOINT_KIND, ENTITY_CHECKPOINT_KIND):
        raise ValueError("unsupported teacher checkpoint kind")
    teacher_schema = payload["teacher_schema_version"]
    supported_schemas = (
        (LEGACY_ENTITY_TEACHER_SCHEMA_VERSION, ENTITY_TEACHER_SCHEMA_VERSION)
        if is_entity else (TEACHER_SCHEMA_VERSION,)
    )
    if type(teacher_schema) is not int or teacher_schema not in supported_schemas:
        raise ValueError("unsupported checkpoint teacher_schema_version")
    if is_entity and (type(payload["privileged_schema_version"]) is not int or payload["privileged_schema_version"] != REQUIRED_PRIVILEGED_SCHEMA_VERSION):
        raise ValueError("unsupported checkpoint privileged_schema_version")
    if payload["action_names"] != list(ACTION_NAMES):
        raise ValueError("checkpoint action names do not match the native action order")
    if (
        payload["action_masks"] != list(ACTION_MASKS)
        or not all(type(mask) is int for mask in payload["action_masks"])
    ):
        raise ValueError("checkpoint action masks do not match the native action order")

    metadata = _json_copy(
        {key: value for key, value in payload.items() if key not in ("model_state", "optimizer_state")},
        "checkpoint metadata",
    )
    for key in ("model_config", "training_config", "metrics", "seed_manifest", "source_manifest"):
        if not isinstance(metadata[key], dict):
            raise ValueError(f"{key} must be a dictionary")
    if not metadata["source_manifest"]:
        raise ValueError("source_manifest must not be empty")
    for key in ("python_version", "torch_version"):
        if not isinstance(metadata[key], str) or not metadata[key]:
            raise ValueError(f"{key} must be a nonempty string")
    validate_manifest(metadata["seed_manifest"])
    if metadata["seed_manifest_hash"] != manifest_hash(metadata["seed_manifest"]):
        raise ValueError("checkpoint seed manifest hash does not match its contents")
    _training_seeds(metadata["training_config"], metadata["seed_manifest"])
    provenance = metadata["metrics"].get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("metrics must include native provenance")
    if (
        type(provenance.get("feature_schema_version")) is not int
        or provenance["feature_schema_version"] != REQUIRED_NATIVE_FEATURE_SCHEMA_VERSION
    ):
        raise ValueError("training provenance has an incompatible native feature schema")
    if is_entity and (type(provenance.get("privileged_schema_version")) is not int or provenance["privileged_schema_version"] != REQUIRED_PRIVILEGED_SCHEMA_VERSION):
        raise ValueError("training provenance has an incompatible privileged schema")

    config_type = EntityTeacherConfig if is_entity else TeacherConfig
    model_type = EntityActorCritic if is_entity else StateActorCritic
    legacy_entity = is_entity and teacher_schema == LEGACY_ENTITY_TEACHER_SCHEMA_VERSION
    expected_fields = (
        LEGACY_ENTITY_MODEL_FIELDS if legacy_entity else {field.name for field in fields(config_type)}
    )
    if set(metadata["model_config"]) != expected_fields:
        raise ValueError("checkpoint model_config must declare every teacher dimension")
    construction_config = dict(metadata["model_config"])
    if legacy_entity:
        # Schema 1 had no representation switches. Its serialized metadata and
        # digest remain unchanged; only the in-memory constructor gets defaults
        # that reproduce the legacy forward pass.
        construction_config.update(LEGACY_ENTITY_REPRESENTATION)
    try:
        config = config_type(**construction_config)
    except (TypeError, ValueError) as error:
        raise ValueError("checkpoint model_config is invalid") from error
    # Loading must not advance the caller's policy-sampling CPU random stream.
    with torch.random.fork_rng(devices=[]):
        model = model_type(config).to(device="cpu", dtype=torch.float32)
    state = payload["model_state"]
    expected_state = model.state_dict()
    if not isinstance(state, Mapping) or set(state) != set(expected_state):
        raise ValueError("checkpoint model_state keys do not match the teacher architecture")
    for key, expected in expected_state.items():
        value = state[key]
        if not isinstance(value, Tensor):
            raise ValueError(f"model_state.{key} must be a tensor")
        if value.shape != expected.shape or value.dtype != expected.dtype:
            raise ValueError(f"model_state.{key} has an incompatible shape or dtype")
        if value.device.type != "cpu" or not bool(torch.isfinite(value).all()):
            raise ValueError(f"model_state.{key} must contain finite CPU weights")
    if not isinstance(payload["optimizer_state"], dict):
        raise ValueError("optimizer_state must be a dictionary")
    _cpu_tree(payload["optimizer_state"], "optimizer_state")
    model.load_state_dict(state, strict=True)
    model.eval()
    return metadata, model


def save_teacher_checkpoint(
    path: str | os.PathLike[str],
    training_result: Any,
    *,
    seed_manifest: dict[str, Any],
    source_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Write an immutable teacher checkpoint and return its JSON-safe receipt.

    A flushed/fsynced temporary file is atomically linked into place. The link
    operation fails if the destination exists, including a concurrent writer's
    file. Filesystems without hard-link support fail explicitly; there is no
    overwrite fallback. Only this call's temporary file is removed on failure.
    """

    destination = Path(path).expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"checkpoint already exists: {destination}")
    model = getattr(training_result, "model", None)
    config = getattr(training_result, "config", None)
    if not isinstance(model, (StateActorCritic, EntityActorCritic)):
        raise TypeError("training_result.model must be a supported teacher")
    if not is_dataclass(config) or isinstance(config, type):
        raise TypeError("training_result.config must be a dataclass instance")
    seeds = _json_copy(seed_manifest, "seed_manifest")
    is_entity = isinstance(model, EntityActorCritic)
    payload = {
        "format_version": ENTITY_CHECKPOINT_FORMAT_VERSION if is_entity else CHECKPOINT_FORMAT_VERSION,
        "kind": ENTITY_CHECKPOINT_KIND if is_entity else CHECKPOINT_KIND,
        "teacher_schema_version": ENTITY_TEACHER_SCHEMA_VERSION if is_entity else TEACHER_SCHEMA_VERSION,
        "native_feature_schema_version": REQUIRED_NATIVE_FEATURE_SCHEMA_VERSION,
        "action_names": list(ACTION_NAMES),
        "action_masks": list(ACTION_MASKS),
        "model_config": asdict(model.config),
        "model_state": _cpu_tree(dict(model.state_dict()), "model_state"),
        "optimizer_state": _cpu_tree(getattr(training_result, "optimizer_state", None), "optimizer_state"),
        "training_config": _json_copy(asdict(config), "training_config"),
        "metrics": _json_copy(getattr(training_result, "metrics", None), "metrics"),
        "seed_manifest": seeds,
        "seed_manifest_hash": manifest_hash(seeds),
        "source_manifest": _json_copy(source_manifest, "source_manifest"),
        "python_version": platform.python_version(),
        "torch_version": str(torch.__version__),
    }
    if is_entity:
        payload["privileged_schema_version"] = REQUIRED_PRIVILEGED_SCHEMA_VERSION
    _metadata_and_model(payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            torch.save(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "path": str(destination),
        "sha256": digest,
        "format_version": payload["format_version"],
        "kind": payload["kind"],
        "model_parameters": sum(parameter.numel() for parameter in model.parameters()),
        "seed_manifest_hash": payload["seed_manifest_hash"],
    }


def load_teacher_checkpoint(path: str | os.PathLike[str]) -> LoadedTeacher:
    """Load a validated CPU/eval teacher using PyTorch's weights-only reader."""

    serialized = Path(path).expanduser().read_bytes()
    digest = hashlib.sha256(serialized).hexdigest()
    payload = torch.load(io.BytesIO(serialized), map_location="cpu", weights_only=True)
    metadata, model = _metadata_and_model(payload)
    return LoadedTeacher(model=model, metadata=metadata, sha256=digest)
