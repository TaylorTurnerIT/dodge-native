"""Full self-attention teacher for the allowlisted M2 entity observations.

The model consumes only the four neural buffers. Episode IDs, seed streams,
diagnostic counters, and hidden engine state are not model inputs. Attention
weights are returned to the caller for diagnostics; this module never retains
them between calls.
"""

from dataclasses import dataclass
import math

import torch
from torch import Tensor, nn


GLOBAL_FEAT_DIM = 14
ENTITY_FEAT_DIM = 16
MAX_ENTITIES = 80
TOKEN_COUNT = MAX_ENTITIES + 1
MODEL_DIM = 128
NUM_LAYERS = 2
NUM_HEADS = 4
FFN_DIM = 256
NUM_ACTIONS = 9
LAYERNORM_EPS = 1e-5
MODEL_VERSION = "omniscient_entity_teacher_full_attention_v1"


@dataclass(frozen=True, slots=True)
class TeacherOutput:
    """One forward result; values are in the learner's reward units."""

    logits: Tensor
    values: Tensor
    latent: Tensor
    attentions: tuple[Tensor, Tensor]


class CustomTransformerLayer(nn.Module):
    """Pre-norm full self-attention with explicitly returned attention weights."""

    def __init__(self) -> None:
        super().__init__()
        self.norm1 = nn.LayerNorm(MODEL_DIM, eps=LAYERNORM_EPS)
        self.mha = nn.MultiheadAttention(
            MODEL_DIM, NUM_HEADS, dropout=0.0, batch_first=True
        )
        self.norm2 = nn.LayerNorm(MODEL_DIM, eps=LAYERNORM_EPS)
        self.ffn = nn.Sequential(
            nn.Linear(MODEL_DIM, FFN_DIM),
            nn.GELU(),
            nn.Linear(FFN_DIM, MODEL_DIM),
        )

    def forward(self, tokens: Tensor, key_padding_mask: Tensor) -> tuple[Tensor, Tensor]:
        normalized = self.norm1(tokens)
        attended, weights = self.mha(
            normalized,
            normalized,
            normalized,
            key_padding_mask=key_padding_mask,
            need_weights=True,
            average_attn_weights=True,
        )
        if weights is None:
            raise RuntimeError("Teacher attention weights were not returned")
        tokens = tokens + attended
        return tokens + self.ffn(self.norm2(tokens)), weights


class OmniscientEntityTeacher(nn.Module):
    """Fixed 81-token, width-128 teacher from the registered v2 training plan.

    Inputs must use the M2 float32/int64/bool layout. True entity-mask entries
    mean valid entities. Masked rows are sanitized before embedding, so their
    values and type IDs cannot affect the player token, even if callers replace
    padding values with nonfinite sentinels. Valid-row finiteness and the
    type-1..8 allowlist are enforced by the environment/rollout boundary.
    """

    def __init__(self) -> None:
        super().__init__()
        self.global_projection = nn.Linear(GLOBAL_FEAT_DIM, MODEL_DIM)
        self.entity_projection = nn.Sequential(
            nn.Linear(ENTITY_FEAT_DIM, MODEL_DIM),
            nn.GELU(),
            nn.Linear(MODEL_DIM, MODEL_DIM),
        )
        self.type_embedding = nn.Embedding(9, MODEL_DIM)
        self.layers = nn.ModuleList(CustomTransformerLayer() for _ in range(NUM_LAYERS))
        self.final_norm = nn.LayerNorm(MODEL_DIM, eps=LAYERNORM_EPS)
        self.actor_head = nn.Sequential(
            nn.Linear(MODEL_DIM, MODEL_DIM),
            nn.GELU(),
            nn.Linear(MODEL_DIM, NUM_ACTIONS),
        )
        self.critic_head = nn.Sequential(
            nn.Linear(MODEL_DIM, MODEL_DIM),
            nn.GELU(),
            nn.Linear(MODEL_DIM, 1),
        )
        self._initialize_head(self.actor_head, final_gain=0.01)
        self._initialize_head(self.critic_head, final_gain=1.0)

    @staticmethod
    def _initialize_head(head: nn.Sequential, final_gain: float) -> None:
        for index, gain in ((0, math.sqrt(2.0)), (2, final_gain)):
            layer = head[index]
            nn.init.orthogonal_(layer.weight, gain=gain)
            nn.init.zeros_(layer.bias)

    @staticmethod
    def _validate_inputs(
        global_feats: Tensor,
        entity_feats: Tensor,
        entity_types: Tensor,
        entity_mask: Tensor,
    ) -> None:
        values = (global_feats, entity_feats, entity_types, entity_mask)
        if not all(isinstance(value, Tensor) for value in values):
            raise TypeError("Teacher inputs must be torch.Tensor objects")
        if global_feats.ndim != 3 or global_feats.shape[1:] != (1, GLOBAL_FEAT_DIM):
            raise ValueError("global_feats must have shape [B,1,14]")
        batch = global_feats.shape[0]
        if batch == 0:
            raise ValueError("Teacher batch must contain at least one observation")
        expected = (
            (batch, MAX_ENTITIES, ENTITY_FEAT_DIM),
            (batch, MAX_ENTITIES),
            (batch, MAX_ENTITIES),
        )
        names = ("entity_feats", "entity_types", "entity_mask")
        for name, value, shape in zip(names, values[1:], expected, strict=True):
            if value.shape != shape:
                raise ValueError(f"{name} must have shape {shape}")
        if global_feats.dtype != torch.float32 or entity_feats.dtype != torch.float32:
            raise TypeError("Teacher floating inputs must use torch.float32")
        if entity_types.dtype != torch.int64:
            raise TypeError("entity_types must use torch.int64")
        if entity_mask.dtype != torch.bool:
            raise TypeError("entity_mask must use torch.bool")
        if any(value.device != global_feats.device for value in values[1:]):
            raise ValueError("Teacher inputs must share one device")

    def forward(
        self,
        global_feats: Tensor,
        entity_feats: Tensor,
        entity_types: Tensor,
        entity_mask: Tensor,
    ) -> TeacherOutput:
        latent, attentions = self.encode(global_feats, entity_feats, entity_types, entity_mask)
        return TeacherOutput(
            logits=self.actor_head(latent),
            values=self.critic_head(latent).squeeze(-1),
            latent=latent,
            attentions=attentions,
        )

    def encode(
        self,
        global_feats: Tensor,
        entity_feats: Tensor,
        entity_types: Tensor,
        entity_mask: Tensor,
    ) -> tuple[Tensor, tuple[Tensor, Tensor]]:
        """Return the unchanged legacy latent/attention without running heads."""
        self._validate_inputs(global_feats, entity_feats, entity_types, entity_mask)
        batch = global_feats.shape[0]
        entity_feats = entity_feats.masked_fill(~entity_mask.unsqueeze(-1), 0.0)
        entity_types = entity_types.masked_fill(~entity_mask, 0)
        global_types = torch.zeros((batch, 1), dtype=torch.int64, device=entity_types.device)
        global_token = self.global_projection(global_feats) + self.type_embedding(global_types)
        entities = self.entity_projection(entity_feats) + self.type_embedding(entity_types)
        tokens = torch.cat((global_token, entities), dim=1)
        # Token zero is always a valid key, including completely empty scenes.
        key_padding_mask = torch.cat(
            (
                torch.zeros((batch, 1), dtype=torch.bool, device=entity_mask.device),
                ~entity_mask,
            ),
            dim=1,
        )
        attention_weights = []
        for layer in self.layers:
            tokens, weights = layer(tokens, key_padding_mask)
            attention_weights.append(weights)
        latent = self.final_norm(tokens)[:, 0, :]
        return latent, (attention_weights[0], attention_weights[1])

    def architecture_description(self) -> dict:
        """Return a fresh JSON-compatible description for checkpoint identities."""
        return {
            "version": MODEL_VERSION,
            "class": type(self).__name__,
            "global_shape": [1, GLOBAL_FEAT_DIM],
            "entity_shape": [MAX_ENTITIES, ENTITY_FEAT_DIM],
            "entity_type_vocab_size": 9,
            "entity_valid_types": list(range(1, 9)),
            "entity_mask_true_means_valid": True,
            "token_count": TOKEN_COUNT,
            "model_dim": MODEL_DIM,
            "num_layers": NUM_LAYERS,
            "num_heads": NUM_HEADS,
            "ffn_dim": FFN_DIM,
            "activation": "gelu",
            "normalization": "pre_norm_plus_final_layernorm",
            "layernorm_eps": LAYERNORM_EPS,
            "dropout": 0.0,
            "attention": "full_self_attention",
            "need_weights": True,
            "average_attn_weights": True,
            "entity_position_embeddings": False,
            "global_embedding": [GLOBAL_FEAT_DIM, MODEL_DIM],
            "entity_embedding": [ENTITY_FEAT_DIM, MODEL_DIM, MODEL_DIM],
            "actor_head": [MODEL_DIM, MODEL_DIM, NUM_ACTIONS],
            "critic_head": [MODEL_DIM, MODEL_DIM, 1],
            "head_initialization": {
                "method": "orthogonal_weights_zero_biases",
                "hidden_gain": math.sqrt(2.0),
                "actor_final_gain": 0.01,
                "critic_final_gain": 1.0,
            },
            "trunk_initialization": "pytorch_default",
            "parameter_count": sum(parameter.numel() for parameter in self.parameters()),
        }
