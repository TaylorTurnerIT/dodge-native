import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
rows = []
for kind in ('late-final-verify','late-artifact-hash','late-manifest-write','late-terminal-write','late-return',
             'unproven-group','deferred-cleanup-cancel','deferred-final-verify-cancel','blocked-worker'):
    for mode in (('closure',) if kind=='blocked-worker' else ('closure','pass')):
        argv = [sys.executable,'-B',str(HERE/'probe_old_boundaries.py'),kind,mode]
        run = subprocess.run(argv,capture_output=True,text=True,timeout=25,
                             env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(HERE/'tmp')))
        name = 'old-' + kind + '-' + mode
        (HERE/(name+'.log')).write_text(run.stdout+run.stderr)
        rows.append(dict(name=name,argv=argv,test_process_exit=run.returncode,log=name+'.log'))
        (HERE/'old-boundary-summary.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
        print(json.dumps(rows[-1]),flush=True)
