"""CPU unit tests against the explicitly loaded owned extension only.

No installed dodge_rl import, Torch, checkpoint, B/E, or study seed use.
The small fixed-seed survival fixture has no qualification significance.
"""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import sys
import unittest

import numpy as np

OUT = Path(__file__).absolute().parent
MANIFEST = json.loads((OUT / "extension/final/manifest.json").read_text())
BINARY = OUT / MANIFEST["path"]
assert hashlib.sha256(BINARY.read_bytes()).hexdigest() == MANIFEST["sha256"]
assert not any(name == "dodge_rl" or name.startswith("dodge_rl.") for name in sys.modules)
spec = importlib.util.spec_from_file_location("_native", BINARY)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
assert Path(native.__file__).absolute() == BINARY


def synthetic_env(**kwargs):
    options = dict(batch_size=2, difficulty=1, patterns_enabled=False,
                   powerups_enabled=False, num_threads=2, chunk_size=1,
                   seeds_by_slot=[[31, 131], [32, 132]])
    options.update(kwargs)
    return native.VecDodgeEnv(**options)


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.env = synthetic_env()

    def same(self, actual, expected):
        if isinstance(expected, np.ndarray):
            np.testing.assert_array_equal(actual, expected)
        elif isinstance(expected, dict):
            self.assertEqual(actual.keys(), expected.keys())
            for name in expected:
                self.same(actual[name], expected[name])
        elif isinstance(expected, (list, tuple)):
            self.assertEqual(len(actual), len(expected))
            for a, b in zip(actual, expected):
                self.same(a, b)
        else:
            self.assertEqual(actual, expected)

    def reject(self, indices, horizons, error, message=None):
        info = self.env.episode_info()
        observations = copy.deepcopy(self.env.observations())
        if message is None:
            with self.assertRaises(error):
                self.env.truncate_practice(indices, horizons)
        else:
            with self.assertRaisesRegex(error, message):
                self.env.truncate_practice(indices, horizons)
        self.same(self.env.episode_info(), info)
        self.same(self.env.observations(), observations)
        self.assertFalse(self.env.is_poisoned())

    def test_strict_bool_float_scalar_dtype_and_dimension_rejection(self):
        invalid = [True, 0.0, "0", [False], [1.0], ["1"], [np.int64(1)],
                   np.array([True]), np.array([1.0]), np.array([1], dtype=np.int32),
                   np.array([1], dtype=np.uint64), np.array([1], dtype=object),
                   np.array([1], dtype=">i8"), np.array(1, dtype=np.int64),
                   np.array([[1]], dtype=np.int64), np.ones((1, 1, 1), dtype=np.int64)]
        for value in invalid:
            with self.subTest(value=repr(value), argument="indices"):
                self.reject(value, [1000], TypeError)
            with self.subTest(value=repr(value), argument="horizons"):
                self.reject([0], value, TypeError)

    def test_integer_overflow_and_negative_rejection_before_native_work(self):
        for value in [[2**63], [2**100], [-(2**63)-1]]:
            self.reject(value, [1000], OverflowError)
            self.reject([0], value, OverflowError)
        for indices, horizons in [([-1], [1000]), ([0], [-1000]),
                                  ([0], [2**32]), ([0], np.array([2**32], dtype=np.int64)),
                                  (np.array([-1], dtype=np.int64), [1000])]:
            self.reject(indices, horizons, ValueError)
        # Invalid second argument elements reject before native validates frame zero.
        self.reject([0, 1], [1000, True], TypeError)
        self.reject([0, 1], [1000, 2**100], OverflowError)

    def test_native_shape_slot_horizon_and_frame_rejections(self):
        self.reject([0, 1], [1000], ValueError, "PracticeShape")
        self.reject([0], [1000, 1000], ValueError, "PracticeShape")
        self.reject([2], [1000], ValueError, "SlotIndex")
        for horizon in [0, 999, 1001, 18000, 19000]:
            self.reject([0], [horizon], ValueError, "PracticeHorizon")
        self.reject((0,), (1000,), ValueError, "PracticeFrame")
        self.reject(np.array([0], dtype=np.int64), np.array([1000], dtype=np.int64),
                    ValueError, "PracticeFrame")
        self.env = synthetic_env(action_repeat=3)
        self.reject([], [], ValueError, "action_repeat=4")

    def test_empty_and_noncontiguous_int64_inputs(self):
        before = self.env.episode_info()
        self.assertEqual(self.env.truncate_practice([], []), [])
        self.assertEqual(self.env.truncate_practice((), ()), [])
        empty = np.array([], dtype=np.int64)
        self.assertEqual(self.env.truncate_practice(empty, empty), [])
        # A valid noncontiguous input reaches native frame validation, not dtype failure.
        ids = np.array([0, 99, 1, 99], dtype=np.int64)[::2]
        hs = np.array([1000, 99, 1000, 99], dtype=np.int64)[::2]
        self.assertFalse(ids.flags.c_contiguous)
        self.reject(ids, hs, ValueError, "PracticeFrame")
        self.same(self.env.episode_info(), before)

    def test_owned_normal_cap_outputs_survive_reset_and_caller_mutation(self):
        self.env = synthetic_env(raw_frame_cap=8, render_pixels=True, auxiliary_targets=True)
        self.env.step([0, 0])
        final = self.env.step([0, 0])
        saved = copy.deepcopy(final)
        self.assertTrue(final["truncated"].all())
        self.reject([0, 1], [1000, 1000], ValueError, "SlotEnded")
        reset = self.env.reset_done([0, 1])
        self.same(final, saved)
        self.assertEqual([i["seed"]["episode"] for i in reset["info"]], [1, 1])
        for value in final["observations"].values():
            if isinstance(value, np.ndarray):
                value.fill(0)
        final["info"][0]["seed"]["episode"] = 999
        self.same(self.env.episode_info(), reset["info"])
        with self.assertRaisesRegex(ValueError, "SlotNotEnded"):
            self.env.reset_done([0, 1])

    @staticmethod
    def avoidance_actions(observations):
        # Fixed observation-only unit fixture. No policy search, training, RNG or
        # seed replacement. Twelve-frame linear prediction is not an evaluator.
        actions = []
        directions = [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1),
                      (-1, -1), (1, -1), (-1, 1), (1, 1)]
        for g, entities, types, mask in zip(observations["global_feats"][:, 0],
                                          observations["entity_feats"],
                                          observations["entity_types"],
                                          observations["entity_mask"]):
            enemies = entities[mask & (types >= 1) & (types <= 3)]
            best = None
            for action, (ax, ay) in enumerate(directions):
                x, y = float(g[0])*64+64, float(g[1])*64+64
                vx, vy = float(g[2])*2.5, float(g[3])*2.5
                clearance = 12.0
                for frame in range(1, 13):
                    vx, vy = vx*0.8+ax*0.5, vy*0.8+ay*0.5
                    x, y = min(125, max(2, x+vx)), min(125, max(2, y+vy))
                    if len(enemies):
                        ex = enemies[:, 0]*128+64+enemies[:, 6]*4*frame
                        ey = enemies[:, 1]*128+64+enemies[:, 7]*4*frame
                        hx = enemies[:, 2]*64+float(g[4])*4-1
                        hy = enemies[:, 3]*64+float(g[4])*4-1
                        clearance = min(clearance, float(np.minimum(
                            np.maximum(np.abs(x-ex)-hx, np.abs(y-ey)-hy), 12).min()))
                score = clearance - 0.002*((x-64)**2+(y-64)**2)**0.5
                candidate = (score, -action, action)
                if best is None or candidate > best:
                    best = candidate
            actions.append(best[2])
        return actions

    def test_live_h1000_return_order_atomic_duplicate_and_owned_results(self):
        self.env = synthetic_env(auxiliary_targets=True)
        observations = self.env.observations()
        for _ in range(250):
            final = self.env.step(self.avoidance_actions(observations))
            self.assertFalse(final["terminated"].any(), "fixed synthetic fixture died; stop, no seed replacement")
            self.assertFalse(final["truncated"].any())
            observations = final["observations"]
        self.assertEqual([i["gameplay_frames"] for i in final["info"]], [1000, 1000])
        saved = copy.deepcopy(final)
        self.reject([0, 0], [1000, 1000], ValueError, "DuplicatePractice")
        self.reject([0, 1], [1000, 2000], ValueError, "PracticeFrame")
        expected = copy.deepcopy([final["info"][1], final["info"][0]])
        for row in expected:
            row["truncated"] = True
        returned = self.env.truncate_practice(np.array([1, 0], dtype=np.int64), (1000, 1000))
        self.same(returned, expected)
        self.same(self.env.observations(), saved["observations"])
        self.same(final, saved)
        self.reject([0], [1000], ValueError, "SlotEnded")
        reset = self.env.reset_done([0, 1])
        self.same(returned, expected)
        self.same(final, saved)
        self.assertEqual([i["seed"]["episode"] for i in reset["info"]], [1, 1])
        returned[0]["seed"]["episode"] = 999
        returned[1]["diagnostics"]["raw_history_samples"] = 999
        self.same(self.env.episode_info(), reset["info"])


if __name__ == "__main__":
    print(json.dumps({"extension": str(BINARY), "sha256": MANIFEST["sha256"],
                      "python": sys.executable, "version": sys.version,
                      "numpy_version": np.__version__, "fixed_unit_seeds": [31, 32, 131, 132]}), flush=True)
    unittest.main(verbosity=2)
