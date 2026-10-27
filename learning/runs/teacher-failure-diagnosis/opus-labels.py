import json,copy,time
from collections import Counter
from dodge_learning.env import NativeEnvironment
from dodge_learning.policies import AvoidancePolicy,ACTION_NAMES
t0=time.time();pol=AvoidancePolicy();n=0;changed=0;labels=Counter();nonneutral_enemy_dependent=0;nonneutral=0
for seed in range(2000,2005):
    with NativeEnvironment(seed=seed,max_episode_frames=1000) as env:
        o=env.current()
        while not(o['info']['terminated'] or o['info']['truncated']):
            a=pol.act(o)
            q={**o,'train_only_state':{**o['train_only_state'],'enemies':[]}}
            b=pol.act(q)
            n+=1;labels[ACTION_NAMES[a]]+=1;changed+=a!=b
            if a!=0: nonneutral+=1;nonneutral_enemy_dependent+=a!=b
            o=env.step(a)
out={'diagnostic':'avoidance_label_enemy_dependence','states':n,'labels':dict(labels),'fraction_labels_changed_when_enemies_removed':changed/n,'nonneutral':nonneutral,'fraction_nonneutral_enemy_dependent':nonneutral_enemy_dependent/max(1,nonneutral),'seconds':time.time()-t0,'note':'enemies list in train_only_state also contains rectangles? see policies.py kind>=2 filter'}
json.dump(out,open('learning/runs/teacher-failure-diagnosis/opus-label-enemy-dependence.json','w'),indent=1);print(out)
