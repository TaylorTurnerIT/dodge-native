"""Inert stdlib gate for externally measured RNG state references."""
import hashlib
import json
from pathlib import Path

SCHEMA = "d2_layerb_rng_real_state_preflight_v1"
STATUS = "measured"
BACKEND = "mps"
ACCEPTED_CHECKPOINT_SHA256 = "b95228e5e2934c915597595f7eb3c8618ee5f7c2182dde1481a060d01c270369"
PARENT_RECEIPT_SHA256 = "cb3645899b5cb660d26d44645e00b3f53c5d0c8341b645b3b78af6b651d8b016"
SEED_FIELDS = frozenset({
    "constructor_init_seed", "python_random_seed", "numpy_global_seed",
    "torch_cpu_global_seed", "action_sampler_torch_mps_seed", "env_master_seed",
})
RECEIPT_FIELDS = frozenset({
    "schema", "status", "backend", "torch_version", "accepted_checkpoint_sha256",
    "parent_receipt_sha256", "study_id", "replica", "complete_seed_vector",
    "vector_sha256", "cpu_rng_state_sha256", "mps_rng_state_sha256",
})


def _hex64(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be lowercase hex SHA-256")


def canonical_vector_sha256(study_id, replica, seeds):
    """Use stdlibderive.py canonical({study_id, replica, seeds}) byte rule."""
    payload = {"study_id": study_id, "replica": replica, "seeds": seeds}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def load_bound_reference(*, receipt_path, expected_receipt_sha256, expected_study_id,
                         expected_replica, expected_seed_vector, expected_vector_sha256,
                         expected_torch_version):
    """Verify file and all provenance/vector bindings before caller mutates state.

    Returns only transition-R2-compatible expected_state_digests. Caller must
    invoke this gate before restore or reseed. No callback or runtime imports.
    """
    _hex64(expected_receipt_sha256, "expected_receipt_sha256")
    _hex64(expected_vector_sha256, "expected_vector_sha256")
    if not isinstance(expected_study_id, str) or not expected_study_id:
        raise ValueError("expected_study_id required")
    if type(expected_replica) is not int or expected_replica < 1:
        raise ValueError("expected_replica must be a positive integer")
    if not isinstance(expected_torch_version, str) or not expected_torch_version:
        raise ValueError("expected_torch_version required")
    if not isinstance(expected_seed_vector, dict) or set(expected_seed_vector) != SEED_FIELDS:
        raise ValueError("expected seed vector must contain exactly six fields")
    if any(type(value) is not int for value in expected_seed_vector.values()):
        raise ValueError("expected seed vector values must be integers")
    computed_vector_sha256 = canonical_vector_sha256(
        expected_study_id, expected_replica, expected_seed_vector)
    if computed_vector_sha256 != expected_vector_sha256:
        raise ValueError("expected vector hash does not match canonical seed vector")

    path = Path(receipt_path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_receipt_sha256:
        raise ValueError("preflight receipt file SHA-256 mismatch")
    try:
        receipt = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("preflight receipt is not valid UTF-8 JSON") from exc
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_FIELDS:
        raise ValueError("preflight receipt schema fields mismatch")
    if receipt["schema"] != SCHEMA:
        raise ValueError("preflight receipt schema mismatch")
    if receipt["status"] != STATUS:
        raise ValueError("preflight receipt status is not measured")
    if receipt["backend"] != BACKEND:
        raise ValueError("preflight receipt backend mismatch")
    if receipt["torch_version"] != expected_torch_version:
        raise ValueError("preflight receipt torch version mismatch")
    if receipt["accepted_checkpoint_sha256"] != ACCEPTED_CHECKPOINT_SHA256:
        raise ValueError("accepted checkpoint hash mismatch")
    if receipt["parent_receipt_sha256"] != PARENT_RECEIPT_SHA256:
        raise ValueError("accepted parent receipt hash mismatch")
    if receipt["study_id"] != expected_study_id or receipt["replica"] != expected_replica:
        raise ValueError("preflight receipt study or replica mismatch")
    if receipt["complete_seed_vector"] != expected_seed_vector:
        raise ValueError("preflight receipt complete seed vector mismatch")
    if receipt["vector_sha256"] != expected_vector_sha256:
        raise ValueError("preflight receipt vector hash mismatch")
    _hex64(receipt["cpu_rng_state_sha256"], "cpu_rng_state_sha256")
    _hex64(receipt["mps_rng_state_sha256"], "mps_rng_state_sha256")
    return {
        "torch_cpu_global_seed": receipt["cpu_rng_state_sha256"],
        "action_sampler_torch_mps_seed": receipt["mps_rng_state_sha256"],
    }
