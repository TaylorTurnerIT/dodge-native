from __future__ import annotations
import importlib.util
from pathlib import Path
OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('execute_once_under_test',OUT/'execute_once.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
metrics=[{'phase_update':u,'counters':{'updates':u-276,'optimizer_steps':3*(u-276),'environment_decisions':16384*(u-276),'raw_frames':1000*(u-276)}} for u in range(277,337)]
expected=[276,288,300,312,324,336]
assert module.r.EVALUATION_UPDATES==tuple(expected)
for update in expected:
 counters=module.expected_checkpoint_counters(update,metrics)
 state={'phase_update':update,'local_update':update-276,'update_progress':{'complete':True,'in_update':False,'completed_updates':update-276},'counters':counters,'optimizer':{'param_groups':[{'lr':0.00003}]}}
 module.validate_terminal_candidate_binding(state,update,counters)
assert module.expected_checkpoint_counters(276,[])=={'updates':0,'optimizer_steps':0,'environment_decisions':0,'raw_frames':0}
for update in [275,277,348]:
 try: module.expected_checkpoint_counters(update,metrics)
 except ValueError: pass
 else: raise AssertionError(f'unregistered boundary {update} accepted')
for mutate in [lambda x:x['update_progress'].__setitem__('in_update',True),lambda x:x['counters'].__setitem__('updates',99),lambda x:x['optimizer']['param_groups'][0].__setitem__('lr',0.0001)]:
 bad={'phase_update':336,'local_update':60,'update_progress':{'complete':True,'in_update':False,'completed_updates':60},'counters':dict(metrics[-1]['counters']),'optimizer':{'param_groups':[{'lr':0.00003}]}}
 mutate(bad)
 try: module.validate_terminal_candidate_binding(bad,336,metrics[-1]['counters'])
 except ValueError: pass
 else: raise AssertionError('mutated terminal candidate accepted')
print('production terminal validator: entry + five later candidates accepted; counter, progress, LR, and boundary mutations rejected')
