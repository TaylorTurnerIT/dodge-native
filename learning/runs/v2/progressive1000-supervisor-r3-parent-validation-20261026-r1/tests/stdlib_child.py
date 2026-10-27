"""Owned finite stdlib subprocess fixture; never imports a runtime or trainer."""
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

OWN = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(OWN))
resource.setrlimit(resource.RLIMIT_CPU,(3,3))
signal.signal(signal.SIGALRM,lambda *_:os._exit(124))
signal.alarm(18)
mode, home = sys.argv[1], Path(sys.argv[2])
assert home.resolve().is_relative_to(OWN/'tests')
def wait_for(path):
    end=time.monotonic()+4
    while not path.exists():
        if time.monotonic()>=end: raise TimeoutError(str(path))
        time.sleep(.005)
if mode == 'publish':
    import binding as b
    original=b.json.dump
    def partial(value, stream, **kwargs):
        stream.write('{"payload":');stream.flush();os.fsync(stream.fileno())
        (home/'partial-ready').touch()
        wait_for(home/'continue')
        stream.seek(0);stream.truncate()
        return original(value,stream,**kwargs)
    b.json.dump=partial
    b.save(home/'committed.json',dict(payload='complete',writer_pid=os.getpid()))
    raise SystemExit(0)
if mode == 'collision':
    import binding as b
    b.save(home/'committed.json',dict(payload='replacement'))
    raise SystemExit(99)
if mode == 'orphan-family':
    child=subprocess.Popen([str(OWN.parents[3]/'python/.venv/bin/python'),'-I','-B',__file__,'stubborn-descendant',str(home)])
    wait_for(home/'descendant-ready')
    (home/'descendant.json').write_text(json.dumps(dict(pid=child.pid,pgid=os.getpgid(child.pid))))
if mode in ('ignore-term','stubborn-descendant'): signal.signal(signal.SIGTERM,signal.SIG_IGN)
if mode == 'family':
    child=subprocess.Popen([str(OWN.parents[3]/'python/.venv/bin/python'),'-I','-B',__file__,'descendant',str(home)])
    def terminate(_number,_frame):
        code=child.wait(timeout=2)
        (home/'descendant-reap.json').write_text(json.dumps(dict(pid=child.pid,raw_exit=code,directly_reaped=True)))
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,terminate)
    wait_for(home/'descendant-ready')
    (home/'descendant.json').write_text(json.dumps(dict(pid=child.pid,pgid=os.getpgid(child.pid))))
(home/('descendant-ready' if mode in ('descendant','stubborn-descendant') else 'ready')).write_text(json.dumps(dict(pid=os.getpid(),ppid=os.getppid(),pgid=os.getpgrp())))
if mode=='exit-zero': raise SystemExit(0)
while True: time.sleep(.05)
