"""Separate guarded real-process suite. The fake suite still forbids all spawn."""
import io
import argparse
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time
import unittest

HERE=Path(__file__).resolve().parent
OWN=HERE.parent
parser=argparse.ArgumentParser()
parser.add_argument('--output-dir',type=Path,default=OWN)
REPORT=parser.parse_args().output_dir.resolve()
if not REPORT.is_relative_to(OWN): raise ValueError('control reports must stay owned')
if REPORT != OWN: REPORT.mkdir(parents=True,exist_ok=False)
if any((REPORT/name).exists() for name in ('real-controls.log','real-test-receipt.json','real-evidence')):
    raise FileExistsError('real control receipt already exists; use a fresh owned --output-dir')
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(OWN))
forbidden=[];spawns=[];signals=[]
class NoRuntime:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'numpy','torch','dodge_rl'}:
            forbidden.append(fullname)
            raise RuntimeError('Forbidden runtime import in real stdlib controls: '+fullname)
sys.meta_path.insert(0,NoRuntime())
import test_real_processes as tests
tests.EVIDENCE_ROOT=REPORT/'real-evidence'

def audit(event,args):
    if event=='subprocess.Popen':
        argv=args[1]
        allowed_ps=argv==['/bin/ps','-axo','pid=,ppid=,pgid=,rss=,lstart=,command=']
        allowed_helper=argv[:4]==[tests.PYTHON,'-I','-B',tests.HELPER] and Path(argv[-1]).resolve().is_relative_to(HERE)
        if not (allowed_ps or allowed_helper): raise RuntimeError('Unowned subprocess rejected: '+repr(argv))
        spawns.append(dict(argv=argv,kind='ps_readonly' if allowed_ps else 'owned_stdlib_child'))
    if event=='os.killpg':
        pid,sig=args
        if pid not in tests.OWNED: raise RuntimeError('Unowned group signal rejected: '+str(pid))
        if sig and tests.OWNED[pid].returncode is not None:
            # A fresh retained group anchor is required after direct reap.
            # These fixtures never need to send after their leader was reaped.
            raise RuntimeError('Reaped synthetic group signal rejected: '+str(pid))
        signals.append(dict(pgid=pid,signal=sig))
    if event=='os.kill':
        pid,sig=args
        if pid!=os.getpid() or sig!=signal.SIGTERM: raise RuntimeError('Unowned PID signal rejected')
        signals.append(dict(pid=pid,signal=sig,reason='inject controller cancellation'))
sys.addaudithook(audit)
resource.setrlimit(resource.RLIMIT_CPU,(15,15))
signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('real suite 55-second wall bound')))
signal.alarm(55)
started=time.monotonic()
suite=unittest.defaultTestLoader.loadTestsFromModule(tests)
log=io.StringIO()
result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
text=log.getvalue()
(REPORT/'real-controls.log').write_text(text)
receipt=dict(schema='progressive1000_supervisor_real_stdlib_controls_v1',tests_run=result.testsRun,
    failures=len(result.failures),errors=len(result.errors),successful=result.wasSuccessful(),
    raw_exit=0 if result.wasSuccessful() else 1,elapsed_seconds=time.monotonic()-started,
    argv_interpreter=tests.PYTHON,flags=['-I','-B'],cpu_seconds_bound=15,wall_seconds_bound=55,
    subprocesses=spawns,signals=signals,forbidden_runtime_imports=forbidden,evidence=tests.EVIDENCE,
    remaining_owned_handles=list(tests.OWNED),scope='Real bounded stdlib processes with mocked gates and synthetic control paths only. No model, native, Torch, NumPy, MPS, checkpoint, campaign or acceptance evidence.')
(REPORT/'real-test-receipt.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
print(text,end='')
raise SystemExit(receipt['raw_exit'])
