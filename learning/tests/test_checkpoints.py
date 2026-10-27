"""Teacher checkpoint fidelity, provenance validation, and atomic publication."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

HAS_TORCH = importlib.util.find_spec("torch") is not None
if HAS_TORCH:
    import numpy as np
    import torch

    from dodge_learning.checkpoints import load_teacher_checkpoint, save_teacher_checkpoint
    from dodge_learning.seeds import seed_manifest
    from dodge_learning.teacher import EncodedState, StateActorCritic, TeacherConfig, batch_states


@dataclass(frozen=True)
class _TrainingConfig:
    train_seeds: tuple[int, ...] = (1000, 1001)
    discount: float = 0.99


@unittest.skipUnless(HAS_TORCH, "install the optional PyTorch models extra")
class TeacherCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)

    @classmethod
    def tearDownClass(cls) -> None:
        torch.set_num_threads(cls.previous_threads)

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "teacher.pt"
        self.model = StateActorCritic(TeacherConfig(hidden_dim=32, entity_dim=16))
        optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-3)
        state = EncodedState(
            np.ones(8, dtype=np.float32),
            np.zeros((1, 11), dtype=np.float32),
            np.zeros((0, 7), dtype=np.float32),
            np.zeros((0, 4), dtype=np.float32),
        )
        self.batch = batch_states([state])
        logits, values = self.model(self.batch)
        (logits.square().mean() + values.square().mean()).backward()
        optimizer.step()
        self.result = SimpleNamespace(
            model=self.model,
            optimizer_state=optimizer.state_dict(),
            metrics={"provenance": {"feature_schema_version": 2}, "native_frames": 8},
            config=_TrainingConfig(),
        )
        self.sources = {"source_hashes": {"teacher.py": "a" * 64}}

    def save(self):
        return save_teacher_checkpoint(
            self.path, self.result, seed_manifest=seed_manifest(), source_manifest=self.sources
        )

    def mutate_saved_payload(self, change):
        payload = torch.load(self.path, map_location="cpu", weights_only=True)
        change(payload)
        torch.save(payload, self.path)

    def test_roundtrip_preserves_predictions_and_json_safe_metadata(self) -> None:
        self.model.eval()
        with torch.no_grad():
            expected = self.model(self.batch)
        receipt = self.save()
        loaded = load_teacher_checkpoint(self.path)
        with torch.no_grad():
            actual = loaded.model(self.batch)
        for expected_tensor, actual_tensor in zip(expected, actual):
            self.assertTrue(torch.equal(expected_tensor, actual_tensor))
        self.assertFalse(loaded.model.training)
        self.assertTrue(all(p.device.type == "cpu" for p in loaded.model.parameters()))
        self.assertEqual(loaded.model.config, TeacherConfig(32, 16))
        self.assertEqual(loaded.sha256, receipt["sha256"])
        self.assertEqual(loaded.sha256, hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(loaded.metadata["training_config"]["train_seeds"], [1000, 1001])
        self.assertNotIn("model_state", loaded.metadata)
        self.assertNotIn("optimizer_state", loaded.metadata)
        self.assertEqual(loaded.metadata["source_manifest"], self.sources)
        json.dumps(receipt, allow_nan=False)
        json.dumps(loaded.metadata, allow_nan=False)
        payload = torch.load(self.path, map_location="cpu", weights_only=True)
        self.assertTrue(payload["optimizer_state"]["state"])
        self.assertTrue(all(value.device.type == "cpu" for value in payload["model_state"].values()))

    def test_schema_action_order_and_model_config_are_validated(self) -> None:
        changes = (
            lambda p: p.__setitem__("format_version", 2),
            lambda p: p.__setitem__("teacher_schema_version", 2),
            lambda p: p.__setitem__("native_feature_schema_version", 1),
            lambda p: p.__setitem__("kind", "student"),
            lambda p: p["action_names"].reverse(),
            lambda p: p["action_masks"].reverse(),
            lambda p: p["model_config"].__setitem__("hidden_dim", 0),
            lambda p: p["model_config"].__setitem__("hidden_dim", 1025),
            lambda p: p["model_config"].__setitem__("entity_dim", True),
            lambda p: p["model_config"].__setitem__("extra", 1),
            lambda p: p["model_config"].pop("entity_dim"),
        )
        for change in changes:
            with self.subTest(change=change):
                self.path.unlink(missing_ok=True)
                self.save()
                self.mutate_saved_payload(change)
                with self.assertRaises(ValueError):
                    load_teacher_checkpoint(self.path)

    def test_nonfinite_shape_and_dtype_corruptions_are_rejected(self) -> None:
        for corruption in ("nonfinite", "shape", "dtype", "missing"):
            with self.subTest(corruption=corruption):
                self.path.unlink(missing_ok=True)
                self.save()

                def change(payload):
                    key = next(iter(payload["model_state"]))
                    if corruption == "nonfinite":
                        payload["model_state"][key].flatten()[0] = float("nan")
                    elif corruption == "shape":
                        payload["model_state"][key] = torch.zeros(1)
                    elif corruption == "dtype":
                        payload["model_state"][key] = payload["model_state"][key].double()
                    else:
                        del payload["model_state"][key]

                self.mutate_saved_payload(change)
                with self.assertRaises(ValueError):
                    load_teacher_checkpoint(self.path)

    def test_seed_manifest_hash_and_actual_training_split_are_validated(self) -> None:
        self.save()
        self.mutate_saved_payload(lambda p: p.__setitem__("seed_manifest_hash", "0" * 64))
        with self.assertRaises(ValueError):
            load_teacher_checkpoint(self.path)
        for seeds in ((3000,), (), (1000, 1000)):
            self.path.unlink(missing_ok=True)
            self.result.config = _TrainingConfig(train_seeds=seeds)
            with self.subTest(seeds=seeds), self.assertRaises(ValueError):
                self.save()
            self.assertFalse(self.path.exists())

    def test_existing_checkpoint_and_racing_writer_are_never_overwritten(self) -> None:
        self.save()
        original = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.save()
        self.assertEqual(self.path.read_bytes(), original)
        self.path.unlink()
        original_link = __import__("os").link

        def concurrent_publish(source, destination):
            self.path.write_bytes(b"another writer")
            original_link(source, destination)

        with mock.patch("dodge_learning.checkpoints.os.link", side_effect=concurrent_publish):
            with self.assertRaises(FileExistsError):
                self.save()
        self.assertEqual(self.path.read_bytes(), b"another writer")
        self.assertEqual(list(self.path.parent.glob(".*.tmp")), [])

    def test_write_failure_cleans_only_owned_temporary_file(self) -> None:
        unrelated = self.path.parent / "keep.txt"
        unrelated.write_text("keep")
        with mock.patch("dodge_learning.checkpoints.torch.save", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                self.save()
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.path.parent.glob(".*.tmp")), [])
        self.assertEqual(unrelated.read_text(), "keep")

    def test_nonfinite_metadata_and_incompatible_training_provenance_fail_before_write(self) -> None:
        for metrics in (
            {"provenance": {"feature_schema_version": 2}, "loss": float("nan")},
            {"provenance": {"feature_schema_version": 1}},
            {},
        ):
            with self.subTest(metrics=metrics):
                self.result.metrics = metrics
                with self.assertRaises(ValueError):
                    self.save()
                self.assertFalse(self.path.exists())

    def test_save_and_load_do_not_advance_cpu_sampling_rng(self) -> None:
        before = torch.get_rng_state().clone()
        self.save()
        load_teacher_checkpoint(self.path)
        self.assertTrue(torch.equal(torch.get_rng_state(), before))


if __name__ == "__main__":
    unittest.main()
