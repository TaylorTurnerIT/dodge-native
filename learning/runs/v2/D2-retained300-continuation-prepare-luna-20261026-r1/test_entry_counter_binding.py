from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
spec=importlib.util.spec_from_file_location('execute_once_under_test',OUT/'execute_once.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
metrics=[{'phase_update':u,'counters':{'updates':u-276,'optimizer_steps':3*(u-276),'environment_decisions':16384*(u-276),'raw_frames':1000*(u-276)}} for u in range(277,349)]
expected=[276,288,300,312,324,336,348]
assert [module.r.PHASE_START,*module.r.EVALUATION_UPDATES[1:]]==expected
for update in expected:
 counters=module.expected_checkpoint_counters(update,metrics)
 assert counters==({'updates':0,'optimizer_steps':0,'environment_decisions':0,'raw_frames':0} if update==276 else metrics[update-277]['counters'])
assert module.expected_checkpoint_counters(276,[])=={'updates':0,'optimizer_steps':0,'environment_decisions':0,'raw_frames':0}
for bad in [275,349]:
 try: module.expected_checkpoint_counters(bad,metrics)
 except (StopIteration,KeyError): pass
 else: raise AssertionError(f'unexpected update {bad} accepted')
print('production checkpoint-counter helper: phase-276 entry and six journal-bound checkpoints passed; out-of-range candidates rejected')
