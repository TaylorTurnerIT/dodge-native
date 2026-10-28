"""Read-only bounded monitor. Prints counts and receipt state only; never row outcomes or partial training output.

  readiness  - which of the six predeclared producer terminal receipts are present and accepted
  progress   - evaluation journal counts, resources, lease state (after launch)
"""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
import binding as b
from build_registration import readiness


def progress():
    out = b.HERE/'worker-output'; value = dict(launched=(b.HERE/'launch.claimed').exists(), out_present=out.is_dir())
    if not out.is_dir():
        return value
    counts = dict(constructors=0, steps=0, completed=0, raw_frames=0); policies = set()
    path = out/'evaluation-events.jsonl'
    if path.is_file():
        with path.open() as stream:
            for line in stream:
                if not line.endswith('\n'):
                    break
                event = json.loads(line); kind = event['kind']
                policies.add(event['policy_id'])
                if kind == 'evaluation_constructor':
                    counts['constructors'] += 1; counts['raw_frames'] += event['startup_frames']
                elif kind == 'evaluation_step':
                    counts['steps'] += 1; counts['raw_frames'] += event['elapsed_raw_frames']
                elif kind == 'evaluation_completed':
                    counts['completed'] += 1
    value.update(counts, policies_started=len(policies), fraction_of_7168=counts['completed']/b.EPISODES)
    value['resources'] = b.worker_resources(out)
    value['worker_result_present'] = (out/'worker-result.json').is_file()
    value['terminal_audit_present'] = (b.HERE/'parent-terminal-audit.json').is_file()
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('mode', choices=('readiness', 'progress'))
    parser.add_argument('--watch', type=int, default=0, help='repeat every N seconds, at most 20 times')
    args = parser.parse_args()
    for _ in range(max(1, min(20, 20 if args.watch else 1))):
        print(json.dumps(readiness() if args.mode == 'readiness' else progress(), sort_keys=True), flush=True)
        if not args.watch:
            break
        time.sleep(args.watch)
