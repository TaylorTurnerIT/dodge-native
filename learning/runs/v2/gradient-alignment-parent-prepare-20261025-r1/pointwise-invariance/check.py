"""Exact in-process state checks around isolated shadow diagnostics."""
from pathlib import Path
import datetime
import importlib.util
import json
import random
import resource
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
OWN = Path(__file__).resolve().parent
PREP = ROOT / "learning/runs/v2/gradient-alignment-prepare-luna-20261025-r3/own"
sys.path.insert(0, str(PREP / "runtime"))
import numpy as np
import torch
import dodge_rl.ppo as ppo
import dodge_rl.gradient_alignment as alignment
from dodge_rl import checkpoints

spec = importlib.util.spec_from_file_location("parity_fixture", PREP / "tests/parity_fixture.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
spec = importlib.util.spec_from_file_location("audit_runner", ROOT / "learning/runs/v2/d2-continuation-prepare-luna-20261025-r3/runner.py")
audit_runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_runner)


def exercise(device, poison=False):
    torch.set_num_threads(1 if device == "cpu" else 4)
    model, batch = fixture.fixture()
    model = model.to(device).eval()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
    random.seed(991)
    np.random.seed(992)
    torch.manual_seed(993)
    if device == "mps":
        torch.mps.manual_seed(994)
    context = {"capture_count": 0, "probe_count": 0}
    original_deepcopy = ppo.copy.deepcopy
    original_measure = alignment.measure_cpu_shadow

    def hashes():
        values = {"model": model.state_dict(), "Adam": optimizer.state_dict(),
                  "grads": {name: parameter.grad for name, parameter in model.named_parameters()},
                  "RNG": checkpoints.capture_rng(device),
                  "modes": {name: module.training for name, module in model.named_modules()},
                  "batch": vars(batch)}
        return {key: audit_runner.fingerprint(value) for key, value in values.items()}

    def checked_deepcopy(value, *args, **kwargs):
        if value is not model:
            return original_deepcopy(value, *args, **kwargs)
        before = hashes()
        result = original_deepcopy(value, *args, **kwargs)
        after = hashes()
        assert before == after, "Shadow capture mutated live state"
        context.update(pre_step_model_hash=before["model"], capture_before=before, capture_after=after)
        context["capture_count"] += 1
        return result

    def checked_measure(shadow, *args, **kwargs):
        assert next(shadow.parameters()).device.type == "cpu"
        assert audit_runner.fingerprint(shadow.state_dict()) == context["pre_step_model_hash"], "Wrong snapshot boundary"
        if device == "cpu":
            assert all(a.data_ptr() != b.data_ptr()
                       for a, b in zip(model.parameters(), shadow.parameters(), strict=True))
        before = hashes()
        assert before["model"] != context["pre_step_model_hash"], "Fixture optimizer made no update"
        result = original_measure(shadow, *args, **kwargs)
        audit_runner.finite_tree(result)
        assert result["backend"] == "cpu_shadow" and result["measures_live_MPS_gradients"] is False
        if poison:
            with torch.no_grad():
                next(model.parameters()).add_(0.01)
        after = hashes()
        context.update(probe_before=before, probe_after=after)
        context["probe_count"] += 1
        assert before == after, "Probe mutated live state"
        return result

    try:
        with patch.object(ppo.copy, "deepcopy", side_effect=checked_deepcopy), \
             patch.object(alignment, "measure_cpu_shadow", side_effect=checked_measure):
            metrics = ppo.ppo_update(model, optimizer, batch,
                ppo.PPOConfig(update_epochs=2, minibatch_size=4, target_kl=100),
                gradient_alignment_diagnostics=True)
        assert not poison, "Negative control failed to detect mutation"
        assert context["capture_count"] == context["probe_count"] == 1
        assert metrics["optimizer_steps"] == 4 and model.training is False
        return {"device": device, "status": "exact_pointwise_invariance_passed", **context}
    except AssertionError as error:
        if not poison or str(error) != "Probe mutated live state":
            raise
        return {"device": device, "status": "negative_control_detected", "error": str(error), **context}


started = time.monotonic()
proof = {"scope": "Synthetic fixtures only; no real environment/checkpoint/training campaign",
         "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "results": [exercise("cpu"), exercise("mps"), exercise("cpu", poison=True)],
         "wall_seconds": time.monotonic() - started,
         "rss_process_high_water_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
         "mps_driver_sample_after_bytes": torch.mps.driver_allocated_memory(),
         "limitation": "Exact pointwise invariance is not independent-run bitwise GPU trajectory parity."}
assert proof["rss_process_high_water_bytes"] <= 6442450944
assert proof["mps_driver_sample_after_bytes"] <= 6442450944
with (OWN / "result.json").open("x") as stream:
    json.dump(proof, stream, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps({key: value for key, value in proof.items() if key != "results"}, indent=2))
print(json.dumps([{key: item[key] for key in ("device", "status", "capture_count", "probe_count")}
                  for item in proof["results"]], indent=2))
