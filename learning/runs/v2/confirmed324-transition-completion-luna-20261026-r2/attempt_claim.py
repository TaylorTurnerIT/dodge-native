"""Persistent one-shot attempt claims for externally registered future drivers."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

CLAIM_FIELDS = frozenset({"run_id", "study_id", "replica", "arm", "vector_sha256", "parent_checkpoint_sha256"})


def canonical_claim(record):
    if not isinstance(record, dict) or set(record) != CLAIM_FIELDS:
        raise ValueError("claim record must bind run, study, replica, arm, vector, and parent checkpoint")
    if type(record["run_id"]) is not str or not record["run_id"] or type(record["study_id"]) is not str or not record["study_id"]:
        raise ValueError("claim run_id and study_id must be nonempty strings")
    if type(record["replica"]) is not int or record["replica"] < 1:
        raise ValueError("claim replica must be a positive integer")
    if type(record["arm"]) is not str or not record["arm"]:
        raise ValueError("claim arm must be a nonempty string")
    for key in ("vector_sha256", "parent_checkpoint_sha256"):
        value = record[key]
        if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError(f"{key} must be lowercase hex SHA-256")
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class AttemptClaim:
    """Claim one externally pinned path atomically; never removes or repairs it."""
    def __init__(self, path, record):
        if path is None:
            raise ValueError("externally registered attempt claim path required")
        self.path = Path(path)
        self.payload = canonical_claim(record)

    def claim(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(self.path, flags, 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=True) as handle:
                handle.write(self.payload)
                handle.flush()
                os.fsync(handle.fileno())
            dirfd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
        except BaseException:
            # A partial file still consumes this fixed path. Never unlink it.
            raise
        return {"path": str(self.path), "record_sha256": hashlib.sha256(self.payload).hexdigest(),
                "record": json.loads(self.payload)}


def verify_claim_receipt(receipt, expected_path, expected_record):
    payload = canonical_claim(expected_record)
    if not isinstance(receipt, dict) or set(receipt) != {"path", "record_sha256", "record"}:
        raise ValueError("verified claim receipt required")
    if Path(receipt["path"]) != Path(expected_path) or receipt["record"] != json.loads(payload):
        raise ValueError("claim receipt path or identity mismatch")
    if receipt["record_sha256"] != hashlib.sha256(payload).hexdigest():
        raise ValueError("claim receipt digest mismatch")
    return receipt
