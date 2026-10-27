"""Read active receipt streams without touching the learner or environment."""
import datetime
import json
from pathlib import Path

r = Path(__file__).resolve().parent.parent / 'milestone3-D2-curriculum-r1'

def rows(name):
    p = r / name
    content = p.read_text() if p.exists() else ''
    return [json.loads(line) for line in content.splitlines() if line.strip()]

m = rows('training-metrics.jsonl')
w = rows('worker-resources.jsonl')
last = m[-1] if m else {}
certificates = sorted(r.glob('*.evaluation.json'))
latest_evaluation = None
if certificates:
    p = certificates[-1]
    certificate = json.loads(p.read_bytes())
    evaluation = certificate['evaluations']['D2']
    latest_evaluation = dict(checkpoint=p.name.removesuffix('.evaluation.json'),
                             checkpoint_sha256=certificate['checkpoint_sha256'],
                             passed=certificate['passed'], **{k: evaluation[k] for k in
                             ('mean_score', 'mean_alive_frames', 'deaths', 'caps')})
print(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    phase_updates=len(m), new_Adam_steps=sum(x['metrics']['optimizer_steps'] for x in m),
    last_metrics={k: last.get('metrics', {}).get(k) for k in
                  ('entropy', 'approx_kl', 'explained_variance', 'grad_norm', 'finite')},
    RSS_peak=max((x.get('rss_bytes', 0) for x in w), default=0),
    MPS_driver_peak=max((x.get('mps_driver_bytes', 0) for x in w), default=0),
    completed_evaluations=len(certificates), latest_evaluation=latest_evaluation,
    terminal=(r / 'run-result.json').exists())))
