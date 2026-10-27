"""Exercise actual execute entry validation and prove failure has no side effects."""
import pathlib
import tempfile
import unittest
import execute_once


class ExecuteBoundaryTests(unittest.TestCase):
    def test_parent_failure_precedes_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            output = root / "D2-retained300-continuation-20261026-r1"
            marker = output / "launch-marker.json"
            def reject():
                raise ValueError("wrong selected endpoint")
            with self.assertRaisesRegex(ValueError, "wrong selected endpoint"):
                execute_once.execute(validate_parent=reject)
            self.assertFalse(output.exists())
            self.assertFalse(marker.exists())

    def test_success_stays_preparation_only(self):
        value = execute_once.execute(validate_parent=lambda: {
            "status": "selected_parent_cpu_validation_passed", "worker_started": False})
        self.assertEqual(value["execute_status"], "preparation_only_no_mutation")
        self.assertFalse(value["worker_started"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
