"""Inert transition contract for future exploratory3matched training pairs.

No runtime imports, checkpoint I/O, environment construction, or launch code.
All operations are through injected APIs and trusted restore/fingerprint callbacks.
"""
from __future__ import annotations

from collections.abc import Mapping

EXPECTED_PARENT = {
    "model": "b106e8e1ef0645b357ae8877587e2668aa239435c845223dd9481b6fa3ad399f",
    "Adam": "29108e8441b859f02e149b8e52e8cb9d36bbe8d739eef8a7435ab392be4c523e",
    "RNG": "831d8fa20b4b9aca009382ccb69f9516336b83540850d86b5cdc53a07ba380ad",
}
SEED_FIELDS = (
    "constructor_init_seed", "python_random_seed", "numpy_global_seed",
    "torch_cpu_global_seed", "action_sampler_torch_mps_seed", "env_master_seed",
)
U32_MAX = (1 << 32) - 1
I63_MAX = (1 << 63) - 1
U64_MAX = (1 << 64) - 1
EXPECTED_EXCLUSION_RANGES = (
    (2952790016, 2952791015), (3489660928, 3489661055),
    (3758096384, 3758097383), (3506438144, 3506439167),
    (3523215360, 3523217407),
)
OLD_CONTROLLER_PROVENANCE = {
    "origin": 372, "horizon": 60, "completed": 24,
    "saved_lr": 2.2203389830508474e-5,
}


def validate_seeds(seeds: Mapping[str, object]) -> None:
    missing = set(SEED_FIELDS) - set(seeds)
    if missing:
        raise ValueError(f"missing explicit seed fields: {sorted(missing)}")
    bounds = {
        "constructor_init_seed": (1, U32_MAX), "numpy_global_seed": (0, U32_MAX),
        "python_random_seed": (1, I63_MAX), "torch_cpu_global_seed": (1, I63_MAX),
        "action_sampler_torch_mps_seed": (1, I63_MAX), "env_master_seed": (1, U64_MAX),
    }
    for key, (low, high) in bounds.items():
        value = seeds[key]
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} outside [{low}, {high}]")


def transition(*, backend: str, seeds: Mapping[str, object],
               current_fingerprints, restore_trusted, fingerprint,
               python_api, numpy_api, torch_api, model, optimizer,
               pair_id: str, arm: str) -> dict:
    """Restore verified parent, seed explicit streams once, set arm LR."""
    if backend != "mps":
        raise ValueError("backend must be mps")
    if not isinstance(pair_id, str) or not pair_id:
        raise ValueError("pair_id is required")
    if arm not in {"A_constant_3e-5", "B_linear_3e-5_to_1e-5_over_60"}:
        raise ValueError("unknown arm")
    validate_seeds(seeds)
    before = current_fingerprints()
    if before != EXPECTED_PARENT:
        raise ValueError("parent model/Adam/RNG fingerprints do not match accepted 348")
    restore_trusted()
    restored = current_fingerprints()
    if restored != EXPECTED_PARENT:
        raise ValueError("trusted restore did not produce accepted 348 fingerprints")

    python_api.seed(seeds["python_random_seed"])
    numpy_api.seed(seeds["numpy_global_seed"])
    # torch.manual_seed also seeds MPS on the pinned runtime; MPS must be last.
    torch_api.manual_seed(seeds["torch_cpu_global_seed"])
    torch_api.mps.manual_seed(seeds["action_sampler_torch_mps_seed"])
    evidence = {
        "torch_cpu_initial_seed": torch_api.initial_seed(),
        "torch_mps_initial_seed": torch_api.mps.initial_seed(),
    }
    if evidence["torch_cpu_initial_seed"] != seeds["torch_cpu_global_seed"]:
        raise ValueError("CPU RNG read-back mismatch")
    if evidence["torch_mps_initial_seed"] != seeds["action_sampler_torch_mps_seed"]:
        raise ValueError("MPS RNG read-back mismatch; check seeding order")
    after_seed = current_fingerprints()
    if after_seed["model"] != restored["model"] or after_seed["Adam"] != restored["Adam"]:
        raise ValueError("reseeding changed model or Adam state")

    # Optimizer state (moments and steps) is not touched; only group LR changes.
    lr = 3e-5 if arm == "A_constant_3e-5" else 3e-5
    groups = optimizer.param_groups
    if not isinstance(groups, list) or not groups:
        raise ValueError("optimizer must have parameter groups")
    for group in groups:
        group["lr"] = lr
    return {
        "pair_id": pair_id, "arm": arm, "backend": backend,
        "seeded_once": True, "seed_evidence": evidence,
        "parent_fingerprints": restored,
        "old_controller_provenance": dict(OLD_CONTROLLER_PROVENANCE),
        "new_controller": ({"kind": "constant", "lr": 3e-5}
                           if arm == "A_constant_3e-5" else
                           {"kind": "linear", "start_lr": 3e-5, "end_lr": 1e-5,
                            "origin": 396, "horizon": 60,
                            "first_update": 397, "last_update": 456}),
    }


def controller_lr(arm: str, cumulative_update: int) -> float:
    if arm == "A_constant_3e-5":
        return 3e-5
    if arm != "B_linear_3e-5_to_1e-5_over_60":
        raise ValueError("unknown arm")
    if type(cumulative_update) is not int or cumulative_update < 397:
        raise ValueError("new controller updates start at 397")
    u = cumulative_update - 396
    return 1e-5 if u >= 60 else 3e-5 - 2e-5 * (u - 1) / 59


def validate_pair(pair: Mapping[str, object]) -> None:
    if set(pair) != {"pair_id", "A", "B"} or not pair["pair_id"]:
        raise ValueError("pair requires one pair_id and exactly A/B")
    a, b = pair["A"], pair["B"]
    validate_seeds(a)
    validate_seeds(b)
    if dict(a) != dict(b):
        raise ValueError("paired arms must use identical explicit seed vector")


def validate_exclusion_controls(ranges, episode_controls) -> None:
    normalized = tuple((row["low"], row["high"]) for row in ranges)
    if normalized != EXPECTED_EXCLUSION_RANGES:
        raise ValueError("future environment requires exact five-range exclusion union")
    if len(episode_controls) != 64:
        raise ValueError("environment controls must cover all 64 parent episode indices")
    for row in episode_controls:
        value = row["first_actual_seed"]
        if type(value) is not int or not 0 <= value <= U32_MAX:
            raise ValueError("first actual seed outside u32")
        if any(low <= value <= high for low, high in normalized):
            raise ValueError("first actual seed collides with exclusion union")
        if type(row["rejection_counter"]) is not int or row["rejection_counter"] < 0:
            raise ValueError("invalid seed rejection counter")
