from __future__ import annotations
import copy, json, sys
from pathlib import Path
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import runner
reg=json.loads((OUT/'registration.json').read_text())
receipt=json.loads(Path(reg['parent']['terminal_receipt_path']).read_text())
runner.check_lease=lambda _reg: None
runner.load_registration(OUT/'registration.json',runner.sha(OUT/'registration.json'))
sys.path.insert(0,reg['runtime_root'])
import torch
from dodge_rl import checkpoints as ckpt
from dodge_rl.models.teacher import OmniscientEntityTeacher
parent=ckpt.load_checkpoint(Path(reg['parent']['path']),expected_sha256=runner.PARENT_SHA)
ckpt.require_complete_update(parent)
runner.validate_parent_checkpoint_for_restore(parent,runner.PARENT_SHA,receipt)
model=OmniscientEntityTeacher().to(device='cpu',dtype=torch.float32)
assert model.architecture_description()==parent['identity']['architecture']
model.load_state_dict(parent['model'],strict=True)
optimizer=torch.optim.Adam(model.parameters(),lr=0.00003,eps=runner.PPO['adam_eps'])
optimizer.load_state_dict(parent['optimizer'])
assert runner.fingerprint(model.state_dict())==receipt['learner_fingerprints']['model']
assert runner.fingerprint(optimizer.state_dict())==receipt['learner_fingerprints']['optimizer']
runner.assert_effective_lr(optimizer,0.00003)
# This CPU-only validation makes no MPS RNG claim.
# The actual MPS worker still restores full CPU/CUDA/MPS RNG via restore_learner before environment setup.
def rejects_state(mutator):
 s=copy.deepcopy(parent); mutator(s)
 try: runner.validate_parent_checkpoint_for_restore(s,runner.PARENT_SHA,receipt)
 except (ValueError,KeyError,TypeError): return True
 return False
def rejects_receipt(mutator):
 r=copy.deepcopy(receipt); mutator(r)
 try: runner.validate_parent_checkpoint_for_restore(parent,runner.PARENT_SHA,r)
 except (ValueError,KeyError,TypeError): return True
 return False
try: runner.validate_parent_checkpoint_for_restore(parent,'f1300e4e86ec89ed9cfba446c8e7f66cf29caad6a1130864edd4d6ee7859d442',receipt); wrong_parent_digest=False
except ValueError: wrong_parent_digest=True
controls={
 'wrong_parent_digest_rejected': wrong_parent_digest,
 'phase_204_parent_rejected': rejects_state(lambda s:s.__setitem__('phase_update',204)),
 'wrong_receipt_checkpoint': rejects_receipt(lambda r:r.__setitem__('checkpoint_sha256','f1300e4e86ec89ed9cfba446c8e7f66cf29caad6a1130864edd4d6ee7859d442')),
 'counter_mutation': rejects_state(lambda s:s['counters'].__setitem__('optimizer_steps',s['counters']['optimizer_steps']+1)),
 'resume_index_mutation': rejects_state(lambda s:s['next_episode_indices'].__setitem__(0,s['next_episode_indices'][0]+1)),
 'effective_group_lr_mutation': rejects_state(lambda s:s['optimizer']['param_groups'][0].__setitem__('lr',0.0003)),
}
bad=copy.deepcopy(reg); bad['config_sha256']='0'*64
try: runner.validate_registration(bad); controls['config_mutation']=False
except (ValueError,KeyError,TypeError): controls['config_mutation']=True
assert all(controls.values()),controls
result={'schema':'d2_retained276_cpu_restore_and_controls_v1','status':'passed','parent_checkpoint_sha256':runner.PARENT_SHA,
 'model_fingerprint':runner.fingerprint(model.state_dict()),'adam_fingerprint':runner.fingerprint(optimizer.state_dict()),
 'effective_learning_rate':0.00003,'optimizer_mutation_applied':False,'negative_controls':controls,
 'environment_constructed':False,'mps_used':False,'game_weight_optimizer_steps':0,
 'rng_scope':'CPU-only restore test made no MPS RNG claim; actual registered worker must restore full MPS RNG before environment construction.'}
(OUT/'cpu-restore-and-controls.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':result['status'],'negative_controls':controls,'model':result['model_fingerprint'],'adam':result['adam_fingerprint']},sort_keys=True))
