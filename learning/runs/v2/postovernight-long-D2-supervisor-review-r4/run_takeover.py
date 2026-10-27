"""Two new-purpose watchdog identity probes after ordinary controls passed."""
from pathlib import Path
import json,os,sys,time
OUT=Path(__file__).resolve().parent;PREP=OUT.parent/'postovernight-long-D2-prepare-r4';sys.path.insert(0,str(PREP))
import run_checks
run_checks.HERE=OUT/'takeover-driver'
directory=OUT/'takeover-controls';directory.mkdir();results=[]
for mode in ('closure','pass'):
 row=run_checks.case(directory,mode,dict(mode=mode,worker_seconds=2.5,inner_seconds=3,outer_seconds=4,phase='outer:watchdog-join-before',mutation='SIGINT',failure_persistence_delay=11),1)
 events=[json.loads(x) for x in (directory/mode/'takeover-events.jsonl').read_text().splitlines()]
 starts=[x for x in events if x['kind']=='monitor_start'];exits=[x for x in events if x['kind']=='monitor_exit'];fails=[x for x in events if x['kind']=='failure']
 assert len(starts)==2 and len({x['pool'] for x in events})==1
 assert starts[0]['stop']!=starts[1]['stop'] and not any(x['stop_set'] for x in starts)
 assert len(exits)==1 and exits[0]['stop']==starts[0]['stop'] and exits[0]['stop_set']
 assert starts[1]['until']==fails[0]['until'] and all(x['until']<=fails[0]['until'] for x in fails)
 assert row['elapsed_seconds']<12.5 and row['raw_wait']['returncode']==1 and not row['harness_kill_required']
 results.append(dict(mode=mode,observation=row,events=events))
with (OUT/'takeover-summary.json').open('x') as f:json.dump(dict(successful=True,OS_subprocesses=2,results=results),f,indent=2);f.write('\n')
print(json.dumps(dict(successful=True,OS_subprocesses=2)))
