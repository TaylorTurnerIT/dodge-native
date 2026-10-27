import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
rows=[]
for mutation,delay,budget in (('cancel',.65,7200),('input',5.1,7200),('none',1.0,.8)):
    for mode in ('closure','pass'):
        name='delayed-unmask-'+mutation+'-'+mode
        argv=[sys.executable,'-B',str(HERE/'probe_final_unmask.py'),str(HERE/name),mutation,mode,str(delay),str(budget)]
        run=subprocess.run(argv,capture_output=True,text=True,timeout=20,
                           env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(HERE/'tmp')))
        (HERE/(name+'.log')).write_text(run.stdout+run.stderr)
        root=HERE/name
        value=dict(name=name,argv=argv,process_exit=run.returncode,delay_seconds=delay,budget_seconds=budget,
                   injection_event_available=(root/'final-unmask-event.json').exists())
        if (root/'independent-observation.json').exists():
            obs=json.loads((root/'independent-observation.json').read_bytes())
            value.update(terminal_status=obs['terminal']['experiment_status'],return_code=obs['return_code'],
                         manifest_available=obs['manifest_available'],manifest_still_matches=obs['manifest_still_matches'],
                         cancelled=obs['cancel_requested'],input_matches=obs['input_matches'],
                         owned_group_positively_absent=obs['owned_group_positively_absent'])
        rows.append(value)
        (HERE/'delayed-unmask-summary.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
        print(json.dumps(value),flush=True)
