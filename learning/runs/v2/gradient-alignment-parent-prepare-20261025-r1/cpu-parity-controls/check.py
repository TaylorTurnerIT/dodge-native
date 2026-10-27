"""Predetermined synthetic CPU controls; no environment or checkpoint learning."""
from pathlib import Path
import copy
import datetime
import hashlib
import importlib.util
import json
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
OWN = Path(__file__).resolve().parent
PREP = ROOT / "learning/runs/v2/gradient-alignment-prepare-luna-20261025-r2/own"
sys.path.insert(0, str(PREP / "runtime"))
spec = importlib.util.spec_from_file_location("fixture", PREP / "tests/parity_fixture.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
import numpy as np
import torch
from dodge_rl.ppo import PPOConfig, ppo_update


def compare(left, right):
    differences = {}
    for name in left:
        a, b = left[name].detach().cpu(), right[name].detach().cpu()
        if not torch.equal(a, b):
            differences[name] = {"unequal_elements": int((a != b).sum()),
                                 "max_absolute_error": float((a - b).abs().max())}
    return differences


results = []
started = time.monotonic()
for threads in (2, 1):
    torch.set_num_threads(threads)
    base, batch = fixture.fixture()
    arms = []
    for label, enabled in (("baseline1", False), ("baseline2", False), ("probe", True)):
        model = copy.deepcopy(base).eval()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
        random.seed(991)
        np.random.seed(992)
        torch.manual_seed(993)
        begin = time.monotonic()
        metrics = ppo_update(model, optimizer, copy.deepcopy(batch),
                             PPOConfig(update_epochs=2, minibatch_size=4, target_kl=100),
                             gradient_alignment_diagnostics=enabled)
        arms.append({"label": label, "state": copy.deepcopy(model.state_dict()),
                     "metrics": {key: value for key, value in metrics.items()
                                 if key != "gradient_alignment_diagnostics"},
                     "seconds": time.monotonic() - begin,
                     "rng": torch.get_rng_state().clone()})
    results.append({"threads": threads,
                    "baseline_repeat_model_differences": compare(arms[0]["state"], arms[1]["state"]),
                    "probe_model_differences": compare(arms[0]["state"], arms[2]["state"]),
                    "baseline_repeat_metrics_equal": arms[0]["metrics"] == arms[1]["metrics"],
                    "probe_common_metrics_equal": arms[0]["metrics"] == arms[2]["metrics"],
                    "baseline_repeat_rng_equal": torch.equal(arms[0]["rng"], arms[1]["rng"]),
                    "probe_rng_equal": torch.equal(arms[0]["rng"], arms[2]["rng"]),
                    "times_seconds": {arm["label"]: arm["seconds"] for arm in arms}})
proof = {"purpose": "Discriminate baseline CPU nondeterminism from probe mutation after first exact parity failure.",
         "scope": "Six predetermined synthetic PPO fixture arms; no environment, real checkpoint or real training campaign.",
         "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "original_source_unchanged": True,
         "source_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in (Path(__file__), PREP / "tests/parity_fixture.py",
                                     PREP / "runtime/dodge_rl/ppo.py")},
         "results": results, "wall_seconds": time.monotonic() - started}
with (OWN / "result.json").open("x") as stream:
    json.dump(proof, stream, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps(proof, indent=2, allow_nan=False))
