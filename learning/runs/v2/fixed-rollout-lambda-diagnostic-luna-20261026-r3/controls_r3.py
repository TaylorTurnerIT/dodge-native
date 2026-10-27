"""R3 synthetic CPU controls. No capture, checkpoint, environment, or training."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import numpy as np
import torch

torch.set_num_threads(2)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RUNTIME = ROOT / "learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime"
import sys
sys.path.insert(0, str(RUNTIME))
from dodge_rl.ppo import compute_gae
spec = importlib.util.spec_from_file_location("diagnostic_r3", HERE / "diagnostic.py")
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

T, N = 3, 4
values = np.array([[.2,.1,-.2,.5],[.3,.4,.1,.2],[0,.2,.3,-.1]], np.float32)
next_values = np.array([[.3,.4,.1,.2],[0,.5,.2,.3],[0,.2,.6,-.1]], np.float32)
term = np.array([[0,0,0,1],[1,0,0,0],[0,0,0,0]], bool)
trunc = np.array([[0,0,0,0],[0,1,0,0],[0,0,0,0]], bool)
score = np.array([[0,65536,0,0],[0,0,65536,0],[0,0,0,0]], np.int64)
elapsed = np.full((T,N),4,np.int64)
alive = elapsed-term.astype(np.int64)
data = {"values":values,"next_values":next_values,"terminated":term,"truncated":trunc,
        "score_delta_raw_fixed":score,"alive_raw_frames":alive,"elapsed_raw_frames":elapsed}
out = d.analyze(data)
r = (score/65536 + alive/100 - 5*term.astype(np.int64)).astype(np.float32)*.1
for lam in d.LAMBDAS:
    adv, targets = compute_gae(torch.from_numpy(r),torch.from_numpy(values),torch.from_numpy(next_values),
                               torch.from_numpy(term),torch.from_numpy(trunc),gamma=.995,gae_lambda=lam)
    row=out["lambda_comparison"][str(lam)]
    for key, expected in (("target_mean",targets.double().mean().item()),
                          ("target_variance",targets.double().var(unbiased=False).item()),
                          ("advantage_mean",adv.double().mean().item()),
                          ("advantage_variance",adv.double().var(unbiased=False).item())):
        assert abs(row[key]-expected)<2e-7,(lam,key,row[key],expected)

# Hand-solved terminal/reset/tail and truncation/bootstrap/reset cases.
one={"values":np.zeros((3,1),np.float32),"next_values":np.array([[0],[999],[2]],np.float32),
     "terminated":np.array([[0],[1],[0]],bool),"truncated":np.zeros((3,1),bool),
     "score_delta_raw_fixed":np.zeros((3,1),np.int64),"elapsed_raw_frames":np.full((3,1),4,np.int64),
     "alive_raw_frames":np.array([[4],[3],[4]],np.int64)}
for lam in d.LAMBDAS:
    expected=np.array([.004+.995*lam*(-.497),-.497,.004+.995*2])
    row=d.analyze(one)["lambda_comparison"][str(lam)]
    assert abs(row["target_mean"]-expected.mean())<2e-7 and abs(row["target_variance"]-expected.var())<2e-7
one["terminated"]=np.zeros((3,1),bool); one["truncated"]=np.array([[0],[1],[0]],bool)
one["alive_raw_frames"]=one["elapsed_raw_frames"].copy();one["next_values"]=np.array([[0],[2],[3]],np.float32)
for lam in d.LAMBDAS:
    expected=np.array([.004+.995*lam*(.004+.995*2),.004+.995*2,.004+.995*3])
    row=d.analyze(one)["lambda_comparison"][str(lam)]
    assert abs(row["target_mean"]-expected.mean())<2e-7 and abs(row["target_variance"]-expected.var())<2e-7

# Distance buckets partition all observed-death starts, including terminal state distance 0.
obs=out["observed_death_comparison"]
assert sum(obs["time_to_death_bucket_counts"].values())==obs["eligible_state_count"]
assert obs["time_to_death_bucket_counts"]["0"]==2
assert obs["excluded_truncation_count"]+obs["excluded_tail_censored_count"]+obs["eligible_state_count"]==T*N

# Exact constant target from repeated 0.1 inputs; preserve tiny genuine variance.
constant={"values":np.zeros((1,3),np.float32),"next_values":np.zeros((1,3),np.float32),
          "terminated":np.zeros((1,3),bool),"truncated":np.zeros((1,3),bool),
          "score_reward":np.full((1,3),.1),"survival_reward":np.zeros((1,3)),"death_reward":np.zeros((1,3))}
assert d.analyze(constant)["lambda_comparison"]["0.95"]["explained_variance_self_bootstrapped"] is None
near=dict(constant,score_reward=np.array([[.1,.1,.100000000001]]))
assert d.analyze(near)["lambda_comparison"]["0.95"]["target_variance"]>0

# NPZ reader to analyzer: variants, missing fields, shape, finite values, accounting, optional reward identity.
def rejected(payload):
    try: d.analyze(d.load_npz(payload))
    except (ValueError, OSError): return True
    return False
with tempfile.TemporaryDirectory(dir=HERE) as td:
    p=Path(td)/"case.npz"
    comp={"score_reward":np.zeros((T,N)),"survival_reward":np.zeros((T,N)),"death_reward":np.zeros((T,N))}
    np.savez(p,**(data|comp));assert rejected(p) # complete variants both present
    np.savez(p,**{k:v for k,v in data.items() if k!="elapsed_raw_frames"});assert rejected(p)
    malformed=dict(data,values=np.zeros((T,N+1),np.float32));np.savez(p,**malformed);assert rejected(p)
    nonfinite=dict(data,values=values.copy());nonfinite["values"][0,0]=np.nan;np.savez(p,**nonfinite);assert rejected(p)
    bad=dict(data,alive_raw_frames=np.full((T,N),5,np.int64));np.savez(p,**bad);assert rejected(p)
    mismatch=dict(data,rewards=np.zeros((T,N),np.float32));np.savez(p,**mismatch);assert rejected(p)
    np.savez(p,**data);assert d.analyze(d.load_npz(p))["lambda_comparison"]["0.95"]

print(json.dumps({"status":"PASS","checks":24,"production_parity_lambdas":[.95,.99],
 "hand_boundary_cases":2,"npz_reader_rejections":6,"observed_bucket_coverage":True,
 "CPU_threads":torch.get_num_threads(),"MPS_used":False,"actual_rollout_read":False,"training":False},sort_keys=True))
