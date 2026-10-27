#!/usr/bin/env python3
"""Pure stdlib discriminator for frozen r3 Execution.monitor cleanup starvation.

Imports frozen r3 modules read-only (no bytecode written). Uses the REAL
Execution.monitor/fail/pool code with a stub guard and a stub Child whose
report is preset. No ML/native import, no worker/supervisor launch, no groups.

Each scenario runs the real monitor thread for a bounded window and reports
whether the cleanup block (cleanup_complete) was reached, and every exception
the monitor's outer `except BaseException` swallowed.
"""
import json
import sys
import threading
import time
import types
from pathlib import Path

FROZEN = Path(sys.argv[1] if len(sys.argv) > 1 else '/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/postovernight-long-D2-boundary-prepare-r3')
sys.dont_write_bytecode = True
sys.path.insert(0, str(FROZEN))
import lifecycle as life          # noqa: E402
import long_d2 as c              # noqa: E402
import long_d2_executor as e     # noqa: E402


class StubProc:
    pid = 2 ** 22 - 7  # not a real owned pid; no signal is ever sent (no groups)


class StubGuard:
    def __init__(self):
        self.failure = None
        self.failure_at = None
        self.last_sample = time.monotonic() + 3600


def scenario(name, returncode, pre_fail, window=1.0):
    life.ACTIVE = None
    t0 = time.monotonic() - 0.5
    ex = e.Execution(t0, {}, None)   # real __init__; installs latch (disarmed below)
    signal_disarm()
    ex.guard = StubGuard()
    ex.child = types.SimpleNamespace(process=StubProc(), report=dict(
        pid=StubProc.pid, raw_wait_status=returncode << 8, returncode=returncode,
        reaped_by=0, direct_child_reaped=True, observed_monotonic=time.monotonic()),
        poll=lambda: None)
    ex.child.poll = lambda r=ex.child.report: r
    ex.recovery_proven = True
    ex.groups = {}
    errors = []
    real_fail = e.Execution.fail

    def logging_fail(self, error, at=None):
        try:
            return real_fail(self, error, at)
        except BaseException as exc:
            errors.append(f'{type(exc).__name__}: {exc}')
            raise
    e.Execution.fail = logging_fail
    try:
        if pre_fail:
            ex.pool.fail('peer failure first', time.monotonic() - 0.01)  # e.g. inner ACKed failure
        th = threading.Thread(target=ex.monitor, daemon=True)
        th.start()
        end = time.monotonic() + window
        while time.monotonic() < end and not ex.cleanup_complete:
            time.sleep(0.01)
        result = dict(scenario=name, inner_returncode=returncode, pool_failed_before_monitor=pre_fail,
                      cleanup_complete=ex.cleanup_complete,
                      swallowed_monitor_exception_count=len(errors),
                      swallowed_distinct=sorted(set(errors)),
                      pool_reason=ex.pool.reason, window_seconds=window)
        ex.stop.set()
        th.join(1)
        return result
    finally:
        e.Execution.fail = real_fail


def signal_disarm():
    import signal
    signal.setitimer(signal.ITIMER_REAL, 0)


def main():
    out = []
    out.append(scenario('inner_exit_0_control', 0, pre_fail=True))
    out.append(scenario('inner_exit_2_control', 2, pre_fail=True))
    out.append(scenario('inner_exit_1_after_peer_failure', 1, pre_fail=True))
    out.append(scenario('inner_exit_1_first_observation', 1, pre_fail=False))
    out.append(scenario('inner_exit_7_after_peer_failure', 7, pre_fail=True))
    print(json.dumps(dict(source=str(FROZEN / 'long_d2_executor.py'), results=out), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
