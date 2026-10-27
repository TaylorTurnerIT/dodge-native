"""Deadline and stall alerts must wake the parent before a hard timeout."""
import copy
import unittest

from watch_progress import assess


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.row=dict(total_updates=60,work_limit_seconds=3780,
            elapsed_seconds=30,projected_work_deadline_miss=False)

    def test_healthy_progress_never_changes_training(self):
        before=copy.deepcopy(self.row)
        self.assertIsNone(assess(self.row,31,3780,60))
        self.assertEqual(self.row,before)

    def test_forecast_warning_alerts_immediately(self):
        self.row['projected_work_deadline_miss']=True
        self.assertEqual(assess(self.row,31,3780,60),'projected_work_deadline_miss')

    def test_missing_stale_and_mismatched_progress_alert(self):
        self.assertIsNone(assess(None,119,3780,60))
        self.assertEqual(assess(None,121,3780,60),'no_progress_for_120_seconds')
        self.assertEqual(assess(self.row,151,3780,60),'progress_stale_for_120_seconds')
        self.assertEqual(assess(self.row,31,1790,60),'progress_registration_mismatch')


if __name__=='__main__':unittest.main()
