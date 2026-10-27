"""Parent synthetic CPU checks, including actual analyzer-to-production moments."""
import hashlib,json,os,runpy,sys,time
from pathlib import Path
import numpy as np
import torch
torch.set_num_threads(2)
ROOT=Path.cwd();SOURCE=ROOT/'learning/runs/v2/fixed-rollout-lambda-diagnostic-luna-20261026-r1';OWN=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
receipt=json.loads((SOURCE/'receipt.json').read_text())
for name,digest in receipt['owned_outputs_sha256'].items():assert sha(SOURCE/name)==digest,name
assert sha(ROOT/receipt['pinned_compute_gae_source']['path'])==receipt['pinned_compute_gae_source']['sha256']
before={str(p.relative_to(SOURCE)):sha(p) for p in SOURCE.rglob('*') if p.is_file()}
started=time.monotonic();context=runpy.run_path(str(SOURCE/'controls.py'),run_name='__main__');d=context['diagnostic'];compute=context['compute_gae'];data=context['data'];analyzed=d.analyze(data);r=context['r'];checks={}
for lam in d.LAMBDAS:
    adv,targets=compute(torch.from_numpy(r),torch.from_numpy(data['values']),torch.from_numpy(data['next_values']),torch.from_numpy(data['terminated']),torch.from_numpy(data['truncated']),gamma=.995,gae_lambda=lam)
    row=analyzed['lambda_comparison'][str(lam)]
    expected={'target_mean':targets.double().mean().item(),'target_variance':targets.double().var(unbiased=False).item(),'advantage_mean':adv.double().mean().item(),'advantage_variance':adv.double().var(unbiased=False).item()}
    for key,value in expected.items():assert abs(row[key]-value)<2e-7,(lam,key,row[key],value)
    checks[f'actual_analyzer_vs_production_lambda_{lam}']=expected
# Hand-solvable boundary sequence. Next value999 at terminal must be ignored.
term=np.array([[False],[True],[False]]);elapsed=np.full((3,1),4,np.int64)
case={'values':np.zeros((3,1),np.float32),'next_values':np.array([[0],[999],[2]],np.float32),'terminated':term,'truncated':np.zeros((3,1),bool),'score_delta_raw_fixed':np.zeros((3,1),np.int64),'alive_raw_frames':elapsed-term.astype(np.int64),'elapsed_raw_frames':elapsed}
a=d.analyze(case)
for lam in d.LAMBDAS:
    expected=np.array([.004+.995*lam*(-.497),-.497,.004+.995*2])
    row=a['lambda_comparison'][str(lam)]
    assert abs(row['target_mean']-expected.mean())<2e-7
    assert abs(row['target_variance']-expected.var())<2e-7
checks['hand_terminal_reset_and_tail']=True
# Time-limit step bootstraps final observation, cuts recurrence into reset segment.
case['terminated']=np.zeros((3,1),bool);case['truncated']=term;case['alive_raw_frames']=elapsed;case['next_values']=np.array([[0],[2],[3]],np.float32)
a=d.analyze(case)
for lam in d.LAMBDAS:
    expected=np.array([.004+.995*lam*(.004+.995*2),.004+.995*2,.004+.995*3])
    row=a['lambda_comparison'][str(lam)]
    assert abs(row['target_mean']-expected.mean())<2e-7
    assert abs(row['target_variance']-expected.var())<2e-7
checks['hand_truncation_bootstrap_and_reset_cut']=True
bad=dict(case,alive_raw_frames=np.full((3,1),5,np.int64))
try:d.analyze(bad)
except ValueError:checks['invalid_raw_accounting_rejected']=True
else:raise AssertionError('invalid raw frames passed')
assert before=={str(p.relative_to(SOURCE)):sha(p) for p in SOURCE.rglob('*') if p.is_file()}
assert not any((OWN/'empty-cache').iterdir())
report={'status':'passed_synthetic_controls_plus_direct_analyzer_production_parity_and_hand_cases','checks':checks,'source_unchanged':True,'CPU_threads':torch.get_num_threads(),'MPS_used':False,'actual_rollout_read':False,'capture':False,'training':False,'source_receipt_sha256':sha(SOURCE/'receipt.json'),'elapsed_seconds':time.monotonic()-started,'source_test_limitation':'Original controls never compared analyzer moments to production; parent direct comparisons above close that narrow gap without editing frozen source.'}
(OWN/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'elapsed_seconds':report['elapsed_seconds']}))
