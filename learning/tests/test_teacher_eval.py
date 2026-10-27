"""Qualification uses held-out campaigns, never short smoke trajectories."""

from __future__ import annotations

import copy
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from dodge_learning.evaluate import EvaluationTimeout, evaluate
from dodge_learning.policies import ACTION_MASKS, ACTION_NAMES
from dodge_learning.seeds import manifest_hash, seed_manifest

HAS_MODELS = importlib.util.find_spec("torch") is not None and importlib.util.find_spec("numpy") is not None
HAS_NATIVE = importlib.util.find_spec("dodge_learning._native") is not None
if HAS_MODELS:
    import numpy as np
    import torch

    from dodge_learning.teacher import StateActorCritic, TeacherBatch, TeacherConfig
    from dodge_learning.teacher_eval import GreedyTeacherPolicy, evaluate_checkpoint, qualify_teacher


def provenance() -> dict:
    return {
        "adapter_version": "0.1.0", "feature_schema_version": 2, "core_schema_version": 1,
        "snapshot_wire_version": 7, "cartridge_sha256": "a" * 64,
        "game_revision": "b" * 40, "core_source_dirty": "false",
        "action_names": list(ACTION_NAMES), "action_masks": list(ACTION_MASKS),
        "action_repeat": 1, "difficulty": 2, "patterns_enabled": True,
        "powerups_enabled": True, "theme_background": 12, "theme_shadow": 1,
        "max_episode_frames": 18000, "discount": 0.99,
    }


def source_identity() -> dict:
    """Fixed synthetic identities for qualification logic, not measured artifacts."""
    return {
        "native_extension_sha256": "d" * 64,
        "python/dodge_learning/teacher.py": "e" * 64,
        "python/dodge_learning/env.py": "f" * 64,
        "python/dodge_learning/entity_teacher.py": "1" * 64,
    }


def source_manifest(identity: dict) -> dict:
    return {
        "native_extension_sha256": identity["native_extension_sha256"],
        "files": {key: value for key, value in identity.items() if key != "native_extension_sha256"},
    }


def report(name="state_teacher", survival=1000, *, learned=True, coverage=25, split="validation") -> dict:
    seeds = seed_manifest()[split]
    return {
        "policy": name, "learned_policy": learned, "split": split,
        "max_episode_frames": 18000, "action_repeat": 1,
        "action_names": list(ACTION_NAMES), "action_masks": list(ACTION_MASKS),
        "provenance": provenance(),
        "source_identity": source_identity(), "source_identity_verified": True,
        "summary": {},
        "episodes": [{
            "seed": seed, "survival_frames": survival, "native_frames": survival + 1,
            "terminated": True, "truncated": False,
            "pattern_completions": None if coverage is None else int(index < coverage),
        } for index, seed in enumerate(seeds)],
    }


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class EvaluationTimeBudgetTests(unittest.TestCase):
    def test_expired_budget_does_not_start_another_episode(self) -> None:
        clock = Clock()
        instances = []

        class Environment:
            def __init__(self, **kwargs):
                instances.append(self)

            def __enter__(self):
                return self

            def __exit__(self, *_):
                clock.value += 1

            def reset(self, **kwargs):
                return {"info": {"terminated": False, "truncated": False, "provenance": {}}}

            def step(self, action):
                return {"reward_sum": 1.0, "info": {
                    "terminated": False, "truncated": True, "elapsed_native_frames": 1,
                    "episode_frames": 1, "pattern_metrics": [], "pattern_completions": 0,
                    "score": 0, "frame": 14, "state_hash": 0, "pixel_hash": 0,
                }}

        with self.assertRaises(EvaluationTimeout):
            evaluate(seeds=[42, 43], max_frames=1, max_seconds=0.5, clock=clock, environment_factory=Environment)
        self.assertEqual(len(instances), 1)

    def test_budget_is_checked_between_native_steps_and_closes_environment(self) -> None:
        clock = Clock()
        instances = []

        class Environment:
            def __init__(self, **kwargs):
                self.frames = 0
                self.closed = False
                instances.append(self)

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.closed = True

            def reset(self, **kwargs):
                return {"info": {"terminated": False, "truncated": False, "provenance": {}}}

            def step(self, action):
                self.frames += 1
                clock.value += 1
                return {"info": {"elapsed_native_frames": 1, "terminated": False, "truncated": False}, "reward_sum": 1.0}

        with self.assertRaises(EvaluationTimeout):
            evaluate(seeds=[42], max_frames=100, max_seconds=2, clock=clock, environment_factory=Environment)
        self.assertEqual(instances[0].frames, 2)
        self.assertTrue(instances[0].closed)

    def test_invalid_time_budgets_fail_before_environment_construction(self) -> None:
        factory = mock.Mock()
        for value in (0, -1, True, "5", float("nan"), float("inf"), 10**1000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                evaluate(max_seconds=value, environment_factory=factory)
        factory.assert_not_called()


@unittest.skipUnless(HAS_MODELS, "install the optional PyTorch models extra")
class TeacherQualificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = seed_manifest()
        self.teacher = report()
        self.baselines = [report(name, survival=500 + index * 100, learned=False) for index, name in enumerate(("neutral", "random", "avoidance"))]

    def test_paired_bootstrap_pass_is_deterministic_and_does_not_change_global_rng(self) -> None:
        before = np.random.get_state()
        result = qualify_teacher(self.teacher, self.baselines, self.manifest)
        self.assertEqual(result, qualify_teacher(self.teacher, self.baselines, self.manifest))
        after = np.random.get_state()
        self.assertEqual(before[0], after[0])
        np.testing.assert_array_equal(before[1], after[1])
        self.assertEqual(before[2:], after[2:])
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["student_collection_allowed"])
        self.assertEqual(result["best_baseline"], "avoidance")
        self.assertEqual(result["paired_improvement_ci95"], [300.0, 300.0])
        self.assertEqual(result["completed_pattern_episodes"], 25)
        self.assertEqual(result["bootstrap_samples"], 2000)
        json.dumps(result, allow_nan=False)

    def test_nonpositive_confidence_lower_bound_and_missing_coverage_fail(self) -> None:
        teacher = report(survival=700)
        result = qualify_teacher(teacher, self.baselines, self.manifest)
        self.assertEqual(result["paired_improvement_ci95"], [0.0, 0.0])
        self.assertFalse(result["student_collection_allowed"])
        for coverage in (None, 0, 24):
            result = qualify_teacher(report(coverage=coverage), self.baselines, self.manifest)
            self.assertEqual(result["status"], "fail")
            self.assertFalse(result["pattern_coverage_pass"])
            self.assertFalse(result["student_collection_allowed"])

    def test_positive_mean_without_positive_paired_interval_does_not_pass(self) -> None:
        teacher = report(survival=500)
        for index, episode in enumerate(teacher["episodes"]):
            episode["survival_frames"] = 100 if index < 50 else 1401
            episode["native_frames"] = episode["survival_frames"] + 1
        result = qualify_teacher(teacher, self.baselines, self.manifest)
        self.assertGreater(result["mean_paired_survival_improvement"], 0)
        self.assertLess(result["paired_improvement_ci95"][0], 0)
        self.assertFalse(result["student_collection_allowed"])

    def test_smoke_cannot_transfer_qualification(self) -> None:
        smoke = report(split="smoke")
        smoke["episodes"] = smoke["episodes"][:3]
        smoke["max_episode_frames"] = 1000
        result = qualify_teacher(smoke, [], self.manifest)
        self.assertEqual(result["status"], "not_evaluated_smoke_only")
        self.assertFalse(result["student_collection_allowed"])
        smoke["episodes"][0]["seed"] = self.manifest["train"][0]
        with self.assertRaises(ValueError):
            qualify_teacher(smoke, [], self.manifest)

    def test_rejects_leakage_aliases_cap_and_provenance_mismatch(self) -> None:
        leaked = copy.deepcopy(self.manifest)
        leaked["train"][0] = 0
        leaked["validation"][0] = 1
        with self.assertRaisesRegex(ValueError, "overlap"):
            qualify_teacher(self.teacher, self.baselines, leaked)
        for location, field, value in (
            ("teacher", "max_episode_frames", 1000),
            ("teacher", "learned_policy", False),
            ("teacher", "action_repeat", 2),
            ("baseline", "max_episode_frames", 1000),
        ):
            teacher, baselines = copy.deepcopy(self.teacher), copy.deepcopy(self.baselines)
            (teacher if location == "teacher" else baselines[0])[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                qualify_teacher(teacher, baselines, self.manifest)
        for field, value in (("difficulty", 1), ("discount", 0.5), ("game_revision", "changed"), ("feature_schema_version", 1)):
            baselines = copy.deepcopy(self.baselines)
            baselines[0]["provenance"][field] = value
            with self.subTest(provenance=field), self.assertRaises(ValueError):
                qualify_teacher(self.teacher, baselines, self.manifest)
        teacher = copy.deepcopy(self.teacher)
        teacher["provenance"]["max_episode_frames"] = 1000
        with self.assertRaisesRegex(ValueError, "cap"):
            qualify_teacher(teacher, self.baselines, self.manifest)

    def test_requires_all_validation_episodes_and_all_baselines(self) -> None:
        for change in ("missing", "seed", "incomplete", "test"):
            teacher = copy.deepcopy(self.teacher)
            if change == "missing":
                teacher["episodes"].pop()
            elif change == "seed":
                teacher["episodes"][0]["seed"] = self.manifest["train"][0]
            elif change == "incomplete":
                teacher["episodes"][0]["terminated"] = False
            else:
                teacher["split"] = "test"
            with self.subTest(change=change), self.assertRaises(ValueError):
                qualify_teacher(teacher, self.baselines, self.manifest)
        with self.assertRaises(ValueError):
            qualify_teacher(self.teacher, self.baselines[:2], self.manifest)

    def test_formal_qualification_requires_verified_complete_matching_source_identity(self) -> None:
        for target in ("teacher", "baseline"):
            for change in ("missing_flag", "unverified", "missing_identity", "missing_hash", "invalid_hash", "mismatch"):
                teacher, baselines = copy.deepcopy(self.teacher), copy.deepcopy(self.baselines)
                selected = teacher if target == "teacher" else baselines[0]
                if change == "missing_flag":
                    del selected["source_identity_verified"]
                elif change == "unverified":
                    selected["source_identity_verified"] = False
                elif change == "missing_identity":
                    del selected["source_identity"]
                elif change == "missing_hash":
                    del selected["source_identity"]["native_extension_sha256"]
                elif change == "invalid_hash":
                    selected["source_identity"]["native_extension_sha256"] = "not-a-sha256"
                else:
                    selected["source_identity"]["native_extension_sha256"] = "0" * 64
                with self.subTest(target=target, change=change), self.assertRaisesRegex(ValueError, "source|fingerprint"):
                    qualify_teacher(teacher, baselines, self.manifest)

    def test_formal_qualification_rejects_a_valid_substituted_frozen_recipe(self) -> None:
        for split in ("train", "smoke", "validation", "test"):
            alternate = copy.deepcopy(self.manifest)
            alternate[split] = list(range(5000, 5000 + len(alternate[split])))
            # The replacement remains structurally valid and has no RNG-stream
            # overlap. Formal qualification must still use the frozen recipe.
            manifest_hash(alternate)
            teacher, baselines = copy.deepcopy(self.teacher), copy.deepcopy(self.baselines)
            if split == "validation":
                for evaluation in [teacher, *baselines]:
                    for episode, seed in zip(evaluation["episodes"], alternate["validation"]):
                        episode["seed"] = seed
            with self.subTest(split=split), self.assertRaisesRegex(ValueError, "frozen seed recipe"):
                qualify_teacher(teacher, baselines, alternate)

    def test_formal_qualification_requires_exact_default_benchmark_types_and_values(self) -> None:
        for field, alternate, wrong_type in (
            ("difficulty", 1, True),
            ("patterns_enabled", False, 1),
            ("powerups_enabled", False, 1),
            ("theme_background", 3, 12.0),
            ("theme_shadow", 8, True),
        ):
            for value in (alternate, wrong_type):
                teacher, baselines = copy.deepcopy(self.teacher), copy.deepcopy(self.baselines)
                for evaluation in [teacher, *baselines]:
                    evaluation["provenance"][field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, "default benchmark"):
                    qualify_teacher(teacher, baselines, self.manifest)
        self.assertEqual(qualify_teacher(self.teacher, self.baselines, self.manifest)["status"], "pass")

    def test_curriculum_smoke_report_remains_diagnostic_only(self) -> None:
        smoke = report(split="smoke")
        smoke["provenance"].update({
            "difficulty": 1, "patterns_enabled": False, "powerups_enabled": False,
            "theme_background": 3, "theme_shadow": 8,
        })
        result = qualify_teacher(smoke, [], self.manifest)
        self.assertEqual(result["status"], "not_evaluated_smoke_only")
        self.assertFalse(result["student_collection_allowed"])


@unittest.skipUnless(HAS_MODELS, "install the optional PyTorch models extra")
class TeacherCheckpointEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.threads = torch.get_num_threads()
        torch.set_num_threads(1)

    @classmethod
    def tearDownClass(cls):
        torch.set_num_threads(cls.threads)

    def loaded(self):
        manifest = seed_manifest()
        return SimpleNamespace(
            model=StateActorCritic(TeacherConfig(32, 16)), sha256="c" * 64,
            metadata={"seed_manifest": manifest, "seed_manifest_hash": manifest_hash(manifest), "metrics": {"provenance": provenance()}, "source_manifest": {"fixture": "missing-fingerprints"}},
        )

    def test_final_test_access_and_invalid_formal_budgets_reject_before_loading(self):
        with mock.patch("dodge_learning.checkpoints.load_teacher_checkpoint") as loader:
            for kwargs in (
                {"split": "test"}, {"seed_count": 0}, {"seed_count": True}, {"seed_count": 101},
                {"qualify": True}, {"qualify": True, "split": "validation", "max_frames": 18000, "seed_count": 3},
                {"qualify": True, "split": "validation", "max_frames": 18000, "compare_baselines": False},
            ):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    evaluate_checkpoint("unused.pt", **kwargs)
            loader.assert_not_called()

    def test_shared_wall_budget_is_not_reset_for_each_policy(self):
        clock = Clock()
        budgets = []

        def fake_evaluate(**kwargs):
            budgets.append(kwargs["max_seconds"])
            clock.value += 2
            return report(kwargs["policy"], learned=kwargs.get("learned_policy", False), split="smoke")

        with (
            mock.patch("dodge_learning.checkpoints.load_teacher_checkpoint", return_value=self.loaded()),
            mock.patch("dodge_learning.teacher_eval._runtime_source_identity", return_value=source_identity()),
            mock.patch("dodge_learning.teacher_eval.time.perf_counter", clock),
            mock.patch("dodge_learning.teacher_eval.evaluate", side_effect=fake_evaluate),
            self.assertRaises(EvaluationTimeout),
        ):
            evaluate_checkpoint("unused.pt", max_seconds=5)
        self.assertEqual(budgets, [5, 3, 1])

    def test_recorded_fingerprint_mismatches_reject_even_smoke_before_episodes(self):
        for key in source_identity():
            loaded = self.loaded()
            expected = source_identity()
            expected[key] = "0" * 64
            loaded.metadata["source_manifest"] = source_manifest(expected)
            with (
                self.subTest(key=key),
                mock.patch("dodge_learning.checkpoints.load_teacher_checkpoint", return_value=loaded),
                mock.patch("dodge_learning.teacher_eval._runtime_source_identity", return_value=source_identity()),
                mock.patch("dodge_learning.teacher_eval.evaluate") as run,
                self.assertRaisesRegex(ValueError, "fingerprint mismatch"),
            ):
                evaluate_checkpoint("unused.pt", seed_count=1, max_frames=1)
            run.assert_not_called()

    def test_missing_checkpoint_fingerprints_forbid_qualification_before_episodes(self):
        with (
            mock.patch("dodge_learning.checkpoints.load_teacher_checkpoint", return_value=self.loaded()),
            mock.patch("dodge_learning.teacher_eval._runtime_source_identity", return_value=source_identity()),
            mock.patch("dodge_learning.teacher_eval.evaluate") as run,
            self.assertRaisesRegex(ValueError, "requires checkpoint fingerprints"),
        ):
            evaluate_checkpoint("unused.pt", split="validation", max_frames=18000, qualify=True)
        run.assert_not_called()

    def test_substituted_checkpoint_recipe_rejects_before_any_environment_or_evaluation(self):
        for split in ("train", "smoke", "validation", "test"):
            loaded = self.loaded()
            alternate = loaded.metadata["seed_manifest"]
            alternate[split] = list(range(5000, 5000 + len(alternate[split])))
            loaded.metadata["seed_manifest_hash"] = manifest_hash(alternate)
            with (
                self.subTest(split=split),
                mock.patch("dodge_learning.checkpoints.load_teacher_checkpoint", return_value=loaded),
                mock.patch("dodge_learning.env.NativeEnvironment") as environment,
                mock.patch("dodge_learning.teacher_eval.evaluate") as run,
                self.assertRaisesRegex(ValueError, "frozen seed recipe"),
            ):
                evaluate_checkpoint("unused.pt", split="validation", max_frames=18000, qualify=True)
            environment.assert_not_called()
            run.assert_not_called()

    def test_real_checkpoint_with_valid_alternate_validation_manifest_cannot_qualify(self):
        from dodge_learning.checkpoints import save_teacher_checkpoint

        @dataclass(frozen=True)
        class Config:
            train_seeds: tuple[int, ...] = (1000,)

        alternate = seed_manifest()
        alternate["validation"] = list(range(5000, 5100))
        fixture = SimpleNamespace(
            model=StateActorCritic(TeacherConfig(32, 16)), optimizer_state={}, config=Config(),
            metrics={"provenance": provenance()},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "alternate-recipe.pt"
            save_teacher_checkpoint(path, fixture, seed_manifest=alternate, source_manifest=source_manifest(source_identity()))
            with (
                mock.patch("dodge_learning.teacher_eval._runtime_source_identity", return_value=source_identity()),
                mock.patch("dodge_learning.env.NativeEnvironment") as environment,
                mock.patch("dodge_learning.teacher_eval.evaluate") as run,
                self.assertRaisesRegex(ValueError, "frozen seed recipe"),
            ):
                evaluate_checkpoint(path, split="validation", max_frames=18000, qualify=True)
            environment.assert_not_called()
            run.assert_not_called()

    @unittest.skipUnless(HAS_NATIVE, "build the optional native bridge")
    def test_saved_nondefault_benchmark_rejects_before_environment_with_genuine_fingerprints(self):
        from dodge_learning import NativeEnvironment
        from dodge_learning.checkpoints import save_teacher_checkpoint
        from dodge_learning.teacher_eval import _runtime_source_identity

        @dataclass(frozen=True)
        class Config:
            train_seeds: tuple[int, ...] = (1000,)

        original_provenance = NativeEnvironment().current()["info"]["provenance"]
        fingerprints = source_manifest(_runtime_source_identity())
        model = StateActorCritic(TeacherConfig(32, 16))
        with tempfile.TemporaryDirectory() as directory:
            for field, value in (
                ("difficulty", 1), ("patterns_enabled", False), ("powerups_enabled", False),
                ("theme_background", 3), ("theme_shadow", 8),
            ):
                current_provenance = dict(original_provenance, **{field: value})
                fixture = SimpleNamespace(
                    model=model, optimizer_state={}, config=Config(),
                    metrics={"provenance": current_provenance},
                )
                path = Path(directory) / f"nondefault-{field}.pt"
                save_teacher_checkpoint(path, fixture, seed_manifest=seed_manifest(), source_manifest=fingerprints)
                with (
                    self.subTest(field=field),
                    mock.patch("dodge_learning.env.NativeEnvironment") as environment,
                    mock.patch("dodge_learning.teacher_eval.evaluate") as run,
                    self.assertRaisesRegex(ValueError, "default benchmark"),
                ):
                    evaluate_checkpoint(path, split="validation", max_frames=18000, qualify=True)
                environment.assert_not_called()
                run.assert_not_called()

    @unittest.skipUnless(HAS_NATIVE, "build the optional native bridge")
    def test_saved_curriculum_checkpoint_allows_unqualified_smoke(self):
        from dodge_learning import NativeEnvironment
        from dodge_learning.checkpoints import save_teacher_checkpoint
        from dodge_learning.teacher_eval import _runtime_source_identity

        @dataclass(frozen=True)
        class Config:
            train_seeds: tuple[int, ...] = (1000,)

        configuration = {
            "difficulty": 1, "patterns_enabled": False, "powerups_enabled": False,
            "theme_background": 3, "theme_shadow": 8,
        }
        measured = NativeEnvironment(**configuration).current()["info"]["provenance"]
        fixture = SimpleNamespace(
            model=StateActorCritic(TeacherConfig(32, 16)), optimizer_state={}, config=Config(),
            metrics={"provenance": measured},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "curriculum.pt"
            save_teacher_checkpoint(
                path, fixture, seed_manifest=seed_manifest(),
                source_manifest=source_manifest(_runtime_source_identity()),
            )
            result = evaluate_checkpoint(path, seed_count=1, max_frames=1, compare_baselines=False)
        self.assertEqual(result["evaluation_config"], configuration)
        self.assertTrue(result["source_identity_verified"])
        self.assertEqual(result["qualification"]["status"], "not_evaluated_smoke_only")
        self.assertFalse(result["qualification"]["student_collection_allowed"])

    def test_matching_checkpoint_fingerprints_and_runtime_are_recorded_on_all_reports(self):
        loaded = self.loaded()
        loaded.metadata["source_manifest"] = source_manifest(source_identity())

        def fake_evaluate(**kwargs):
            return report(kwargs["policy"], learned=kwargs.get("learned_policy", False), split="smoke")

        with (
            mock.patch("dodge_learning.checkpoints.load_teacher_checkpoint", return_value=loaded),
            mock.patch("dodge_learning.teacher_eval._runtime_source_identity", return_value=source_identity()),
            mock.patch("dodge_learning.teacher_eval.evaluate", side_effect=fake_evaluate),
        ):
            result = evaluate_checkpoint("unused.pt", seed_count=1, max_frames=1)
        self.assertTrue(result["source_identity_verified"])
        self.assertEqual(result["source_identity"], source_identity())
        for evaluation in [result["teacher"], *result["baselines"]]:
            self.assertTrue(evaluation["source_identity_verified"])
            self.assertEqual(evaluation["source_identity"], source_identity())
            self.assertEqual(evaluation["summary"]["runtime"], result["runtime"])
        self.assertEqual(result["runtime"]["torch_threads"], torch.get_num_threads())
        for key in ("python_version", "torch_version", "machine"):
            self.assertTrue(result["runtime"][key])
        self.assertFalse(result["qualification"]["student_collection_allowed"])

    @unittest.skipUnless(HAS_NATIVE, "build the optional native bridge")
    def test_real_tiny_checkpoint_roundtrip_and_two_frame_smoke(self):
        from dodge_learning import NativeEnvironment
        from dodge_learning.checkpoints import save_teacher_checkpoint

        @dataclass(frozen=True)
        class Config:
            train_seeds: tuple[int, ...] = (1000,)

        native_provenance = NativeEnvironment().current()["info"]["provenance"]
        fixture = SimpleNamespace(
            model=StateActorCritic(TeacherConfig(32, 16)), optimizer_state={}, config=Config(),
            metrics={"provenance": native_provenance, "native_frames": 0},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "teacher.pt"
            receipt = save_teacher_checkpoint(path, fixture, seed_manifest=seed_manifest(), source_manifest={"fixture": "smoke-only"})
            result = evaluate_checkpoint(path, seed_count=1, max_frames=2, max_seconds=20)
            self.assertEqual(result["checkpoint"]["sha256"], receipt["sha256"])
            self.assertEqual(result["teacher"]["summary"]["native_frames"], 2)
            self.assertEqual(len(result["baselines"]), 3)
            self.assertFalse(result["qualification"]["student_collection_allowed"])
            self.assertFalse(result["source_identity_verified"])
            self.assertEqual(set(result["source_identity"]), set(source_identity()))
            for evaluation in [result["teacher"], *result["baselines"]]:
                self.assertFalse(evaluation["source_identity_verified"])
                self.assertEqual(evaluation["source_identity"], result["source_identity"])
            self.assertEqual(result["qualification"]["status"], "not_evaluated_smoke_only")
            self.assertEqual(result["allowed_provenance_differences"], ["max_episode_frames", "discount"])
            json.dumps(result, allow_nan=False)

    @unittest.skipUnless(HAS_NATIVE, "build the optional native bridge")
    def test_greedy_policy_passes_only_encoded_features_without_gradients(self):
        from dodge_learning import NativeEnvironment

        model = StateActorCritic(TeacherConfig(32, 16))
        with torch.no_grad():
            model.actor.weight.zero_()
            model.actor.bias.zero_()
            model.actor.bias[5] = 1
        observation = NativeEnvironment().current()
        received = []
        handle = model.register_forward_pre_hook(lambda _, args: received.append((args, torch.is_grad_enabled())))
        self.addCleanup(handle.remove)
        actor = GreedyTeacherPolicy(model, observation["info"]["provenance"])
        self.assertEqual(actor.act(observation), 5)
        self.assertIsInstance(received[0][0][0], TeacherBatch)
        self.assertFalse(received[0][1])
        self.assertFalse(model.training)
        observation["info"]["provenance"]["feature_schema_version"] = 1
        with self.assertRaises(ValueError):
            actor.act(observation)

    @unittest.skipUnless(HAS_NATIVE, "build the optional native bridge")
    def test_runtime_provenance_mismatch_stops_before_policy_decision(self):
        loaded = self.loaded()
        with mock.patch("dodge_learning.checkpoints.load_teacher_checkpoint", return_value=loaded):
            with self.assertRaisesRegex(ValueError, "mismatch"):
                evaluate_checkpoint("unused.pt", seed_count=1, max_frames=1)


if __name__ == "__main__":
    unittest.main()
