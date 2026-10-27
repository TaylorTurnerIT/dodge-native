"""CPU-only selected-parent preparation gate. Never starts a worker."""
from __future__ import annotations
import hashlib, json, pathlib, sys
import parent_adapter as adapter
ROOT=pathlib.Path(__file__).resolve().parents[4]
RUNS=ROOT/"learning/runs/v2"
PARENT=RUNS/"D2-retained276-lr3em5-20261026-r2"
AUDIT=RUNS/"D2-retained276-lr3em5-parent-terminal-audit-20261026-r2"
PREP=RUNS/"D2-retained276-lr3em5-prepare-luna-20261026-r2"
RUNTIME=RUNS/"D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
def sha(p):
 h=hashlib.sha256(); f=open(p,"rb")
 for b in iter(lambda:f.read(1<<20),b""): h.update(b)
 return h.hexdigest()
def validate():
 import importlib.util
 sys.path.insert(0,str(RUNTIME)); sys.path.insert(0,str(PREP))
 from dodge_rl.checkpoints import load_checkpoint
 spec=importlib.util.spec_from_file_location("r4_fingerprint_runner", PREP/"runner.py")
 mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
 cp=PARENT/"checkpoint-000300-candidate.pt"; sel=AUDIT/"retained-best-candidate-receipt.json"
 cost=AUDIT/"completed-iteration-receipt.json"; meta=pathlib.Path(str(cp)+".json")
 state=load_checkpoint(cp, expected_sha256=adapter.CHECKPOINT_SHA)
 adapter.validate_parent(state,sha(cp),json.loads(sel.read_text()),sha(sel),mod.fingerprint,json.loads(meta.read_text()),sha(meta),json.loads(cost.read_text()),sha(cost))
 model=__import__("dodge_rl.models.teacher",fromlist=["OmniscientEntityTeacher"]).OmniscientEntityTeacher().cpu()
 import torch
 opt=torch.optim.Adam(model.parameters(),lr=3e-5,eps=1e-5)
 model.load_state_dict(state["model"],strict=True); opt.load_state_dict(state["optimizer"])
 if mod.fingerprint(opt.state_dict()) != mod.fingerprint(state["optimizer"]): raise ValueError("Adam restore changed saved state")
 if any(g["lr"] != 3e-5 for g in opt.param_groups): raise ValueError("Adam LR changed during restore")
 return {"status":"selected_parent_cpu_validation_passed","selected_phase_update":300,"local_update":24,"cumulative_updates":348,"adam_restored_exactly":True,"lr_override":False,"worker_started":False}
if __name__=="__main__": print(json.dumps(validate(),sort_keys=True))
