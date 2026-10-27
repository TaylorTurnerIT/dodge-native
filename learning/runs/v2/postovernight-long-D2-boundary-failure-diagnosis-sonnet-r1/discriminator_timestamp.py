#!/usr/bin/env python3
"""Pure stdlib discriminator: do explicit-`at` FailurePool.fail call sites agree
with the first_failure_descriptor that observed_failure attaches?

Real frozen r3 functions only: lifecycle.FailurePool.fail, lifecycle.notify_failure,
long_d2.observed_failure, long_d2.worker_failure. No channel, process, ML or native
import. A single process-local clock; no timer is armed.
"""
import json
import sys
import time
from pathlib import Path

FROZEN = Path(sys.argv[1] if len(sys.argv) > 1 else '/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/postovernight-long-D2-boundary-prepare-r3')
sys.dont_write_bytecode = True
sys.path.insert(0, str(FROZEN))
import lifecycle as life   # noqa: E402
import long_d2 as c        # noqa: E402


def fresh(t0_back=1.0):
    life.ACTIVE = None
    life.CHANNEL = None
    life.POOL = life.FailurePool(time.monotonic() - t0_back)
    return life.POOL


def attempt(label, fn):
    try:
        value = fn()
        return dict(site=label, raised=None, returned=repr(value)[:80])
    except BaseException as error:
        return dict(site=label, raised=f'{type(error).__name__}: {error}')


def site_worker_failure_plain_exception():
    pool = fresh()
    result = c.outcome_fields('identity_or_lease_failure')
    permission = dict(failed=False, acknowledged_until=None, ack_failed=False)
    return c.worker_failure(RuntimeError('plain worker exception'), None, None, None, result, permission), pool.first_global


def site_worker_failure_stop():
    pool = fresh()
    result = c.outcome_fields('identity_or_lease_failure')
    permission = dict(failed=False, acknowledged_until=None, ack_failed=False)
    return c.worker_failure(c.Stop('stop exception', 'safety_stop'), None, None, None, result, permission), pool.first_global


def site_notify_failure_error_with_descriptor_no_at():
    # Worker main(): `life.notify_failure(error)` where `error` was already
    # processed by worker_failure/primary_error and so carries a descriptor.
    pool = fresh()
    error, _ = c.observed_failure(RuntimeError('already described'), None, 'worker')
    time.sleep(0.001)
    life.CHANNEL = None
    return life.notify_failure(error), pool.first_global


def site_notify_failure_error_with_descriptor_explicit_at():
    # Inner supervise_owned: notify_failure(error, descriptor.timestamp).
    pool = fresh()
    error, descriptor = c.observed_failure(RuntimeError('inner described'), None, 'inner')
    time.sleep(0.001)
    life.CHANNEL = None
    return life.notify_failure(error, descriptor['timestamp']), pool.first_global


def site_pool_fail_descriptor_default_at():
    # The r3 repair: reason carries descriptor, at omitted.
    pool = fresh()
    error, _ = c.observed_failure(RuntimeError('r3 default'), None, 'worker')
    time.sleep(0.001)
    return pool.fail(error), pool.first_global


def site_pool_fail_descriptor_with_fresh_now_at():
    # What worker_failure / notify_failure(at=None) actually pass: explicit fresh now.
    pool = fresh()
    error, _ = c.observed_failure(RuntimeError('r3 explicit now'), None, 'worker')
    time.sleep(0.001)
    return pool.fail(error, time.monotonic()), pool.first_global


def main():
    sites = [
        ('worker_failure(plain RuntimeError) [long_d2.py:938]', site_worker_failure_plain_exception),
        ('worker_failure(Stop) [long_d2.py:938]', site_worker_failure_stop),
        ('notify_failure(error_with_descriptor) no at [lifecycle.py:228; long_d2.py:1374]', site_notify_failure_error_with_descriptor_no_at),
        ('notify_failure(error, descriptor.timestamp) [long_d2.py:1316]', site_notify_failure_error_with_descriptor_explicit_at),
        ('pool.fail(error_with_descriptor) default at [r3 repair]', site_pool_fail_descriptor_default_at),
        ('pool.fail(error_with_descriptor, fresh now) [explicit conflict]', site_pool_fail_descriptor_with_fresh_now_at),
    ]
    print(json.dumps(dict(source=str(FROZEN), results=[attempt(*s) for s in sites]), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
