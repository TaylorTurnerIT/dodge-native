"""Retain exact commands, source identity, stdout/stderr, and failures."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

out = Path(__file__).resolve().parent
label, *command = sys.argv[1:]
command_cwd = Path.cwd()
if command[:1] == ['--cwd']:
    command_cwd = Path(command[1]).resolve()
    command = command[2:]
log = out / f'{label}.log'
if log.exists():
    raise SystemExit(f'refusing to replace {log}')
paths = [Path('Cargo.lock'), Path('crates/dodge-rl-env/Cargo.toml')]
paths += list(Path('crates/dodge-rl-env/src').glob('*.rs'))
paths += list(Path('python/dodge_rl').glob('*.py'))
paths += list(Path('python/tests').glob('*.py'))
paths += [p for p in [Path('python/pyproject.toml')] if p.exists()]
identity = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
start = time.monotonic()
record = dict(label=label, command=command, cwd=str(command_cwd),
              at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              source_sha256=identity,
              environment={k: os.environ[k] for k in ['VIRTUAL_ENV','PYO3_PYTHON'] if k in os.environ})
with log.open('w') as stream:
    result = subprocess.run(command, cwd=command_cwd, stdout=stream, stderr=subprocess.STDOUT)
record.update(exit_code=result.returncode, elapsed_seconds=time.monotonic()-start,
              log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
with (out / 'commands.jsonl').open('a') as stream:
    stream.write(json.dumps(record, sort_keys=True) + '\n')
print(json.dumps({k: record[k] for k in ['label','exit_code','elapsed_seconds']}))
print(log.read_text()[-12000:])
sys.exit(result.returncode)
