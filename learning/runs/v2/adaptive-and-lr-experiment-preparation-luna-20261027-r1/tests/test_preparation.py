import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adaptive_policy import AdaptiveExposureScheduler, Completion, assignment_block
from lr_schedule import learning_rate_for_update, require_restored_lr, set_and_check_optimizer_lr

DIGEST = hashlib.sha256(b"fixed fake study vector").hexdigest()


class AdaptivePolicyTests(unittest.TestCase):
    def test_first_update_is_full_game_then_admits_short_mix_after_frame_floor(self):
        scheduler = AdaptiveExposureScheduler(DIGEST)
        horizons = [scheduler.assign(1)[1] for _ in range(100)]
        self.assertEqual(set(horizons), {18000})
        row = scheduler.finish_update(1, (), full_game_frames=7000, stage_frames=3000)
        self.assertEqual(row["realized_full_game_frame_share"], 0.7)
        self.assertEqual(row["next_update_stage_assignment_percent"], 30)
        assignments = [scheduler.assign(2) for _ in range(100)]
        self.assertEqual(sum(h == 1000 for _, h, _, _ in assignments), 30)
        self.assertEqual(sum(h == 18000 for _, h, _, _ in assignments), 70)

    def test_below_floor_suspends_short_horizons_next_update(self):
        scheduler = AdaptiveExposureScheduler(DIGEST)
        scheduler.finish_update(1, (), full_game_frames=69, stage_frames=31)
        self.assertEqual(scheduler.next_stage_quota_percent, 0)
        horizons = [scheduler.assign(2)[1] for _ in range(100)]
        self.assertEqual(set(horizons), {18000})

    def test_block_is_deterministic_and_quota_exact(self):
        first = assignment_block(DIGEST, 4, 12, 2, 30)
        self.assertEqual(first, assignment_block(DIGEST, 4, 12, 2, 30))
        self.assertEqual(first.count(5000), 30)
        self.assertEqual(first.count(18000), 70)
        self.assertNotEqual(first, assignment_block(DIGEST, 4, 13, 2, 30))

    def test_mastery_waits_for_minimum_updates_and_two_complete_windows(self):
        scheduler = AdaptiveExposureScheduler(DIGEST)
        for update in range(1, 10):
            rows = [Completion(i, 0, 0, 1000, True) for i in range(100)]
            result = scheduler.finish_update(update, rows,
                full_game_frames=700, stage_frames=300)
            self.assertFalse(result["promoted"])
        rows = [Completion(i, 0, 0, 1000, i < 90) for i in range(100)]
        result = scheduler.finish_update(10, rows,
            full_game_frames=700, stage_frames=300)
        self.assertTrue(result["promoted"])
        self.assertEqual(result["generation_after"], 1)
        self.assertEqual(scheduler.horizon, 2000)

    def test_duplicate_or_wrong_order_completion_rejected_before_update_advance(self):
        scheduler = AdaptiveExposureScheduler(DIGEST)
        duplicate = [Completion(1, 2, 0, 1000, True)] * 2
        with self.assertRaisesRegex(ValueError, "duplicate"):
            scheduler.finish_update(1, duplicate, full_game_frames=1, stage_frames=1)
        self.assertEqual(scheduler.update, 0)
        with self.assertRaisesRegex(ValueError, "order"):
            scheduler.finish_update(2, (), full_game_frames=0, stage_frames=0)


class LearningRateTests(unittest.TestCase):
    def test_endpoint_inclusive_60_update_schedule(self):
        self.assertEqual(learning_rate_for_update(1), 3e-5)
        self.assertEqual(learning_rate_for_update(60), 1e-5)
        self.assertAlmostEqual(learning_rate_for_update(30),
                               3e-5 + (1e-5 - 3e-5) * 29 / 59)
        with self.assertRaises(ValueError):
            learning_rate_for_update(0)

    def test_restore_check_then_per_update_assignment(self):
        optimizer = type("FakeAdam", (), {})()
        optimizer.param_groups = [{"lr": 3e-5}, {"lr": 3e-5}]
        self.assertEqual(require_restored_lr(optimizer, 3e-5), [3e-5, 3e-5])
        expected = learning_rate_for_update(2)
        self.assertEqual(set_and_check_optimizer_lr(optimizer, expected), [3e-5, 3e-5])
        self.assertTrue(all(group["lr"] == expected for group in optimizer.param_groups))
        with self.assertRaisesRegex(ValueError, "restored"):
            require_restored_lr(optimizer, 3e-5)

    def test_mismatched_optimizer_group_not_silently_accepted_by_restore(self):
        optimizer = type("FakeAdam", (), {})()
        optimizer.param_groups = [{"lr": 3e-5}, {"lr": 1e-5}]
        with self.assertRaisesRegex(ValueError, "restored"):
            require_restored_lr(optimizer, 3e-5)


if __name__ == "__main__":
    unittest.main()
