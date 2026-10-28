"""Read-only bounded alert command for one remaining run; completion wakes the controlling thread.

It never signals training, changes caps, clears leases, or launches another arm.
The launcher's own observer ownership and direct wait remain independent.
"""
import argparse
import json
from pathlib import Path
import time

PACKAGE = Path(__file__).resolve().parent


def assess(row, elapsed, work_seconds, total_updates, stale_seconds=120):
    if row is None:
        return 'no_progress_for_120_seconds' if elapsed > stale_seconds else None
    if row['total_updates'] != total_updates or row['work_limit_seconds'] != work_seconds:
        return 'progress_registration_mismatch'
    if row['projected_work_deadline_miss']:
        return 'projected_work_deadline_miss'
    if elapsed - row['elapsed_seconds'] > stale_seconds:
        return 'progress_stale_for_120_seconds'
    return None


def last_complete_row(path):
    if not path.is_file():
        return None
    for line in reversed(path.read_bytes().splitlines(keepends=True)):
        if line.endswith(b'\n'):
            return json.loads(line)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    index = json.loads((PACKAGE / 'registration-index.json').read_text())
    if args.run_id not in {row['run_id'] for row in index['runs']}:
        raise ValueError('unregistered monitored run')
    home = PACKAGE / args.run_id
    reg = json.loads((home / 'registration-final.json').read_text())
    execution = json.loads((home / 'parent-execution.json').read_text())
    started = execution['started']
    latest = None
    while True:
        elapsed = time.monotonic() - started
        exit_path = home / 'execution-exit.json'
        if exit_path.exists():
            print(json.dumps(dict(status='terminal_parent_audit_required', run_id=args.run_id,
                execution_exit=json.loads(exit_path.read_text()), latest_progress=latest)), flush=True)
            return 0
        latest = last_complete_row(home / 'progress-reports.jsonl')
        reason = assess(latest, elapsed, reg['limits']['work_seconds'], reg['schedule']['updates'])
        if reason is None and elapsed > reg['limits']['total_seconds'] + 30:
            reason = 'outer_execution_overdue_parent_inspection_required'
        if reason:
            result = dict(status='early_progress_alert', reason=reason, run_id=args.run_id,
                elapsed_seconds=elapsed, latest_progress=latest,
                training_signalled=False, lease_changed=False, caps_changed=False)
            # Exclusive alert publication preserves the first observed warning.
            with (home / 'progress-alert.json').open('x') as output:
                json.dump(result, output, sort_keys=True, indent=2)
                output.write('\n')
            print(json.dumps(result), flush=True)
            return 0
        time.sleep(2)


if __name__ == '__main__':
    raise SystemExit(main())
