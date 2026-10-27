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
        self.assertEqual(auditor.REG_PATH.name, "registration-final-r2.json")
        self.assertIn("validate_actual_package", (OWN / "audit_candidates.py").read_text())
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

    def test_actual_registration_and_source_manifest_contract(self):
        import json
        reg = json.loads(auditor.REG_PATH.read_bytes())
        auditor.validate_actual_package(reg, auditor.REGISTRATION_SHA256)
        self.assertEqual(reg["runtime_sha256"], "2cf10e9f056f41b39dc17845192e9adf553a5f699546d4f5dcea764a23e36b31")
        self.assertEqual(reg["latest_resource_cost_anchor"]["sha256"], auditor.CAMPAIGN_COST_BASELINE_SHA)

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
        self.assertIn("frozen_sources.get(name)", source)
        self.assertIn('"observer_instantiation"', source)
        self.assertFalse((OWN / "audit-binding.json").exists())

    def test_parent_binding_digest_is_required_and_recorded(self):
        wrapper = (OWN / "wrapper.py").read_text()
        auditor_source = (OWN / "audit_candidates.py").read_text()
        self.assertIn('parser.add_argument("--binding-sha256", required=True', wrapper)
        self.assertIn('parser.add_argument("--binding-sha256", required=True', auditor_source)
        self.assertIn('"binding_sha256": BINDING_SHA', auditor_source)
        self.assertIn('"binding_sha256": BINDING_SHA', wrapper)
        self.assertIn('terminal_record_sha256', auditor_source)
        self.assertIn('audit.pop("_terminal_records")', wrapper)

    def test_bootstrap_readiness_stops_before_candidate_audit(self):
        source = (OWN / "bootstrap_readiness.py").read_text()
        self.assertIn("auditor.load_frozen(", source)
        self.assertNotIn("auditor.audit(", source)
        self.assertIn('"checkpoint_deserialization": False', source)

    def test_all_python_sources_parse_without_importing_runtime(self):
        for path in sorted(OWN.glob("*.py")):
            with self.subTest(path=path.name):
                ast.parse(path.read_text(), filename=str(path))


if __name__ == "__main__":
    unittest.main()
