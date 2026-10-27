"""Exactly one fail-fast stdlib stage; preserves raw output and terminal status."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess
import time
H=Path(__file__).resolve().parent
ROOT=H.parents[3]

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')
def main():
    out=H/'unit-stage';out.mkdir()  # No reuse or retry.
    cache=out/'fresh-pycache';cache.mkdir();fixtures=out/'fixtures';fixtures.mkdir()
    alias='learning/.venv/bin/python'
    argv=[alias,'-B',str(H/'run_unit_suite.py')]
    env=dict(os.environ,VALIDATION_DIR=str(fixtures),PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(cache))
    relevant={'VALIDATION_DIR','PYTHONDONTWRITEBYTECODE','PYTHONPYCACHEPREFIX','PYTHONPATH','PYTHONHOME','PYTHONSAFEPATH','PATH','PYTORCH_ENABLE_MPS_FALLBACK'}
    save(out/'command.json',dict(argv=argv,cwd=str(ROOT),timeout_seconds=300,started_at_utc=now(),
        env_values={k:v for k,v in env.items() if k in relevant},
        other_env_value_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in env.items() if k not in relevant},
        interpreter_alias_preserved=True,ordered_modules=['test_repairs','test_boundary'],
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in H.glob('*.py')}))
    start=time.monotonic();result={}
    try:
        with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
            process=subprocess.Popen(argv,cwd=ROOT,env=env,stdout=stdout,stderr=stderr)
            try:
                raw=process.wait(timeout=300)
                result=dict(raw_exit=raw,timed_out=False)
            except subprocess.TimeoutExpired:
                process.kill();raw=process.wait()
                result=dict(raw_exit=raw,timed_out=True,termination='unit stage timeout; no retry')
    finally:
        result.update(finished_at_utc=now(),elapsed_seconds=time.monotonic()-start,validation_attempts=1,
                      no_retry=True,cache_empty=not any(cache.iterdir()))
        save(out/'raw-result.json',result)
    print(json.dumps(result,sort_keys=True))
    raise SystemExit(result['raw_exit'] if not result.get('timed_out') else 124)
if __name__=='__main__':main()
