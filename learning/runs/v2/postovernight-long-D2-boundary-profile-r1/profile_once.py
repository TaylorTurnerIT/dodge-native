"""One diagnostic: initial boundary, then one profiled contended boundary."""
import time
START = time.monotonic()
from pathlib import Path
import cProfile
import json
import os
import pstats
import sys
import threading
import traceback

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[3]
CANDIDATE = WORKSPACE / 'learning/runs/v2/postovernight-long-D2-boundary-prepare-r11'
sys.path.insert(0, str(CANDIDATE))
import long_d2 as c
import lifecycle as life
import boundary_integrity as integrity


def main():
    output = HERE / 'output'
    output.mkdir()
    capsule = CANDIDATE / 'capsule-final'
    context = c.capsule_context(capsule, verify_inputs=False)
    life.POOL = life.FailurePool(START, 60)
    latch = life.ProcessLatch()
    latch.install(START + 60)
    stop = threading.Event()
    contender = guard = None
    profiler = cProfile.Profile()
    result = dict(status='failed', diagnostic_only=True, ML_imports=False,
                  genuine_runtime_check_claimed=False, MPS_driver_observed=False)
    code = 1
    try:
        guard = c.Guard(START + 60, latch.check,
                        lambda: integrity.verify(context, capsule), None)
        guard.start()
        def contend():
            number = 1
            while not stop.is_set():
                for _ in range(12000):
                    number = (number * 1664525 + 1013904223) & 0xffffffff
        contender = threading.Thread(target=contend, name='profile-python-CPU-contender')
        life.start_thread(contender)
        profiler.enable()
        guard.check(force=True)
        profiler.disable()
        stop.set()
        contender.join(timeout=life.remaining(START + 60, .5))
        c.require(not contender.is_alive(), 'Profile contender survived')
        guard.close()
        result['status'] = 'completed_diagnostic_not_validation'
        code = 0
    except BaseException as error:
        result.update(error=repr(error), traceback=traceback.format_exc())
    finally:
        profiler.disable()
        stop.set()
        if contender is not None:
            contender.join(timeout=.5)
        if guard is not None:
            guard.event.set()
            if guard.thread is not None:
                guard.thread.join(timeout=.5)
        stats = []
        for (filename, line, name), values in pstats.Stats(profiler).stats.items():
            primitive, calls, own, cumulative, _ = values
            stats.append(dict(filename=filename, line=line, function=name,
                              primitive_calls=primitive, calls=calls,
                              own_seconds=own, cumulative_seconds=cumulative))
        stats.sort(key=lambda row: row['cumulative_seconds'], reverse=True)
        c.save(output / 'function-stats.json', stats)
        result.update(elapsed_seconds=time.monotonic() - START,
                      boundaries=[] if guard is None else guard.boundaries,
                      resources=None if guard is None else guard.receipt(),
                      contender_absent=contender is None or not contender.is_alive(),
                      sampler_absent=guard is None or guard.thread is None or not guard.thread.is_alive(),
                      forbidden_modules=[name for name in sys.modules if name.split('.')[0] in {'torch','numpy','dodge_rl'}],
                      limitations=['cProfile changes timing; function costs are diagnostic, not a benchmark or reliability proof.',
                                   'Exactly one initial uncontented boundary and one contended boundary; no R/A endpoint pass or twelve-update stress.',
                                   'Thread CPU versus wall does not uniquely identify GIL, storage or scheduler attribution.'])
        c.save(output / 'result.json', result)
        if result['forbidden_modules'] or not result['contender_absent'] or not result['sampler_absent']:
            code = 1
    os._exit(code)


if __name__ == '__main__':
    main()
