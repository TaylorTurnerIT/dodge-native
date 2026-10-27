"""Finite owned stdlib stand-in at the real process_rows subprocess boundary."""
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time

OWN = Path(__file__).resolve().parents[1]
home = Path(sys.argv[1])
assert home.resolve().is_relative_to(OWN/'tests')
resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
signal.signal(signal.SIGALRM, lambda *_: os._exit(124))
signal.alarm(8)
plan = json.loads((home/'plan.json').read_text())
assert 0 <= plan['delay_seconds'] <= 4 and plan['exit_code'] in (0, 23)
(home/'ready.json').write_text(json.dumps(dict(pid=os.getpid(), ppid=os.getppid(),
    pgid=os.getpgrp(), started_monotonic=time.monotonic(), plan=plan)))
time.sleep(plan['delay_seconds'])
if plan['exit_code']:
    print('owned synthetic ps command failure', file=sys.stderr)
    raise SystemExit(plan['exit_code'])
# Keep this same directly owned PID/group and return genuine current ps rows.
os.execv('/bin/ps', ['/bin/ps', '-axo', 'pid=,ppid=,pgid=,rss=,lstart=,command='])
