"""Read retained campaign evidence; never import campaign code or control processes."""
import datetime
import json
import sys
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent
OBSERVER = OUT.parent
CAMPAIGN = OBSERVER.with_name('postovernight-long-D2-campaign-r2')


def read(path):
    return json.loads(path.read_text()) if path.is_file() else None


def last_row(path):
    if not path.is_file():
        return None
    with path.open('rb') as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - 65536))
        lines = stream.read().splitlines()
    for line in reversed(lines):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


wait = float(sys.argv[1]) if len(sys.argv) > 1 else 0
if not 0 <= wait <= 50:
    raise ValueError('Read-only monitor wait must be within 0..50 seconds')
time.sleep(wait)
progress = read(OBSERVER / 'progress.json')
metric = last_row(CAMPAIGN / 'training-metrics.jsonl')
evaluations = []
errors = []
for path in sorted(CAMPAIGN.glob('*.long-evaluation.json')):
    try:
        certificate = read(path)
        if certificate.get('complete'):
            evaluations.append(dict(
                file=path.name,
                checkpoint_sha256=certificate.get('checkpoint_sha256'),
                gate=certificate.get('progression_gate_passed'),
                evaluations={stage: {key: value.get(key) for key in
                    ('complete', 'episodes', 'deaths', 'caps', 'mean_score', 'mean_alive_frames')}
                    for stage, value in certificate.get('evaluations', {}).items()},
            ))
    except (OSError, ValueError) as error:
        errors.append(dict(file=str(path), error=repr(error)))
snapshot = dict(
    utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    progress=progress,
    counters=None if metric is None else metric.get('counters'),
    last_resource_sample=last_row(CAMPAIGN / 'worker-resources.jsonl'),
    completed_evaluations=evaluations,
    terminal_result=read(OBSERVER / 'execution-result.json'),
    read_errors=errors,
)
with (OUT / 'live-observations.jsonl').open('a') as stream:
    stream.write(json.dumps(snapshot, sort_keys=True, allow_nan=False) + '\n')
latest = evaluations[-1] if evaluations else {}
latest_d2 = latest.get('evaluations', {}).get('D2', {})
phase = {} if metric is None else metric.get('counters', {}).get('phase', {})
summary = dict(elapsed=None if progress is None else progress.get('elapsed_seconds'),
    updates=phase.get('updates'), raw_frames=phase.get('raw_frames'),
    evaluations=len(evaluations), score=latest_d2.get('mean_score'),
    alive=latest_d2.get('mean_alive_frames'), gate=latest.get('gate'),
    terminal=snapshot['terminal_result'] is not None, read_errors=errors)
print(json.dumps(summary, sort_keys=True, allow_nan=False))
