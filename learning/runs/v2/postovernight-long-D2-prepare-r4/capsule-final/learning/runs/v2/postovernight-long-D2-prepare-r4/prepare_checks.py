"""Execute final stdlib preparation checks once; exclusive logs and receipts."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import long_d2 as c
HERE=Path(__file__).resolve().parent

def command(argv,name,timeout=90):
    start=time.monotonic()
    with (HERE/'attempts'/(name+'.log')).open('x') as stream:
        result=subprocess.run(argv,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    c.save(HERE/'attempts'/(name+'-command.json'),dict(argv=argv,raw_exit=result.returncode,elapsed_seconds=time.monotonic()-start))
    c.require(result.returncode==0,'Preparation check failed: '+name)

def main():
    command([sys.executable,'-B',str(HERE/'run_unit_checks.py'),str(HERE/'attempts/units-final')],'units-final')
    command([sys.executable,'-B',str(HERE/'freeze.py')],'freeze-final')
    registration=c.read_json(HERE/'registration.json')
    argv=[sys.executable,'-B',registration['executor'],'preflight','--registration',str(HERE/'registration.json')]
    start=time.monotonic();r=subprocess.run(argv,capture_output=True,text=True,timeout=60,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    c.save(HERE/'executor-preflight-command.json',dict(argv=argv,raw_exit=r.returncode,elapsed_seconds=time.monotonic()-start,stderr=r.stderr))
    c.require(r.returncode==0,'Executor pure preflight failed: '+r.stderr)
    c.save(HERE/'pure-executor-preflight.json',json.loads(r.stdout))
    command([sys.executable,'-B',str(HERE/'volume_probe.py')],'volume-final')
    # Validate top-level JSON with the actual stdlib CLI. Finalizer checks its own JSON separately.
    for path in sorted(HERE.glob('*.json')):
        subprocess.run([sys.executable,'-B','-m','json.tool',str(path)],check=True,stdout=subprocess.DEVNULL)
    c.require(c.read_json(c.STATE_PATH).get('active_long_campaign') is None,'Unexpected active production lease')
    p=c.registered_protocol(c.ORIGINAL_ROOT/c.PROTOCOL_REL)
    c.require(not (c.ORIGINAL_ROOT/p['output']).exists(),'Production campaign output exists')
    c.require(not (c.ORIGINAL_ROOT/Path(p['terminal_lifecycle']['acceptance_receipt']).parent).exists(),'Production execution directory exists')
    c.save(HERE/'preparation-checks.json',dict(complete=True,ML_imports=False,production_launch=False,lease=False))
    print('Final unit/freeze/executor preflight/volume controls passed.')

if __name__=='__main__':main()
