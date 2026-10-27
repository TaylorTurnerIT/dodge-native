import copy, json, os, time, resource
import torch
from torch.distributions import Categorical
from dodge_rl.ppo import PPOConfig, RolloutBatch, ppo_update
from dodge_rl.models.teacher import OmniscientEntityTeacher


def fixture(batch_size=8):
    torch.manual_seed(81723)
    model = OmniscientEntityTeacher().cpu().train()
    obs = dict(global_feats=torch.randn(1,batch_size,1,14), entity_feats=torch.randn(1,batch_size,80,16), entity_types=torch.randint(0,9,(1,batch_size,80)), entity_mask=torch.rand(1,batch_size,80)>.4)
    with torch.no_grad():
        out=model(*(obs[k][0] for k in ('global_feats','entity_feats','entity_types','entity_mask')))
        dist=Categorical(logits=out.logits); actions=dist.sample(); old=dist.log_prob(actions); values=out.values
    batch=RolloutBatch(**obs, actions=actions[None], old_log_probs=old[None], values=values[None], rewards=torch.randn(1,batch_size), next_values=torch.randn(1,batch_size), terminated=torch.zeros(1,batch_size,dtype=torch.bool), truncated=torch.zeros(1,batch_size,dtype=torch.bool))
    return model,batch


def main():
    torch.set_num_threads(2)
    base,batch=fixture(8)
    a,b=copy.deepcopy(base),copy.deepcopy(base)
    oa=torch.optim.Adam(a.parameters(),lr=1e-4); ob=torch.optim.Adam(b.parameters(),lr=1e-4)
    cfg=PPOConfig(update_epochs=2,minibatch_size=4,target_kl=100)
    torch.manual_seed(451)
    before=time.perf_counter(); ma=ppo_update(a,oa,copy.deepcopy(batch),cfg); dt0=time.perf_counter()-before
    rng0=torch.get_rng_state().clone()
    torch.manual_seed(451)
    before=time.perf_counter(); mb=ppo_update(b,ob,copy.deepcopy(batch),cfg,gradient_alignment_diagnostics=True); dt1=time.perf_counter()-before
    rng1=torch.get_rng_state().clone()
    assert torch.equal(rng0,rng1)
    assert {k:v for k,v in ma.items()} == {k:v for k,v in mb.items() if k!='gradient_alignment_diagnostics'}
    assert all(torch.equal(x,y) for x,y in zip(a.state_dict().values(),b.state_dict().values()))
    assert mb['gradient_alignment_diagnostics']['minibatch_samples']==4
    assert mb['optimizer_steps']==4
    print(json.dumps({'python':__import__('sys').version,'torch':torch.__version__,'module':__import__('dodge_rl.ppo',fromlist=['']).__file__,'disabled_seconds':dt0,'enabled_seconds':dt1,'overhead_fraction':dt1/dt0-1,'rss_max_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'metrics':mb['gradient_alignment_diagnostics']},default=str))

if __name__=='__main__': main()
