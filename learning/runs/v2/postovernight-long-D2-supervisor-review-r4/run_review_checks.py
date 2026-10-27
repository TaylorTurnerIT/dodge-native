"""Selected fresh R4 controls, sequential and stop on first unexpected result."""
from pathlib import Path
import json,os,sys,time,traceback,unittest
OUT=Path(__file__).resolve().parent
PREP=OUT.parent/'postovernight-long-D2-prepare-r4'
sys.path.insert(0,str(PREP))
import run_checks
import long_d2 as c
import test_worker_ack_contract as ack
started=time.monotonic()
DIRECTORY=OUT/'targeted-controls';DIRECTORY.mkdir()
(OUT/'worker-ack').mkdir();ack.EVIDENCE=OUT/'worker-ack'
results=[]
try:
 for mode,code in (('closure',2),('pass',0)):
  base=dict(mode=mode,worker_seconds=2.5,inner_seconds=3,outer_seconds=4)
  plans=[('positive',dict(base,phase='outer:final-IO',mutation='none'),code),
         ('blocked-final-read',dict(base,phase='outer:final-IO',mutation='read'),1),
         ('blocked-final-sleep',dict(base,phase='outer:final-IO',mutation='none',delay=4.5),1)]
  for phase in ('receipt-before','receipt-close-before','receipt-close-after','watchdog-join-before','watchdog-join-after','final-lease','final-sample'):
   plans.append(('late-'+phase,dict(base,phase='outer:'+phase,mutation='none',delay=4.5),1))
  for phase,mutation in (('guard-close-after','SIGTERM'),('watchdog-join-before','SIGINT'),('final-IO','SIGTERM'),('pending-before','SIGALRM'),('blocked-before-disarm','SIGALRM'),('final-lease','cancel'),('final-IO','input')):
   plans.append((phase+'-'+mutation,dict(base,phase='outer:'+phase,mutation=mutation),1))
  plans.append(('watchdog-takeover-persistence-bound',dict(base,phase='outer:watchdog-join-before',mutation='SIGINT',failure_persistence_delay=11),1))
  for name,options,expected in plans:
   value=run_checks.case(DIRECTORY,mode+'-'+name,options,expected);value['name']=mode+'-'+name
   results.append(value)
   with (OUT/'case-results.jsonl').open('a') as stream:stream.write(json.dumps(value,sort_keys=True)+'\n')
 for name,options in (
  ('wedged-worker',dict(mode='wedged',worker_seconds=.6,inner_seconds=1,outer_seconds=1.5)),
  ('registration-race',dict(mode='blocked',phase='inner:spawn-before-registration',mutation='crash',worker_seconds=1,inner_seconds=1.5,outer_seconds=2)),
  ('inner-dies-worker-lives',dict(mode='blocked',phase='inner:during-worker',mutation='crash',worker_seconds=1,inner_seconds=1.5,outer_seconds=2)),
  ('binding-corruption',dict(mode='closure',phase='inner:before-D',mutation='binding'))):
  value=run_checks.case(DIRECTORY,name,options,1);value['name']=name;results.append(value)
  with (OUT/'case-results.jsonl').open('a') as stream:stream.write(json.dumps(value,sort_keys=True)+'\n')
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(ack.WorkerAckContract)
 unit=unittest.TextTestRunner(verbosity=2,failfast=True).run(suite)
 summary=dict(successful=unit.wasSuccessful(),OS_subprocesses=len(results),unit_methods=unit.testsRun,unit_failures=len(unit.failures),unit_errors=len(unit.errors),worker_AST_scenarios=len(list((OUT/'worker-ack').glob('worker-*.json'))),elapsed_seconds=time.monotonic()-started,ML_imports=[n for n in sys.modules if n.split('.')[0] in ('torch','numpy','dodge_rl')],results=results)
 with (OUT/'fresh-checks-summary.json').open('x') as f:json.dump(summary,f,indent=2,sort_keys=True);f.write('\n')
 assert unit.wasSuccessful()
except BaseException as error:
 with (OUT/'first-unexpected-failure.json').open('x') as f:json.dump(dict(error=repr(error),traceback=traceback.format_exc(),completed_cases=len(results),elapsed_seconds=time.monotonic()-started),f,indent=2);f.write('\n')
 raise
print(json.dumps({k:v for k,v in summary.items() if k!='results'}),flush=True)
