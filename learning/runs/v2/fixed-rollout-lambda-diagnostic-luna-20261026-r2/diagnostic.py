"""Fixed-rollout lambda sensitivity analysis. NumPy only; never trains or reads checkpoints."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

GAMMA = 0.995
LAMBDAS = (0.95, 0.99)
REWARD_SCALE = 0.1
K_MAX = 4


def _array(data, name, shape, dtype_kind):
    a = np.asarray(data[name])
    if a.shape != shape or a.dtype.kind not in dtype_kind:
        raise ValueError(f"{name}: wrong shape or dtype")
    if a.dtype.kind == "f" and not np.isfinite(a).all():
        raise ValueError(f"{name}: nonfinite")
    return a


def load_npz(path):
    """Read only plain numeric/bool arrays. Pickle/object arrays are forbidden."""
    with np.load(Path(path), allow_pickle=False) as archive:
        required = {"values", "next_values", "terminated", "truncated"}
        raw = {"score_delta_raw_fixed", "alive_raw_frames", "elapsed_raw_frames"}
        components = {"score_reward", "survival_reward", "death_reward"}
        keys = set(archive.files)
        if not required <= keys or not (raw <= keys or components <= keys):
            raise ValueError("missing required arrays")
        if keys - required - raw - components - {"rewards"}:
            raise ValueError("unexpected array fields")
        return {k: archive[k] for k in archive.files}


def analyze(data):
    """Analyze immutable [T,N] rollout arrays; returns JSON-safe descriptive moments."""
    if "values" not in data:
        raise ValueError("missing values")
    values = np.asarray(data["values"])
    if values.ndim != 2 or min(values.shape) < 1 or values.dtype.kind != "f" or not np.isfinite(values).all():
        raise ValueError("values must be finite nonempty float [T,N]")
    shape = values.shape
    nv = _array(data, "next_values", shape, "f")
    if nv.dtype != values.dtype:
        raise ValueError("values and next_values dtype differs")
    term = _array(data, "terminated", shape, "b")
    trunc = _array(data, "truncated", shape, "b")
    if term.dtype.kind != "b" or trunc.dtype.kind != "b":
        raise ValueError("boundary arrays must be bool")
    if np.any(term & trunc):
        raise ValueError("termination and truncation overlap")

    raw_names = {"score_delta_raw_fixed", "alive_raw_frames", "elapsed_raw_frames"}
    comp_names = {"score_reward", "survival_reward", "death_reward"}
    have_raw, have_comp = raw_names <= data.keys(), comp_names <= data.keys()
    if have_raw == have_comp:
        raise ValueError("provide exactly raw fields or scaled reward components")
    if have_raw:
        score = _array(data, "score_delta_raw_fixed", shape, "iu")
        alive = _array(data, "alive_raw_frames", shape, "iu")
        elapsed = _array(data, "elapsed_raw_frames", shape, "iu")
        if np.any(score < 0) or np.any((elapsed < 1) | (elapsed > K_MAX)):
            raise ValueError("raw score or elapsed frames out of bounds")
        if np.any(alive != elapsed - term.astype(alive.dtype)):
            raise ValueError("alive_raw_frames != elapsed_raw_frames - terminated")
        parts = {
            "score": score.astype(np.float64) / 65536 * REWARD_SCALE,
            "survival": alive.astype(np.float64) / 100 * REWARD_SCALE,
            "death": -5 * term.astype(np.float64) * REWARD_SCALE,
        }
    else:
        parts = {name.removesuffix("_reward"): _array(data, name, shape, "f").astype(np.float64)
                 for name in sorted(comp_names)}
        if not np.allclose(parts["death"], -0.5 * term, rtol=0, atol=1e-7):
            raise ValueError("scaled death reward must equal -0.5 * terminated")
    rewards = sum(parts.values())
    if "rewards" in data:
        supplied = _array(data, "rewards", shape, "f")
        if not np.allclose(rewards, supplied, rtol=0, atol=1e-7):
            raise ValueError("reward component identity mismatch")

    result = {"gamma": GAMMA, "reward_scale": REWARD_SCALE,
              "lambda_comparison": {}, "population_variance_ddof": 0,
              "ev_definition": "1 - var(target-value)/var(target); undefined when target variance is zero",
              "target_scope": "self-bootstrapped descriptive target, not critic quality"}
    for lam in LAMBDAS:
        # Linear decomposition: target = V + A = reward contribution + value/bootstrap contribution.
        # Each component follows same terminal/truncation masks and episode boundary recurrence.
        contributions = {k: np.zeros(shape, np.float64) for k in parts}
        vb = np.zeros(shape, np.float64)
        carry_parts = {k: np.zeros(shape[1], np.float64) for k in parts}
        carry_vb = np.zeros(shape[1], np.float64)
        for t in range(shape[0] - 1, -1, -1):
            boot = (~term[t]).astype(np.float64)
            cont = (~(term[t] | trunc[t])).astype(np.float64)
            factor = GAMMA * lam * cont
            for k, reward_part in parts.items():
                # reward terms have no value bootstrap
                carry_parts[k] = reward_part[t] + factor * carry_parts[k]
                contributions[k][t] = carry_parts[k]
            # Include -V_t + gamma*nextV bootstrap in the advantage component.
            carry_vb = -values[t] + GAMMA * nv[t] * boot + factor * carry_vb
            vb[t] = values[t] + carry_vb
        adv = sum(contributions.values()) + vb - values
        target = values + adv
        if not np.isfinite(target).all():
            raise ValueError("nonfinite computed target")
        cov = {}
        names = list(contributions) + ["value_bootstrap"]
        arrays = [contributions[k] for k in contributions] + [vb]
        for i, left in enumerate(names):
            for j in range(i, len(names)):
                cov[f"{left}|{names[j]}"] = float(np.mean((arrays[i] - arrays[i].mean()) * (arrays[j] - arrays[j].mean())))
        reconstructed = sum(cov[f"{x}|{x}"] for x in names) + 2 * sum(
            cov[f"{names[i]}|{names[j]}"] for i in range(len(names)) for j in range(i + 1, len(names)))
        target_var = float(np.var(target, ddof=0))
        var_adv = float(np.var(adv, ddof=0))
        residual_var = float(np.var(target - values, ddof=0))
        ev = None if target_var == 0 else float(1 - residual_var / target_var)
        result["lambda_comparison"][str(lam)] = {
            "target_mean": float(target.mean()), "target_variance": target_var,
            "advantage_mean": float(adv.mean()), "advantage_variance": var_adv,
            "explained_variance_self_bootstrapped": ev,
            "component_target_variances": {k: float(np.var(v, ddof=0)) for k, v in zip(names, arrays)},
            "component_target_covariances": cov,
            "component_variance_reconstruction": reconstructed,
            "component_variance_identity_error": float(reconstructed - target_var),
            "target_minus_baseline_norm": None,
        }
        result["lambda_comparison"][str(lam)]["_target"] = target
    base = result["lambda_comparison"]["0.95"]["_target"]
    for key in ("0.95", "0.99"):
        row = result["lambda_comparison"][key]
        target = row.pop("_target")
        row["signed_change_from_lambda_0.95_mean"] = float((target - base).mean())
        row["norm_difference_from_lambda_0.95"] = float(np.linalg.norm(target - base))

    # Observed discounted returns only for contiguous same-slot segments ending in death.
    observed, death_distance = [], []
    T, N = shape
    for n in range(N):
        for start in range(T):
            end = next((t for t in range(start, T) if term[t, n] or trunc[t, n]), None)
            if end is not None and term[end, n]:
                observed.append(sum((GAMMA ** (t - start)) * rewards[t, n] for t in range(start, end + 1)))
                death_distance.append(end - start)
    result["observed_death_comparison"] = {
        "eligible_state_count": len(observed),
        "excluded_tail_censored_and_truncated": True,
        "observed_discounted_return_mean": float(np.mean(observed)) if observed else None,
        "time_to_death_bucket_means": {
            "1_4": _mean_for_bucket(observed, death_distance, 1, 4),
            "5_16": _mean_for_bucket(observed, death_distance, 5, 16),
            "17_plus": _mean_for_bucket(observed, death_distance, 17, None),
        },
        "interpretation": "descriptive, conditioned on death observed inside this slot; no distance-variance monotonicity claim",
    }
    return result


def _mean_for_bucket(values, distances, lo, hi):
    selected = [v for v, d in zip(values, distances) if d >= lo and (hi is None or d <= hi)]
    return float(np.mean(selected)) if selected else None


def json_text(result):
    return json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
