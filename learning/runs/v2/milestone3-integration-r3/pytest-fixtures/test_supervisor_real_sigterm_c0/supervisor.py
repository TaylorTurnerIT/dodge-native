
import importlib.util, pathlib, sys, hashlib
import dodge_rl
source_root = pathlib.Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
for name in ('supervision', 'checkpoints', 'train_teacher'):
    path = source_root / 'python/dodge_rl' / (name + '.py')
    spec = importlib.util.spec_from_file_location('dodge_rl.' + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    setattr(dodge_rl, name, module)
    spec.loader.exec_module(module)
    print('EXECUTED_SOURCE', name, str(path), hashlib.sha256(path.read_bytes()).hexdigest(), flush=True)

import json, os, signal, subprocess, time
from datetime import datetime, timezone
from types import SimpleNamespace
from dodge_rl import train_teacher as t, identity as i
directory = pathlib.Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/milestone3-integration-r3/pytest-fixtures/test_supervisor_real_sigterm_c0')
config = directory / 'config.json'; config.write_text(json.dumps(i.default_config('pilot')))
identity = directory / 'identity.json'; identity.write_text('{}')
args = SimpleNamespace(config=config, identity=identity, run_dir=directory/'run',
    command='pilot',run_id='synthetic-sigterm',resume_checkpoint=None,parent_checkpoint=None)
class Guard:
    maximum_rss = maximum_mps = 0
    def __init__(self, **kwargs): pass
    def check(self, **kwargs): pass
t.Guard=Guard; t.assert_lease=lambda *a, **kw: {}; t.verify_inputs=lambda *a, **kw: {}
t.utc_now=lambda:datetime(2026,10,24,10,tzinfo=timezone.utc)
t.current_rss_bytes=lambda pid:100
real_popen=subprocess.Popen
worker_code = '''import os,signal,time,pathlib,sys
directory=pathlib.Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/milestone3-integration-r3/pytest-fixtures/test_supervisor_real_sigterm_c0')
def stop(*args):
    (directory/'cooperative-diagnostic.pt').write_bytes(b'synthetic checkpoint opportunity')
    sys.exit(0)
signal.signal(signal.SIGTERM,stop)
(directory/'worker-ready').write_text(str(os.getpid()))
time.sleep(60)
'''
t.subprocess.Popen=lambda command, **kwargs:real_popen([sys.executable,'-B','-c',worker_code],**kwargs)
raise SystemExit(t.run_supervised(args))
