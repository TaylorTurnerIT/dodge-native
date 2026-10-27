"""Inference-only paired evaluation mechanics; no runtime imports at module load."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np


SEEDS = tuple(range(3489660928, 3489660992))
REPLICATES = (64001, 64002, 64003)
CHECKPOINTS = ("best180", "latest252")
CANONICAL_ROW_KEYS = (
    "episode_index", "seed", "score_raw_fixed", "score", "alive_frames",
    "gameplay_frames", "terminated", "truncated", "objective_return",
    "death_cause", "fatal_gameplay_frame", "death_observed_lethal_contacts",
)
STREAM_VERSION = "paired-eval-splitmix64-v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def read_jsonl(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    require(bool(rows), f"Empty JSONL: {path}")
    return rows


def canonical_control_rows(rows: Iterable[dict]) -> list[dict]:
    result = []
    for row in rows:
        require(set(row) == set(CANONICAL_ROW_KEYS), "Control row canonical fields changed")
        result.append({key: row[key] for key in CANONICAL_ROW_KEYS})
    return sorted(result, key=lambda row: row["seed"])


def compare_control(actual: list[dict], expected_path: Path) -> None:
    expected = canonical_control_rows(read_jsonl(expected_path))
    observed = canonical_control_rows(actual)
    require(len(expected) == len(observed) == 64, "Argmax control row count differs")
    for left, right in zip(observed, expected, strict=True):
        require(left == right, f"Argmax control mismatch at seed {right['seed']}")


def episode_schedule() -> list[dict]:
    """Both argmax controls precede every sampled evaluation."""
    result = []
    for checkpoint in CHECKPOINTS:
        result.append({"checkpoint": checkpoint, "mode": "argmax", "replicate_seed": None})
    for replicate_seed in REPLICATES:
        for checkpoint in CHECKPOINTS:
            result.append({"checkpoint": checkpoint, "mode": "sampled", "replicate_seed": replicate_seed})
    return result


def episode_count(schedule: list[dict] | None = None) -> int:
    return sum(64 for _ in (schedule or episode_schedule()))


def _splitmix64(value: int) -> int:
    value = (value + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    z = value
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    return z ^ (z >> 31)


class UniformStream:
    """Private 53-bit uniform stream keyed only by version, replicate, and game seed."""

    def __init__(self, replicate_seed: int, game_seed: int):
        require(type(replicate_seed) is int and replicate_seed in REPLICATES, "Unregistered controller seed")
        require(type(game_seed) is int and game_seed in SEEDS, "Unregistered development seed")
        key = f"{STREAM_VERSION}|{replicate_seed}|{game_seed}".encode("ascii")
        self._state = int.from_bytes(hashlib.sha256(key).digest()[:8], "big")

    def next(self) -> float:
        self._state = (self._state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self._state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        bits = (z ^ (z >> 31)) >> 11
        return bits / 9007199254740992.0


def inverse_cdf(probabilities: Iterable[float], uniform: float) -> int:
    """Use normalized float64 probabilities; equality at a CDF edge selects next bin."""
    values = [float(value) for value in probabilities]
    require(bool(values) and all(math.isfinite(value) and value >= 0.0 for value in values),
            "Invalid action probabilities")
    require(math.isfinite(uniform) and 0.0 <= uniform < 1.0, "Uniform outside [0,1)")
    total = math.fsum(values)
    require(math.isfinite(total) and total > 0.0, "Action probabilities sum to zero")
    normalized = [value / total for value in values]
    cumulative = 0.0
    last_positive = -1
    for index, probability in enumerate(normalized):
        if probability > 0.0:
            last_positive = index
        cumulative += probability
        if uniform < cumulative:
            return index
    require(last_positive >= 0, "No positive action probability")
    return last_positive


def sample_logits_cpu(logits, uniform: float) -> int:
    """Convert float32 logits to CPU float64, normalize stably, then use inverse CDF."""
    import torch

    values = torch.as_tensor(logits).detach().to(device="cpu", dtype=torch.float64).reshape(-1)
    require(values.numel() == 9 and bool(torch.isfinite(values).all()), "Policy logits must be finite [9]")
    probabilities = torch.softmax(values, dim=-1).tolist()
    return inverse_cdf(probabilities, uniform)


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    require(bool(values), "Cannot average no values")
    return math.fsum(values) / len(values)


def _tail_means(values: Iterable[float]) -> dict:
    ordered = sorted(float(value) for value in values)
    require(len(ordered) == 64, "Canonical tail summary requires 64 per-seed values")
    return {"bottom16_mean": _mean(ordered[:16]), "top16_mean": _mean(ordered[-16:]),
            "all64_mean": _mean(ordered)}


def summarize_mode(rows: list[dict], checkpoint: str, mode: str) -> dict:
    require(checkpoint in CHECKPOINTS and mode in {"argmax", "sampled"}, "Unknown summary group")
    grouped: dict[int, list[dict]] = {seed: [] for seed in SEEDS}
    for row in rows:
        if row["checkpoint"] == checkpoint and row["mode"] == mode:
            grouped[row["seed"]].append(row)
    expected_n = 1 if mode == "argmax" else 3
    require(all(len(grouped[seed]) == expected_n for seed in SEEDS), "Per-seed episode count differs")
    seed_alive = {seed: _mean(row["alive_frames"] for row in grouped[seed]) for seed in SEEDS}
    seed_score = {seed: _mean(row["score"] for row in grouped[seed]) for seed in SEEDS}
    caps = sum(bool(row["truncated"]) for seed in SEEDS for row in grouped[seed])
    denominators = {"episodes": len(SEEDS) * expected_n,
                    "terminated": sum(bool(row["terminated"]) for seed in SEEDS for row in grouped[seed]),
                    "truncated_censored": caps}
    cause_counts = {}
    for row in (row for seed in SEEDS for row in grouped[seed]):
        if row["terminated"]:
            cause = row["death_cause"] or "unavailable"
            cause_counts[cause] = cause_counts.get(cause, 0) + 1
    restricted = [row for seed in SEEDS for row in grouped[seed] if not row["truncated"]]
    result = {"checkpoint": checkpoint, "mode": mode, "per_seed_alive_frames": seed_alive,
              "per_seed_score": seed_score, "alive_frames": _tail_means(seed_alive.values()),
              "score": _tail_means(seed_score.values()), "score_mean": _mean(seed_score.values()),
              "deaths_by_cause": cause_counts,
              "death_denominators": denominators, "cap_count": caps,
              "censored_scope": "all episode rows retained; cap outcomes are right-censored",
              "uncensored_only_restricted_alive_mean": None if not restricted else _mean(r["alive_frames"] for r in restricted),
              "uncensored_only_episode_count": len(restricted)}
    if mode == "sampled":
        replicate_summaries = {}
        per_seed_values = {}
        for replicate in REPLICATES:
            selected = [row for row in rows if row["checkpoint"] == checkpoint and row["mode"] == mode
                        and row["replicate_seed"] == replicate]
            require(len(selected) == 64, "Sample replicate incomplete")
            per_seed_values[replicate] = {row["seed"]: row["alive_frames"] for row in selected}
            replicate_summaries[str(replicate)] = {
                "alive_frames": _tail_means(row["alive_frames"] for row in selected),
                "score": _tail_means(row["score"] for row in selected),
                "score_mean": _mean(row["score"] for row in selected),
                "death_denominators": {"episodes": 64,
                                        "terminated": sum(bool(row["terminated"]) for row in selected),
                                        "truncated_censored": sum(bool(row["truncated"]) for row in selected)},
                "deaths_by_cause": {cause: sum(row["terminated"] and
                                                 (row["death_cause"] or "unavailable") == cause
                                                 for row in selected)
                                    for cause in sorted({(row["death_cause"] or "unavailable")
                                                         for row in selected if row["terminated"]})},
            }
        seed_sds = [float(np.std([per_seed_values[r][seed] for r in REPLICATES], ddof=1)) for seed in SEEDS]
        result["replicate_summaries"] = replicate_summaries
        result["replicate_noise_floor_frames"] = {"median_seed_sd": float(np.median(seed_sds)),
                                                   "max_seed_sd": max(seed_sds)}
    return result


CONTRAST_NAMES = ("C1_env_seed_checkpoint_argmax", "C2_action_mode_best180",
                  "C3_action_mode_latest252", "C4_interaction", "C5_checkpoint_sampled")


def contrast_values(rows: list[dict]) -> dict[str, dict[int, float]]:
    lookup = {(row["checkpoint"], row["mode"], row["replicate_seed"], row["seed"]): row["alive_frames"]
              for row in rows}
    values = {name: {} for name in CONTRAST_NAMES}
    for seed in SEEDS:
        best_arg = lookup[("best180", "argmax", None, seed)]
        latest_arg = lookup[("latest252", "argmax", None, seed)]
        best_sample = _mean(lookup[("best180", "sampled", rep, seed)] for rep in REPLICATES)
        latest_sample = _mean(lookup[("latest252", "sampled", rep, seed)] for rep in REPLICATES)
        values[CONTRAST_NAMES[0]][seed] = latest_arg - best_arg
        values[CONTRAST_NAMES[1]][seed] = best_sample - best_arg
        values[CONTRAST_NAMES[2]][seed] = latest_sample - latest_arg
        values[CONTRAST_NAMES[3]][seed] = values[CONTRAST_NAMES[2]][seed] - values[CONTRAST_NAMES[1]][seed]
        values[CONTRAST_NAMES[4]][seed] = latest_sample - best_sample
    return values


def paired_bootstrap(rows: list[dict], draws: int = 10000, seed: int = 764002) -> dict:
    require(draws == 10000 and seed == 764002, "Bootstrap registration differs")
    by_contrast = contrast_values(rows)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, 64, size=(draws, 64), endpoint=False)
    seed_order = list(SEEDS)
    index_digest = hashlib.sha256(indices.astype("<u4", copy=False).tobytes()).hexdigest()
    output = {}
    for name in CONTRAST_NAMES:
        per_seed = np.asarray([by_contrast[name][game_seed] for game_seed in seed_order], dtype=np.float64)
        boot_means = per_seed[indices].mean(axis=1)
        low, high = np.quantile(boot_means, [0.025, 0.975], method="linear")
        mean_diff = float(per_seed.mean())
        within_margin = float(low) >= -100.0 and float(high) <= 100.0
        clear = (float(low) > 0.0 or float(high) < 0.0) and abs(mean_diff) >= 100.0
        sorted_values = np.sort(per_seed)
        output[name] = {"mean_diff": mean_diff, "median_diff": float(np.median(per_seed)),
                        "bootstrap_95_ci": [float(low), float(high)], "improved": int(np.sum(per_seed > 0)),
                        "worsened": int(np.sum(per_seed < 0)), "tied": int(np.sum(per_seed == 0)),
                        "Q1_Q4_mean_diffs_canonical": {"bottom16_mean": float(sorted_values[:16].mean()),
                                                       "top16_mean": float(sorted_values[-16:].mean())},
                        "decision": "practically_similar" if within_margin else
                                   "exploratory_clear_difference" if clear else "inconclusive"}
    return {"unit": "64 paired game-seed clusters", "draws": draws, "seed": seed,
            "method": "percentile; one seed-index matrix reused across contrasts; linear quantiles",
            "seed_index_matrix_sha256": index_digest,
            "conditional_on": "fixed checkpoint pair and environment-seed cohort; not training-replicate uncertainty",
            "contrasts": output,
            "primary_contrast": "C4_interaction",
            "interpretation_limit": "A wide CI including zero is inconclusive and does not disprove a theory."}


def summarize_all(rows: list[dict]) -> dict:
    require(len(rows) == 512, "Expected exactly 512 episode rows")
    expected_arms = [item for item in episode_schedule() for _ in SEEDS]
    for position, (arm, row) in enumerate(zip(expected_arms, rows, strict=True)):
        require({key: row[key] for key in ("checkpoint", "mode", "replicate_seed")} == arm
                and row["seed"] == SEEDS[position % 64]
                and row["episode_index"] == position % 64,
                "Episode work/order/provenance differs")
    groups = {f"{checkpoint}_{mode}": summarize_mode(rows, checkpoint, mode)
              for checkpoint in CHECKPOINTS for mode in ("argmax", "sampled")}
    contrasts = paired_bootstrap(rows)
    censored = sum(row["truncated"] for row in rows)
    return {"schema": "latest_best_paired_eval_summary_v1", "episode_count": 512,
            "censored_episode_count": int(censored),
            "complete_uncensored_campaign": censored == 0,
            "per_checkpoint_mode": groups, "paired_contrasts": contrasts,
            "qualification_claim": False, "held_out_claim": False,
            "reproducibility_control_note": "Argmax replay checks reproducibility; it adds no environment-seed evidence.",
            "finite_cohort_note": "Existing D development seeds only; no finite-cohort generalization claim."}
