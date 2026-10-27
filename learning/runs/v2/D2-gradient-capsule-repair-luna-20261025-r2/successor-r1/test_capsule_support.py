import tempfile
import unittest
from pathlib import Path

import runner


class CapsuleSupport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.docs = self.root / "docs"
        self.docs.mkdir()
        source = Path(__file__).resolve().parent / "own/docs"
        self.reg = {"runtime_root": str(self.root), "capsule_support": {
            "v2-m3-run-protocol.json": "9e0d82028011f83e0cf6ddaef5f5e118591158d8a557f6698c82c150d5a69bab",
            "teacher-qualification-v2.json": "e091f8a2fad0a307d289a6d306112606b15df8f8aa0f3a75707ac7cfb2cee803",
            "v2-m3-component-contract.md": "a1051d82527a9aec1f7967ff8ab217c30263240e032991aeff7b993fd975ba47",
            "teacher-qualification-v3.json": "bfcbee1609cec0180495c957cf4b5e0b31356f395e2a706217cc9225647d23ae"}, "pins": {}}
        for name, digest in self.reg["capsule_support"].items():
            (self.docs / name).write_bytes((source / name).read_bytes())
            self.reg["pins"][str(self.docs / name)] = digest

    def tearDown(self): self.tmp.cleanup()

    def test_complete_exact_capsule_support_passes(self):
        runner.validate_capsule_support(self.reg)

    def test_missing_support_file_fails(self):
        (self.docs / "v2-m3-run-protocol.json").unlink()
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            runner.validate_capsule_support(self.reg)

    def test_mutated_support_file_fails(self):
        with (self.docs / "teacher-qualification-v3.json").open("ab") as stream: stream.write(b"x")
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            runner.validate_capsule_support(self.reg)

    def test_unpinned_support_file_fails(self):
        self.reg["pins"].pop(str(self.docs / "teacher-qualification-v2.json"))
        with self.assertRaisesRegex(ValueError, "not externally pinned"):
            runner.validate_capsule_support(self.reg)


if __name__ == "__main__": unittest.main()
