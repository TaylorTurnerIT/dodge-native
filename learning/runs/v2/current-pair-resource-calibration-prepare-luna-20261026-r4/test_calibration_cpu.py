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

launcher = load("r4_calibration_launcher_under_test", HERE / "launch_once.py")
probe = load("r4_calibration_probe_under_test", HERE / "probe.py")


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
            "owner": "parent_registered_calibration_r4",
            "identity": "calibration-r4-5f83a08a-f23d-4ced-8f08-762ca19ee8f2",
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
        prior = launcher.MARKER
        try:
            with __import__("tempfile").TemporaryDirectory(dir=HERE) as tmp:
                launcher.MARKER = Path(tmp) / "launch-once.marker"
                launcher.claim_once({"run_id": "r4"}, "plan", "state")
                with self.assertRaises(FileExistsError):
                    launcher.claim_once({"run_id": "r4"}, "plan", "state")
        finally:
            launcher.MARKER = prior

    def test_plan_bounds_and_historical_cache_correction(self):
        plan = json.loads((HERE / "calibration-plan.json").read_text())
        self.assertEqual(plan["run_id"], "current-pair-resource-calibration-luna-20261026-r4")
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
                 "mps_samples": [4096] * 20}
        probe.validate_representative_measurements(**valid)
        cases = [
            {"mps_samples": []},
            {"mps_samples": [4096] * 19},
            {"mps_samples": [None] * 20},
            {"mps_samples": ["4096"] * 20},
            {"mps_samples": [math.nan] * 20},
            {"mps_samples": [-1] * 20},
            {"mps_samples": [0] * 20},
            {"guard_count": 208},
            {"active_seconds": 46.0},
        ]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                probe.validate_representative_measurements(**(valid | change))

    def test_guard_formula_arbitrary_pass_counts_and_one_pass_not_repeat_proof(self):
        base = {"gaps": [0.25], "after_read_ages": [0.1], "sample_count": 20,
                "forward_count": 240, "active_seconds": 30.0, "mps_samples": [1] * 20}
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
        worker = load("r4_actual_r6_worker", R6 / "worker.py")
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
                "mps_samples": [1] * 20}
        probe.validate_representative_measurements(**(base | {"guard_count": 272}))
        with self.assertRaises(RuntimeError):
            probe.validate_representative_measurements(**(base | {"guard_count": 208}))
        self.assertEqual(cache_files, {p: (digest(p), p.stat().st_mtime_ns) for p in cache_files})

if __name__ == "__main__":
    unittest.main(verbosity=2)
