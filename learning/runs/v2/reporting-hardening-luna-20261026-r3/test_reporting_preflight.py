from __future__ import annotations

import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
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
            ("checkpoint_sha256", "0" * 64),
            ("registration_sha256", "0" * 64),
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

    def test_rejects_missing_or_malformed_pins_on_both_sides(self):
        pairs = (("checkpoint_sha256", "parent.sha256"),
                 ("registration_sha256", "parent.registration_sha256"),
                 ("runtime_sha256", "runtime_sha256"),
                 ("policy_sha256", "policy_sha256"))
        for receipt_key, registration_key in pairs:
            for value in (None, "not-a-digest"):
                with self.subTest(key=receipt_key, side="receipt", value=value):
                    receipt = copy.deepcopy(self.receipt)
                    receipt[receipt_key] = value
                    with self.assertRaisesRegex(ValueError, "SHA256"):
                        tool.validate_authority(receipt, self.registration,
                                                RECEIPT_SHA, REGISTRATION_SHA)
                with self.subTest(key=receipt_key, side="registration", value=value):
                    reg = copy.deepcopy(self.registration)
                    if registration_key.startswith("parent."):
                        reg["parent"][registration_key.split(".", 1)[1]] = value
                    else:
                        reg[registration_key] = value
                    with self.assertRaisesRegex(ValueError, "SHA256"):
                        tool.validate_authority(self.receipt, reg,
                                                RECEIPT_SHA, REGISTRATION_SHA)

    def test_optional_checkpoint_local_timing_can_be_absent(self):
        receipt = copy.deepcopy(self.receipt)
        receipt.pop("checkpoint_recorded_work_wall_seconds")
        receipt.pop("inclusive_iteration_wall_seconds")
        tool.validate_authority(receipt, self.registration, RECEIPT_SHA, REGISTRATION_SHA)


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

    def test_unsorted_input_rows_still_use_sorted_tail_means(self):
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
        self.assertEqual(result["Q1"], sum(ordered[:16]) / 16)
        self.assertEqual(result["Q4"], sum(ordered[-16:]) / 16)

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
        self.assertEqual(report.splitlines()[2],
            "| BEST REFERENCE (phase 180) | checkpoint-000180-candidate.pt | "
            "585.6250 | 3502.5625 | 1854.468750 | 32, 11, 0, 11, 10 | 0 | 0 | 0 |")
        self.assertEqual(report.splitlines()[3],
            "| LATEST (phase 252) | checkpoint-000252-candidate.pt | "
            "532.8125 | 3192.3125 | 1604.078125 | 24, 9, 3, 13, 15 | 0 | 0 | 0 |")

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


class EvaluationValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = V2 / "D2-continuation-20261025-r2/development-000252.json"
        cls.data = json.loads(cls.path.read_text())

    def summarize_mutation(self, mutate):
        data = copy.deepcopy(self.data)
        mutate(data)
        target = Path(__file__).parent / "test-fixtures"
        target.mkdir(exist_ok=True)
        path = target / "mutated-evaluation.json"
        try:
            path.write_text(json.dumps(data))
            return tool.summarize_evaluation(path)
        finally:
            path.unlink(missing_ok=True)
            target.rmdir()

    def test_rejects_duplicate_and_foreign_seeds_and_indices(self):
        for field, value in (("seed", 0xD0000000), ("seed", 0xE0000000),
                             ("episode_index", 0), ("episode_index", 64)):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    self.summarize_mutation(lambda data: data["evaluation"]["rows"][1].__setitem__(field, value))

    def test_rejects_row_aggregate_cause_and_total_mismatch(self):
        changes = (
            lambda e: e["rows"][0].__setitem__("death_cause", "unknown"),
            lambda e: e.__setitem__("deaths", 63),
            lambda e: e.__setitem__("caps", 1),
            lambda e: e["death_causes"].__setitem__("normal_enemy", 25),
            lambda e: e["rows"][0].__setitem__("truncated", True),
        )
        for mutate in changes:
            with self.subTest(change=mutate):
                with self.assertRaises(ValueError):
                    self.summarize_mutation(lambda d: mutate(d["evaluation"]))

    def test_rejects_incomplete_and_wrong_row_count(self):
        for mutate in (lambda d: d["evaluation"].__setitem__("complete", False),
                       lambda d: d["evaluation"]["rows"].pop(),
                       lambda d: d["evaluation"].__setitem__("episodes", 63)):
            with self.subTest(mutate=mutate):
                with self.assertRaises(ValueError):
                    self.summarize_mutation(mutate)

    def test_rejects_invalid_supplied_optional_wall_timing(self):
        receipt = copy.deepcopy(AuthorityTests.receipt)
        receipt["checkpoint_recorded_work_wall_seconds"] = -1
        with self.assertRaisesRegex(ValueError, "Optional checkpoint-local timing"):
            tool.validate_authority(receipt, AuthorityTests.registration,
                                    RECEIPT_SHA, REGISTRATION_SHA)

    def test_reports_valid_caps_and_unknown_causes(self):
        def mutate(data):
            e = data["evaluation"]
            unknown = e["rows"][0]
            cap = e["rows"][1]
            e["death_causes"][unknown["death_cause"]] -= 1
            e["death_causes"]["unknown"] = 1
            e["death_causes"][cap["death_cause"]] -= 1
            unknown["death_cause"] = "unknown"
            cap["death_cause"] = None
            cap["terminated"] = False
            cap["truncated"] = True
            e["deaths"] = 63
            e["caps"] = 1
        record = self.summarize_mutation(mutate)
        self.assertEqual((record["unknown"], record["unavailable"], record["caps"]), (1, 0, 1))

    def test_rejects_stale_embedded_performance_and_mean(self):
        for target, key in (("performance", "alive_frames"),
                            ("mean", "mean_alive_frames")):
            def mutate(data):
                if target == "performance":
                    data["performance"][key]["Q1"] += 1
                else:
                    data["evaluation"][key] += 1
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    self.summarize_mutation(mutate)


class InspectorCliTests(unittest.TestCase):
    def test_digest_mismatch_emits_no_manifest(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            output = Path(tmp) / "manifest.json"
            command = [sys.executable, "-B", str(Path(__file__).with_name("reporting_preflight.py")),
                       "inspect", "--receipt", str(RECEIPT_PATH.resolve()),
                       "--receipt-sha256", "0" * 64,
                       "--registration", str(REGISTRATION_PATH.resolve()),
                       "--registration-sha256", REGISTRATION_SHA,
                       "--output", str(output)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
