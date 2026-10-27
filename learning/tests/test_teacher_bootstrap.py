"""Teacher warmup budgets, current-state labels, RNG ownership, and checkpoint tags."""

from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest import mock

HAS_MODELS = importlib.util.find_spec("torch") is not None and importlib.util.find_spec("numpy") is not None
HAS_NATIVE = importlib.util.find_spec("dodge_learning._native") is not None
if HAS_MODELS:
    import numpy as np
    import torch

    from dodge_learning.entity_teacher import EntityActorCritic, EntityTeacherConfig
    from dodge_learning.teacher_bootstrap import BootstrapConfig, _class_weights, train_bootstrap


class FakeEnvironment:
    instances = []

    def __init__(self, *, seed, max_episode_frames, action_repeat, discount):
        if action_repeat != 1 or discount != .99:
            raise AssertionError("bootstrap must use its declared native cadence")
        self.seed = seed
        self.limit = max_episode_frames
        self.frames = 0
        self.resets = []
        self.actions = []
        self.closed = False
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def reset(self, *, seed):
        self.seed = seed
        self.frames = 0
        self.resets.append(seed)
        return self.observation()

    def observation(self):
        terminated = self.seed == 1001 and self.frames == 2
        truncated = not terminated and self.frames >= self.limit
        return {
            "privileged_state": {
                "schema_version": 1, "globals": [0.] * 64,
                "entities": [{"features": [self.frames / 128.] + [0.] * 31,
                              "kind": 0, "bounds": [64., 64., 68., 68.], "spatial": False}],
                "capture_bounds": [0., 0., 128., 128.],
            },
            "train_only_state": {"frame_for_label": self.frames},
            "reward_sum": 0. if terminated else 1.,
            "info": {
                "frame": 13 + self.frames, "episode_frames": self.frames,
                "elapsed_native_frames": int(self.frames > 0),
                "terminated": terminated, "truncated": truncated,
                "pattern_completions": int(self.frames >= 2),
                "pattern_metrics": [{"id": 1, "encounters": int(self.frames >= 1),
                                     "exposure_frames": self.frames, "completions": int(self.frames >= 2)}],
                "provenance": {"feature_schema_version": 2, "privileged_schema_version": 1},
            },
        }

    def step(self, action):
        previous = self.observation()["info"]
        if previous["terminated"] or previous["truncated"]:
            raise AssertionError("stepped a finished episode")
        if action != self.frames % 9:
            raise AssertionError("label/action did not belong to the pre-step state")
        self.actions.append(action)
        self.frames += 1
        return self.observation()


class FakeHeuristic:
    def act(self, observation):
        return observation["train_only_state"]["frame_for_label"] % 9


@unittest.skipUnless(HAS_MODELS, "install the optional models extra")
class TeacherBootstrapTests(unittest.TestCase):
    def setUp(self):
        FakeEnvironment.instances = []

    def config(self, **changes):
        return replace(BootstrapConfig(total_frames=7, batch_size=4, epochs=2,
                                       max_episode_frames=3, max_seconds=30), **changes)

    def model(self):
        with torch.random.fork_rng(devices=[]):
            torch.random.default_generator.manual_seed(17)
            return EntityActorCritic(EntityTeacherConfig(embed_dim=32, depth=1))

    def train(self, config=None, model=None, **kwargs):
        with mock.patch("dodge_learning.teacher_bootstrap.AvoidancePolicy", FakeHeuristic):
            return train_bootstrap(config or self.config(), model=model or self.model(),
                                   environment_factory=FakeEnvironment, **kwargs)

    def test_bounds_and_complete_training_seed_sequence(self):
        for changes in (
            {"total_frames": 0}, {"total_frames": 10001}, {"total_frames": True},
            {"max_seconds": 601}, {"max_seconds": float("nan")},
            {"max_seconds": 10 ** 1000}, {"max_episode_frames": 1001},
            {"batch_size": 0}, {"epochs": 9}, {"learning_rate": 0},
            {"replay_capacity": 0}, {"replay_capacity": 4097},
            {"replay_capacity": True}, {"replay_capacity": 3},
            {"class_balance": "inverse"}, {"class_balance": True},
            {"torch_threads": 2}, {"train_seeds": (1000, 2000)},
            {"train_seeds": (1000,)}, {"train_seeds": tuple(range(2000, 2100))},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.config(**changes)

    def test_exact_budgets_current_frame_labels_final_batch_and_value_head(self):
        model = self.model()
        initial = {key: value.clone() for key, value in model.state_dict().items()}
        progress = []
        result = self.train(model=model, progress_callback=progress.append)
        metrics = result.metrics
        for key, expected in (
            ("frames_collected", 7), ("updates", 2), ("optimizer_steps", 4),
            ("samples_optimized", 14), ("unique_samples_optimized", 7),
            ("replay_samples_optimized", 7), ("replay_rows", 7),
            ("unoptimized_frames", 0), ("episodes_started", 3), ("episodes_completed", 2),
            ("terminal_episodes", 1), ("truncated_episodes", 1),
            ("completed_pattern_episodes", 2), ("pattern_completions", 2),
            ("partial_episode_frames", 2),
        ):
            with self.subTest(key=key):
                self.assertEqual(metrics[key], expected)
        self.assertEqual(metrics["method"], "heuristic_bootstrap")
        self.assertEqual(metrics["class_balance"], "none")
        self.assertEqual(metrics["class_weights"], [1.] * 9)
        self.assertIs(metrics["teacher_qualified"], False)
        self.assertEqual(FakeEnvironment.instances[0].resets, [1000, 1001, 1002])
        self.assertEqual(FakeEnvironment.instances[0].actions, [0, 1, 2, 0, 1, 0, 1])
        self.assertTrue(FakeEnvironment.instances[0].closed)
        self.assertEqual(metrics["action_histogram"]["neutral"], 3)
        self.assertEqual(metrics["action_histogram"]["left"], 3)
        self.assertEqual(metrics["action_histogram"]["right"], 1)
        self.assertEqual(sum(metrics["action_histogram"].values()), 7)
        self.assertEqual([row["frames_collected"] for row in progress], [4, 7])
        for name in ("value.weight", "value.bias"):
            torch.testing.assert_close(model.state_dict()[name], initial[name], rtol=0, atol=0)
        self.assertTrue(all(parameter.requires_grad for parameter in model.value.parameters()))
        self.assertFalse(model.training)
        self.assertTrue(any(not torch.equal(value, initial[key]) for key, value in model.state_dict().items()))
        self.assertGreater(float(model.blocks[0].attention.in_proj_weight.grad.abs().sum()), 0)
        json.dumps(metrics, allow_nan=False)

    def test_later_epochs_revisit_earlier_batches_with_bounded_replay(self):
        from dodge_learning.entity_teacher import batch_entities

        batches = []

        def record(states, *args, **kwargs):
            batches.append([round(float(state.features[0, 0]) * 128) for state in states])
            return batch_entities(states, *args, **kwargs)

        with mock.patch("dodge_learning.teacher_bootstrap.batch_entities", side_effect=record):
            result = self.train(self.config(total_frames=6, max_episode_frames=10,
                                           batch_size=2, replay_capacity=4, epochs=2))
        self.assertEqual(len(batches), 6)
        self.assertEqual([sorted(batches[index]) for index in (0, 2, 4)], [[0, 1], [2, 3], [4, 5]])
        self.assertTrue(any(value < 2 for value in batches[3]), batches)
        self.assertTrue(all(2 <= value <= 5 for value in batches[5]), batches)
        self.assertEqual(result.metrics["replay_capacity"], 4)
        self.assertEqual(result.metrics["replay_rows"], 4)
        self.assertEqual(result.metrics["replay_samples_optimized"], 6)
        self.assertEqual(result.metrics["samples_optimized"], 12)
        self.assertEqual(result.metrics["unique_samples_optimized"], 6)
        self.assertEqual(result.metrics["unoptimized_frames"], 0)

    def test_capped_class_weights_preserve_absent_actions_and_strengthen_rare_labels(self):
        from torch.nn import functional as functional

        counts = np.array([10000, 100, 1, 0, 0, 0, 0, 0, 0], dtype=np.int64)
        weights = _class_weights(counts, "sqrt_inverse_frequency")
        torch.testing.assert_close(weights, torch.tensor([1., 4., 4., 1., 1., 1., 1., 1., 1.]))
        self.assertIsNone(_class_weights(counts, "none"))
        torch.testing.assert_close(_class_weights(np.zeros(9, dtype=np.int64), "sqrt_inverse_frequency"), torch.ones(9))
        targets = torch.tensor([0] * 9 + [1])
        plain_logits = torch.zeros(9, requires_grad=True)
        weighted_logits = torch.zeros(9, requires_grad=True)
        functional.cross_entropy(plain_logits.expand(10, 9), targets).backward()
        functional.cross_entropy(weighted_logits.expand(10, 9), targets,
                                 weight=_class_weights(np.array([9, 1, 0, 0, 0, 0, 0, 0, 0]), "sqrt_inverse_frequency")).backward()
        self.assertGreater(float(plain_logits.grad[1]), 0)
        self.assertLess(float(weighted_logits.grad[1]), 0)

    def test_training_uses_current_replay_class_counts_including_eviction(self):
        original_ce = torch.nn.functional.cross_entropy
        seen = []

        def record(logits, targets, **kwargs):
            seen.append(kwargs["weight"].clone())
            return original_ce(logits, targets, **kwargs)

        with mock.patch("dodge_learning.teacher_bootstrap.F.cross_entropy", side_effect=record):
            result = self.train(self.config(total_frames=7, batch_size=4, replay_capacity=4,
                                           epochs=1, class_balance="sqrt_inverse_frequency"))
        # First four labels are [0,1,2,0]; the final replay contains [0,1,0,1].
        torch.testing.assert_close(seen[0][:3], torch.tensor([1., 2. ** .5, 2. ** .5]))
        torch.testing.assert_close(seen[1], torch.ones(9))
        self.assertEqual(result.metrics["class_balance"], "sqrt_inverse_frequency")
        self.assertEqual(result.metrics["class_weight_cap"], 4.)
        self.assertEqual(result.metrics["class_weights"], [1.] * 9)

    def test_private_rngs_and_threads_are_restored_with_nonzero_dropout(self):
        first_model = self.model()
        # Exercise the full RNG fork with stochastic transformer operations.
        for module in first_model.modules():
            if isinstance(module, torch.nn.Dropout):
                module.p = .2
        torch_state = torch.random.get_rng_state().clone()
        numpy_state = np.random.get_state()
        python_state = random.getstate()
        threads = torch.get_num_threads()
        self.train(model=first_model)
        torch.testing.assert_close(torch.random.get_rng_state(), torch_state)
        current_numpy = np.random.get_state()
        self.assertEqual(numpy_state[0], current_numpy[0])
        np.testing.assert_array_equal(numpy_state[1], current_numpy[1])
        self.assertEqual(numpy_state[2:], current_numpy[2:])
        self.assertEqual(random.getstate(), python_state)
        self.assertEqual(torch.get_num_threads(), threads)

    def test_schema_failures_close_native_environment_and_restore_value_trainability(self):
        class WrongSchema(FakeEnvironment):
            def observation(self):
                result = super().observation()
                result["info"]["provenance"]["privileged_schema_version"] = 0
                return result

        model = self.model()
        threads = torch.get_num_threads()
        with self.assertRaisesRegex(RuntimeError, "privileged_schema_version"):
            train_bootstrap(self.config(), model=model, environment_factory=WrongSchema)
        self.assertTrue(FakeEnvironment.instances[-1].closed)
        self.assertTrue(all(parameter.requires_grad for parameter in model.value.parameters()))
        self.assertEqual(torch.get_num_threads(), threads)

    def test_time_budget_during_collection_reports_unoptimized_raw_frames(self):
        now = [0.]

        class TimedEnvironment(FakeEnvironment):
            def step(self, action):
                result = super().step(action)
                now[0] += 1.
                return result

        with (
            mock.patch("dodge_learning.teacher_bootstrap.time.monotonic", side_effect=lambda: now[0]),
            mock.patch("dodge_learning.teacher_bootstrap.AvoidancePolicy", FakeHeuristic),
        ):
            result = train_bootstrap(self.config(max_seconds=2), model=self.model(), environment_factory=TimedEnvironment)
        self.assertEqual(result.metrics["frames_collected"], 2)
        self.assertEqual(result.metrics["unique_samples_optimized"], 0)
        self.assertEqual(result.metrics["unoptimized_frames"], 2)
        self.assertEqual(result.metrics["stop_reason"], "time_budget")

    @unittest.skipUnless(HAS_NATIVE, "build the optional native bridge")
    def test_tiny_native_checkpoint_remains_tagged_bootstrap_and_has_only_training_seeds(self):
        from dodge_learning.checkpoints import load_teacher_checkpoint, save_teacher_checkpoint
        from dodge_learning.seeds import seed_manifest
        from dodge_learning.teacher_run import source_manifest

        result = train_bootstrap(self.config(total_frames=4, max_episode_frames=2, batch_size=3, epochs=1), model=self.model())
        self.assertEqual(result.metrics["frames_collected"], 4)
        self.assertEqual(result.metrics["unique_samples_optimized"], 4)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "teacher.pt"
            receipt = save_teacher_checkpoint(path, result, seed_manifest=seed_manifest(), source_manifest=source_manifest())
            loaded = load_teacher_checkpoint(path)
        self.assertEqual(receipt["format_version"], 2)
        self.assertEqual(receipt["kind"], "dodge_entity_transformer_teacher")
        self.assertEqual(loaded.metadata["metrics"]["method"], "heuristic_bootstrap")
        self.assertIs(loaded.metadata["metrics"]["teacher_qualified"], False)
        self.assertEqual(loaded.metadata["training_config"]["train_seeds"], seed_manifest()["train"])
        self.assertTrue(all(1000 <= row["seed"] <= 1099 for row in result.metrics["episodes"]))


if __name__ == "__main__":
    unittest.main()
