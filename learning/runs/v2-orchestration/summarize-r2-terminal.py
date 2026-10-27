"""Bounded terminal summaries; never print embedded boundary or episode arrays."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]
CAMPAIGN = ROOT / 'learning/runs/v2/postovernight-long-D2-campaign-r2'


def read(path):
    return json.loads(path.read_text())


rows = []
for path in sorted(CAMPAIGN.glob('*.long-evaluation.json')):
    cert = read(path)
    ev = cert['evaluations']['D2']
    rows.append(dict(certificate=path.name, checkpoint_sha256=cert['checkpoint_sha256'],
                     **{key: ev[key] for key in ('mean_alive_frames', 'mean_score', 'episodes', 'deaths', 'caps')},
                     complete=cert.get('complete'), passed=cert.get('passed'),
                     progression_gate_passed=cert.get('progression_gate_passed')))
print(json.dumps(dict(evaluation_count=len(rows), best_score=max(rows, key=lambda x:x['mean_score']),
                      best_survival=max(rows, key=lambda x:x['mean_alive_frames']), last=rows[-1]), indent=2))
print('EVALUATION_ROWS', json.dumps([[row['certificate'].split('-')[1], row['mean_alive_frames'], row['mean_score']] for row in rows]))
for name in ('long-worker-result.json', 'long-run-result.json', 'finalization-result.json'):
    path = CAMPAIGN / name
    if not path.exists():
        print(name, 'ABSENT')
        continue
    data = read(path)
    print(name, 'KEYS', list(data))
    print('SCALARS', json.dumps({key: value for key, value in data.items() if not isinstance(value, (dict,list))}))
    for key in ('counters', 'resources', 'resource', 'resource_receipt', 'safety', 'last_metrics', 'last_evaluation'):
        value = data.get(key)
        if isinstance(value, dict):
            if key == 'counters':
                print(key, json.dumps(value))
            else:
                print(key, json.dumps({k: v for k, v in value.items() if not isinstance(v, (dict,list))}))
