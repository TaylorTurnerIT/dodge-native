"""Filesystem rejection cases and complete preservation of the reviewed auditor."""
import json
from pathlib import Path
import tempfile
import unittest

import repair_contract as contract


class CacheDispositionTests(unittest.TestCase):
    def test_absence_is_read_only_and_rejects_all_existing_states(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'cache'
            contract.require_absent_cache(path)
            self.assertFalse(path.exists())
            path.mkdir()
            with self.assertRaises(ValueError):
                contract.require_absent_cache(path)
            (path / 'unexpected.pyc').write_bytes(b'preserve')
            with self.assertRaises(ValueError):
                contract.require_absent_cache(path)
            self.assertEqual((path / 'unexpected.pyc').read_bytes(), b'preserve')
            (path / 'unexpected.pyc').unlink()
            path.rmdir()
            path.write_bytes(b'file')
            with self.assertRaises(ValueError):
                contract.require_absent_cache(path)
            path.unlink()
            path.symlink_to(Path(temporary) / 'missing-target')
            with self.assertRaises(ValueError):
                contract.require_absent_cache(path)
            self.assertTrue(path.is_symlink())

    def test_auditor_matches_explicit_source_delta(self):
        delta = json.loads((contract.HERE / 'reviewed-delta.json').read_text())
        original = Path(delta['original_path'])
        self.assertEqual(contract.digest(original), delta['original_sha256'])
        expected = original.read_text()
        for change in delta['replacements']:
            self.assertEqual(expected.count(change['before']), 1)
            expected = expected.replace(change['before'], change['after'])
        self.assertEqual(expected, (contract.HERE / 'accept_saved_screen.py').read_text())


if __name__ == '__main__':
    unittest.main()
