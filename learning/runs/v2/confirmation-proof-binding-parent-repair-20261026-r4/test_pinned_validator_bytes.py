"""Regression controls for the selection validator's verified-byte execution boundary."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import worker


class PinnedValidatorBytesTests(unittest.TestCase):
    def test_stale_pin_rejects_before_any_module_side_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'validator.py'
            marker = Path(directory) / 'executed'
            path.write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').touch()\n')
            with self.assertRaisesRegex(RuntimeError, 'pin absent or mismatch'):
                worker.load_selection_validator({'path': str(path), 'sha256': '0' * 64})
            self.assertFalse(marker.exists())

    def test_only_verified_bytes_execute_when_path_changes_after_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'validator.py'
            marker = Path(directory) / 'executed'
            trusted = b'VALUE = 42\n'
            path.write_bytes(trusted)
            original_read = Path.read_bytes
            reads = []

            def read_and_swap(target):
                data = original_read(target)
                if target == path:
                    reads.append(data)
                    path.write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').touch()\n')
                return data

            with patch.object(Path, 'read_bytes', read_and_swap):
                with self.assertRaisesRegex(RuntimeError, 'after import pin absent or mismatch'):
                    worker.load_selection_validator({'path': str(path),
                                                     'sha256': hashlib.sha256(trusted).hexdigest()})
            self.assertEqual(reads, [trusted])
            self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main()
