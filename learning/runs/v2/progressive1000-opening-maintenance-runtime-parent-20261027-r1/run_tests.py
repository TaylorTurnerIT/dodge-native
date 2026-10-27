"""Bounded fake/stdlib CPU controls only. Never import native or accepted state."""
from pathlib import Path
import json
import os
import sys
import unittest

HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE/'tests')]
os.environ['TMPDIR']=str(HERE/'tmp')
import tempfile
tempfile.tempdir=str(HERE/'tmp')
import torch
torch.set_num_threads(1)
print('Scope: synthetic CPU and stdlib only; no native/environment/study/checkpoint/MPS execution.',flush=True)
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(HERE/'tests')))
for name in sys.modules:
    if name=='dodge_rl' or name.startswith('dodge_rl.') or name=='_native':
        raise RuntimeError('forbidden runtime/native import: '+name)
summary=dict(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
    success=result.wasSuccessful(),native_imported=False,accepted_checkpoint_deserialized=False,
    real_MPS_tested=False,study_seed_or_cohort_executed=False,torch_version=str(torch.__version__))
(HERE/'logs/test-summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
print(json.dumps(summary),flush=True)
raise SystemExit(not result.wasSuccessful())
