#!/usr/bin/env python3
"""Proposed Layer B per-replica RNG seed vectors. Standard library only.

This file derives, checks, and prints the *proposed* seed vectors for the
three paired training replicas of the D2 Layer B study. It imports no torch, no
numpy, and no native module, opens no checkpoint, and writes nothing. It does
not reserve seeds, grant launch authority, or mutate any predecessor artifact.

    python3 stdlibderive.py                # print seed-vectors JSON
    python3 stdlibderive.py --check FILE   # verify a committed file matches

Derivation rule (reproducible, domain separated, no hidden state):

    token = SHA256("D2-LAYERB-RNG-VECTOR-V1|study=<STUDY_ID>|replica=<i>"
                   "|stream=<name>|attempt=<n>")

Streams and integer bounds (every bound is checked, not assumed):

    env_master_seed              u64, 1 <= x <= 2**64-1, outside the reserved
                                 union and outside prior registered master seeds
    torch_cpu_global_seed        i64-safe, 1 <= x <= 2**63-1
    action_sampler_torch_mps_seed i64-safe, 1 <= x <= 2**63-1
    python_random_seed           i64-safe, 1 <= x <= 2**63-1
    numpy_global_seed            u32, 0 <= x <= 2**32-1
    constructor_init_seed        u32-safe, 1 <= x <= 2**32-1

The env slot stream is not a generator with independent state: the native
environment derives each episode seed from (run_seed, slot, episode) with
SplitMix64 and a rejection counter. This file reimplements that pure function
to precompute an env control for the 64 parent episode indices.

There is deliberately no field for a private NumPy Generator or for an
independent minibatch stream: the pinned runtime owns neither. torch.randperm
draws from the torch CPU global generator, and the action sampler draws from
the device (MPS) global generator. Inventing separate seeds for those would
misdescribe the code.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

STUDY_ID = "expanded-D2-training-replication-layerb-20261026-r1"
DOMAIN = "D2-LAYERB-RNG-VECTOR-V1"
SCHEMA = "d2_layerb_proposed_rng_seed_vectors_v2"

MASK64 = (1 << 64) - 1
I63_MAX = (1 << 63) - 1
U32_MAX = (1 << 32) - 1
U64_MAX = MASK64

# Pinned protocol union (docs/v2-m3-run-protocol.json training_excluded_ranges)
# plus the two uninstalled expanded blocks proposed by the parent r5 artifact.
RESERVED_RANGES = (
    ("B", 0xB0000000, 0xB00003E7),
    ("D128", 0xD0000000, 0xD000007F),
    ("E", 0xE0000000, 0xE00003E7),
    ("D1_new", 0xD1000000, 0xD10003FF),
    ("D2_new", 0xD2000000, 0xD20007FF),
)

# Selected prior master seeds observed in predecessor registrations. This is
# a finite rejection list, not an exhaustive history or collision guarantee.
# Episode seed safety is separately enforced by the five reserved ranges.
PRIOR_MASTER_SEEDS = (810631976, 3192039780, 3791628417, 4200000000, 4200000001)

# Parent 348 continuation state: the fresh environment resumes at these
# per-slot episode indices (retained-best-candidate-receipt.json, sha256
# cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016).
PARENT_RECEIPT_SHA256 = "cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016"
PARENT_NEXT_EPISODE_INDICES = (
    282, 289, 286, 291, 305, 279, 308, 300,
    320, 296, 300, 304, 288, 303, 298, 301,
    305, 308, 297, 283, 301, 293, 275, 298,
    285, 310, 296, 300, 277, 288, 291, 298,
    304, 305, 311, 284, 288, 288, 298, 287,
    301, 309, 296, 286, 293, 291, 274, 302,
    306, 283, 296, 309, 301, 304, 293, 309,
    291, 298, 305, 300, 273, 300, 290, 322,
)

STREAM_BOUNDS = {
    "env_master_seed": (1, U64_MAX, "u64 run_seed at VecDodgeEnv construction"),
    "torch_cpu_global_seed": (1, I63_MAX, "torch.manual_seed / torch.set_rng_state"),
    "action_sampler_torch_mps_seed": (1, I63_MAX, "torch.mps.manual_seed"),
    "python_random_seed": (1, I63_MAX, "random.seed"),
    "numpy_global_seed": (0, U32_MAX, "numpy.random.seed"),
    "constructor_init_seed": (1, U32_MAX, "seed_initialization calls numpy.random.seed; u32 before model construction"),
}
STREAM_ORDER = tuple(STREAM_BOUNDS)


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def token(replica: int, stream: str, attempt: int) -> bytes:
    message = (f"{DOMAIN}|study={STUDY_ID}|replica={replica}"
               f"|stream={stream}|attempt={attempt}").encode()
    return hashlib.sha256(message).digest()


def in_reserved(value: int) -> bool:
    return any(low <= value <= high for _name, low, high in RESERVED_RANGES)


def derive_stream(replica: int, stream: str) -> tuple[int, int]:
    low, high, _api = STREAM_BOUNDS[stream]
    width = 4 if stream in {"numpy_global_seed", "constructor_init_seed"} else 8
    for attempt in range(1 << 20):
        raw = int.from_bytes(token(replica, stream, attempt)[:width], "big")
        value = raw
        if stream in {"numpy_global_seed", "constructor_init_seed"}:
            value = raw & U32_MAX
        else:
            value = raw & I63_MAX if stream != "env_master_seed" else raw & U64_MAX
        if not low <= value <= high:
            continue
        if stream == "env_master_seed" and (in_reserved(value) or value in PRIOR_MASTER_SEEDS):
            continue
        return value, attempt
    raise RuntimeError(f"exhausted derivation attempts for {stream}")


def mix(z: int) -> int:
    z &= MASK64
    z ^= z >> 30
    z = (z * 0xBF58_476D_1CE4_E5B9) & MASK64
    z ^= z >> 27
    z = (z * 0x94D0_49BB_1331_11EB) & MASK64
    z ^= z >> 31
    return z


def env_actual_seed(run_seed: int, slot: int, episode: int) -> dict:
    base = (mix(run_seed ^ 0x444F_4447_455F_5632)
            ^ mix((slot + 0x9E37_79B9_7F4A_7C15) & MASK64)
            ^ mix((episode + 0xD1B5_4A32_D192_ED03) & MASK64))
    counter = 0
    while True:
        candidate = mix(base ^ mix((counter + 0x94D0_49BB_1331_11EB) & MASK64)) >> 32
        if not in_reserved(candidate):
            return {"slot": slot, "episode": episode, "counter": counter,
                    "actual_seed": candidate}
        counter += 1


def python_controls(seed: int) -> dict:
    scratch = random.Random(seed)
    first_bits = scratch.getrandbits(64)
    first_float = scratch.random()
    seeded = random.Random(seed)
    state = seeded.getstate()
    state_blob = canonical([[str(state[0])], list(state[1]),
                            None if state[2] is None else str(state[2])])
    return {
        "stream": "python_random_seed",
        "kind": "scratch_instance_stdlib",
        "first_getrandbits64": first_bits,
        "first_random_float_repr": repr(first_float),
        "post_seed_state_sha256": sha256_hex(state_blob),
        "note": "Computed with random.Random(seed) so the global stream is untouched.",
    }


def build_vectors() -> dict:
    vectors = []
    for replica in (1, 2, 3):
        seeds, attempts = {}, {}
        for stream in STREAM_ORDER:
            value, attempt = derive_stream(replica, stream)
            seeds[stream], attempts[stream] = value, attempt
        payload = {"study_id": STUDY_ID, "replica": replica, "seeds": seeds}
        env_rows = [env_actual_seed(seeds["env_master_seed"], slot, episode)
                    for slot, episode in enumerate(PARENT_NEXT_EPISODE_INDICES)]
        actual = [row["actual_seed"] for row in env_rows]
        vectors.append({
            "replica": replica,
            "seeds": seeds,
            "vector_sha256": sha256_hex(canonical(payload)),
            "derivation_attempts": attempts,
            "env_control": {
                "kind": "splitmix64_slot_stream_first_episode",
                "source": "crates/dodge-rl-env/src/seed.rs training_seed_normalized",
                "episode_indices": list(PARENT_NEXT_EPISODE_INDICES),
                "first_slot_actual_seeds": actual[:4],
                "all_slots_actual_seed_sha256": sha256_hex(
                    b"".join(value.to_bytes(4, "big") for value in actual)),
                "distinct_actual_seeds": len(set(actual)),
                "reserved_hits": sum(1 for value in actual if in_reserved(value)),
                "zero_actual_seeds": sum(1 for value in actual if value == 0),
            },
            "python_control": python_controls(seeds["python_random_seed"]),
        })
    validate(vectors)
    return {
        "schema": SCHEMA,
        "status": "proposed_only_not_reserved_not_applied",
        "study_id": STUDY_ID,
        "proposal_scope": {
            "planned_arms": ["A_constant_3e-5", "B_linear_3e-5_to_1e-5_over_60"],
            "planned_pairs": 3,
            "pairing": "identical vector across arms, distinct vector across replicas",
            "claim_limit": "descriptive only; n=3 exploratory pairs; no .05 confirmatory claim",
            "authority": "none; seeds are not reserved, no launch, no gate or protocol mutation",
            "not_applied": [
                "training exclusion union B/E/D128/D1_new/D2_new is not installed",
                "no runner or registration binds these vectors",
                "no checkpoint or RNG reseed has been executed",
            ],
        },
        "derivation": {
            "domain": DOMAIN,
            "token_rule": "token=SHA256(DOMAIN|study=STUDY_ID|replica=i|stream=name|attempt=n)",
            "field_rule": ("env_master_seed,torch_cpu_global_seed,"
                           "action_sampler_torch_mps_seed,python_random_seed "
                           "take the first 8 token bytes as a "
                           "big-endian integer; 63-bit streams mask to 2**63-1; "
                           "numpy_global_seed and constructor_init_seed take the first 4 bytes; "
                           "an out-of-bounds or reserved candidate increments attempt"),
            "canonical_json": "sort_keys=True,separators=(',',':'),ensure_ascii=True",
            "vector_sha256_rule": "SHA256(canonical_json({study_id,replica,seeds}))",
            "bounds": {name: {"min": low, "max": high, "api": api}
                       for name, (low, high, api) in STREAM_BOUNDS.items()},
            "reserved_ranges": [{"name": name, "low": low, "high": high}
                                for name, low, high in RESERVED_RANGES],
            "prior_master_seeds_rejected": list(PRIOR_MASTER_SEEDS),
        },
        "streams": {
            "env_master_seed": {
                "owner": "native environment (Rust), per environment construction",
                "role": "training namespace master seed for the 64-slot stream",
                "consumed_by": ["training_seed_normalized(run_seed, slot, episode)"],
                "state": "immutable per run; episode seeds are pure function outputs",
                "paired_identical_across_arms": True,
                "distinct_across_replicas": True,
            },
            "constructor_init_seed": {
                "owner": "python learner bootstrap (train_teacher.seed_initialization)",
                "role": "seeds Python/NumPy/torch-CPU before model construction",
                "consumed_by": ["nn.init.orthogonal_ actor/critic heads",
                                "pytorch default trunk init"],
                "state": "consumed then overwritten by verified restore; retained only so the "
                         "pre-restore phase is identical across arms",
                "paired_identical_across_arms": True,
                "distinct_across_replicas": True,
            },
            "torch_cpu_global_seed": {
                "owner": "process-wide torch CPU default generator",
                "role": "minibatch shuffle and any CPU-side torch draw",
                "consumed_by": ["torch.randperm(16384, device='cpu') once per epoch",
                                "Categorical.sample only if the model runs on CPU"],
                "state": "single shared generator; no independent minibatch stream exists",
                "paired_identical_across_arms": True,
                "distinct_across_replicas": True,
            },
            "action_sampler_torch_mps_seed": {
                "owner": "process-wide torch MPS default generator",
                "role": "action sampling when the policy is on MPS",
                "consumed_by": ["Categorical.sample() on [64,9] logits"],
                "state": "active only when the pinned backend is mps",
                "paired_identical_across_arms": True,
                "distinct_across_replicas": True,
            },
            "python_random_seed": {
                "owner": "python random module global state",
                "role": "captured and restored by checkpoints.capture_rng/restore_rng",
                "consumed_by": [],
                "state": "dormant in the pinned runtime; no random.* call exists",
                "paired_identical_across_arms": True,
                "distinct_across_replicas": True,
            },
            "numpy_global_seed": {
                "owner": "numpy global RandomState",
                "role": "captured and restored by checkpoints.capture_rng/restore_rng",
                "consumed_by": [],
                "state": "dormant in the pinned runtime; np.random is never drawn from",
                "paired_identical_across_arms": True,
                "distinct_across_replicas": True,
            },
            "numpy_owned_generator": {
                "owner": "none in the pinned runtime",
                "role": "not implemented; capture_rng accepts an optional generator but "
                        "make_state never captures one",
                "consumed_by": [],
                "state": "absent; do not claim an independent NumPy stream",
                "paired_identical_across_arms": None,
                "distinct_across_replicas": None,
            },
        },
        "vectors": vectors,
        "controls_pending_runtime": [
            "capture torch CPU/MPS generator state fingerprints after reseed "
            "(torch.get_rng_state / torch.mps.get_rng_state)",
            "assert the post-restore, pre-reseed RNG fingerprint equals the parent receipt value",
            "assert model and Adam fingerprints are unchanged across the reseed",
            "record the first torch.randperm(16384) and first Categorical.sample outputs "
            "for the first update; not predictable without torch",
            "assert a scratch numpy RandomState control for numpy_global_seed",
        ],
    }


def validate(vectors: list) -> None:
    assert len(vectors) == 3
    for row in vectors:
        seeds = row["seeds"]
        assert set(seeds) == set(STREAM_ORDER)
        for name, value in seeds.items():
            low, high, _api = STREAM_BOUNDS[name]
            assert type(value) is int and low <= value <= high, (name, value)
        assert not in_reserved(seeds["env_master_seed"])
        assert seeds["env_master_seed"] not in PRIOR_MASTER_SEEDS
        control = row["env_control"]
        assert control["reserved_hits"] == 0, control
        assert control["zero_actual_seeds"] == 0, control
        assert control["distinct_actual_seeds"] == len(PARENT_NEXT_EPISODE_INDICES)
        assert row["vector_sha256"] == sha256_hex(canonical(
            {"study_id": STUDY_ID, "replica": row["replica"], "seeds": seeds}))
    for name in STREAM_ORDER:
        values = [row["seeds"][name] for row in vectors]
        assert len(set(values)) == 3, f"{name} repeats across replicas"
    hashes = [row["vector_sha256"] for row in vectors]
    assert len(set(hashes)) == 3


def main(argv: list) -> int:
    if len(argv) == 3 and argv[1] == "--check":
        expected = json.loads(Path(argv[2]).read_bytes())
        produced = build_vectors()
        if canonical(expected) != canonical(produced):
            print("MISMATCH: committed seed-vectors file differs", file=sys.stderr)
            return 1
        print("OK: committed seed-vectors file matches stdlib derivation")
        return 0
    print(json.dumps(build_vectors(), indent=1, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
