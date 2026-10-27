"""Synthetic pure-contract controls. No runtime, checkpoint, ledger, or lease access."""
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("finalize_parent.py")
SPEC = importlib.util.spec_from_file_location("prepared_finalizer", SOURCE)
finalizer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(finalizer)


class FinalizerPureControls(unittest.TestCase):
    def test_exact_lease_guard_and_cancel_guard(self):
        lease = {"run_id": "synthetic", "kind": "campaign"}
        finalizer.validate_parent_guard({"active_long_campaign": lease}, lease, False)
        with self.assertRaises(ValueError):
            finalizer.validate_parent_guard({"active_long_campaign": None}, lease, False)
        with self.assertRaises(ValueError):
            finalizer.validate_parent_guard({"active_long_campaign": lease}, lease, True)

    def test_six_candidate_selection_uses_mean_and_earlier_tie(self):
        candidates = {str(update): {"mean_alive_frames": mean} for update, mean in
                      ((324, 4), (336, 5), (348, 9), (360, 9), (372, 3), (384, 8))}
        self.assertEqual(finalizer.candidate_selection(candidates, 7), "348")
        with self.assertRaises(ValueError):
            finalizer.candidate_selection(candidates, 9)

    def test_cost_adds_parent_anchor_and_observed_outer_only(self):
        self.assertEqual(finalizer.campaign_cost(10824.835578584221, 1131.1351048339857),
                         11955.970683418207)
        with self.assertRaises(ValueError):
            finalizer.campaign_cost(float("nan"), 1)

    def test_schedule_spec_extraction_is_literal_and_hashable(self):
        source = b'SCHEDULE_SPEC = {"origin_cumulative_update": 372, "horizon_updates": 60}\n'
        spec = finalizer.read_json_from_bytes(source)
        self.assertEqual(spec, {"origin_cumulative_update": 372, "horizon_updates": 60})
        self.assertEqual(finalizer.canonical_sha(spec), finalizer.canonical_sha(dict(reversed(list(spec.items())))))

    def test_schedule_metadata_maps_without_resetting_progress(self):
        saved = {"schedule_origin_cumulative_update": 372, "horizon_updates": 60,
                 "completed_schedule_updates": 24,
                 "schedule_spec_sha256": finalizer.SCHEDULE_SPEC_SHA, "optimizer_param_group_count": 2}
        registered = {"origin_cumulative_update": 372, "horizon_updates": 60,
                      "spec_sha256": finalizer.SCHEDULE_SPEC_SHA}
        mapped = finalizer.schedule_field_mapping(saved, registered)
        self.assertEqual(mapped["completed_schedule_updates"], 24)
        with self.assertRaises(ValueError):
            finalizer.schedule_field_mapping({**saved, "completed_schedule_updates": 0}, registered)

    def test_snapshot_comparison_rejects_concurrent_change(self):
        finalizer.validate_snapshot_unchanged(b'{"x":1}', b'{"x":1}')
        with self.assertRaises(ValueError):
            finalizer.validate_snapshot_unchanged(b'{"x":2}', b'{"x":1}')

    def test_import_does_not_finalize(self):
        self.assertNotEqual(finalizer.OWN, finalizer.EXPECTED_OWN)
        self.assertEqual(finalizer.OWN.name, "D2-retained348-linear-finalizer-prepare-parent-20261026-r4")
        self.assertEqual(finalizer.ROOT, Path("/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79"))


if __name__ == "__main__":
    unittest.main()
