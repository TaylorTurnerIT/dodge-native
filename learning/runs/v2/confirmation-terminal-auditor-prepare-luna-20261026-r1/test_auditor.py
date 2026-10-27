import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('auditor', HERE / 'auditor.py')
auditor = importlib.util.module_from_spec(spec); spec.loader.exec_module(auditor)

class SyntheticGateTests(unittest.TestCase):
    def test_nonzero_and_bool_exit_rejected_before_filesystem(self):
        for value in (1, True, -1):
            with self.assertRaises(auditor.AuditError):
                auditor.audit('/must-not-open', '0'*64, value, '/must-not-write')

    def test_registration_pin_rejected_before_json(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'reg'; p.write_text('{}')
            with self.assertRaisesRegex(auditor.AuditError, 'registration external SHA'):
                auditor.audit(p, '0'*64, 0, Path(td)/'new')
            self.assertFalse((Path(td)/'new').exists())

    def test_process_query_rejects_pid_ppid_or_group_presence(self):
        for row in ('10 1 10', '20 10 20', '20 1 10'):
            self.assertEqual(auditor._process_rows(10, lambda _: row), [tuple(map(int,row.split()))])
        self.assertEqual(auditor._process_rows(10, lambda _: '20 1 20'), [])

    def test_raw_pin_detects_drift(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x'; p.write_bytes(b'a')
            with self.assertRaisesRegex(auditor.AuditError, 'SHA-256 mismatch'):
                auditor.file_pin(p, hashlib.sha256(b'b').hexdigest(), 'fixture')

if __name__ == '__main__': unittest.main(verbosity=2)
