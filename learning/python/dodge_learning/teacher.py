"""Versioned current-state features and a small shared-encoder PPO teacher.

This module accepts only the native actor-feature projection. Snapshot bytes,
RNG, seed, future targets, and evaluation metadata are not model inputs. Both
actor and value head use the same declared information budget.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Any

import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor, nn

TEACHER_SCHEMA_VERSION = 1
REQUIRED_NATIVE_FEATURE_SCHEMA_VERSION = 2
MAX_ENTITIES_PER_TYPE = 4096
ACTION_COUNT = 9
GLOBAL_DIM = 8
ENEMY_DIM = 11
RECTANGLE_DIM = 7
WARNING_DIM = 4
ENEMY_KINDS = (-1, 0, 1, 2, 3, 4)


def _immutable_array(value: Any, name: str, width: int, *, vector: bool = False) -> NDArray[np.float32]:
    source = np.asarray(value)
    expected = source.ndim == 1 and source.shape == (width,) if vector else (
        source.ndim == 2 and source.shape[1] == width
    )
    if not expected:
        shape = f"[{width}]" if vector else f"[entities, {width}]"
        raise ValueError(f"{name} must have shape {shape}")
    if not vector and source.shape[0] > MAX_ENTITIES_PER_TYPE:
        raise ValueError(f"{name} exceeds the {MAX_ENTITIES_PER_TYPE}-entity capacity")
    if source.dtype.kind not in "iuf":
        raise ValueError(f"{name} must contain finite numeric values, not booleans")
    with np.errstate(over="ignore", invalid="ignore"):
        array = np.asarray(source, dtype=np.float32)
    if not bool(np.isfinite(array).all()):
        raise ValueError(f"{name} must contain finite float32 values")
    # A bytes-backed copy cannot be made writable again through setflags().
    return np.frombuffer(array.tobytes(order="C"), dtype=np.float32).reshape(array.shape)


@dataclass(frozen=True)
class EncodedState:
    """Owned, immutable float32 features; coordinates retain their signed range."""

    globals: NDArray[np.float32]
    enemies: NDArray[np.float32]
    rectangles: NDArray[np.float32]
    warnings: NDArray[np.float32]

    def __post_init__(self) -> None:
        for name, width, vector in (
            ("globals", GLOBAL_DIM, True),
            ("enemies", ENEMY_DIM, False),
            ("rectangles", RECTANGLE_DIM, False),
            ("warnings", WARNING_DIM, False),
        ):
            object.__setattr__(
                self, name, _immutable_array(getattr(self, name), name, width, vector=vector)
            )


@dataclass(frozen=True)
class TeacherBatch:
    """Padded feature tensors and explicit masks for each entity type."""

    globals: Tensor
    enemies: Tensor
    enemy_mask: Tensor
    rectangles: Tensor
    rectangle_mask: Tensor
    warnings: Tensor
    warning_mask: Tensor


@dataclass(frozen=True)
class TeacherConfig:
    hidden_dim: int = 128
    entity_dim: int = 32

    def __post_init__(self) -> None:
        for name, maximum in (("hidden_dim", 1024), ("entity_dim", 256)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise ValueError(f"{name} must be an integer from 1 to {maximum}")


def _record(value: Any, keys: tuple[str, ...], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    if set(value) != set(keys):
        raise ValueError(f"{name} must contain exactly these keys: {', '.join(keys)}")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number, not a boolean")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{name} must be a finite number") from error
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _flag(value: Any, name: str) -> float:
    if not isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a boolean")
    return float(value)


def _rows(value: Any, keys: tuple[str, ...], name: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence of entity mappings")
    if len(value) > MAX_ENTITIES_PER_TYPE:
        raise ValueError(f"{name} exceeds the {MAX_ENTITIES_PER_TYPE}-entity capacity")
    return [_record(row, keys, f"{name}[{index}]") for index, row in enumerate(value)]


def encode_state(train_only_state: Mapping[str, Any]) -> EncodedState:
    """Validate and normalize one native feature-schema-2 actor projection.

    The caller verifies ``info.provenance.feature_schema_version`` against
    ``REQUIRED_NATIVE_FEATURE_SCHEMA_VERSION``; that metadata is deliberately
    absent from this function's strict input schema.
    """

    state = _record(
        train_only_state, ("player", "globals", "enemies", "rectangles", "warnings"), "state"
    )
    player = _record(state["player"], ("x", "y", "vx", "vy", "size"), "player")
    dynamics = _record(state["globals"], ("speed", "freeze_rate", "freeze_active"), "globals")
    globals_ = [
        _number(player["x"], "player.x") / 128,
        _number(player["y"], "player.y") / 128,
        _number(player["vx"], "player.vx") / 4,
        _number(player["vy"], "player.vy") / 4,
        _number(player["size"], "player.size") / 8,
        _number(dynamics["speed"], "globals.speed") / 4,
        _number(dynamics["freeze_rate"], "globals.freeze_rate"),
        _flag(dynamics["freeze_active"], "globals.freeze_active"),
    ]
    enemies = []
    for row in _rows(state["enemies"], ("x", "y", "vx", "vy", "size", "kind"), "enemies"):
        kind = row["kind"]
        if isinstance(kind, (bool, np.bool_)) or not isinstance(kind, Integral) or kind not in ENEMY_KINDS:
            raise ValueError(f"enemy.kind must be one of {ENEMY_KINDS}")
        enemies.append([
            _number(row["x"], "enemy.x") / 128,
            _number(row["y"], "enemy.y") / 128,
            _number(row["vx"], "enemy.vx") / 4,
            _number(row["vy"], "enemy.vy") / 4,
            _number(row["size"], "enemy.size") / 8,
            *(float(kind == candidate) for candidate in ENEMY_KINDS),
        ])
    rectangles = []
    for row in _rows(
        state["rectangles"], ("x", "y", "width", "height", "dx", "dy", "solid"), "rectangles"
    ):
        rectangles.append([
            _number(row["x"], "rectangle.x") / 128,
            _number(row["y"], "rectangle.y") / 128,
            _number(row["width"], "rectangle.width") / 128,
            _number(row["height"], "rectangle.height") / 128,
            _number(row["dx"], "rectangle.dx") / 4,
            _number(row["dy"], "rectangle.dy") / 4,
            _flag(row["solid"], "rectangle.solid"),
        ])
    warnings = [
        [_number(row[key], f"warning.{key}") / 128 for key in ("x0", "y0", "x1", "y1")]
        for row in _rows(state["warnings"], ("x0", "y0", "x1", "y1"), "warnings")
    ]
    return EncodedState(
        np.asarray(globals_),
        np.asarray(enemies, dtype=np.float64).reshape(-1, ENEMY_DIM),
        np.asarray(rectangles, dtype=np.float64).reshape(-1, RECTANGLE_DIM),
        np.asarray(warnings, dtype=np.float64).reshape(-1, WARNING_DIM),
    )


def batch_states(
    states: Sequence[EncodedState], device: str | torch.device = "cpu"
) -> TeacherBatch:
    """Pad variable-length entities without dropping any row; empty sets use one masked slot."""

    if not isinstance(states, Sequence) or isinstance(states, (str, bytes)) or not states:
        raise ValueError("states must be a nonempty sequence of EncodedState objects")
    if not all(isinstance(state, EncodedState) for state in states):
        raise TypeError("states must contain only EncodedState objects")
    globals_ = torch.from_numpy(np.stack([state.globals for state in states])).to(device)

    def padded(name: str, width: int) -> tuple[Tensor, Tensor]:
        maximum = max(1, max(getattr(state, name).shape[0] for state in states))
        values = np.zeros((len(states), maximum, width), dtype=np.float32)
        mask = np.zeros((len(states), maximum), dtype=np.bool_)
        for index, state in enumerate(states):
            rows = getattr(state, name)
            values[index, :len(rows)] = rows
            mask[index, :len(rows)] = True
        return torch.from_numpy(values).to(device), torch.from_numpy(mask).to(device)

    enemies, enemy_mask = padded("enemies", ENEMY_DIM)
    rectangles, rectangle_mask = padded("rectangles", RECTANGLE_DIM)
    warnings, warning_mask = padded("warnings", WARNING_DIM)
    return TeacherBatch(globals_, enemies, enemy_mask, rectangles, rectangle_mask, warnings, warning_mask)


class StateActorCritic(nn.Module):
    """Order-invariant state policy with masked mean/max entity summaries."""

    def __init__(self, config: TeacherConfig | None = None) -> None:
        super().__init__()
        if config is not None and not isinstance(config, TeacherConfig):
            raise TypeError("config must be a TeacherConfig")
        self.config = config if config is not None else TeacherConfig()
        hidden, entity = self.config.hidden_dim, self.config.entity_dim

        def encoder(width: int, output: int) -> nn.Sequential:
            return nn.Sequential(nn.Linear(width, output), nn.Tanh(), nn.Linear(output, output), nn.Tanh())

        self.global_encoder = encoder(GLOBAL_DIM, hidden)
        self.enemy_encoder = encoder(ENEMY_DIM, entity)
        self.rectangle_encoder = encoder(RECTANGLE_DIM, entity)
        self.warning_encoder = encoder(WARNING_DIM, entity)
        self.merged = encoder(hidden + entity * 6, hidden)
        self.actor = nn.Linear(hidden, ACTION_COUNT)
        self.value = nn.Linear(hidden, 1)

    @staticmethod
    def _pool(values: Tensor, mask: Tensor, encoder: nn.Module) -> Tensor:
        # Clear padding before encoding so even arbitrary padded values cannot
        # affect valid rows or overflow into pooled summaries.
        encoded = encoder(values.masked_fill(~mask.unsqueeze(-1), 0.0))
        valid = mask.unsqueeze(-1)
        mean = encoded.masked_fill(~valid, 0.0).sum(dim=1) / mask.sum(dim=1, keepdim=True).clamp_min(1)
        maximum = encoded.masked_fill(~valid, -torch.inf).amax(dim=1)
        maximum = torch.where(mask.any(dim=1, keepdim=True), maximum, torch.zeros_like(maximum))
        return torch.cat((mean, maximum), dim=-1)

    def forward(self, batch: TeacherBatch) -> tuple[Tensor, Tensor]:
        if not isinstance(batch, TeacherBatch):
            raise TypeError("batch must be a TeacherBatch")
        if batch.globals.ndim != 2 or batch.globals.shape[0] == 0 or batch.globals.shape[1] != GLOBAL_DIM:
            raise ValueError("globals must have nonempty shape [batch, 8]")
        size = batch.globals.shape[0]
        for name, values, mask, width in (
            ("enemies", batch.enemies, batch.enemy_mask, ENEMY_DIM),
            ("rectangles", batch.rectangles, batch.rectangle_mask, RECTANGLE_DIM),
            ("warnings", batch.warnings, batch.warning_mask, WARNING_DIM),
        ):
            if values.ndim != 3 or values.shape[0] != size or values.shape[2] != width:
                raise ValueError(f"{name} must have shape [batch, entities, {width}]")
            if not 1 <= values.shape[1] <= MAX_ENTITIES_PER_TYPE or mask.shape != values.shape[:2]:
                raise ValueError(f"{name} must have matching bounded entity and mask dimensions")
            if mask.dtype != torch.bool:
                raise TypeError(f"{name} mask must have boolean dtype")
            if values.dtype != torch.float32 or values.device != batch.globals.device or mask.device != values.device:
                raise ValueError("teacher features must be float32 tensors on one device")
        if batch.globals.dtype != torch.float32:
            raise TypeError("globals must have float32 dtype")
        summary = torch.cat((
            self.global_encoder(batch.globals),
            self._pool(batch.enemies, batch.enemy_mask, self.enemy_encoder),
            self._pool(batch.rectangles, batch.rectangle_mask, self.rectangle_encoder),
            self._pool(batch.warnings, batch.warning_mask, self.warning_encoder),
        ), dim=-1)
        hidden = self.merged(summary)
        return self.actor(hidden), self.value(hidden).squeeze(-1)
