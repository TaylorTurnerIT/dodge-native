
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

import json, os, signal, time
from datetime import datetime, timezone
from types import SimpleNamespace
from dodge_rl import train_teacher as t, identity as i, checkpoints as c
directory=pathlib.Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/milestone3-integration-r3/pytest-fixtures/test_worker_cancellation_attem0')
config=directory/'config.json';config.write_text(json.dumps(i.default_config('pilot')))
class Guard:
    maximum_rss=maximum_mps=0
    def __init__(self, **kwargs): pass
    def check(self, **kwargs): pass
class Experiment:
    progress={'in_update':True,'complete':False,'optimizer_steps':1}
    def __init__(self,*args): pass
    def pilot(self):
        os.kill(os.getpid(), signal.SIGTERM)
    def checkpoint(self,tag):
        path=directory/(tag+'.pt')
        return path,c.save_checkpoint(path,{'tag':tag,'update_progress':self.progress})
    def close(self): (directory/'closed').write_text('yes')
t.Guard=Guard;t.Experiment=Experiment;t.verify_inputs=lambda *a:{};t.assert_lease=lambda *a, **kw:{}
t.utc_now=lambda:datetime(2026,10,24,10,tzinfo=timezone.utc)
started=time.monotonic()
args=SimpleNamespace(config=config,config_sha256=i.file_hash(config),identity_sha256='a'*64,
    phase='pilot',consumed_wall_seconds=0,execution_started_monotonic=started,
    deadline_monotonic=started+300,run_dir=directory,run_id='synthetic-worker',resume_checkpoint=None)
raise SystemExit(t.worker(args))
