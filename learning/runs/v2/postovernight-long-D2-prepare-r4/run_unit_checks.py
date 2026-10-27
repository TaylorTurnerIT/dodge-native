"""Exact selected inherited controls plus new r3 tests; fail on first failure."""
from pathlib import Path
import json
import os
import shutil
import sys
import unittest
import long_d2 as c
HERE=Path(__file__).resolve().parent
out=Path(sys.argv[1]).resolve();out.mkdir()
(out/'tmp').mkdir();os.environ['TMPDIR']=str(out/'tmp');os.environ['LONG_D2_TEST_EVIDENCE']=str(out)
import tempfile
tempfile.tempdir=str(out/'tmp')
(out/'sources').mkdir()
for p in HERE.glob('*.py'):shutil.copyfile(p,out/'sources'/p.name)
import legacy_controls as legacy
import test_lifecycle as current
import test_worker_ack_contract as worker_ack
suite=unittest.TestSuite()
for name in ('ConfigTests','LeaseTests','LegacyTests','ScheduleTests','StateTests','GuardTests'):
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(getattr(legacy,name)))
# Source/mirror controls remain pure and do not execute the full legacy suite.
for name in ('test_raw_and_semantic_distinct','test_each_legacy_byte_pin','test_module_origins_and_mirrors',
             'test_namespace_without_origin_rejected','test_readonly_inventory_permissions_and_escape','test_freeze_and_preflight_import_purity'):
    suite.addTest(legacy.IdentityTests(name))
suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(current))
suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(worker_ack))
result=unittest.TextTestRunner(verbosity=2,failfast=True).run(suite)
c.save(out/'unit-result.json',dict(methods_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
    successful=result.wasSuccessful(),ML_imports=any(n in ('torch','numpy','dodge_rl') for n in sys.modules),
    sources={p.name:c.sha(p) for p in HERE.glob('*.py')}))
raise SystemExit(0 if result.wasSuccessful() else 1)
