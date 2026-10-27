"""Fresh targeted R3 stdlib OS controls. Fail on the first unexpected result."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
PREP = HERE.parent / 'postovernight-long-D2-prepare-r3'
sys.path.insert(0, str(PREP))
import run_checks as checks

directory = HERE / 'targeted-controls'
directory.mkdir()
(directory / 'tested-sources.json').write_text(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in PREP.glob('*.py')}, indent=2) + '\n')
cases = []
for mode in ('closure', 'pass'):
    for phase, mutation in (
        ('inner:hash-after', 'cancel'), ('outer:receipt-after', 'input'),
        ('inner:guard-close-after', 'SIGINT'), ('outer:guard-close-after', 'SIGTERM'),
        ('outer:watchdog-join-after', 'cancel'), ('outer:before-D', 'input'),
        ('inner:pending-before', 'SIGTERM'), ('outer:pending-before', 'SIGINT'),
        ('inner:exit-gap', 'forward_SIGTERM'), ('inner:before-D', 'symlink'),
        ('inner:before-D', 'extra'), ('inner:before-D', 'binding')):
        cases.append((mode + '-' + phase.replace(':', '-') + '-' + mutation,
                      dict(mode=mode, phase=phase, mutation=mutation), 1))
    cases.append((mode + '-r3-short-late-terminal',
                  dict(mode=mode, phase='inner:terminal-after', mutation='none', delay=5,
                       worker_seconds=3, inner_seconds=4, outer_seconds=6), 1))
cases.extend([
    ('wedged-worker-separate-session', dict(mode='wedged', worker_seconds=2, inner_seconds=3, outer_seconds=4), 1),
    ('registration-race', dict(mode='blocked', phase='inner:spawn-before-registration', mutation='crash',
                               worker_seconds=2, inner_seconds=3, outer_seconds=4), 1),
    ('inner-death-worker-lives', dict(mode='blocked', phase='inner:during-worker', mutation='crash',
                                     worker_seconds=2, inner_seconds=3, outer_seconds=4), 1),
])
results = []
started = time.monotonic()
try:
    for name, options, expected in cases:
        results.append(checks.case(directory, name, options, expected))
except BaseException as error:
    (directory / 'stopped.json').write_text(json.dumps(dict(error=repr(error), completed=len(results), failed_case=name), indent=2) + '\n')
    raise
finally:
    (directory / 'summary.json').write_text(json.dumps(dict(results=results, completed=len(results), planned=len(cases),
        elapsed_seconds=time.monotonic()-started, ML_imports=[n for n in sys.modules if n.split('.')[0] in ('torch','numpy','dodge_rl')]), indent=2) + '\n')
