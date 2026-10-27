"""Native entity-teacher training/checkpoint integration, without quality claims."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest

HAS_MODELS = importlib.util.find_spec("torch") is not None and importlib.util.find_spec("numpy") is not None
HAS_NATIVE = importlib.util.find_spec("dodge_learning._native") is not None
if HAS_MODELS and HAS_NATIVE:
    import torch

    from dodge_learning.checkpoints import load_teacher_checkpoint, save_teacher_checkpoint
    from dodge_learning.entity_teacher import EntityActorCritic, batch_entities, encode_entities
    from dodge_learning.env import NativeEnvironment
    from dodge_learning.ppo import PPOConfig, train_teacher
    from dodge_learning.seeds import seed_manifest
    from dodge_learning.teacher import StateActorCritic
    from dodge_learning.teacher_eval import GreedyTeacherPolicy
    from dodge_learning.teacher_run import source_manifest


@unittest.skipUnless(HAS_MODELS and HAS_NATIVE, "build the native bridge and install the optional models extra")
class EntityPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)
        cls.config = PPOConfig(
            total_frames=8, rollout_steps=4, epochs=1, minibatch_size=4,
            max_episode_frames=4, train_seeds=(1000, 1001), max_seconds=60,
        )
        cls.progress = []
        # Leave architecture and model unset to verify the production default.
        cls.result = train_teacher(cls.config, progress_callback=cls.progress.append)
        cls.sources = source_manifest()

    @classmethod
    def tearDownClass(cls) -> None:
        torch.set_num_threads(cls.previous_threads)

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "entity-teacher.pt"

    def save(self) -> dict:
        return save_teacher_checkpoint(
            self.path, self.result, seed_manifest=seed_manifest(), source_manifest=self.sources,
        )

    def test_default_native_training_collects_and_optimizes_exact_budget(self) -> None:
        self.assertIsInstance(self.result.model, EntityActorCritic)
        metrics = self.result.metrics
        self.assertEqual(metrics["architecture"], "entity_transformer")
        for name, expected in (
            ("frames_collected", 8), ("updates", 2), ("optimizer_steps", 2),
            ("samples_optimized", 8), ("unoptimized_frames", 0),
            ("episodes_started", 2), ("episodes_completed", 2),
            ("truncated_episodes", 2), ("terminal_episodes", 0),
        ):
            with self.subTest(name=name):
                self.assertEqual(metrics[name], expected)
        self.assertEqual(metrics["stop_reason"], "frame_budget")
        self.assertEqual([row["frames_collected"] for row in self.progress], [4, 8])
        self.assertEqual(metrics["provenance"]["feature_schema_version"], 2)
        self.assertEqual(metrics["provenance"]["privileged_schema_version"], 1)
        self.assertTrue(math.isfinite(metrics["loss"]))
        self.assertTrue(self.result.optimizer_state["state"])

    def test_native_checkpoint_roundtrip_preserves_outputs_and_exact_architecture_receipt(self) -> None:
        with NativeEnvironment(seed=1000, max_episode_frames=4) as env:
            observation = env.current()
        batch = batch_entities([encode_entities(observation["privileged_state"])])
        self.result.model.eval()
        with torch.no_grad():
            expected = self.result.model.distillation_outputs(batch)
        receipt = self.save()
        payload = torch.load(self.path, map_location="cpu", weights_only=True)
        loaded = load_teacher_checkpoint(self.path)
        self.assertEqual(payload["format_version"], 2)
        self.assertEqual(payload["kind"], "dodge_entity_transformer_teacher")
        self.assertEqual(payload["privileged_schema_version"], 1)
        for key in ("format_version", "kind"):
            self.assertEqual(receipt[key], payload[key])
            self.assertEqual(loaded.metadata[key], payload[key])
        self.assertEqual(receipt["sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(loaded.sha256, receipt["sha256"])
        self.assertEqual(loaded.metadata["metrics"]["provenance"], self.result.metrics["provenance"])
        self.assertEqual(loaded.metadata["source_manifest"], self.sources)
        self.assertEqual(loaded.metadata["training_config"]["train_seeds"], [1000, 1001])
        self.assertIsInstance(loaded.model, EntityActorCritic)
        self.assertFalse(loaded.model.training)
        with torch.no_grad():
            actual = loaded.model.distillation_outputs(batch)
        for name in ("logits", "value", "latent", "attention"):
            torch.testing.assert_close(getattr(actual, name), getattr(expected, name), atol=0, rtol=0)

        policy = GreedyTeacherPolicy(loaded.model, loaded.metadata["metrics"]["provenance"])
        self.assertEqual(policy.act(observation), int(expected.logits.argmax(dim=-1).item()))
        # The new policy must use privileged_state, even when legacy features
        # are absent or invalid. Neither pixels nor diagnostic scores enter it.
        alternate = copy.deepcopy(observation)
        alternate["train_only_state"] = None
        alternate["pixels"] = b"unused by the entity teacher"
        alternate["info"]["score"] = -123456
        self.assertEqual(policy.act(alternate), policy.act(observation))

    def test_missing_privileged_schema_is_rejected_by_policy_and_checkpoint(self) -> None:
        receipt = self.save()
        loaded = load_teacher_checkpoint(self.path)
        self.assertEqual(receipt["kind"], "dodge_entity_transformer_teacher")
        with NativeEnvironment(seed=1000, max_episode_frames=4) as env:
            observation = env.current()
        del observation["info"]["provenance"]["privileged_schema_version"]
        with self.assertRaisesRegex(ValueError, "privileged schema"):
            GreedyTeacherPolicy(loaded.model).act(observation)
        payload = torch.load(self.path, map_location="cpu", weights_only=True)
        for missing in ("checkpoint_field", "training_provenance"):
            changed = copy.deepcopy(payload)
            if missing == "checkpoint_field":
                del changed["privileged_schema_version"]
            else:
                del changed["metrics"]["provenance"]["privileged_schema_version"]
            bad_path = self.path.parent / f"missing-{missing}.pt"
            torch.save(changed, bad_path)
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                load_teacher_checkpoint(bad_path)

    def test_missing_native_privileged_schema_fails_before_ppo_rollout(self) -> None:
        class MissingPrivilegedSchemaEnvironment:
            def __init__(self, **kwargs):
                self.inner = NativeEnvironment(**kwargs)

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.inner.close()

            def reset(self, seed):
                payload = self.inner.reset(seed)
                del payload["info"]["provenance"]["privileged_schema_version"]
                return payload

            def step(self, action):
                raise AssertionError("invalid schema must fail before any native step")

        with self.assertRaisesRegex(RuntimeError, "privileged schema"):
            train_teacher(self.config, environment_factory=MissingPrivilegedSchemaEnvironment)

    def test_entity_checkpoint_rejects_legacy_labels_and_legacy_weights(self) -> None:
        self.save()
        payload = torch.load(self.path, map_location="cpu", weights_only=True)
        with torch.random.fork_rng(devices=[]):
            legacy_weights = StateActorCritic().state_dict()
        for corruption in ("legacy_format", "legacy_kind", "legacy_architecture_label", "legacy_weights"):
            changed = copy.deepcopy(payload)
            if corruption == "legacy_format":
                changed["format_version"] = 1
            elif corruption == "legacy_kind":
                changed["kind"] = "dodge_state_teacher"
            elif corruption == "legacy_architecture_label":
                changed["kind"] = "dodge_state_teacher"
                changed["format_version"] = 1
                del changed["privileged_schema_version"]
            else:
                changed["model_state"] = legacy_weights
            bad_path = self.path.parent / f"{corruption}.pt"
            torch.save(changed, bad_path)
            with self.subTest(corruption=corruption), self.assertRaises(ValueError):
                load_teacher_checkpoint(bad_path)


if __name__ == "__main__":
    unittest.main()
