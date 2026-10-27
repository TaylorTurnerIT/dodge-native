"""Action, latent, and spatial-attention bridges for the image-only student.

These objectives transfer a frozen teacher's outputs; they do not establish
teacher competence. Spatial targets use only rendered hazard footprints. A
teacher may use hidden state without pretending that hidden geometry exists in
the current image. Every teacher target is detached inside this module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch
from torch import Tensor
from torch.nn import functional as F

from .models import distillation_loss


@dataclass(frozen=True)
class DistillationConfig:
    action_weight: float = 1.0
    latent_weight: float = 1.0
    attention_weight: float = 1.0
    temperature: float = 1.0

    def __post_init__(self) -> None:
        for name in ("action_weight", "latent_weight", "attention_weight"):
            value = getattr(self, name)
            if (
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not 0 <= value <= 1_000_000 or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be finite and in [0, 1000000]")
        if not any((self.action_weight, self.latent_weight, self.attention_weight)):
            raise ValueError("at least one distillation loss weight must be positive")
        if (
            isinstance(self.temperature, bool) or not isinstance(self.temperature, (int, float))
            or not 0.01 <= self.temperature <= 100 or not math.isfinite(self.temperature)
        ):
            raise ValueError("temperature must be finite and in [0.01, 100]")


@dataclass(frozen=True)
class DistillationLosses:
    total: Tensor
    action: Tensor
    latent: Tensor
    attention: Tensor
    attention_rows: int


def _float_tensor(value: Tensor, name: str) -> None:
    if not isinstance(value, Tensor):
        raise TypeError(f"{name} must be a PyTorch tensor")
    if not value.is_floating_point():
        raise TypeError(f"{name} must contain floating-point values")


def _same_tensor_format(reference: Tensor, value: Tensor, name: str) -> None:
    _float_tensor(value, name)
    if value.device != reference.device or value.dtype != reference.dtype:
        raise ValueError(f"{name} must match the reference device and dtype")


def _grid_dimensions(grid_size: int, image_size: int) -> None:
    for name, value in (("grid_size", grid_size), ("image_size", image_size)):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 4096:
            raise ValueError(f"{name} must be an integer from 1 to 4096")
    if grid_size > image_size:
        raise ValueError("grid_size must not exceed image_size")


def teacher_attention_to_grid(
    attention: Tensor,
    bounds: Tensor,
    spatial_mask: Tensor,
    entity_mask: Tensor,
    capture_bounds: Tensor,
    grid_size: int,
    image_size: int = 128,
) -> tuple[Tensor, Tensor]:
    """Project entity attention to a row-major grid using visible area overlap.

    Bounds and capture bounds are half-open game-image pixel intervals
    ``[x0, y0, x1, y1]``. Native capture cancels camera translation, so clipped
    geometry retains its original game-image coordinates. Each spatial entity
    distributes its weight uniformly over its clipped footprint. Zero-width
    axes receive a one-pixel footprint, covering points and warning lines.
    Offscreen or nonspatial entities contribute no target mass. The result is
    normalized across representable mass; rows with none return zeros and a
    false validity flag. No padding or hidden geometry is moved to an edge.

    The projection detaches every argument. It supervises the student without
    fitting the teacher or giving the student privileged forward inputs.
    """
    _grid_dimensions(grid_size, image_size)
    _float_tensor(attention, "attention")
    if attention.ndim != 2 or not all(attention.shape):
        raise ValueError("attention must have nonempty shape [batch, entities]")
    batch, count = attention.shape
    _same_tensor_format(attention, bounds, "bounds")
    _same_tensor_format(attention, capture_bounds, "capture_bounds")
    if bounds.shape != (batch, count, 4) or capture_bounds.shape != (batch, 4):
        raise ValueError("bounds/capture_bounds must have shapes [batch, entities, 4]/[batch, 4]")
    for name, mask in (("spatial_mask", spatial_mask), ("entity_mask", entity_mask)):
        if not isinstance(mask, Tensor) or mask.dtype != torch.bool:
            raise TypeError(f"{name} must be a boolean tensor")
        if mask.shape != attention.shape or mask.device != attention.device:
            raise ValueError(f"{name} must match attention shape and device")
    active = spatial_mask & entity_mask
    if not bool(torch.isfinite(attention.masked_select(entity_mask)).all()):
        raise ValueError("valid entity attention must be finite")
    if bool((attention.masked_select(entity_mask) < 0).any()):
        raise ValueError("valid entity attention must be nonnegative")
    if not bool(torch.isfinite(bounds[active]).all()) or not bool(torch.isfinite(capture_bounds).all()):
        raise ValueError("spatial bounds and capture bounds must be finite")
    if bool((bounds[active, 2:] < bounds[active, :2]).any()):
        raise ValueError("spatial bounds must have ordered endpoints")
    if bool((capture_bounds[:, 2:] < capture_bounds[:, :2]).any()):
        raise ValueError("capture bounds must have ordered endpoints")

    with torch.no_grad():
        weights = attention.detach().masked_fill(~active, 0)
        geometry = bounds.detach().masked_fill(~active.unsqueeze(-1), 0)
        lower = geometry[:, :, :2]
        upper = geometry[:, :, 2:]
        upper = torch.where(upper == lower, lower + 1, upper)
        capture_lower = capture_bounds.detach()[:, None, :2].clamp(0, image_size)
        capture_upper = capture_bounds.detach()[:, None, 2:].clamp(0, image_size)
        lower = torch.maximum(lower, capture_lower)
        upper = torch.minimum(upper, capture_upper)

        edges = torch.linspace(0, image_size, grid_size + 1, device=attention.device, dtype=attention.dtype)
        overlap_x = (
            torch.minimum(upper[:, :, 0, None], edges[1:])
            - torch.maximum(lower[:, :, 0, None], edges[:-1])
        ).clamp_min(0)
        overlap_y = (
            torch.minimum(upper[:, :, 1, None], edges[1:])
            - torch.maximum(lower[:, :, 1, None], edges[:-1])
        ).clamp_min(0)
        areas = (overlap_y.unsqueeze(-1) * overlap_x.unsqueeze(-2)).flatten(2)
        visible_area = areas.sum(dim=-1, keepdim=True)
        per_entity = areas / visible_area.clamp_min(torch.finfo(areas.dtype).tiny)
        target = (weights.unsqueeze(-1) * per_entity).sum(dim=1)
        mass = target.sum(dim=-1, keepdim=True)
        valid_rows = mass.squeeze(-1) > 0
        target = target / mass.clamp_min(torch.finfo(target.dtype).tiny)
    return target, valid_rows


def distillation_losses(
    student_logits: Tensor,
    student_latent: Tensor,
    student_attention: Tensor,
    teacher_logits: Tensor,
    teacher_latent: Tensor,
    teacher_attention: Tensor,
    bounds: Tensor,
    spatial_mask: Tensor,
    entity_mask: Tensor,
    capture_bounds: Tensor,
    *,
    grid_size: int,
    config: DistillationConfig | None = None,
) -> DistillationLosses:
    """Return weighted action KL, normalized-latent MSE, and attention KL.

    Latent matching compares L2-normalized vectors, keeping its scale separate
    from policy-logit magnitude. Spatial KL is averaged over rows with visible
    target mass. With no visible hazard mass, it returns differentiable zero.
    All three bridges are enabled by default; explicit zero weights support
    controlled ablations. Teacher parameters never receive these gradients.
    """
    if config is not None and not isinstance(config, DistillationConfig):
        raise TypeError("config must be a DistillationConfig")
    config = DistillationConfig() if config is None else config
    _grid_dimensions(grid_size, 128)
    action = distillation_loss(student_logits, teacher_logits, config.temperature)
    for name, value in (
        ("student_latent", student_latent), ("teacher_latent", teacher_latent),
        ("student_attention", student_attention), ("teacher_attention", teacher_attention),
    ):
        _same_tensor_format(student_logits, value, name)
    batch = student_logits.shape[0]
    if student_latent.ndim != 2 or student_latent.shape[0] != batch or not student_latent.shape[1]:
        raise ValueError("student_latent must have nonempty shape [batch, latent]")
    if teacher_latent.shape != student_latent.shape:
        raise ValueError("teacher/student latents must have matching shapes")
    if student_attention.shape != (batch, grid_size * grid_size):
        raise ValueError("student_attention must have shape [batch, grid_size squared]")
    for name, value in (
        ("student_latent", student_latent), ("teacher_latent", teacher_latent),
        ("student_attention", student_attention),
    ):
        if not bool(torch.isfinite(value.detach()).all()):
            raise ValueError(f"{name} must be finite")
    if bool((student_attention.detach() < 0).any()) or not torch.allclose(
        student_attention.detach().sum(dim=-1),
        torch.ones(batch, device=student_logits.device, dtype=student_logits.dtype),
        atol=1e-5, rtol=1e-5,
    ):
        raise ValueError("student_attention must contain normalized nonnegative distributions")

    latent = F.mse_loss(F.normalize(student_latent, dim=-1), F.normalize(teacher_latent.detach(), dim=-1))
    target, valid_rows = teacher_attention_to_grid(
        teacher_attention, bounds, spatial_mask, entity_mask, capture_bounds, grid_size
    )
    if target.shape[0] != batch:
        raise ValueError("teacher and student attention must have matching batch dimensions")
    attention_rows = int(valid_rows.sum().item())
    if attention_rows:
        attention_loss = F.kl_div(
            student_attention[valid_rows].clamp_min(torch.finfo(student_attention.dtype).tiny).log(),
            target[valid_rows], reduction="batchmean",
        )
    else:
        attention_loss = student_attention.sum() * 0.0
    total = (
        config.action_weight * action + config.latent_weight * latent
        + config.attention_weight * attention_loss
    )
    if not bool(torch.isfinite(total.detach())):
        raise ValueError("distillation produced a nonfinite loss")
    return DistillationLosses(total, action, latent, attention_loss, attention_rows)
