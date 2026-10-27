"""CPU-only tests of schedule functions embedded in the actual runner."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import math
from pathlib import Path
import sys
import types
import unittest

import torch

ROOT = Path(__file__).resolve().parent


def load_runner():
    adapter = types.ModuleType("parent_adapter")
    adapter.CHECKPOINT_SHA = "a" * 64
    adapter.RECEIPT_SHA = "b" * 64
    adapter.SCHEMA = "test-schema"
    schema = types.ModuleType("registration_schema")
    schema.RUN_ID = "D2-retained324-linear-lr-20261026-r1"
    sys.modules["parent_adapter"] = adapter
    sys.modules["registration_schema"] = schema
    spec = importlib.util.spec_from_file_location("runner_under_test", ROOT / "runner.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = load_runner()


class RunnerScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def optimizer(self):
        p1 = torch.nn.Parameter(torch.tensor([0.25, -0.5], dtype=torch.float64))
        p2 = torch.nn.Parameter(torch.tensor([0.75], dtype=torch.float64))
        return torch.optim.Adam([{"params": [p1]}, {"params": [p2]}], lr=3e-5)

    def test_actual_runner_origin_init_resume_and_counter_guards(self):
        optimizer = self.optimizer()
        state = runner.initialize_or_restore_schedule(optimizer, 372)
        self.assertEqual(state["completed_schedule_updates"], 0)
        with self.assertRaisesRegex(ValueError, "inherited cumulative update 372"):
            runner.initialize_or_restore_schedule(self.optimizer(), 371)
        with self.assertRaisesRegex(ValueError, "requires saved schedule metadata"):
            runner.initialize_or_restore_schedule(optimizer, 384, scheduled_resume=True)
        for actual in (371, 373, True, 372.0):
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                runner.stage_schedule_update(optimizer, state, 372, 0, actual)
        with self.assertRaisesRegex(ValueError, "Inherited cumulative updates must equal 372"):
            runner.stage_schedule_update(optimizer, state, 371, 1, 372)
        stale = dict(state, completed_schedule_updates=1)
        with self.assertRaisesRegex(ValueError, "disagrees with actual cumulative update"):
            runner.validate_future_scheduled_resume(stale, 372, optimizer)
        with self.assertRaisesRegex(ValueError, "requires saved schedule metadata"):
            runner.validate_future_scheduled_resume(None, 384, optimizer)

    def test_full_sixty_actual_runner_stages_commits_metrics_and_saved_lrs(self):
        optimizer = self.optimizer()
        committed = runner.initialize_or_restore_schedule(optimizer, 372)
        start = {"optimizer": copy.deepcopy(optimizer.state_dict()), "lr_schedule": dict(committed)}
        self.assertEqual(runner.validate_saved_schedule_lr(start, 372), 3e-5)
        for local in range(60):
            actual = 372 + local
            lr, staged = runner.stage_schedule_update(optimizer, committed, 372, local, actual)
            expected = 3e-5 - 2e-5 * local / 59 if local < 59 else 1e-5
            self.assertAlmostEqual(lr, expected, places=15)
            self.assertEqual([group["lr"] for group in optimizer.param_groups], [lr, lr])
            for group in optimizer.param_groups:
                for parameter in group["params"]:
                    parameter.grad = torch.full_like(parameter, 0.125)
            optimizer.step()
            runner.finite_tree({"loss": 0.25, "explained_variance": 0.5})
            committed = runner.commit_schedule_after_success(
                committed, staged, actual, 372, local, checks_passed=True)
            metric = runner.schedule_metric_fields(optimizer, committed, 373 + local)
            self.assertEqual(metric["cumulative_updates"], 373 + local)
            self.assertEqual(metric["optimizer_group_lrs"], [lr, lr])
            self.assertEqual(metric["lr_schedule"]["completed_schedule_updates"], local + 1)
            if local == 11:
                state12 = {"optimizer": copy.deepcopy(optimizer.state_dict()),
                           "lr_schedule": dict(committed)}
                self.assertEqual(runner.validate_saved_schedule_lr(state12, 384), lr)
        self.assertEqual(committed["completed_schedule_updates"], 60)
        state60 = {"optimizer": copy.deepcopy(optimizer.state_dict()),
                   "lr_schedule": dict(committed)}
        self.assertEqual(runner.validate_saved_schedule_lr(state60, 432), 1e-5)
        resumed = self.optimizer()
        resumed.load_state_dict(state60["optimizer"])
        resumed_state = runner.initialize_or_restore_schedule(
            resumed, 432, state60["lr_schedule"], scheduled_resume=True)
        self.assertEqual(resumed_state, committed)
        hold_lr, _ = runner.stage_schedule_update(resumed, resumed_state, 372, 60, 432)
        self.assertEqual(hold_lr, 1e-5)

    def test_failed_ppo_or_diagnostic_never_commits_staged_metadata(self):
        for failure in ("ppo", "finite", "gradient"):
            optimizer = self.optimizer()
            committed = runner.initialize_or_restore_schedule(optimizer, 372)
            before = copy.deepcopy(committed)
            _, staged = runner.stage_schedule_update(optimizer, committed, 372, 0, 372)
            with self.subTest(failure=failure):
                if failure == "ppo":
                    with self.assertRaisesRegex(RuntimeError, "synthetic PPO failure"):
                        raise RuntimeError("synthetic PPO failure")
                elif failure == "finite":
                    with self.assertRaisesRegex(ValueError, "Nonfinite metric"):
                        runner.finite_tree({"loss": math.nan})
                else:
                    with self.assertRaisesRegex(ValueError, "Gradient probe scope"):
                        runner.validate_gradient_alignment({})
                self.assertEqual(committed, before)
                with self.assertRaisesRegex(ValueError, "Cannot commit schedule"):
                    runner.commit_schedule_after_success(committed, staged, 372, 372, 0,
                                                        checks_passed=False)
                self.assertEqual(committed, before)

    def test_runner_source_import_pin_and_commit_order(self):
        source = (ROOT / "runner.py").read_text()
        compile(source, str(ROOT / "runner.py"), "exec")
        helper = (ROOT / "lr_schedule.py").read_bytes()
        self.assertEqual(hashlib.sha256(helper).hexdigest(), runner.LR_SCHEDULE_SHA256)
        self.assertEqual(Path(runner.lr_schedule.__file__).resolve(), (ROOT / "lr_schedule.py").resolve())
        runner.lr_schedule.verify_frozen_manifest(ROOT)
        self.assertEqual(source.count("assert_effective_lr(optimizer, LEARNING_RATE)"), 1)
        tree = ast.parse(source)
        worker = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "worker")
        worker_source = ast.get_source_segment(source, worker)
        identity_init = next(node.lineno for node in ast.walk(worker)
                             if isinstance(node, ast.Assign)
                             and any(isinstance(target, ast.Name) and target.id == "identity"
                                     for target in node.targets))
        for node in ast.walk(worker):
            if not isinstance(node, ast.Assign):
                continue
            if any(isinstance(target, ast.Subscript)
                   and isinstance(target.value, ast.Name) and target.value.id == "identity"
                   for target in node.targets):
                self.assertGreaterEqual(node.lineno, identity_init,
                                        "identity subscript assigned before identity initialization")
        self.assertLess(worker_source.index("ckpt.restore_learner"),
                        worker_source.index("initialize_or_restore_schedule("))
        self.assertLess(worker_source.index("identity = {"), worker_source.index('"lr_schedule": dict(lr_schedule.SCHEDULE_SPEC)'))
        for check in ("finite_tree(value)", 'progress_candidate.get("complete")',
                      'validate_gradient_alignment(value["gradient_alignment_diagnostics"])',
                      "math.isclose(old_ev, direct_ev"):
            self.assertLess(worker_source.index(check),
                            worker_source.index("commit_schedule_after_success("))
        self.assertLess(worker_source.index("commit_schedule_after_success("),
                        worker_source.index('counters["updates"] = update'))


if __name__ == "__main__":
    unittest.main()
