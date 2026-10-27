"""Exercise the worker entry point with the real JSON fixture and fake inference."""
import importlib.util
import json
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "expanded-runner-integrated-parent-20261026-r5"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixtures = load("heartbeat_entry_fixtures", BASE / "test_runner.py")


class LifecycleTests(unittest.TestCase):
    def run_fixture(self, fail=False):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            f = fixtures.fixture(directory, sleep_seconds=0.3, heartbeat_stale=0.1)
            registration = json.loads(f["reg"].read_text())
            worker_source = (HERE / "worker.py").read_text()
            worker_source = worker_source.replace(
                "022d41dde9bace0b4f4c4c06b9b4ed007bc2c60013cd98734086e587d7bb997e",
                registration["runtime"]["member_sha256"]["dodge_rl/_native.cpython-312-darwin.so"])
            worker_source = worker_source.replace(
                "/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/D2-retained324-linear-lr-20261026-r1/development-000348.jsonl",
                registration["benchmark_reference"]["certificate_path"])
            worker_source = worker_source.replace(
                "d6e914345dcc955f678db41eb08d9f20af8e77490652f8d25f7ee09550a63a03",
                registration["benchmark_reference"]["certificate_sha256"])
            f["worker"].write_text(worker_source)
            if fail:
                f["evaluator"].write_text(f["evaluator"].read_text().replace(
                    "time.sleep(0.3)", "time.sleep(0.3)\n raise RuntimeError('injected inference failure')"))
            registration["limits"]["guard_poll_seconds"] = 0.02
            for name in ("worker", "evaluator"):
                registration["source"][name + "_sha256"] = fixtures.sha(f[name])
            fixtures.write(f["reg"], registration)
            pin = fixtures.sha(f["reg"])
            fixtures.write(f["marker"], {"run_id": registration["run_id"], "registration_sha256": pin})
            heartbeat = f["out"].parent / "worker-heartbeat.json"
            module = load("entry_lifecycle_worker", f["worker"])
            original_prefix = sys.pycache_prefix
            original_bytecode = sys.dont_write_bytecode
            try:
                arguments = (f["reg"], f["evaluator"], f["out"], "benchmark", 348,
                             "benchmark_dev64", pin, time.monotonic() + 10, heartbeat)
                if fail:
                    with self.assertRaisesRegex(RuntimeError, "injected inference failure"):
                        module.run(*arguments)
                    self.assertFalse(f["out"].exists())
                else:
                    result = module.run(*arguments)
                    self.assertTrue(result["complete"])
                    self.assertTrue(f["out"].exists())
                    self.assertGreater(json.loads(heartbeat.read_text())["sequence"], 4)
                self.assertFalse(any(t.name == "worker-heartbeat-sampler" for t in threading.enumerate()))
            finally:
                sys.pycache_prefix = original_prefix
                sys.dont_write_bytecode = original_bytecode

    def test_full_entry_point_survives_inference_without_guard_callbacks(self):
        self.run_fixture()

    def test_inference_exception_stops_sampler_and_preserves_no_success_bundle(self):
        self.run_fixture(fail=True)

    def test_partially_imported_torch_is_startup_without_accessing_backends(self):
        module = load("partial_torch_worker", HERE / "worker.py")
        prior = sys.modules.get("torch")
        sys.modules["torch"] = types.SimpleNamespace(__spec__=types.SimpleNamespace(_initializing=True))
        try:
            self.assertEqual(module.driver_memory_status("mps"), (0, "startup", False))
        finally:
            if prior is None:
                sys.modules.pop("torch", None)
            else:
                sys.modules["torch"] = prior
