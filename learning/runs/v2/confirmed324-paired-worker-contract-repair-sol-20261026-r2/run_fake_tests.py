"""Only CPU fakes/stdlib. Refuse accidental real runtime imports."""
import importlib.abc
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE=Path(__file__).resolve().parent
assert sys.dont_write_bytecode and sys.pycache_prefix==str(HERE/'empty-pycache')
assert os.environ['PYTHONPYCACHEPREFIX']==sys.pycache_prefix
assert not any((HERE/'empty-pycache').iterdir())
tempfile.tempdir=str(HERE/'tmp')
blocked=[]
class NoRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'numpy','torch','dodge_rl'}:
            blocked.append(fullname)
            raise RuntimeError('real runtime import forbidden in source-only tests: '+fullname)
sys.meta_path.insert(0,NoRuntime())
# R5 binding controls compare module identity. These are empty ModuleType fakes,
# installed without import, package code execution, real arrays or tensors.
assert 'numpy' not in sys.modules and 'torch' not in sys.modules
sys.modules['numpy']=types.ModuleType('numpy')
sys.modules['torch']=types.ModuleType('torch')
suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_*.py')
result=unittest.TextTestRunner(verbosity=2).run(suite)
assert not any((HERE/'empty-pycache').iterdir())
with (HERE/'fake-test-summary.json').open('w') as stream:
    json.dump(dict(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                   unexpected_runtime_import_requests=blocked,executable=sys.executable,version=sys.version,
                   flags=str(sys.flags),pycache_prefix=sys.pycache_prefix,cache_empty=True,
                   evidence='CPU fakes and stdlib only; no runtime qualification'),stream,indent=2)
    stream.write('\n')
raise SystemExit(0 if result.wasSuccessful() and not blocked else 1)
