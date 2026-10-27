"""Proposed pure arithmetic controls; no environment or RNG-state access.

This source does not install exclusions or authorize any execution. The caller
must bind a reviewed native implementation and inspect its effective union
before constructing training environments in either arm.
"""
import hashlib
import json

STUDY_ID = "progressive1000-confirmed324-20261026-r1"
DOMAIN = "D2-LAYERB-RNG-VECTOR-V1"
U32 = (1 << 32) - 1
U64 = (1 << 64) - 1
I63 = (1 << 63) - 1
BOUNDS = {
    "env_master_seed": (1, U64),
    "torch_cpu_global_seed": (1, I63),
    "action_sampler_torch_mps_seed": (1, I63),
    "python_random_seed": (1, I63),
    "numpy_global_seed": (0, U32),
    "constructor_init_seed": (1, U32),
}
NAMED_RANGES = {
    "B": (0xB0000000, 0xB00003E7),
    "D128": (0xD0000000, 0xD000007F),
    "D100_opened": (0xD1000000, 0xD10003FF),
    "D200_consumed": (0xD2000000, 0xD20007FF),
    "new_D2_evaluation_cohort": (0xD3000000, 0xD30003FF),
    "E": (0xE0000000, 0xE00003E7),
}
HISTORICAL_RANGES = (NAMED_RANGES["B"], NAMED_RANGES["D128"], NAMED_RANGES["E"])


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("strict integer outside bounds")
    return value


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def vector_hash(study, replica, seeds):
    if type(study) is not str or not study:
        raise ValueError("nonempty study required")
    integer(replica, 1, 3)
    if type(seeds) is not dict or set(seeds) != set(BOUNDS):
        raise ValueError("complete six-field vector required")
    for key, value in seeds.items():
        integer(value, *BOUNDS[key])
    return digest({"study_id": study, "replica": replica, "seeds": seeds})


def normalize(additional):
    """Mirror pinned Rust inclusive union: always B; merge adjacency; reject all."""
    ranges = []
    for pair in additional:
        if type(pair) not in (list, tuple) or len(pair) != 2:
            raise ValueError("range pair required")
        lo, hi = pair
        integer(lo, 0, U32)
        integer(hi, 0, U32)
        if lo > hi:
            raise ValueError("excluded seed range start exceeds end")
        ranges.append((lo, hi))
    ranges.append(NAMED_RANGES["B"])
    union = []
    for lo, hi in sorted(ranges):
        if union and lo <= union[-1][1] + 1:
            union[-1] = (union[-1][0], max(hi, union[-1][1]))
        else:
            union.append((lo, hi))
    if union == [(0, U32)]:
        raise ValueError("excluded seed union covers all u32 seeds")
    return tuple(union)


def inside(seed, ranges):
    return any(lo <= seed <= hi for lo, hi in ranges)


def require_training_union(effective, arm):
    """Proposed preconstruction check; no native API calls are made here."""
    if arm not in ("control", "curriculum"):
        raise ValueError("unknown arm")
    canonical_union = normalize(effective)
    if tuple(tuple(x) for x in effective) != canonical_union:
        raise ValueError("effective exclusions must already be canonical")
    for lo, hi in NAMED_RANGES.values():
        if not any(a <= lo and hi <= b for a, b in canonical_union):
            raise ValueError("missing required exclusion before construction")
    return canonical_union


def mix(z):
    z &= U64
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & U64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & U64
    return z ^ (z >> 31)


def candidate(run, slot, episode, counter):
    integer(run, 0, U64)
    integer(slot, 0, U64)
    integer(episode, 0, U64)
    integer(counter, 0, U64)
    base = (mix(run ^ 0x444F4447455F5632)
            ^ mix((slot + 0x9E3779B97F4A7C15) & U64)
            ^ mix((episode + 0xD1B54A32D192ED03) & U64))
    return mix(base ^ mix((counter + 0x94D049BB133111EB) & U64)) >> 32


def reject(candidate_at, ranges, budget=4096):
    integer(budget, 1, 1 << 20)
    for counter in range(budget):
        seed = integer(candidate_at(counter), 0, U32)
        if not inside(seed, ranges):
            return counter, seed
    raise ValueError("bounded control exhausted; no seed substitution authorized")


def training_seed(run, slot, episode, additional=HISTORICAL_RANGES):
    ranges = normalize(additional)
    counter, seed = reject(lambda c: candidate(run, slot, episode, c), ranges)
    return {"slot": slot, "episode": episode, "counter": counter,
            "actual_seed": seed, "evaluation": False}


def derive(replica, prior_masters):
    integer(replica, 1, 3)
    seeds, attempts = {}, {}
    ranges = normalize(list(NAMED_RANGES.values()))
    for name, (low, high) in BOUNDS.items():
        for attempt in range(1 << 20):
            token = hashlib.sha256(
                f"{DOMAIN}|study={STUDY_ID}|replica={replica}|stream={name}|attempt={attempt}".encode()
            ).digest()
            width = 4 if name in ("numpy_global_seed", "constructor_init_seed") else 8
            value = int.from_bytes(token[:width], "big")
            if name not in ("env_master_seed", "numpy_global_seed", "constructor_init_seed"):
                value &= I63
            if not low <= value <= high:
                continue
            if name == "env_master_seed" and (inside(value, ranges) or value in prior_masters):
                continue
            seeds[name], attempts[name] = value, attempt
            break
        else:
            raise ValueError("derivation attempts exhausted")
    return {"replica": replica, "seeds": seeds, "derivation_attempts": attempts,
            "vector_sha256": vector_hash(STUDY_ID, replica, seeds)}
