"""Run only this binding's bounded stdlib controls, with import/spawn guards."""
import io
import argparse
import json
import resource
import signal
from pathlib import Path
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
OWN = HERE.parent
parser=argparse.ArgumentParser()
parser.add_argument('--output-dir',type=Path,default=OWN)
REPORT=parser.parse_args().output_dir.resolve()
if not REPORT.is_relative_to(OWN): raise ValueError('control reports must stay owned')
if REPORT != OWN: REPORT.mkdir(parents=True,exist_ok=False)
if any((REPORT/name).exists() for name in ('controls.log','test-receipt.json')):
    raise FileExistsError('control receipt already exists; use a fresh owned --output-dir')
sys.path.insert(0,str(HERE))
forbidden = []
spawns = []


class NoRuntime:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'numpy','torch','dodge_rl'}:
            forbidden.append(fullname)
            raise RuntimeError('Forbidden runtime import in stdlib controls: '+fullname)


def audit(event,args):
    if event == 'subprocess.Popen':
        spawns.append(str(args[0]))
        raise RuntimeError('Real subprocess launch forbidden in fake-process controls')


sys.meta_path.insert(0,NoRuntime())
sys.addaudithook(audit)
resource.setrlimit(resource.RLIMIT_CPU,(15,15))
signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('fake suite 30-second wall bound')))
signal.alarm(30)
started = time.monotonic()
suite = unittest.defaultTestLoader.discover(str(HERE),pattern='test_bindings.py')
sys.modules['test_bindings'].EVIDENCE_ROOT = REPORT/'fake-evidence'
log = (REPORT/'controls.log').open('x',buffering=1)
result = unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
log.close()
text = (REPORT/'controls.log').read_text()
receipt = dict(schema='progressive1000_supervisor_stdlib_controls_v1',tests_run=result.testsRun,
    failures=len(result.failures),errors=len(result.errors),successful=result.wasSuccessful(),
    raw_exit=0 if result.wasSuccessful() else 1,elapsed_seconds=time.monotonic()-started,
    actual_subprocess_launches=spawns,forbidden_runtime_imports=forbidden,
    scope='Synthetic process objects and JSON/hash controls only; no actual restore, runtime, cleanup or campaign qualification.')
(REPORT/'test-receipt.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
print(text,end='')
raise SystemExit(receipt['raw_exit'])
