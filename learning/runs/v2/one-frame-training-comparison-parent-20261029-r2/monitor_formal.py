"""Read only formal execution receipts and cost counters; never inspect D9 outcomes."""
from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PACKAGE = ROOT / 'learning/runs/v2/one-frame-training-comparison-luna-20261029-r2'
RUN_ID = PACKAGE.name


def read(path):
    return json.loads(path.read_bytes())


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return None


def main():
    exit_path = PACKAGE / 'execution-exit.json'
    if exit_path.is_file():
        print(json.dumps({'phase': 'terminal_parent_audit_required', 'execution_exit': read(exit_path)}, sort_keys=True))
        return
    result = {'run_id': RUN_ID, 'phase': 'not_dispatched', 'arms': {}}
    parent = PACKAGE / 'parent-execution.json'
    if parent.is_file():
        receipt = read(parent)
        result.update(phase='running', observer_pid=receipt['observer_pid'],
                      observer_alive=alive(receipt['observer_pid']))
    launch = PACKAGE / 'dispatch' / RUN_ID / 'worker-launch.json'
    if launch.is_file():
        receipt = read(launch)
        result.update(worker_pid=receipt['worker_pid'], worker_alive=alive(receipt['worker_pid']))
    journal = PACKAGE / 'worker-output/training.jsonl'
    if journal.is_file():
        if journal.stat().st_size > 10 * 1024 * 1024:
            raise RuntimeError('training counter journal exceeds bounded monitor read')
        for line in journal.read_bytes().splitlines(keepends=True):
            if not line.endswith(b'\n'):
                continue
            row = json.loads(line)
            if row.get('kind') == 'update':
                arm = result['arms'].setdefault(row['arm'], {'updates': 0, 'gameplay_frames': 0,
                    'startup_frames': 0, 'policy_decisions': 0, 'optimizer_steps': 0,
                    'latest_saved_gameplay_boundary': None})
                arm['updates'] += 1
                arm['gameplay_frames'] += row['gameplay_frames']
                arm['startup_frames'] += row['startup_frames']
                arm['policy_decisions'] += 64 * row['decisions']
                arm['optimizer_steps'] += row['optimizer_steps']
            elif row.get('kind') == 'recovery_checkpoint':
                arm = result['arms'].get(row['arm'])
                if arm is not None:
                    arm['latest_saved_gameplay_boundary'] = row['snapshot']['recovery_boundary_gameplay_frames']
    resources = PACKAGE / 'worker-output/resources.jsonl'
    if resources.is_file():
        with resources.open('rb') as stream:
            size = stream.seek(0, os.SEEK_END)
            stream.seek(max(0, size - 65536))
            lines = stream.read().splitlines(keepends=True)
        for line in reversed(lines):
            if line.endswith(b'\n'):
                row = json.loads(line)
                result['latest_resource_sample'] = {k: row[k] for k in
                    ('elapsed_seconds', 'rss_bytes', 'mps_driver_bytes', 'arm') if k in row}
                break
    # File names reveal completed group counts without opening any D9 row data.
    result['completed_evaluation_groups'] = sum(
        1 for path in (PACKAGE / 'worker-output').glob('*_sampled.json') if path.is_file())
    result['evaluation_group_target'] = 6
    result['gameplay_frame_target_per_arm'] = 11796480
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
