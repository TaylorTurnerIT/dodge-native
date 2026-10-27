from __future__ import annotations
import sys
sys.dont_write_bytecode = True
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
R6 = ROOT / "learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r6"
LEXICAL = ROOT / "python/.venv/bin/python"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

launcher = load("r5_calibration_launcher_under_test", HERE / "launch_once.py")
probe = load("r5_calibration_probe_under_test", HERE / "probe.py")


class CalibrationCpuTests(unittest.TestCase):
    def test_real_lexical_venv_cpu_child_and_base_isolated_negative(self):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        cache = HERE / "test-bytecode-prefix"
        cache.mkdir(exist_ok=True)
        env["PYTHONPYCACHEPREFIX"] = str(cache)
        script = "import importlib.util,json,sys; print(json.dumps({'prefix':sys.prefix,'torch':importlib.util.find_spec('torch').origin,'numpy':importlib.util.find_spec('numpy').origin}))"
        positive = subprocess.run([str(LEXICAL), "-B", "-c", script], env=env,
                                  capture_output=True, text=True, check=True, timeout=15)
        found = json.loads(positive.stdout)
        self.assertEqual(Path(found["prefix"]).resolve(), LEXICAL.parent.parent.resolve())
        site = Path(found["prefix"]) / "lib/python3.12/site-packages"
        self.assertTrue(Path(found["torch"]).resolve().is_relative_to(site.resolve()))
        self.assertTrue(Path(found["numpy"]).resolve().is_relative_to(site.resolve()))
        self.assertEqual(list(cache.iterdir()), [])
        target = LEXICAL.resolve()
        negative = subprocess.run([str(target), "-I", "-B", "-c",
                                   "import importlib.util; assert importlib.util.find_spec('torch') is None"],
                                  env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(negative.returncode, 0, negative.stderr)

    def test_exact_external_reservation_and_distinct_live_authority(self):
        plan = json.loads((HERE / "calibration-plan.json").read_text())
        plan_sha = "a" * 64
        review = "b" * 64
        manifest = "c" * 64
        reservation = {
            "schema": "current_pair_resource_calibration_parent_reservation_v2",
            "kind": "resource_calibration", "run_id": plan["run_id"],
            "client_request_id": plan["client_request_id"], "plan_sha256": plan_sha,
            "source_pins_sha256": plan["source_pins_sha256"],
            "owner": "parent_registered_calibration_r5",
            "identity": "calibration-r5-ef296efd-45e4-48b1-b2a1-8ec78bb35c31",
            "authorization": "one_shot_resource_probe", "authorized_once": True,
            "cancel_requested": False, "no_concurrent_long_mps_training": True,
            "review_status": "passed", "review_receipt_sha256": review,
            "review_source_manifest_sha256": manifest,
            "state_path": plan["authoritative_state_path"]}
        active = plan["authoritative_state_fields"]["active_inference_diagnostic"] | {
            "plan_sha256": plan_sha, "review_status": "passed",
            "review_receipt_sha256": review, "review_source_manifest_sha256": manifest}
        with __import__("tempfile").TemporaryDirectory(dir=HERE) as tmp:
            state_path = Path(tmp) / "state.json"
            plan["authoritative_state_path"] = str(state_path)
            reservation["state_path"] = str(state_path)
            state_path.write_text(json.dumps({"active_long_campaign": None,
                                              "active_inference_diagnostic": active}))
            digest_value = launcher.check_live_state(plan, plan_sha, reservation)
            self.assertEqual(len(digest_value), 64)
            bad = dict(active, owner="actual_evaluator")
            state_path.write_text(json.dumps({"active_long_campaign": None,
                                              "active_inference_diagnostic": bad}))
            with self.assertRaisesRegex(RuntimeError, "exact active calibration"):
                launcher.check_live_state(plan, plan_sha, reservation)
            state_path.write_text(json.dumps({"active_long_campaign": {"run_id": "training"},
                                              "active_inference_diagnostic": active}))
            with self.assertRaisesRegex(RuntimeError, "active_long_campaign"):
                launcher.check_live_state(plan, plan_sha, reservation)

    def test_fixed_marker_is_per_registration_not_output_path(self):
        import tempfile
        prior = launcher.MARKER
        marker_dir = Path(tempfile.mkdtemp(prefix="test-marker-", dir=HERE))
        try:
            launcher.MARKER = marker_dir / "launch-once.marker"
            launcher.claim_once({"run_id": "r5"}, "plan", "state")
            with self.assertRaises(FileExistsError):
                launcher.claim_once({"run_id": "r5"}, "plan", "state")
        finally:
            launcher.MARKER = prior

    def _spawn_harmless_child(self, code):
        return subprocess.Popen([str(LEXICAL), "-B", "-c", code], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True)

    def _cleanup_with_injected_identity(self, identity, *, identity_reader=None, code="import time; time.sleep(60)"):
        import tempfile
        out = Path(tempfile.mkdtemp(prefix="test-launcher-boundary-", dir=HERE))
        spawned = []
        try:
            launcher.spawn_child_and_capture_identity(
                [str(LEXICAL), "-B", "-c", code], cwd=ROOT, env=os.environ.copy(),
                output=out, outer_deadline=__import__("time").monotonic() + 5.0,
                identity_reader=identity_reader or (lambda _process, _deadline: identity),
                spawn_observer=spawned.append)
        except RuntimeError:
            pass
        else:
            self.fail("expected failed identity control")
        child = spawned[0]
        receipt = json.loads((out / "launcher-result.json").read_text())
        cleanup = json.loads((out / "launcher-cleanup-evidence.json").read_text())
        self.assertIsNotNone(child.poll())
        self.assertEqual(cleanup["direct_child_reaped"], True)
        self.assertEqual(cleanup["absence_status"], "unknown")
        return receipt, cleanup

    def test_launcher_postspawn_boundary_ps_missing_and_malformed_reap_child(self):
        for label, completed in (("missing", subprocess.CompletedProcess([], 1, "", "ps missing")),
                                 ("malformed", subprocess.CompletedProcess([], 0, "bad birth data", ""))):
            with self.subTest(label=label), mock.patch.object(launcher.subprocess, "run", return_value=completed):
                receipt, cleanup = self._cleanup_with_injected_identity(
                    None, identity_reader=launcher.capture_process_identity)
                self.assertEqual(receipt["status"], "failed_postspawn")
                self.assertEqual(cleanup["group_identity_candidate"], False)

    def test_launcher_postspawn_boundary_pgid_mismatch_never_signals_group(self):
        real_killpg = launcher.os.killpg
        with mock.patch.object(launcher.os, "killpg", wraps=real_killpg) as killpg:
            _, cleanup = self._cleanup_with_injected_identity(("birth", 999999))
        killpg.assert_not_called()
        self.assertFalse(cleanup["group_identity_candidate"])

    def test_launcher_cleanup_identity_mismatch_uses_direct_child_only(self):
        import tempfile, time
        child = self._spawn_harmless_child("import time; time.sleep(60)")
        try:
            out = Path(tempfile.mkdtemp(prefix="test-identity-mismatch-", dir=HERE))
            calls = []
            def reader(process, _deadline):
                calls.append(process.pid)
                return ("different-birth", process.pid)
            real_killpg = launcher.os.killpg
            with mock.patch.object(launcher.os, "killpg", wraps=real_killpg) as killpg:
                result = launcher.cleanup_spawned_child(
                    child, out, reason="test_cleanup_identity_mismatch",
                    outer_deadline=time.monotonic() + 5.0,
                    identity=("original-birth", child.pid), identity_reader=reader)
            killpg.assert_not_called()
            self.assertGreaterEqual(len(calls), 1)
            self.assertIsNotNone(child.poll())
            self.assertTrue(result["cleanup"]["group_identity_candidate"])
            self.assertEqual(result["cleanup"]["absence_status"], "unknown")
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=2)

    def test_launcher_cleanup_kills_term_ignoring_harmless_child_within_bound(self):
        import tempfile, time
        import select
        code = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(60)"
        child = self._spawn_harmless_child(code)
        try:
            self.assertTrue(select.select([child.stdout], [], [], 2.0)[0], "child handler did not become ready")
            self.assertEqual(child.stdout.readline().strip(), "ready")
            identity = launcher.capture_process_identity(child, time.monotonic() + 2.0)
            self.assertIsNotNone(identity)
            out = Path(tempfile.mkdtemp(prefix="test-term-ignore-", dir=HERE))
            started = time.monotonic()
            result = launcher.cleanup_spawned_child(
                child, out, reason="test_term_ignore", outer_deadline=started + 5.0,
                identity=identity)
            cleanup = result["cleanup"]
            self.assertTrue(cleanup["term_sent"])
            self.assertTrue(cleanup["kill_sent"])
            self.assertTrue(cleanup["direct_child_reaped"])
            self.assertLessEqual(cleanup["cleanup_seconds"], 5.0)
            self.assertEqual(cleanup["absence_status"], "unknown")
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=2)

    def test_plan_bounds_and_historical_cache_correction(self):
        plan = json.loads((HERE / "calibration-plan.json").read_text())
        self.assertEqual(plan["run_id"], "current-pair-resource-calibration-luna-20261026-r5")
        self.assertEqual(plan["workload"]["active_synthetic_envs"], 64)
        self.assertEqual(plan["workload"]["real_game_episodes"], 0)
        self.assertEqual(plan["workload"]["active_window_seconds_max"], 45)
        self.assertEqual(plan["limits"]["outer_wall_seconds"], 120)
        self.assertEqual(plan["limits"]["work_seconds"], 90)
        self.assertEqual(plan["limits"]["cleanup_seconds"], 10)
        self.assertEqual(len(plan["historical_cache_correction"]["files"]), 2)

    def test_mps_and_resource_measurement_negative_controls(self):
        valid = {"gaps": [0.25] * 19, "after_read_ages": [0.1] * 20,
                 "sample_count": 20, "forward_count": 240, "guard_count": 272,
                 "evaluate_passes": 2, "active_seconds": 30.0,
                 "active_mps_samples": [4096] * 20,
                 "all_session_mps_samples": [0, 0] + [4096] * 20}
        probe.validate_representative_measurements(**valid)
        cases = [
            {"active_mps_samples": []},
            {"active_mps_samples": [4096] * 19},
            {"active_mps_samples": [None] * 20},
            {"active_mps_samples": ["4096"] * 20},
            {"active_mps_samples": [math.nan] * 20},
            {"active_mps_samples": [-1] * 20},
            {"active_mps_samples": [0] * 20},
            {"all_session_mps_samples": [0, 0] + [None] * 20},
            {"guard_count": 208},
            {"active_seconds": 46.0},
        ]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                probe.validate_representative_measurements(**(valid | change))

    def test_mps_startup_zero_is_valid_but_active_zero_and_bad_values_fail(self):
        valid = {"gaps": [0.25] * 19, "after_read_ages": [0.1] * 20,
                 "sample_count": 20, "forward_count": 240, "guard_count": 272,
                 "evaluate_passes": 2, "active_seconds": 30.0,
                 "active_mps_samples": [4096] * 20,
                 "all_session_mps_samples": [0, 0] + [4096] * 20}
        probe.validate_representative_measurements(**valid)
        for samples in ([0] * 20, [None] * 20, [float("nan")] * 20, ["1"] * 20):
            with self.subTest(samples=samples[:2]), self.assertRaises(RuntimeError):
                probe.validate_representative_measurements(**(valid | {
                    "active_mps_samples": list(samples),
                    "all_session_mps_samples": [0, 0] + list(samples)}))

    def test_active_sample_window_excludes_startup_and_records_bounds(self):
        samples = [{"monotonic": value, "mps_driver_bytes": value * 100}
                   for value in (9.9, 10.0, 10.25, 10.5, 11.0, 11.01)]
        active = probe.samples_in_window(samples, 10.0, 11.0)
        self.assertEqual([entry["monotonic"] for entry in active], [10.0, 10.25, 10.5, 11.0])
        self.assertEqual([entry["mps_driver_bytes"] for entry in active], [1000.0, 1025.0, 1050.0, 1100.0])

    def test_guard_formula_arbitrary_pass_counts_and_one_pass_not_repeat_proof(self):
        base = {"gaps": [0.25], "after_read_ages": [0.1], "sample_count": 20,
                "forward_count": 240, "active_seconds": 30.0,
                "active_mps_samples": [1] * 20,
                "all_session_mps_samples": [0, 0] + [1] * 20}
        for passes in (1, 2, 7, 30):
            with self.subTest(passes=passes):
                probe.validate_representative_measurements(**(base | {
                    "evaluate_passes": passes, "guard_count": 136 * passes}))
        self.assertEqual(136, 136 * 1)
        with self.assertRaisesRegex(RuntimeError, "136 per worker.evaluate"):
            probe.validate_representative_measurements(**(base | {
                "evaluate_passes": 1, "guard_count": 208}))

    def test_actual_cpu_two_pass_r6_evaluator_reproduces_272_guards(self):
        runtime = ROOT / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
        sys.path.insert(0, str(runtime))
        frozen_roots = [R6, ROOT / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"]
        cache_files = {p: (digest(p), p.stat().st_mtime_ns)
                       for cache_root in frozen_roots for p in cache_root.rglob("*.pyc")}
        import torch
        from dodge_rl.dev_eval import development_environment_config
        worker = load("r5_actual_r6_worker", R6 / "worker.py")
        class CpuModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.anchor = torch.nn.Parameter(torch.zeros(()), requires_grad=False)
                self.forward_calls = 0
            def forward(self, global_feats, entity_feats, entity_types, entity_mask):
                self.forward_calls += 1
                return type("Output", (), {"logits": torch.zeros((global_feats.shape[0], 9)) + self.anchor})()
        model = CpuModel().eval()
        guards, total_rows = [], 0
        for _ in range(2):
            rows = worker.evaluate(model, checkpoint="best204", mode="argmax", replicate_seed=None,
                                   env_factory=probe.SyntheticEnv,
                                   config_factory=development_environment_config,
                                   expected_control_path=None, check_guard=lambda: guards.append(1),
                                   fixture=False)
            self.assertEqual(len(rows), 64)
            total_rows += len(rows)
        self.assertEqual(total_rows, 128)
        self.assertEqual(model.forward_calls, 16)
        self.assertEqual(len(guards), 272)
        base = {"gaps": [0.25], "after_read_ages": [0.1], "sample_count": 20,
                "forward_count": 240, "evaluate_passes": 2, "active_seconds": 30.0,
                "active_mps_samples": [1] * 20,
                "all_session_mps_samples": [0, 0] + [1] * 20}
        probe.validate_representative_measurements(**(base | {"guard_count": 272}))
        with self.assertRaises(RuntimeError):
            probe.validate_representative_measurements(**(base | {"guard_count": 208}))
        self.assertEqual(cache_files, {p: (digest(p), p.stat().st_mtime_ns) for p in cache_files})

if __name__ == "__main__":
    unittest.main(verbosity=2)
