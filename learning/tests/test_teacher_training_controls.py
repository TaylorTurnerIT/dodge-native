"""Teacher CLI controls and provenance-checked weights-only continuation."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import copy
from dataclasses import replace
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HAS_MODELS = importlib.util.find_spec("torch") is not None
HAS_NATIVE = importlib.util.find_spec("dodge_learning._native") is not None
if HAS_MODELS and HAS_NATIVE:
    import torch

    from dodge_learning.checkpoints import load_teacher_checkpoint
    from dodge_learning.ppo import PPOConfig
    from dodge_learning.seeds import manifest_hash, seed_manifest
    from dodge_learning.teacher import StateActorCritic
    from dodge_learning.teacher_run import _prepare_teacher, main


@unittest.skipUnless(HAS_MODELS and HAS_NATIVE, "requires models and the native bridge")
class TeacherTrainingControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.root = Path(cls.directory.name)
        cls.parent = cls.root / "parent"
        cls.options = [
            "--frames", "8", "--max-seconds", "30", "--rollout-steps", "4",
            "--epochs", "1", "--minibatch-size", "4", "--episode-frames", "4",
            "--embed-dim", "32", "--depth", "1", "--num-heads", "4",
        ]
        with redirect_stdout(io.StringIO()):
            main([
                "train", "--output-dir", str(cls.parent), *cls.options,
                "--gamma", ".995", "--gae-lambda", ".9", "--value-coef", ".2",
                "--entropy-coef", ".03", "--max-grad-norm", ".7", "--torch-threads", "1",
                "--reward-scale", ".02",
            ])

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_cli_records_learning_controls_and_entity_model_dimensions(self):
        configuration = json.loads((self.parent / "config.json").read_text())
        loaded = load_teacher_checkpoint(self.parent / "teacher.pt")
        receipt = json.loads((self.parent / "run.json").read_text())
        for key, expected in (
            ("gamma", .995), ("gae_lambda", .9), ("value_coef", .2),
            ("entropy_coef", .03), ("max_grad_norm", .7), ("torch_threads", 1),
            ("reward_scale", .02),
        ):
            with self.subTest(key=key):
                self.assertEqual(configuration[key], expected)
                self.assertEqual(loaded.metadata["training_config"][key], expected)
        self.assertEqual(configuration["architecture"], "entity_transformer")
        self.assertEqual(configuration["model_config"], loaded.metadata["model_config"])
        self.assertEqual(configuration["model_config"]["embed_dim"], 32)
        self.assertEqual(configuration["model_config"]["depth"], 1)
        self.assertEqual(configuration["model_config"]["num_heads"], 4)
        self.assertIsNone(configuration["warm_start"])
        self.assertEqual(receipt["model_config"], configuration["model_config"])
        self.assertEqual(loaded.metadata["training_config"]["train_seeds"], seed_manifest()["train"])

    def arguments(self, **changes):
        values = {
            "architecture": "entity_transformer", "embed_dim": 32,
            "depth": 1, "num_heads": 4, "warm_start": self.parent / "teacher.pt",
        }
        values.update(changes)
        return argparse.Namespace(**values)

    def test_warm_start_loads_identical_weights_without_importing_parent_optimizer_or_rng(self):
        rng = torch.random.get_rng_state().clone()
        model, model_config, continuation = _prepare_teacher(
            self.arguments(), PPOConfig(total_frames=8, max_episode_frames=4), seed_manifest(),
        )
        parent = load_teacher_checkpoint(self.parent / "teacher.pt")
        for key, value in parent.model.state_dict().items():
            torch.testing.assert_close(value, model.state_dict()[key], rtol=0, atol=0)
        self.assertEqual(model_config, parent.metadata["model_config"])
        self.assertEqual(continuation["parent_checkpoint"]["sha256"], parent.sha256)
        self.assertEqual(continuation["optimizer_state"], "fresh")
        self.assertEqual(continuation["training_seed_order"], "restart_from_first_training_seed")
        self.assertEqual(continuation["sampling_rngs"], "fresh_private_rngs_from_run_seed")
        self.assertFalse(continuation["exact_resume"])
        self.assertFalse(continuation["qualification_transferred"])
        self.assertTrue(torch.equal(rng, torch.random.get_rng_state()))

    def test_continuation_keeps_new_run_counts_and_parent_lineage_in_checkpoint(self):
        output = self.root / "continuation"
        with redirect_stdout(io.StringIO()):
            main([
                "train", "--output-dir", str(output), *self.options,
                "--warm-start", str(self.parent / "teacher.pt"),
            ])
        report = json.loads((output / "run.json").read_text())
        loaded = load_teacher_checkpoint(output / "teacher.pt")
        lineage = report["warm_start"]
        self.assertEqual(report["metrics"]["frames_collected"], 8)
        self.assertEqual(loaded.metadata["metrics"]["frames_collected"], 8)
        self.assertEqual(loaded.metadata["metrics"]["warm_start"], lineage)
        self.assertEqual(lineage["parent_checkpoint"]["frames_collected"], 8)
        self.assertFalse(report["student_collection_allowed"])
        self.assertEqual(report["qualification"], "not_evaluated")
        self.assertEqual(json.loads((output / "config.json").read_text())["warm_start"], lineage)

    def test_warm_start_rejects_changed_source_recipe_config_and_model_before_training(self):
        checkpoint = self.parent / "teacher.pt"
        payload = torch.load(checkpoint, map_location="cpu", weights_only=True)
        cases = []
        changed = copy.deepcopy(payload)
        changed["source_manifest"]["files"]["python/dodge_learning/entity_teacher.py"] = "0" * 64
        cases.append(("source", changed, "fingerprint"))
        for name in ("ppo.py", "checkpoints.py", "teacher_run.py"):
            changed = copy.deepcopy(payload)
            changed["source_manifest"]["files"][f"python/dodge_learning/{name}"] = "0" * 64
            cases.append((f"training-source-{name}", changed, "training source fingerprint"))
        changed = copy.deepcopy(payload)
        changed["source_manifest"] = {"fixture": "missing"}
        cases.append(("missing-source", changed, "fingerprints"))
        changed = copy.deepcopy(payload)
        changed["metrics"]["provenance"]["patterns_enabled"] = False
        cases.append(("native-config", changed, "default benchmark"))
        changed = copy.deepcopy(payload)
        changed["training_config"]["train_seeds"] = changed["training_config"]["train_seeds"][1:]
        cases.append(("seed-order", changed, "seed sequence"))
        changed = copy.deepcopy(payload)
        changed["seed_manifest"]["validation"] = list(range(9000, 9100))
        changed["seed_manifest_hash"] = manifest_hash(changed["seed_manifest"])
        cases.append(("recipe", changed, "frozen seed manifest"))
        for name, changed, error in cases:
            path = self.root / f"bad-{name}.pt"
            torch.save(changed, path)
            output = self.root / f"reject-{name}"
            with self.subTest(name=name), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["train", "--output-dir", str(output), *self.options, "--warm-start", str(path)])
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(ValueError, error):
                _prepare_teacher(self.arguments(warm_start=path), PPOConfig(total_frames=8), seed_manifest())
        with self.assertRaisesRegex(ValueError, "dimensions"):
            _prepare_teacher(self.arguments(embed_dim=64), PPOConfig(total_frames=8), seed_manifest())
        with self.assertRaisesRegex(ValueError, "entity_transformer"):
            _prepare_teacher(self.arguments(architecture="legacy_mlp"), PPOConfig(total_frames=8), seed_manifest())
        loaded = load_teacher_checkpoint(checkpoint)
        with torch.random.fork_rng(devices=[]):
            loaded = replace(loaded, model=StateActorCritic())
        with mock.patch("dodge_learning.checkpoints.load_teacher_checkpoint", return_value=loaded):
            with self.assertRaisesRegex(ValueError, "entity-transformer checkpoint"):
                _prepare_teacher(self.arguments(), PPOConfig(total_frames=8), seed_manifest())

    def test_onset_checkpoint_requires_both_collection_and_shared_training_source(self):
        payload = torch.load(self.parent / "teacher.pt", map_location="cpu", weights_only=True)
        payload["metrics"]["method"] = "teacher_onset_ablation_supervised"
        path = self.root / "onset-source-parent.pt"
        torch.save(payload, path)
        _, _, lineage = _prepare_teacher(
            self.arguments(warm_start=path), PPOConfig(total_frames=8), seed_manifest(),
        )
        for name in ("teacher_onset_ablation.py", "teacher_representation_ablation.py"):
            key = f"python/dodge_learning/{name}"
            self.assertEqual(lineage["training_source_identity"][key], payload["source_manifest"]["files"][key])
            for change in ("missing", "changed"):
                altered = copy.deepcopy(payload)
                if change == "missing":
                    del altered["source_manifest"]["files"][key]
                else:
                    altered["source_manifest"]["files"][key] = "0" * 64
                rejected = self.root / f"onset-source-{name}-{change}.pt"
                torch.save(altered, rejected)
                with self.subTest(name=name, change=change), self.assertRaisesRegex(ValueError, "training source fingerprint"):
                    _prepare_teacher(self.arguments(warm_start=rejected), PPOConfig(total_frames=8), seed_manifest())

    def test_fit_budget_checkpoint_requires_experiment_label_and_shared_sources(self):
        payload = torch.load(self.parent / "teacher.pt", map_location="cpu", weights_only=True)
        payload["metrics"]["method"] = "teacher_fit_budget_supervised"
        path = self.root / "fit-budget-source-parent.pt"
        torch.save(payload, path)
        _, _, lineage = _prepare_teacher(
            self.arguments(warm_start=path), PPOConfig(total_frames=8), seed_manifest(),
        )
        for name in (
            "teacher_fit_budget.py", "teacher_onset_ablation.py",
            "teacher_representation_ablation.py", "policies.py", "seeds.py",
        ):
            key = f"python/dodge_learning/{name}"
            self.assertEqual(lineage["training_source_identity"][key], payload["source_manifest"]["files"][key])
            for change in ("missing", "changed"):
                altered = copy.deepcopy(payload)
                if change == "missing":
                    del altered["source_manifest"]["files"][key]
                else:
                    altered["source_manifest"]["files"][key] = "0" * 64
                rejected = self.root / f"fit-budget-source-{name}-{change}.pt"
                torch.save(altered, rejected)
                with self.subTest(name=name, change=change), self.assertRaisesRegex(ValueError, "training source fingerprint"):
                    _prepare_teacher(self.arguments(warm_start=rejected), PPOConfig(total_frames=8), seed_manifest())


if __name__ == "__main__":
    unittest.main()
