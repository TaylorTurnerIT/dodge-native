"""Run existing tests without writing fixtures or bytecode into original artifacts."""
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
source = ROOT / "learning/runs/v2/milestone2-validation-harness-r1/test_harness.py"
spec = importlib.util.spec_from_file_location("original_readonly_pure_tests", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
fixtures = HERE / "existing-test-temporaries"
fixtures.mkdir(exist_ok=True)
module.HERE = fixtures
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
sys.exit(not result.wasSuccessful())
