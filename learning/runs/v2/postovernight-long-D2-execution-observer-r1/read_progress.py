import json
from pathlib import Path
c=Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79/learning/runs/v2/postovernight-long-D2-campaign-r1')
o=c.parent/'postovernight-long-D2-execution-observer-r1'
def last(name):
 p=c/name
 if not p.exists() or not p.stat().st_size:return {}
 with p.open('rb') as f:
  f.seek(max(0,p.stat().st_size-32768));rows=f.read().splitlines()
 for line in reversed(rows):
  try:return json.loads(line)
  except (ValueError,UnicodeError):continue
 return {}
m=last('training-metrics.jsonl');s=last('schedule.jsonl');r=last('worker-resources.jsonl')
certs=sorted(c.glob('*.long-evaluation.json'));e=json.loads(certs[-1].read_text())['evaluations']['D2'] if certs else {}
print(json.dumps(dict(terminal=(o/'process-exit.json').exists(),phase_updates=m.get('counters',{}).get('phase_updates',0),latest_score=e.get('mean_score'),latest_alive=e.get('mean_alive_frames'),latest_checkpoint=certs[-1].name if certs else None,schedule_event=s.get('event'),remaining_worker_seconds=s.get('remaining_worker_seconds'),RSS_bytes=r.get('rss_bytes'),MPS_bytes=r.get('mps_driver_bytes')),sort_keys=True))
