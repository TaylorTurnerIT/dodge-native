import argparse
import json
import random
import unittest

from dodge_learning.evaluate import MAX_SEEDS, evaluate, parse_seeds, unique_seeds
from dodge_learning.policies import (
    ACTION_MASKS,
    ACTION_NAMES,
    AvoidancePolicy,
    RandomPolicy,
    make_policy,
)


def state(enemies=None, rectangles=None):
    return {
        "train_only_state": {
            "player": {"x": 64.0, "y": 64.0, "vx": 0.0, "vy": 0.0, "size": 4.0},
            "globals": {"speed": 1.0, "freeze_rate": 1.0, "freeze_active": False},
            "enemies": [] if enemies is None else enemies,
            "rectangles": [] if rectangles is None else rectangles,
            "warnings": [],
        },
    }


class FakeEnvironment:
    instances = []

    def __init__(self, *, seed, max_episode_frames, action_repeat):
        self.seed = seed
        self.max_frames = max_episode_frames
        self.closed = False
        self.actions = []
        self.frames = 0
        self.instances.append(self)
        if action_repeat != 1:
            raise AssertionError("expected repeat 1")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def reset(self, *, seed):
        self.frames = 0
        return self._observation()

    def _observation(self):
        dead = self.seed == 3 and self.frames >= 2
        truncated = not dead and self.frames >= self.max_frames
        observation = state()
        observation.update({
            "pixels": bytes(128 * 128),
            "reward_sum": 0.0 if dead or self.frames == 0 else 1.0,
            "info": {
                "frame": self.frames + 13,
                "episode_frames": self.frames,
                "elapsed_native_frames": 0 if self.frames == 0 else 1,
                "score": 0.5,
                "terminated": dead,
                "truncated": truncated,
                "state_hash": self.frames + 123,
                "pixel_hash": self.frames + 456,
                "pattern_completions": 0,
                "provenance": {"core_schema_version": 1, "cartridge_sha256": "abc"},
            },
        })
        return observation

    def step(self, action):
        self.actions.append(action)
        self.frames += 1
        return self._observation()


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        FakeEnvironment.instances = []

    def test_seed_stream_deduplication_and_bounds(self):
        self.assertEqual(unique_seeds([0, 1, 2, 2]), [0, 2])
        self.assertEqual(parse_seeds("42, 1, 0, 42, 4294967295"), [42, 1, 0xFFFFFFFF])
        for invalid in ([], [-1], [0x100000000], [True], [1.5], [1] * (MAX_SEEDS + 1)):
            with self.assertRaises(ValueError):
                unique_seeds(invalid)
        for invalid in ("", "1,,2", "-1", "4294967296", "x"):
            with self.assertRaises(argparse.ArgumentTypeError):
                parse_seeds(invalid)

    def test_action_mapping_random_reproducibility_and_global_rng_isolation(self):
        self.assertEqual(ACTION_MASKS, (0, 1, 2, 4, 8, 5, 6, 9, 10))
        self.assertEqual(ACTION_NAMES[6], "up_right")
        before = random.getstate()
        first, second = RandomPolicy(42), RandomPolicy(42)
        values = [first.act({}) for _ in range(100)]
        self.assertEqual(values, [second.act({}) for _ in range(100)])
        self.assertEqual(set(values), set(range(9)))
        self.assertEqual(random.getstate(), before)
        with self.assertRaises(ValueError):
            make_policy("pretend-trained")

    def test_avoidance_reacts_to_enemy_and_pattern_rectangle(self):
        policy = AvoidancePolicy()
        self.assertEqual(policy.act(state()), 0)
        enemy = {"x": 66.0, "y": 62.0, "vx": 0.0, "vy": 0.0, "size": 4.0, "kind": 0}
        self.assertEqual(ACTION_MASKS[policy.act(state(enemies=[enemy]))] & 1, 1)
        rectangle = {"x": 65.0, "y": 0.0, "width": 10.0, "height": 128.0, "dx": 0.0, "dy": 0.0}
        self.assertEqual(ACTION_MASKS[policy.act(state(rectangles=[rectangle]))] & 1, 1)
        friendly = dict(enemy, kind=3)
        self.assertEqual(policy.act(state(enemies=[friendly])), 0)

    def test_evaluation_distinguishes_terminal_and_truncated_and_reports_json(self):
        report = evaluate(policy="neutral", seeds=[3, 1, 0], max_frames=2,
                          environment_factory=FakeEnvironment)
        terminal, capped = report["episodes"]
        self.assertEqual((terminal["native_frames"], terminal["survival_frames"]), (2, 1))
        self.assertTrue(terminal["terminated"])
        self.assertFalse(terminal["truncated"])
        self.assertEqual(capped["survival_frames"], 2)
        self.assertTrue(capped["truncated"])
        self.assertEqual(report["summary"]["native_frames"], 4)
        self.assertEqual(report["summary"]["mean_survival_frames"], 1.5)
        self.assertEqual(report["summary"]["tenth_percentile_survival_frames"], 1.1)
        self.assertFalse(report["learned_policy"])
        json.loads(json.dumps(report, allow_nan=False))
        self.assertTrue(all(env.closed for env in FakeEnvironment.instances))
        self.assertTrue(all(env.actions == [0, 0] for env in FakeEnvironment.instances))

    def test_evaluation_rejects_invalid_budgets_before_constructing_environment(self):
        for invalid in (0, -1, 18_001, True, 1.5):
            with self.assertRaises(ValueError):
                evaluate(max_frames=invalid, environment_factory=FakeEnvironment)
        self.assertFalse(FakeEnvironment.instances)

    def test_pattern_identity_exposure_and_completion_survive_episode_aggregation(self):
        class PatternEnvironment(FakeEnvironment):
            def _observation(self):
                result = super()._observation()
                result["info"]["pattern_completions"] = 1
                if self.seed == 4:
                    metrics = [
                        {"id": 7, "encounters": 1, "exposure_frames": 3, "completions": 1},
                        {"id": 2, "encounters": 1, "exposure_frames": 1, "completions": 0},
                    ]
                else:
                    metrics = [
                        {"id": 7, "encounters": 1, "exposure_frames": 1, "completions": 1},
                        {"id": 9, "encounters": 1, "exposure_frames": 3, "completions": 0},
                    ]
                result["info"]["pattern_metrics"] = metrics
                return result

        report = evaluate(seeds=[4, 5], max_frames=4, environment_factory=PatternEnvironment)
        self.assertEqual(report["episodes"][0]["pattern_metrics"], [
            {"id": 2, "encounters": 1, "exposure_frames": 1, "completions": 0},
            {"id": 7, "encounters": 1, "exposure_frames": 3, "completions": 1},
        ])
        self.assertEqual(report["episodes"][1]["pattern_metrics"][0]["exposure_frames"], 1)
        self.assertEqual(report["summary"]["pattern_metrics"], [
            {"id": 2, "encounters": 1, "exposure_frames": 1, "completions": 0},
            {"id": 7, "encounters": 2, "exposure_frames": 4, "completions": 2},
            {"id": 9, "encounters": 1, "exposure_frames": 3, "completions": 0},
        ])
        self.assertEqual(report["summary"]["pattern_totals"], {
            "encounters": 4, "exposure_frames": 8, "completions": 2,
        })
        self.assertEqual(report["summary"]["completed_pattern_episodes"], 2)
        json.loads(json.dumps(report, allow_nan=False))

    def test_pattern_metrics_distinguish_unavailable_and_measured_zero(self):
        missing = evaluate(max_frames=1, environment_factory=FakeEnvironment)
        self.assertIsNone(missing["episodes"][0]["pattern_metrics"])
        self.assertIsNone(missing["summary"]["pattern_metrics"])
        self.assertIsNone(missing["summary"]["pattern_totals"])

        class ZeroPatterns(FakeEnvironment):
            def _observation(self):
                result = super()._observation()
                result["info"]["pattern_metrics"] = []
                return result

        zero = evaluate(max_frames=1, environment_factory=ZeroPatterns)
        self.assertEqual(zero["episodes"][0]["pattern_metrics"], [])
        self.assertEqual(zero["summary"]["pattern_metrics"], [])
        self.assertEqual(zero["summary"]["pattern_totals"], {
            "encounters": 0, "exposure_frames": 0, "completions": 0,
        })

        class MixedAvailability(ZeroPatterns):
            def _observation(self):
                result = super()._observation()
                if self.seed == 5:
                    result["info"].pop("pattern_metrics")
                return result

        mixed = evaluate(seeds=[4, 5], max_frames=1, environment_factory=MixedAvailability)
        self.assertEqual(mixed["episodes"][0]["pattern_metrics"], [])
        self.assertIsNone(mixed["episodes"][1]["pattern_metrics"])
        self.assertIsNone(mixed["summary"]["pattern_totals"])

    def test_pattern_metrics_reject_invalid_native_counters(self):
        valid = {"id": 7, "encounters": 1, "exposure_frames": 2, "completions": 1}
        invalid = [
            ([dict(valid, encounters=-1)], 1),
            ([dict(valid, exposure_frames=float("nan"))], 1),
            ([dict(valid, completions=1.0)], 1),
            ([dict(valid, id=True)], 1),
            ([dict(valid, id=256)], 1),
            ([valid, valid], 2),
            ([dict(valid, completions=2)], 2),
            ([dict(valid, exposure_frames=3)], 1),
            ([dict(valid, encounters=2, exposure_frames=1)], 1),
            ([valid], 0),
            ({"id": valid}, 1),
            ([{"id": 7}], 0),
            ([dict(valid, id=7, completions=0), dict(valid, id=8, completions=0)], 0),
        ]
        for metrics, scalar in invalid:
            with self.subTest(metrics=metrics, scalar=scalar):
                class InvalidPatterns(FakeEnvironment):
                    def _observation(self):
                        result = super()._observation()
                        result["info"]["pattern_metrics"] = metrics
                        result["info"]["pattern_completions"] = scalar
                        return result

                with self.assertRaises(RuntimeError):
                    evaluate(seeds=[4], max_frames=2, environment_factory=InvalidPatterns)
                self.assertTrue(FakeEnvironment.instances[-1].closed)

    def test_broken_environment_cannot_run_forever_or_hide_skipped_frames(self):
        class NeverFinishes(FakeEnvironment):
            def _observation(self):
                result = super()._observation()
                result["info"]["terminated"] = result["info"]["truncated"] = False
                return result

        with self.assertRaisesRegex(RuntimeError, "did not finish"):
            evaluate(seeds=[42], max_frames=2, environment_factory=NeverFinishes)
        self.assertTrue(FakeEnvironment.instances[-1].closed)

        class SkipsFrames(FakeEnvironment):
            def step(self, action):
                result = super().step(action)
                result["info"]["elapsed_native_frames"] = 2
                return result

        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            evaluate(seeds=[42], max_frames=2, environment_factory=SkipsFrames)


if __name__ == "__main__":
    unittest.main()
