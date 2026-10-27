"""Read-only checks against byte-pinned JSON/source evidence. No checkpoint loading or publication."""
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("finalize_parent.py")
SPEC = importlib.util.spec_from_file_location("read_only_finalizer_evidence", SOURCE)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class RealEvidenceControls(unittest.TestCase):
    def test_real_schedule_named_constants_match_frozen_audit(self):
        reg = module.read(module.REG_PATH)
        worker = module.read_json_from_bytes(Path(reg["lr_schedule_path"]).read_bytes())
        auditor = module.read_json_from_bytes((module.AUDITOR / "lr_schedule.py").read_bytes())
        self.assertEqual(worker, auditor)
        self.assertEqual(module.canonical_sha(worker), module.SCHEDULE_SPEC_SHA)
        self.assertEqual(worker, module.read(module.FULL_PATH)["audit"]["schedule_spec"])

    def test_unresolved_schedule_name_or_executable_expression_rejected(self):
        for source in (b'SCHEDULE_SPEC = {"x": UNKNOWN}\n',
                       b'SCHEDULE_SPEC = {"x": open("forbidden")}\n'):
            with self.assertRaises(ValueError):
                module.read_json_from_bytes(source)

    def test_real_registered_terminal_evidence_and_all_pins_read_only(self):
        module._verify_registered_evidence(
            module.read(module.REG_PATH), module.read(module.FULL_PATH), module.read(module.OBS_PATH),
            module.read(module.RUN / "execution-result.json"), module.read(module.RUN / "worker-result.json"))


if __name__ == "__main__":
    unittest.main()
