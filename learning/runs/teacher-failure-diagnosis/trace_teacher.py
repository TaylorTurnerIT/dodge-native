"""Read-only, bounded policy failure diagnostics; no training."""
from collections import Counter
import hashlib,json,math
from pathlib import Path
import torch
from dodge_learning.checkpoints import load_teacher_checkpoint
from dodge_learning.entity_teacher import encode_entities,batch_entities
from dodge_learning.env import NativeEnvironment
from dodge_learning.policies import AvoidancePolicy,ACTION_NAMES
from dodge_learning.teacher_eval import _verify_source_identity

torch.set_num_threads(1)
root=Path.cwd(); out=root/'learning/runs/teacher-failure-diagnosis'
checkpoint=root/'learning/runs/entity-teacher-warm-ppo-100000/teacher.pt'
loaded=load_teacher_checkpoint(checkpoint);model=loaded.model.eval()
identity,verified=_verify_source_identity(loaded.metadata['source_manifest'])
assert verified

def clearance(px,py,extent,x,y,w,h):
    dx=max(x-(px+extent),(px-extent)-(x+w),0.)
    dy=max(y-(py+extent),(py-extent)-(y+h),0.)
    if dx or dy:return math.hypot(dx,dy)
    return -min(px+extent-x,x+w-(px-extent),py+extent-y,y+h-(py-extent))

def nearest_hazard(o,weights):
    player=o['train_only_state']['player'];px,py=player['x'],player['y']
    rate=o['train_only_state']['globals']['speed']*o['train_only_state']['globals']['freeze_rate']
    candidates=[]
    for index,row in enumerate(o['privileged_state']['entities']):
        f=row['features'];kind=row['kind']
        if kind==1 and f[6]*4<2:
            x,y,vx,vy,s=f[0]*128,f[1]*128,f[2]*4,f[3]*4,f[4]*8
            extent=player['size']-1
            c=clearance(px,py,extent,x,y,s,s)
            candidates.append({'entity_index':index,'kind':'enemy','personality':f[6]*4,'x':x,'y':y,'vx':vx,'vy':vy,'size':s,'dx':x-px,'dy':y-py,'relative_vx':vx*rate-player['vx'],'relative_vy':vy*rate-player['vy'],'aabb_separation':c,'attention':weights[index]})
        elif kind==2 and f[16] and f[17]:
            x,y,vx,vy=f[0]*128,f[1]*128,f[2]*4,f[3]*4;w,h=f[5]*128,f[6]*128
            c=clearance(px,py,max(0,player['size']-2),x,y,w-1,h-1)
            candidates.append({'entity_index':index,'kind':'active_lethal_rectangle','x':x,'y':y,'vx':vx,'vy':vy,'width':w,'height':h,'dx':x-px,'dy':y-py,'relative_vx':vx-player['vx'],'relative_vy':vy-player['vy'],'aabb_separation':c,'attention':weights[index]})
    return min(candidates,key=lambda c:c['aabb_separation']) if candidates else None

def policy_snapshot(o):
    batch=batch_entities([encode_entities(o['privileged_state'])])
    with torch.inference_mode():r=model.distillation_outputs(batch)
    probabilities=r.logits.softmax(-1)[0].tolist();a=r.attention[0].tolist();by_kind={}
    for row,w in zip(o['privileged_state']['entities'],a):by_kind[str(row['kind'])]=by_kind.get(str(row['kind']),0.)+w
    order=sorted(range(len(a)),key=a.__getitem__,reverse=True)[:5]
    return {'teacher_action':int(r.logits.argmax(-1).item()),'teacher_action_name':ACTION_NAMES[int(r.logits.argmax(-1).item())],'probabilities':probabilities,'attention_by_kind':by_kind,'spatial_attention_mass':sum(w for row,w in zip(o['privileged_state']['entities'],a) if row['spatial']),'top_attention':[{'index':i,'kind':o['privileged_state']['entities'][i]['kind'],'attention':a[i],'features_first_five':o['privileged_state']['entities'][i]['features'][:5]}for i in order],'nearest_lethal_hazard':nearest_hazard(o,a),'entity_count':len(a)}

episodes=[]
for seed in (1000,2000):
    for controller in ('teacher','avoidance'):
        trace=[];actions=Counter();teacher_choices=Counter();disagreements=0;oracle=AvoidancePolicy()
        with NativeEnvironment(seed=seed,max_episode_frames=1000) as env:
            o=env.current()
            while not (o['info']['terminated'] or o['info']['truncated']):
                advice=oracle.act(o); frame=o['info']['episode_frames']
                # Teacher trajectories are queried every frame; avoidance
                # trajectories are sampled every eight frames for comparison.
                need_teacher=controller=='teacher' or frame%8==0
                pred=policy_snapshot(o) if need_teacher else None
                actual=pred['teacher_action'] if controller=='teacher' else advice
                actions[ACTION_NAMES[actual]]+=1
                if pred:
                    row={'episode_frame':frame,'native_frame':o['info']['frame'],'player':dict(o['train_only_state']['player']),'avoidance_action':advice,'avoidance_action_name':ACTION_NAMES[advice],'executed_action':actual,'executed_action_name':ACTION_NAMES[actual],**pred}
                    trace.append(row);teacher_choices[pred['teacher_action_name']]+=1;disagreements+=int(pred['teacher_action']!=advice)
                o=env.step(actual)
            episode={'seed':seed,'controller':controller,'native_frames':o['info']['episode_frames'],'survival_frames':o['info']['survival_frames'],'terminated':o['info']['terminated'],'truncated':o['info']['truncated'],'pattern_completions':o['info']['pattern_completions'],'action_counts':dict(actions),'teacher_query_count':len(trace),'teacher_prediction_counts':dict(teacher_choices),'teacher_avoidance_disagreements':disagreements,'disagreement_rate':disagreements/len(trace),'final_player':dict(o['train_only_state']['player']),'trace_stride':1 if controller=='teacher' else 8,'landmarks':[r for r in trace if r['episode_frame'] in (0,20,40,60,80,100,120,140,160,180,200,240,320,400,480,640,800,960)],'last_twenty_queried_states':trace[-20:],'all_queried_states':trace}
        episodes.append(episode)
report={'diagnostic':'teacher_failure_trace','checkpoint_path':str(checkpoint),'checkpoint_sha256':loaded.sha256,'runtime_source_identity_verified':verified,'runtime_source_identity':identity,'qualification':'not_evaluated_diagnostic_only','trained':False,'max_frames_per_policy_episode':1000,'hazard_distance':'approximate signed AABB separation, using native enemy player extent size-1; actual native fixed-point dynamics remain authoritative','attention_kind_ids':{'0':'player','1':'enemy_powerup','2':'rectangle','3':'warning','4':'pattern','5':'queued_target','6':'spawn','7':'particle','8':'RNG_word','10':'settings','11':'highscore','12':'palette','13':'queued_spawn','14':'variant'},'episodes':episodes}
p=out/'teacher-failure-traces.json';p.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({'path':str(p),'episodes':[{k:e[k]for k in ('seed','controller','native_frames','survival_frames','terminated','truncated','pattern_completions','action_counts','teacher_query_count','teacher_prediction_counts','disagreement_rate')}for e in episodes]},indent=2))
