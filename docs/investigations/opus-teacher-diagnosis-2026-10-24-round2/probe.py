import json, sys, time, copy, math
import numpy as np, torch
from dodge_learning.env import NativeEnvironment
from dodge_learning.entity_teacher import encode_entities, batch_entities
from dodge_learning.checkpoints import load_teacher_checkpoint
from dodge_learning.policies import AvoidancePolicy, ACTION_NAMES, _box_clearance
torch.set_num_threads(1)
R='runs/teacher-representation-ablation-r1/'
models={a:load_teacher_checkpoint(R+a+'.pt').model.eval() for a in ('baseline','relative')}
oracle=AvoidancePolicy()
def strip(obs):
    o=copy.deepcopy(obs); s=o['train_only_state']; s['enemies']=[]; s['rectangles']=[]; s['warnings']=[]; return o
def costs(obs):
    # recompute oracle cost vector via act internals: monkey min
    import dodge_learning.policies as P
    vals={}
    orig=min
    return None
def clearance(obs):
    s=obs['train_only_state']; p=s['player']; ext=max(0.0,float(p['size'])-2)
    c=[_box_clearance(float(p['x']),float(p['y']),float(e['x']),float(e['y']),float(e['size']),float(e['size']))-ext for e in s['enemies'] if int(e['kind'])<2]
    c+=[_box_clearance(float(p['x']),float(p['y']),float(r['x']),float(r['y']),float(r['width']),float(r['height']))-ext for r in s['rectangles']]
    return min(c) if c else 999.0
def probs(m,obs):
    with torch.no_grad():
        return m.distillation_outputs(batch_entities([encode_entities(obs['privileged_state'])])).logits.softmax(-1)[0].numpy()
out={'schema':'opus-r2-closed-loop-probe','dev_smoke_seeds_only':True,'arms':{}}
t0=time.time()
with NativeEnvironment(seed=2000,max_episode_frames=1000,action_repeat=1,discount=0.99) as env:
  # A) oracle-visited states: category accuracy
  for driver in ('oracle','baseline','relative'):
    for seed in (2000,2001,2002):
      obs=env.reset(seed=seed); rows=[]
      while not(obs['info']['terminated'] or obs['info']['truncated']):
        lab=oracle.act(obs); center=oracle.act(strip(obs)); cl=clearance(obs)
        pr={a:probs(m,obs) for a,m in models.items()}
        act = lab if driver=='oracle' else int(pr[driver].argmax())
        rows.append(dict(f=obs['info']['episode_frames'],lab=lab,center=center,cl=round(cl,2),
             **{a+'_pred':int(p.argmax()) for a,p in pr.items()},
             **{a+'_plab':round(float(p[lab]),3) for a,p in pr.items()},
             **{a+'_pneu':round(float(p[0]),3) for a,p in pr.items()}))
        obs=env.step(act)
        if time.time()-t0>50: break
      n=len(rows); key=f'{driver}:{seed}'
      ed=[r for r in rows if r['lab']!=r['center']]; cd=[r for r in rows if r['lab']==r['center']]
      danger=[r for r in rows if r['cl']<6]
      summ=dict(frames=n,terminated=bool(obs['info']['terminated']),patterns=obs['info'].get('pattern_completions'),
        enemy_driven_labels=len(ed),center_driven_labels=len(cd),danger_frames_cl_lt6=len(danger),
        oracle_label_counts={ACTION_NAMES[i]:sum(r['lab']==i for r in rows) for i in range(9) if any(r['lab']==i for r in rows)})
      for a in models:
        summ[a]=dict(acc_all=np.mean([r[a+'_pred']==r['lab'] for r in rows]) if rows else None,
          acc_enemy_driven=float(np.mean([r[a+'_pred']==r['lab'] for r in ed])) if ed else None,
          acc_center_driven=float(np.mean([r[a+'_pred']==r['lab'] for r in cd])) if cd else None,
          acc_danger=float(np.mean([r[a+'_pred']==r['lab'] for r in danger])) if danger else None,
          pred_neutral_frac=float(np.mean([r[a+'_pred']==0 for r in rows])),
          mean_p_label_enemy_driven=float(np.mean([r[a+'_plab'] for r in ed])) if ed else None,
          mean_p_neutral_enemy_driven=float(np.mean([r[a+'_pneu'] for r in ed])) if ed else None)
        summ[a]={k:(float(v) if v is not None else None) for k,v in summ[a].items()}
      summ['last20']=rows[-20:] if driver!='oracle' else None
      out['arms'][key]=summ
      print(key,json.dumps({k:v for k,v in summ.items() if k!='last20'}),flush=True)
      if time.time()-t0>50: out['truncated_by_time']=True; break
    if time.time()-t0>50: break
out['elapsed']=time.time()-t0
json.dump(out,open('runs/teacher-failure-diagnosis/opus-r2-closed-loop-probe.json','w'),indent=1,default=float)
