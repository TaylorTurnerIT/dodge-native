"""Measurement-only shared-trunk gradient alignment summaries."""
from __future__ import annotations

import math
import torch


def summarize(actor_grads, critic_grads, named_parameters, *, metadata):
    """Summarize aligned gradient tuples; missing gradients count as zeros."""
    names = [name for name, _ in named_parameters]
    params = [p for _, p in named_parameters]
    a_parts, c_parts = [], []
    coverage = {"actor_used": 0, "critic_used": 0, "parameters": len(params), "elements": 0}
    groups = {}
    for i, (name, p) in enumerate(zip(names, params)):
        ga, gc = actor_grads[i], critic_grads[i]
        coverage["elements"] += p.numel()
        coverage["actor_used"] += int(ga is not None)
        coverage["critic_used"] += int(gc is not None)
        av = torch.zeros_like(p) if ga is None else ga
        cv = torch.zeros_like(p) if gc is None else gc
        a_parts.append(av.detach().reshape(-1).to(device="cpu", dtype=torch.float64))
        c_parts.append(cv.detach().reshape(-1).to(device="cpu", dtype=torch.float64))
        if name.startswith("layers."):
            group = ".".join(name.split(".")[:2])
        elif name.startswith("global_projection") or name.startswith("entity_projection") or name.startswith("type_embedding"):
            group = "embeddings_and_input_projections"
        else:
            group = "remaining_shared_parameters"
        if group not in groups:
            groups[group] = [[], []]
        groups[group][0].append(a_parts[-1]); groups[group][1].append(c_parts[-1])

    def values(a, c):
        av, cv = torch.cat(a), torch.cat(c)
        dot = float(torch.dot(av, cv))
        an, cn = float(torch.linalg.vector_norm(av)), float(torch.linalg.vector_norm(cv))
        out = {"dot": dot, "actor_norm": an, "weighted_critic_norm": cn,
               "norm_ratio_critic_over_actor": None if an == 0 else cn / an}
        out["cosine"] = None if an == 0 or cn == 0 else dot / (an * cn)
        out["zero_norm_reason"] = ("actor_gradient_zero" if an == 0 else "critic_gradient_zero") if out["cosine"] is None else None
        return out
    result = {**values(a_parts, c_parts), "groups": {k: values(*v) for k, v in groups.items()},
              "coverage": coverage, **metadata,
              "objectives": {"actor": "policy_loss - ent_coef * entropy", "critic": "vf_coef * value_loss"},
              "interpretation": "negative cosine opposes; near zero is orthogonal; positive aligns. Raw gradients do not establish Adam update interference or behavioral harm."}
    return result
