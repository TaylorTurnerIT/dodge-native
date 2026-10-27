"""Ordered targeted stdlib tests. Fail once, stop; no campaign authorization."""
from pathlib import Path
import json
import os
import sys
import unittest
import test_repairs
import test_boundary
import test_r7

def main():
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(module) for module in (test_r7,test_repairs,test_boundary))
    planned=[test.id() for module_suite in suite for class_suite in module_suite for test in class_suite]
    result=unittest.TextTestRunner(verbosity=2,failfast=True).run(suite)
    forbidden=[name for name in sys.modules if name.split('.')[0] in ('torch','numpy','dodge_rl')]
    report=dict(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
                unexpected_successes=len(result.unexpectedSuccesses),planned_tests=planned,
                failed_tests=[test.id() for test,_ in result.failures],error_tests=[test.id() for test,_ in result.errors],
                unrun_tests=planned[result.testsRun:],successful=result.wasSuccessful() and not forbidden,
                forbidden_imports=forbidden,scope='real stdlib classes, synthetic clocks/files/peers; no OS lifecycle matrix, ML/native imports, or performance claim',
                executable_observed=sys.executable,argv=sys.argv,validation_dir=os.environ['VALIDATION_DIR'])
    (Path(os.environ['VALIDATION_DIR']).parent/'suite-result.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    raise SystemExit(0 if report['successful'] else 1)
if __name__=='__main__':main()
