from __future__ import annotations
import copy, json, sys
from pathlib import Path
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import runner
reg=json.loads((OUT/'registration.json').read_text())
runner.check_lease=lambda _reg: None
reg_loaded,config=runner.load_registration(OUT/'registration.json',runner.sha(OUT/'registration.json'))
helper=runner._VERIFIED_TRANSITION
sys.path.insert(0,reg_loaded['runtime_root'])
import torch
from dodge_rl import checkpoints as ckpt
from dodge_rl.models.teacher import OmniscientEntityTeacher
parent=ckpt.load_checkpoint(Path(reg_loaded['parent']['path']),expected_sha256=runner.PARENT_SHA)
receipt=runner.read(reg_loaded['parent']['terminal_receipt_path'])
runner.validate_parent_checkpoint_for_restore(parent,runner.PARENT_SHA,receipt)
model=OmniscientEntityTeacher().to(device='cpu',dtype=torch.float32)
model.load_state_dict(parent['model'],strict=True)
optimizer=torch.optim.Adam(model.parameters(),lr=0.0001,eps=config['ppo']['adam_eps'])
optimizer.load_state_dict(parent['optimizer'])
assert runner.fingerprint(model.state_dict())==receipt['learner_fingerprints']['model']
assert runner.fingerprint(optimizer.state_dict())==receipt['learner_fingerprints']['optimizer']
assert helper.assert_effective_lr(optimizer,0.0001) is None
cpu_rng_before=torch.get_rng_state().clone(); model_before=runner.fingerprint(model.state_dict())
optimizer_before=optimizer.state_dict(); before=helper.begin_transition_record(optimizer_before,{'parent_checkpoint_sha256':runner.PARENT_SHA})
mode_before=model.training; grad_before=torch.is_grad_enabled()
delta=helper.apply_resume_lr_override(optimizer,config['ppo']['learning_rate'],reg_loaded['arm_transition'])
record=helper.transition_record(before,optimizer.state_dict(),delta)
assert torch.equal(cpu_rng_before,torch.get_rng_state())
assert runner.fingerprint(model.state_dict())==model_before
assert model.training is mode_before and torch.is_grad_enabled() is grad_before
helper.assert_effective_lr(optimizer,0.00003)
assert helper.fingerprint(helper.without_group_lr(optimizer.state_dict()))==before['parent_optimizer_fingerprint_excluding_lr']
assert record['non_lr_fields_changed']==[]

controls={}
(OUT/'attempts').mkdir(exist_ok=True)
# Prove postcondition checks detect model and CPU RNG mutations, then restore both.
model_state=copy.deepcopy(model.state_dict()); base_model=runner.fingerprint(model.state_dict())
with torch.no_grad(): next(model.parameters()).add_(1)
controls['model_change_detected']=runner.fingerprint(model.state_dict()) != base_model
model.load_state_dict(model_state,strict=True)
rng_state=torch.get_rng_state().clone(); torch.manual_seed(17)
controls['cpu_rng_change_detected']=not torch.equal(torch.get_rng_state(),rng_state)
torch.set_rng_state(rng_state)
def rejected(name,fn):
 try: fn()
 except (ValueError,KeyError,TypeError): controls[name]=True
 else: controls[name]=False
rejected('wrong_parent_digest',lambda:runner.validate_parent_checkpoint_for_restore(parent,'f1300e4e86ec89ed9cfba446c8e7f66cf29caad6a1130864edd4d6ee7859d442',receipt))
def wrong_receipt():
 r=copy.deepcopy(receipt);r['checkpoint_sha256']='f1300e4e86ec89ed9cfba446c8e7f66cf29caad6a1130864edd4d6ee7859d442';runner.validate_parent_checkpoint_for_restore(parent,runner.PARENT_SHA,r)
rejected('wrong_receipt_checkpoint',wrong_receipt)
def wrong_counters():
 s=copy.deepcopy(parent);s['counters']['optimizer_steps']+=1;runner.validate_parent_checkpoint_for_restore(s,runner.PARENT_SHA,receipt)
rejected('wrong_parent_counters',wrong_counters)
def wrong_indices():
 s=copy.deepcopy(parent);s['next_episode_indices'][0]+=1;runner.validate_parent_checkpoint_for_restore(s,runner.PARENT_SHA,receipt)
rejected('wrong_parent_episode_indices',wrong_indices)
def wrong_resource_anchor():
 a=json.loads(Path(reg_loaded['resource_cost_anchor']['path']).read_text());a['wall_accounting']['completed_campaign_resource_cost_after_seconds']+=1
 mutated=OUT/'attempts'/'mutated-resource-cost-anchor.json';mutated.parent.mkdir(exist_ok=True);mutated.write_text(json.dumps(a,sort_keys=True))
 runner.validate_resource_cost_anchor_path(mutated,reg_loaded['resource_cost_anchor']['sha256'])
rejected('wrong_resource_cost_anchor',wrong_resource_anchor)
def wrong_config():
 c=copy.deepcopy(config);c['ppo']['target_kl']+=0.001;helper.validate_config_transition(json.loads(Path(reg_loaded['parent_config_path']).read_text()),c)
rejected('wrong_config_non_lr_change',wrong_config)
def wrong_effective_lr(): helper.apply_resume_lr_override(torch.optim.Adam(model.parameters(),lr=0.0001),0.0001,reg_loaded['arm_transition'])
rejected('wrong_effective_lr_config',wrong_effective_lr)
def wrong_transition_parent_lr():
 opt=torch.optim.Adam(model.parameters(),lr=0.0003);helper.apply_resume_lr_override(opt,0.00003,reg_loaded['arm_transition'])
rejected('wrong_restored_lr',wrong_transition_parent_lr)
def wrong_copied_lr(): helper.assert_saved_optimizer_lr({'optimizer':{'param_groups':[{'lr':0.0001}]}})
rejected('copied_parent_lr_checkpoint',wrong_copied_lr)
assert all(controls.values()),controls
result={'schema':'d2_retained276_lr3em5_cpu_restore_and_controls_v1','status':'passed','parent_checkpoint_sha256':runner.PARENT_SHA,
 'model_fingerprint':runner.fingerprint(model.state_dict()),'parent_adam_fingerprint':before['parent_optimizer_fingerprint'],
 'effective_adam_fingerprint':runner.fingerprint(optimizer.state_dict()),'effective_learning_rate':0.00003,
 'transition_record':record,'negative_controls':controls,'environment_constructed':False,'mps_used':False,
 'rng_scope':'CPU model/Adam restore and CPU RNG preservation only; no MPS RNG restoration claim.'}
(OUT/'cpu-restore-and-controls.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':result['status'],'negative_controls':controls,'mps_used':False},sort_keys=True))
