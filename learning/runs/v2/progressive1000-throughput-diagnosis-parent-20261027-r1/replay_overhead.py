"""Measure saved harness work only; no Torch/native import or training."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RUN = ROOT / 'learning/runs/v2/progressive1000-control-retry-proposal-parent-20261027-r1'
SOURCE = ROOT / 'learning/runs/v2/progressive1000-shared-runtime-staticmethod-repair-sol-20261026-r2'


def strict_read(path):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(key)
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique)


def measure(callback, count):
    values = []
    for _ in range(3):
        start = time.perf_counter()
        for _ in range(count):
            callback()
        values.append((time.perf_counter()-start)/count)
    return dict(calls_per_trial=count, trials=3, median_seconds_per_call=statistics.median(values), trial_seconds_per_call=values)


def main():
    target = ROOT / 'learning/runs/v2-orchestration/state.json'
    raw = target.read_bytes()
    loaded = strict_read(target)
    original = measure(lambda: strict_read(target).get('active_long_campaign'), 200)
    cached = measure(lambda: target.read_bytes() == raw, 200)
    # Four guard calls per decision, four per optimizer minibatch, two per KL
    # minibatch, plus epoch/entry/exit guards. Reset guards add further calls.
    floor = 256*4 + 128*4 + 128*2 + 4
    original['estimated_seconds_per_update_guard_floor'] = floor*original['median_seconds_per_call']
    cached['estimated_seconds_per_update_guard_floor'] = floor*cached['median_seconds_per_call']
    snapshots = {}
    event_counts = {}
    with (RUN / 'worker-output/training-events.jsonl').open() as stream:
        for line in stream:
            row = json.loads(line)
            event_counts[row['kind']] = event_counts.get(row['kind'], 0)+1
            if row['kind'] == 'collection_complete_before_PPO' and row['global_update'] in (1, 12, 24, 44):
                snapshots[str(row['global_update'])] = row['snapshot']
    snapshot_costs = {}
    for local, snapshot in snapshots.items():
        snapshot_costs[local] = dict(bytes=len(json.dumps(snapshot)),
            copy_and_encode=measure(lambda: json.dumps(copy.deepcopy(snapshot), sort_keys=True, allow_nan=False), 5))
    # Execute only the original stdlib emit definition, preserving its exact code.
    module = ast.parse((SOURCE / 'worker.py').read_text())
    emit_node = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'emit')
    ns = dict(json=json, os=os)
    exec(compile(ast.Module(body=[emit_node], type_ignores=[]), str(SOURCE / 'worker.py'), 'exec'), ns)
    with (HERE / 'fsync-replay.jsonl').open('x') as output:
        fsync_cost = measure(lambda: ns['emit'](output, dict(kind='returned_step_cost', update=1,
            decision=1, elapsed_raw_frames=[4]*64)), 100)
    metrics = [json.loads(line) for line in (RUN / 'worker-output/training-metrics.jsonl').read_text().splitlines()]
    windows = []
    for first, last in ((1, 12), (13, 24), (25, 36), (37, 44)):
        before = metrics[first-2]['elapsed_seconds'] if first > 1 else 0
        seconds = metrics[last-1]['elapsed_seconds']-before
        windows.append(dict(first=first, last=last, seconds=seconds, seconds_per_update=seconds/(last-first+1)))
    receipt = dict(schema='progressive1000_offline_overhead_replay_v1', training_runs=0,
        torch_or_native_imported=False, ledger_bytes=len(raw), ledger_sha256=hashlib.sha256(raw).hexdigest(),
        ledger_parse=original, unchanged_bytes_check=cached, guards_per_update_floor=floor,
        guard_scope='Current ledger and host replay; does not establish historical causal attribution.',
        original_emit_fsync=fsync_cost, snapshot_costs=snapshot_costs, saved_event_counts=event_counts,
        saved_update_windows=windows,
        limitation='Historical run has no phase timers. External load, thermals, GPU and other causes remain unmeasured.')
    (HERE / 'offline-replay.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
