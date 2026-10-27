"""Redirect existing pure fixtures into this new evidence directory."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
kind = sys.argv[1]
source = {
    'previous37': ROOT / 'learning/runs/v2/milestone2-supervisor-repair-r1/test_supervisor.py',
    'original9': ROOT / 'learning/runs/v2/milestone2-validation-harness-r1/test_harness.py',
}[kind]
spec = importlib.util.spec_from_file_location('retained_' + kind, source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if kind == 'original9':
    selected = Path(os.environ['SUPERVISOR_UNDER_TEST']).resolve()
    assert Path(module.HARNESS.__file__).resolve() == selected
    fixtures = HERE / 'original9-fixtures'
    fixtures.mkdir(exist_ok=False)
    module.HERE = fixtures
print(json.dumps({'retained_test_source': str(source), 'suite': kind,
    'selected_executed_source': str(Path(os.environ['SUPERVISOR_UNDER_TEST']).resolve())}), flush=True)
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
sys.exit(not result.wasSuccessful())
