"""Test the child-handle assignment window and a surviving same-group child."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from test_runner import fixture, invoke, sha, write


class SignalAssignmentTests(unittest.TestCase):
    def repin(self, f):
        registration = json.loads(f["reg"].read_text())
        for name in ("launcher", "evaluator"):
            registration["source"][name + "_sha256"] = sha(f[name])
        write(f["reg"], registration)
        f["regsha"] = sha(f["reg"])

    def test_signal_inside_popen_before_handle_return(self):
        with tempfile.TemporaryDirectory() as directory:
            f = fixture(directory, sleep_seconds=30, heartbeat_stale=5)
            hook = """
_original_popen = subprocess.Popen
def _signal_before_return(*args, **kwargs):
 child = _original_popen(*args, **kwargs)
 if kwargs.get('start_new_session'):
  os.kill(os.getpid(), signal.SIGTERM)
 return child
subprocess.Popen = _signal_before_return
"""
            source = f["launcher"].read_text()
            f["launcher"].write_text(source.replace("if __name__=='__main__':", hook + "\nif __name__=='__main__':"))
            self.repin(f)
            result = invoke(f, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            receipt = json.loads(f["out"].with_suffix(".json.outer-receipt.json").read_text())
            self.assertIn("supervisor_signal", receipt["stop_reason"])
            self.assertTrue(receipt["process_group_absent"])

    def test_worker_inherits_unblocked_termination_signals(self):
        with tempfile.TemporaryDirectory() as directory:
            f = fixture(directory)
            source = f["evaluator"].read_text()
            source = source.replace(" check_guard()", " import signal\n blocked=signal.pthread_sigmask(signal.SIG_BLOCK,[])\n assert not {signal.SIGTERM,signal.SIGHUP,signal.SIGINT}.intersection(blocked)\n check_guard()", 1)
            f["evaluator"].write_text(source)
            self.repin(f)
            result = invoke(f)
            self.assertEqual(result.returncode, 0, result.stderr)

    def surviving_children_case(self, during_cleanup=False):
        with tempfile.TemporaryDirectory() as directory:
            f = fixture(directory)
            source = f["evaluator"].read_text()
            source = source.replace(" check_guard()", " import subprocess,sys\n child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n print('SURVIVING_CHILD='+str(child.pid),flush=True)\n check_guard()", 1)
            f["evaluator"].write_text(source)
            sentinel = Path(directory) / "worker-exited"
            needle = "  remaining,sample_error=sample_procs(proc.pid) if proc else ([],None);rows=remaining"
            source = f["launcher"].read_text()
            self.assertIn(needle, source)
            if during_cleanup:
                cleanup = " end=min(time.monotonic()+CLEANUP,deadline)"
                self.assertIn(cleanup, source)
                source = source.replace(cleanup, " Path(" + repr(str(sentinel)) + ").write_text('ready')\n time.sleep(0.5)\n" + cleanup)
            else:
                source = source.replace(needle, "  Path(" + repr(str(sentinel)) + ").write_text('ready')\n  time.sleep(5)\n" + needle)
            f["launcher"].write_text(source)
            self.repin(f)
            command = [sys.executable, str(f["launcher"]), "--registration", str(f["reg"]),
                       "--registration-sha256", f["regsha"], "--worker", str(f["worker"]),
                       "--evaluator", str(f["evaluator"]), "--stage", "benchmark",
                       "--candidate-update", "348", "--cohort", "benchmark_dev64", "--output", str(f["out"])]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            children = []
            try:
                deadline = time.monotonic() + 8
                while not sentinel.exists():
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.02)
                children = [int(line.split("=", 1)[1]) for line in f["log"].read_text().splitlines()
                            if line.startswith("SURVIVING_CHILD=")]
                self.assertEqual(len(children), 2)
                for pid in children:
                    os.kill(pid, 0)
                process.send_signal(signal.SIGTERM)
                if during_cleanup:
                    process.send_signal(signal.SIGHUP)
                process.communicate(timeout=12)
                receipt = json.loads(f["out"].with_suffix(".json.outer-receipt.json").read_text())
                self.assertIn("process_group_survived" if during_cleanup else "supervisor_signal", receipt["stop_reason"])
                self.assertTrue(receipt["process_group_absent"])
                for pid in children:
                    with self.assertRaises(ProcessLookupError):
                        os.kill(pid, 0)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=12)
                for pid in children:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_signal_after_worker_exit_cleans_surviving_grandchildren(self):
        self.surviving_children_case()

    def test_repeated_signals_during_orphan_cleanup_preserve_reaping_and_receipt(self):
        self.surviving_children_case(during_cleanup=True)
