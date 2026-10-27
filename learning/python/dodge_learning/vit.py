"""Optional compact vision transformer for four-frame Dodge image histories."""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch
from torch import Tensor, nn

IMAGE_CHANNELS = 4
IMAGE_SIZE = 128
ACTION_COUNT = 9


@dataclass(frozen=True)
class ViTConfig:
    """Bound the initial transformer experiments for the local Mac.

    The default 16-pixel patches produce an 8 by 8 grid of 64 spatial tokens.
    Patch sizes 8 and 4 produce 256 and 1,024 spatial tokens, respectively.
    Frames are fused into channels before patch embedding; they do not multiply
    the spatial sequence length.
    """

    patch_size: int = 16
    embed_dim: int = 128
    depth: int = 4
    num_heads: int = 4
    mlp_ratio: float = 2.0
    dropout: float = 0.0

    def __post_init__(self) -> None:
        for name, lower, upper in (
            ("embed_dim", 8, 512),
            ("depth", 1, 12),
            ("num_heads", 1, 16),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
                raise ValueError(f"{name} must be an integer from {lower} to {upper}")
        if isinstance(self.patch_size, bool) or self.patch_size not in (4, 8, 16):
            raise ValueError("patch_size must be 4, 8, or 16")
        if not isinstance(self.patch_size, int):
            raise ValueError("patch_size must be 4, 8, or 16")
        if self.embed_dim % self.num_heads:
            raise ValueError("embed_dim must be divisible by num_heads")
        for name, lower, upper, inclusive_upper in (
            ("mlp_ratio", 1.0, 8.0, True),
            ("dropout", 0.0, 1.0, False),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value < lower
                or (value > upper if inclusive_upper else value >= upper)
                or not math.isfinite(value)
            ):
                end = "inclusive" if inclusive_upper else "exclusive"
                raise ValueError(f"{name} must be finite from {lower} to {upper} ({end} upper bound)")

    @property
    def num_tokens(self) -> int:
        return (IMAGE_SIZE // self.patch_size) ** 2


class _TransformerBlock(nn.Module):
    """Pre-norm self-attention and feed-forward residual branches."""

    def __init__(self, config: ViTConfig) -> None:
        super().__init__()
        self.attention_norm = nn.LayerNorm(config.embed_dim)
        self.attention = nn.MultiheadAttention(
            config.embed_dim,
            config.num_heads,
            dropout=config.dropout,
            batch_first=True,
        )
        self.attention_dropout = nn.Dropout(config.dropout)
        self.mlp_norm = nn.LayerNorm(config.embed_dim)
        hidden_dim = int(config.embed_dim * config.mlp_ratio)
        self.mlp = nn.Sequential(
            nn.Linear(config.embed_dim, hidden_dim),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(hidden_dim, config.embed_dim),
            nn.Dropout(config.dropout),
        )

    def forward(self, tokens: Tensor) -> Tensor:
        normalized = self.attention_norm(tokens)
        attended, _ = self.attention(
            normalized, normalized, normalized, need_weights=False
        )
        tokens = tokens + self.attention_dropout(attended)
        return tokens + self.mlp(self.mlp_norm(tokens))


@dataclass(frozen=True)
class ViTOutput:
    """Image-derived policy, latent, and the patch weights used to pool that latent."""

    logits: Tensor
    latent: Tensor
    attention: Tensor


class ViTPolicy(nn.Module):
    """Map only [batch, 4, 128, 128] image tensors to nine action logits.

    The caller supplies four consecutive grayscale frames, oldest first,
    using palette-derived luminance normalized to [0, 1]. Learned positions
    preserve spatial information before learned attention pooling. There
    are no privileged-state, metadata, or teacher inputs to the actor.
    """

    def __init__(self, config: ViTConfig | None = None) -> None:
        super().__init__()
        if config is not None and not isinstance(config, ViTConfig):
            raise TypeError("config must be a ViTConfig or None")
        self.config = ViTConfig() if config is None else config
        self.patch_embed = nn.Conv2d(
            IMAGE_CHANNELS,
            self.config.embed_dim,
            kernel_size=self.config.patch_size,
            stride=self.config.patch_size,
        )
        self.position_embedding = nn.Parameter(
            torch.empty(1, self.config.num_tokens, self.config.embed_dim)
        )
        nn.init.trunc_normal_(self.position_embedding, std=0.02)
        self.embedding_dropout = nn.Dropout(self.config.dropout)
        self.blocks = nn.ModuleList(
            _TransformerBlock(self.config) for _ in range(self.config.depth)
        )
        self.output_norm = nn.LayerNorm(self.config.embed_dim)
        self.attention_score = nn.Linear(self.config.embed_dim, 1, bias=False)
        self.head = nn.Linear(self.config.embed_dim, ACTION_COUNT)

    def forward(self, images: Tensor) -> Tensor:
        return self.distillation_outputs(images).logits

    def distillation_outputs(self, images: Tensor) -> ViTOutput:
        """Expose all three training outputs without adding deployment inputs.

        Attention is the learned distribution that pools patch features into
        the action latent. Its supervision therefore changes the policy path,
        rather than fitting a disconnected visualization head.
        """
        if not isinstance(images, Tensor):
            raise TypeError("images must be a PyTorch tensor")
        if images.ndim != 4 or tuple(images.shape[1:]) != (
            IMAGE_CHANNELS,
            IMAGE_SIZE,
            IMAGE_SIZE,
        ):
            raise ValueError("images must have shape [batch, 4, 128, 128]")
        if images.shape[0] == 0:
            raise ValueError("image batch must not be empty")
        if not images.is_floating_point():
            raise TypeError("images must be normalized floating-point grayscale values")
        if not bool(torch.isfinite(images).all()) or bool(((images < 0) | (images > 1)).any()):
            raise ValueError("images must contain finite values in [0, 1]")
        tokens = self.patch_embed(images).flatten(2).transpose(1, 2)
        tokens = self.embedding_dropout(tokens + self.position_embedding)
        for block in self.blocks:
            tokens = block(tokens)
        tokens = self.output_norm(tokens)
        attention = self.attention_score(tokens).squeeze(-1).softmax(dim=-1)
        latent = torch.sum(attention.unsqueeze(-1) * tokens, dim=1)
        return ViTOutput(self.head(latent), latent, attention)
