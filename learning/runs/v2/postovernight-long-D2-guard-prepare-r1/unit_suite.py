"""Fresh inherited controls and affected regressions. No ML imports."""
from pathlib import Path
import json,os,sys,unittest
import long_d2 as c
H=Path(__file__).resolve().parent;out=Path(os.environ['LONG_D2_TEST_EVIDENCE'])
(out/'tmp').mkdir();import tempfile;tempfile.tempdir=str(out/'tmp')
import legacy_controls as legacy
import test_lifecycle as current
import test_worker_ack_contract as ack
import test_guard_repair as repair
suite=unittest.TestSuite()
for name in ('ConfigTests','LeaseTests','LegacyTests','ScheduleTests','StateTests','GuardTests'):
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(getattr(legacy,name)))
for name in ('test_raw_and_semantic_distinct','test_each_legacy_byte_pin','test_module_origins_and_mirrors','test_namespace_without_origin_rejected','test_readonly_inventory_permissions_and_escape','test_freeze_and_preflight_import_purity'):
    suite.addTest(legacy.IdentityTests(name))
for module in (current,ack,repair):suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
r=unittest.TextTestRunner(verbosity=2,failfast=True).run(suite)
c.save(out/'unit-result.json',dict(methods_run=r.testsRun,failures=len(r.failures),errors=len(r.errors),successful=r.wasSuccessful(),ML_imports=any(n in ('torch','numpy','dodge_rl') for n in sys.modules),sources={p.name:c.sha(p) for p in H.glob('*.py')}))
raise SystemExit(0 if r.wasSuccessful() else 1)
