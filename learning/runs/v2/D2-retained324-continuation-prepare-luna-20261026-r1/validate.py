import hashlib,json,pathlib,sys,unittest.mock as mock
ROOT=pathlib.Path.cwd(); FINAL=ROOT/'learning/runs/v2/D2-retained324-continuation-prepare-luna-20261026-r1'; sys.path.insert(0,str(FINAL))
import runner as r, execute_once as launcher
registration=FINAL/'registration.json'; digest=hashlib.sha256(registration.read_bytes()).hexdigest(); checks={}
with mock.patch.object(r,'check_lease',lambda reg:None):
 reg,config=r.load_registration(registration,digest)
 checks['all_pins_verified']=len(reg['pins']); checks['actual_lease_installed']=False; checks['lease_check_substituted_only_for_preparation']=True
 out=pathlib.Path(reg['output']); assert not out.exists()
 try: launcher.execute(registration,'0'*64)
 except ValueError: checks['invalid_registration_fails_before_output']=not out.exists()
 else: raise RuntimeError('Invalid registration accepted')
 class BoundaryReached(Exception): pass
 original_mkdir=pathlib.Path.mkdir
 def intercept(path,*args,**kwargs):
  if path.resolve()==out.resolve(): raise BoundaryReached('mutation intercepted after actual preflight')
  return original_mkdir(path,*args,**kwargs)
 with mock.patch.object(pathlib.Path,'mkdir',intercept):
  try: launcher.execute(registration,digest)
  except BoundaryReached: checks['real_execute_passed_preflight_before_first_mutation']=True
  else: raise RuntimeError('Real execute failed to reach intercepted mutation')
 checks['actual_output_absent']=not out.exists(); checks['marker_absent']=not (out/'launch-marker.json').exists()
 torch=r  # runtime import follows registration's pinned isolated runtime
 sys.path.insert(0,reg['runtime_root']); import torch; torch.set_num_threads(2)
 from dodge_rl.checkpoints import load_checkpoint
 from dodge_rl.models.teacher import OmniscientEntityTeacher
 receipt=r.read(reg['parent']['terminal_receipt_path']); parent=load_checkpoint(pathlib.Path(reg['parent']['path']),expected_sha256=r.PARENT_SHA)
 r.validate_parent_checkpoint_for_restore(parent,r.PARENT_SHA,receipt)
 checks['wrong_endpoint360_rejected']=False; checks['wrong_local60_rejected']=False; checks['wrong_cumulative408_rejected']=False
 for key,value,label in (('candidate_phase_update',360,'wrong_endpoint360_rejected'),('candidate_local_update',60,'wrong_local60_rejected')):
  bad=dict(receipt); bad[key]=value
  try: r.validate_parent_checkpoint_for_restore(parent,r.PARENT_SHA,bad)
  except ValueError: checks[label]=True
 bad=dict(receipt); bad['candidate_cumulative_counters']=dict(receipt['candidate_cumulative_counters'],updates=408)
 try: r.validate_parent_checkpoint_for_restore(parent,r.PARENT_SHA,bad)
 except ValueError: checks['wrong_cumulative408_rejected']=True
 model=OmniscientEntityTeacher().cpu(); optimizer=torch.optim.Adam(model.parameters(),lr=r.LEARNING_RATE,eps=1e-5)
 model.load_state_dict(parent['model'],strict=True); optimizer.load_state_dict(parent['optimizer'])
 checks['CPU_model_restored_exactly']=r.fingerprint(model.state_dict())==r.fingerprint(parent['model'])
 checks['CPU_Adam_restored_exactly']=r.fingerprint(optimizer.state_dict())==r.fingerprint(parent['optimizer'])
 checks['saved_RNG_fingerprint_matches_receipt']=r.fingerprint(parent['rng'])==receipt['learner_fingerprints']['rng']
 checks['same_LR_no_override']=all(group['lr']==3e-5 for group in optimizer.param_groups)
 checks['MPS_RNG_restored']=False; checks['optimizer_steps']=0; checks['new_training_launches']=0
 checks['selected324_vs_completed_cost_clocks_distinct']=r._PARENT_CLOCKS['new_selected_trajectory_baseline']==5678.9823631240915 and r._PARENT_CLOCKS['new_campaign_cost_baseline']==9758.365427209174
 checks['registered_cache_empty']=not any(pathlib.Path(reg['import_policy']['pycache_prefix']).iterdir())
 checks['selected_receipt_sha256']=r.sha(reg['parent']['terminal_receipt_path']); checks['completed_cost_sha256']=r.sha(reg['parent']['completed_cost_receipt_path'])
 checks['registration_sha256']=digest; checks['sources_sha256']={n:r.sha(FINAL/n) for n in ('runner.py','execute_once.py','parent_adapter.py','registration_schema.py')}
 checks['status']='passed_integrated_CPU_preparation; live lease and parent independent review pending'
 for key in ('invalid_registration_fails_before_output','real_execute_passed_preflight_before_first_mutation','actual_output_absent','marker_absent','CPU_model_restored_exactly','CPU_Adam_restored_exactly','saved_RNG_fingerprint_matches_receipt','same_LR_no_override','wrong_endpoint360_rejected','wrong_local60_rejected','wrong_cumulative408_rejected','selected324_vs_completed_cost_clocks_distinct','registered_cache_empty'):
  if checks.get(key) is not True: raise RuntimeError('Preparation check failed: '+key)
(FINAL/'validation.json').write_text(json.dumps(checks,indent=2)+'\n'); print(json.dumps(checks))
