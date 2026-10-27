"""Fail closed on real runtime imports; fixture writes only in owned tmp."""
import importlib.abc
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
HERE=Path(__file__).resolve().parent
assert sys.dont_write_bytecode and sys.pycache_prefix==str(HERE/'empty-pycache')
assert not any((HERE/'empty-pycache').iterdir())
tempfile.tempdir=str(HERE/'tmp')
blocked=[]
class NoRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'torch','numpy','dodge_rl'}:
            blocked.append(fullname); raise RuntimeError('real runtime import forbidden: '+fullname)
sys.meta_path.insert(0,NoRuntime())
suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_restore_probe.py')
result=unittest.TextTestRunner(verbosity=2).run(suite)
summary=dict(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),blocked_runtime_import_requests=blocked,loaded_runtime_modules=[n for n in sys.modules if n.split('.')[0] in {'torch','numpy','dodge_rl'}],cache_empty=not any((HERE/'empty-pycache').iterdir()),executable=sys.executable,prefix=sys.prefix,version=sys.version)
(HERE/'fake-test-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
raise SystemExit(0 if result.wasSuccessful() and not blocked and not summary['loaded_runtime_modules'] else 1)
