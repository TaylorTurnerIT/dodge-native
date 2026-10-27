"""Privileged entity-transformer actor/critic and its distillation outputs.

The teacher consumes the native structured gameplay projection without a
visibility allowlist. Spatial flags describe attention-target geometry; they
never decide which entities enter the policy. A player query attends to the
entire entity set in each transformer block. This costs O(N) attention storage
instead of a quadratic catalog-by-catalog matrix on the local Mac. Shared
token-wise feed-forward layers preserve permutation symmetry for nonplayer
entities. The final attention operation forms the latent used by both PPO
heads, so its weights are part of the learned decision path.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Integral
from typing import Any

import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor, nn

LEGACY_ENTITY_TEACHER_SCHEMA_VERSION = 1
ENTITY_TEACHER_SCHEMA_VERSION = 2
REQUIRED_PRIVILEGED_SCHEMA_VERSION = 1
GLOBAL_DIM = 64
ENTITY_DIM = 32
ENTITY_KIND_COUNT = 16
MAX_ENTITY_COUNT = 8192
ACTION_COUNT = 9
_ELEMENT_TYPES = np.frompyfunc(type, 1, 1)
_BOOLEAN_TYPES = np.empty(2, dtype=object)
_BOOLEAN_TYPES[:] = [bool, np.bool_]


def _array(value: Any, name: str, shape: tuple[int, ...], dtype: Any) -> NDArray:
    """Own immutable arrays, rejecting coercions that can hide invalid values."""
    source = np.asarray(value)
    if source.shape != shape:
        raise ValueError(f"{name} must have shape {list(shape)}")
    if dtype == np.bool_:
        if source.dtype.kind != "b":
            raise ValueError(f"{name} must contain booleans")
    elif dtype == np.int64:
        if source.dtype.kind not in "iu":
            raise ValueError(f"{name} must contain integer kinds")
        if np.any(source < 0) or np.any(source >= ENTITY_KIND_COUNT):
            raise ValueError(f"{name} kinds must be from 0 to {ENTITY_KIND_COUNT - 1}")
    else:
        if source.dtype.kind not in "iuf":
            raise ValueError(f"{name} must contain finite numbers, not booleans")
    if dtype != np.bool_ and not isinstance(value, np.ndarray):
        # Float coercion hides booleans in mixed Python sequences. Retain
        # scalar types for this check, without recursively visiting every
        # engine field in Python on each native frame.
        scalar_types = _ELEMENT_TYPES(np.asarray(value, dtype=object))
        if bool(np.isin(scalar_types, _BOOLEAN_TYPES).any()):
            raise ValueError(f"{name} must contain numbers, not booleans")
    with np.errstate(over="ignore", invalid="ignore"):
        array = np.asarray(source, dtype=dtype)
    if dtype == np.float32 and not bool(np.isfinite(array).all()):
        raise ValueError(f"{name} must contain finite float32 values")
    return np.frombuffer(array.tobytes(order="C"), dtype=dtype).reshape(shape)


@dataclass(frozen=True)
class EncodedEntities:
    """Owned native features, including unfiltered nonvisual teacher entities."""

    globals: NDArray[np.float32]
    features: NDArray[np.float32]
    kinds: NDArray[np.int64]
    bounds: NDArray[np.float32]
    spatial: NDArray[np.bool_]
    capture_bounds: NDArray[np.float32]

    def __post_init__(self) -> None:
        shape = np.asarray(self.features).shape
        if len(shape) != 2 or shape[1] != ENTITY_DIM or not 1 <= shape[0] <= MAX_ENTITY_COUNT:
            raise ValueError(f"features must have shape [1..{MAX_ENTITY_COUNT}, {ENTITY_DIM}]")
        count = shape[0]
        for name, expected, dtype in (
            ("globals", (GLOBAL_DIM,), np.float32),
            ("features", (count, ENTITY_DIM), np.float32),
            ("kinds", (count,), np.int64),
            ("bounds", (count, 4), np.float32),
            ("spatial", (count,), np.bool_),
            ("capture_bounds", (4,), np.float32),
        ):
            object.__setattr__(self, name, _array(getattr(self, name), name, expected, dtype))
        if self.kinds[0] != 0 or bool((self.kinds[1:] == 0).any()):
            raise ValueError("the first entity must be the only player (kind 0)")
        if bool((self.bounds[:, :2] > self.bounds[:, 2:]).any()):
            raise ValueError("entity bounds must have ordered corners")
        # An empty clipping rectangle is permitted and carries no spatial loss.
        if bool((self.capture_bounds[:2] > self.capture_bounds[2:]).any()):
            raise ValueError("capture bounds must have ordered corners")


@dataclass(frozen=True)
class EntityBatch:
    """Padded entity records; every valid entity is retained behind its mask."""

    globals: Tensor
    features: Tensor
    kinds: Tensor
    mask: Tensor
    bounds: Tensor
    spatial: Tensor
    capture_bounds: Tensor


@dataclass(frozen=True)
class EntityTeacherOutput:
    logits: Tensor
    value: Tensor
    latent: Tensor
    attention: Tensor


@dataclass(frozen=True)
class EntityTeacherConfig:
    embed_dim: int = 128
    depth: int = 2
    num_heads: int = 4
    mlp_ratio: float = 2.0
    dropout: float = 0.0
    attention_prior: float = 1.0
    relative_geometry: bool = False
    kind_embedding_scale: float = 1.0

    def __post_init__(self) -> None:
        for name, lower, upper in (
            ("embed_dim", 8, 512), ("depth", 1, 12), ("num_heads", 1, 16),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
                raise ValueError(f"{name} must be an integer from {lower} to {upper}")
        if self.embed_dim % self.num_heads:
            raise ValueError("embed_dim must be divisible by num_heads")
        for name, lower, upper, inclusive in (
            ("mlp_ratio", 1.0, 8.0, True), ("dropout", 0.0, 1.0, False),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool) or not isinstance(value, (int, float))
                or value < lower or (value > upper if inclusive else value >= upper)
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} is outside its finite supported range")
        for name, lower, upper in (
            ("attention_prior", 1.0, 4096.0),
            ("kind_embedding_scale", 0.001, 1.0),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not lower <= value <= upper or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be finite and in [{lower}, {upper}]")
        if type(self.relative_geometry) is not bool:
            raise ValueError("relative_geometry must be a boolean")


def _record(value: Any, keys: set[str], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"{name} must contain exactly: {', '.join(sorted(keys))}")
    return value


def encode_entities(privileged_state: Mapping[str, Any]) -> EncodedEntities:
    """Validate schema 1; native code already supplies normalized features."""
    state = _record(
        privileged_state, {"schema_version", "globals", "entities", "capture_bounds"}, "privileged state"
    )
    if type(state["schema_version"]) is not int or state["schema_version"] != REQUIRED_PRIVILEGED_SCHEMA_VERSION:
        raise ValueError("unsupported privileged state schema_version")
    rows = state["entities"]
    if (
        not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray))
        or not 1 <= len(rows) <= MAX_ENTITY_COUNT
    ):
        raise ValueError(f"entities must contain from 1 to {MAX_ENTITY_COUNT} records, including the player")
    features, kinds, bounds, spatial = [], [], [], []
    for index, candidate in enumerate(rows):
        row = _record(candidate, {"features", "kind", "bounds", "spatial"}, f"entity {index}")
        kind = row["kind"]
        if isinstance(kind, (bool, np.bool_)) or not isinstance(kind, Integral) or not 0 <= kind < ENTITY_KIND_COUNT:
            raise ValueError(f"entity kind must be an integer from 0 to {ENTITY_KIND_COUNT - 1}")
        if not isinstance(row["spatial"], (bool, np.bool_)):
            raise ValueError("entity spatial flag must be a boolean")
        features.append(row["features"])
        kinds.append(kind)
        bounds.append(row["bounds"])
        spatial.append(row["spatial"])
    return EncodedEntities(state["globals"], features, kinds, bounds, spatial, state["capture_bounds"])


def batch_entities(
    states: Sequence[EncodedEntities], device: str | torch.device = "cpu",
) -> EntityBatch:
    """Pad variable entity sets without truncation or visibility filtering."""
    if (
        not isinstance(states, Sequence) or isinstance(states, (str, bytes)) or not states
        or not all(isinstance(state, EncodedEntities) for state in states)
    ):
        raise ValueError("states must be a nonempty sequence of EncodedEntities")
    size, maximum = len(states), max(state.features.shape[0] for state in states)
    features = np.zeros((size, maximum, ENTITY_DIM), dtype=np.float32)
    kinds = np.zeros((size, maximum), dtype=np.int64)
    mask = np.zeros((size, maximum), dtype=np.bool_)
    bounds = np.zeros((size, maximum, 4), dtype=np.float32)
    spatial = np.zeros((size, maximum), dtype=np.bool_)
    for index, state in enumerate(states):
        count = state.features.shape[0]
        features[index, :count] = state.features
        kinds[index, :count] = state.kinds
        bounds[index, :count] = state.bounds
        spatial[index, :count] = state.spatial
        mask[index, :count] = True

    def tensor(array: NDArray) -> Tensor:
        return torch.from_numpy(array).to(device)

    return EntityBatch(
        tensor(np.stack([state.globals for state in states])), tensor(features), tensor(kinds),
        tensor(mask), tensor(bounds), tensor(spatial),
        tensor(np.stack([state.capture_bounds for state in states])),
    )


class _EntityAttentionBlock(nn.Module):
    """Pre-norm player-to-entity attention followed by shared residual MLPs."""

    def __init__(self, config: EntityTeacherConfig) -> None:
        super().__init__()
        width, hidden = config.embed_dim, int(config.embed_dim * config.mlp_ratio)
        self.token_norm = nn.LayerNorm(width)
        self.query_norm = nn.LayerNorm(width)
        self.attention = nn.MultiheadAttention(
            width, config.num_heads, dropout=config.dropout, batch_first=True,
        )
        self.query_mlp_norm = nn.LayerNorm(width)
        self.token_mlp_norm = nn.LayerNorm(width)

        def mlp() -> nn.Sequential:
            return nn.Sequential(
                nn.Linear(width, hidden), nn.GELU(), nn.Dropout(config.dropout),
                nn.Linear(hidden, width), nn.Dropout(config.dropout),
            )

        self.query_mlp, self.token_mlp = mlp(), mlp()
        self.dropout = nn.Dropout(config.dropout)

    def forward(
        self, query: Tensor, tokens: Tensor, mask: Tensor,
        attention_bias: Tensor | None = None,
    ) -> tuple[Tensor, Tensor, Tensor]:
        # A shared token transform can represent each type's rich engine fields
        # without constructing an N-by-N attention matrix for the catalog.
        tokens = tokens + self.token_mlp(self.token_mlp_norm(tokens))
        normalized = self.token_norm(tokens)
        if attention_bias is None:
            # Keep the legacy numerical path when the prior is disabled.
            attended, weights = self.attention(
                self.query_norm(query), normalized, normalized,
                key_padding_mask=~mask, need_weights=True, average_attn_weights=True,
            )
        else:
            # One query attends to all valid keys. Only padding receives -inf;
            # catalog metadata keeps finite logits and remains eligible.
            additive_mask = attention_bias.masked_fill(~mask, -torch.inf)
            additive_mask = additive_mask[:, None, :].repeat_interleave(
                self.attention.num_heads, dim=0,
            )
            attended, weights = self.attention(
                self.query_norm(query), normalized, normalized,
                attn_mask=additive_mask, need_weights=True, average_attn_weights=True,
            )
        query = query + self.dropout(attended)
        query = query + self.query_mlp(self.query_mlp_norm(query))
        return query, tokens, weights[:, 0]


class EntityActorCritic(nn.Module):
    """Entity-transformer PPO teacher; no images or visibility gate enter policy."""

    def __init__(self, config: EntityTeacherConfig | None = None) -> None:
        super().__init__()
        if config is not None and not isinstance(config, EntityTeacherConfig):
            raise TypeError("config must be an EntityTeacherConfig")
        self.config = EntityTeacherConfig() if config is None else config
        width = self.config.embed_dim
        self.entity_projection = nn.Linear(ENTITY_DIM, width)
        self.kind_embedding = nn.Embedding(ENTITY_KIND_COUNT, width)
        if self.config.kind_embedding_scale != 1.0:
            # Rescale the existing draw so a controlled ablation consumes the
            # same initialization RNG sequence as the baseline.
            with torch.no_grad():
                self.kind_embedding.weight.mul_(self.config.kind_embedding_scale)
        self.global_projection = nn.Sequential(nn.Linear(GLOBAL_DIM, width), nn.GELU(), nn.Linear(width, width))
        self.blocks = nn.ModuleList(_EntityAttentionBlock(self.config) for _ in range(self.config.depth))
        self.output_norm = nn.LayerNorm(width)
        self.actor = nn.Linear(width, ACTION_COUNT)
        self.value = nn.Linear(width, 1)
        # PPO starts with an almost-uniform action distribution. A random
        # large policy head can make greedy actions collapse to a wall before
        # the trunk has learned geometry; value outputs retain unit gain.
        nn.init.orthogonal_(self.actor.weight, gain=0.01)
        nn.init.zeros_(self.actor.bias)
        nn.init.orthogonal_(self.value.weight, gain=1.0)
        nn.init.zeros_(self.value.bias)

    @staticmethod
    def _validate(batch: EntityBatch) -> None:
        if not isinstance(batch, EntityBatch):
            raise TypeError("batch must be an EntityBatch")
        if batch.globals.ndim != 2 or batch.globals.shape[0] < 1 or batch.globals.shape[1] != GLOBAL_DIM:
            raise ValueError(f"globals must have nonempty shape [batch, {GLOBAL_DIM}]")
        size = batch.globals.shape[0]
        if (
            batch.features.ndim != 3 or batch.features.shape[0] != size
            or batch.features.shape[2] != ENTITY_DIM
            or not 1 <= batch.features.shape[1] <= MAX_ENTITY_COUNT
        ):
            raise ValueError(f"features must have shape [batch, 1..{MAX_ENTITY_COUNT}, {ENTITY_DIM}]")
        shape = batch.features.shape[:2]
        for name, value, expected, dtype in (
            ("globals", batch.globals, (size, GLOBAL_DIM), torch.float32),
            ("features", batch.features, (*shape, ENTITY_DIM), torch.float32),
            ("kinds", batch.kinds, shape, torch.int64),
            ("mask", batch.mask, shape, torch.bool),
            ("bounds", batch.bounds, (*shape, 4), torch.float32),
            ("spatial", batch.spatial, shape, torch.bool),
            ("capture_bounds", batch.capture_bounds, (size, 4), torch.float32),
        ):
            if tuple(value.shape) != tuple(expected) or value.dtype != dtype:
                raise ValueError(f"{name} has an incompatible shape or dtype")
            if value.device != batch.globals.device:
                raise ValueError("all entity batch tensors must share a device")
        if not bool(batch.mask[:, 0].all()) or not bool((batch.kinds[:, 0] == 0).all()):
            raise ValueError("the first entity in every row must be a valid player")
        valid_kinds = batch.kinds[batch.mask]
        if bool(((valid_kinds < 0) | (valid_kinds >= ENTITY_KIND_COUNT)).any()):
            raise ValueError("valid entity kinds are outside the supported range")
        if bool(((batch.kinds[:, 1:] == 0) & batch.mask[:, 1:]).any()):
            raise ValueError("the first entity must be the only player")
        for name, value in (
            ("globals", batch.globals), ("features", batch.features[batch.mask]),
            ("bounds", batch.bounds[batch.mask]), ("capture_bounds", batch.capture_bounds),
        ):
            if not bool(torch.isfinite(value).all()):
                raise ValueError(f"{name} must contain finite valid values")

    def distillation_outputs(self, batch: EntityBatch) -> EntityTeacherOutput:
        self._validate(batch)
        # Invalid padding can contain arbitrary nonfinite values or out-of-range
        # kinds. Clear it before learned projections and embedding lookup.
        features = self._policy_features(batch)
        kinds = batch.kinds.masked_fill(~batch.mask, 0)
        attention_bias = self._attention_bias(batch, features, kinds)
        tokens = self.entity_projection(features) + self.kind_embedding(kinds)
        query = tokens[:, :1] + self.global_projection(batch.globals).unsqueeze(1)
        for block in self.blocks:
            if attention_bias is None:
                query, tokens, attention = block(query, tokens, batch.mask)
            else:
                query, tokens, attention = block(query, tokens, batch.mask, attention_bias)
        latent = self.output_norm(query[:, 0])
        return EntityTeacherOutput(self.actor(latent), self.value(latent).squeeze(-1), latent, attention)

    def _policy_features(self, batch: EntityBatch) -> Tensor:
        """Clean padding and optionally use invertible player-relative geometry.

        Enemy and rectangle prefixes share x, y, vx, vy units with the player.
        Warning prefixes contain two endpoint pairs instead. The player keeps
        its absolute kinematics, so these changes preserve the original data;
        no entity, hidden field, or offscreen object is removed.
        """
        features = batch.features.masked_fill(~batch.mask.unsqueeze(-1), 0.0)
        if not self.config.relative_geometry:
            return features
        player = features[:, :1, :4]
        physical = ((batch.kinds == 1) | (batch.kinds == 2)) & batch.mask
        warnings = (batch.kinds == 3) & batch.mask
        warning_origin = torch.cat((player[:, :, :2], player[:, :, :2]), dim=-1)
        prefix = torch.where(
            physical.unsqueeze(-1), features[:, :, :4] - player, features[:, :, :4],
        )
        prefix = torch.where(warnings.unsqueeze(-1), prefix - warning_origin, prefix)
        return torch.cat((prefix, features[:, :, 4:]), dim=-1)

    def _attention_bias(self, batch: EntityBatch, features: Tensor, kinds: Tensor) -> Tensor | None:
        """Finite prior for current physical objects, independent of visibility.

        Native schema 1 marks active rectangles in slot 16. Warning slots 4/7
        hold their parent pattern index and renderer-phase flag. Globals 20/21
        identify the active pattern. These native flags distinguish catalog
        definitions from current objects without discarding either group.
        """
        if self.config.attention_prior == 1.0:
            return None
        enemies = kinds == 1
        rectangles = (kinds == 2) & (features[:, :, 16] > 0.5)
        active_pattern = batch.globals[:, 20:21] > 0.5
        warning_parent = features[:, :, 4] == batch.globals[:, 21:22]
        warnings = (kinds == 3) & (features[:, :, 7] > 0.5) & active_pattern & warning_parent
        physical = (enemies | rectangles | warnings) & batch.mask
        return physical.to(dtype=features.dtype) * math.log(self.config.attention_prior)

    def forward(self, batch: EntityBatch) -> tuple[Tensor, Tensor]:
        output = self.distillation_outputs(batch)
        return output.logits, output.value
