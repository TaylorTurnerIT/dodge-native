"""Frozen episode splits for the first teacher/student experiments."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .evaluate import unique_seeds

SEED_SCHEMA_VERSION = 1


def seed_manifest() -> dict[str, Any]:
    """Return a fresh manifest; test seeds are reserved for a frozen recipe."""
    manifest = {
        "schema_version": SEED_SCHEMA_VERSION,
        "train": list(range(1000, 1100)),
        "smoke": list(range(2000, 2010)),
        "validation": list(range(3000, 3100)),
        "test": list(range(4000, 4100)),
    }
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    if set(manifest) != {"schema_version", "train", "smoke", "validation", "test"}:
        raise ValueError("seed manifest must declare all four episode splits")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != SEED_SCHEMA_VERSION:
        raise ValueError("unsupported seed manifest schema")
    seen = set()
    for split in ("train", "smoke", "validation", "test"):
        values = manifest[split]
        if not isinstance(values, list) or unique_seeds(values) != values:
            raise ValueError(f"{split} must contain distinct RNG streams")
        streams = {1 if seed == 0 else seed for seed in values}
        if seen & streams:
            raise ValueError("episode seed splits overlap, including equivalent RNG streams")
        seen.update(streams)


def manifest_hash(manifest: dict[str, Any]) -> str:
    validate_manifest(manifest)
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()
