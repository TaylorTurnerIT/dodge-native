"""One fixed-order switch-interval diagnostic; frozen r11 source stays intact."""
import time
START = time.monotonic()
from pathlib import Path
import json
import math
import os
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
    lease = output / 'synthetic-safety-lease.json'
    c.save(lease, {'active_long_campaign': context[-1]})
    original = sys.getswitchinterval()
    stop = threading.Event()
    burn = guard = None
    passes = []
    result = dict(status='failed', diagnostic_only=True, retries=0,
                  genuine_runtime_check_claimed=False, MPS_driver_observed=False)
    code = 1
    try:
        c.require(math.isclose(original, .005, rel_tol=0, abs_tol=1e-12),
                  'Unexpected baseline switch interval; no substituted setting')
        def safety():
            latch.check()
            c.assert_lease(lease, context[-1])
        guard = c.Guard(START + 60, safety,
                        lambda: integrity.verify(context, capsule), None)
        guard.start()
        c.require(len(guard.boundaries) == 1, 'Initial boundary count differs')
        passes.append(dict(label='B0-uncontended', boundary_sequence=0,
                           switch_interval_before=original,
                           switch_interval_during=sys.getswitchinterval(),
                           switch_interval_after=sys.getswitchinterval()))
        def contend():
            n=1
            while not stop.is_set():
                for _ in range(12000):n=(n*1664525+1013904223)&0xffffffff
        burn = threading.Thread(target=contend, name='validation-python-CPU-contender')
        life.start_thread(burn)
        for label, interval in [('A1', .005), ('B1', .0001), ('A2', .005), ('B2', .0001)]:
            row = dict(label=label, requested_switch_interval=interval,
                       switch_interval_before=sys.getswitchinterval(),
                       boundary_sequence=len(guard.boundaries))
            passes.append(row)
            c.require(row['switch_interval_before'] == original, 'Interval leaked before pass')
            try:
                try:
                    sys.setswitchinterval(interval)
                    row['switch_interval_during'] = sys.getswitchinterval()
                    c.require(math.isclose(row['switch_interval_during'], interval,
                                           rel_tol=0, abs_tol=1e-12), 'Interval not installed')
                    guard.check(force=True)
                finally:
                    sys.setswitchinterval(original)
            finally:
                if sys.getswitchinterval() != original:
                    sys.setswitchinterval(original)
                row['switch_interval_after'] = sys.getswitchinterval()
            c.require(row['switch_interval_after'] == original, 'Interval not restored')
            boundary = guard.boundaries[row['boundary_sequence']]
            c.require(boundary['verdict'] == 'passed' and boundary['files'] == 273
                      and boundary['bytes'] == 47527648, 'Boundary work differs')
            c.require(guard.maximum_sample_gap < .5, 'Probe sample gap reached 0.5s')
            if label.startswith('B'):
                preceding = guard.boundaries[row['boundary_sequence'] - 1]
                row['paired_speed_ratio'] = preceding['duration_seconds'] / boundary['duration_seconds']
                if boundary['duration_seconds'] >= 1 or row['paired_speed_ratio'] < 10:
                    result.update(status='falsified_probe_criterion',
                                  stop_reason='First short-interval pass failed the fixed <1s and >=10x criterion')
                    break
        stop.set()
        burn.join(timeout=life.remaining(START + 60, .5))
        c.require(not burn.is_alive(), 'Probe contender survived')
        guard.close()
        if result['status'] != 'falsified_probe_criterion':
            c.require(len(passes) == 5 and len(guard.boundaries) == 5, 'Fixed probe incomplete')
            defaults = [guard.boundaries[row['boundary_sequence']]['duration_seconds']
                        for row in passes if row['label'] in ('A1', 'A2')]
            if all(value >= 4 for value in defaults):
                result['status'] = 'supported_probe_only'
                code = 0
            else:
                result.update(status='inconclusive_probe_only',
                              stop_reason='At least one default pass was below the preregistered 4s reproduction floor')
                code = 2
    except BaseException as error:
        result.update(status='failed', error=repr(error), traceback=traceback.format_exc())
    finally:
        try:
            sys.setswitchinterval(original)
        finally:
            if sys.getswitchinterval() != original:
                sys.setswitchinterval(original)
        stop.set()
        if burn is not None:
            burn.join(timeout=.5)
        if guard is not None:
            guard.event.set()
            if guard.thread is not None:
                guard.thread.join(timeout=.5)
        result.update(elapsed_seconds=time.monotonic() - START,
                      original_switch_interval=original,
                      final_switch_interval=sys.getswitchinterval(),
                      passes=passes, boundaries=[] if guard is None else guard.boundaries,
                      resources=None if guard is None else guard.receipt(),
                      contender_absent=burn is None or not burn.is_alive(),
                      sampler_absent=guard is None or guard.thread is None or not guard.thread.is_alive(),
                      forbidden_modules=[name for name in sys.modules
                          if name.split('.')[0] in {'torch', 'numpy', 'dodge_rl'}],
                      limitations=[
                          'This is a fixed-order scheduling intervention, not a foundation stress retry or production benchmark.',
                          'The interval is process-global and affects both contender and monitor; no unique GIL-wait attribution is claimed.',
                          'No genuine legacy/runtime/origin callback, R/A endpoint campaign, ML import, MPS observation or training ran.',
                          'Five boundaries do not establish reliability, production speedup, continuous immutability or memory attestation.'
                      ])
        if (result['forbidden_modules'] or not result['contender_absent']
                or not result['sampler_absent'] or result['final_switch_interval'] != original):
            result['status'] = 'failed'
            code = 1
        c.save(output / 'result.json', result)
    os._exit(code)


if __name__ == '__main__':
    main()
