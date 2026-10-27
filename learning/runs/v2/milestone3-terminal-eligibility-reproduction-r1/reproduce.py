from pathlib import Path
import hashlib,json,sys
from types import SimpleNamespace
from test_checkpoints import checkpoint,certificate,simple_identity,eval_result
from dodge_rl import checkpoints as c,train_teacher as t
from dodge_rl.identity import default_config
from dodge_rl.supervision import GuardStop
root=Path.cwd();out=Path(sys.argv[1]);identity=json.loads((root/'learning/runs/v2/milestone3-integration-r2/probe-frozen-identity.json').read_text());h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();pins=identity['sources'];assert all(h(root/p)==d for p,d in pins.items())
rows=[]
for status in ['failed','cancelled','missing']:
 directory=out/status;directory.mkdir();path=directory/'candidate.pt';_,digest=checkpoint(path);certificate(path,digest)
 if status!='missing':(directory/'run-result.json').write_text(json.dumps({'status':status,'phase':'pilot','worker_result':{'status':'failed'}}))
 loaded,proof=c.validate_transition(path,simple_identity(default_config('D1',parent_sha256=digest)))
 rows.append({'source_terminal_status':status,'transition_accepted':proof['passed'],'checkpoint_sha256':digest})
directory=out/'late-final-guard';directory.mkdir();path=directory/'candidate.pt';_,digest=checkpoint(path)
class Guard:
 def __init__(self):self.calls=0
 def check(self,**kw):
  self.calls+=1
  if self.calls==3:raise GuardStop('Synthetic final guard expiry after certificate publication')
e=t.Experiment.__new__(t.Experiment);e.config=default_config('pilot');e.directory=directory;e.guard=Guard();e.model=object();e.device='cpu';e.actor_gradient_seen=e.critic_gradient_seen=True;e.counters={'phase_updates':1};e.last_metrics=None
old=t.evaluate;t.evaluate=lambda *a,**kw:eval_result(2,700)
try:
 try:e.evaluate_checkpoint(path,digest,pilot_before=eval_result(.5,500));raise AssertionError('Final guard did not stop')
 except GuardStop:pass
finally:t.evaluate=old
assert e.guard.calls==3 and c.evaluation_path(path).is_file()
loaded,proof=c.validate_transition(path,simple_identity(default_config('D1',parent_sha256=digest)))
rows.append({'source_terminal_status':'final_guard_expired_after_certificate','transition_accepted':proof['passed'],'checkpoint_sha256':digest})
assert all(row['transition_accepted'] is True for row in rows)
assert all(h(root/p)==d for p,d in pins.items())
result={'status':'four_synthetic_reproductions_confirm_P1','cases':rows,'source_pins_unchanged':len(pins),'scope':'synthetic2to1Linearcheckpoints;nooptimizerupdates_or_game_rollouts','B_E_opened':False}
(out/'reproduction-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
