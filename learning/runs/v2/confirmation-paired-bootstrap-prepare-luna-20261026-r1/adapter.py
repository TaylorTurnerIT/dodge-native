"""Inert finite-cohort confirmation statistics adapter; no runtime or checkpoint imports."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import numpy as np

N = 2048
SEEDS = tuple(range(0xD2000000, 0xD2000800))
INCUMBENT_UPDATE = 348
EXPECTED_INCUMBENT_SHA256 = "b95228e5e2934c915597595f7eb3c8618ee5f7c2182dde1481a060d01c270369"
EXPECTED_SELECTION_UPDATE = 324
BOOTSTRAP_SEED = 4200261026
BOOTSTRAP_RESAMPLES = 20000
CHUNK_RESAMPLES = 128
RAW_FRAME_CAP = 18000


class ContractError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _hash(value: Any, label: str) -> str:
    _require(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value), f"invalid {label} SHA-256")
    return value


def _verify_result(binding: dict, *, expected_checkpoint: str, cohort_hash: str, backend: str, label: str) -> tuple[np.ndarray, dict]:
    _require(isinstance(binding, dict) and isinstance(binding.get("result"), dict), f"{label}: candidate-result binding malformed")
    expected_output_hash = _hash(binding.get("expected_output_sha256"), f"{label} pinned output")
    result = binding["result"]
    payload = {k: v for k, v in result.items() if k != "output_sha256"}
    try:
        actual_output_hash = sha256_json(payload)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{label}: output is not canonical finite JSON") from exc
    _require(_hash(result.get("output_sha256"), f"{label} output") == actual_output_hash, f"{label}: tampered output hash")
    _require(expected_output_hash == actual_output_hash, f"{label}: output differs from external pinned binding")
    _require(_hash(result.get("checkpoint_sha256"), f"{label} checkpoint") == expected_checkpoint, f"{label}: checkpoint mismatch")
    _require(_hash(result.get("cohort_sha256"), f"{label} cohort") == cohort_hash, f"{label}: cohort mismatch")
    _require(result.get("backend") == backend, f"{label}: backend mismatch")
    seeds = result.get("seeds")
    _require(isinstance(seeds, list) and len(seeds) == N, f"{label}: partial or malformed seeds")
    _require(all(type(s) is int for s in seeds), f"{label}: noninteger seed")
    _require(seeds == list(SEEDS), f"{label}: missing, duplicate, or reordered seed")
    values = result.get("alive_frames")
    _require(isinstance(values, list) and len(values) == N, f"{label}: partial alive values")
    arr = np.asarray(values, dtype=np.float64)
    _require(arr.shape == (N,) and np.isfinite(arr).all(), f"{label}: nonfinite or malformed alive values")
    _require(((arr >= 0) & (arr <= RAW_FRAME_CAP)).all(), f"{label}: alive value outside [0, {RAW_FRAME_CAP}]")
    deaths = result.get("death_counts")
    _require(isinstance(deaths, dict) and deaths and all(isinstance(k, str) and type(v) is int and v >= 0 for k, v in deaths.items()), f"{label}: invalid full death counts")
    _require(sum(deaths.values()) == N - int(np.count_nonzero(arr == RAW_FRAME_CAP)), f"{label}: death counts do not reconcile to capped episodes")
    cap_count = result.get("cap_count")
    _require(type(cap_count) is int and cap_count == int(np.count_nonzero(arr == RAW_FRAME_CAP)), f"{label}: cap count mismatch")
    return arr, result


def _summaries(values: np.ndarray) -> dict:
    ordered = np.sort(values)
    return {
        "death_counts": None,  # filled from bound result
        "cap_count": int(np.count_nonzero(values == RAW_FRAME_CAP)),
        "worst": float(ordered[0]),
        "q1_mean_lowest_512": float(ordered[:512].mean()),
        "mean": float(values.mean()),
        "q4_mean_highest_512": float(ordered[-512:].mean()),
        "best": float(ordered[-1]),
    }


def analyze(registration: dict, selection: dict, terminal_audit: dict, winner_result: dict, incumbent_result: dict) -> dict:
    """Analyze bound external evidence; never persists, promotes, or authorizes anything."""
    _require(isinstance(registration, dict) and registration.get("status") == "final_frozen", "registration is not final_frozen")
    _require(registration.get("confirmation") == {"count": N, "first_seed": SEEDS[0], "last_seed": SEEDS[-1], "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_resamples": BOOTSTRAP_RESAMPLES, "quantile_method": "linear", "lower_percentile": 5.0, "statistic": "paired_mean_alive_frames_winner_minus_locked_incumbent", "eligible_rule": "LB>0"}, "registration confirmation fields do not match frozen proposal rule")
    _require(registration.get("cohort_seeds") == list(SEEDS), "registration cohort seed vector mismatch")
    cohort_hash = _hash(registration.get("cohort_sha256"), "registration cohort")
    _require(sha256_json(list(SEEDS)) == cohort_hash, "registration cohort hash mismatch")
    _require(isinstance(selection, dict) and selection.get("frozen") is True, "selection record is not frozen")
    _require(selection.get("phase_update") == EXPECTED_SELECTION_UPDATE, "frozen selection phase update must be 324")
    winner_hash = _hash(selection.get("checkpoint_sha256"), "winner checkpoint")
    incumbent_hash = _hash(registration.get("incumbent_checkpoint_sha256"), "incumbent checkpoint")
    _require(incumbent_hash == EXPECTED_INCUMBENT_SHA256, "incumbent checkpoint does not match accepted 348 pin")
    _require(winner_hash != incumbent_hash, "winner checkpoint equals incumbent checkpoint")
    _require(registration.get("incumbent_phase_update") == INCUMBENT_UPDATE, "incumbent is not accepted update 348")
    _require(_hash(selection.get("selection_sha256"), "selection record") == sha256_json({k: v for k, v in selection.items() if k != "selection_sha256"}), "selection record hash mismatch")
    _require(isinstance(terminal_audit, dict) and terminal_audit.get("status") == "successful" and terminal_audit.get("terminal") is True, "parent terminal audit failed or incomplete")
    audit_payload = {k: v for k, v in terminal_audit.items() if k != "receipt_sha256"}
    _require(_hash(terminal_audit.get("receipt_sha256"), "terminal audit receipt") == sha256_json(audit_payload), "terminal audit receipt hash mismatch")
    backend = registration.get("backend")
    _require(isinstance(backend, str) and backend, "registration backend missing")
    w, winner_payload = _verify_result(winner_result, expected_checkpoint=winner_hash, cohort_hash=cohort_hash, backend=backend, label="winner")
    i, incumbent_payload = _verify_result(incumbent_result, expected_checkpoint=incumbent_hash, cohort_hash=cohort_hash, backend=backend, label="incumbent")
    difference = w - i
    rng = np.random.Generator(np.random.PCG64(BOOTSTRAP_SEED))
    means = np.empty(BOOTSTRAP_RESAMPLES, dtype=np.float64)
    for start in range(0, BOOTSTRAP_RESAMPLES, CHUNK_RESAMPLES):
        stop = min(start + CHUNK_RESAMPLES, BOOTSTRAP_RESAMPLES)
        indices = rng.integers(0, N, size=(stop - start, N), dtype=np.int64)
        means[start:stop] = difference[indices].mean(axis=1)
    lower = float(np.quantile(means, 0.05, method="linear"))
    ws, ins = _summaries(w), _summaries(i)
    ws["death_counts"], ins["death_counts"] = winner_payload["death_counts"], incumbent_payload["death_counts"]
    return {
        "schema": "inert_confirmation_statistics_v1",
        "finite_cohort_mean_difference_winner_minus_348": float(difference.mean()),
        "paired_bootstrap_lower_bound_5pct": lower,
        "eligibility": "eligible" if lower > 0 else "inconclusive",
        "winner": ws,
        "incumbent_348": ins,
        "bootstrap": {"generator": "numpy.random.PCG64", "seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES, "quantile_method": "linear", "chunk_resamples": CHUNK_RESAMPLES, "same_seed_indices_for_both_models": True},
        "limits": ["approximate bootstrap coverage; no exact finite-sample guarantee", "no method-A/B claim", "no qualification or stage promotion", "statistics only; no ledger write, promotion, or rerun authority"],
    }
