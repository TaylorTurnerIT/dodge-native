import json,copy,time,sys
import numpy as np,torch
from dodge_learning.checkpoints import load_teacher_checkpoint
from dodge_learning.entity_teacher import encode_entities,batch_entities,EntityActorCritic
from dodge_learning.env import NativeEnvironment
from dodge_learning.policies import AvoidancePolicy
t0=time.time()
R='learning/runs/'
ck={'warm_ppo':R+'entity-teacher-warm-ppo-100000/teacher.pt','boot_weighted':R+'entity-teacher-bootstrap-weighted-10000/teacher.pt'}
models={k:load_teacher_checkpoint(v).model.eval() for k,v in ck.items()}
torch.manual_seed(7);models['fresh_init']=EntityActorCritic().eval()
# collect states along avoidance trajectory seed 2000
states=[];pol=AvoidancePolicy()
with NativeEnvironment(seed=2000,max_episode_frames=600) as env:
    o=env.current()
    while not(o['info']['terminated'] or o['info']['truncated']):
        if o['info']['episode_frames']%15==0: states.append(copy.deepcopy(o['privileged_state']))
        o=env.step(pol.act(o))
def run(m,ps):
    with torch.inference_mode(): return m.distillation_outputs(batch_entities([encode_entities(p) for p in ps]))
def edit(p,fn):
    q=copy.deepcopy(p);fn(q);return q
out={'n_states':len(states),'entity_counts':[len(s['entities']) for s in states][:5]}
kinds_hist={}
for e in states[-1]['entities']:kinds_hist[e['kind']]=kinds_hist.get(e['kind'],0)+1
out['kind_histogram_last_state']=kinds_hist
for name,m in models.items():
    r={}
    W=m.entity_projection.weight;b=m.entity_projection.bias
    emb=m.kind_embedding.weight
    # decomposition on enemy and player tokens
    feats={0:[],1:[],2:[]}
    for s in states:
        for e in s['entities']:
            if e['kind'] in feats: feats[e['kind']].append(e['features'])
    for k,F in feats.items():
        if not F: continue
        F=torch.tensor(F)
        Wf=F@W.T
        r[f'kind{k}']={'n':len(F),'kind_emb_norm':float(emb[k].norm()),'bias_norm':float(b.norm()),
          'Wf_norm_mean':float(Wf.norm(dim=1).mean()),'Wf_centered_std_norm':float((Wf-Wf.mean(0)).norm(dim=1).mean())}
    o=run(m,states)
    P=o.logits.softmax(-1);L=o.latent
    r['prob_std_across_states_max']=float(P.std(0).max());r['argmax']=o.logits.argmax(-1).tolist()
    r['latent_relstd']=float((L-L.mean(0)).norm(dim=1).mean()/L.norm(dim=1).mean())
    A=o.attention
    ent=-(A.clamp_min(1e-12)*A.clamp_min(1e-12).log()).sum(1)
    r['attention_entropy_mean']=float(ent.mean());r['log_n_mean']=float(np.mean([np.log(len(s['entities'])) for s in states]))
    # counterfactuals on a mid state
    base=states[len(states)//2]
    def setp(x,y):
        def f(q):q['entities'][0]['features'][0]=x/128;q['entities'][0]['features'][1]=y/128
        return f
    def enemy_on(dx,dy,vx,vy):
        def f(q):
            px=q['entities'][0]['features'][0]*128;py=q['entities'][0]['features'][1]*128
            for e in q['entities']:
                if e['kind']==1:
                    e['features'][0]=(px+dx)/128;e['features'][1]=(py+dy)/128;e['features'][2]=vx/4;e['features'][3]=vy/4;break
        return f
    def strip(q):q['entities']=[e for e in q['entities'] if e['kind'] in (0,1)]
    def noenemy(q):q['entities']=[e for e in q['entities'] if e['kind']!=1]
    variants={'base':base,'player_left_wall':edit(base,setp(2,64)),'player_right_wall':edit(base,setp(125,64)),'player_top':edit(base,setp(64,2)),
      'enemy_incoming_from_left':edit(base,enemy_on(-8,0,2,0)),'enemy_incoming_from_right':edit(base,enemy_on(8,0,-2,0)),
      'enemy_from_above':edit(base,enemy_on(0,-8,0,2)),'only_player_and_enemies':edit(base,strip),'no_enemies':edit(base,noenemy)}
    cf={}
    pb=run(m,[base]).logits.softmax(-1)[0]
    for vn,v in variants.items():
        p=run(m,[v]).logits.softmax(-1)[0]
        cf[vn]={'argmax':int(p.argmax()),'tv_from_base':float(0.5*(p-pb).abs().sum()),'probs':[round(float(x),3) for x in p]}
    r['counterfactuals']=cf
    # gradient sensitivity of logits wrt player x and nearest enemy x vs wrt nonspatial tokens
    enc=encode_entities(base);bt=batch_entities([enc])
    feat=bt.features.clone().requires_grad_(True)
    from dodge_learning.entity_teacher import EntityBatch
    bb=EntityBatch(bt.globals,feat,bt.kinds,bt.mask,bt.bounds,bt.spatial,bt.capture_bounds)
    lo=m.distillation_outputs(bb).logits
    g=torch.autograd.grad(lo.std(),feat)[0][0]
    kinds=bt.kinds[0]
    r['grad_logit_spread_by_kind']={int(k):float(g[kinds==k].abs().sum()) for k in kinds.unique()}
    out[name]=r
out['seconds']=time.time()-t0
json.dump(out,open('learning/runs/teacher-failure-diagnosis/opus-representation-probe.json','w'),indent=1)
print(json.dumps(out,indent=1))
