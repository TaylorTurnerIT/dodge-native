"""Bounded synthetic 512-sample PPO timing; fixed disabled/enabled order."""
import json, os, random, resource, time
import numpy as np
import torch
from dodge_rl.ppo import PPOConfig, ppo_update
from parity_fixture import fixture


def sync(device):
    if device == "mps": torch.mps.synchronize()


def seed(device):
    random.seed(991); np.random.seed(992); torch.manual_seed(993)
    if device == "mps": torch.mps.manual_seed(994)


def run(device):
    torch.set_num_threads(1 if device == "cpu" else 4)
    base, batch = fixture(512)
    base = base.to(device).eval()
    cfg = PPOConfig(update_epochs=1, minibatch_size=512, target_kl=100)
    def once(enabled):
        model = __import__('copy').deepcopy(base)
        opt = torch.optim.Adam(model.parameters(), lr=1e-4)
        seed(device); sync(device); start=time.perf_counter()
        result=ppo_update(model,opt,__import__('copy').deepcopy(batch),cfg,gradient_alignment_diagnostics=enabled)
        sync(device); elapsed=time.perf_counter()-start
        return elapsed, result
    # One unreported warmup pair; then at most three fixed-order paired repeats.
    once(False); once(True)
    pairs=[]
    for i in range(3):
        off, _=once(False); on, metrics=once(True)
        diag=metrics.get('gradient_alignment_diagnostics')
        pairs.append({'repeat':i+1,'disabled_seconds':off,'enabled_seconds':on,
                      'absolute_added_seconds':on-off,'minibatches':1,'epochs':1,'probe_count':diag['probe_count']})
    return {'device':device,'threads':torch.get_num_threads(),'samples':512,'pairs':pairs,
            'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'mps_allocated_bytes':torch.mps.current_allocated_memory() if device=='mps' else 0,
            'mps_driver_allocated_bytes':torch.mps.driver_allocated_memory() if device=='mps' else 0}

if __name__=='__main__':
    result={'scope':'synthetic 512-sample PPO update only; no rollout or environment',
            'results':[run(d) for d in ('cpu','mps') if d=='cpu' or torch.backends.mps.is_available()]}
    print(json.dumps(result,allow_nan=False),flush=True)
    cap=6*1024**3
    if any(r['peak_rss_bytes']>cap or r['mps_allocated_bytes']>cap or r['mps_driver_allocated_bytes']>cap for r in result['results']):
        raise SystemExit('resource cap exceeded')
