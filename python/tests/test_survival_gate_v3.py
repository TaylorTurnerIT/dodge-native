"""Policy tests without importing the native binding or running a model."""
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("survival_gate", ROOT / "python/dodge_rl/survival_gate.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def summary(stage, alive, score=0):
    return {"stage": stage, "complete": True, "episodes": 64,
            "mean_alive_frames": alive, "mean_score": score}


class SurvivalGateTests(unittest.TestCase):
    def test_score_is_not_a_progress_condition(self):
        for stage, threshold in (("D1", 1500), ("D2", 3060)):
            with self.subTest(stage=stage):
                self.assertTrue(gate.progress_passed(stage, {stage: summary(stage, threshold, 0)}))
                self.assertFalse(gate.progress_passed(stage, {stage: summary(stage, threshold - 0.01, 10000)}))

    def test_both_difficulties_required_before_qualification(self):
        rows = {"D2": summary("D2", 6726.0523), "D3": summary("D3", 4433.0418)}
        self.assertTrue(gate.progress_passed("D3", rows))
        for stage in rows:
            changed = {k: dict(v) for k, v in rows.items()}
            changed[stage]["mean_alive_frames"] -= 0.01
            self.assertFalse(gate.progress_passed("D3", changed))

    def test_invalid_development_evidence_is_rejected(self):
        for field, value in (("complete", False), ("stage", "D1"), ("episodes", 63),
                             ("mean_alive_frames", float("nan")), ("mean_alive_frames", float("inf"))):
            row = summary("D2", 3060)
            row[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                gate.progress_passed("D2", {"D2": row})

    def test_qualification_keeps_inclusive_point_and_strict_lower_bounds(self):
        rows = {k: {"alive_frame_ratio_point": 1.1, "alive_frame_ratio_lower_bound": 1.000001}
                for k in ("D2", "D3")}
        self.assertTrue(gate.qualification_passed(rows))
        rows["D3"]["alive_frame_ratio_lower_bound"] = 1.0
        self.assertFalse(gate.qualification_passed(rows))
        rows["D3"]["alive_frame_ratio_lower_bound"] = float("nan")
        with self.assertRaises(ValueError):
            gate.qualification_passed(rows)

    def test_unknown_phase_and_missing_difficulty_rejected(self):
        with self.assertRaises(ValueError):
            gate.progress_passed("D4", {})
        with self.assertRaises(KeyError):
            gate.qualification_passed({})

    def test_published_policy_matches_predicates(self):
        policy = json.loads((ROOT / "docs/teacher-qualification-v3.json").read_text())
        self.assertEqual(policy["version"], gate.POLICY_VERSION)
        self.assertFalse(policy["development"]["score_required_for_pass"])
        self.assertFalse(policy["qualification"]["score_required_for_pass"])
        for stage in ("D1", "D2"):
            threshold = policy["development"][stage]["mean_alive_frames_min"]
            self.assertTrue(gate.progress_passed(stage, {stage: summary(stage, threshold)}))
            self.assertFalse(gate.progress_passed(stage, {stage: summary(stage, threshold - 1)}))


if __name__ == "__main__":
    unittest.main()
