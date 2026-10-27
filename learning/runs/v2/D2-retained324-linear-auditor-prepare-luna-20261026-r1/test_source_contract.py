"""Static source boundary controls; no registration, package, lease, or run artifacts read."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

import audit_candidates as auditor

OWN = Path(__file__).resolve().parent


class SourceContract(unittest.TestCase):
    def test_six_candidates_and_schedule_contract_are_in_auditor(self):
        self.assertEqual(auditor.UPDATES, (324, 336, 348, 360, 372, 384))
        self.assertEqual(auditor.RUN_ID, "D2-retained324-linear-lr-20261026-r1")
        self.assertEqual(auditor.CAMPAIGN_COST_BASELINE, 10824.835578584221)
        self.assertEqual(auditor.ORIGINAL_PRODUCING_CAMPAIGN_COST, 9758.365427209174)
        self.assertEqual(auditor.CAMPAIGN_COST_BASELINE_SHA,
                         "d3ddc427f18c8a88c45439452c9efcd966daefe423222e0fa03e97ff4f4fc7d3")
        source = (OWN / "audit_candidates.py").read_text()
        for name in ("validate_entry_state", "validate_resume", "validate_certificate",
                     "validate_metric_rows", "validate_wall", "runtime_origins",
                     "finite_tensors", "validate_entry_against_parent"):
            self.assertIn(f"def {name}(", source)
        self.assertIn("validate_checkpoint_schedule", source)
        self.assertIn("validate_metric_schedule", source)
        self.assertIn("validate_progression", source)
        self.assertNotIn("differs from arm LR", source)

    def test_full_audit_has_no_direct_cli_authority(self):
        source = (OWN / "audit_candidates.py").read_text()
        self.assertIn("full mode is parent-only", source)
        self.assertIn("def full_mode(", (OWN / "wrapper.py").read_text())
        self.assertIn("owned_processes_absent", (OWN / "wrapper.py").read_text())
        self.assertIn("active_long_campaign_exact", (OWN / "wrapper.py").read_text())

    def test_binding_builder_needs_explicit_digests_and_exclusive_output(self):
        source = (OWN / "binding_builder.py").read_text()
        self.assertIn("registration_sha256: str", source)
        self.assertIn("reviewed_manifest_sha256: str", source)
        self.assertIn("observer_sha256: str", source)
        self.assertIn('args.output.open("x")', source)
        self.assertIn("--registration-sha256", source)
        self.assertIn("--reviewed-manifest-sha256", source)
        self.assertFalse((OWN / "audit-binding.json").exists())

    def test_all_python_sources_parse_without_importing_runtime(self):
        for path in sorted(OWN.glob("*.py")):
            with self.subTest(path=path.name):
                ast.parse(path.read_text(), filename=str(path))


if __name__ == "__main__":
    unittest.main()
