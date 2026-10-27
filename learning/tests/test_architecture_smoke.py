"""Assembled diagnostic boundaries with a deterministic, synthetic native source."""

from __future__ import annotations

import importlib.util
import json
import unittest
from unittest.mock import patch

from dodge_learning.architecture_smoke import run_architecture_smoke

HAS_TORCH = importlib.util.find_spec("torch") is not None
if HAS_TORCH:
    import torch


class ArchitectureSmokeBoundsTests(unittest.TestCase):
    def test_frame_and_device_limits_fail_before_native_construction(self) -> None:
        for invalid in (0, 129, True, 1.0):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                run_architecture_smoke(max_frames=invalid)
        for invalid in ("auto", "cuda", None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                run_architecture_smoke(invalid)


class FakeNativeEnvironment:
    """Expose a nonvisual catalog row immediately and a hazard after two steps."""

    def __init__(self, *, seed, action_repeat, max_episode_frames):
        if seed != 1000 or action_repeat != 1:
            raise AssertionError("diagnostic must use fixed training seed and repeat 1")
        self.limit = max_episode_frames
        self.frames = 0

    def current(self):
        rows = [
            {"features": [0.] * 32, "kind": 0, "bounds": [64., 64., 68., 68.], "spatial": False},
            {"features": [0.] * 32, "kind": 4, "bounds": [200., 0., 216., 16.], "spatial": False},
        ]
        if self.frames >= 2:
            rows.append({"features": [0.] * 32, "kind": 1, "bounds": [0., 0., 16., 16.], "spatial": True})
        return {
            "pixels": bytes([self.frames % 16]) * (128 * 128),
            "privileged_state": {"schema_version": 1, "globals": [0.] * 64,
                                 "entities": rows, "capture_bounds": [0., 0., 128., 128.]},
            "train_only_state": {
                "player": {"x": 64., "y": 64., "vx": 0., "vy": 0., "size": 4.},
                "globals": {"speed": 1., "freeze_rate": 1., "freeze_active": False},
                "enemies": [], "rectangles": [], "warnings": [],
            },
            "info": {
                "frame": 13 + self.frames, "elapsed_native_frames": int(self.frames > 0),
                "terminated": False, "truncated": self.frames >= self.limit,
                "state_hash": self.frames, "pixel_hash": self.frames,
                "provenance": {"privileged_schema_version": 1, "feature_schema_version": 2,
                               "action_repeat": 1},
            },
        }

    def step(self, action):
        if self.frames >= self.limit:
            raise AssertionError("diagnostic exceeded its game-frame cap")
        if not 0 <= action < 9:
            raise AssertionError("diagnostic supplied invalid action")
        self.frames += 1
        return self.current()

    def student_observation(self):
        return self.current()["pixels"]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


@unittest.skipUnless(HAS_TORCH, "install the optional PyTorch models extra")
class ArchitectureSmokeAssemblyTests(unittest.TestCase):
    def test_three_losses_use_same_paired_frame_without_training_or_files(self) -> None:
        rng_before = torch.random.get_rng_state().clone()
        threads_before = torch.get_num_threads()
        with (
            patch("dodge_learning.env.NativeEnvironment", FakeNativeEnvironment),
            patch("torch.save", side_effect=AssertionError("diagnostic must not save weights")),
            patch("torch.optim.Adam", side_effect=AssertionError("diagnostic must not create optimizer")),
            patch("torch.optim.SGD", side_effect=AssertionError("diagnostic must not create optimizer")),
        ):
            report = run_architecture_smoke("cpu", max_frames=8)
        self.assertEqual(report["game_frames"], 2)
        self.assertEqual(report["paired_frame"], 15)
        self.assertEqual(report["privileged_entity_count"], 3)
        self.assertEqual(report["encoded_entity_count"], 3)
        self.assertEqual(report["nonspatial_entity_count"], 2)
        self.assertEqual(report["valid_attention_rows"], 1)
        self.assertEqual(set(report["losses"]), {"total", "action", "latent", "attention"})
        self.assertEqual(report["shapes"]["images"], [1, 4, 128, 128])
        self.assertEqual(report["shapes"]["student_attention"], [1, 64])
        self.assertTrue(report["same_snapshot_pair_verified"])
        self.assertTrue(report["teacher_gradients_absent"])
        self.assertTrue(report["student_gradients_finite"])
        self.assertGreater(report["max_abs_student_gradient"], 0)
        self.assertEqual(report["optimizer_steps"], 0)
        for key in ("trained_policy", "teacher_trained", "student_collection_allowed",
                    "game_evaluation", "checkpoint_written", "dataset_written"):
            self.assertIs(report[key], False)
        self.assertEqual(report["qualification"], "not_evaluated")
        self.assertTrue(torch.equal(rng_before, torch.random.get_rng_state()))
        self.assertEqual(threads_before, torch.get_num_threads())
        json.dumps(report, allow_nan=False)

    def test_no_hazard_within_cap_reports_zero_attention_rows(self) -> None:
        with patch("dodge_learning.env.NativeEnvironment", FakeNativeEnvironment):
            report = run_architecture_smoke("cpu", max_frames=1)
        self.assertEqual(report["game_frames"], 1)
        self.assertEqual(report["valid_attention_rows"], 0)
        self.assertEqual(report["losses"]["attention"], 0)
        self.assertEqual(report["encoded_entity_count"], 2)
        self.assertTrue(report["teacher_gradients_absent"])


if __name__ == "__main__":
    unittest.main()
