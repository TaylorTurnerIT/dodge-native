"""Source-extracted discriminator; no candidate imports, native code, or processes."""
import ast
import json
import math
from pathlib import Path
import signal
import threading
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
CANDIDATE = HERE.parent / 'postovernight-long-D2-boundary-prepare-r3'

class Clock:
    def __init__(self):
        self.value = 100.0
    def monotonic(self):
        self.value += 0.001
        return self.value

clock = Clock()
life = SimpleNamespace(ACTIVE=None, CHANNEL=None)
ns = dict(time=clock, math=math, threading=threading, signal=signal, life=life)

def extract(filename, names):
    source = (CANDIDATE / filename).read_text()
    tree = ast.parse(source)
    selected = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    assert {n.name for n in selected} == set(names)
    text = '\n\n'.join(ast.get_source_segment(source, n) for n in selected) + '\n'
    (HERE / ('extracted-' + filename)).write_text(text)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(CANDIDATE / filename), 'exec'), ns)

extract('lifecycle.py', {'Stop', 'FailurePool'})
life.Stop = ns['Stop']
extract('long_d2.py', {'failure_outcome', 'outcome_fields', 'observed_failure', 'primary_error', 'record_primary_failure', 'worker_failure'})
life.POOL = ns['FailurePool'](90.0)
ack_calls = []
life.notify_failure = lambda *args: ack_calls.append(args)
result = ns['outcome_fields']('identity_or_lease_failure')
permission = dict(failed=False, acknowledged_until=None, ack_failed=False)
try:
    ns['worker_failure'](ValueError('injected genuine worker exception'), None, None, None, result, permission)
    observed = dict(unexpected_return=True)
except Exception as error:
    observed = dict(error_type=type(error).__name__, error=str(error), permission=permission,
                    pool_first=life.POOL.first, pool_until=life.POOL.until,
                    ack_calls=len(ack_calls), result=result, clock=clock.value)
print(json.dumps(observed, indent=2, sort_keys=True))
assert observed['error'] == 'Failure descriptor timestamp differs'
assert observed['ack_calls'] == 0 and observed['pool_first'] is None
assert result['first_local_failure']['timestamp'] < clock.value
print('CONFIRMED: ordinary worker failure throws before cleanup pool and executor ACK; initiating descriptor remains only in memory.')
