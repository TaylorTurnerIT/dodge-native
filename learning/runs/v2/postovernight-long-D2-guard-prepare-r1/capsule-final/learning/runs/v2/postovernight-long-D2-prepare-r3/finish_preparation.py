"""Preparation-only final checks. Never invokes the executor run command."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import long_d2 as c
HERE=Path(__file__).resolve().parent

def command(argv,log):
    started=time.monotonic()
    with (HERE/log).open('x') as stream:
        result=subprocess.run(argv,stdout=stream,stderr=subprocess.STDOUT,
                              env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),timeout=60)
    c.save(HERE/(log+'.command.json'),dict(argv=argv,raw_exit=result.returncode,elapsed_seconds=time.monotonic()-started))
    c.require(result.returncode==0,'Preparation check failed: '+log)


def main():
    command([sys.executable,'-B',str(HERE/'run_unit_checks.py'),str(HERE/'attempts/units-final-r2')],'attempts/units-final-r2.log')
    command([sys.executable,'-B',str(HERE/'freeze.py')],'freeze.log')
    argv=[sys.executable,'-B',str(HERE/'capsule-final'/c.PREPARE_REL/'long_d2_executor.py'),
          'preflight','--registration',str(HERE/'registration.json')]
    result=subprocess.run(argv,capture_output=True,text=True,timeout=30,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    c.save(HERE/'executor-preflight-command.json',dict(argv=argv,raw_exit=result.returncode,stderr=result.stderr))
    c.require(result.returncode==0,'Executor pure preflight failed: '+result.stderr)
    value=json.loads(result.stdout)
    c.save(HERE/'pure-executor-preflight.json',value)
    command([sys.executable,'-B',str(HERE/'volume_probe.py')],'volume-probe.log')
    # Parse final JSON evidence with the actual stdlib CLI, before final inventory.
    for path in sorted(HERE.glob('*.json')):
        subprocess.run([sys.executable,'-m','json.tool',str(path)],check=True,stdout=subprocess.DEVNULL)
    c.require(not (c.ORIGINAL_ROOT/c.registered_protocol(c.ORIGINAL_ROOT/c.PROTOCOL_REL)['output']).exists(),
              'Production campaign output unexpectedly exists')
    c.require(not (c.ORIGINAL_ROOT/'learning/runs/v2/postovernight-long-D2-execution-r1').exists(),
              'Production execution directory unexpectedly exists')
    c.require(c.read_json(c.STATE_PATH).get('active_long_campaign') is None,'Unexpected production active lease')
    # The caller runs finalize_preparation.py only after the full OS matrix ends.
    print(json.dumps(dict(preparation_checks_complete=True,ML_execution=False,lease_created=False),sort_keys=True))


if __name__=='__main__':main()
