"""Synthetic-only exact enabled/disabled PPO parity on CPU and MPS."""
import copy, hashlib, json, os, random, resource, subprocess, time
import numpy as np
import torch
from torch.distributions import Categorical
from dodge_rl.ppo import PPOConfig, RolloutBatch, ppo_update
from dodge_rl.models.teacher import OmniscientEntityTeacher


def snapshot_batch(batch):
    return {k: (v.detach().clone() if torch.is_tensor(v) else v) for k, v in vars(batch).items()}


def fixture(batch_size=8):
    torch.manual_seed(81723)
    model = OmniscientEntityTeacher().cpu().eval()
    gf = torch.randn(1, batch_size, 1, 14)
    ef = torch.randn(1, batch_size, 80, 16)
    et = torch.randint(1, 9, (1, batch_size, 80))
    et[0, 0] = torch.arange(1, 9).repeat(10)
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


def first_difference(a, b, path="root"):
    if torch.is_tensor(a) and torch.is_tensor(b):
        if not torch.equal(a, b): return {"name": path, "max_abs_delta": float((a.detach().cpu()-b.detach().cpu()).abs().max().item()), "shape": list(a.shape)}
    elif isinstance(a, np.ndarray) and isinstance(b, np.ndarray):
        if not np.array_equal(a,b): return {"name":path,"max_abs_delta":float(np.max(np.abs(a-b)))}
    elif isinstance(a, dict) and isinstance(b, dict):
        if a.keys()!=b.keys(): return {"name":path,"left_keys":list(map(str,a.keys())),"right_keys":list(map(str,b.keys()))}
        for key in a:
            result=first_difference(a[key],b[key],path+"."+str(key))
            if result: return result
    elif isinstance(a,(tuple,list)) and isinstance(b,(tuple,list)):
        if len(a)!=len(b): return {"name":path,"left_len":len(a),"right_len":len(b)}
        for i,(x,y) in enumerate(zip(a,b)):
            result=first_difference(x,y,path+f"[{i}]")
            if result: return result
    elif a != b: return {"name":path,"left":str(a),"right":str(b)}
    return None


def fingerprint(value):
    h=hashlib.sha256()
    def visit(v):
        if torch.is_tensor(v): h.update(v.detach().cpu().contiguous().numpy().tobytes())
        elif isinstance(v,dict):
            for k in sorted(v,key=str): h.update(str(k).encode()); visit(v[k])
        elif isinstance(v,(list,tuple)):
            for item in v: visit(item)
        else: h.update(repr(v).encode())
    visit(value)
    return h.hexdigest()

def run_device(device):
    torch.set_num_threads(1 if device == "cpu" else 4)
    base, original_batch = fixture()
    batch_before = snapshot_batch(original_batch)
    a, b, c = copy.deepcopy(base).to(device), copy.deepcopy(base).to(device), copy.deepcopy(base).to(device)
    a.eval(); b.eval(); c.eval()
    oa = torch.optim.Adam(a.parameters(), lr=1e-4); ob = torch.optim.Adam(b.parameters(), lr=1e-4); oc = torch.optim.Adam(c.parameters(), lr=1e-4)
    cfg = PPOConfig(update_epochs=2, minibatch_size=4, target_kl=100)
    def seed_all():
        random.seed(991); np.random.seed(992); torch.manual_seed(993)
        if device == 'mps': torch.mps.manual_seed(994)
    def rng():
        return {'python': random.getstate(), 'numpy': np.random.get_state(), 'torch_cpu': torch.get_rng_state().clone(),
                'torch_mps': torch.mps.get_rng_state().clone() if device == 'mps' else None}
    batch_a, batch_b = copy.deepcopy(original_batch), copy.deepcopy(original_batch)
    seed_all(); start=time.perf_counter(); ma=ppo_update(a,oa,batch_a,cfg); t0=time.perf_counter()-start; rng0=rng()
    batch_c = copy.deepcopy(original_batch)
    seed_all(); mc=ppo_update(c,oc,batch_c,cfg); rngc=rng()
    try:
        equal_tree(ma,mc,"baseline_metrics"); equal_tree(a.state_dict(),c.state_dict(),"baseline_model")
        equal_tree(oa.state_dict(),oc.state_dict(),"baseline_adam"); equal_tree(rng0,rngc,"baseline_rng")
        baseline_control=True; baseline_delta=None
    except AssertionError:
        baseline_control=False
        baseline_delta=first_difference(a.state_dict(),c.state_dict(),"baseline.model") or first_difference(oa.state_dict(),oc.state_dict(),"baseline.adam") or first_difference(ma,mc,"baseline.metrics") or first_difference(rng0,rngc,"baseline.rng")
    seed_all(); start=time.perf_counter(); mb=ppo_update(b,ob,batch_b,cfg,gradient_alignment_diagnostics=True); t1=time.perf_counter()-start; rng1=rng()
    diag=mb['gradient_alignment_diagnostics']
    def finite_tree(value, path='diag'):
        if isinstance(value, dict):
            for k, v in value.items(): finite_tree(v, path+'.'+str(k))
        elif isinstance(value, (list, tuple)):
            for i, v in enumerate(value): finite_tree(v, path+f'[{i}]')
        elif isinstance(value, float): assert np.isfinite(value), f'nonfinite {path}'
        elif value is None: raise AssertionError(f'None at {path}')
    finite_tree(diag)
    assert diag['backend']=='cpu_shadow' and diag['measures_live_MPS_gradients'] is False
    assert diag['snapshot']=='first_minibatch_pre_optimizer_step' and diag['probe_count']==1
    common={k:v for k,v in ma.items()}; enabled={k:v for k,v in mb.items() if k!='gradient_alignment_diagnostics'}
    parity_error = None
    try:
        equal_tree(common,enabled,'metrics'); equal_tree(a.state_dict(),b.state_dict(),'model')
        equal_tree(oa.state_dict(),ob.state_dict(),'adam'); equal_tree(oa.param_groups,ob.param_groups,'param_groups')
        equal_tree(rng0,rng1,'rng')
        assert a.training is False and b.training is False
        equal_tree(batch_before,snapshot_batch(batch_a),'batch_disabled')
        equal_tree(batch_before,snapshot_batch(batch_b),'batch_enabled')
        equal_tree([p.grad for p in a.parameters()],[p.grad for p in b.parameters()],'postclip_grad_buffers')
    except AssertionError as exc:
        parity_error = str(exc)
    def fingerprint(state):
        h=hashlib.sha256()
        for name,value in state.items():
            h.update(str(name).encode())
            if torch.is_tensor(value): h.update(value.detach().cpu().contiguous().numpy().tobytes())
            else: h.update(repr(value).encode())
        return h.hexdigest()
    mismatch = first_difference(a.state_dict(),b.state_dict(),"model") or first_difference(oa.state_dict(),ob.state_dict(),"adam") if parity_error else None
    if parity_error and mismatch is None and 'tensor mismatch at ' in parity_error:
        path=parity_error.split('tensor mismatch at ',1)[1]
        aa,bb=(oa.state_dict(),ob.state_dict()) if path.startswith('adam') else (a.state_dict(),b.state_dict())
        try:
            parts=path.split('.')[1:]
            for part in parts: aa=aa[part]; bb=bb[part]
            if torch.is_tensor(aa) and torch.is_tensor(bb): mismatch={'name':path,'max_abs_delta':float((aa-bb).abs().max().item()),'shape':list(aa.shape)}
        except Exception: pass
    assert ma['optimizer_steps']==mb['optimizer_steps']==4
    assert diag['minibatch_count']==4
    expected=min(1.0,cfg.max_grad_norm/(diag['live_preclip_grad_norm']+1e-6))
    assert diag['live_clip_coefficient']==expected
    return {'device':device,'threads':torch.get_num_threads(),'disabled_seconds':t0,'enabled_seconds':t1,'optimizer_steps':4,'baseline_repeat_exact':baseline_control,'baseline_mismatch':baseline_delta,'enabled_parity':'exact' if parity_error is None else 'failed','parity_error':parity_error,'mismatch':mismatch,'disabled_model_sha256':fingerprint(a.state_dict()),'enabled_model_sha256':fingerprint(b.state_dict()),'disabled_adam_sha256':fingerprint(oa.state_dict()),'enabled_adam_sha256':fingerprint(ob.state_dict()),
            'probe_count':1,'diagnostics':diag,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'driver_allocated_bytes':torch.mps.driver_allocated_memory() if device=='mps' else 0,
            'mps_allocated_bytes':torch.mps.current_allocated_memory() if device=='mps' else 0}


if __name__=='__main__':
    outputs=[]
    for dev in ('cpu','mps'):
        if dev=='mps' and not torch.backends.mps.is_available(): raise RuntimeError('MPS unavailable')
        outputs.append(run_device(dev))
    print(json.dumps({'fixture':'synthetic frozen RolloutBatch; no episode PRNG or checkpoint', 'results':outputs},allow_nan=False,default=str), flush=True)
    if any(item['enabled_parity'] != 'exact' or not item['baseline_repeat_exact'] for item in outputs): raise SystemExit(2)
