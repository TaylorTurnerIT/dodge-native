"""CPU-shadow reference gradient alignment; never reads the live gradient buffers."""
from __future__ import annotations
import math
import torch
from torch.distributions import Categorical


def summarize(actor_grads, critic_grads, named_parameters, *, metadata):
    named_parameters = list(named_parameters)
    if len(actor_grads) != len(named_parameters) or len(critic_grads) != len(named_parameters):
        raise ValueError("gradient tuple count differs from named shared parameter count")
    vectors = {"actor": [], "critic": []}
    groups = {}
    coverage = {"parameters": len(named_parameters), "elements": 0,
                "actor_used": 0, "critic_used": 0}
    for (name, param), ga, gc in zip(named_parameters, actor_grads, critic_grads):
        coverage["elements"] += param.numel()
        coverage["actor_used"] += int(ga is not None)
        coverage["critic_used"] += int(gc is not None)
        pair = []
        for objective, grad in (("actor", ga), ("critic", gc)):
            if grad is None:
                vec = torch.zeros(param.numel(), dtype=torch.float64)
            else:
                if grad.shape != param.shape:
                    raise ValueError(f"{objective} gradient shape mismatch for {name}: {tuple(grad.shape)} != {tuple(param.shape)}")
                bad = ~torch.isfinite(grad)
                if bool(bad.any()):
                    coord = tuple(int(x) for x in bad.nonzero()[0].tolist())
                    raise FloatingPointError(f"nonfinite {objective} gradient for {name} at {coord}")
                vec = grad.detach().to(device="cpu", dtype=torch.float32).to(torch.float64).reshape(-1)
                if not bool(torch.isfinite(vec).all()):
                    coord = tuple(int(x) for x in (~torch.isfinite(vec)).nonzero()[0].tolist())
                    raise FloatingPointError(f"nonfinite {objective} CPU copy for {name} at flat coordinate {coord[0]}")
            pair.append(vec)
        vectors["actor"].append(pair[0]); vectors["critic"].append(pair[1])
        if name.startswith("layers."):
            group = ".".join(name.split(".")[:2])
        elif name.startswith(("global_projection", "entity_projection", "type_embedding")):
            group = "embeddings_and_input_projections"
        elif name.startswith("final_norm"):
            group = "final_norm"
        else:
            group = "remaining_shared_parameters"
        groups.setdefault(group, [[], []])
        groups[group][0].append(pair[0]); groups[group][1].append(pair[1])

    def metrics(a, c):
        av, cv = torch.cat(a), torch.cat(c)
        dot = float(torch.dot(av, cv)); an = float(torch.linalg.vector_norm(av)); cn = float(torch.linalg.vector_norm(cv))
        if not all(math.isfinite(v) for v in (dot, an, cn)):
            raise FloatingPointError("nonfinite gradient alignment reduction")
        result = {"dot": dot, "actor_norm": an, "weighted_critic_norm": cn, "defined": an > 0 and cn > 0}
        if an > 0 and cn > 0:
            result["cosine"] = dot / (an * cn)
            result["norm_ratio_critic_over_actor"] = cn / an
        return result
    result = metrics(vectors["actor"], vectors["critic"])
    result["groups"] = {key: metrics(*value) for key, value in groups.items()}
    result["coverage"] = coverage
    result.update(metadata)
    result["objectives"] = {"actor": "policy_loss - ent_coef * entropy", "critic": "vf_coef * value_loss"}
    result["interpretation"] = "Raw CPU reference gradients: negative cosine opposes, near-zero is orthogonal. No Adam causal-harm claim."
    return result


def measure_cpu_shadow(model, observation, actions, old_log_probs, returns, advantages, *, config):
    """Differentiate weighted objectives on isolated pre-step CPU clone and batch."""
    shadow = model
    shadow_params = dict(shadow.named_parameters())
    shared = [(name, p) for name, p in shadow_params.items()
              if p.requires_grad and not name.startswith(("actor_head.", "critic_head."))]
    output = shadow(*(observation[name] for name in ("global_feats", "entity_feats", "entity_types", "entity_mask")))
    policy = Categorical(logits=output.logits)
    logratio = policy.log_prob(actions) - old_log_probs
    ratio = logratio.exp()
    policy_loss = torch.maximum(-advantages * ratio,
                                -advantages * ratio.clamp(1-config.clip_coef, 1+config.clip_coef)).mean()
    value_loss = 0.5 * (output.values - returns).square().mean()
    entropy = policy.entropy().mean()
    actor_objective = policy_loss - config.ent_coef * entropy
    critic_objective = config.vf_coef * value_loss
    actor_grads = torch.autograd.grad(actor_objective, [p for _, p in shared], allow_unused=True, retain_graph=True)
    critic_grads = torch.autograd.grad(critic_objective, [p for _, p in shared], allow_unused=True)
    return summarize(actor_grads, critic_grads, shared, metadata={
        "backend": "cpu_shadow", "measures_live_MPS_gradients": False,
        "snapshot": "first_minibatch_pre_optimizer_step", "probe_count": 1,
        "minibatch_count": len(actions), "parameter_count": len(shared),
        "element_count": sum(p.numel() for _, p in shared),
    })
