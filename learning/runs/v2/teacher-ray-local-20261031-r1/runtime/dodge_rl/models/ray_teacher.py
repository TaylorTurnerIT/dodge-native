"""Zero-gated R0 residual with CPU geometry and CPU/MPS learned parameters."""

import torch
from torch import Tensor, nn

from ..clearance_rays import (
    FEATURE_NAMES, RAY_FEATURE_DIM, RAY_SCHEMA,
)
from .teacher import MODEL_DIM, OmniscientEntityTeacher, TeacherOutput


class RayGeometryTeacher(nn.Module):
    """Add a zero-gated 46→64→128 branch to a supplied synthetic CPU teacher.

    The legacy model's parameters stay trainable and retain their values. New
    names are deliberately distinct; this class does not migrate checkpoint or
    optimizer state. Constructing the branch preserves the caller's CPU RNG.
    """

    cpu_geometry_inputs = True

    @property
    def actor_head(self):
        return self.legacy.actor_head

    @property
    def critic_head(self):
        return self.legacy.critic_head

    def __init__(self, legacy: OmniscientEntityTeacher, *, branch_seed: int = 0):
        super().__init__()
        if not isinstance(legacy, OmniscientEntityTeacher):
            raise TypeError("legacy must be an OmniscientEntityTeacher")
        if type(branch_seed) is not int or not 0 <= branch_seed < 2**63:
            raise ValueError("branch_seed must be an integer in [0,2**63)")
        if any(p.device.type != "cpu" or p.dtype != torch.float32 for p in legacy.parameters()):
            raise ValueError("R0 adapter currently supports float32 CPU parameters only")
        self.legacy = legacy
        with torch.random.fork_rng(devices=[]):
            torch.random.default_generator.manual_seed(branch_seed)
            self.branch = nn.Sequential(
                nn.Linear(RAY_FEATURE_DIM, 64, device="cpu", dtype=torch.float32),
                nn.GELU(),
                nn.Linear(64, MODEL_DIM, device="cpu", dtype=torch.float32),
            )
        self.gate = nn.Parameter(torch.zeros((), device="cpu", dtype=torch.float32))

    def forward(
        self, global_feats: Tensor, entity_feats: Tensor,
        entity_types: Tensor, entity_mask: Tensor,
    ) -> TeacherOutput:
        self.legacy._validate_inputs(global_feats, entity_feats, entity_types, entity_mask)
        from ..ray_frontend import batched_clearance_rays
        if global_feats.device.type != "cpu":
            raise ValueError("R0 adapter requires original CPU arrays")
        device = self.gate.device
        if device.type not in ("cpu", "mps") or any(
            p.device != device or p.dtype != torch.float32 for p in self.parameters()
        ):
            raise ValueError("R0 requires one float32 CPU/MPS parameter device")
        ray_tensor = batched_clearance_rays(
            global_feats, entity_feats, entity_types, entity_mask,
        ).to(device)
        legacy_latent, attentions = self.legacy.encode(
            *(value.to(device) for value in (global_feats, entity_feats, entity_types, entity_mask)),
        )
        latent = legacy_latent + self.gate * self.branch(ray_tensor)
        return TeacherOutput(
            logits=self.legacy.actor_head(latent),
            values=self.legacy.critic_head(latent).squeeze(-1),
            latent=latent, attentions=attentions,
        )

    def architecture_description(self) -> dict:
        return {
            "version": "entity_teacher_r0_cpu_geometry_mps_branch_v2",
            "legacy": self.legacy.architecture_description(),
            "ray_schema": RAY_SCHEMA,
            "ray_features": list(FEATURE_NAMES),
            "branch": [RAY_FEATURE_DIM, 64, MODEL_DIM],
            "residual": "legacy_final_norm_latent + scalar_gate * branch",
            "initial_gate": 0.0,
            "parameter_count": sum(p.numel() for p in self.parameters()),
            "geometry_device": "cpu_float64_before_single_transfer",
        }
