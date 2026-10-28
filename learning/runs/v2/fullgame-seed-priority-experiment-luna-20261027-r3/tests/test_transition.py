"""CPU toy fixtures only. No production checkpoint deserialization or real MPS seeding."""
import hashlib
import importlib
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import transition as t
import fingerprints as fp
import rng_reference as rr
from attempt_claim import AttemptClaim
import driver_binding as db

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
        self.param_groups = [{"lr": 3e-5, "betas": (0.9, 0.999), "params": ["w"]}]
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
        self.parent_rng = {"python": "p", "numpy_global": "n", "numpy_generator": None, "torch_cpu": "c", "torch_mps": "m", "sampling_backend": "torch_global_mps"}
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
        self.optimizer.param_groups[0]["lr"] = 3e-5
        self.optimizer.state["w"]["exp_avg"] = ToyArray(b"moment-01")
        self.live_rng = dict(self.parent_rng)

    def call(self, session=None, source=None, reference=None):
        session = session or t.TransitionSession()
        reference = reference or {"receipt_path": self.reference_path,
                                  "receipt_sha256": self.ref_hash,
                                  "vector_sha256": self.vector_hash}
        claim_file = self.path / "durable-attempt.claimed"
        claim_record = {"run_id":"synthetic-run-1", "study_id":STUDY, "replica":REPLICA,
                        "arm":"control_constant_3e-5", "vector_sha256":self.vector_hash,
                        "parent_checkpoint_sha256":rr.ACCEPTED_CHECKPOINT_SHA256}
        args = dict(session=session, attempt_claim=AttemptClaim(claim_file, claim_record), backend="mps", seeds=SEEDS,
                    pair={"pair_id": "pair-1", "A": SEEDS, "B": SEEDS},
                    verify_trusted_source=source or self.source,
                    restore_trusted=self.restore, model=self.model,
                    optimizer=self.optimizer, rng_capture=self.capture_rngpayload,
                    pinned_rng_reference=reference, python_api=self.python_api,
                    numpy_api=self.numpy_api, torch_api=self.fake_torch,
                    pair_id="pair-1", arm="control_constant_3e-5", study_id=STUDY,
                    replica=REPLICA, torch_version=VERSION, run_id="synthetic-run-1")
        return t.transition(**args)

    def test_success_saved_lr_noop_preserves_full_and_content_hash(self):
        with patch.object(t, "EXPECTED_PARENT", self.expected), \
             patch.object(t, "_sha256_file", side_effect=lambda path: (
                 t.ACCEPTED_PARENT_RECEIPT_SHA256 if str(path).endswith("parent-receipt.json")
                 else rr.ACCEPTED_CHECKPOINT_SHA256)):
            result = self.call()
        self.assertEqual(self.restores, 1)
        self.assertEqual(self.events, ["restore", "python", "numpy", "torch_cpu", "torch_mps"])
        self.assertEqual(t.controller_lr("progressive1000_curriculum_constant_3e-5", 373), 3e-5)
        self.assertEqual(t.controller_lr("progressive1000_curriculum_constant_3e-5", 432), 3e-5)
        self.assertEqual(result["parent_fingerprints"], self.expected)
        self.assertEqual(result["post_lr_fingerprints"]["Adam"], self.expected["Adam"])
        self.assertEqual(result["post_lr_fingerprints"]["Adam_content_excluding_lr"],
                         fp.optimizer_content_fingerprint(self.optimizer.state_dict()))
        self.assertEqual(self.optimizer.param_groups[0]["lr"], 3e-5)
        self.assertEqual(result["new_controller"]["end_lr"], 3e-5)

    def test_attempt_claim_blocks_fresh_session_reload_and_subprocess(self):
        claim_path = self.path / "registered.claim"
        claim_record = {"run_id":"r", "study_id":"s", "replica":1, "arm":"A",
                        "vector_sha256":"a"*64, "parent_checkpoint_sha256":"b"*64}
        receipt = AttemptClaim(claim_path, claim_record).claim()
        claim_path.write_bytes(b"consumed restore failed")
        with self.assertRaises(FileExistsError): AttemptClaim(claim_path, claim_record).claim()
        importlib.reload(t)
        with self.assertRaises(FileExistsError): AttemptClaim(claim_path, claim_record).claim()
        with self.assertRaises(FileExistsError): AttemptClaim(claim_path, claim_record).claim()
        code = "from attempt_claim import AttemptClaim; AttemptClaim(%r, %r).claim()" % (str(claim_path), claim_record)
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=Path(__file__).parent,
            env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE":"1"}, capture_output=True)
        self.assertNotEqual(result.returncode, 0)


    def test_model_and_optimizer_content_mutation_after_lr_override_are_distinct(self):
        model_before = fp.fingerprint(self.model.state_dict())
        adam_before = fp.fingerprint(self.optimizer.state_dict())
        content_before = fp.optimizer_content_fingerprint(self.optimizer.state_dict())
        self.optimizer.param_groups[0]["lr"] = 3e-5
        self.assertEqual(fp.fingerprint(self.optimizer.state_dict()), adam_before)
        self.assertEqual(fp.optimizer_content_fingerprint(self.optimizer.state_dict()), content_before)
        self.model.weights["w"] = ToyArray(b"changed")
        self.assertNotEqual(fp.fingerprint(self.model.state_dict()), model_before)
        self.optimizer.state["w"]["exp_avg"] = ToyArray(b"changed")
        self.assertNotEqual(fp.optimizer_content_fingerprint(self.optimizer.state_dict()), content_before)

    def test_controller_boundaries_and_arm_metadata(self):
        self.assertEqual(t.controller_lr("progressive1000_curriculum_constant_3e-5", 373), 3e-5)
        self.assertEqual(t.controller_lr("progressive1000_curriculum_constant_3e-5", 432), 3e-5)
        for update in (372, 433):
            with self.assertRaisesRegex(ValueError, r"\[373, 432\]"):
                t.controller_lr("control_constant_3e-5", update)
        self.assertEqual(t.controller_lr("control_constant_3e-5", 432), 3e-5)

    def test_seed_types_reject_bool_and_float_before_claim(self):
        for bad in (True, 1.0):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                t.validate_seeds({**SEEDS, "python_random_seed": bad})

    def test_reference_binding_rejects_bool_float_replica_and_seed_before_claim(self):
        base = dict(receipt_path=self.reference_path, expected_receipt_sha256=self.ref_hash,
                    expected_study_id=STUDY, expected_replica=REPLICA,
                    expected_seed_vector=SEEDS, expected_vector_sha256=self.vector_hash,
                    expected_torch_version=VERSION)
        for bad in (True, 1.0):
            with self.subTest(replica=bad), self.assertRaisesRegex(ValueError, "positive integer"):
                rr.load_bound_reference(**{**base, "expected_replica":bad})
            with self.subTest(seed=bad), self.assertRaisesRegex(ValueError, "integers"):
                rr.load_bound_reference(**{**base, "expected_seed_vector":{**SEEDS, "python_random_seed":bad}})

    def test_lr_change_002_to_saved_lr_changes_only_full_adam_hash(self):
        self.optimizer.param_groups[0]["lr"] = 0.02
        full_before = fp.fingerprint(self.optimizer.state_dict())
        content_before = fp.optimizer_content_fingerprint(self.optimizer.state_dict())
        self.optimizer.param_groups[0]["lr"] = 3e-5
        self.assertNotEqual(fp.fingerprint(self.optimizer.state_dict()), full_before)
        self.assertEqual(fp.optimizer_content_fingerprint(self.optimizer.state_dict()), content_before)

    def test_exclusion_ranges_have_positive_and_negative_coverage(self):
        controls = [{"slot":i, "episode_index":0, "first_actual_seed":i+1, "rejection_counter":0} for i in range(64)]
        t.validate_exclusion_controls(t.EXPECTED_EXCLUSION_RANGES, controls)
        bad = [dict(row) for row in controls]
        bad[-1]["first_actual_seed"] = t.EXPECTED_EXCLUSION_RANGES[0][0]
        with self.assertRaisesRegex(ValueError, "collides"):
            t.validate_exclusion_controls(t.EXPECTED_EXCLUSION_RANGES, bad)

    def test_pinned_sources_verify_exact_paths_and_hashes(self):
        root = Path(__file__).resolve().parents[5]
        verified = db.verify_pinned_sources(root)
        self.assertEqual(verified[str(db.CHECKPOINTS_RELATIVE)]["sha256"], db.CHECKPOINTS_SHA256)
        source = (root / db.CHECKPOINTS_RELATIVE).read_text()
        self.assertIn("def capture_rng(", source)
        self.assertIn("def restore_learner(", source)
        self.assertEqual(db.RAW_RNG_KEYS, {"python", "numpy_global", "numpy_generator", "torch_cpu", "torch_mps", "sampling_backend"})

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

    def test_pending_reference_rejected_before_restore_and_claim(self):
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
        self.assertFalse((self.path / "durable-attempt.claimed").exists())

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
        self.assertFalse((self.path / "durable-attempt.claimed").exists())

    def test_failed_live_restore_consumes_session_and_blocks_retry(self):
        session = t.TransitionSession()
        with patch.object(t, "EXPECTED_PARENT", {"model": "wrong", "Adam": "wrong", "RNG": "wrong"}), \
             patch.object(t, "_sha256_file", side_effect=lambda path: (
                 t.ACCEPTED_PARENT_RECEIPT_SHA256 if str(path).endswith("parent-receipt.json")
                 else rr.ACCEPTED_CHECKPOINT_SHA256)), self.assertRaisesRegex(ValueError, "did not produce"):
            self.call(session=session)
        self.assertTrue(session._started)
        self.assertTrue((self.path / "durable-attempt.claimed").exists())
        with self.assertRaisesRegex(RuntimeError, "already consumed"):
            self.call(session=session)
        with patch.object(t, "EXPECTED_PARENT", {"model": "wrong", "Adam": "wrong", "RNG": "wrong"}), \
             patch.object(t, "_sha256_file", side_effect=lambda path: (
                 t.ACCEPTED_PARENT_RECEIPT_SHA256 if str(path).endswith("parent-receipt.json")
                 else rr.ACCEPTED_CHECKPOINT_SHA256)), self.assertRaises(FileExistsError):
            self.call(session=t.TransitionSession())


if __name__ == "__main__": unittest.main(verbosity=2)
