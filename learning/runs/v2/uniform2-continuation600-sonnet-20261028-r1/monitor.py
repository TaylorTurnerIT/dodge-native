"""Read-only bounded monitor: counts, resources and lease state only; never evaluation outcomes."""
from __future__ import annotations
import argparse
import json
import time
import binding as b


def progress():
    out = b.HERE/'worker-output'; value = dict(launched=(b.HERE/'launch.claimed').exists(), out_present=out.is_dir())
    if not out.is_dir():
        return value
    updates = steps = episodes = 0
    for name in ('training-events.jsonl', 'evaluation-events.jsonl'):
        path = out/name
        if path.is_file():
            with path.open() as stream:
                for line in stream:
                    if not line.endswith('\n'):
                        break
                    kind = json.loads(line)['kind']
                    updates += kind == 'update_metrics'; steps += kind == 'returned_step_cost'; episodes += kind == 'evaluation_episode'
    value.update(updates_journaled=updates, returned_training_steps=steps, evaluation_episodes_journaled=episodes,
                 checkpoints=len(list(out.glob('checkpoint-global-*.pt'))), evaluation_receipts=len(list(out.glob('evaluation-*.json'))),
                 resources=b.worker_resources(out), worker_result_present=(out/'worker-result.json').is_file(),
                 terminal_audit_present=(b.HERE/'parent-terminal-audit.json').is_file())
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--watch', type=int, default=0, help='repeat every N seconds, at most 20 times')
    a = parser.parse_args()
    for _ in range(20 if a.watch else 1):
        print(json.dumps(progress(), sort_keys=True), flush=True)
        if not a.watch:
            break
        time.sleep(a.watch)
