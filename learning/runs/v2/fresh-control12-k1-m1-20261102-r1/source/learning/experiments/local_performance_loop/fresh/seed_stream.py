"""Finite, non-pool training seed permutation. Standard library only.

This version deliberately differs from the native SplitMix stream. It requires
a future reviewed adapter. No cohort discovery, file IO, RNG, or simulator calls.
"""
from dataclasses import dataclass, field
from bisect import bisect_right
from functools import cached_property
import hashlib
import json

VERSION = "fresh_feistel8_cyclewalk_v1"
MANDATORY_U32 = ((0, 0), (0xB0000000, 0xB00003E7),
                 (0xD0000000, 0xD000007F), (0xE0000000, 0xE00003E7))


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"invalid {name}")
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def normalize(ranges, maximum):
    union = []
    for pair in ranges:
        if len(pair) != 2:
            raise ValueError("exclusion must have two inclusive endpoints")
        low, high = pair
        integer(low, 0, maximum, "exclusion start")
        integer(high, low, maximum, "exclusion end")
        union.append((low, high))
    merged = []
    for low, high in sorted(union):
        if merged and low <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(high, merged[-1][1]))
        else:
            merged.append((low, high))
    return tuple(merged)


@dataclass(frozen=True)
class StreamSpec:
    campaign: str
    replica: str
    slots: int
    heldout_manifest_sha256: str
    additional_exclusions: tuple = ()
    bits: int = 32
    max_walk: int = 128
    effective_exclusions: tuple = field(init=False)

    def __post_init__(self):
        for name in ("campaign", "replica"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"invalid {name}")
        integer(self.bits, 4, 32, "bits")
        if self.bits % 2:
            raise ValueError("Feistel domain must have even bit width")
        integer(self.slots, 1, 2 ** self.bits - 1, "slots")
        integer(self.max_walk, 1, 2 ** self.bits, "max_walk")
        stamp = self.heldout_manifest_sha256
        if (not isinstance(stamp, str) or len(stamp) != 64
                or any(c not in "0123456789abcdef" for c in stamp)):
            raise ValueError("held-out manifest needs lowercase SHA256")
        mandatory = MANDATORY_U32 if self.bits == 32 else ((0, 0),)
        additional = normalize(self.additional_exclusions, 2 ** self.bits - 1)
        # A held-out zero names native stream 1 too. Excluding zero ourselves
        # avoids duplicate training streams without otherwise excluding seed 1.
        aliases = ((1, 1),) if any(low == 0 for low, _ in additional) else ()
        ranges = normalize((*mandatory, *additional, *aliases), 2 ** self.bits - 1)
        object.__setattr__(self, "additional_exclusions", additional)
        object.__setattr__(self, "effective_exclusions", ranges)
        if not self.capacity:
            raise ValueError("excluded entire seed domain")

    @cached_property
    def capacity(self):
        return 2 ** self.bits - sum(b - a + 1 for a, b in self.effective_exclusions)

    def metadata(self):
        return dict(version=VERSION, campaign=self.campaign, replica=self.replica,
                    slots=self.slots, bits=self.bits, max_walk=self.max_walk,
                    heldout_manifest_sha256=self.heldout_manifest_sha256,
                    exclusions=[list(pair) for pair in self.effective_exclusions],
                    capacity=self.capacity, uniqueness_scope="one stream spec")

    @cached_property
    def identity(self):
        return digest(self.metadata())

    @cached_property
    def exclusion_starts(self):
        return tuple(low for low, _ in self.effective_exclusions)

    @cached_property
    def allowed_segments(self):
        starts, lows, count, cursor = [], [], 0, 0
        for low, high in (*self.effective_exclusions, (2 ** self.bits, 2 ** self.bits)):
            if cursor < low:
                starts.append(count)
                lows.append(cursor)
                count += low - cursor
            cursor = high + 1
        return tuple(starts), tuple(lows)

    @classmethod
    def from_metadata(cls, metadata):
        """Reconstruct the identical permutation; reject drift in derived fields."""
        # Zero is always mandatory. Its external alias, if any, is already
        # represented as seed 1 in the effective union. Do not infer it anew.
        additional = tuple((max(1, low), high) for low, high in metadata["exclusions"] if high >= 1)
        spec = cls(campaign=metadata["campaign"], replica=metadata["replica"],
                   slots=metadata["slots"], heldout_manifest_sha256=metadata["heldout_manifest_sha256"],
                   additional_exclusions=additional, bits=metadata["bits"], max_walk=metadata["max_walk"])
        if spec.metadata() != metadata:
            raise ValueError("stream metadata/version/derived fields differ")
        return spec


def _excluded(spec, value):
    index = bisect_right(spec.exclusion_starts, value) - 1
    return index >= 0 and value <= spec.effective_exclusions[index][1]


def _permutation(spec, value):
    """Eight balanced Feistel rounds; a bijection, not a security claim."""
    half = spec.bits // 2
    mask = (1 << half) - 1
    left, right = value >> half, value & mask
    key = bytes.fromhex(spec.identity)
    for round_index in range(8):
        payload = bytes([round_index]) + right.to_bytes(2, "big")
        f = int.from_bytes(hashlib.blake2b(payload, key=key, digest_size=4).digest(), "big") & mask
        left, right = right, left ^ f
    return (left << half) | right


def seed_for(spec, slot, episode):
    """Pure lookup, independent of reset order; never reserves or consumes seeds.

    Rank episode*slots+slot maps to an allowed input. Cycle-walking a bijection
    through excluded values remains a bijection on allowed inputs. No birthday
    collisions or seen-set ordering. A walk cap failure never substitutes a seed.
    """
    integer(slot, 0, spec.slots - 1, "slot")
    integer(episode, 0, spec.capacity, "episode")
    ordinal = episode * spec.slots + slot
    if ordinal >= spec.capacity:
        raise ValueError("seed domain exhausted; no wrap or replacement")
    starts, lows = spec.allowed_segments
    index = bisect_right(starts, ordinal) - 1
    value = lows[index] + ordinal - starts[index]
    for walk in range(1, spec.max_walk + 1):
        value = _permutation(spec, value)
        if not _excluded(spec, value):
            return dict(stream_sha256=spec.identity, campaign=spec.campaign,
                        replica=spec.replica, slot=slot, episode=episode,
                        ordinal=ordinal, actual_seed=value, excluded_hops=walk - 1,
                        evaluation=False)
    raise ValueError("cycle-walk cap reached; preserve incident, no retry")
