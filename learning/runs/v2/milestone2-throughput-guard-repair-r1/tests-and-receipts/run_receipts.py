"""Run one explicit pure check and retain exact executed source identity."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
label, source, suite, *extra = sys.argv[1:]
source = Path(source).resolve(strict=True)
raw = source.read_bytes()
(HERE / (label + '-executed-source.py')).write_bytes(raw)
if suite == 'new5':
    command = [str(ROOT / 'python/.venv/bin/python'), '-B', '-W', 'error', str(HERE / 'test_throughput_guard.py'), *extra]
else:
    command = [str(ROOT / 'python/.venv/bin/python'), '-B', '-W', 'error', str(HERE / 'run_selected_suite.py'), suite]
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', SUPERVISOR_UNDER_TEST=str(source),
    SUPERVISOR_CASES=str(HERE / (label + '-supervisor-cases')), THROUGHPUT_CASES=str(HERE / (label + '-throughput-cases')))
log = HERE / (label + '.log')
record = {'at_utc': datetime.now(timezone.utc).isoformat(), 'label': label, 'command': command,
    'cwd': str(ROOT), 'selected_executed_source': str(source),
    'selected_executed_source_sha256': hashlib.sha256(raw).hexdigest(),
    'selected_source_snapshot': label + '-executed-source.py', 'suite': suite,
    'environment_overrides': {k: env[k] for k in ('PYTHONDONTWRITEBYTECODE', 'SUPERVISOR_UNDER_TEST', 'SUPERVISOR_CASES', 'THROUGHPUT_CASES')},
    'test_sources_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')},
    'pure_only': True, 'native_execution': False, 'campaign_executed': False}
start = time.monotonic()
with log.open('xb') as stream:
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
        record['exit_code'] = result.returncode
    except subprocess.TimeoutExpired as error:
        record.update(exit_code=124, error=repr(error))
record.update(elapsed_seconds=time.monotonic()-start, log=log.name, log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
with (HERE / (label + '.json')).open('x') as stream:
    json.dump(record, stream, indent=2, sort_keys=True); stream.write('\n')
print(json.dumps(record, sort_keys=True))
print(log.read_text())
sys.exit(record['exit_code'])
