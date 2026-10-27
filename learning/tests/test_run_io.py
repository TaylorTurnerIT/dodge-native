import json
from pathlib import Path
import tempfile
import unittest

from dodge_learning.teacher_run import write_json


class RunReceiptTests(unittest.TestCase):
    def test_receipt_publication_preserves_existing_file_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            write_json(path, {"frames": 17})
            with self.assertRaises(FileExistsError):
                write_json(path, {"frames": 999})
            self.assertEqual(json.loads(path.read_text()), {"frames": 17})
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_invalid_numeric_receipt_never_creates_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            with self.assertRaises(ValueError):
                write_json(path, {"loss": float("nan")})
            self.assertFalse(path.exists())
