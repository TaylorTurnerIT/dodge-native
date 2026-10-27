"""Representation configuration, legacy teacher fidelity, and CLI provenance."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import copy
from dataclasses import asdict, fields
import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

HAS_MODELS = importlib.util.find_spec("torch") is not None and importlib.util.find_spec("numpy") is not None
HAS_NATIVE = importlib.util.find_spec("dodge_learning._native") is not None
PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPRESENTATION_DEFAULTS = {
    "attention_prior": 1.0, "relative_geometry": False, "kind_embedding_scale": 1.0,
}
LEGACY_FIELDS = {"embed_dim", "depth", "num_heads", "mlp_ratio", "dropout"}

if HAS_MODELS and HAS_NATIVE:
    import torch

    from dodge_learning.checkpoints import load_teacher_checkpoint, save_teacher_checkpoint
    from dodge_learning.entity_teacher import EntityActorCritic, EntityTeacherConfig, batch_entities, encode_entities
    from dodge_learning.env import NativeEnvironment
    from dodge_learning.ppo import PPOConfig
    from dodge_learning.seeds import seed_manifest
    from dodge_learning.teacher_bootstrap import main as bootstrap_main
    from dodge_learning.teacher_run import _prepare_teacher, main, source_manifest


@unittest.skipUnless(HAS_MODELS and HAS_NATIVE, "requires models and the native bridge")
class TeacherRepresentationControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)
        with NativeEnvironment(seed=1000, max_episode_frames=2) as environment:
            cls.observation = environment.current()
        cls.batch = batch_entities([encode_entities(cls.observation["privileged_state"])])
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(7)
            cls.baseline_model = EntityActorCritic(EntityTeacherConfig(embed_dim=32, depth=1)).eval()
        result = SimpleNamespace(
            model=cls.baseline_model, optimizer_state={}, config=PPOConfig(total_frames=2),
            metrics={"provenance": cls.observation["info"]["provenance"], "fixture": "untrained-checkpoint"},
        )
        cls.current_path = cls.root / "current.pt"
        save_teacher_checkpoint(
            cls.current_path, result, seed_manifest=seed_manifest(), source_manifest=source_manifest(),
        )
        cls.current_payload = torch.load(cls.current_path, weights_only=True, map_location="cpu")
        cls.legacy_payload = copy.deepcopy(cls.current_payload)
        cls.legacy_payload["teacher_schema_version"] = 1
        cls.legacy_payload["model_config"] = {
            key: value for key, value in cls.legacy_payload["model_config"].items() if key in LEGACY_FIELDS
        }
        cls.legacy_path = cls.root / "legacy.pt"
        torch.save(cls.legacy_payload, cls.legacy_path)

    @classmethod
    def tearDownClass(cls) -> None:
        torch.set_num_threads(cls.previous_threads)
        cls.directory.cleanup()

    def test_schema_one_defaults_preserve_outputs_metadata_digest_and_sampling_rng(self) -> None:
        original = self.legacy_path.read_bytes()
        rng = torch.random.get_rng_state().clone()
        loaded = load_teacher_checkpoint(self.legacy_path)
        self.assertTrue(torch.equal(rng, torch.random.get_rng_state()))
        self.assertEqual(loaded.metadata["teacher_schema_version"], 1)
        self.assertEqual(set(loaded.metadata["model_config"]), LEGACY_FIELDS)
        self.assertEqual(loaded.metadata["model_config"], self.legacy_payload["model_config"])
        self.assertEqual(loaded.metadata["source_manifest"], self.legacy_payload["source_manifest"])
        self.assertEqual(loaded.sha256, hashlib.sha256(original).hexdigest())
        self.assertEqual(self.legacy_path.read_bytes(), original)
        for key, expected in REPRESENTATION_DEFAULTS.items():
            self.assertEqual(getattr(loaded.model.config, key), expected)
        with torch.no_grad():
            expected = self.baseline_model.distillation_outputs(self.batch)
            actual = loaded.model.distillation_outputs(self.batch)
        for name in ("logits", "value", "latent", "attention"):
            torch.testing.assert_close(getattr(actual, name), getattr(expected, name), rtol=0, atol=0)

    def test_retained_real_schema_one_checkpoint_matches_archived_forward(self) -> None:
        artifact = PROJECT_ROOT / "learning/runs/entity-teacher-bootstrap-weighted-10000/teacher.pt"
        archive = PROJECT_ROOT / "learning/.cache/teacher-training-review-r2/learning/python/dodge_learning/entity_teacher.py"
        if not artifact.is_file() or not archive.is_file():
            self.skipTest("retained local legacy artifact and frozen model source are optional")
        body = artifact.read_bytes()
        copied = self.root / "real-legacy-copy.pt"
        copied.write_bytes(body)
        payload = torch.load(copied, weights_only=True, map_location="cpu")
        self.assertEqual(payload["teacher_schema_version"], 1)
        module_name = "_dodge_legacy_entity_forward_for_representation_test"
        spec = importlib.util.spec_from_file_location(module_name, archive)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
            with torch.random.fork_rng(devices=[]):
                legacy_model = module.EntityActorCritic(module.EntityTeacherConfig(**payload["model_config"])).eval()
            legacy_model.load_state_dict(payload["model_state"], strict=True)
            legacy_batch = module.EntityBatch(**{field.name: getattr(self.batch, field.name) for field in fields(module.EntityBatch)})
            loaded = load_teacher_checkpoint(copied)
            with torch.no_grad():
                expected = legacy_model.distillation_outputs(legacy_batch)
                actual = loaded.model.distillation_outputs(self.batch)
            for name in ("logits", "value", "latent", "attention"):
                torch.testing.assert_close(getattr(actual, name), getattr(expected, name), rtol=0, atol=0)
            self.assertEqual(loaded.metadata["model_config"], payload["model_config"])
            self.assertEqual(loaded.sha256, hashlib.sha256(body).hexdigest())
            self.assertEqual(artifact.read_bytes(), body)
        finally:
            del sys.modules[module_name]

    def test_schema_version_requires_exact_config_fields_and_uncoerced_values(self) -> None:
        cases = []
        for version in (True, 1.0, 0, 3):
            payload = copy.deepcopy(self.current_payload)
            payload["teacher_schema_version"] = version
            cases.append((f"bad-version-{version!r}", payload))
        for version, config in (
            (1, self.current_payload["model_config"]),
            (2, self.legacy_payload["model_config"]),
            (1, {**self.legacy_payload["model_config"], "attention_prior": 1.0}),
        ):
            payload = copy.deepcopy(self.current_payload)
            payload["teacher_schema_version"] = version
            payload["model_config"] = config
            cases.append((f"mixed-fields-{len(cases)}", payload))
        payload = copy.deepcopy(self.current_payload)
        del payload["model_config"]["relative_geometry"]
        cases.append(("partial-new-fields", payload))
        for key, values in (
            ("attention_prior", (True, 0, "512")),
            ("relative_geometry", (0, 1, "false")),
            ("kind_embedding_scale", (True, 0, "0.02")),
        ):
            for value in values:
                payload = copy.deepcopy(self.current_payload)
                payload["model_config"][key] = value
                cases.append((f"invalid-{key}-{value!r}", payload))
        for index, (label, payload) in enumerate(cases):
            path = self.root / f"malformed-{index}.pt"
            torch.save(payload, path)
            with self.subTest(label=label), self.assertRaises(ValueError):
                load_teacher_checkpoint(path)

    def test_new_checkpoint_records_all_flags_and_preserves_opt_in_outputs(self) -> None:
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(7)
            model = EntityActorCritic(EntityTeacherConfig(
                embed_dim=32, depth=1, attention_prior=512., relative_geometry=True,
                kind_embedding_scale=.02,
            )).eval()
        result = SimpleNamespace(
            model=model, optimizer_state={}, config=PPOConfig(total_frames=2),
            metrics={"provenance": self.observation["info"]["provenance"]},
        )
        path = self.root / "opt-in.pt"
        save_teacher_checkpoint(path, result, seed_manifest=seed_manifest(), source_manifest=source_manifest())
        payload = torch.load(path, weights_only=True, map_location="cpu")
        loaded = load_teacher_checkpoint(path)
        self.assertEqual(payload["teacher_schema_version"], 2)
        self.assertEqual(len(payload["model_config"]), 8)
        self.assertEqual(payload["model_config"], asdict(model.config))
        self.assertEqual(loaded.model.config, model.config)
        with torch.no_grad():
            expected = model.distillation_outputs(self.batch)
            actual = loaded.model.distillation_outputs(self.batch)
        for name in ("logits", "value", "latent", "attention"):
            torch.testing.assert_close(getattr(actual, name), getattr(expected, name), rtol=0, atol=0)

    def test_cli_flags_are_recorded_and_warm_start_rejects_representation_mismatch(self) -> None:
        output = self.root / "cli-ppo"
        with redirect_stdout(io.StringIO()):
            main([
                "train", "--output-dir", str(output), "--frames", "2", "--max-seconds", "30",
                "--rollout-steps", "2", "--minibatch-size", "2", "--epochs", "1",
                "--episode-frames", "2", "--embed-dim", "32", "--depth", "1",
                "--attention-prior", "512", "--relative-geometry", "--kind-embedding-scale", ".02",
            ])
        loaded = load_teacher_checkpoint(output / "teacher.pt")
        self.assertEqual(loaded.metadata["model_config"]["attention_prior"], 512.)
        self.assertIs(loaded.metadata["model_config"]["relative_geometry"], True)
        self.assertEqual(loaded.metadata["model_config"]["kind_embedding_scale"], .02)
        values = dict(
            architecture="entity_transformer", embed_dim=32, depth=1, num_heads=4,
            attention_prior=512., relative_geometry=True, kind_embedding_scale=.02,
            warm_start=output / "teacher.pt",
        )
        for key, value in REPRESENTATION_DEFAULTS.items():
            changed = {**values, key: value}
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "representation"):
                _prepare_teacher(argparse.Namespace(**changed), PPOConfig(total_frames=2), seed_manifest())

    def test_bootstrap_cli_records_the_same_model_and_training_flags(self) -> None:
        output = self.root / "cli-bootstrap"
        with redirect_stdout(io.StringIO()):
            bootstrap_main([
                "--output-dir", str(output), "--frames", "2", "--max-seconds", "30",
                "--episode-frames", "2", "--batch-size", "2", "--epochs", "1",
                "--attention-prior", "512", "--relative-geometry", "--kind-embedding-scale", ".02",
            ])
        loaded = load_teacher_checkpoint(output / "teacher.pt")
        for key, expected in (("attention_prior", 512.), ("relative_geometry", True), ("kind_embedding_scale", .02)):
            self.assertEqual(loaded.metadata["model_config"][key], expected)
            self.assertEqual(loaded.metadata["training_config"][key], expected)
        self.assertEqual(loaded.metadata["metrics"]["model_config"], loaded.metadata["model_config"])

    def test_legacy_mlp_rejects_nondefault_representation_flags_before_run_creation(self) -> None:
        for flag in (("--attention-prior", "512"), ("--relative-geometry",), ("--kind-embedding-scale", ".02")):
            output = self.root / f"reject-mlp-{flag[0]}"
            with self.subTest(flag=flag), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["train", "--output-dir", str(output), "--architecture", "legacy_mlp", *flag])
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
