"""Owned stdlib probe: block an ordinary read in the final post-watchdog pin check.

Run only as a subprocess. The parent owns the hard timeout and kills only this
probe's direct executor after recording survival beyond the shared cap.
"""
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
PREP = HERE.parent / 'postovernight-long-D2-prepare-r3'
sys.path.insert(0, str(PREP))
import synthetic as fixture

root = Path(sys.argv[1]).resolve()
block = sys.argv[2] == 'block'
original_install = fixture.install_hooks

def install(root, options, role):
    trigger, event = original_install(root, options, role)
    if role != 'outer':
        return trigger, event
    original_authority = fixture.e.Execution.authority
    original_verify = fixture.c.verify_files
    active = [None]
    fired = [False]
    def authority(execution, force=False):
        if (force and execution.watchdog is not None and not execution.watchdog.is_alive()
                and execution.pool.until is None
                and (root / 'execution/acceptance-receipt.json').exists()):
            active[0] = execution
        return original_authority(execution, force)
    def verify(pins):
        execution = active[0]
        if execution is not None and not fired[0]:
            fired[0] = True
            info = dict(boundary='final authority(True), after watchdog join and endpoint close',
                        actual_verifier_invoked=True, block=block, pid=os.getpid(),
                        t0=execution.t0, normal_deadline=execution.t0+fixture.e.NORMAL_SECONDS,
                        latest_shared_cap=execution.t0+fixture.e.NORMAL_SECONDS+10,
                        monotonic=time.monotonic(), latch_phase=execution.latch.phase,
                        live_owned_threads=[t.name for t in threading.enumerate() if t.name.startswith('long-D2-')],
                        watchdog_alive=execution.watchdog.is_alive(),
                        guard_threads_alive=[t.is_alive() for t in (execution.guard.thread, execution.guard.verify_thread)],
                        timer=signal.getitimer(signal.ITIMER_REAL), groups=execution.groups,
                        ML_imports=[n for n in sys.modules if n.split('.')[0] in ('torch','numpy','dodge_rl')])
            (root / 'final-read-event.json').write_text(json.dumps(info, indent=2) + '\n')
            if block:
                read_fd, write_fd = os.pipe()
                # This is an ordinary interruptible pipe read, not an
                # uninterruptible kernel task. The write endpoint remains open.
                os.read(read_fd, 1)
                os.close(read_fd)
                os.close(write_fd)
        return original_verify(pins)
    fixture.e.Execution.authority = authority
    fixture.c.verify_files = verify
    return trigger, event

fixture.install_hooks = install
sys.argv = [str(PREP / 'synthetic.py'), 'executor', '--root', str(root)]
fixture.main()
