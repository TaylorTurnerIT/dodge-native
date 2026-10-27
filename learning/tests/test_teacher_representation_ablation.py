"""Fixed teacher-data splits, label timing, paired optimization, and limits."""

from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HAS_MODELS = importlib.util.find_spec("torch") is not None and importlib.util.find_spec("numpy") is not None
if HAS_MODELS:
    import numpy as np
    import torch

    from dodge_learning.checkpoints import load_teacher_checkpoint
    from dodge_learning.entity_teacher import EntityActorCritic, EntityTeacherConfig
    from dodge_learning.teacher_representation_ablation import (
        ARMS, AblationConfig, _enemy_counterfactual, collect_dataset, run_ablation,
    )


class FakeController:
    def act(self, observation):
        return int(observation["privileged_state"]["entities"][0]["features"][0] * 128) % 9


class FakeEnvironment:
    instances = []

    def __init__(self, *, seed, max_episode_frames, action_repeat, discount):
        if action_repeat != 1 or discount != .99:
            raise AssertionError("collection protocol changed")
        self.cap = max_episode_frames
        self.seed = seed
        self.frames = 0
        self.resets = []
        self.actions = []
        self.closed = False
        self.instances.append(self)

    def observation(self):
        player = [float(self.frames) / 128, .5, 0., 0., .5] + [0.] * 27
        enemy = [.75, .5, -.25, 0., .5, .5, 0.] + [0.] * 25
        return {
            "privileged_state": {
                "schema_version": 1, "globals": [0.] * 64,
                "entities": [
                    {"features": player, "kind": 0, "bounds": [0., 64., 4., 68.], "spatial": False},
                    {"features": enemy, "kind": 1, "bounds": [96., 64., 101., 70.], "spatial": True},
                    {"features": [0.] * 32, "kind": 5, "bounds": [0.] * 4, "spatial": False},
                ],
                "capture_bounds": [0., 0., 128., 128.],
            },
            "reward_sum": float(self.frames > 0),
            "info": {
                "frame": 13 + self.frames, "episode_frames": self.frames,
                "elapsed_native_frames": int(self.frames > 0),
                "terminated": False, "truncated": self.frames >= self.cap,
                "provenance": {"feature_schema_version": 2, "privileged_schema_version": 1, "action_repeat": 1},
            },
        }

    def reset(self, seed):
        self.seed = seed
        self.frames = 0
        self.resets.append(seed)
        return self.observation()

    def step(self, action):
        if self.frames >= self.cap:
            raise AssertionError("collection stepped a finished episode")
        if action != self.frames % 9:
            raise AssertionError("heuristic label was not paired before the action")
        self.actions.append(action)
        self.frames += 1
        return self.observation()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True


@unittest.skipUnless(HAS_MODELS, "install optional model dependencies")
class FixedDataCollectionTests(unittest.TestCase):
    def setUp(self):
        FakeEnvironment.instances = []

    def config(self, **changes):
        return replace(AblationConfig(episode_frames=3, train_stride=2, smoke_stride=2, epochs=1,
                                     batch_size=64, max_seconds=30, arm_seconds=10,
                                     counterfactual_samples=2), **changes)

    def collect(self, split="train", config=None, factory=FakeEnvironment, **kwargs):
        with mock.patch("dodge_learning.teacher_representation_ablation.AvoidancePolicy", FakeController):
            return collect_dataset(config or self.config(), split, environment_factory=factory, **kwargs)

    def test_frozen_splits_strides_and_pre_action_labels_are_reproducible(self):
        first = self.collect()
        second = self.collect()
        smoke = self.collect("smoke")
        self.assertEqual(first.receipt["seed_sequence"], list(range(1000, 1100)))
        self.assertEqual(smoke.receipt["seed_sequence"], list(range(2000, 2010)))
        self.assertEqual((first.receipt["native_frames"], first.receipt["heuristic_queries"]), (300, 300))
        self.assertEqual(len(first.states), 200)
        self.assertEqual(len(smoke.states), 20)
        self.assertEqual(first.sample_ids[:4], ((1000, 0), (1000, 2), (1001, 0), (1001, 2)))
        self.assertEqual(first.labels[:4].tolist(), [0, 2, 0, 2])
        self.assertEqual(first.receipt["state_identity_sha256"], second.receipt["state_identity_sha256"])
        self.assertNotEqual(first.receipt["state_identity_sha256"], smoke.receipt["state_identity_sha256"])
        self.assertTrue(first.receipt["complete"])
        self.assertTrue(FakeEnvironment.instances[0].closed)
        self.assertEqual(FakeEnvironment.instances[0].actions[:6], [0, 1, 2, 0, 1, 2])
        self.assertTrue(all(state.features.shape[0] == 3 for state in first.states))
        with self.assertRaises(ValueError):
            first.labels.setflags(write=True)

    def test_deadline_and_memory_failures_close_the_environment(self):
        now = [0.]

        class Timed(FakeEnvironment):
            def step(self, action):
                result = super().step(action)
                now[0] += 1.
                return result

        result = self.collect(factory=Timed, clock=lambda: now[0], deadline=2.)
        self.assertEqual(result.receipt["native_frames"], 2)
        self.assertEqual(result.receipt["samples"], 1)
        self.assertIs(result.receipt["complete"], False)
        self.assertEqual(result.receipt["stop_reason"], "time_budget")
        self.assertTrue(FakeEnvironment.instances[-1].closed)
        with self.assertRaisesRegex(MemoryError, "memory budget"):
            self.collect(config=self.config(dataset_max_bytes=128))
        self.assertTrue(FakeEnvironment.instances[-1].closed)

    def test_config_rejects_changed_splits_and_unbounded_experiments(self):
        for changes in (
            {"train_seeds": (1000, 2000)}, {"smoke_seeds": (3000,)},
            {"epochs": 0}, {"max_seconds": 1201}, {"arm_seconds": 301},
            {"episode_frames": 501}, {"dataset_max_bytes": 2 * 1024 ** 3 + 1},
            {"torch_threads": 2}, {"train_stride": True}, {"learning_rate": float("nan")},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.config(**changes)
        with self.assertRaises(ValueError):
            self.collect("validation")

    def test_native_schema_and_cadence_changes_reject_collection(self):
        class WrongSchema(FakeEnvironment):
            def step(self, action):
                result = super().step(action)
                result["info"]["provenance"]["privileged_schema_version"] = 2
                return result

        class SkipsFrames(FakeEnvironment):
            def step(self, action):
                result = super().step(action)
                result["info"]["elapsed_native_frames"] = 2
                return result

        for factory in (WrongSchema, SkipsFrames):
            with self.subTest(factory=factory), self.assertRaises(RuntimeError):
                self.collect(factory=factory)
            self.assertTrue(FakeEnvironment.instances[-1].closed)

    def test_counterfactual_changes_only_enemy_kinematics_and_bounds(self):
        dataset = self.collect("smoke")
        original = dataset.states[0]
        changed = _enemy_counterfactual(original)
        np.testing.assert_array_equal(original.features[0], changed.features[0])
        np.testing.assert_array_equal(original.features[2], changed.features[2])
        np.testing.assert_array_equal(original.globals, changed.globals)
        np.testing.assert_array_equal(original.kinds, changed.kinds)
        np.testing.assert_array_equal(original.spatial, changed.spatial)
        np.testing.assert_array_equal(original.features[1, 4:], changed.features[1, 4:])
        self.assertAlmostEqual(float(changed.features[1, 0] - changed.features[0, 0]), 8 / 128)
        self.assertEqual(float(changed.features[1, 2]), -.5)
        self.assertFalse(np.array_equal(original.bounds[1], changed.bounds[1]))


@unittest.skipUnless(HAS_MODELS, "install optional model dependencies")
class PairedAblationTests(unittest.TestCase):
    def test_all_arms_fit_same_training_rows_and_never_optimize_smoke_rows(self):
        import dodge_learning.teacher_representation_ablation as module

        if "attention_prior" not in EntityTeacherConfig.__dataclass_fields__:
            self.skipTest("representation model flags are being integrated")
        config = AblationConfig(episode_frames=3, train_stride=2, smoke_stride=2,
                               epochs=1, batch_size=64, max_seconds=30, arm_seconds=10,
                               counterfactual_samples=2)
        batches = []
        original_logits = module._logits

        def record_logits(model, states):
            if torch.is_grad_enabled():
                # Smoke records use a distinct global marker injected below.
                self.assertTrue(all(float(state.globals[0]) == 0 for state in states))
                batches.append(tuple((float(state.features[0, 0]), state.features.shape[0]) for state in states))
            return original_logits(model, states)

        class MarkedEnvironment(FakeEnvironment):
            def observation(self):
                value = super().observation()
                value["privileged_state"]["globals"][0] = float(self.seed >= 2000)
                return value

        def factory(model_config):
            return EntityActorCritic(replace(model_config, embed_dim=16, depth=1))

        before_rng = torch.random.get_rng_state().clone()
        before_threads = torch.get_num_threads()
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(module, "AvoidancePolicy", FakeController),
            mock.patch.object(module, "_logits", side_effect=record_logits),
        ):
            path = Path(directory) / "run"
            report = run_ablation(config, path, environment_factory=MarkedEnvironment,
                                 model_factory=factory, source_manifest_factory=lambda: {"fixture": "source"})
            self.assertEqual(len(report["arms"]), 4)
            self.assertTrue(report["matched_training_budget"])
            self.assertTrue(report["matched_parameter_counts"])
            self.assertTrue(report["fixed_training_identity_for_all_arms"])
            self.assertTrue(report["fixed_held_out_identity_for_all_arms"])
            self.assertIs(report["teacher_qualified"], False)
            self.assertEqual(report["dataset_storage"], "memory_only_no_images")
            self.assertLessEqual(report["estimated_dataset_memory_bytes"], config.dataset_max_bytes)
            self.assertEqual(len(batches), 16)
            for offset in (4, 8, 12):
                self.assertEqual(batches[:4], batches[offset:offset + 4])
            for arm, (name, flags) in zip(report["arms"], ARMS):
                self.assertEqual(arm["name"], name)
                loaded = load_teacher_checkpoint(path / f"{name}.pt")
                self.assertEqual(loaded.metadata["metrics"]["method"], "representation_ablation_supervised")
                self.assertEqual(loaded.metadata["training_config"]["train_seeds"], list(range(1000, 1100)))
                for key, expected in flags.items():
                    self.assertEqual(getattr(loaded.model.config, key), expected)
                self.assertEqual(arm["metrics"]["optimizer_steps"], 4)
                self.assertEqual(arm["metrics"]["samples_optimized"], 200)
                self.assertIs(arm["metrics"]["evaluation"]["teacher_qualified"], False)
                self.assertEqual(arm["metrics"]["evaluation"]["enemy_counterfactual"]["samples"], 2)
            json.loads((path / "run.json").read_text())
            with self.assertRaises(FileExistsError):
                run_ablation(config, path, environment_factory=MarkedEnvironment)
        self.assertEqual(torch.get_num_threads(), before_threads)
        self.assertTrue(torch.equal(torch.random.get_rng_state(), before_rng))


if __name__ == "__main__":
    unittest.main()
