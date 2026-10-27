"""One fail-fast suite: 112 current inherited methods plus r14 adapted/new tests.

All inherited methods run directly against the CURRENT candidate and current
constants. Four named static methods have explicitly migrated expectations in
their test sources; no historical-target rebinding, patching of production
constants or mocks of the candidate is used.
"""
from pathlib import Path
import json
import os
import sys
import time
import unittest
import long_d2 as c
import test_r14
import test_r11
import test_r10
import test_r7
import test_repairs
import test_boundary

H = Path(__file__).resolve().parent
MODULES = (test_r14, test_r11, test_r10, test_r7, test_repairs, test_boundary)
MIGRATED_STATIC = (
    'test_r11.R11.test_C01_exact_success_consumers_transport_inner_fixtures_and_old91',
    'test_r11.R11.test_C02_protocol_only_candidate_paths_and_qualified_semantics',
    'test_r10.R10.test_exact_r9_transport_success_consumers_protected_blocks',
    'test_r7.R7.test_success_consumers_and_protected_failure_helpers_byte_equal',
)


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = []
        self.started = None

    def startTest(self, test):
        self.started = time.perf_counter()
        super().startTest(test)

    def row(self, test, status, detail=None):
        self.rows.append(dict(test=test.id(), status=status, detail=detail,
            elapsed_seconds=time.perf_counter() - self.started,
            source_binding='r14_current_candidate_migrated_static' if test.id() in MIGRATED_STATIC else 'r14_current_candidate'))

    def addSuccess(self, test):
        self.row(test, 'passed')
        super().addSuccess(test)

    def addFailure(self, test, error):
        self.row(test, 'failed', self._exc_info_to_string(error, test))
        super().addFailure(test, error)

    def addError(self, test, error):
        self.row(test, 'error', self._exc_info_to_string(error, test))
        super().addError(test, error)

    def addSkip(self, test, reason):
        self.row(test, 'skipped', reason)
        super().addSkip(test, reason)


def main():
    tests = [test for module in MODULES for test in flatten(unittest.defaultTestLoader.loadTestsFromModule(module))]
    planned = [test.id() for test in tests]
    result = unittest.TextTestRunner(verbosity=2, failfast=True, resultclass=RecordedResult).run(unittest.TestSuite(tests))
    forbidden = [name for name in sys.modules if name.split('.')[0] in ('torch', 'numpy', 'dodge_rl')]
    report = dict(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        skipped=len(result.skipped), unexpected_successes=len(result.unexpectedSuccesses),
        planned_tests=planned, per_test_results=result.rows,
        failed_tests=[test.id() for test, _ in result.failures], error_tests=[test.id() for test, _ in result.errors],
        unrun_tests=planned[result.testsRun:], successful=result.wasSuccessful() and not forbidden,
        forbidden_imports=forbidden, existing_method_count=sum(not name.startswith('test_r14.') for name in planned),
        new_method_count=sum(name.startswith('test_r14.') for name in planned),
        migrated_static_methods=list(MIGRATED_STATIC), historical_target_rebinding=False,
        modeled_signals=True, actual_OS_signals=False, actual_interval_operations=True,
        actual_reader_thread=True, no_lifecycle_stress_startup_or_ML_campaign=True,
        executable_observed=sys.executable, argv=sys.argv, validation_dir=os.environ['VALIDATION_DIR'])
    with (Path(os.environ['VALIDATION_DIR']).parent / 'suite-result.json').open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    raise SystemExit(0 if report['successful'] else 1)

if __name__ == '__main__':
    main()
