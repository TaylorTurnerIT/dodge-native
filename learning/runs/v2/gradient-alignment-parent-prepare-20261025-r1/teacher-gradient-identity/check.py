"""Compare real teacher shadow vectors with actual preclip CPU PPO gradients."""
from pathlib import Path
import datetime
import hashlib
import importlib.util
import json
import math
import resource
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
OWN = Path(__file__).resolve().parent
PREP = ROOT / "learning/runs/v2/gradient-alignment-prepare-luna-20261025-r3/own"
sys.path.insert(0, str(PREP / "runtime"))
import torch
import dodge_rl.ppo as ppo
import dodge_rl.gradient_alignment as alignment

spec = importlib.util.spec_from_file_location("fixture", PREP / "tests/parity_fixture.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
torch.set_num_threads(1)
model, batch = fixture.fixture(512)
model.train()
optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
named = dict(model.named_parameters())
shared_names = [name for name in named if not name.startswith(("actor_head.", "critic_head."))]
context = {"live_preclip": {}, "shadow_vectors": [], "active_shadow": None}
original_clip = torch.nn.utils.clip_grad_norm_
original_grad = torch.autograd.grad
original_measure = alignment.measure_cpu_shadow


def capture_clip(parameters, *args, **kwargs):
    context["live_preclip"] = {name: named[name].grad.detach().cpu().clone() for name in shared_names}
    return original_clip(parameters, *args, **kwargs)


def capture_grad(outputs, inputs, *args, **kwargs):
    result = original_grad(outputs, inputs, *args, **kwargs)
    if context["active_shadow"] is not None:
        lookup = {id(parameter): name for name, parameter in context["active_shadow"].named_parameters()}
        context["shadow_vectors"].append({lookup[id(parameter)]: torch.zeros_like(parameter) if grad is None else grad.detach().cpu().clone()
                                          for parameter, grad in zip(inputs, result, strict=True)})
    return result


def capture_measure(shadow, *args, **kwargs):
    context["active_shadow"] = shadow
    try:
        return original_measure(shadow, *args, **kwargs)
    finally:
        context["active_shadow"] = None


torch.manual_seed(993)
with patch.object(torch.nn.utils, "clip_grad_norm_", side_effect=capture_clip), \
     patch.object(torch.autograd, "grad", side_effect=capture_grad), \
     patch.object(alignment, "measure_cpu_shadow", side_effect=capture_measure):
    metrics = ppo.ppo_update(model, optimizer, batch,
                             ppo.PPOConfig(update_epochs=1, minibatch_size=512, target_kl=100),
                             gradient_alignment_diagnostics=True)
assert metrics["optimizer_steps"] == 1
assert len(context["shadow_vectors"]) == 2
actor, critic = context["shadow_vectors"]
assert list(actor) == list(critic) == shared_names
errors = {}
for name in shared_names:
    recomposed = actor[name] + critic[name]
    actual = context["live_preclip"][name]
    # This float32 linearity check is separate from exact state-mutation checks.
    torch.testing.assert_close(recomposed, actual, rtol=0, atol=1e-6)
    errors[name] = float((recomposed - actual).abs().max())
av = torch.cat([actor[name].double().flatten() for name in shared_names])
cv = torch.cat([critic[name].double().flatten() for name in shared_names])
lv = torch.cat([context["live_preclip"][name].double().flatten() for name in shared_names])
reference = {"dot": float(av @ cv), "actor_norm": float(av.norm()),
             "weighted_critic_norm": float(cv.norm()),
             "cosine": float((av @ cv) / (av.norm() * cv.norm())),
             "norm_ratio_critic_over_actor": float(cv.norm() / av.norm())}
diagnostic = metrics["gradient_alignment_diagnostics"]
for key, value in reference.items():
    assert math.isclose(value, diagnostic[key], rel_tol=1e-12, abs_tol=1e-12)
assert diagnostic["coverage"]["parameters"] == len(shared_names) == 33
assert diagnostic["coverage"]["elements"] == av.numel() == 286976
poisoned = av.clone()
poisoned[0] += 0.01
assert not torch.allclose(poisoned + cv, lv, rtol=0, atol=1e-6)
proof = {"status": "passed", "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "scope": "One synthetic CPU PPO minibatch on actual 81-token128width2layer4head teacher; no environment or real checkpoint",
         "minibatch_samples": 512, "optimizer_steps": 1, "probe_count": 1,
         "shared_parameters": len(shared_names), "shared_elements": av.numel(),
         "max_absolute_recomposition_error": max(errors.values()),
         "recomposition_absolute_tolerance": 1e-6,
         "tolerance_scope": "Float32 gradient linearity only, not model/Adam/RNG/checkpoint identity or state-mutation parity",
         "all_parameter_errors": errors, "summary_reference": reference,
         "combined_shadow_norm": float((av + cv).norm()), "actual_preclip_shared_norm": float(lv.norm()),
         "live_preclip_all_parameter_norm": diagnostic["live_preclip_grad_norm"],
         "scope_note": "Live clipping norm includes heads; actor/critic vectors and their norms exclude heads.",
         "wrong_vector_negative_control_detected": True,
         "source_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in (Path(__file__), PREP / "runtime/dodge_rl/ppo.py",
                                        PREP / "runtime/dodge_rl/gradient_alignment.py")},
         "rss_process_high_water_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
assert proof["rss_process_high_water_bytes"] <= 6442450944
with (OWN / "result.json").open("x") as stream:
    json.dump(proof, stream, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps({key: value for key, value in proof.items() if key not in ("all_parameter_errors", "source_sha256")}, indent=2))
