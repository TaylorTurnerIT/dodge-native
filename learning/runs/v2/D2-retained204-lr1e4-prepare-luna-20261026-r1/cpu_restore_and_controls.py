from __future__ import annotations
import copy, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import runner
reg=json.loads((OUT/"registration.json").read_text())
receipt=json.loads(Path(reg["parent"]["terminal_receipt_path"]).read_text())
sys.path.insert(0,reg["runtime_root"])
import torch
from dodge_rl import checkpoints as ckpt
from dodge_rl.models.teacher import OmniscientEntityTeacher
from resume_lr_transition import apply_resume_lr_override, transition_record
parent=ckpt.load_checkpoint(Path(reg["parent"]["path"]),expected_sha256=runner.PARENT_SHA)
ckpt.require_complete_update(parent)
runner.validate_parent_checkpoint_for_restore(parent,runner.PARENT_SHA,receipt)
model=OmniscientEntityTeacher().to(device="cpu",dtype=torch.float32)
assert model.architecture_description()==parent["identity"]["architecture"]
model.load_state_dict(parent["model"],strict=True)
optimizer=torch.optim.Adam(model.parameters(),lr=0.0003,eps=0.00001)
optimizer.load_state_dict(parent["optimizer"])
assert runner.fingerprint(model.state_dict())==runner.fingerprint(parent["model"])
assert runner.fingerprint(optimizer.state_dict())==runner.fingerprint(parent["optimizer"])
before={"model":runner.fingerprint(model.state_dict()),"Adam":runner.fingerprint(optimizer.state_dict())}
raw=optimizer.state_dict()
delta=apply_resume_lr_override(optimizer,0.0001,reg["arm_transition"])
transition=transition_record(raw,optimizer.state_dict(),delta,{"parent_checkpoint_sha256":runner.PARENT_SHA,"candidate_receipt_sha256":runner.PARENT_RECEIPT_SHA,"parent_config_sha256":runner.PARENT_CONFIG_SHA,"arm_config_sha256":runner.CONFIG_SHA,"helper_sha256":runner.sha(reg["lr_transition_helper_path"])})
assert before["model"]==runner.fingerprint(model.state_dict())
assert transition["parent_optimizer_fingerprint_excluding_lr"]==transition["effective_optimizer_fingerprint_excluding_lr"]
assert transition["parent_optimizer_fingerprint"]!=transition["effective_optimizer_fingerprint"]
# Negative controls: every mutation must fail the authoritative checkpoint binding.
def rejects(mutator):
 s=copy.deepcopy(parent); mutator(s)
 try: runner.validate_parent_checkpoint_for_restore(s,runner.PARENT_SHA,receipt)
 except ValueError: return True
 return False
controls={
 "counter_optimizer_steps":rejects(lambda s:s["counters"].__setitem__("optimizer_steps",s["counters"]["optimizer_steps"]+1)),
 "phase":rejects(lambda s:s.__setitem__("phase_update",205)),
 "raw_frames":rejects(lambda s:s["cumulative_counters"].__setitem__("raw_frames",s["cumulative_counters"]["raw_frames"]+1)),
 "resume_index":rejects(lambda s:s["next_episode_indices"].__setitem__(0,s["next_episode_indices"][0]+1)),
}
assert all(controls.values()),controls
badreg=copy.deepcopy(reg); badreg["parent"]["selection_sha256"]="0"*64
try: runner.validate_parent_terminal_receipt(receipt,badreg); controls["selection_receipt"]=False
except ValueError: controls["selection_receipt"]=True
assert all(controls.values()),controls
result={"schema":"d2_retained204_cpu_restore_and_controls_v1","status":"passed","parent_checkpoint_sha256":runner.PARENT_SHA,"model_tensor_fingerprint":before["model"],"adam_tensor_and_moment_fingerprint":before["Adam"],"transition":transition,"negative_controls":controls,"environment_constructed":False,"mps_used":False,"game_weight_optimizer_steps":0,"rng_restore_scope":"CPU model and Adam restore only; full registered MPS RNG restore remains mandatory in actual worker before environment construction"}
(OUT/"cpu-restore-and-controls.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
print(json.dumps({"status":result["status"],"negative_controls":controls,"model":before["model"],"adam":before["Adam"]},sort_keys=True))
