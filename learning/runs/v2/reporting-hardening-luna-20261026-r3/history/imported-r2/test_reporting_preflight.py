from __future__ import annotations

import copy
import json
from pathlib import Path
import random
import unittest

import reporting_preflight as tool

ROOT = Path(__file__).resolve().parents[4]
V2 = ROOT / "learning/runs/v2"
RECEIPT_PATH = V2 / "d2-gradient-parent-terminal-audit-20261025-r2/parent-terminal-receipt.json"
REGISTRATION_PATH = V2 / "D2-continuation180-parent-freeze-20261025-r4/registration-proposed.json"
REGISTRATION_SHA = "0059ce1a3f2dae18a34b085b57b251c115ac53e7bc82835a6eff2164ac70e949"
RECEIPT_SHA = "7968a62b6e601fab971e4145dbaebfa1995c8f696e6df442ab70fc0435b74903"


class AuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT_PATH.read_text())
        cls.receipt["_path"] = str(RECEIPT_PATH.resolve())
        cls.registration = json.loads(REGISTRATION_PATH.read_text())

    def test_real_accepted_receipt_and_registration_bind(self):
        self.assertEqual(tool.sha256(RECEIPT_PATH), RECEIPT_SHA)
        self.assertEqual(tool.sha256(REGISTRATION_PATH), REGISTRATION_SHA)
        authority = tool.validate_authority(self.receipt, self.registration,
                                           RECEIPT_SHA, REGISTRATION_SHA)
        self.assertEqual(authority["checkpoint_sha256"],
                         "105e0f7a83e154116bd9f0d5eaaf573a896886468c9038f548f5ce7e6377c7ea")
        self.assertEqual(authority["phase_updates"], 180)
        self.assertEqual(authority["cumulative_counters"]["updates"], 228)
        self.assertEqual(authority["inclusive_outer_wall_seconds"], 2952.324712417151)

    def test_rejects_failed_or_different_authority(self):
        mutations = [
            ("status", "failed"),
            ("training_continuation_eligible", False),
            ("phase", "D3"),
            ("run_id", "other-run"),
            ("completed_phase_updates", 252),
            ("completed_local_updates", 72),
            ("runtime_sha256", "0" * 64),
            ("policy_sha256", "0" * 64),
        ]
        for key, value in mutations:
            with self.subTest(key=key):
                receipt = copy.deepcopy(self.receipt)
                receipt[key] = value
                with self.assertRaises(ValueError):
                    tool.validate_authority(receipt, self.registration,
                                            RECEIPT_SHA, REGISTRATION_SHA)

    def test_rejects_registration_parent_substitution_and_receipt_path(self):
        reg = copy.deepcopy(self.registration)
        reg["parent"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "checkpoint digest"):
            tool.validate_authority(self.receipt, reg, RECEIPT_SHA, REGISTRATION_SHA)
        reg = copy.deepcopy(self.registration)
        reg["parent"]["terminal_receipt_path"] = "/tmp/other.json"
        with self.assertRaisesRegex(ValueError, "receipt path"):
            tool.validate_authority(self.receipt, reg, RECEIPT_SHA, REGISTRATION_SHA)


class PerformanceTests(unittest.TestCase):
    def test_actual_252_and_180_rows_and_shuffled_order(self):
        cases = (
            (V2 / "D2-continuation-20261025-r2/development-000252.json",
             532.8125, 3192.3125, 1604.078125),
            (V2 / "D2-gradient-alignment-20261025-r2/development-000180.json",
             585.625, 3502.5625, 1854.46875),
        )
        for path, q1, q4, mean in cases:
            data = json.loads(path.read_text())
            rows = data["evaluation"]["rows"]
            canonical = tool.summarize_performance(rows)
            self.assertEqual((canonical["Q1"], canonical["Q4"], canonical["mean"]),
                             (q1, q4, mean))
            shuffled = list(rows)
            random.Random(73).shuffle(shuffled)
            self.assertEqual(tool.summarize_performance(shuffled), canonical)
            self.assertEqual(tool.summarize_performance(rows, metric="score"),
                             tool.summarize_performance(list(reversed(rows)), metric="score"))

    def test_negative_control_unsorted_slice_is_not_canonical(self):
        rows = [{"alive_frames": value} for value in [900, 1, 800, 2, 700, 3, 600, 4,
                  500, 5, 400, 6, 300, 7, 200, 8, 100, 9, 99, 10, 98, 11, 97, 12,
                  96, 13, 95, 14, 94, 15, 93, 16, 92, 17, 91, 18, 90, 19, 89, 20,
                  88, 21, 87, 22, 86, 23, 85, 24, 84, 25, 83, 26, 82, 27, 81, 28,
                  80, 29, 79, 30, 78, 31, 77, 32]]
        result = tool.summarize_performance(rows)
        shuffled = list(rows)
        random.Random(17).shuffle(shuffled)
        self.assertEqual(tool.summarize_performance(shuffled), result)
        ordered = sorted(row["alive_frames"] for row in rows)
        inclusive_percentile_q1 = (ordered[15] + ordered[16]) / 2
        inclusive_percentile_q4 = (ordered[47] + ordered[48]) / 2
        self.assertNotEqual(result["Q1"], inclusive_percentile_q1)
        self.assertNotEqual(result["Q4"], inclusive_percentile_q4)

    def test_actual_report_designations_and_death_counts(self):
        best_path = V2 / "D2-gradient-alignment-20261025-r2/development-000180.json"
        latest_path = V2 / "D2-continuation-20261025-r2/development-000252.json"
        best = tool.summarize_evaluation(best_path)
        latest = tool.summarize_evaluation(latest_path)
        self.assertEqual((best["summary"]["Q1"], best["summary"]["Q4"],
                          best["summary"]["mean"]),
                         (585.625, 3502.5625, 1854.46875))
        self.assertEqual((latest["summary"]["Q1"], latest["summary"]["Q4"],
                          latest["summary"]["mean"]),
                         (532.8125, 3192.3125, 1604.078125))
        self.assertEqual(latest["deaths"], {
            "normal_enemy": 24, "kamikaze_enemy": 9, "kamikaze_explosion": 3,
            "moving_pattern_rect": 13, "static_pattern_rect": 15,
        })
        report = tool.markdown_report(best_path, latest_path)
        self.assertEqual(report.count("| BEST REFERENCE"), 1)
        self.assertEqual(report.count("| LATEST"), 1)

    def test_actual_252_percentile_negative_control(self):
        path = V2 / "D2-continuation-20261025-r2/development-000252.json"
        rows = json.loads(path.read_text())["evaluation"]["rows"]
        ordered = sorted(row["alive_frames"] for row in rows)
        inclusive_q1 = ordered[15] * 0.25 + ordered[16] * 0.75
        inclusive_q4 = ordered[47] * 0.75 + ordered[48] * 0.25
        canonical = tool.summarize_performance(rows)
        self.assertEqual((inclusive_q1, inclusive_q4), (617.25, 2415.25))
        self.assertEqual((canonical["Q1"], canonical["Q4"]),
                         (532.8125, 3192.3125))
        self.assertNotEqual((inclusive_q1, inclusive_q4),
                            (canonical["Q1"], canonical["Q4"]))

    def test_rejects_bad_cohorts_and_values(self):
        with self.assertRaises(ValueError):
            tool.summarize_performance([{"alive_frames": 3}])
        rows = [{"alive_frames": 1.0} for _ in range(64)]
        rows[0]["alive_frames"] = float("nan")
        with self.assertRaises(ValueError):
            tool.summarize_performance(rows)


if __name__ == "__main__":
    unittest.main()
