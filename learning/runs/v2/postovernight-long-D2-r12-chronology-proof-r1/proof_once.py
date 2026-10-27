"""One source-intact discriminator for callback failure followed by cleanup signal."""
from pathlib import Path
from unittest.mock import patch
import json
import signal
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'learning/runs/v2/postovernight-long-D2-boundary-prepare-r12'))
import long_d2 as c
import lifecycle as life


def case(inject_cleanup_signal):
    now = [100.0]
    original = sys.getswitchinterval()
    real_set = sys.setswitchinterval
    latch = life.ProcessLatch()
    latch.deadline = 200.0
    callback_error = c.Stop('earlier callback integrity failure', 'resource_stop')
    injected = []
    def callback():
        raise callback_error
    def setting(value):
        if inject_cleanup_signal and value == original and not injected:
            injected.append(True)
            now[0] = 101.0
            latch.handle(signal.SIGTERM, None)
        real_set(value)
    guard = c.Guard(200.0, lambda: None, callback, None,
                    clock=lambda: now[0], rss=lambda: 1, peak=lambda: 1)
    try:
        with patch.object(c.time, 'monotonic', side_effect=lambda: now[0]), \
             patch.object(life, 'ACTIVE', latch), patch.object(sys, 'setswitchinterval', setting):
            try:
                guard.full_check(True)
            except BaseException as error:
                primary, descriptor = c.observed_failure(error, guard, 'worker')
                return dict(injected_cleanup_signal=inject_cleanup_signal,
                            callback_error_outcome=callback_error.outcome,
                            callback_raised_at=100.0,
                            propagated_outcome=getattr(error, 'outcome', None),
                            primary_outcome=primary.outcome,
                            descriptor=descriptor,
                            guard_failure_at=guard.failure_at,
                            guard_retains_callback_error=guard.failure is callback_error,
                            callback_in_exception_context=error.__context__ is callback_error,
                            first_cancel_at=latch.first_cancel_at,
                            interval_restored=sys.getswitchinterval() == original,
                            boundary_verdict=guard.boundaries[0]['verdict'])
            raise AssertionError('Failure was not raised')
    finally:
        if sys.getswitchinterval() != original:
            real_set(original)


control = case(False)
trigger = case(True)
assert control['primary_outcome'] == 'resource_stop' and control['descriptor']['timestamp'] == 100.0
assert control['guard_retains_callback_error']
assert trigger['primary_outcome'] == 'cancelled' and trigger['descriptor']['timestamp'] == 101.0
assert not trigger['guard_retains_callback_error'] and trigger['callback_in_exception_context']
assert control['interval_restored'] and trigger['interval_restored']
assert control['boundary_verdict'] == trigger['boundary_verdict'] == 'failed'
forbidden = [name for name in sys.modules if name.split('.')[0] in {'torch', 'numpy', 'dodge_rl'}]
assert not forbidden
value = dict(status='reproduced_primary_failure_chronology_regression', control=control,
             trigger=trigger, forbidden_imports=forbidden,
             limitations=['Modeled clock and direct ProcessLatch.handle call; no real OS signal, lifecycle or training evidence.',
                          'Frozen r12 source was imported without mutation. This is not a retry of its failed test suite.'])
with (HERE / 'result.json').open('x') as stream:
    json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps(value, sort_keys=True))
