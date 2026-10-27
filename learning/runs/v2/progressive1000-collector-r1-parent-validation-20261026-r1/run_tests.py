"""Bounded synthetic CPU test entry point; fail fast, no campaign/launch API."""
from pathlib import Path
import json
import sys
import unittest

import torch

root = Path(__file__).resolve().parent
sys.path[:0] = [str(root), str(root / "tests"), str(root / "successor")]
torch.set_num_threads(1)
print("Scope: synthetic CPU unit tests; no native/checkpoint/MPS/study seeds.", flush=True)
print("Python:", sys.version, flush=True)
print("Torch:", torch.__version__, "threads:", torch.get_num_threads(), flush=True)
result = unittest.TextTestRunner(verbosity=2, failfast=True).run(
    unittest.defaultTestLoader.discover(str(root / "tests")))
for name in sys.modules:
    if name == "dodge_rl" or name.startswith("dodge_rl.") or name == "_native":
        raise RuntimeError("forbidden runtime/native import: " + name)
if result.wasSuccessful():
    from test_collector import EVIDENCE
    (root / "logs/fake-controls.json").write_text(json.dumps({
        "scope": "synthetic CPU preparation only, never native/runtime qualification",
        "tests_run": result.testsRun, "controls": EVIDENCE}, indent=2, sort_keys=True) + "\n")
print("Native/checkpoint runtime imports: none", flush=True)
print("CUDA initialized:", torch.cuda.is_initialized(), flush=True)
raise SystemExit(not result.wasSuccessful())
