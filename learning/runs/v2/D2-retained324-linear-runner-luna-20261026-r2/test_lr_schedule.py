"""Synthetic CPU tests; no production checkpoint or training access."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import unittest

import torch

from schedule import (END_LR, HORIZON_UPDATES, ORIGIN_CUMULATIVE_UPDATE,
    SCHEDULE_SPEC, SCHEDULE_SPEC_SHA256, apply_next_update_lr,
    learning_rate_for_cumulative_update, new_schedule_state,
    validate_schedule_state, verify_frozen_manifest)


class ScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def optimizer(self, two_groups=False):
        first = torch.nn.Parameter(torch.tensor([0.25, -0.5], dtype=torch.float64))
        second = torch.nn.Parameter(torch.tensor([0.75], dtype=torch.float64))
        params = [[first], [second]] if two_groups else [[first, second]]
        return torch.optim.Adam([{"params": group} for group in params], lr=3e-5)

    def fresh(self, optimizer, actual=372):
        return new_schedule_state(optimizer, actual)

    def step_schedule(self, optimizer, state, actual):
        lr, staged = apply_next_update_lr(optimizer, state, actual)
        for group in optimizer.param_groups:
            for parameter in group["params"]:
                parameter.grad = torch.full_like(parameter, 0.1)
        optimizer.step()
        return staged, lr

    def test_full_sixty_update_sequence_and_hold_resume(self):
        opt = self.optimizer()
        state = self.fresh(opt)
        for completed in range(60):
            state, lr = self.step_schedule(opt, state, 372 + completed)
            expected = 3e-5 - 2e-5 * completed / 59 if completed < 60 else 1e-5
            self.assertAlmostEqual(lr, expected, places=15)
        self.assertEqual(state["completed_schedule_updates"], 60)
        state, lr = self.step_schedule(opt, state, 432)
        self.assertEqual(lr, END_LR)
        self.assertEqual(state["completed_schedule_updates"], 61)
        saved_optimizer, saved_state = copy.deepcopy(opt.state_dict()), copy.deepcopy(state)
        resumed = self.optimizer()
        resumed.load_state_dict(saved_optimizer)
        state = validate_schedule_state(saved_state, resumed)
        state, lr = self.step_schedule(resumed, state, 433)
        self.assertEqual(lr, END_LR)
        self.assertEqual(state["completed_schedule_updates"], 62)
        self.assertEqual([g["lr"] for g in resumed.param_groups], [END_LR])

    def test_actual_count_and_fresh_parent_are_bound(self):
        opt = self.optimizer()
        with self.assertRaises(ValueError):
            self.fresh(opt, 371)
        state = self.fresh(opt)
        for count in (371, 373, True, 372.0):
            with self.subTest(count=count), self.assertRaises(ValueError):
                apply_next_update_lr(opt, state, count)
        stale = dict(state, completed_schedule_updates=1)
        with self.assertRaisesRegex(ValueError, "do not match actual"):
            apply_next_update_lr(opt, stale, 372)

    def test_metadata_rejects_missing_invalid_and_spec_mismatch(self):
        opt, base = self.optimizer(), self.fresh(self.optimizer())
        with self.assertRaises(ValueError):
            validate_schedule_state({}, opt)
        with self.assertRaises(ValueError):
            validate_schedule_state(None, opt)
        for key, value in (("completed_schedule_updates", True),
                           ("completed_schedule_updates", 0.0),
                           ("schedule_origin_cumulative_update", True),
                           ("schedule_spec_sha256", "0" * 64),
                           ("optimizer_param_group_count", 2)):
            bad = dict(base, **{key: value})
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_schedule_state(bad, opt)
        missing = dict(base)
        missing.pop("horizon_updates")
        with self.assertRaises(ValueError):
            validate_schedule_state(missing, opt)
        self.assertEqual(SCHEDULE_SPEC_SHA256, hashlib.sha256(json.dumps(
            SCHEDULE_SPEC, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest())

    def test_all_groups_validate_before_mutation(self):
        opt = self.optimizer(two_groups=True)
        state = self.fresh(opt)
        before = [group["lr"] for group in opt.param_groups]
        opt.param_groups[1]["lr"] = float("nan")
        with self.assertRaisesRegex(ValueError, "must be finite"):
            apply_next_update_lr(opt, state, 372)
        self.assertEqual(opt.param_groups[0]["lr"], before[0])
        self.assertTrue(math.isnan(opt.param_groups[1]["lr"]))

    def test_split_resume_exact_adam_state_and_group_lrs(self):
        full, full_state = self.optimizer(two_groups=True), None
        full_state = self.fresh(full)
        for n in range(60):
            full_state, _ = self.step_schedule(full, full_state, 372 + n)
        split = self.optimizer(two_groups=True)
        split_state = self.fresh(split)
        for n in range(27):
            split_state, _ = self.step_schedule(split, split_state, 372 + n)
        saved_opt, saved_state = copy.deepcopy(split.state_dict()), copy.deepcopy(split_state)
        saved_params = [[parameter.detach().clone() for parameter in group["params"]]
                        for group in split.param_groups]
        resumed = self.optimizer(two_groups=True)
        with torch.no_grad():
            for source_group, destination_group in zip(saved_params, resumed.param_groups):
                for source, destination in zip(source_group, destination_group["params"]):
                    destination.copy_(source)
        resumed.load_state_dict(saved_opt)
        resumed_state = validate_schedule_state(saved_state, resumed)
        for n in range(27, 60):
            resumed_state, _ = self.step_schedule(resumed, resumed_state, 372 + n)
        self.assertEqual(full_state, resumed_state)
        self.assertEqual([g["lr"] for g in full.param_groups], [g["lr"] for g in resumed.param_groups])
        for full_group, resumed_group in zip(full.param_groups, resumed.param_groups):
            for fp, rp in zip(full_group["params"], resumed_group["params"]):
                torch.testing.assert_close(fp, rp, rtol=0, atol=0)
                for key, expected in full.state[fp].items():
                    actual = resumed.state[rp][key]
                    if isinstance(expected, torch.Tensor):
                        torch.testing.assert_close(expected, actual, rtol=0, atol=0)
                    else:
                        self.assertEqual(expected, actual)

    def test_lr_application_preserves_adam_moments_and_steps(self):
        opt = self.optimizer()
        opt.param_groups[0]["params"][0].grad = torch.tensor([0.3, -0.7], dtype=torch.float64)
        opt.step()
        before = copy.deepcopy(opt.state_dict()["state"])
        apply_next_update_lr(opt, self.fresh(opt), 372)
        after = opt.state_dict()["state"]
        for key, entries in before.items():
            for name, value in entries.items():
                if isinstance(value, torch.Tensor):
                    torch.testing.assert_close(value, after[key][name], rtol=0, atol=0)
                else:
                    self.assertEqual(value, after[key][name])

    def test_frozen_manifest_binds_spec_and_source(self):
        verify_frozen_manifest(Path(__file__).parent)


if __name__ == "__main__":
    unittest.main()
