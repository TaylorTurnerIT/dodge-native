"""Launcher lifecycle contracts with mocked process; never launches a worker."""
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import Mock, patch

import execute_once as e
import runner as r


class Process:
    pid = 987654321
    def poll(self): return 0
    def wait(self, timeout=0): return 0


class LauncherLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent, prefix="launcher-")
        self.root = Path(self.tmp.name)
        self.out = self.root / "learning/runs/v2" / r.RUN_ID
        self.reg = {"schema": "d2_training_v3_continuation_registration_v1", "root": str(self.root),
                    "output": str(self.out), "runtime_root": str(self.root / "runtime"),
                    "interpreter": "/python", "runner_path": "/runner.py", "launcher_path": str(Path(e.__file__).resolve()),
                    "state_path": str(self.root / "state"), "cancel_path": str(self.root / "cancel"),
                    "import_policy": {"pycache_prefix": str(self.root / "cache")}}
        self.regpath = self.root / "registration.json"
        self.regpath.write_text(json.dumps(self.reg))
        self.sha = "a" * 64

    def tearDown(self): self.tmp.cleanup()

    def _run(self, validate=None, *, start=0., work_finished=1601., postflight=True):
        self.out.mkdir(parents=True, exist_ok=True)
        r.save(self.out / "worker-result.json", {"status": "completed"})
        clock_values = iter([start, start, start, work_finished, work_finished, work_finished,
                             work_finished, work_finished, work_finished, work_finished, work_finished])
        def load(*args):
            if not postflight and load.calls:
                raise ValueError("postflight input changed")
            load.calls += 1
            return self.reg, {}
        load.calls = 0
        process = Process()
        with patch.object(r, "load_registration", side_effect=load), patch.object(r, "check_lease"), \
             patch.object(e, "validate_outputs", return_value={"updates_checked": 60} if validate is None else validate), \
             patch.object(e, "group_exists", return_value=False), patch.object(e, "subprocess") as sub:
            sub.Popen.return_value = process
            code = e.execute(self.regpath, self.sha, clock=lambda: next(clock_values, work_finished),
                             popen=sub.Popen, sleep=lambda _: None)
        return code, r.read(self.out / "execution-result.json")

    def test_default_group_absence_is_confirmed_before_output_validation(self):
        calls = []
        original = e.validate_outputs
        with patch.object(r, "load_registration", return_value=(self.reg, {})), patch.object(r, "check_lease"), \
             patch.object(e, "group_exists", side_effect=lambda _: calls.append("group") or False), \
             patch.object(e, "validate_outputs", side_effect=lambda *a: calls.append("validate") or {"updates_checked": 60}), \
             patch.object(e.subprocess, "Popen", return_value=Process()):
            self.out.mkdir(parents=True)
            r.save(self.out / "worker-result.json", {"status": "completed"})
            e.execute(self.regpath, self.sha, clock=lambda: 0., sleep=lambda _: None, popen=Mock(return_value=Process()))
        self.assertEqual(calls, ["group", "validate"])

    def test_second_launch_preserves_every_existing_byte(self):
        self.out.mkdir(parents=True)
        r.save(self.out / "launch-marker.json", {"single_use": True})
        r.save(self.out / "execution-result.json", {"status": "passed"})
        before = {p.name: p.read_bytes() for p in self.out.iterdir()}
        with self.assertRaises(FileExistsError): e.execute(self.regpath, self.sha)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.out.iterdir()})

    def test_postflight_failure_never_signals_reused_proven_absent_group(self):
        self.out.mkdir(parents=True)
        r.save(self.out / "worker-result.json", {"status": "completed"})
        loads = [0]
        def load(*args):
            loads[0] += 1
            if loads[0] == 2: raise ValueError("postflight input changed")
            return self.reg, {}
        with patch.object(r, "load_registration", side_effect=load), patch.object(r, "check_lease"), \
             patch.object(e, "validate_outputs", return_value={"updates_checked": 60}), \
             patch.object(e, "group_exists", side_effect=[False, True]) as exists, \
             patch.object(e.os, "killpg") as kill:
            code = e.execute(self.regpath, self.sha, clock=lambda: 0., sleep=lambda _: None,
                             popen=Mock(return_value=Process()))
        self.assertEqual(code, 1)
        self.assertEqual(exists.call_count, 1)
        kill.assert_not_called()

    def test_late_publication_cancel_fails(self):
        import inspect
        self.out.mkdir(parents=True)
        r.save(self.out / "worker-result.json", {"status": "completed"})
        fired = False
        def clock():
            nonlocal fired
            frame = inspect.currentframe().f_back
            if not fired and frame.f_code.co_name == "execute" and frame.f_locals.get("result", {}).get("status") == "passed":
                fired = True; signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            return 0.
        with patch.object(r, "load_registration", return_value=(self.reg, {})), patch.object(r, "check_lease"), \
             patch.object(e, "group_exists", return_value=False), patch.object(e, "validate_outputs", return_value={"updates_checked": 60}), \
             patch.object(e, "validate_outputs", return_value={"updates_checked": 60}):
            code = e.execute(self.regpath, self.sha, clock=clock, sleep=lambda _: None, popen=Mock(return_value=Process()))
        self.assertTrue(fired)
        self.assertEqual(code, 1)
        self.assertEqual(r.read(self.out / "publication-failure.json")["status"], "failed")

    def test_1601_and_1602_seconds_can_finalize_but_1800_cannot(self):
        for elapsed, expected in ((1601., 0), (1602., 0), (1800., 1)):
            with self.subTest(elapsed=elapsed):
                case_root = self.root / f"case-{int(elapsed)}"
                self.out = case_root / "learning/runs/v2" / r.RUN_ID
                self.reg["root"] = str(case_root)
                self.reg["output"] = str(self.out)
                self.regpath.write_text(json.dumps(self.reg))
                code, result = self._run(work_finished=elapsed)
                self.assertEqual(code, expected)
                if expected:
                    self.assertNotEqual(result["status"], "passed")


if __name__ == "__main__": unittest.main()
