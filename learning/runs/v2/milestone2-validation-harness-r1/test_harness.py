"""Pure receipt/guard tests. These do not import or execute the native binding."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SPEC = importlib.util.spec_from_file_location("v2_validation_harness", ROOT / "learning/scripts/v2_validate_environment.py")
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


def synthetic_log(rows):
    """Serialize independently assembled copies of retained baseline facts."""
    output = ["SYNTHETIC CHECKER FIXTURE ONLY; NO NATIVE EXECUTION"]
    total_frames = 0
    for difficulty, group in rows.items():
        pattern_frames = {}
        raw = alive = score = caps = 0
        for row in group:
            value = {"difficulty": difficulty, "episode_index": row["episode_index"], "seed": row["seed"], "score_raw_fixed": row["scores"]["final_score_raw_fixed"], "raw_frames": row["gameplay_native_frames"], "alive_frames": row["raw_survival_frames"], "terminated": row["death"], "truncated": row["cap_truncation"], "death_events": row["frame_event_counts_enemy_spawn_collision_death_pattern_active_terminal"][2], "full_state_hash": row["final_state_hash"]}
            value["objective_return"] = value["score_raw_fixed"] / 65536 + value["alive_frames"] / 100 - 5 * value["terminated"]
            output.append("V2_FULL_PARITY_EPISODE " + json.dumps(value))
            raw += value["raw_frames"]
            alive += value["alive_frames"]
            score += value["score_raw_fixed"]
            caps += value["truncated"]
            for pattern in row["counts"]["pattern_frames"]:
                pattern_frames[pattern["id"]] = pattern_frames.get(pattern["id"], 0) + pattern["frames"]
        output += ["V2_FULL_PARITY_PATTERN " + json.dumps({"difficulty": difficulty, "id": key, "frames": value}) for key, value in pattern_frames.items()]
        output.append("V2_FULL_PARITY_DIFFICULTY " + json.dumps({"difficulty": difficulty, "episodes": 1000, "raw_frames_per_path": raw, "alive_frames": alive, "score_sum_raw_fixed": score, "caps": caps, "pattern_ids": len(pattern_frames)}))
        total_frames += raw
    output.append("V2_FULL_PARITY_TOTAL " + json.dumps({"episodes": 2000, "raw_frames_per_path": total_frames, "wall_seconds": 1.0}))
    return "\n".join(output) + "\n"


class PureGuardTests(unittest.TestCase):
    def test_cutoff_full_budget_inclusive_boundary(self):
        plan = HARNESS.read_plan()
        HARNESS.assert_cutoff_budget(datetime(2026, 10, 24, 12, 20, tzinfo=timezone.utc), plan)
        with self.assertRaisesRegex(ValueError, "does not fit cutoff"):
            HARNESS.assert_cutoff_budget(datetime(2026, 10, 24, 12, 20, 0, 1, tzinfo=timezone.utc), plan)

    def test_no_overwrite_evidence(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            path = Path(directory) / "receipt.json"
            HARNESS.save_new(path, {"first": 1})
            with self.assertRaises(FileExistsError):
                HARNESS.save_new(path, {"second": 2})
            self.assertEqual(json.loads(path.read_text()), {"first": 1})

    def test_plateau_accepts_stable_allocator_and_rejects_growth(self):
        stable = [{"measured_step_calls": index * 1000, "rss_bytes": 100_000_000 + index % 3 * 1024} for index in range(101)]
        self.assertTrue(HARNESS.memory_plateau(stable)["passed"])
        growing = [{"measured_step_calls": index * 1000, "rss_bytes": 100_000_000 + index * 1024**2} for index in range(101)]
        self.assertFalse(HARNESS.memory_plateau(growing)["passed"])

    def test_plateau_rejects_missing_reordered_and_warmup_only_samples(self):
        complete = [{"measured_step_calls": index * 1000, "rss_bytes": 100_000_000} for index in range(101)]
        for samples in (complete[:-1], list(reversed(complete)), complete[:1]):
            with self.assertRaises(ValueError):
                HARNESS.memory_plateau(samples)

    def test_exact_lease_required(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            state = Path(directory) / "state.json"
            with patch.object(HARNESS, "STATE", state):
                state.write_text(json.dumps({"active_long_campaign": None}))
                with self.assertRaisesRegex(ValueError, "No parent-owned"):
                    HARNESS.assert_lease("run", "hash")
                lease = {"run_id": "run", "identity_sha256": "hash", "kind": "M2_validation", "authorization": "frozen_reviewed_M2_campaign"}
                state.write_text(json.dumps({"active_long_campaign": lease}))
                self.assertEqual(HARNESS.assert_lease("run", "hash"), lease)
                for run_id, identity in (("different", "hash"), ("run", "different")):
                    with self.assertRaisesRegex(ValueError, "identity mismatch"):
                        HARNESS.assert_lease(run_id, identity)


class PureNativeReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = HARNESS.load_baselines()
        cls.valid_log = synthetic_log(cls.rows)

    def parse_text(self, text):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            log = Path(directory) / "synthetic-checker-fixture.log"
            log.write_text(text)
            return HARNESS.parse_native_output(log)

    def test_all_2000_rows_and_censored_baselines_recomputed(self):
        result = self.parse_text(self.valid_log)
        self.assertEqual(result["episodes"], 2000)
        self.assertEqual(result["difficulties"]["D2"]["score_mean"], 100.1075)
        self.assertEqual(result["difficulties"]["D3"]["score_mean"], 88.633)
        self.assertEqual(result["difficulties"]["D2"]["caps"], 15)
        self.assertEqual(result["difficulties"]["D3"]["caps"], 2)

    def test_duplicate_missing_and_wrong_score_rejected(self):
        lines = self.valid_log.splitlines()
        first = next(line for line in lines if line.startswith("V2_FULL_PARITY_EPISODE "))
        for log in (self.valid_log + first + "\n", self.valid_log.replace(first + "\n", "", 1)):
            with self.assertRaises(ValueError):
                self.parse_text(log)
        data = json.loads(first.split(" ", 1)[1])
        data["score_raw_fixed"] += 1
        with self.assertRaisesRegex(ValueError, "differs from original"):
            self.parse_text(self.valid_log.replace(first, "V2_FULL_PARITY_EPISODE " + json.dumps(data), 1))

    def test_wrong_survival_cap_death_count_and_fingerprint_rejected(self):
        first = next(line for line in self.valid_log.splitlines() if line.startswith("V2_FULL_PARITY_EPISODE "))
        original = json.loads(first.split(" ", 1)[1])
        for key in ("alive_frames", "truncated", "death_events", "full_state_hash"):
            changed = original.copy()
            changed[key] = not original[key] if key == "truncated" else original[key] + 1
            with self.assertRaisesRegex(ValueError, "differs from original"):
                self.parse_text(self.valid_log.replace(first, "V2_FULL_PARITY_EPISODE " + json.dumps(changed), 1))

    def test_missing_pattern_coverage_and_wrong_totals_rejected(self):
        pattern = next(line for line in self.valid_log.splitlines() if line.startswith("V2_FULL_PARITY_PATTERN "))
        with self.assertRaisesRegex(ValueError, "pattern coverage differs"):
            self.parse_text(self.valid_log.replace(pattern + "\n", "", 1))
        total = next(line for line in self.valid_log.splitlines() if line.startswith("V2_FULL_PARITY_TOTAL "))
        bad = json.loads(total.split(" ", 1)[1])
        bad["raw_frames_per_path"] += 1
        with self.assertRaisesRegex(ValueError, "total mismatch"):
            self.parse_text(self.valid_log.replace(total, "V2_FULL_PARITY_TOTAL " + json.dumps(bad), 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
