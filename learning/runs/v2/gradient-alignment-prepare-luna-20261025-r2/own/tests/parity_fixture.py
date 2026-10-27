"""Synthetic-only exact enabled/disabled PPO parity on CPU and MPS."""
import copy, json, os, random, subprocess, time
import numpy as np
import torch
from torch.distributions import Categorical
from dodge_rl.ppo import PPOConfig, RolloutBatch, ppo_update
from dodge_rl.models.teacher import OmniscientEntityTeacher
import importlib.util

RUNNER = os.path.abspath('learning/runs/v2/critic-diagnostic-runner-prepare-20261025-r1/runner.py')
spec = importlib.util.spec_from_file_location('frozen_runner', RUNNER)
runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)


def snapshot_batch(batch):
    return {k: (v.detach().clone() if torch.is_tensor(v) else v) for k, v in vars(batch).items()}


def fixture(batch_size=8):
    torch.manual_seed(81723)
    model = OmniscientEntityTeacher().cpu().eval()
    gf = torch.randn(1, batch_size, 1, 14)
    ef = torch.randn(1, batch_size, 80, 16)
    et = torch.randint(1, 9, (1, batch_size, 80))
    mask = torch.zeros(1, batch_size, 80, dtype=torch.bool)
    mask[:, 0, :1] = True; mask[:, 1, :17] = True; mask[:, 2, :] = True
    # Rows 3..7 intentionally have no valid entity; global observation remains valid.
    with torch.no_grad():
        out = model(gf[0], ef[0], et[0], mask[0])
        dist = Categorical(logits=out.logits); actions = dist.sample(); old = dist.log_prob(actions); values = out.values
    batch = RolloutBatch(global_feats=gf, entity_feats=ef, entity_types=et, entity_mask=mask,
        actions=actions[None], old_log_probs=old[None], values=values[None], rewards=torch.randn(1,batch_size),
        next_values=torch.randn(1,batch_size), terminated=torch.zeros(1,batch_size,dtype=torch.bool),
        truncated=torch.zeros(1,batch_size,dtype=torch.bool))
    return model, batch


def equal_tree(a, b, path='root'):
    if torch.is_tensor(a):
        assert torch.equal(a, b), f'tensor mismatch at {path}'
    elif isinstance(a, np.ndarray):
        assert np.array_equal(a, b), f'array mismatch at {path}'
    elif isinstance(a, dict):
        assert a.keys() == b.keys(), f'keys mismatch at {path}'
        for k in a: equal_tree(a[k], b[k], path+'.'+str(k))
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), f'length mismatch at {path}'
        for i, (x,y) in enumerate(zip(a,b)): equal_tree(x,y,path+f'[{i}]')
    elif isinstance(a, float):
        assert a == b, f'float mismatch at {path}: {a} != {b}'
    else:
        assert a == b, f'mismatch at {path}: {a} != {b}'


def run_device(device):
    torch.set_num_threads(2)
    base, original_batch = fixture()
    batch_before = snapshot_batch(original_batch)
    a, b = copy.deepcopy(base).to(device), copy.deepcopy(base).to(device)
    a.eval(); b.eval()
    oa = torch.optim.Adam(a.parameters(), lr=1e-4); ob = torch.optim.Adam(b.parameters(), lr=1e-4)
    cfg = PPOConfig(update_epochs=2, minibatch_size=4, target_kl=100)
    def seed_all():
        random.seed(991); np.random.seed(992); torch.manual_seed(993)
        if device == 'mps': torch.mps.manual_seed(994)
    def rng():
        return {'python': random.getstate(), 'numpy': np.random.get_state(), 'torch_cpu': torch.get_rng_state().clone(),
                'torch_mps': torch.mps.get_rng_state().clone() if device == 'mps' else None}
    batch_a, batch_b = copy.deepcopy(original_batch), copy.deepcopy(original_batch)
    seed_all(); start=time.perf_counter(); ma=ppo_update(a,oa,batch_a,cfg); t0=time.perf_counter()-start; rng0=rng()
    seed_all(); start=time.perf_counter(); mb=ppo_update(b,ob,batch_b,cfg,gradient_alignment_diagnostics=True); t1=time.perf_counter()-start; rng1=rng()
    diag=mb['gradient_alignment_diagnostics']; runner.finite_tree(diag)
    common={k:v for k,v in ma.items()}; enabled={k:v for k,v in mb.items() if k!='gradient_alignment_diagnostics'}
    equal_tree(common,enabled,'metrics')
    equal_tree(a.state_dict(),b.state_dict(),'model')
    equal_tree(oa.state_dict(),ob.state_dict(),'adam')
    equal_tree(oa.param_groups,ob.param_groups,'param_groups')
    equal_tree(rng0,rng1,'rng')
    assert a.training is False and b.training is False
    equal_tree(batch_before,snapshot_batch(batch_a),'batch_disabled')
    equal_tree(batch_before,snapshot_batch(batch_b),'batch_enabled')
    equal_tree([p.grad for p in a.parameters()],[p.grad for p in b.parameters()],'postclip_grad_buffers')
    assert ma['optimizer_steps']==mb['optimizer_steps']==4
    assert diag['minibatch_samples']==4 and diag['epoch_index']==0 and diag['minibatch_index']==0
    # Verify coefficient against exact original global norm formula.
    expected=min(1.0,cfg.max_grad_norm/(diag['global_preclip_norm']+1e-6))
    assert diag['global_clip_coefficient']==expected
    return {'device':device,'disabled_seconds':t0,'enabled_seconds':t1,'optimizer_steps':4,
            'probe_count':1,'diagnostics':diag,'driver_allocated_bytes':torch.mps.driver_allocated_memory() if device=='mps' else 0,
            'mps_allocated_bytes':torch.mps.current_allocated_memory() if device=='mps' else 0}


if __name__=='__main__':
    outputs=[]
    for dev in ('cpu','mps'):
        if dev=='mps' and not torch.backends.mps.is_available(): raise RuntimeError('MPS unavailable')
        outputs.append(run_device(dev))
    print(json.dumps({'fixture':'synthetic frozen RolloutBatch; no episode PRNG or checkpoint', 'results':outputs},allow_nan=False,default=str))
