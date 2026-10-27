"""Synthetic CPU controls only; no environment, model, or rollout capture."""
import importlib.util
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
FROZEN = Path(__file__).resolve().parents[1] / "D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
sys.path.insert(0, str(FROZEN))
from dodge_rl.ppo import compute_gae

spec = importlib.util.spec_from_file_location("diagnostic", HERE / "diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)

# T=3, N=4: terminal death, time-limit truncation, rollout tail, and reset after terminal.
values = np.array([[.2, .1, -.2, .5], [.3, .4, .1, .2], [.0, .2, .3, -.1]], np.float32)
next_values = np.array([[.3, .4, .1, .2], [.0, .5, .2, .3], [.0, .2, .6, -.1]], np.float32)
term = np.array([[False, False, False, True], [True, False, False, False], [False, False, False, False]])
trunc = np.array([[False, False, False, False], [False, True, False, False], [False, False, False, False]])
score = np.array([[0, 65536, 0, 0], [0, 0, 65536, 0], [0, 0, 0, 0]], np.int64)
elapsed = np.full((3, 4), 4, np.int64)
alive = elapsed - term.astype(np.int64)
data = {"values": values, "next_values": next_values, "terminated": term,
        "truncated": trunc, "score_delta_raw_fixed": score,
        "alive_raw_frames": alive, "elapsed_raw_frames": elapsed}

out = diagnostic.analyze(data)
def digest_arrays(arrays):
    h = hashlib.sha256()
    for name in sorted(arrays):
        a = np.ascontiguousarray(arrays[name])
        h.update(name.encode() + b"\0" + a.dtype.str.encode() + b"\0")
        h.update(json.dumps(a.shape).encode() + b"\0" + a.tobytes())
    return h.hexdigest()
# Production parity on synthetic fixed rollout, CPU torch only.
r = (score / 65536 + alive / 100 - 5 * term.astype(np.int64)).astype(np.float32) * .1
for lam in diagnostic.LAMBDAS:
    adv, targets = compute_gae(torch.from_numpy(r), torch.from_numpy(values),
                               torch.from_numpy(next_values), torch.from_numpy(term),
                               torch.from_numpy(trunc), gamma=.995, gae_lambda=lam)
    row = out["lambda_comparison"][str(lam)]
    carry = np.zeros(4, np.float32)
    expected = np.empty_like(r)
    for t in range(2, -1, -1):
        delta = r[t] + .995 * next_values[t] * (~term[t]) - values[t]
        carry = delta + .995 * lam * (~(term[t] | trunc[t])) * carry
        expected[t] = carry + values[t]
    assert np.allclose(targets.numpy(), expected, rtol=0, atol=1e-7)
    assert np.allclose(adv.numpy() + values, targets.numpy(), rtol=0, atol=0)
    assert abs(row["component_variance_identity_error"]) < 1e-7

# Constant target has undefined EV; empty death eligibility and strict finite JSON.
constant = {"values": np.zeros((2, 1), np.float32), "next_values": np.zeros((2, 1), np.float32),
            "terminated": np.zeros((2, 1), bool), "truncated": np.zeros((2, 1), bool),
            "score_reward": np.zeros((2, 1)), "survival_reward": np.zeros((2, 1)),
            "death_reward": np.zeros((2, 1))}
c = diagnostic.analyze(constant)
assert c["lambda_comparison"]["0.95"]["explained_variance_self_bootstrapped"] is None
assert c["observed_death_comparison"]["eligible_state_count"] == 0
assert "NaN" not in diagnostic.json_text(c)
# Negative finite values are valid in observation and reward components.
negative = dict(constant, values=np.array([[-1.], [-2.]], np.float32),
                score_reward=np.array([[-.2], [.1]]))
assert np.isfinite(diagnostic.analyze(negative)["lambda_comparison"]["0.99"]["target_variance"])
# Invalid overlap and malformed raw accounting must fail closed.
try:
    diagnostic.analyze(dict(data, truncated=term.copy()))
except ValueError:
    pass
else:
    raise AssertionError("overlapping boundaries accepted")
print("synthetic_controls=PASS; scenarios=terminal,truncated,nonterminal-tail,post-terminal-reset; production_GAE=CPU-parity; variance_identity=PASS; constant_EV=undefined; empty_death=PASS; finite_negative=PASS; invalid_overlap=rejected")
print("synthetic_input_sha256=" + digest_arrays(data))
print("synthetic_output_sha256=" + hashlib.sha256(diagnostic.json_text(out).encode()).hexdigest())
