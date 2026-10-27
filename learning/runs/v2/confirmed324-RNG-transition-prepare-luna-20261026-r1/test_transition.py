"""CPU toy fixtures only. No production checkpoint deserialization or real MPS seeding."""
import hashlib
import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import transition as t
import fingerprints as fp
import rng_reference as rr

SEEDS = {
    "constructor_init_seed": 11, "python_random_seed": 12,
    "numpy_global_seed": 13, "torch_cpu_global_seed": 14,
    "action_sampler_torch_mps_seed": 15, "env_master_seed": 16,
}
STUDY = "unit-only-study"
REPLICA = 1
VERSION = "unit-only-torch"


class ToyArray:
    dtype = "float32"
    shape = (2,)
    def __init__(self, payload=b"\x00\x00\x80?\x00\x00\x00@"):
        self.payload = payload
    def tobytes(self): return self.payload


class ToyModel:
    def __init__(self): self.weights = {"w": ToyArray()}
    def state_dict(self): return self.weights


class ToyOptimizer:
    def __init__(self):
        self.param_groups = [{"lr": 0.02, "betas": (0.9, 0.999), "params": ["w"]}]
        self.state = {"w": {"step": 3, "exp_avg": ToyArray(b"moment-01")}}
    def state_dict(self): return {"param_groups": self.param_groups, "state": self.state}


class FakeTorch:
    def __init__(self):
        self.backends = SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True))
        self.mps = SimpleNamespace(manual_seed=self._mps_seed, get_rng_state=self._mps_state)
        self.cpu = b"cpu-start"
        self.mps_state = b"mps-start"
        self.seed = None
    def manual_seed(self, seed): self.seed = seed; self.cpu = f"cpu:{seed}".encode()
    def _mps_seed(self, seed): self.mps_state = f"mps:{seed}".encode()
    def initial_seed(self): return self.seed
    def get_rng_state(self): return self.cpu
    def _mps_state(self): return self.mps_state


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.checkpoint = self.path / "toy-checkpoint"
        self.checkpoint.write_bytes(b"toy fixture; never deserialize")
        self.receipt_path = self.path / "parent-receipt.json"
        self.receipt_path.write_text("toy parent receipt")
        self.model, self.optimizer = ToyModel(), ToyOptimizer()
        self.parent_rng = {"python": "p", "numpy": "n", "torch_cpu": "c", "torch_mps": "m"}
        self.live_rng = dict(self.parent_rng)
        self.restores = 0
        self.events = []
        self.fake_torch = FakeTorch()
        self.fake_torch.manual_seed = lambda seed: (self.events.append("torch_cpu"), setattr(self.fake_torch, "seed", seed), setattr(self.fake_torch, "cpu", f"cpu:{seed}".encode()))
        self.fake_torch.mps.manual_seed = lambda seed: (self.events.append("torch_mps"), setattr(self.fake_torch, "mps_state", f"mps:{seed}".encode()))
        self.python_api = SimpleNamespace(seed=lambda seed: self.events.append("python"))
        self.numpy_api = SimpleNamespace(seed=lambda seed: self.events.append("numpy"))
        self.expected = {
            "model": fp.fingerprint(self.model.state_dict()),
            "Adam": fp.fingerprint(self.optimizer.state_dict()),
            "RNG": fp.fingerprint(self.parent_rng),
        }
        self.raw_reference = self.reference_bytes("measured")
        self.reference_path = self.path / "rng-reference.json"
        self.reference_path.write_bytes(self.raw_reference)
        self.ref_hash = hashlib.sha256(self.raw_reference).hexdigest()
        self.vector_hash = rr.canonical_vector_sha256(STUDY, REPLICA, SEEDS)
        self.cpu_digest = fp.fingerprint(f"cpu:{SEEDS['torch_cpu_global_seed']}".encode())
        self.mps_digest = fp.fingerprint(f"mps:{SEEDS['action_sampler_torch_mps_seed']}".encode())

    def reference_bytes(self, status):
        body = {
            "schema": rr.SCHEMA, "status": status, "backend": "mps",
            "torch_version": VERSION,
            "accepted_checkpoint_sha256": rr.ACCEPTED_CHECKPOINT_SHA256,
            "parent_receipt_sha256": rr.PARENT_RECEIPT_SHA256,
            "study_id": STUDY, "replica": REPLICA,
            "complete_seed_vector": SEEDS,
            "vector_sha256": rr.canonical_vector_sha256(STUDY, REPLICA, SEEDS),
            "cpu_rng_state_sha256": "0" * 64,
            "mps_rng_state_sha256": "0" * 64,
        }
        body["cpu_rng_state_sha256"] = fp.fingerprint(f"cpu:{SEEDS['torch_cpu_global_seed']}".encode())
        body["mps_rng_state_sha256"] = fp.fingerprint(f"mps:{SEEDS['action_sampler_torch_mps_seed']}".encode())
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()

    def capture_rngpayload(self): return dict(self.live_rng)

    def source(self):
        return {"receipt_sha256": t.ACCEPTED_PARENT_RECEIPT_SHA256,
                "checkpoint_sha256": rr.ACCEPTED_CHECKPOINT_SHA256,
                "checkpoint_path": str(self.checkpoint),
                "receipt_path": str(self.receipt_path),
                "checkpoint_fingerprints": dict(t.EXPECTED_PARENT),
                "learner_fingerprints": dict(t.EXPECTED_PARENT)}

    def restore(self):
        self.restores += 1
        self.events.append("restore")
        self.model.weights["w"] = ToyArray()
        self.optimizer.param_groups[0]["lr"] = 0.02
        self.optimizer.state["w"]["exp_avg"] = ToyArray(b"moment-01")
        self.live_rng = dict(self.parent_rng)

    def call(self, session=None, source=None, reference=None):
        session = session or t.TransitionSession()
        reference = reference or {"receipt_path": self.reference_path,
                                  "receipt_sha256": self.ref_hash,
                                  "vector_sha256": self.vector_hash}
        claim_file = self.path / "durable-attempt.claimed"
        def claim():
            fd = claim_file.open("x")
            fd.write("claimed\n")
            fd.close()
        args = dict(session=session, attempt_claim=claim, backend="mps", seeds=SEEDS,
                    pair={"pair_id": "pair-1", "A": SEEDS, "B": SEEDS},
                    verify_trusted_source=source or self.source,
                    restore_trusted=self.restore, model=self.model,
                    optimizer=self.optimizer, rng_capture=self.capture_rngpayload,
                    pinned_rng_reference=reference, python_api=self.python_api,
                    numpy_api=self.numpy_api, torch_api=self.fake_torch,
                    pair_id="pair-1", arm="A_constant_3e-5", study_id=STUDY,
                    replica=REPLICA, torch_version=VERSION)
        return t.transition(**args)

    def test_success_and_lr_full_hash_changes_content_hash_stays(self):
        with patch.object(t, "EXPECTED_PARENT", self.expected), \
             patch.object(t, "_sha256_file", side_effect=lambda path: (
                 t.ACCEPTED_PARENT_RECEIPT_SHA256 if str(path).endswith("parent-receipt.json")
                 else rr.ACCEPTED_CHECKPOINT_SHA256)):
            result = self.call()
        self.assertEqual(self.restores, 1)
        self.assertEqual(self.events, ["restore", "python", "numpy", "torch_cpu", "torch_mps"])
        self.assertEqual(t.controller_lr("B_linear_3e-5_to_1e-5_over_60", 373), 3e-5)
        self.assertEqual(t.controller_lr("B_linear_3e-5_to_1e-5_over_60", 432), 1e-5)
        self.assertEqual(result["parent_fingerprints"], self.expected)
        self.assertNotEqual(result["post_lr_fingerprints"]["Adam"], self.expected["Adam"])
        self.assertEqual(result["post_lr_fingerprints"]["Adam_content_excluding_lr"],
                         fp.optimizer_content_fingerprint(self.optimizer.state_dict()))
        self.assertEqual(self.optimizer.param_groups[0]["lr"], 3e-5)

    def test_in_place_moment_mutation_detected_after_reseed(self):
        session = t.TransitionSession()
        original = self.capture_rngpayload
        def mutate():
            self.live_rng = original()
            if self.fake_torch.seed is not None:
                self.optimizer.state["w"]["exp_avg"] = ToyArray(b"moment-08")
            return dict(self.live_rng)
        self.capture_rngpayload = mutate
        with patch.object(t, "EXPECTED_PARENT", self.expected), \
             patch.object(t, "_sha256_file", side_effect=lambda path: (
                 t.ACCEPTED_PARENT_RECEIPT_SHA256 if str(path).endswith("parent-receipt.json")
                 else rr.ACCEPTED_CHECKPOINT_SHA256)), self.assertRaisesRegex(ValueError, "reseeding changed"):
            self.call(session=session)
        self.assertTrue(session._started)
        with self.assertRaisesRegex(RuntimeError, "already consumed"):
            self.call(session=session)

    def test_pending_reference_rejected_before_restore_and_attempt(self):
        raw = self.reference_bytes("pending_notrun")
        self.reference_path.write_bytes(raw)
        self.ref_hash = hashlib.sha256(raw).hexdigest()
        session = t.TransitionSession()
        with patch.object(t, "EXPECTED_PARENT", self.expected), \
             patch.object(t, "_sha256_file", side_effect=lambda path: (
                 t.ACCEPTED_PARENT_RECEIPT_SHA256 if str(path).endswith("parent-receipt.json")
                 else rr.ACCEPTED_CHECKPOINT_SHA256)), self.assertRaisesRegex(ValueError, "not measured"):
            self.call(session=session)
        self.assertEqual(self.restores, 0)
        self.assertFalse(session._started)

    def test_wrong_reference_binding_rejected_before_restore(self):
        bad = {"receipt_path": self.reference_path,
               "receipt_sha256": self.ref_hash, "vector_sha256": "f" * 64}
        session = t.TransitionSession()
        with patch.object(t, "EXPECTED_PARENT", self.expected), \
             patch.object(t, "_sha256_file", side_effect=lambda path: (
                 t.ACCEPTED_PARENT_RECEIPT_SHA256 if str(path).endswith("parent-receipt.json")
                 else rr.ACCEPTED_CHECKPOINT_SHA256)), self.assertRaisesRegex(ValueError, "expected vector hash"):
            self.call(session=session, reference=bad)
        self.assertEqual(self.restores, 0)
        self.assertFalse(session._started)

    def test_failed_live_restore_consumes_session_and_blocks_retry(self):
        session = t.TransitionSession()
        with patch.object(t, "EXPECTED_PARENT", {"model": "wrong", "Adam": "wrong", "RNG": "wrong"}), \
             patch.object(t, "_sha256_file", side_effect=lambda path: (
                 t.ACCEPTED_PARENT_RECEIPT_SHA256 if str(path).endswith("parent-receipt.json")
                 else rr.ACCEPTED_CHECKPOINT_SHA256)), self.assertRaisesRegex(ValueError, "did not produce"):
            self.call(session=session)
        self.assertTrue(session._started)
        with self.assertRaisesRegex(RuntimeError, "already consumed"):
            self.call(session=session)


if __name__ == "__main__": unittest.main(verbosity=2)
