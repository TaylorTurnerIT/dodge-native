"""Integration checks across the installed in-process Rust/Python boundary."""

from __future__ import annotations

import importlib.util
import json
import unittest

from dodge_learning import NativeEnvironment
from dodge_learning.evaluate import evaluate
from dodge_learning.pixels import PixelHistory
from dodge_learning.policies import ACTION_MASKS, ACTION_NAMES, AvoidancePolicy

HAS_NATIVE = importlib.util.find_spec("dodge_learning._native") is not None


@unittest.skipUnless(HAS_NATIVE, "build the optional native bridge")
class NativeIntegrationTests(unittest.TestCase):
    def test_seeded_reset_and_all_actions_replay_identically(self) -> None:
        env = NativeEnvironment(seed=42, max_episode_frames=40)
        initial = env.reset()
        self.assertEqual(initial["info"]["frame"], 13)
        self.assertEqual(initial["info"]["episode_frames"], 0)
        self.assertEqual(len(initial["pixels"]), 128 * 128)
        self.assertEqual(initial["info"]["provenance"]["action_masks"], list(ACTION_MASKS))
        self.assertEqual(initial["info"]["provenance"]["action_names"], list(ACTION_NAMES))
        self.assertEqual(initial["info"]["provenance"]["feature_schema_version"], 2)
        trace = [env.step(action) for action in range(9)]
        self.assertEqual(env.reset(), initial)
        self.assertEqual([env.step(action) for action in range(9)], trace)
        self.assertNotEqual(env.reset(74)["info"]["state_hash"], initial["info"]["state_hash"])
        self.assertEqual(env.reset(42), initial)

    def test_repeat_cap_preserves_final_image_and_bootstrap(self) -> None:
        env = NativeEnvironment(max_episode_frames=3, action_repeat=5, discount=0.5)
        initial = env.reset()
        result = env.step(0)
        self.assertEqual(result["reward_sum"], 3)
        self.assertEqual(result["discounted_reward"], 1.75)
        self.assertEqual(result["bootstrap_discount"], 0.125)
        self.assertEqual(result["info"]["elapsed_native_frames"], 3)
        self.assertEqual(result["info"]["episode_frames"], 3)
        self.assertTrue(result["info"]["truncated"])
        self.assertFalse(result["info"]["terminated"])
        self.assertNotEqual(result["info"]["frame"], initial["info"]["frame"])
        with self.assertRaises(RuntimeError):
            env.step(0)
        self.assertEqual(env.current(), result)

    def test_current_retains_transition_statistics_and_errors_preserve_result(self) -> None:
        env = NativeEnvironment(max_episode_frames=2, action_repeat=4, discount=0.5)
        initial = env.current()
        self.assertEqual(initial, env.reset())
        result = env.step(0)
        self.assertEqual(result["bootstrap_discount"], 0.25)
        self.assertEqual(env.current(), result)
        for action in (9, True):
            with self.assertRaises(ValueError):
                env.step(action)
            self.assertEqual(env.current(), result)
        with self.assertRaises(RuntimeError):
            env.step(0)
        self.assertEqual(env.current(), result)
        self.assertEqual(env.reset(), initial)

    def test_numeric_configuration_rejects_booleans_and_invalid_seeds(self) -> None:
        for name in ("seed", "max_episode_frames", "action_repeat", "difficulty", "discount", "theme_background", "theme_shadow"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                NativeEnvironment(**{name: True})
        for name in ("patterns_enabled", "powerups_enabled"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                NativeEnvironment(**{name: 1})
        for discount in (0, -1, 10**1000, -(10**1000), float("nan"), float("inf"), "0.9"):
            with self.subTest(discount=discount), self.assertRaises(ValueError):
                NativeEnvironment(discount=discount)
        env = NativeEnvironment(max_episode_frames=2)
        before = env.current()
        for seed in (-1, 2**32, 1.5, True, "42"):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                env.reset(seed)
            self.assertEqual(env.current(), before)

    def test_student_accessor_returns_only_native_pixels(self) -> None:
        env = NativeEnvironment(max_episode_frames=2)
        observation = env.current()
        image = env.student_observation()
        self.assertIs(type(image), bytes)
        self.assertEqual(image, observation["pixels"])
        observation["info"]["seed"] = "changed"
        observation["train_only_state"]["player"]["x"] = -10000
        self.assertEqual(env.student_observation(), image)
        observation = env.step(1)
        self.assertEqual(env.student_observation(), observation["pixels"])

    def test_real_native_pattern_encounter_exposure_and_completion(self) -> None:
        env = NativeEnvironment(seed=74, max_episode_frames=1000)
        policy = AvoidancePolicy()
        observation = env.reset()
        self.assertEqual(observation["info"]["pattern_metrics"], [])
        exposures = 0
        while not (observation["info"]["terminated"] or observation["info"]["truncated"]):
            observation = env.step(policy.act(observation))
            exposures += observation["info"]["events"].count("pattern_active")
            if observation["info"]["pattern_completions"]:
                break
        rows = observation["info"]["pattern_metrics"]
        self.assertEqual(sum(row["completions"] for row in rows), 1)
        self.assertEqual(sum(row["encounters"] for row in rows), 1)
        self.assertEqual(sum(row["exposure_frames"] for row in rows), exposures)
        self.assertGreater(exposures, 0)
        self.assertFalse(observation["info"]["terminated"])
        self.assertEqual(env.reset()["info"]["pattern_metrics"], [])

    def test_invalid_actions_do_not_mutate_and_history_uses_native_frames(self) -> None:
        env = NativeEnvironment(max_episode_frames=4)
        before = env.reset()
        for action in (-1, 9, True, 1.5, "left"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                env.step(action)
            self.assertEqual(env.current(), before)
        history = PixelHistory()
        history.reset(before["pixels"], before["info"]["frame"])
        result = env.step(1)
        history.append(result["pixels"], result["info"]["frame"])
        self.assertEqual(history.frames[-1], result["pixels"])
        env.reset(74)
        history.reset(env.current()["pixels"], env.current()["info"]["frame"])
        self.assertEqual(len(set(history.frames)), 1)

    def test_actor_features_exclude_metadata_and_evaluation_is_json_safe(self) -> None:
        env = NativeEnvironment(max_episode_frames=4)
        observation = env.reset()
        self.assertEqual(set(observation["train_only_state"]), {"player", "globals", "enemies", "rectangles", "warnings"})
        forbidden = {"seed", "rng", "state_hash", "pixel_hash", "score", "patterns", "targets", "highscores"}

        def check(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & forbidden)
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)

        check(observation["train_only_state"])
        report = evaluate(policy="neutral", seeds=[42, 43], max_frames=4)
        json.dumps(report, allow_nan=False)
        self.assertEqual(report["summary"]["native_frames"], 8)
        self.assertEqual(report["summary"]["cap_hit_rate"], 1)
        self.assertEqual(report["provenance"]["snapshot_wire_version"], 7)


if __name__ == "__main__":
    unittest.main()
