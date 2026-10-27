import hashlib,importlib.util,json
from pathlib import Path
import numpy as np
ROOT=Path.cwd();OWN=Path(__file__).resolve().parent;source=ROOT/'learning/runs/v2/fixed-rollout-lambda-diagnostic-luna-20261026-r3/diagnostic.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()=='de763f423f8b1ff5123adce386945f4ee0a268d69c9391a592b0810b109e3da2'
spec=importlib.util.spec_from_file_location('diagnostic_review_r3',source);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
shape=(3,1);term=np.array([[False],[False],[True]])
data={'values':np.zeros(shape),'next_values':np.zeros(shape),'terminated':term,'truncated':np.zeros(shape,bool),'score_delta_raw_fixed':np.array([[65536],[131072],[0]],np.int64),'elapsed_raw_frames':np.full(shape,4,np.int64),'alive_raw_frames':np.array([[4],[4],[3]],np.int64)}
actual=d.analyze(data)['observed_death_comparison'];a,b,c=.104,.204,-.497;expected=[a+.995*b+.995**2*c,b+.995*c,c];expected_mean=float(np.mean(expected))
assert not np.isclose(actual['observed_discounted_return_mean'],expected_mean,rtol=0,atol=1e-8)
partial={'values':np.zeros(shape),'next_values':np.zeros(shape),'terminated':np.zeros(shape,bool),'truncated':np.zeros(shape,bool),'score_reward':np.zeros(shape),'survival_reward':np.zeros(shape),'death_reward':np.zeros(shape),'elapsed_raw_frames':np.full(shape,4,np.int64)}
d.analyze(partial)
r={'status':'both_R3_review_defects_reproduced_on_synthetic_CPU_arrays','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'observed_return_reported_mean':actual['observed_discounted_return_mean'],'expected_hand_returns':expected,'expected_observed_return_mean':expected_mean,'complete_components_plus_partial_raw_accepted':True,'actual_rollout_read':False,'training_or_capture':False,'MPS':False}
(OWN/'reproduction.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
