from __future__ import annotations
import json, sys
from pathlib import Path
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import runner
from resume_lr_transition import validate_config_transition
reg=json.loads((OUT/"registration.json").read_text())
parent=json.loads(Path(reg["parent_config_path"]).read_text())
arm=json.loads(Path(reg["config_path"]).read_text())
validate_config_transition(parent,arm)
assert runner.PHASE_START==204 and runner.PHASE_END==276
assert list(runner.EVALUATION_UPDATES)==[204,216,228,240,252,264,276]
assert runner.RUN_ID=="D2-retained204-lr1e4-20261026-r1" and reg["run_seed"]==3791628418
assert "lr-transition.json" in reg["expected_outputs"]
source=(OUT/"runner.py").read_text(); launcher=(OUT/"execute_once.py").read_text()
restore=source.index("ckpt.restore_learner(parent, model, optimizer, \"mps\")")
override=source.index("apply_resume_lr_override(optimizer")
env=source.index("dodge_rl.VecDodgeEnv(")
update=source.index("guarded_update(optimizer, 0.0001, ppo_update")
assert restore < override < env < update
assert '"evaluations_checked": 7' in launcher
assert "for update in r.EVALUATION_UPDATES:" in launcher
assert "VecDodgeEnv.close" not in source and ".close()" not in source
print("source contract: config-only LR delta, 204->276 schedule, guarded update ordering, 7-evaluation report, no close() call")
