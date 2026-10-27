"""Recheck captured frozen-source hashes; exclude parent-owned attempts."""
import hashlib
import json
from pathlib import Path
import time
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
initial=json.loads((HERE/'input-hashes.json').read_text())
checked=[];mismatches=[]
for record in initial['inputs']:
    path=record['path']
    if 'postovernight-long-D2-boundary-prepare-r3/' not in path or '/attempts/' in path:
        continue
    raw=(ROOT/path).read_bytes();actual=hashlib.sha256(raw).hexdigest()
    checked.append(dict(path=path,sha256=actual))
    if actual!=record['sha256']:mismatches.append(dict(path=path,expected=record['sha256'],actual=actual))
for path,expected in initial['expected'].items():
    actual=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
    if actual!=expected:mismatches.append(dict(path=path,expected=expected,actual=actual))
result=dict(schema='review_end_frozen_hash_check_v1',checked=checked,mismatches=mismatches,contextual_state_rehashed_as_immutable=False,elapsed_seconds=time.time()-initial['timestamp'])
(HERE/'end-snapshot.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(files=len(checked),mismatches=mismatches,elapsed_seconds=result['elapsed_seconds'])))
raise SystemExit(bool(mismatches))
