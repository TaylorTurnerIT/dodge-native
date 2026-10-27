"""Independent old-regression checks with actual Guard and an owned OS worker."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import signal
import sys
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PREP = HERE.parent / 'postovernight-long-D2-prepare-r2'
sys.path.insert(0, str(PREP))
import publication_probes as probes
c = probes.c
kind, mode = sys.argv[1:3]
root = HERE / ('old-' + kind + '-' + mode)
real_stop, real_verify = c.stop_owned, c.verify_files
stopped = fired = False

def mark(kind):
    (root / 'independent-trigger.json').write_text(json.dumps(dict(kind=kind, monotonic=time.monotonic())) + '\n')

def stop(process):
    global stopped, fired
    receipt = real_stop(process)
    stopped = True
    if kind == 'unproven-group':
        receipt['group_empty'] = False
        fired = True
        mark(kind)
    if kind == 'deferred-cleanup-cancel' and not fired:
        fired = True
        mark(kind)
        os.kill(os.getpid(), signal.SIGINT)
        os.kill(os.getpid(), signal.SIGTERM)
    return receipt

def verify(pins):
    global fired
    real_verify(pins)
    if stopped and not fired and kind in ('late-final-verify', 'deferred-final-verify-cancel'):
        fired = True
        mark(kind)
        if kind == 'late-final-verify':
            time.sleep(1.1)
        else:
            os.kill(os.getpid(), signal.SIGINT)
            os.kill(os.getpid(), signal.SIGTERM)

with ExitStack() as stack:
    stack.enter_context(patch.object(c, 'stop_owned', side_effect=stop))
    stack.enter_context(patch.object(c, 'verify_files', side_effect=verify))
    if kind.startswith('late-') or kind == 'blocked-worker':
        stack.enter_context(patch.object(c, 'BUDGET', .8))
    phase = {'late-artifact-hash':'hash-before', 'late-manifest-write':'manifest-after',
             'late-terminal-write':'terminal-after', 'late-return':'alarm-exit'}.get(kind,'no-existing-trigger')
    value = probes.scenario(root, phase=phase, mutation='none', mode='blocked' if kind=='blocked-worker' else mode,
                            delay=1.1 if phase != 'no-existing-trigger' else 0)
value['independent_kind'] = kind
value['independent_trigger_fired'] = fired or value['trigger_fired'] or kind=='blocked-worker'
(root / 'independent-observation.json').write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
assert value['independent_trigger_fired'], 'injection did not reach target'
assert value['return_code'] == 1, value
assert value['terminal']['experiment_status'] == 'failed', value
assert not value['manifest_available'], value
assert value['owned_group_positively_absent'], value
assert not value['ML_imports'], value
assert all(not x['open_output_writers'] for x in value['artifact_hash_writer_checks']), value
if 'cancel' in kind:
    run = c.read_json(root / 'campaign/long-run-result.json')
    assert run['cancellation_requests'] == 2, run
print(json.dumps(dict(kind=kind, mode=mode, controller_return_code=value['return_code'], assertions_passed=True)))
