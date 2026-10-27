"""Fixed dataset ownership, exact reproduction and non-mutating budget snapshots."""

from __future__ import annotations

import copy
from dataclasses import replace
import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

HAS_MODELS = importlib.util.find_spec("torch") is not None and importlib.util.find_spec("numpy") is not None
if HAS_MODELS:
    import numpy as np
    import torch
    import dodge_learning.teacher_fit_budget as dose
    import dodge_learning.teacher_onset_ablation as onset
    from dodge_learning.entity_teacher import EntityActorCritic, encode_entities


class FakeOracle:
    def act(self, observation):
        return observation.get("label", 0)


class FakePolicy:
    def act(self, observation):
        return observation.get("action", 0)


class DeathEnvironment:
    def __init__(self, *, seed, max_episode_frames, action_repeat, discount):
        self.frame = 0

    def observation(self):
        return {"label": 1, "action": 1, "train_only_state": {"player": {"vx": 0., "vy": 0.}},
                "reward_sum": float(0 < self.frame < 3),
                "info": {"episode_frames": self.frame, "elapsed_native_frames": int(self.frame > 0),
                         "terminated": self.frame == 3, "truncated": False, "provenance": {},
                         "pattern_completions": 0}}

    def reset(self, seed):
        self.frame = 0
        return self.observation()

    def step(self, action):
        self.frame += 1
        return self.observation()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


@unittest.skipUnless(HAS_MODELS, "install optional model dependencies")
class FitBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)

    @classmethod
    def tearDownClass(cls):
        torch.set_num_threads(cls.previous_threads)

    def data(self, split="train", marker=0.):
        rows = []
        for index in range(8):
            features = [index / 128, .5, 0., 0., .5] + [0.] * 27
            state = encode_entities({"schema_version": 1, "globals": [marker] + [0.] * 63,
                                     "entities": [{"features": features, "kind": 0,
                                                   "bounds": [0., 0., 4., 4.], "spatial": False}],
                                     "capture_bounds": [0., 0., 128., 128.]})
            label = index % 3
            observation = {"train_only_state": {"player": {"vx": 0., "vy": 0.}}}
            rows.append((state, label, (1000 if split == "train" else 2000, index), onset._tags(observation, label, 0)))
        return onset._dataset(rows, {"split": split, "complete": True, "collection_mode": "oracle_train",
                                     "native_frames": 8, "provenance": {"feature_schema_version": 2,
                                     "privileged_schema_version": 1, "action_repeat": 1}})

    def factory(self, config):
        return EntityActorCritic(replace(config, embed_dim=8, depth=1, num_heads=1))

    def config(self, **changes):
        return replace(dose.FitBudgetConfig(epochs=4, milestones=(2, 4), reproduction_epoch=2, batch_size=4), **changes)

    def budget(self, config=None):
        return dose.ResourceBudget(config or self.config(), clock=lambda: 0., rss=lambda: 0)

    def reference(self, data=None, epochs=2):
        result = onset.fit_arm(onset.OnsetConfig(epochs=epochs, batch_size=4), "old", data or self.data(),
                               deadline=100., clock=lambda: 0., model_factory=self.factory)
        return dose.ReproductionReference(copy.deepcopy(dict(result.model.state_dict())),
                                          copy.deepcopy(result.optimizer_state), copy.deepcopy(result.metrics))

    def fit(self, reference=None, snapshot=lambda state: False, partial=None):
        data = self.data()
        return dose.fit_dose(self.config(), data, reference or self.reference(data), budget=self.budget(),
                             snapshot=snapshot, partial=partial, model_factory=self.factory)

    def test_new_budget_does_not_widen_old_ablation_limits(self):
        self.assertEqual(dose.FitBudgetConfig().max_seconds, 1800)
        with self.assertRaises(ValueError):
            onset.OnsetConfig(max_seconds=1800)
        for changes in ({"epochs": 65}, {"milestones": (2, 2, 4)}, {"milestones": (True, 4)},
                        {"max_seconds": 1801}, {"max_rss_bytes": dose.MAX_RSS_BYTES + 1},
                        {"train_seeds": (1000,)}, {"learning_rate": float("nan")}, {"torch_threads": 2}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.config(**changes)
        with self.assertRaisesRegex(ValueError, "frozen fit-budget recipe"):
            self.config().require_production_recipe()

    def test_cooperative_time_and_peak_memory_limits(self):
        clock = [0.]
        memory = [0]
        budget = dose.ResourceBudget(dose.FitBudgetConfig(max_seconds=1, max_rss_bytes=100),
                                     clock=lambda: clock[0], rss=lambda: memory[0])
        self.assertEqual(budget.check(), 0.)
        memory[0] = 101
        with self.assertRaisesRegex(MemoryError, "peak-RSS"):
            budget.check()
        memory[0], clock[0] = 0, 1.
        with self.assertRaises(onset.AblationTimeout):
            budget.check()

    def test_epoch_reproduction_matches_old_optimizer_and_exact_model(self):
        reference = self.reference()
        snapshots = []
        result = self.fit(reference=reference, snapshot=lambda state: snapshots.append(state) or False)
        self.assertEqual([state.metrics["epochs_completed"] for state in snapshots], [2, 4])
        self.assertEqual(result.metrics["optimizer_steps"], 8)
        self.assertEqual(result.metrics["samples_optimized"], 32)
        self.assertTrue(snapshots[0].metrics["reproduction"]["exact_model_tensors"])
        self.assertEqual(dose.tree_digest(snapshots[0].optimizer_state), dose.tree_digest(reference.optimizer_state))
        self.assertNotEqual(dose.tree_digest(snapshots[0].optimizer_state), dose.tree_digest(result.optimizer_state))
        self.assertFalse(result.model.training)
        self.assertTrue(all(parameter.requires_grad for parameter in result.model.value.parameters()))

    def test_snapshot_evaluation_preserves_continuous_fit_and_rng(self):
        reference = self.reference()
        before_torch = torch.random.get_rng_state().clone()
        before_numpy = np.random.get_state()
        plain = self.fit(reference=reference)
        smoke = self.data("smoke", marker=1.)
        evaluations = []

        def evaluate(state):
            evaluations.append(dose.evaluate_fixed(state.model, smoke, self.budget()))
            return False

        observed = self.fit(reference=reference, snapshot=evaluate)
        self.assertEqual(onset._weights_digest(plain.model), onset._weights_digest(observed.model))
        self.assertEqual(dose.tree_digest(plain.optimizer_state), dose.tree_digest(observed.optimizer_state))
        self.assertEqual(plain.metrics["minibatch_order_sha256"], observed.metrics["minibatch_order_sha256"])
        self.assertTrue(torch.equal(before_torch, torch.random.get_rng_state()))
        after_numpy = np.random.get_state()
        np.testing.assert_array_equal(before_numpy[1], after_numpy[1])
        self.assertEqual(before_numpy[2:], after_numpy[2:])
        self.assertEqual(len(evaluations), 2)

    def test_snapshot_checkpoint_retains_its_optimizer_before_later_updates(self):
        from dodge_learning.checkpoints import load_teacher_checkpoint, save_teacher_checkpoint
        from dodge_learning.seeds import seed_manifest
        reference = self.reference()
        with tempfile.TemporaryDirectory() as temporary:
            paths = []

            def save(state):
                path = Path(temporary) / f"epoch-{state.metrics['epochs_completed']}.pt"
                save_teacher_checkpoint(path, state, seed_manifest=seed_manifest(), source_manifest={"fixture": "unit"})
                paths.append(path)
                return False

            result = self.fit(reference=reference, snapshot=save)
            loaded = load_teacher_checkpoint(paths[0])
            payload = torch.load(paths[0], map_location="cpu", weights_only=True)
            self.assertEqual(dose.tree_digest(dict(loaded.model.state_dict())), dose.tree_digest(reference.model_state))
            self.assertEqual(dose.tree_digest(payload["optimizer_state"]), dose.tree_digest(reference.optimizer_state))
            self.assertNotEqual(dose.tree_digest(payload["optimizer_state"]), dose.tree_digest(result.optimizer_state))
            self.assertEqual(loaded.metadata["metrics"]["epochs_completed"], 2)
            self.assertEqual(loaded.metadata["training_config"]["milestones"], [2, 4])

    def test_wrong_model_optimizer_or_order_aborts_before_snapshot(self):
        for field in ("model", "optimizer", "order"):
            reference = self.reference()
            if field == "model":
                reference.model_state[next(iter(reference.model_state))].add_(1)
            elif field == "optimizer":
                reference.optimizer_state["state"][0]["exp_avg"].add_(1)
            else:
                reference.metrics["minibatch_order_sha256"] = "0" * 64
            snapshot, partial = mock.Mock(), mock.Mock()
            with self.subTest(field=field), self.assertRaisesRegex(RuntimeError, "reproduction failed"):
                self.fit(reference=reference, snapshot=snapshot, partial=partial)
            snapshot.assert_not_called()
            self.assertEqual(partial.call_args.args[0].metrics["epochs_completed"], 2)

    def test_snapshot_cannot_change_weights_or_torch_rng(self):
        for mutation in ("weights", "rng"):
            def corrupt(state):
                if mutation == "weights":
                    next(state.model.parameters()).data.add_(1)
                else:
                    torch.rand(1)
                return False
            with self.subTest(mutation=mutation), self.assertRaisesRegex(RuntimeError, "snapshot changed"):
                self.fit(snapshot=corrupt)

    def test_only_train_records_enter_gradient_enabled_calls(self):
        original_logits = dose._logits
        smoke = self.data("smoke", marker=1.)
        reference = self.reference()
        grad_calls = []

        def checked(model, states):
            if torch.is_grad_enabled():
                self.assertTrue(all(float(state.globals[0]) == 0 for state in states))
                grad_calls.append(len(states))
            return original_logits(model, states)

        with mock.patch.object(dose, "_logits", side_effect=checked):
            self.fit(reference=reference, snapshot=lambda state: dose.evaluate_fixed(state.model, smoke, self.budget()) and False)
        self.assertEqual(sum(grad_calls), 32)
        factory = mock.Mock()
        for data in (smoke, self.data()):
            if data is not smoke:
                data.data.receipt["complete"] = False
            with self.assertRaisesRegex(ValueError, "complete nonempty training"):
                dose.fit_dose(self.config(), data, reference, budget=self.budget(), snapshot=mock.Mock(), model_factory=factory)
        factory.assert_not_called()

    def test_final_loss_is_fixed_model_cross_entropy(self):
        model = self.factory(onset.RELATIVE_CONFIG)
        model.actor.weight.data.zero_()
        model.actor.bias.data.zero_()
        metrics = dose.evaluate_fixed(model, self.data(), self.budget())
        self.assertAlmostEqual(metrics["final_ce_loss"], math.log(9), places=5)
        self.assertEqual(metrics["subsets"]["all"]["count"], 8)
        self.assertEqual(metrics["subsets"]["all"]["correct"], 3)
        self.assertEqual(metrics["prediction_counts"]["neutral"], 8)
        self.assertNotIn("online_classification_loss", metrics)

    def test_early_stop_gate_requires_all_three_fit_subsets(self):
        metrics = {"subsets": {key: {"recall": 1.} for key in ("all", "nonneutral_onset", "nonneutral_continuation")}}
        self.assertTrue(dose.fit_gate(metrics))
        for key, value in (("all", .98), ("nonneutral_onset", .89), ("nonneutral_continuation", .94), ("nonneutral_onset", None)):
            changed = copy.deepcopy(metrics)
            changed["subsets"][key]["recall"] = value
            self.assertFalse(dose.fit_gate(changed))
        result = self.fit(snapshot=lambda state: True)
        self.assertEqual(result.metrics["stop_reason"], "early_fit_gate")
        self.assertEqual(result.metrics["epochs_completed"], 2)

    def test_visited_onsets_and_action_runs_use_each_native_frame(self):
        tracker = dose.TrackedPolicy(FakePolicy())
        labels, actions = [0, 1, 1, 0, 2, 2, 2], [0, 1, 1, 1, 2, 0, 2]
        with mock.patch.object(dose, "AvoidancePolicy", FakeOracle):
            for label, action in zip(labels, actions):
                observation = {"label": label, "action": action, "train_only_state": {"player": {"vx": 0., "vy": 0.}}}
                self.assertEqual(tracker.act(observation), action)
        report = tracker.report()
        self.assertEqual(report["longest_same_nonneutral_action_run"], 3)
        self.assertEqual(report["longest_run_by_action"], {"left": 3, "right": 1})
        agreement = report["visited_path_oracle_agreement"]
        self.assertEqual((agreement["nonneutral_onset"]["correct"], agreement["nonneutral_onset"]["count"]), (2, 2))
        self.assertEqual((agreement["nonneutral_continuation"]["correct"], agreement["nonneutral_continuation"]["count"]), (2, 3))

    def test_gameplay_keeps_reward_survival_and_executed_runs_separate(self):
        with mock.patch.object(dose, "AvoidancePolicy", FakeOracle), \
             mock.patch.object(onset, "AvoidancePolicy", FakeOracle), \
             mock.patch("dodge_learning.teacher_eval.GreedyTeacherPolicy", return_value=FakePolicy()), \
             mock.patch("dodge_learning.teacher_eval._match_provenance"):
            report = dose.evaluate_gameplay(mock.Mock(), {}, self.budget(), environment_factory=DeathEnvironment)
        self.assertEqual(report["mean_survival_frames"], 2.)
        self.assertEqual(report["native_frames"], 30)
        self.assertEqual(report["episodes"][0]["longest_same_nonneutral_action_run"], 3)
        self.assertEqual(report["unique_action_sequences"], 1)
        self.assertEqual(report["episodes"][0]["visited_path_oracle_agreement"]["nonneutral_continuation"]["count"], 2)

    def test_wrong_collector_is_rejected_before_model_loading(self):
        with tempfile.TemporaryDirectory() as temporary:
            wrong = Path(temporary) / "moving.pt"
            wrong.write_bytes(b"moving teacher instead of stationary collector")
            with mock.patch.object(dose, "load_collector") as load, self.assertRaisesRegex(ValueError, "original stationary"):
                dose.load_frozen_inputs(wrong, wrong)
            load.assert_not_called()

    def test_data_and_tag_hashes_both_guard_fixed_examples(self):
        data = self.data()
        receipt = data.data.receipt
        dose.require_identity(data, receipt["state_identity_sha256"], receipt["tags_identity_sha256"], "base")
        for expected_data, expected_tags in (("0" * 64, receipt["tags_identity_sha256"]), (receipt["state_identity_sha256"], "0" * 64)):
            with self.assertRaisesRegex(RuntimeError, "dataset or onset-tag identity"):
                dose.require_identity(data, expected_data, expected_tags, "base")

    def test_dataset_mismatch_retains_failure_without_fitting(self):
        data = self.data()
        collector = SimpleNamespace(sha256=dose.COLLECTOR_SHA256)
        reference = SimpleNamespace(sha256=dose.REFERENCE_SHA256)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fit"
            with mock.patch("dodge_learning.teacher_run.source_manifest", return_value={"files": {}}), \
                 mock.patch.object(dose, "load_frozen_inputs", return_value=(collector, reference, mock.Mock())), \
                 mock.patch.object(dose, "collect_tagged", return_value=(data, None)), \
                 mock.patch.object(dose, "fit_dose") as fit:
                with self.assertRaisesRegex(RuntimeError, "base dataset"):
                    dose.run_fit_budget(dose.FitBudgetConfig(), output, Path("collector"), Path("reference"), clock=lambda: 0., rss=lambda: 0)
                fit.assert_not_called()
            self.assertTrue((output / "failure.json").exists())
            self.assertTrue((output / "partial-run.json").exists())
            self.assertFalse((output / "run.json").exists())

    def test_memory_limit_retains_failure_and_closes_before_loading(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fit"
            with mock.patch("dodge_learning.teacher_run.source_manifest", return_value={"files": {}}), \
                 mock.patch.object(dose, "load_frozen_inputs") as load, self.assertRaises(MemoryError):
                dose.run_fit_budget(dose.FitBudgetConfig(max_rss_bytes=1), output, Path("a"), Path("b"), clock=lambda: 0., rss=lambda: 2)
            load.assert_not_called()
            self.assertTrue((output / "failure.json").exists())

    def test_fit_limit_retains_last_partial_optimizer_before_raising(self):
        reference = self.reference()
        calls = [0]
        def memory():
            calls[0] += 1
            return 0 if calls[0] < 5 else dose.MAX_RSS_BYTES + 1
        budget = dose.ResourceBudget(self.config(), clock=lambda: 0., rss=memory)
        partial = mock.Mock()
        with self.assertRaises(MemoryError):
            dose.fit_dose(self.config(), self.data(), reference, budget=budget, snapshot=mock.Mock(),
                          partial=partial, model_factory=self.factory)
        state = partial.call_args.args[0]
        self.assertEqual(state.metrics["stop_reason"], "failure")
        self.assertEqual(state.metrics["optimizer_steps"], 1)
        self.assertTrue(state.optimizer_state["state"])

    def test_existing_output_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            marker = output / "keep"
            marker.write_text("preserve")
            with mock.patch.object(dose, "load_frozen_inputs") as load, self.assertRaises(FileExistsError):
                dose.run_fit_budget(dose.FitBudgetConfig(), output, Path("a"), Path("b"))
            load.assert_not_called()
            self.assertEqual(marker.read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()
