"""Synthetic JSON fixtures only; no measured RNG references are created."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import rng_reference as gate

STUDY = "unit-only-study"
REPLICA = 2
VERSION = "unit-only-torch-version"
SEEDS = {
    "constructor_init_seed": 11,
    "python_random_seed": 12,
    "numpy_global_seed": 13,
    "torch_cpu_global_seed": 14,
    "action_sampler_torch_mps_seed": 15,
    "env_master_seed": 16,
}
VECTOR_HASH = gate.canonical_vector_sha256(STUDY, REPLICA, SEEDS)
CPU_HASH = "1" * 64
MPS_HASH = "2" * 64


def valid_receipt():
    return {
        "schema": gate.SCHEMA,
        "status": "measured",
        "backend": "mps",
        "torch_version": VERSION,
        "accepted_checkpoint_sha256": gate.ACCEPTED_CHECKPOINT_SHA256,
        "parent_receipt_sha256": gate.PARENT_RECEIPT_SHA256,
        "study_id": STUDY,
        "replica": REPLICA,
        "complete_seed_vector": dict(SEEDS),
        "vector_sha256": VECTOR_HASH,
        "cpu_rng_state_sha256": CPU_HASH,
        "mps_rng_state_sha256": MPS_HASH,
    }


class ReferenceGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic-preflight.json"
        self.receipt = valid_receipt()
        self.write()

    def write(self):
        raw = json.dumps(self.receipt, sort_keys=True, separators=(",", ":")).encode()
        self.path.write_bytes(raw)
        self.file_hash = hashlib.sha256(raw).hexdigest()

    def call(self, **overrides):
        args = {
            "receipt_path": self.path,
            "expected_receipt_sha256": self.file_hash,
            "expected_study_id": STUDY,
            "expected_replica": REPLICA,
            "expected_seed_vector": dict(SEEDS),
            "expected_vector_sha256": VECTOR_HASH,
            "expected_torch_version": VERSION,
        }
        args.update(overrides)
        return gate.load_bound_reference(**args)

    def reject_receipt_edit(self, change, message):
        change(self.receipt)
        self.write()
        # Simulate caller retaining original externally pinned file hash.
        args_hash = hashlib.sha256(b"different externally pinned bytes").hexdigest()
        with self.assertRaisesRegex(ValueError, message):
            self.call(expected_receipt_sha256=args_hash)

    def test_valid_synthetic_fixture_returns_compatible_digest_mapping(self):
        self.assertEqual(self.call(), {
            "torch_cpu_global_seed": CPU_HASH,
            "action_sampler_torch_mps_seed": MPS_HASH,
        })

    def test_pending_status_rejected(self):
        self.receipt["status"] = "pending_notrun"
        self.write()
        with self.assertRaisesRegex(ValueError, "file SHA-256"):
            self.call(expected_receipt_sha256="0" * 64)
        # The matching file hash reaches and rejects status validation.
        with self.assertRaisesRegex(ValueError, "not measured"):
            self.call()

    def test_wrong_vector_version_parent_checkpoint_and_nonhex_rejected(self):
        cases = [
            ("complete_seed_vector", dict(SEEDS, torch_cpu_global_seed=999), "vector mismatch"),
            ("torch_version", "other-version", "version mismatch"),
            ("parent_receipt_sha256", "0" * 64, "parent receipt hash mismatch"),
            ("accepted_checkpoint_sha256", "0" * 64, "checkpoint hash mismatch"),
            ("mps_rng_state_sha256", "z" * 64, "lowercase hex"),
        ]
        for field, value, message in cases:
            with self.subTest(field=field):
                self.receipt = valid_receipt()
                self.receipt[field] = value
                self.write()
                with self.assertRaisesRegex(ValueError, message):
                    self.call()

    def test_wrong_expected_vector_binding_rejected_before_file_acceptance(self):
        changed = dict(SEEDS, torch_cpu_global_seed=99)
        with self.assertRaisesRegex(ValueError, "expected vector hash"):
            self.call(expected_seed_vector=changed)

    def test_receipt_vector_hash_mismatch_rejected(self):
        self.receipt["vector_sha256"] = "0" * 64
        self.write()
        with self.assertRaisesRegex(ValueError, "receipt vector hash"):
            self.call()

    def test_receipt_byte_drift_after_external_hash_rejected(self):
        pinned = self.file_hash
        self.receipt["cpu_rng_state_sha256"] = "3" * 64
        self.write()
        with self.assertRaisesRegex(ValueError, "file SHA-256"):
            self.call(expected_receipt_sha256=pinned)

    def test_digest_shapes_and_expected_external_hash_are_checked(self):
        self.receipt["cpu_rng_state_sha256"] = None
        self.write()
        with self.assertRaisesRegex(ValueError, "cpu_rng_state_sha256"):
            self.call()
        with self.assertRaisesRegex(ValueError, "expected_receipt_sha256"):
            self.call(expected_receipt_sha256="G" * 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
