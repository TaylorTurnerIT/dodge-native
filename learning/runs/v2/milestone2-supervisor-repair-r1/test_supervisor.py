"""Pure supervisor regressions. Popen, clocks, RSS, imports and native parsing are controlled.

All fixtures/receipts remain under the repair evidence directory. No game or
extension operation occurs, even when exercising the campaign/worker functions.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
import copy
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import signal
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = Path(os.environ.get("SUPERVISOR_UNDER_TEST", ROOT / "learning/scripts/v2_validate_environment.py"))
SPEC = importlib.util.spec_from_file_location("repair_supervisor", SOURCE)
H = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(H)
CASES = Path(os.environ.get("SUPERVISOR_CASES", HERE / "cases-r1"))
CASES.mkdir(parents=True, exist_ok=True)
REAL_PLAN = json.loads((ROOT / "learning/runs/v2/milestone2-validation-harness-r1/campaign-plan.json").read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeProcess:
    pid = 740001  # Synthetic identifier; os.killpg is always mocked.

    def __init__(self, polls=(0,), on_poll=None, waits=None):
        self.polls = list(polls)
        self.on_poll = on_poll
        self.waits = list(waits or [])
        self.returncode = None
        self.poll_count = 0
        self.wait_timeouts = []

    def poll(self):
        self.poll_count += 1
        if self.on_poll:
            self.on_poll(self)
        value = self.polls.pop(0) if len(self.polls) > 1 else self.polls[0]
        if isinstance(value, Exception):
            raise value
        if value is not None:
            self.returncode = value
        return value

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        value = self.waits.pop(0) if self.waits else (self.returncode if self.returncode is not None else 0)
        if isinstance(value, Exception):
            raise value
        self.returncode = value
        self.polls = [value]
        return value


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.directory = CASES / self.id().split(".")[-1]
        self.directory.mkdir(exist_ok=False)
        self.output = self.directory / "synthetic-campaign"
        self.clock = SimpleNamespace(mono=1000.0, utc=datetime(2026, 10, 24, 7, 52, tzinfo=timezone.utc))
        self.plan = copy.deepcopy(REAL_PLAN)
        self.select("trajectory")
        self.plan_path = self.directory / "plan.json"
        self.input = self.directory / "synthetic-input.txt"
        self.extension = self.directory / "synthetic-extension.txt"
        self.binary = self.directory / "synthetic-binary.txt"
        self.build = self.directory / "synthetic-build-receipt.txt"
        for path in (self.input, self.extension, self.binary, self.build):
            path.write_text("SYNTHETIC PURE FIXTURE; NEVER EXECUTED\n")
        self.identity_path = self.directory / "identity.json"
        self.state = self.directory / "lease.json"
        self.inventory_hook = self.save_hook = self.spawn_hook = None
        self.spawned = []
        self.process_factory = lambda name: FakeProcess((None, 0) if name == "native_parity" else (0,))
        self.write_identity()
        self.anchor = digest(self.identity_path)
        self.write_lease(self.anchor)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(H, "PLAN_PATH", self.plan_path))
        self.stack.enter_context(patch.object(H, "STATE", self.state))
        self.stack.enter_context(patch.object(H, "read_plan", side_effect=lambda: self.plan))
        self.stack.enter_context(patch.object(H, "source_inventory", side_effect=self.inventory))
        self.stack.enter_context(patch.object(H, "runtime_identity", side_effect=lambda: self.identity["runtime"]))
        self.stack.enter_context(patch.object(H.time, "monotonic", side_effect=lambda: self.clock.mono))
        self.stack.enter_context(patch.object(H, "utc_now", side_effect=lambda: self.clock.utc))
        self.stack.enter_context(patch.object(H.time, "sleep", side_effect=lambda seconds: None))
        self.popen = self.stack.enter_context(patch.object(H.subprocess, "Popen", side_effect=self.spawn))
        self.signals = self.stack.enter_context(patch.object(H.os, "killpg"))
        self.stack.enter_context(patch.object(H, "current_rss_bytes", return_value=1024))
        self.stack.enter_context(patch.object(H, "peak_rss_bytes", return_value=1024))
        self.parse = self.stack.enter_context(patch.object(H, "parse_native_output", return_value={"status": "passed", "synthetic": True}))
        save = H.save_new
        def saved(path, value):
            save(path, value)
            if self.save_hook:
                self.save_hook(path)
        self.stack.enter_context(patch.object(H, "save_new", side_effect=saved))

    def select(self, *names):
        self.plan["stages"] = [copy.deepcopy(next(s for s in REAL_PLAN["stages"] if s["name"] == name)) for name in names]

    def inventory(self):
        if self.inventory_hook:
            self.inventory_hook()
        return {"synthetic-input.txt": digest(self.input)}

    def write_identity(self):
        self.plan_path.write_text(json.dumps(self.plan))
        self.identity = {"version": "m2_validation_identity_v1", "plan_sha256": digest(self.plan_path),
                         "source_sha256": {"synthetic-input.txt": digest(self.input)},
                         "runtime": {"extension_path": str(self.extension), "extension_sha256": digest(self.extension)},
                         "binary_and_receipt_sha256": {str(p): digest(p) for p in (self.binary, self.build)},
                         "native_test_binary": str(self.binary), "synthetic": True}
        self.identity_path.write_text(json.dumps(self.identity))

    def reselect(self, *names):
        self.select(*names)
        self.write_identity()
        self.anchor = digest(self.identity_path)
        self.write_lease(self.anchor)

    def write_lease(self, anchor):
        self.state.write_text(json.dumps({"active_long_campaign": {"run_id": "pure-test", "identity_sha256": anchor,
            "kind": "M2_validation", "authorization": "frozen_reviewed_M2_campaign"}}))

    def revoke(self):
        self.state.write_text(json.dumps({"active_long_campaign": None}))

    def expire(self):
        self.clock.mono = 2800.0  # Exactly the unchanged 1800-second deadline.

    def cutoff(self):
        self.clock.utc = datetime(2026, 10, 24, 13, tzinfo=timezone.utc)

    def spawn(self, command, **kwargs):
        name = "native_parity" if command[0] == str(self.binary) else command[command.index("--phase") + 1]
        self.spawned.append(name)
        if name != "native_parity":
            (self.output / (name + "-result.json")).write_text(json.dumps({"status": "passed", "identity_sha256": self.anchor, "observed_peak_self_rss_bytes": 1024, "synthetic": True}))
        if self.spawn_hook:
            self.spawn_hook(name, command)
        return self.process_factory(name)

    def check(self, anchor=None):
        # Allows the identical regression suite to demonstrate the old behavior.
        if "expected_identity_hash" in inspect.signature(H.check_identity).parameters:
            return H.check_identity(self.identity_path, anchor or self.anchor)
        return H.check_identity(self.identity_path)

    def campaign(self):
        H.campaign(SimpleNamespace(identity=self.identity_path, output=self.output, run_id="pure-test"))

    def failed(self, pattern):
        with self.assertRaisesRegex((ValueError, RuntimeError), pattern):
            self.campaign()
        result = json.loads((self.output / "campaign-result.json").read_text())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["identity_sha256"], self.anchor)
        self.assertEqual(result["automatic_retries"], 0)
        self.assertFalse(result["resource_limits_relaxed"])
        self.assertTrue((self.output / "artifact-sha256.json").exists())
        return result

    def test_internally_valid_replacement_rejected_by_original_anchor(self):
        self.check()
        self.input.write_text("different but internally consistent input\n")
        self.write_identity()
        replacement = digest(self.identity_path)
        self.assertNotEqual(replacement, self.anchor)
        self.check(replacement)  # The replacement is internally valid.
        with self.assertRaisesRegex(ValueError, "identity document changed"):
            self.check()

    def test_exact_parsed_bytes_hashed_not_a_separate_read(self):
        original = self.identity_path.read_bytes()
        replaced = json.loads(original)
        replaced["unreviewed_metadata"] = True
        raw = json.dumps(replaced).encode()
        original_read = Path.read_bytes
        def read(path):
            return raw if path == self.identity_path else original_read(path)
        with patch.object(Path, "read_bytes", read):
            with self.assertRaisesRegex(ValueError, "identity document changed"):
                self.check()

    def test_replacement_during_identity_verification_rejected(self):
        def replace():
            changed = dict(self.identity, replaced_during_verification=True)
            self.identity_path.write_text(json.dumps(changed))
        self.inventory_hook = replace
        with self.assertRaisesRegex(ValueError, "identity document changed"):
            self.check()

    def test_replacement_after_final_worker_starts_fails_original_anchor(self):
        def replace(name, command):
            self.input.write_text("changed input paired with replaced identity\n")
            self.write_identity()
        self.spawn_hook = replace
        result = self.failed("identity document changed")
        self.assertEqual(self.spawned, ["trajectory"])
        self.assertEqual(result["phases"][-1]["status"], "failed")

    def final_hook(self, action):
        def hook():
            if (self.output / "trajectory-receipt.json").exists():
                action()
        self.inventory_hook = hook

    def test_replacement_during_final_verification_fails(self):
        self.final_hook(lambda: self.identity_path.write_text(json.dumps(dict(self.identity, final_replacement=True))))
        self.failed("identity document changed")

    def test_final_revocation_fails(self):
        self.final_hook(self.revoke)
        self.failed("No parent-owned")

    def test_final_deadline_fails(self):
        self.final_hook(self.expire)
        self.failed("Campaign wall guard expired")

    def test_final_cutoff_fails(self):
        self.final_hook(self.cutoff)
        self.failed("Overnight cutoff reached")

    def test_late_exit_without_poll_iteration_rejected(self):
        self.process_factory = lambda name: FakeProcess((0,), on_poll=lambda process: setattr(self.clock, "mono", 1120.0))
        result = self.failed("trajectory wall guard expired")
        self.assertEqual(result["phases"][0]["rss_samples"], 0)
        self.assertEqual(result["phases"][0]["exit_code"], 0)
        self.assertEqual(result["phases"][0]["status"], "failed")

    def test_late_exit_after_one_poll_rejected(self):
        def hook(process):
            if process.poll_count == 2:
                self.clock.mono = 1120.0
        self.process_factory = lambda name: FakeProcess((None, 0), on_poll=hook)
        self.failed("trajectory wall guard expired")

    def test_prelaunch_command_save_expiry_launches_nothing(self):
        self.save_hook = lambda path: self.expire() if path.name == "trajectory-command.json" else None
        self.failed("Campaign wall guard expired")
        self.popen.assert_not_called()

    def test_prelaunch_cutoff_launches_nothing(self):
        self.save_hook = lambda path: self.cutoff() if path.name == "trajectory-command.json" else None
        self.failed("Overnight cutoff reached")
        self.popen.assert_not_called()

    def test_prelaunch_revocation_launches_nothing(self):
        self.save_hook = lambda path: self.revoke() if path.name == "trajectory-command.json" else None
        self.failed("No parent-owned")
        self.popen.assert_not_called()

    def test_between_stages_deadline_prevents_next_launch(self):
        self.reselect("trajectory", "throughput")
        self.save_hook = lambda path: self.expire() if path.name == "trajectory-receipt.json" else None
        self.failed("Campaign wall guard expired")
        self.assertEqual(self.spawned, ["trajectory"])

    def test_between_stages_cutoff_prevents_next_launch(self):
        self.reselect("trajectory", "throughput")
        self.save_hook = lambda path: self.cutoff() if path.name == "trajectory-receipt.json" else None
        self.failed("Overnight cutoff reached")
        self.assertEqual(self.spawned, ["trajectory"])

    def test_between_stages_revocation_prevents_next_launch(self):
        self.reselect("trajectory", "throughput")
        self.save_hook = lambda path: self.revoke() if path.name == "trajectory-receipt.json" else None
        self.failed("No parent-owned")
        self.assertEqual(self.spawned, ["trajectory"])

    def test_expensive_identity_check_cannot_start_worker_after_deadline(self):
        calls = []
        def consume():
            calls.append(1)
            if len(calls) == 2:
                self.expire()
        self.inventory_hook = consume
        self.failed("Campaign wall guard expired")
        self.popen.assert_not_called()

    def test_expensive_native_parse_rejected_and_receipts_survive(self):
        self.reselect("native_parity", "trajectory")
        self.parse.side_effect = lambda log: (setattr(self.clock, "mono", 1900.0) or {"status": "passed"})
        self.failed("native_parity wall guard expired")
        self.assertEqual(self.spawned, ["native_parity"])
        self.assertEqual(json.loads((self.output / "native_parity-receipt.json").read_text())["status"], "failed")

    def test_parse_exception_preserves_stage_and_overall_receipts(self):
        self.reselect("native_parity")
        self.parse.side_effect = ValueError("deliberate pure parser failure")
        result = self.failed("deliberate pure parser failure")
        self.assertIn("owned_process_stop", result)
        self.assertEqual(json.loads((self.output / "native_parity-receipt.json").read_text())["status"], "failed")

    def test_worker_result_parse_cost_guarded(self):
        original = Path.read_text
        def read(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            if path.name == "trajectory-result.json":
                self.clock.mono = 1120.0
            return value
        with patch.object(Path, "read_text", read):
            self.failed("trajectory wall guard expired")

    def test_final_evidence_hashing_cost_guarded(self):
        original = H.sha256
        def hashed(path):
            value = original(path)
            if path.name == "trajectory-receipt.json":
                self.expire()
            return value
        with patch.object(H, "sha256", side_effect=hashed):
            self.failed("Campaign wall guard expired")

    def test_cleanup_errors_do_not_replace_campaign_failure(self):
        self.process_factory = lambda name: FakeProcess((0,), waits=[7])
        with patch.object(H, "stop_owned", side_effect=RuntimeError("deliberate cleanup failure")):
            result = self.failed("trajectory failed with exit 7")
        self.assertIn("deliberate cleanup failure", result["owned_process_stop"]["errors"][0]["error"])
        receipt = json.loads((self.output / "trajectory-receipt.json").read_text())
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("exit 7", receipt["error"])

    def test_campaign_kill_race_retains_cleanup_stage_overall(self):
        process = FakeProcess((None,), waits=[subprocess.TimeoutExpired("synthetic", 2), 0])
        self.process_factory = lambda name: process
        self.save_hook = lambda path: self.expire() if path.name == "trajectory-launch.json" else None
        self.signals.side_effect = [None, ProcessLookupError("synthetic group exited before KILL")]
        result = self.failed("Campaign wall guard expired")
        self.assertTrue(result["owned_process_stop"]["reaped"])
        self.assertEqual(result["owned_process_stop"]["signal_races"][0]["signal"], "kill")
        self.assertEqual(json.loads((self.output / "trajectory-receipt.json").read_text())["status"], "failed")

    def test_successful_synthetic_stages_use_same_anchor_and_caps(self):
        self.reselect("native_parity", "trajectory", "memory", "throughput")
        self.campaign()
        result = json.loads((self.output / "campaign-result.json").read_text())
        self.assertEqual(result["status"], "passed")
        self.assertEqual([p["wall_limit_seconds"] for p in result["phases"]], [900, 120, 600, 120])
        self.assertEqual(len(self.spawned), 4)
        for phase in result["phases"][1:]:
            command = phase["command"]
            self.assertEqual(command[command.index("--identity-sha256") + 1], self.anchor)
            self.assertEqual(float(command[command.index("--campaign-deadline-monotonic") + 1]), 2800.0)
        self.assertEqual(self.plan["receipt_reserve_seconds"], 600)
        self.assertEqual(self.plan["campaign_wall_seconds"], 1800)
        for name, expected in json.loads((self.output / "artifact-sha256.json").read_text()).items():
            self.assertEqual(digest(self.output / name), expected)
        self.signals.assert_not_called()

    def worker_args(self):
        return SimpleNamespace(identity=self.identity_path, identity_sha256=self.anchor, run_id="pure-test", phase="trajectory", directory=self.directory,
                               campaign_deadline_monotonic=2800.0, phase_started_monotonic=1000.0)

    def run_worker(self, action=None):
        def work(*args):
            if action:
                action()
            return {"status": "passed", "synthetic": True}
        with patch.object(H.importlib, "import_module", return_value=SimpleNamespace(VecDodgeEnv=object())), patch.object(H, "worker_trajectory", side_effect=work):
            H.worker(self.worker_args())

    def test_worker_does_not_reanchor_replaced_identity(self):
        self.input.write_text("new internally valid input\n")
        self.write_identity()
        with self.assertRaisesRegex(ValueError, "identity document changed"):
            self.run_worker()
        self.assertTrue((self.directory / "trajectory-failure.json").exists())

    def test_worker_final_identity_replacement_fails(self):
        def replace():
            self.identity_path.write_text(json.dumps(dict(self.identity, worker_replacement=True)))
        with self.assertRaisesRegex(ValueError, "identity document changed"):
            self.run_worker(replace)
        self.assertFalse((self.directory / "trajectory-result.json").exists())

    def test_worker_final_deadline_fails(self):
        with self.assertRaisesRegex(ValueError, "Campaign wall guard expired"):
            self.run_worker(self.expire)
        self.assertTrue((self.directory / "trajectory-failure.json").exists())

    def test_worker_final_revocation_fails(self):
        with self.assertRaisesRegex(ValueError, "No parent-owned"):
            self.run_worker(self.revoke)

    def test_worker_success_anchor_receipt(self):
        self.run_worker()
        result = json.loads((self.directory / "trajectory-result.json").read_text())
        self.assertEqual(result["identity_sha256"], self.anchor)


class CleanupTests(unittest.TestCase):
    def stop(self, process, signals=None):
        with patch.object(H.os, "killpg", side_effect=signals) as send:
            result = H.stop_owned(process)
        self.assertTrue(all(call.args[0] == process.pid for call in send.call_args_list))
        return result, send

    def test_already_exited_reaped_without_signal(self):
        process = FakeProcess((0,))
        result, send = self.stop(process)
        send.assert_not_called()
        self.assertTrue(result["reaped"])
        self.assertEqual(process.wait_timeouts, [0])

    def test_normal_term_exit_reaped(self):
        result, send = self.stop(FakeProcess((None,), waits=[-signal.SIGTERM]))
        self.assertTrue(result["term_sent"])
        self.assertFalse(result["kill_sent"])
        self.assertTrue(result["reaped"])
        self.assertEqual(send.call_count, 1)

    def test_exit_during_term_signal_reaped(self):
        result, _ = self.stop(FakeProcess((None,), waits=[0]), [ProcessLookupError("TERM race")])
        self.assertTrue(result["reaped"])
        self.assertEqual(result["signal_races"][0]["signal"], "term")

    def test_exit_between_timeout_and_kill_reaped(self):
        process = FakeProcess((None,), waits=[subprocess.TimeoutExpired("synthetic", 2), 0])
        result, send = self.stop(process, [None, ProcessLookupError("KILL race")])
        self.assertTrue(result["reaped"])
        self.assertFalse(result["kill_sent"])
        self.assertEqual(result["signal_races"][0]["signal"], "kill")
        self.assertEqual(process.wait_timeouts, [2, 5])

    def test_exit_observed_after_timeout_skips_kill(self):
        process = FakeProcess((None, 0), waits=[subprocess.TimeoutExpired("synthetic", 2), 0])
        result, send = self.stop(process)
        self.assertTrue(result["reaped"])
        self.assertEqual(send.call_count, 1)

    def test_kill_escalation_reaped(self):
        process = FakeProcess((None,), waits=[subprocess.TimeoutExpired("synthetic", 2), -signal.SIGKILL])
        result, send = self.stop(process)
        self.assertTrue(result["kill_sent"])
        self.assertTrue(result["reaped"])
        self.assertEqual(send.call_args_list[-1].args, (process.pid, signal.SIGKILL))

    def test_signal_and_wait_failures_return_diagnostics(self):
        process = FakeProcess((None,), waits=[RuntimeError("wait failed"), subprocess.TimeoutExpired("synthetic", 5)])
        result, _ = self.stop(process, [PermissionError("TERM denied"), PermissionError("KILL denied")])
        self.assertFalse(result["reaped"])
        self.assertGreaterEqual(len(result["errors"]), 4)
        self.assertEqual(process.wait_timeouts, [2, 5])

    def test_poll_failure_recorded_and_wait_bounded(self):
        process = FakeProcess((RuntimeError("poll failure"), None), waits=[0])
        result, _ = self.stop(process)
        self.assertTrue(result["reaped"])
        self.assertEqual(result["errors"][0]["operation"], "poll")


if __name__ == "__main__":
    unittest.main(verbosity=2)
