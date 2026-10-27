"""Progress warnings and lease change detection are independent of learning."""
import json
from pathlib import Path
import tempfile
import unittest

from progress_monitor import LeaseReader, parse_lease, ProgressMonitor


class ProgressTests(unittest.TestCase):
    def test_forecast_warns_after_slowdown_without_stopping_training(self):
        now = [0.0]
        monitor = ProgressMonitor(0, 1790, clock=lambda: now[0])
        for update in range(1, 25):
            monitor.begin_update(update)
            now[0] += 22 if update <= 12 else 43
            row = monitor.finish_update(update)
            if update == 12:
                self.assertFalse(row['projected_work_deadline_miss'])
        self.assertTrue(row['projected_work_deadline_miss'])
        self.assertEqual(row['completed_updates'], 24)
        self.assertEqual(row['total_updates'], 60)

    def test_phase_totals_and_active_update_forecast(self):
        now = [0.0]
        monitor = ProgressMonitor(0, 100, total_updates=3, clock=lambda: now[0])
        monitor.begin_update(1)
        now[0] = 2
        monitor.enter('PPO')
        now[0] = 10
        row = monitor.finish_update(1)
        self.assertEqual(row['phase_seconds']['collection'], 2)
        self.assertEqual(row['phase_seconds']['PPO'], 8)
        self.assertEqual(row['projected_total_seconds'], 30)
        monitor.begin_update(2)
        now[0] = 50
        self.assertEqual(monitor.payload()['projected_total_seconds'], 60)

    def test_changed_lease_same_size_and_restored_mtime_is_seen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'ledger.json'
            path.write_text('{"active_long_campaign":"a"}')
            calls = []
            def parser(raw):
                calls.append(raw)
                return parse_lease(raw)
            reader = LeaseReader(path, parser)
            self.assertEqual(reader.read(), 'a')
            self.assertEqual(reader.read(), 'a')
            self.assertEqual(len(calls), 1)
            import os
            old = path.stat()
            path.write_text('{"active_long_campaign":"b"}')
            os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
            self.assertEqual(reader.read(), 'b')

    def test_malformed_changed_deleted_or_duplicate_ledger_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'ledger.json'
            path.write_text('{"active_long_campaign":null}')
            reader = LeaseReader(path, parse_lease)
            self.assertIsNone(reader.read())
            for raw in ('{', '{"active_long_campaign":null,"active_long_campaign":1}',
                        '{"active_long_campaign":NaN}'):
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    reader.read()
            path.unlink()
            with self.assertRaises(FileNotFoundError):
                reader.read()


if __name__ == '__main__':
    unittest.main()
