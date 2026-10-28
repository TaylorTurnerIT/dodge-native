"""Static-priority, fresh-rollout seed schedule; stdlib only."""
from __future__ import annotations
import hashlib, json

SCHEMA = "dodge_seed_priority_pool_v1"
STREAM_SCHEMA = "dodge_seed_priority_stream_v1"
EPISODES_PER_SLOT = 15361
MAX_SEQUENCE_LENGTH = 16384
UNIFORM_FRACTION = 0.5
MAX_RELATIVE_PROBABILITY = 4.0


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def validate_pool(doc, *, expected_pool_size=512):
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise ValueError("audited training-only pool schema required")
    if doc.get("role") != "training_only" or doc.get("evaluation_seeds_used_for_selection") is not False:
        raise ValueError("pool must be selected only from training evidence")
    if doc.get("history_closure") != "parent_accepted_bounded_scope_no_universal_claim":
        raise ValueError("explicitly limited parent-accepted history scope required")
    rows = doc.get("seeds")
    if not isinstance(rows, list) or len(rows) != expected_pool_size:
        raise ValueError("pool size differs")
    seen, hard, easy = set(), set(), set()
    exclusions = doc.get("excluded_seed_ranges")
    if not isinstance(exclusions, list) or not exclusions:
        raise ValueError("explicit evaluation/training exclusions required")
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"seed", "stratum", "training_evidence"}:
            raise ValueError("malformed pool row")
        seed = row["seed"]
        if type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF or seed in seen:
            raise ValueError("pool seeds must be unique uint32 integers")
        if row["stratum"] not in {"hard", "easy"}:
            raise ValueError("pool stratum must be hard or easy")
        evidence = row["training_evidence"]
        if not isinstance(evidence, dict) or evidence.get("evaluation") is not False or evidence.get("role") != "training":
            raise ValueError("pool row lacks training-only source evidence")
        if any(type(pair) is not list or len(pair) != 2 or
               type(pair[0]) is not int or type(pair[1]) is not int or pair[0] > pair[1]
               for pair in exclusions):
            raise ValueError("malformed explicit exclusions")
        if any(lo <= seed <= hi for lo, hi in exclusions):
            raise ValueError("pool intersects excluded/future cohort seed")
        seen.add(seed)
        (hard if row["stratum"] == "hard" else easy).add(seed)
    if expected_pool_size not in (512, 1024):
        raise ValueError("pool must contain 512 or 1024 seeds")
    half = expected_pool_size // 2
    if len(hard) != half or len(easy) != half:
        raise ValueError("pool must have balanced hard/easy strata")
    return {"all": tuple(sorted(seen)), "hard": tuple(sorted(hard)), "easy": tuple(sorted(easy)),
            "pool_sha256": sha256_bytes(canonical(doc)),
            "exclusions_sha256": sha256_bytes(canonical(exclusions))}


def _draw_key(study_id, replica, env_master_seed, slot, episode, purpose):
    return hashlib.sha256(canonical([STREAM_SCHEMA, study_id, replica, env_master_seed,
                                     slot, episode, purpose])).digest()


def sequence_entries(pool, *, study_id, replica, env_master_seed, arm, slot, count=EPISODES_PER_SLOT):
    """Return fixed (seed, component) assignments without touching policy RNG."""
    if arm not in {"uniform", "opening_priority"}:
        raise ValueError("unknown arm")
    if type(replica) is not int or replica not in (1, 2, 3) or type(slot) is not int or not 0 <= slot < 64:
        raise ValueError("replica/slot outside registered design")
    if type(count) is not int or not 1 <= count <= MAX_SEQUENCE_LENGTH:
        raise ValueError("invalid bounded stream length")
    if type(env_master_seed) is not int or not 0 < env_master_seed < 2**64:
        raise ValueError("registered environment master seed required")
    all_seeds, hard = pool["all"], pool["hard"]
    if len(all_seeds) not in (512, 1024) or len(hard) != len(all_seeds)//2:
        raise ValueError("expected balanced 512/1024 training pool")
    out = []
    for episode in range(count):
        uniform_key = _draw_key(study_id, replica, env_master_seed, slot, episode, "uniform")
        if arm == "uniform":
            candidates, key, component = all_seeds, uniform_key, "uniform"
        else:
            component_key = _draw_key(study_id, replica, env_master_seed, slot, episode, "component")
            if component_key[0] < 128:
                candidates, key, component = all_seeds, uniform_key, "uniform_floor"
            else:
                candidates = hard
                key = _draw_key(study_id, replica, env_master_seed, slot, episode, "hard")
                component = "hard_priority"
        out.append((candidates[int.from_bytes(key[:8], "big") % len(candidates)], component))
    return out


def sequence(pool, *, study_id, replica, env_master_seed, arm, slot, count=EPISODES_PER_SLOT):
    return [seed for seed, _component in sequence_entries(pool, study_id=study_id,
        replica=replica,env_master_seed=env_master_seed,arm=arm,slot=slot,count=count)]


def stream_digest(values):
    # Compact registration binds generated sequence without storing million-row JSON.
    return sha256_bytes(canonical(values))


def inclusion_probabilities(pool):
    n, h = len(pool["all"]), len(pool["hard"])
    return {"uniform": 1 / n, "hard_seed_priority": UNIFORM_FRACTION / n + (1 - UNIFORM_FRACTION) / h,
            "relative_cap": (UNIFORM_FRACTION / n + (1 - UNIFORM_FRACTION) / h) * n,
            "required_relative_cap": MAX_RELATIVE_PROBABILITY}
