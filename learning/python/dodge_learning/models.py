"""Optional PyTorch vision policy and policy-distillation objective.

Import this module explicitly after installing the learner's models extra. The
base environment, pixel utilities, and baseline evaluator do not need PyTorch.
"""

from __future__ import annotations

import math

import torch
from torch import Tensor, nn
from torch.nn import functional as F

IMAGE_CHANNELS = 12
IMAGE_SIZE = 128
ACTION_COUNT = 9


class VisionPolicy(nn.Module):
    """Map four RGB frames to nine action logits, without privileged inputs.

    Input shape is ``[batch, 12, 128, 128]``, oldest frame first, with each
    frame's RGB channels adjacent. The caller normalizes RGB values to [0, 1].
    The model returns unnormalized logits in the native action order.
    """

    def __init__(self) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(IMAGE_CHANNELS, 32, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.Conv2d(64, 64, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((4, 4)),
        )
        self.head = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 4 * 4, 256),
            nn.ReLU(),
            nn.Linear(256, ACTION_COUNT),
        )

    def forward(self, images: Tensor) -> Tensor:
        if not isinstance(images, Tensor):
            raise TypeError("images must be a PyTorch tensor")
        if images.ndim != 4 or tuple(images.shape[1:]) != (
            IMAGE_CHANNELS,
            IMAGE_SIZE,
            IMAGE_SIZE,
        ):
            raise ValueError("images must have shape [batch, 12, 128, 128]")
        if images.shape[0] == 0:
            raise ValueError("image batch must not be empty")
        if not images.is_floating_point():
            raise TypeError("images must be normalized floating-point RGB values")
        return self.head(self.features(images))


def distillation_loss(
    student_logits: Tensor,
    teacher_logits: Tensor,
    temperature: float = 1.0,
) -> Tensor:
    """Return T² KL(teacher || student), averaged over decisions.

    Teacher logits are detached before constructing targets. This objective
    trains only the student; it does not establish teacher quality or gameplay
    performance. Both tensors must be finite, matching [batch, 9] logits on the
    same device and with the same floating-point dtype.
    """

    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise ValueError("temperature must be a finite positive number")
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("temperature must be a finite positive number")
    if not math.isfinite(temperature * temperature):
        raise ValueError("temperature squared must be finite")
    for name, logits in (("student", student_logits), ("teacher", teacher_logits)):
        if not isinstance(logits, Tensor):
            raise TypeError(f"{name} logits must be a PyTorch tensor")
        if logits.ndim != 2 or logits.shape[1] != ACTION_COUNT or logits.shape[0] == 0:
            raise ValueError(f"{name} logits must have nonempty shape [batch, 9]")
        if not logits.is_floating_point():
            raise TypeError(f"{name} logits must be floating-point values")
        if not bool(torch.isfinite(logits.detach()).all()):
            raise ValueError(f"{name} logits must be finite")
    if student_logits.shape != teacher_logits.shape:
        raise ValueError("student and teacher logits must have matching shapes")
    if student_logits.device != teacher_logits.device:
        raise ValueError("student and teacher logits must use the same device")
    if student_logits.dtype != teacher_logits.dtype:
        raise ValueError("student and teacher logits must use the same dtype")

    student_log_probs = F.log_softmax(student_logits / temperature, dim=-1)
    teacher_log_probs = F.log_softmax(teacher_logits.detach() / temperature, dim=-1)
    loss = F.kl_div(
        student_log_probs,
        teacher_log_probs,
        reduction="batchmean",
        log_target=True,
    ) * (temperature * temperature)
    if not bool(torch.isfinite(loss.detach())):
        raise ValueError("temperature produces a nonfinite distillation loss")
    return loss
