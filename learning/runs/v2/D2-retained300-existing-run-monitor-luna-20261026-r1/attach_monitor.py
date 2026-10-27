#!/usr/bin/env python3
"""Read-only monitor for the already-running D2 retained-300 campaign."""
import json
import os
import pathlib
import subprocess
import time

ROOT = pathlib.Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
OUT = ROOT / 'learning/runs/v2/D2-retained300-existing-run-monitor-luna-20261026-r1'
OBS = ROOT / 'learning/runs/v2/D2-retained300-execution-observer-parent-20261026-r1'
RUN = ROOT / 'learning/runs/v2/D2-retained300-continuation-20261026-r1'
REG = ROOT / 'learning/runs/v2/D2-retained300-continuation-freeze-20261026-r5/registration.json'
T0 = 622809.591901916
DEADLINE = T0 + 1800.0
PIDS = (26658, 26659, 26662)
POLL = 12.0
PUBLICATION_ALLOWANCE = 75.0

def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None

def proc_snapshot():
    p = subprocess.run(['ps', '-p', ','.join(map(str, PIDS)), '-o', 'pid=,ppid=,pgid=,etime=,stat=,command='], text=True, capture_output=True)
    return p.stdout.strip().splitlines()

def latest_metrics():
    p = RUN / 'training-metrics.jsonl'
    rows = []
    try:
        for line in p.open():
            try: rows.append(json.loads(line))
            except ValueError: continue
    except OSError: pass
    return rows[-1] if rows else None

def candidate_table():
    rows = []
    for cp in sorted(RUN.glob('checkpoint-*-candidate.pt')):
        meta = read_json(pathlib.Path(str(cp) + '.json')) or {}
        rows.append({'checkpoint': cp.name, 'present': cp.exists(), 'bytes': cp.stat().st_size if cp.exists() else None,
                     'sha256': meta.get('sha256'), 'survival': 'present; provisional pending parent acceptance',
                     'death_cause': None})
    return rows

def snapshot():
    resources = []
    try:
        with (OBS / 'resources.jsonl').open() as f:
            for line in f:
                try: resources.append(json.loads(line))
                except ValueError: pass
    except OSError: pass
    last_res = resources[-1] if resources else None
    return {
        'lexical_monotonic': time.monotonic(),
        'outer_deadline_monotonic': DEADLINE,
        'observer_observation': read_json(OBS / 'observation.json'),
        'observer_error': read_json(OBS / 'observer-error.json'),
        'worker_launch': read_json(RUN / 'worker-launch.json'),
        'worker_result': read_json(RUN / 'worker-result.json'),
        'execution_result': read_json(RUN / 'execution-result.json'),
        'latest_metric': latest_metrics(),
        'candidate_table': candidate_table(),
        'resource_samples': len(resources),
        'latest_resource': last_res,
        'processes': proc_snapshot(),
    }

def main():
    log = (OUT / 'attach_monitor.log').open('a', buffering=1)
    start = time.monotonic()
    absent_since = None
    while True:
        s = snapshot()
        now = s['lexical_monotonic']
        terminal_receipt = s['observer_observation'] is not None or s['observer_error'] is not None
        live = bool(s['processes'])
        if not live:
            if absent_since is None: absent_since = now
        else:
            absent_since = None
        log.write(json.dumps({k:s[k] for k in ('lexical_monotonic','latest_metric','resource_samples','processes')}, default=str) + '\n')
        reason = None
        if terminal_receipt: reason = 'observer terminal receipt present'
        elif not live and absent_since is not None and now - absent_since >= PUBLICATION_ALLOWANCE: reason = 'named processes absent; publication allowance elapsed'
        elif now >= DEADLINE:
            if live: reason = 'original outer deadline reached with named processes still present; stop without signaling'
            else: reason = 'original outer deadline reached; processes absent'
        if reason:
            s['monitor_terminal_reason'] = reason
            s['monitor_started_monotonic'] = start
            s['monitor_finished_monotonic'] = now
            s['registration_sha256_expected'] = '8a60dc80f1ebe03c43bf18eebf75199e14f207b677570ac2d6d4368ddfcb0f79'
            (OUT / 'terminal-report.json').write_text(json.dumps(s, indent=2, sort_keys=True) + '\n')
            log.write(json.dumps({'terminal': reason, 'monotonic': now}) + '\n')
            return
        time.sleep(POLL)

if __name__ == '__main__': main()
