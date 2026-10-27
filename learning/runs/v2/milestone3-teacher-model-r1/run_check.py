"""Retain one bounded component check and exact source snapshots."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
label, *command = sys.argv[1:]
checks = HERE / 'checks'
checks.mkdir(exist_ok=True)
log = checks / f'{label}.log'
receipt = checks / f'{label}.json'
source_dir = checks / f'{label}-sources'
source_dir.mkdir(exist_ok=False)
paths = ['python/dodge_rl/models/__init__.py', 'python/dodge_rl/models/teacher.py', 'python/tests/test_teacher.py']
pins = {}
for name in paths:
    source = ROOT / name
    raw = source.read_bytes()
    pins[name] = hashlib.sha256(raw).hexdigest()
    target = source_dir / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4', VECLIB_MAXIMUM_THREADS='4')
record = {'label': label, 'command': command, 'cwd': str(ROOT), 'at_utc': datetime.now(timezone.utc).isoformat(),
          'source_sha256': pins, 'synthetic_CPU_only': True, 'game_environment_constructed_or_stepped': False,
          'training_campaign': False, 'MPS_probe': False, 'timeout_seconds': 120,
          'environment_overrides': {key: env[key] for key in ('PYTHONDONTWRITEBYTECODE', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')}}
started = time.monotonic()
with log.open('xb') as stream:
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
        record['exit_code'] = result.returncode
    except subprocess.TimeoutExpired as error:
        record.update(exit_code=124, error=repr(error))
record.update(elapsed_seconds=time.monotonic()-started, log=str(log.relative_to(ROOT)), log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
with receipt.open('x') as stream:
    json.dump(record, stream, indent=2, sort_keys=True); stream.write('\n')
with (HERE/'commands.jsonl').open('a') as stream:
    stream.write(json.dumps(record, sort_keys=True)+'\n')
print(json.dumps(record, sort_keys=True))
print(log.read_text()[-14000:])
sys.exit(record['exit_code'])
