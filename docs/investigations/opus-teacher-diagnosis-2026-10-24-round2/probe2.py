import json, time
import numpy as np, torch
from dodge_learning.env import NativeEnvironment
from dodge_learning.entity_teacher import encode_entities, batch_entities
from dodge_learning.checkpoints import load_teacher_checkpoint
from dodge_learning.policies import AvoidancePolicy, ACTION_NAMES, _DIRECTIONS
torch.set_num_threads(1)
R='runs/teacher-representation-ablation-r1/'
models={a:load_teacher_checkpoint(R+a+'.pt').model.eval() for a in ('baseline','relative')}
oracle=AvoidancePolicy()
def vel_action(p):
    # action whose direction matches sign of player velocity (|v|>0.05), i.e. "keep doing what you were doing"
    sx=0 if abs(p['vx'])<0.05 else (1 if p['vx']>0 else -1); sy=0 if abs(p['vy'])<0.05 else (1 if p['vy']>0 else -1)
    return _DIRECTIONS.index((sx,sy))
t0=time.time(); res={'schema':'opus-r2-onset-vs-continuation','dev_smoke_seeds_only':True,'definition':'oracle-driven rollouts, cap 1000; onset = oracle label differs from oracle label on previous frame; velocity_copy predictor = direction of sign(player vx,vy)','seeds':{}}
agg={k:[] for k in ('onset','cont')}
with NativeEnvironment(seed=2000,max_episode_frames=1000,action_repeat=1,discount=0.99) as env:
  for seed in (2000,2001,2002,2003,2004):
    obs=env.reset(seed=seed); prev=0; rows=[]; first=None
    while not(obs['info']['terminated'] or obs['info']['truncated']):
        lab=oracle.act(obs); p=obs['train_only_state']['player']
        with torch.no_grad(): pr={a:m.distillation_outputs(batch_entities([encode_entities(obs['privileged_state'])])).logits.softmax(-1)[0].numpy() for a,m in models.items()}
        r=dict(f=obs['info']['episode_frames'],lab=lab,onset=lab!=prev,vel=vel_action(p),**{a:int(v.argmax()) for a,v in pr.items()},**{a+'_plab':float(v[lab]) for a,v in pr.items()})
        if first is None and lab!=0: first=dict(frame=r['f'],label=ACTION_NAMES[lab],player={k:p[k] for k in ('x','y','vx','vy')},**{a+'_p':{ACTION_NAMES[i]:round(float(v[i]),4) for i in range(9)} for a,v in pr.items()})
        rows.append(r); prev=lab; obs=env.step(lab)
    on=[r for r in rows if r['onset']]; co=[r for r in rows if not r['onset']]
    def acc(rs,k): return float(np.mean([r[k]==r['lab'] for r in rs])) if rs else None
    s=dict(frames=len(rows),onsets=len(on),continuations=len(co),first_nonneutral=first)
    for k in ('baseline','relative','vel'):
        s[k]=dict(acc_onset=acc(on,k),acc_continuation=acc(co,k),acc_all=acc(rows,k),
                  agree_with_velocity_copy=float(np.mean([r[k]==r['vel'] for r in rows])) if k!='vel' else None)
    for k in ('baseline','relative'):
        s[k]['acc_nonneutral_onset']=acc([r for r in on if r['lab']!=0],k)
        s[k]['acc_nonneutral_continuation']=acc([r for r in co if r['lab']!=0],k)
        s[k]['acc_nonneutral_from_rest']=acc([r for r in rows if r['lab']!=0 and r['vel']==0],k)
        s[k]['n_nonneutral_from_rest']=sum(1 for r in rows if r['lab']!=0 and r['vel']==0)
    s['vel']['acc_nonneutral_continuation']=acc([r for r in co if r['lab']!=0],'vel')
    res['seeds'][seed]=s; print(seed,json.dumps(s),flush=True)
    if time.time()-t0>45: res['truncated_by_time']=True; break
res['elapsed']=time.time()-t0
json.dump(res,open('runs/teacher-failure-diagnosis/opus-r2-onset-vs-continuation.json','w'),indent=1)
