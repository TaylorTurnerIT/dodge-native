"""Synthetic CPU tests for schedule arithmetic and Adam resume behavior."""

from __future__ import annotations

import copy
import math
import unittest

import torch

from schedule import (
    END_LR,
    HORIZON_UPDATES,
    ORIGIN_CUMULATIVE_UPDATE,
    SCHEDULE_SPEC_SHA256,
    apply_next_update_lr,
    learning_rate_for_cumulative_update,
    new_schedule_state,
    validate_schedule_state,
)


class ScheduleTests(unittest.TestCase):
    def optimizer(self, *, two_groups: bool = False) -> torch.optim.Adam:
        first = torch.nn.Parameter(torch.tensor([0.25, -0.5], dtype=torch.float64))
        second = torch.nn.Parameter(torch.tensor([0.75], dtype=torch.float64))
        groups = [first, second] if two_groups else [first, second]
        if two_groups:
            return torch.optim.Adam([{"params": [first]}, {"params": [second]}], lr=3e-5)
        return torch.optim.Adam(groups, lr=3e-5)

    def test_endpoints_off_by_one_and_hold(self) -> None:
        self.assertEqual(learning_rate_for_cumulative_update(373), 3e-5)
        self.assertAlmostEqual(learning_rate_for_cumulative_update(431), 1e-5 + 2e-5 / 59)
        self.assertAlmostEqual(learning_rate_for_cumulative_update(432), 1e-5)
        self.assertEqual(learning_rate_for_cumulative_update(433), END_LR)
        self.assertEqual(learning_rate_for_cumulative_update(1000), END_LR)

    def _run(self, optimizer: torch.optim.Adam, state: dict, start: int, stop: int) -> dict:
        for update in range(start, stop):
            lr, state = apply_next_update_lr(optimizer, state)
            self.assertTrue(math.isfinite(lr))
            for param_index, parameter in enumerate(optimizer.param_groups[0]["params"]):
                target = torch.full_like(parameter, 0.1 * (param_index + 1))
                loss = ((parameter - target) ** 2).sum()
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()
        return state

    def test_split_resume_matches_uninterrupted_adam(self) -> None:
        full = self.optimizer()
        full_state = new_schedule_state(full)
        full_state = self._run(full, full_state, 0, HORIZON_UPDATES)

        split = self.optimizer()
        split_state = new_schedule_state(split)
        split_state = self._run(split, split_state, 0, 23)
        saved_optimizer = copy.deepcopy(split.state_dict())
        saved_schedule = copy.deepcopy(split_state)

        resumed = self.optimizer()
        with torch.no_grad():
            for source, destination in zip(split.param_groups[0]["params"], resumed.param_groups[0]["params"]):
                destination.copy_(source)
        resumed.load_state_dict(saved_optimizer)
        resumed_state = validate_schedule_state(saved_schedule, resumed)
        resumed_state = self._run(resumed, resumed_state, 23, HORIZON_UPDATES)

        self.assertEqual(full_state, resumed_state)
        for full_param, resumed_param in zip(full.param_groups[0]["params"], resumed.param_groups[0]["params"]):
            torch.testing.assert_close(full_param, resumed_param, rtol=0, atol=0)
        for full_param, resumed_param in zip(full.param_groups[0]["params"], resumed.param_groups[0]["params"]):
            for state_key, expected in full.state[full_param].items():
                actual = resumed.state[resumed_param][state_key]
                if isinstance(expected, torch.Tensor):
                    torch.testing.assert_close(expected, actual, rtol=0, atol=0)
                else:
                    self.assertEqual(expected, actual)

    def test_lr_change_leaves_adam_moments_and_steps_unchanged(self) -> None:
        optimizer = self.optimizer()
        parameter = optimizer.param_groups[0]["params"][0]
        parameter.grad = torch.tensor([0.3, -0.7], dtype=parameter.dtype)
        optimizer.step()
        before = copy.deepcopy(optimizer.state_dict()["state"])
        state = new_schedule_state(optimizer)
        lr, _ = apply_next_update_lr(optimizer, state)
        self.assertEqual(lr, 3e-5)
        after = optimizer.state_dict()["state"]
        self.assertEqual(before.keys(), after.keys())
        for key, entries in before.items():
            for name, value in entries.items():
                if isinstance(value, torch.Tensor):
                    torch.testing.assert_close(value, after[key][name], rtol=0, atol=0)
                else:
                    self.assertEqual(value, after[key][name])

    def test_bad_metadata_and_group_mismatch_rejected(self) -> None:
        optimizer = self.optimizer()
        base = new_schedule_state(optimizer)
        for key, value in (
            ("schedule_origin_cumulative_update", 371),
            ("horizon_updates", 59),
            ("schedule_spec_sha256", "0" * 64),
            ("completed_schedule_updates", HORIZON_UPDATES + 1),
            ("completed_schedule_updates", float("nan")),
            ("optimizer_param_group_count", 2),
        ):
            bad = dict(base)
            bad[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_schedule_state(bad, optimizer)
        grouped = self.optimizer(two_groups=True)
        with self.assertRaisesRegex(ValueError, "parameter-group count"):
            validate_schedule_state(base, grouped)
        self.assertEqual(SCHEDULE_SPEC_SHA256, base["schedule_spec_sha256"])

    def test_invalid_updates_and_nonfinite_optimizer_lr_rejected_atomically(self) -> None:
        for value in (0, ORIGIN_CUMULATIVE_UPDATE, -1, True, 373.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                learning_rate_for_cumulative_update(value)
        optimizer = self.optimizer(two_groups=True)
        state = new_schedule_state(optimizer)
        optimizer.param_groups[1]["lr"] = float("nan")
        old_first = optimizer.param_groups[0]["lr"]
        with self.assertRaisesRegex(ValueError, "must be finite"):
            apply_next_update_lr(optimizer, state)
        self.assertEqual(optimizer.param_groups[0]["lr"], old_first)


if __name__ == "__main__":
    unittest.main()
