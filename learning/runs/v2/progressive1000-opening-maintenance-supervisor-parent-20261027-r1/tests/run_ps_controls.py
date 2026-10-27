"""Separate bounded real-ps-boundary controls; no original test is rerun here."""
import argparse
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
OWN = HERE.parent
parser = argparse.ArgumentParser()
parser.add_argument('--output-dir', type=Path, required=True)
REPORT = parser.parse_args().output_dir.resolve()
if not REPORT.is_relative_to(OWN):
    raise ValueError('control reports must stay owned')
REPORT.mkdir(parents=True, exist_ok=False)
sys.path[:0] = [str(HERE), str(OWN)]
forbidden = []
spawns = []
signals = []


class NoRuntime:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'numpy', 'torch', 'dodge_rl'}:
            forbidden.append(fullname)
            raise RuntimeError('Forbidden runtime import in ps controls: '+fullname)


sys.meta_path.insert(0, NoRuntime())
import test_ps_deadlines as tests
original = tests.original
original.EVIDENCE_ROOT = REPORT/'real-evidence'


def audit(event, args):
    if event == 'subprocess.Popen':
        argv = args[1]
        ps = argv == tests.PS
        helper = (argv[:3] == [tests.PYTHON, '-I', '-B']
                  and argv[3] in (original.HELPER, tests.PS_HELPER)
                  and Path(argv[-1]).resolve().is_relative_to(HERE))
        if not (ps or helper):
            raise RuntimeError('Unowned subprocess rejected: '+repr(argv))
        spawns.append(dict(argv=argv, kind='ps_readonly' if ps else 'owned_stdlib_child'))
    if event == 'os.killpg':
        pid, sig = args
        if pid not in original.OWNED:
            raise RuntimeError('Unowned group signal rejected: '+str(pid))
        if sig and original.OWNED[pid].returncode is not None:
            raise RuntimeError('Reaped synthetic group signal rejected: '+str(pid))
        signals.append(dict(pgid=pid, signal=sig))
    if event == 'os.kill':
        pid, sig = args
        proc = original.OWNED.get(pid)
        if (proc is None or proc.returncode is not None or sig != signal.SIGKILL
                or proc.args[:4] != [tests.PYTHON, '-I', '-B', tests.PS_HELPER]):
            raise RuntimeError('Unowned PID signal rejected in ps controls')
        signals.append(dict(pid=pid, signal=sig,
                            reason='subprocess.run kills its own interrupted ps helper'))


sys.addaudithook(audit)
resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(
    TimeoutError('ps suite 30-second wall bound')))
signal.alarm(30)
started = time.monotonic()
names = sorted(name for name in tests.PsDeadlines.__dict__ if name.startswith('test_'))
assert len(names) == 4
suite = unittest.TestSuite(tests.PsDeadlines(name) for name in names)
with (REPORT/'ps-controls.log').open('x', buffering=1) as log:
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
receipt = dict(schema='progressive1000_ps_deadline_real_stdlib_controls_v1',
    tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
    successful=result.wasSuccessful(), raw_exit=0 if result.wasSuccessful() else 1,
    elapsed_seconds=time.monotonic()-started, argv_interpreter=tests.PYTHON,
    flags=['-I', '-B'], cpu_seconds_bound=15, wall_seconds_bound=30,
    helper_cpu_seconds_bound=1, helper_wall_seconds_bound=8,
    original_tests_in_this_suite=0, selected_tests=names,
    subprocesses=spawns, signals=signals, forbidden_runtime_imports=forbidden,
    evidence=original.EVIDENCE, remaining_owned_handles=list(original.OWNED),
    scope='Real process_rows/subprocess.run boundary and existing SIGALRM, owned stdlib workers/helpers and read-only ps. Synthetic gates and shortened test clocks only; no runtime, model, checkpoint, restore, training, evaluation or launch authority.')
with (REPORT/'ps-test-receipt.json').open('x') as stream:
    stream.write(json.dumps(receipt, sort_keys=True, indent=2)+'\n')
print((REPORT/'ps-controls.log').read_text(), end='')
raise SystemExit(receipt['raw_exit'])
