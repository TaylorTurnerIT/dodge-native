"""Bounded stdlib CPU/fake checks only. Never import native, torch or accepted state."""
from pathlib import Path
import json
import shutil
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "tests")]
print("Scope: stdlib CPU/fake only; no native/environment/checkpoint/MPS/training/reference execution.", flush=True)
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(HERE / "tests")))
forbidden = [n for n in sys.modules if n == "torch" or n == "numpy" or n == "dodge_rl" or n.startswith("dodge_rl.") or n == "_native"]
summary = dict(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
    success=result.wasSuccessful() and not forbidden, forbidden_imports=forbidden, native_imported=False,
    torch_imported="torch" in sys.modules, accepted_checkpoint_deserialized=False, real_MPS_tested=False,
    study_seed_or_cohort_executed=False, launch_authority=False)
shutil.rmtree(HERE / "tmp", ignore_errors=True)
(HERE / "logs/test-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary), flush=True)
raise SystemExit(not summary["success"])
