"""Exclusive check receipts with selected-source pins and owned-process limits."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
label, selected, suite = sys.argv[1:]
source = Path(selected).resolve(strict=True)
raw = source.read_bytes()
snapshot = HERE / (label + '-executed-source.py')
with snapshot.open('xb') as stream:
    stream.write(raw)
if suite == 'real-api':
    command = [str(ROOT / 'python/.venv/bin/python'), '-B', '-W', 'error', str(HERE / 'real_api_smoke.py')]
else:
    command = [str(ROOT / 'python/.venv/bin/python'), '-B', '-W', 'error', str(HERE / 'run_selected_suite.py'), suite]
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', SUPERVISOR_UNDER_TEST=str(source),
    SUPERVISOR_CASES=str(HERE / (label + '-supervisor-cases')),
    THROUGHPUT_CASES=str(HERE / (label + '-throughput-cases')),
    ORIGINAL9_FIXTURES=str(HERE / (label + '-original9-fixtures')))
record = {'at_utc': datetime.now(timezone.utc).isoformat(), 'label': label, 'command': command,
    'cwd': str(ROOT), 'selected_executed_source': str(source),
    'selected_executed_source_sha256': hashlib.sha256(raw).hexdigest(),
    'selected_source_snapshot': snapshot.name, 'suite': suite, 'pure_only': suite != 'real-api',
    'campaign_executed': False, 'wall_limit_seconds': 120, 'observed_rss_limit_bytes': 6442450944,
    'environment_overrides': {key: env[key] for key in ('PYTHONDONTWRITEBYTECODE', 'SUPERVISOR_UNDER_TEST', 'SUPERVISOR_CASES', 'THROUGHPUT_CASES', 'ORIGINAL9_FIXTURES')},
    'test_sources_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')}}
log = HERE / (label + '.log')
start = time.monotonic()
samples = []
with log.open('xb') as stream:
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    record['owned_pid'] = process.pid
    record['owned_pgid'] = process.pid
    stopped = None
    while process.poll() is None:
        elapsed = time.monotonic() - start
        sample = subprocess.run(['ps', '-o', 'rss=', '-p', str(process.pid)], capture_output=True, text=True, timeout=5)
        if sample.returncode == 0 and sample.stdout.strip().isdigit():
            rss = int(sample.stdout.strip()) * 1024
            samples.append({'elapsed_seconds': elapsed, 'rss_bytes': rss})
            if rss > record['observed_rss_limit_bytes']:
                stopped = 'RSS guard exceeded'
        elif process.poll() is None:
            stopped = 'Cannot sample live owned process RSS'
        if elapsed >= 120:
            stopped = 'Wall guard exceeded'
        if stopped:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            break
        time.sleep(0.1)
    record['exit_code'] = process.wait(timeout=5)
    record['guard_error'] = stopped
record.update(elapsed_seconds=time.monotonic() - start, log=log.name,
    log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),
    sampled_peak_rss_bytes=max((sample['rss_bytes'] for sample in samples), default=None), rss_samples=samples)
with (HERE / (label + '.json')).open('x') as stream:
    json.dump(record, stream, indent=2, sort_keys=True); stream.write('\n')
print(json.dumps({key: value for key, value in record.items() if key != 'rss_samples'}, sort_keys=True))
print(log.read_text()[-12000:])
sys.exit(record['exit_code'] or int(bool(record['guard_error'])))
