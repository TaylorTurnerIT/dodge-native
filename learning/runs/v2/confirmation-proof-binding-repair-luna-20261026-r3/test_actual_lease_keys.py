"""Check serialization against the real long-campaign ledger key."""
import json
import subprocess
import sys
import tempfile
import time
import unittest

from test_runner import fixture, invoke, write


class ActualLeaseKeyTests(unittest.TestCase):
    def test_active_long_campaign_rejected_before_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            f = fixture(directory)
            ledger = json.loads(f["state"].read_text())
            ledger["active_long_campaign"] = {"run_id": "other-training"}
            write(f["state"], ledger)
            result = invoke(f)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(f["marker"].exists())

    def test_active_long_campaign_appearing_during_run_stops_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            f = fixture(directory, sleep_seconds=3, heartbeat_stale=5)
            command = [sys.executable, str(f["launcher"]), "--registration", str(f["reg"]),
                       "--registration-sha256", f["regsha"], "--worker", str(f["worker"]),
                       "--evaluator", str(f["evaluator"]), "--stage", "benchmark",
                       "--candidate-update", "348", "--cohort", "benchmark_dev64",
                       "--output", str(f["out"])]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 6
                while (not f["log"].exists() or "EVAL_START" not in f["log"].read_text()):
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.02)
                ledger = json.loads(f["state"].read_text())
                ledger["active_long_campaign"] = {"run_id": "other-training"}
                write(f["state"], ledger)
                process.communicate(timeout=12)
                self.assertNotEqual(process.returncode, 0)
                receipt = json.loads(f["out"].with_suffix(".json.outer-receipt.json").read_text())
                self.assertEqual(receipt["stop_reason"], "lease_invalid")
                self.assertTrue(receipt["process_group_absent"])
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=12)
