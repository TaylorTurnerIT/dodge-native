"""Focused CPU tests for the retained-204 terminal wrapper. Negative controls run in subprocesses."""
import importlib.util
import os
import subprocess
import sys
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("terminal_wrapper", HERE / "wrapper.py")
wrapper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wrapper)
WRAPPER = HERE / "wrapper.py"
ENV = dict(os.environ, PYTHONPYCACHEPREFIX=str(wrapper.PYCACHE_PREFIX))
BASE_PYTHON = Path("/Users/taylor/.local/share/uv/python/cpython-3.12.15-macos-aarch64-none/bin/python3.12")


def observation(**extra):
    base = {"outer_raw_exit": 0, "worker_raw_exit": 0, "first_event": None, "launch_count": 1,
            "outer_limit_seconds": 1800, "outer_inclusive_wall_seconds": 1408.0,
            "max_aggregate_rss_bytes": 1986183168, "aggregate_rss_limit_bytes": 6442450944,
            "mps_limit_bytes": 6442450944, "outer_process_absent": True, "worker_process_absent": True,
            "worker_group_absent": True, "postflight": {"pins": {"failures": []}, "cache_empty_after": True}}
    base.update(extra)
    return base


def execution(**extra):
    base = {"actual_worker_launch_count": 1, "observed_worker_raw_exit": 0, "status": "passed"}
    base.update(extra)
    return base


def worker(**extra):
    base = {"status": "completed", "first_failure": None, "peak_rss_bytes": 3000000000,
            "peak_mps_driver_bytes": 2000000000}
    base.update(extra)
    return base


class TerminalGateTests(unittest.TestCase):
    def test_clean_record_passes(self):
        gates = wrapper.terminal_gates(observation(), execution(), worker())
        self.assertEqual(gates["outer_raw_exit"], 0)

    def test_nonzero_worker_exit_rejected(self):
        with self.assertRaisesRegex(wrapper.WrapperError, "raw exits"):
            wrapper.terminal_gates(observation(worker_raw_exit=1), execution(), worker())

    def test_rss_over_cap_rejected(self):
        with self.assertRaisesRegex(wrapper.WrapperError, "Aggregate RSS"):
            wrapper.terminal_gates(observation(max_aggregate_rss_bytes=6442450945), execution(), worker())

    def test_worker_mps_over_cap_rejected(self):
        with self.assertRaisesRegex(wrapper.WrapperError, "Worker memory"):
            wrapper.terminal_gates(observation(), execution(), worker(peak_mps_driver_bytes=6442450945))

    def test_wall_over_limit_rejected(self):
        with self.assertRaisesRegex(wrapper.WrapperError, "wall"):
            wrapper.terminal_gates(observation(outer_inclusive_wall_seconds=1801.0), execution(), worker())

    def test_source_postflight_failure_rejected(self):
        bad = observation(postflight={"pins": {"failures": ["x"]}, "cache_empty_after": True})
        with self.assertRaisesRegex(wrapper.WrapperError, "postflight"):
            wrapper.terminal_gates(bad, execution(), worker())

    def test_worker_first_failure_rejected(self):
        with self.assertRaisesRegex(wrapper.WrapperError, "Terminal status"):
            wrapper.terminal_gates(observation(), execution(), worker(first_failure={"error": "x"}))


class ProcessAbsenceTests(unittest.TestCase):
    def test_reaped_child_is_absent(self):
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        obs = observation(observer_pid=child.pid, outer_pid=2 ** 22 + 1, outer_process_group=2 ** 22 + 1)
        exe = execution(worker_pid=2 ** 22 + 2, owned_pgid=2 ** 22 + 2)
        self.assertTrue(wrapper.owned_processes_absent(obs, exe))

    def test_live_pid_rejected(self):
        obs = observation(observer_pid=os.getpid(), outer_pid=2 ** 22 + 1, outer_process_group=2 ** 22 + 1)
        with self.assertRaisesRegex(wrapper.WrapperError, "still exists"):
            wrapper.owned_processes_absent(obs, execution(worker_pid=2 ** 22 + 2, owned_pgid=2 ** 22 + 2))


class ImportHardeningTests(unittest.TestCase):
    def test_preloaded_dodge_rejected_before_original_import(self):
        reg = {"runtime_root": str(HERE), "runtime_continuity": {"member_sha256": {}}, "pins": {}}
        calls = []

        def original(_reg):
            calls.append(_reg)
            raise AssertionError("original import ran")

        injected = types.ModuleType("dodge_rl.checkpoints")
        sys.modules["dodge_rl.checkpoints"] = injected
        try:
            strict = wrapper.make_strict_import_runtime(original, reg)
            with self.assertRaisesRegex(wrapper.WrapperError, "Preloaded Dodge modules"):
                strict(reg)
        finally:
            del sys.modules["dodge_rl.checkpoints"]
        self.assertEqual(calls, [])

    def test_registration_mismatch_rejected(self):
        reg = {"runtime_root": str(HERE), "runtime_continuity": {"member_sha256": {}}, "pins": {}}
        strict = wrapper.make_strict_import_runtime(lambda r: None, reg)
        with self.assertRaisesRegex(wrapper.WrapperError, "Runtime registration differs"):
            strict({**reg, "run_id": "other"})

    def test_dependency_origins_bound_to_registered_pins(self):
        reg = wrapper.load_registration()
        origins = wrapper.bind_dependency_origins(reg)
        self.assertEqual(set(origins), {"torch", "numpy"})
        for name, item in origins.items():
            self.assertEqual(item["sha256"], reg["pins"][item["path"]])


class SubprocessNegativeControls(unittest.TestCase):
    def test_wrong_interpreter_fails_before_audit(self):
        if not BASE_PYTHON.exists():
            self.skipTest("base interpreter not present")
        before = set(os.listdir(HERE))
        result = subprocess.run([str(BASE_PYTHON), "-B", str(WRAPPER), "--provisional", "--name", "neg-interp.json"],
                                capture_output=True, text=True, env=ENV, timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Lexical interpreter differs", result.stderr)
        self.assertEqual(set(os.listdir(HERE)), before)

    def test_preloaded_out_of_runtime_dodge_fails_before_decoder(self):
        driver = ("import sys, types, runpy\n"
                  "sys.modules['dodge_rl.checkpoints'] = types.ModuleType('dodge_rl.checkpoints')\n"
                  f"sys.argv = [{str(WRAPPER)!r}, '--provisional', '--name', 'neg-preload.json']\n"
                  f"runpy.run_path({str(WRAPPER)!r}, run_name='__main__')\n")
        before = set(os.listdir(HERE))
        result = subprocess.run([str(wrapper.INTERPRETER), "-B", "-c", driver],
                                capture_output=True, text=True, env=ENV, timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Preloaded Dodge modules rejected", result.stderr)
        self.assertEqual(set(os.listdir(HERE)), before)


if __name__ == "__main__":
    unittest.main()
