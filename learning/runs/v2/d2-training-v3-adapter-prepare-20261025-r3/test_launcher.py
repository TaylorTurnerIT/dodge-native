import unittest
from unittest.mock import patch

import launcher


class FakeProcess:
    pid = 987654

    def __init__(self):
        self.waited = False

    def wait(self):
        self.waited = True
        return 0


class LauncherBoundaryTests(unittest.TestCase):
    def test_stop_signals_only_live_owned_group_and_proves_absence(self):
        proc = FakeProcess()
        with patch.object(launcher, "group_exists", side_effect=[True, False, False, False]), \
             patch.object(launcher.os, "killpg") as killpg:
            self.assertTrue(launcher.stop_owned(proc, sleep=lambda _: None, clock=lambda: 0))
        killpg.assert_called_once_with(proc.pid, launcher.signal.SIGTERM)
        self.assertTrue(proc.waited)

    def test_empty_group_gets_no_signal(self):
        proc = FakeProcess()
        with patch.object(launcher, "group_exists", return_value=False), \
             patch.object(launcher.os, "killpg") as killpg:
            self.assertTrue(launcher.stop_owned(proc, sleep=lambda _: None, clock=lambda: 0))
        killpg.assert_not_called()

    def test_finalization_budget_checks_cancellation_and_absolute_deadline(self):
        reg = {"cancel_path": "/nonexistent/cancel", "started_monotonic": 1,
               "absolute_deadline_monotonic": 5000}
        launcher.check_finalization_budget(reg, 2, lambda: 3)
        reg["absolute_deadline_monotonic"] = 2
        with self.assertRaises(ValueError):
            launcher.check_finalization_budget(reg, 2, lambda: 3)


if __name__ == "__main__":
    unittest.main()
