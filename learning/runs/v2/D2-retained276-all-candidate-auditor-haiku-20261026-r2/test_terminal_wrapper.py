"""Focused CPU tests for the retained-276 continuation terminal wrapper.

Every nested interpreter runs with -B and inherits PYTHONDONTWRITEBYTECODE=1 plus the registered
PYTHONPYCACHEPREFIX, so no bytecode can land in the registered prefix. Negative controls that reach
the audit fail before any output is written; the output directory listing is compared to prove it.
"""
import ast
import importlib.util
import os
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("terminal_wrapper", HERE / "wrapper.py")
wrapper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wrapper)
WRAPPER = HERE / "wrapper.py"
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(wrapper.PYCACHE_PREFIX))
ENV.pop("PYTHONPATH", None)
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


def listing():
    return set(os.listdir(HERE)), sorted(os.listdir(wrapper.PYCACHE_PREFIX))


class BytecodeBindingTests(unittest.TestCase):
    def test_registered_prefix_is_empty_and_is_the_prep_empty_pycache(self):
        self.assertEqual(wrapper.PYCACHE_PREFIX, wrapper.PREP / "empty-pycache")
        self.assertEqual(list(wrapper.PYCACHE_PREFIX.iterdir()), [])

    def test_inherited_env_flag_is_required(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
            with self.assertRaisesRegex(wrapper.WrapperError, "inherited"):
                wrapper.bind_bytecode()

    def test_wrong_prefix_binding_rejected(self):
        with mock.patch.object(sys, "pycache_prefix", "/tmp/other-prefix"):
            with self.assertRaisesRegex(wrapper.WrapperError, "prefix differs"):
                wrapper.bind_bytecode()

    def test_nested_child_inherits_no_bytecode_writes(self):
        before = listing()
        child = subprocess.run([sys.executable, "-B", "-c",
                                "import sys; print(sys.dont_write_bytecode, sys.flags.dont_write_bytecode)"],
                               capture_output=True, text=True, env=ENV, timeout=120)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(child.stdout.split(), ["True", "1"])
        self.assertEqual(listing(), before)
        self.assertEqual(list(wrapper.PYCACHE_PREFIX.iterdir()), [])


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

    def test_missing_process_absence_flag_rejected(self):
        with self.assertRaisesRegex(wrapper.WrapperError, "process absence"):
            wrapper.terminal_gates(observation(worker_group_absent=False), execution(), worker())

    def test_launch_count_two_rejected(self):
        with self.assertRaisesRegex(wrapper.WrapperError, "launch count"):
            wrapper.terminal_gates(observation(launch_count=2), execution(), worker())


class ProcessAbsenceTests(unittest.TestCase):
    def test_reaped_child_is_absent(self):
        child = subprocess.Popen([sys.executable, "-B", "-c", "pass"], env=ENV)
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

    def test_registration_digest_pinned(self):
        self.assertEqual(wrapper.sha_file(wrapper.REG_PATH), wrapper.REG_SHA)
        reg = wrapper.load_registration()
        self.assertEqual(reg["run_id"], "D2-retained276-continuation-20261026-r2")

    def test_auditor_digest_pinned(self):
        self.assertEqual(wrapper.sha_file(wrapper.AUD_PATH), wrapper.AUD_SHA)

    def test_dependency_origins_bound_to_registered_pins(self):
        reg = wrapper.load_registration()
        origins = wrapper.bind_dependency_origins(reg)
        self.assertEqual(set(origins), {"torch", "numpy"})
        for name, item in origins.items():
            self.assertEqual(item["sha256"], reg["pins"][item["path"]])


class ObserverBindingTests(unittest.TestCase):
    """Full mode is bound to the one registered observer directory and its accepted source."""

    def setUp(self):
        self.aud = wrapper.load_auditor()

    def test_registered_observer_dir_passes(self):
        self.aud.check_observer_dir(self.aud.OBSERVER_DIR)

    def test_other_observer_dir_rejected(self):
        with self.assertRaisesRegex(self.aud.AuditError, "Observer directory differs"):
            self.aud.check_observer_dir(HERE)

    def test_observer_source_digest_drift_rejected(self):
        with mock.patch.object(self.aud, "OBSERVER_SHA", "00" * 32):
            with self.assertRaisesRegex(self.aud.AuditError, "Observer source digest differs"):
                self.aud.check_observer_dir(self.aud.OBSERVER_DIR)

    def test_observer_instantiation_digest_drift_rejected(self):
        with mock.patch.object(self.aud, "stable_json", return_value=({"observer_sha256": "00" * 32}, "x")):
            with self.assertRaisesRegex(self.aud.AuditError, "Observer instantiation digest differs"):
                self.aud.check_observer_dir(self.aud.OBSERVER_DIR)

    def test_wrapper_checks_observer_dir_before_audit_call(self):
        tree = ast.parse(WRAPPER.read_text(encoding="utf-8"))
        run_audit = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_audit")
        calls = {c.func.attr: c.lineno for c in ast.walk(run_audit)
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
        self.assertLess(calls["check_observer_dir"], calls["audit"])


class SubprocessNegativeControls(unittest.TestCase):
    def test_wrong_interpreter_fails_before_audit(self):
        if not BASE_PYTHON.exists():
            self.skipTest("base interpreter not present")
        before = listing()
        result = subprocess.run([str(BASE_PYTHON), "-B", str(WRAPPER), "--provisional", "--name", "neg-interp.json"],
                                capture_output=True, text=True, env=ENV, timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Lexical interpreter differs", result.stderr)
        self.assertEqual(listing(), before)

    def test_preloaded_out_of_runtime_dodge_fails_before_audit(self):
        driver = ("import sys, types, runpy\n"
                  "sys.modules['dodge_rl.checkpoints'] = types.ModuleType('dodge_rl.checkpoints')\n"
                  f"sys.argv = [{str(WRAPPER)!r}, '--provisional', '--name', 'neg-preload.json']\n"
                  f"runpy.run_path({str(WRAPPER)!r}, run_name='__main__')\n")
        before = listing()
        result = subprocess.run([str(wrapper.INTERPRETER), "-B", "-c", driver],
                                capture_output=True, text=True, env=ENV, timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Preloaded Dodge modules rejected", result.stderr)
        self.assertEqual(listing(), before)

    def test_full_mode_refused_on_cli(self):
        before = listing()
        result = subprocess.run([str(wrapper.INTERPRETER), "-B", str(WRAPPER), "--name", "neg-full.json"],
                                capture_output=True, text=True, env=ENV, timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("parent-only", result.stderr)
        self.assertEqual(listing(), before)


if __name__ == "__main__":
    unittest.main()
