"""Label timing, fixed split ownership, matched fitting, and explicit limits."""

from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

HAS_MODELS = importlib.util.find_spec("torch") is not None and importlib.util.find_spec("numpy") is not None
if HAS_MODELS:
    import numpy as np
    import torch
    from dodge_learning.entity_teacher import EntityActorCritic, EntityTeacherConfig
    from dodge_learning.teacher_representation_ablation import AblationConfig, AblationTimeout, collect_dataset
    import dodge_learning.teacher_onset_ablation as onset


class FakeOracle:
    def act(self, observation):
        # Every retained base frame has label zero. Its preceding frame can
        # have label one, so previous-retained-label tagging would be wrong.
        return int(observation["info"]["episode_frames"] % 10 == 9)


class FakeNeutral:
    def act(self, observation):
        return 0


class FakeEnvironment:
    instances = []

    def __init__(self, *, seed, max_episode_frames, action_repeat, discount):
        if action_repeat != 1 or discount != .99:
            raise AssertionError("native collection protocol changed")
        self.cap, self.seed, self.frames = max_episode_frames, seed, 0
        self.actions, self.resets = [], []
        self.closed = False
        self.instances.append(self)

    def observation(self):
        features = [self.frames / 128, .5, 0., 0., .5] + [0.] * 27
        return {
            "privileged_state": {
                "schema_version": 1, "globals": [0.] * 64,
                "entities": [{"features": features, "kind": 0, "bounds": [0., 0., 4., 4.], "spatial": False}],
                "capture_bounds": [0., 0., 128., 128.],
            },
            "train_only_state": {"player": {"vx": 0., "vy": 0.}},
            "reward_sum": float(self.frames > 0),
            "info": {"episode_frames": self.frames, "elapsed_native_frames": int(self.frames > 0),
                     "terminated": False, "truncated": self.frames >= self.cap,
                     "provenance": {"feature_schema_version": 2, "privileged_schema_version": 1, "action_repeat": 1}},
        }

    def reset(self, seed):
        self.frames, self.seed = 0, seed
        self.resets.append(seed)
        return self.observation()

    def step(self, action):
        if self.frames >= self.cap:
            raise AssertionError("stepped finished episode")
        self.actions.append(action)
        self.frames += 1
        return self.observation()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True


@unittest.skipUnless(HAS_MODELS, "install optional model dependencies")
class OnsetCollectionTests(unittest.TestCase):
    def setUp(self):
        FakeEnvironment.instances = []

    def config(self, **changes):
        return replace(onset.OnsetConfig(episode_frames=46, extra_per_seed=3, epochs=1, max_seconds=30, arm_seconds=10), **changes)

    def collect(self, mode="oracle_train", config=None, **kwargs):
        with mock.patch.object(onset, "AvoidancePolicy", FakeOracle):
            return onset.collect_tagged(config or self.config(), mode, environment_factory=kwargs.pop("environment_factory", FakeEnvironment),
                                        deadline=kwargs.pop("deadline", 100.), clock=kwargs.pop("clock", lambda: 0.), **kwargs)

    def test_original_dataset_hash_matches_prior_collection_exactly(self):
        base, extra = self.collect()
        with mock.patch("dodge_learning.teacher_representation_ablation.AvoidancePolicy", FakeOracle):
            original = collect_dataset(AblationConfig(episode_frames=46), "train", environment_factory=FakeEnvironment, clock=lambda: 0.)
        self.assertEqual(base.data.receipt["state_identity_sha256"], original.receipt["state_identity_sha256"])
        self.assertEqual(base.data.sample_ids, original.sample_ids)
        self.assertEqual(base.data.labels.tolist(), original.labels.tolist())
        self.assertEqual(extra.data.sample_ids[:3], ((1000, 5), (1000, 25), (1000, 45)))
        self.assertEqual(len(base.data.states), 500)
        self.assertEqual(len(extra.data.states), 300)
        self.assertEqual(base.data.receipt["heuristic_queries"], 4600)

    def test_onset_uses_immediately_previous_native_frame(self):
        base, _ = self.collect()
        self.assertFalse(base.tags[0]["label_changed_vs_previous_frame"])
        self.assertEqual(base.tags[0]["previous_oracle_label"], None)
        self.assertEqual(base.data.sample_ids[1], (1000, 10))
        self.assertEqual(int(base.data.labels[1]), 0)
        self.assertTrue(base.tags[1]["label_changed_vs_previous_frame"])
        self.assertEqual(base.tags[1]["previous_oracle_label"], 1)
        self.assertTrue(FakeEnvironment.instances[0].closed)
        self.assertEqual(FakeEnvironment.instances[0].actions[9], 1)

    def test_learned_actions_execute_while_oracle_only_labels(self):
        learned, extra = self.collect("learned_train", learned_policy=FakeNeutral())
        self.assertIsNone(extra)
        self.assertEqual(learned.data.sample_ids[:3], ((1000, 5), (1000, 25), (1000, 45)))
        self.assertEqual(len(set(learned.data.sample_ids)), 300)
        self.assertTrue(all(action == 0 for action in FakeEnvironment.instances[0].actions))
        self.assertEqual(learned.data.receipt["episodes"][0]["candidate_count"], 9)
        again, _ = self.collect("learned_train", learned_policy=FakeNeutral())
        self.assertEqual(learned.data.receipt["state_identity_sha256"], again.data.receipt["state_identity_sha256"])

    def test_smoke_split_and_no_leakage_guard(self):
        smoke, extra = self.collect("oracle_smoke")
        base, _ = self.collect()
        self.assertIsNone(extra)
        self.assertEqual(smoke.data.receipt["seed_sequence"], list(range(2000, 2010)))
        self.assertEqual(smoke.data.sample_ids[1], (2000, 5))
        with self.assertRaisesRegex(ValueError, "never enter optimization"):
            onset.combine_datasets(base, smoke, "invalid")
        with self.assertRaises(ValueError):
            self.collect("validation")

    def test_exact_and_near_rest_thresholds_use_raw_velocities(self):
        observation = {"train_only_state": {"player": {"vx": .02, "vy": -.049}}}
        tags = onset._tags(observation, 1, 0)
        self.assertFalse(tags["nonneutral_from_rest"])
        self.assertTrue(tags["nonneutral_from_near_rest"])
        self.assertTrue(tags["nonneutral_onset"])
        observation["train_only_state"]["player"]["vx"] = .05
        self.assertFalse(onset._tags(observation, 1, 0)["near_rest"])

    def test_short_episode_fails_instead_of_padding_candidates(self):
        with self.assertRaisesRegex(ValueError, "not enough unique"):
            self.collect("learned_train", config=self.config(episode_frames=11), learned_policy=FakeNeutral())
        self.assertTrue(FakeEnvironment.instances[-1].closed)

    def test_deadline_and_memory_fail_close_environment(self):
        now = [0.]

        class Timed(FakeEnvironment):
            def step(self, action):
                result = super().step(action)
                now[0] += 1
                return result

        with self.assertRaises(AblationTimeout):
            self.collect(environment_factory=Timed, deadline=2., clock=lambda: now[0])
        self.assertTrue(FakeEnvironment.instances[-1].closed)
        with self.assertRaisesRegex(MemoryError, "memory budget"):
            self.collect(config=self.config(dataset_max_bytes=128))
        self.assertTrue(FakeEnvironment.instances[-1].closed)

    def test_cadence_or_schema_change_rejects_collection(self):
        class WrongCadence(FakeEnvironment):
            def step(self, action):
                row = super().step(action)
                row["info"]["elapsed_native_frames"] = 2
                return row
        with self.assertRaisesRegex(RuntimeError, "one native frame"):
            self.collect(environment_factory=WrongCadence)
        self.assertTrue(FakeEnvironment.instances[-1].closed)

    def test_quantile_selection_keeps_endpoints_and_unique_rows(self):
        self.assertEqual(onset.evenly_spaced_indices(40, 25)[0], 0)
        self.assertEqual(onset.evenly_spaced_indices(40, 25)[-1], 39)
        self.assertEqual(len(set(onset.evenly_spaced_indices(40, 25))), 25)
        self.assertEqual(onset.evenly_spaced_indices(3, 3), (0, 1, 2))
        for values in ((2, 3), (0, 0), (True, 1)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                onset.evenly_spaced_indices(*values)

    def test_config_rejects_changed_splits_or_unbounded_budgets(self):
        for change in ({"train_seeds": (1000,)}, {"smoke_seeds": (3000,)}, {"max_seconds": 1201},
                       {"arm_seconds": 301}, {"dataset_max_bytes": 2 * 1024 ** 3 + 1}, {"torch_threads": 2},
                       {"epochs": True}, {"learning_rate": float("nan")}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.config(**change)

    def test_greedy_survival_excludes_terminal_death_frame(self):
        class Death(FakeEnvironment):
            def observation(self):
                row = super().observation()
                if self.frames >= 3:
                    row["info"]["terminated"] = True
                    row["info"]["truncated"] = False
                    row["reward_sum"] = 0.
                return row

        with mock.patch.object(onset, "AvoidancePolicy", FakeOracle), mock.patch("dodge_learning.teacher_eval._match_provenance"):
            report = onset.greedy_smoke(self.config(gameplay_frames=10), lambda seed: FakeNeutral(), provenance={},
                                        deadline=100., clock=lambda: 0., environment_factory=Death)
        self.assertEqual(report["mean_survival_frames"], 2.)
        self.assertEqual(report["native_frames"], 30)
        self.assertEqual(report["episodes"][0]["executed_native_frames"], 3)
        self.assertEqual(report["episodes"][0]["frames_survived"], 2)


@unittest.skipUnless(HAS_MODELS, "install optional model dependencies")
class OnsetFittingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)

    @classmethod
    def tearDownClass(cls):
        torch.set_num_threads(cls.previous_threads)

    def dataset(self, split="train", labels=(0, 1, 2, 3, 4, 5, 6, 7)):
        from dodge_learning.entity_teacher import encode_entities
        environment = FakeEnvironment(seed=1000, max_episode_frames=500, action_repeat=1, discount=.99)
        rows = []
        for index, label in enumerate(labels):
            environment.frames = index
            observation = environment.observation()
            rows.append((encode_entities(observation["privileged_state"]), label, (1000, index), onset._tags(observation, label, 0)))
        return onset._dataset(rows, {"split": split, "complete": True, "collection_mode": "oracle_train", "native_frames": 8,
                                     "provenance": {"feature_schema_version": 2, "privileged_schema_version": 1, "action_repeat": 1}})

    def model_factory(self, config):
        return EntityActorCritic(replace(config, embed_dim=8, num_heads=1, depth=1))

    def test_fit_pairs_initialization_order_and_budget(self):
        config = onset.OnsetConfig(epochs=2, batch_size=4)
        first = onset.fit_arm(config, "a", self.dataset(), deadline=100, clock=lambda: 0., model_factory=self.model_factory)
        second = onset.fit_arm(config, "b", self.dataset(labels=(8, 7, 6, 5, 4, 3, 2, 1)), deadline=100, clock=lambda: 0., model_factory=self.model_factory)
        for key in ("initial_weights_sha256", "minibatch_order_sha256", "samples_optimized", "optimizer_steps"):
            self.assertEqual(first.metrics[key], second.metrics[key])
        self.assertEqual(first.metrics["optimizer_steps"], 4)
        self.assertEqual(first.metrics["samples_optimized"], 16)
        self.assertEqual(first.metrics["epochs_completed"], 2)
        self.assertNotEqual(onset._weights_digest(first.model), onset._weights_digest(second.model))
        self.assertTrue(all(parameter.requires_grad for parameter in first.model.value.parameters()))
        self.assertFalse(first.model.training)

    def test_fit_rejects_smoke_or_partial_training_before_model_creation(self):
        factory = mock.Mock(side_effect=AssertionError("must not construct model"))
        data = self.dataset("smoke")
        with self.assertRaises(ValueError):
            onset.fit_arm(onset.OnsetConfig(), "bad", data, deadline=100, clock=lambda: 0., model_factory=factory)
        data = self.dataset()
        data.data.receipt["complete"] = False
        with self.assertRaises(ValueError):
            onset.fit_arm(onset.OnsetConfig(), "bad", data, deadline=100, clock=lambda: 0., model_factory=factory)
        factory.assert_not_called()

    def test_subset_recall_has_exact_counts_and_absent_denominators(self):
        data = self.dataset(labels=(0, 1, 1))
        model = self.model_factory(onset.RELATIVE_CONFIG)
        model.actor.weight.data.zero_()
        model.actor.bias.data.zero_()
        metrics = onset.subset_metrics(model, data, deadline=100, clock=lambda: 0.)
        self.assertEqual(metrics["subsets"]["all"]["count"], 3)
        self.assertEqual(metrics["subsets"]["all"]["correct"], 1)
        self.assertEqual(metrics["subsets"]["nonneutral_from_rest"]["count"], 2)
        self.assertEqual(metrics["subsets"]["nonneutral_from_rest"]["correct"], 0)
        self.assertIsNone(metrics["subsets"]["nonneutral_continuation"]["recall"])

    def test_exact_input_overlap_differs_from_seed_frame_overlap(self):
        base = self.dataset(labels=(0, 1))
        same_states_new_ids = onset.TaggedDataset(replace(base.data, sample_ids=((1001, 0), (1001, 1))), base.tags)
        overlap = onset.dataset_overlap(base, same_states_new_ids)
        self.assertEqual(overlap["extra_samples_matching_any_base_state_and_label"], 2)
        self.assertEqual(overlap["extra_samples_with_same_seed_frame_as_base"], 0)
        changed_labels = self.dataset(labels=(8, 8))
        overlap = onset.dataset_overlap(base, changed_labels)
        self.assertEqual(overlap["extra_samples_matching_any_base_state_and_label"], 0)
        self.assertEqual(overlap["extra_samples_with_same_seed_frame_as_base"], 2)

    def test_timeout_returns_partial_fit_for_checkpoint_preservation(self):
        result = onset.fit_arm(onset.OnsetConfig(), "timeout", self.dataset(), deadline=0, clock=lambda: 0., model_factory=self.model_factory)
        self.assertEqual(result.metrics["stop_reason"], "time_budget")
        self.assertEqual(result.metrics["optimizer_steps"], 0)
        self.assertEqual(result.metrics["epochs_completed"], 0)
        self.assertIsInstance(result.optimizer_state, dict)

    def test_collection_failure_retains_receipt_and_never_fits_partial_data(self):
        loaded = SimpleNamespace(sha256="0" * 64, metadata={"source_manifest": {"files": {}}, "metrics": {}})
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            with mock.patch("dodge_learning.teacher_run.source_manifest", return_value={"files": {"new_module.py": "1" * 64}}), \
                 mock.patch.object(onset, "load_collector", return_value=loaded), \
                 mock.patch.object(onset, "collect_tagged", side_effect=AblationTimeout("collection incomplete")), \
                 mock.patch.object(onset, "fit_arm") as fit:
                with self.assertRaisesRegex(AblationTimeout, "collection incomplete"):
                    onset.run_onset_ablation(onset.OnsetConfig(), output, Path("collector.pt"), clock=lambda: 0.)
                fit.assert_not_called()
            failure = json.loads((output / "failure.json").read_text())
            self.assertEqual(failure["error_type"], "AblationTimeout")
            self.assertEqual(failure["completed_arms"], [])
            self.assertTrue((output / "partial-run.json").is_file())
            self.assertFalse((output / "run.json").exists())

    def test_runner_rejects_existing_output_before_any_collection(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(onset, "load_collector") as load:
            output = Path(temporary)
            marker = output / "keep.txt"
            marker.write_text("original")
            with self.assertRaises(FileExistsError):
                onset.run_onset_ablation(onset.OnsetConfig(), output, Path("collector.pt"))
            load.assert_not_called()
            self.assertEqual(marker.read_text(), "original")


if __name__ == "__main__":
    unittest.main()
