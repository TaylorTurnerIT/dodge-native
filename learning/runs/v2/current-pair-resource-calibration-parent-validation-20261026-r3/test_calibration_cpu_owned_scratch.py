import sys
__file__='/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/current-pair-resource-calibration-prepare-luna-20261026-r3/test_calibration_cpu.py'
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

launcher = load("calibration_launcher_under_test", HERE / "launch_once.py")
probe = load("calibration_probe_under_test", HERE / "probe.py")

class CalibrationCpuTests(unittest.TestCase):
    def _main_fixture(self, root, *, bad_interpreter=False):
        root = Path(root)
        plan_path = root / "plan.json"
        pins_path = root / "pins.json"
        reservation_path = root / "reservation.json"
        state_path = root / "state.json"
        output = root / "output"
        probe_path = root / "harmless_probe.py"
        probe_path.write_text("raise SystemExit(0)\n")
        pins_path.write_text(json.dumps({"files": {}, "directories": {}}))
        lexical = Path(sys.executable)
        target = lexical.resolve()
        plan = {"run_id": "fixture-run", "client_request_id": "fixture-client",
                "source_pins_sha256": __import__("hashlib").sha256(pins_path.read_bytes()).hexdigest(),
                "authoritative_state_path": str(state_path),
                "interpreter": {"lexical_path": str(lexical),
                                "resolved_target": str(root / "missing-python" if bad_interpreter else target),
                                "sha256": __import__("hashlib").sha256(target.read_bytes()).hexdigest()}}
        plan_path.write_text(json.dumps(plan))
        plan_sha = __import__("hashlib").sha256(plan_path.read_bytes()).hexdigest()
        reservation = {"schema": "current_pair_resource_calibration_parent_reservation_v1",
                       "run_id": plan["run_id"], "client_request_id": plan["client_request_id"],
                       "plan_sha256": plan_sha, "authorization": "one_shot_resource_probe",
                       "authorized_once": True, "cancel_requested": False,
                       "no_concurrent_long_mps_training": True,
                       "state_path": str(state_path)}
        reservation_path.write_text(json.dumps(reservation))
        state_path.write_text(json.dumps({"active_long_campaign": None,
            "active_inference_diagnostic": {"run_id": plan["run_id"],
                "client_request_id": plan["client_request_id"], "plan_sha256": plan_sha,
                "authorization": "one_shot_resource_probe", "cancel_requested": False}}))
        return plan_path, pins_path, reservation_path, output, probe_path

    def test_main_cli_harmless_child_and_second_output_share_one_fixed_marker(self):
        with tempfile.TemporaryDirectory(dir=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/current-pair-resource-calibration-parent-validation-20261026-r3')) as tmp:
            plan, pins, reservation, output, harmless = self._main_fixture(tmp)
            marker = Path(tmp) / "fixed-marker"
            argv = ["launch_once", "--plan", str(plan), "--pins", str(pins),
                    "--reservation", str(reservation), "--output", str(output)]
            fake_preflight = mock.Mock()
            fake_preflight.run.return_value = {"status": "passed", "mps_operations": 0}
            with mock.patch.object(launcher, "MARKER", marker), \
                 mock.patch.object(launcher, "PROBE", harmless), \
                 mock.patch.object(launcher.importlib.util, "spec_from_file_location",
                                   return_value=mock.Mock(loader=mock.Mock(exec_module=lambda module:
                                       setattr(module, "run", fake_preflight.run)))), \
                 mock.patch.object(sys, "argv", argv):
                self.assertEqual(launcher.main(), 0)
                self.assertTrue((output / "launcher-result.json").is_file())
                argv[-1] = str(Path(tmp) / "second-output")
                with self.assertRaises(FileExistsError):
                    launcher.main()

    def test_main_cli_missing_interpreter_fails_before_fixed_marker(self):
        with tempfile.TemporaryDirectory(dir=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/current-pair-resource-calibration-parent-validation-20261026-r3')) as tmp:
            plan, pins, reservation, output, harmless = self._main_fixture(tmp, bad_interpreter=True)
            marker = Path(tmp) / "fixed-marker"
            argv = ["launch_once", "--plan", str(plan), "--pins", str(pins),
                    "--reservation", str(reservation), "--output", str(output)]
            fake_preflight = mock.Mock()
            fake_preflight.run.return_value = {"status": "passed", "mps_operations": 0}
            with mock.patch.object(launcher, "MARKER", marker), \
                 mock.patch.object(launcher, "PROBE", harmless), \
                 mock.patch.object(launcher.importlib.util, "spec_from_file_location",
                                   return_value=mock.Mock(loader=mock.Mock(exec_module=lambda module:
                                       setattr(module, "run", fake_preflight.run)))), \
                 mock.patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(RuntimeError, "interpreter target differs"):
                    launcher.main()
            self.assertFalse(marker.exists())

    def test_live_authority_requires_exact_parent_lease_and_fails_closed(self):
        plan = {"authoritative_state_path": "", "run_id": "run", "client_request_id": "client"}
        with tempfile.TemporaryDirectory(dir=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/current-pair-resource-calibration-parent-validation-20261026-r3')) as tmp:
            state_path = Path(tmp) / "state.json"
            plan["authoritative_state_path"] = str(state_path)
            active = {"run_id": "run", "client_request_id": "client", "plan_sha256": "pin",
                      "authorization": "one_shot_resource_probe", "cancel_requested": False}
            state = {"active_long_campaign": None, "active_inference_diagnostic": active}
            state_path.write_text(json.dumps(state))
            digest = launcher.check_live_state(plan, "pin")
            self.assertEqual(len(digest), 64)
            active["plan_sha256"] = "other"
            state_path.write_text(json.dumps(state))
            with self.assertRaisesRegex(RuntimeError, "exact active calibration"):
                probe.check_live_state(plan, "pin")
            state["active_long_campaign"] = {"run_id": "training"}
            state_path.write_text(json.dumps(state))
            with self.assertRaisesRegex(RuntimeError, "active_long_campaign"):
                launcher.check_live_state(plan, "pin")

    def test_fixed_marker_blocks_second_claim_across_output_locations(self):
        with tempfile.TemporaryDirectory(dir=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/current-pair-resource-calibration-parent-validation-20261026-r3')) as tmp:
            marker = Path(tmp) / "owned-calibration" / "launch-once.marker"
            marker.parent.mkdir()
            launcher.MARKER = marker
            plan = {"run_id": "run"}
            launcher.claim_once(plan, "plan", "state")
            with self.assertRaises(FileExistsError):
                launcher.claim_once(plan, "plan", "state")
            self.assertEqual(marker.parent, Path(tmp) / "owned-calibration")

    def test_cli_pre_spawn_reservation_failure_does_not_consume_marker(self):
        with tempfile.TemporaryDirectory(dir=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/current-pair-resource-calibration-parent-validation-20261026-r3')) as tmp:
            outputs = [Path(tmp) / "out-a", Path(tmp) / "nested" / "out-b"]
            for output in outputs:
                result = subprocess.run([
                    sys.executable, str(HERE / "launch_once.py"),
                    "--plan", str(HERE / "calibration-plan.json"),
                    "--pins", str(HERE / "source-pins.json"),
                    "--reservation", str(Path(tmp) / "missing-parent-reservation.json"),
                    "--output", str(output)], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("reservation is missing", result.stderr)
                self.assertFalse((HERE / "launch-once.marker").exists())

    def test_fixture_scope_and_frozen_plan_gates_are_explicit(self):
        plan = json.loads((HERE / "calibration-plan.json").read_text())
        self.assertEqual(plan["run_id"], "current-pair-resource-calibration-luna-20261026-r3")
        self.assertEqual(plan["workload"]["active_synthetic_envs"], 64)
        self.assertEqual(plan["workload"]["real_game_episodes"], 0)
        self.assertGreaterEqual(plan["success_gates"]["complete_resource_samples_min"], 20)
        self.assertTrue(plan["success_gates"]["resource_interarrival_gaps_nonempty"])
        self.assertEqual(plan["limits"]["outer_wall_seconds"], 120)
        self.assertEqual(plan["limits"]["cleanup_seconds"], 10)

    def test_probe_measurement_gates_reject_empty_and_incomplete_data(self):
        valid = {"gaps": [0.25], "after_read_ages": [0.1], "sample_count": 20,
                 "forward_count": 240, "guard_count": 64 + 30 * 72,
                 "evaluate_passes": 30, "active_seconds": 30.0}
        probe.validate_representative_measurements(**valid)
        for key, value in (("gaps", []), ("after_read_ages", []), ("sample_count", 0),
                           ("forward_count", 8), ("guard_count", 64),
                           ("active_seconds", 1.0)):
            failed = dict(valid)
            failed[key] = value
            with self.subTest(gate=key), self.assertRaises(RuntimeError):
                probe.validate_representative_measurements(**failed)

    def test_r6_evaluator_runs_64_synthetic_episodes_on_cpu(self):
        import torch
        root = HERE.parents[3]
        runtime = root / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
        sys.path.insert(0, str(runtime))
        r6 = load("_r3_cpu_r6_worker", root / "learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r6/worker.py")
        from dodge_rl.dev_eval import development_environment_config
        class CpuModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.anchor = torch.nn.Parameter(torch.zeros(()), requires_grad=False)
                self.forward_calls = 0
            def forward(self, global_feats, entity_feats, entity_types, entity_mask):
                self.forward_calls += 1
                return type("Output", (), {"logits": torch.zeros((global_feats.shape[0], 9)) + self.anchor})()
        model = CpuModel().eval()
        guards, rows = [], []
        completed = r6.evaluate(model, checkpoint="best204", mode="argmax", replicate_seed=None,
                                env_factory=probe.SyntheticEnv,
                                config_factory=development_environment_config,
                                expected_control_path=None, check_guard=lambda: guards.append(1),
                                episode_sink=rows.append, fixture=False)
        self.assertEqual(len(completed), 64)
        self.assertEqual(len(rows), 64)
        self.assertEqual(model.forward_calls, 8)
        self.assertEqual(len(guards), 64 + 9 * 8)
        self.assertTrue(all(row["terminated"] is False and row["truncated"] is True for row in rows))

if __name__ == "__main__":
    unittest.main(verbosity=2)
