import hashlib,json,pathlib,sys,time,unittest.mock as mock
ROOT=pathlib.Path.cwd()
FINAL=ROOT/'learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r2'
sys.path.insert(0,str(FINAL))
import runner as r
import execute_once as launcher
registration=FINAL/'registration.json'
digest=hashlib.sha256(registration.read_bytes()).hexdigest()
checks={}
original_lease=r.check_lease
# Preparation-only: real full input checks, exact lease condition substituted without installing a live reservation.
with mock.patch.object(r,'check_lease',lambda reg:None):
 reg,config=r.load_registration(registration,digest)
 checks['all_pins_verified']=len(reg['pins'])
 checks['actual_lease_installed']=False
 checks['lease_check_substituted_only_for_preparation']=True
 out=pathlib.Path(reg['output'])
 if out.exists():raise RuntimeError('Actual run output unexpectedly exists')
 try:launcher.execute(registration,'0'*64)
 except ValueError:checks['invalid_registration_fails_before_output']=not out.exists()
 else:raise RuntimeError('Invalid registration accepted')
 class BoundaryReached(Exception):pass
 original_mkdir=pathlib.Path.mkdir
 def forbid_actual_mutation(path,*args,**kwargs):
  if path.resolve()==out.resolve():raise BoundaryReached('Actual output mutation intercepted after real registration preflight')
  return original_mkdir(path,*args,**kwargs)
 with mock.patch.object(pathlib.Path,'mkdir',forbid_actual_mutation):
  try:launcher.execute(registration,digest)
  except BoundaryReached:checks['real_execute_passed_preflight_before_first_mutation']=True
  else:raise RuntimeError('Actual execute did not reach intercepted mutation boundary')
 checks['actual_output_absent']=not out.exists()
 checks['marker_absent']=not (out/'launch-marker.json').exists()
 sys.path.insert(0,reg['runtime_root'])
 import torch
 torch.set_num_threads(2)
 from dodge_rl.checkpoints import load_checkpoint
 from dodge_rl.models.teacher import OmniscientEntityTeacher
 parent=load_checkpoint(pathlib.Path(reg['parent']['path']),expected_sha256=r.PARENT_SHA)
 r.validate_parent_checkpoint_for_restore(parent,r.PARENT_SHA,r.read(reg['parent']['terminal_receipt_path']))
 model=OmniscientEntityTeacher().cpu()
 optimizer=torch.optim.Adam(model.parameters(),lr=r.LEARNING_RATE,eps=1e-5)
 model.load_state_dict(parent['model'],strict=True);optimizer.load_state_dict(parent['optimizer'])
 checks['CPU_model_restored_exactly']=r.fingerprint(model.state_dict())==r.fingerprint(parent['model'])
 checks['CPU_Adam_restored_exactly']=r.fingerprint(optimizer.state_dict())==r.fingerprint(parent['optimizer'])
 checks['saved_RNG_fingerprint_matches_receipt']=r.fingerprint(parent['rng'])==r.read(reg['parent']['terminal_receipt_path'])['learner_fingerprints']['rng']
 checks['MPS_RNG_restored']=False
 checks['optimizer_steps']=0
 checks['new_training_launches']=0
 checks['registered_cache_empty']=not any(pathlib.Path(reg['import_policy']['pycache_prefix']).iterdir())
 checks['registration_sha256']=digest
 checks['sources_sha256']={name:r.sha(FINAL/name) for name in ('runner.py','execute_once.py','parent_adapter.py','registration_schema.py')}
 checks['status']='passed_integrated_CPU_preparation;live_lease_and_MPS_preflight_pending'
 for key in ('invalid_registration_fails_before_output','real_execute_passed_preflight_before_first_mutation','actual_output_absent','marker_absent','CPU_model_restored_exactly','CPU_Adam_restored_exactly','saved_RNG_fingerprint_matches_receipt','registered_cache_empty'):
  if checks.get(key) is not True:raise RuntimeError('Preparation check failed: '+key)
 pathlib.Path(__file__).with_name('validation.json').write_text(json.dumps(checks,indent=2)+'\n')
 print(json.dumps(checks))
