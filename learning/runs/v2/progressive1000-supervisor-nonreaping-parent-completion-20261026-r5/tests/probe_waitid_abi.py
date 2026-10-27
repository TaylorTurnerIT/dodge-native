"""Owned stdlib ABI diagnostic; preserve raw libc output and true wait exit."""
import ctypes
import errno
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
OWN=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(OWN))
import observe
PYTHON=str(OWN.parents[3]/'python/.venv/bin/python')
resource.setrlimit(resource.RLIMIT_CPU,(3,3))
signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('ABI probe 8-second bound')))
signal.alarm(8)
home=OWN/'tests/abi-probe';home.mkdir()
result=dict(scope='One owned stdlib child only; no runtime or campaign.')
with (home/'child.log').open('x') as log:
    proc=subprocess.Popen([PYTHON,'-I','-B',str(OWN/'tests/stdlib_child.py'),'exit-on-release',str(home)],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    result['pid']=proc.pid
    try:
        waitid=observe.nonreaping_waitid()
        end=time.monotonic()+4
        while not (home/'ready').exists():
            if time.monotonic()>=end: raise TimeoutError('ready')
            time.sleep(.005)
        def raw(pid):
            info=observe.DarwinSiginfo()
            ctypes.set_errno(0)
            rc=waitid(os.P_PID,pid,ctypes.byref(info),os.WEXITED|os.WNOHANG|os.WNOWAIT)
            return dict(result=rc,errno=ctypes.get_errno(),raw_hex=bytes(info).hex(),fields={n:getattr(info,n) for n in ('si_signo','si_errno','si_code','si_pid','si_uid','si_status')})
        result['running']=raw(proc.pid)
        result['wrong_pid']=raw(os.getpid())
        (home/'release').touch()
        while True:
            status=raw(proc.pid)
            if status['fields']['si_pid']: break
            if time.monotonic()>=end: raise TimeoutError('exit')
            time.sleep(.005)
        result['exited']=status
        result['repeat']=raw(proc.pid)
        result['popen_returncode_before_wait']=proc.returncode
    finally:
        (home/'release').touch(exist_ok=True)
        result['raw_reap_exit']=proc.wait(timeout=2)
        result['group_absent']=not observe.group_exists(proc.pid)
signal.alarm(0)
(OWN/'abi-probe-receipt.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps(result,sort_keys=True))
