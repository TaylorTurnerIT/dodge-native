import importlib.util,json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path.cwd();OWN=Path(__file__).resolve().parent;source=ROOT/'learning/runs/v2/fixed-rollout-lambda-diagnostic-luna-20261026-r1'
spec=importlib.util.spec_from_file_location('review_diagnostic',source/'diagnostic.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
shape=(1,3);z=np.zeros(shape);flags=np.zeros(shape,bool)
case={'values':z.copy(),'next_values':z.copy(),'terminated':flags.copy(),'truncated':flags.copy(),'score_reward':np.full(shape,.1),'survival_reward':z.copy(),'death_reward':z.copy()}
constant=d.analyze(case)['lambda_comparison']['0.95']
both=dict(case,score_delta_raw_fixed=np.zeros(shape,np.int64),alive_raw_frames=np.full(shape,4,np.int64),elapsed_raw_frames=np.full(shape,4,np.int64))
try:d.analyze(both)
except ValueError as e:both_rejected=str(e)
else:raise AssertionError('both variants unexpectedly accepted')
death=dict(case,terminated=np.ones(shape,bool),score_reward=z.copy(),survival_reward=np.full(shape,.003),death_reward=np.full(shape,-.5))
observed=d.analyze(death)['observed_death_comparison']
result={'raw_plus_scaled_variants_rejected':both_rejected,'constant_target_EV_reported':constant['explained_variance_self_bootstrapped'],'constant_target_variance_reported':constant['target_variance'],'constant_target_expected_EV':None,'distance_zero_eligible_states':observed['eligible_state_count'],'distance_zero_current_bucket_means':observed['time_to_death_bucket_means'],'scope':'CPU NumPy synthetic examples only; no capture or current training modification'}
(OWN/'review-triage-evidence.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
