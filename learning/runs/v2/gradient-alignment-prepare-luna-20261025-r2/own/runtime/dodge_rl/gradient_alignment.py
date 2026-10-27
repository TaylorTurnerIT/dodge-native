"""Measurement-only shared-trunk gradient alignment summaries."""
from __future__ import annotations

import math
import torch


def summarize(actor_grads, critic_grads, named_parameters, *, metadata):
    """Summarize aligned gradient tuples; missing gradients count as zeros."""
    named_parameters = list(named_parameters)
    names = [name for name, _ in named_parameters]
    params = [p for _, p in named_parameters]
    if len(actor_grads) != len(params) or len(critic_grads) != len(params):
        raise ValueError("gradient tuple count differs from named shared parameter count")
    a_parts, c_parts = [], []
    coverage = {"actor_used": 0, "critic_used": 0, "parameters": len(params), "elements": 0}
    groups = {}
    for i, (name, p) in enumerate(named_parameters):
        ga, gc = actor_grads[i], critic_grads[i]
        for objective, grad in (("actor", ga), ("critic", gc)):
            if grad is not None:
                if tuple(grad.shape) != tuple(p.shape):
                    raise ValueError(f"{objective} gradient shape mismatch for {name}: {tuple(grad.shape)} != {tuple(p.shape)}")
                bad = ~torch.isfinite(grad)
                if bool(bad.any().item()):
                    coord = tuple(int(x) for x in bad.nonzero()[0].tolist())
                    raise FloatingPointError(f"nonfinite {objective} gradient for {name} at {coord}")
        coverage["elements"] += p.numel()
        coverage["actor_used"] += int(ga is not None)
        coverage["critic_used"] += int(gc is not None)
        # Explicit source-device -> CPU float32 transfer, then CPU float64 reduction.
        av = torch.zeros_like(p) if ga is None else ga.detach()
        cv = torch.zeros_like(p) if gc is None else gc.detach()
        acpu = av.to(device="cpu", dtype=torch.float32).to(dtype=torch.float64)
        ccpu = cv.to(device="cpu", dtype=torch.float32).to(dtype=torch.float64)
        for objective, copied in (("actor", acpu), ("critic", ccpu)):
            bad = ~torch.isfinite(copied)
            if bool(bad.any()):
                coord = tuple(int(x) for x in bad.nonzero()[0].tolist())
                raise FloatingPointError(f"nonfinite {objective} CPU copy for {name} at {coord}")
        a_parts.append(acpu.reshape(-1))
        c_parts.append(ccpu.reshape(-1))
        if name.startswith("layers."):
            group = ".".join(name.split(".")[:2])
        elif name.startswith(("global_projection", "entity_projection", "type_embedding")):
            group = "embeddings_and_input_projections"
        else:
            group = "remaining_shared_parameters"
        groups.setdefault(group, [[], []])
        groups[group][0].append(a_parts[-1]); groups[group][1].append(c_parts[-1])

    def values(a, c):
        av, cv = torch.cat(a), torch.cat(c)
        dot = float(torch.dot(av, cv))
        an, cn = float(torch.linalg.vector_norm(av)), float(torch.linalg.vector_norm(cv))
        if not all(map(math.isfinite, (dot, an, cn))):
            raise FloatingPointError("nonfinite gradient alignment reduction")
        out = {"dot": dot, "actor_norm": an, "weighted_critic_norm": cn}
        if an > 0:
            out["norm_ratio_critic_over_actor"] = cn / an
        if an > 0 and cn > 0:
            out["cosine"] = dot / (an * cn)
            out["defined"] = True
        else:
            out["defined"] = False
            out["zero_norm_reason"] = "actor_gradient_zero" if an == 0 else "critic_gradient_zero"
        return out

    return {**values(a_parts, c_parts), "groups": {k: values(*v) for k, v in groups.items()},
            "coverage": coverage, **metadata,
            "objectives": {"actor": "policy_loss - ent_coef * entropy", "critic": "vf_coef * value_loss"},
            "interpretation": "negative cosine opposes; near zero is orthogonal; positive aligns. Raw gradients do not establish Adam update interference or behavioral harm."}
