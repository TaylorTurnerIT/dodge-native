"""Diagnostic classification on held-out, heuristic-visited teacher states."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from dodge_learning.checkpoints import load_teacher_checkpoint
from dodge_learning.entity_teacher import encode_entities, batch_entities
from dodge_learning.env import NativeEnvironment
from dodge_learning.policies import AvoidancePolicy, ACTION_NAMES

parser=argparse.ArgumentParser()
parser.add_argument('checkpoints',nargs='+')
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if args.output.exists(): raise FileExistsError(args.output)
torch.set_num_threads(1)
states=[]; labels=[]; samples=[]; source=hashlib.sha256()
for seed in (2000,2001):
    with NativeEnvironment(seed=seed,max_episode_frames=1000) as environment:
        observation=environment.current(); controller=AvoidancePolicy()
        while not (observation['info']['terminated'] or observation['info']['truncated']):
            label=controller.act(observation)
            if observation['info']['episode_frames']%8==0:
                state=encode_entities(observation['privileged_state'])
                states.append(state); labels.append(label)
                sample=(seed,observation['info']['episode_frames'],observation['info']['state_hash'],label)
                samples.append(sample);source.update(json.dumps(sample).encode())
            observation=environment.step(label)
results=[]
for path in args.checkpoints:
    loaded=load_teacher_checkpoint(path); model=loaded.model.eval(); predicted=[]
    with torch.inference_mode():
        for start in range(0,len(states),16):
            logits,_=model(batch_entities(states[start:start+16]))
            predicted.extend(logits.argmax(-1).tolist())
    confusion=np.zeros((9,9),dtype=np.int64)
    for label,prediction in zip(labels,predicted): confusion[label,prediction]+=1
    recall={ACTION_NAMES[i]:float(confusion[i,i]/confusion[i].sum()) if confusion[i].sum() else None for i in range(9)}
    results.append({'checkpoint':str(path),'sha256':loaded.sha256,'accuracy':sum(a==b for a,b in zip(labels,predicted))/len(labels),'target_counts':dict(Counter(ACTION_NAMES[i] for i in labels)),'prediction_counts':dict(Counter(ACTION_NAMES[i] for i in predicted)),'recall':recall,'confusion_target_rows_prediction_columns':confusion.tolist()})
report={'diagnostic':'teacher_action_recall_on_heuristic_visited_smoke_states','seeds':[2000,2001],'episode_frame_cap':1000,'sample_stride':8,'samples':len(states),'sample_identity_sha256':source.hexdigest(),'inputs':'full_privileged_state','optimizer_steps':0,'qualification':'not_evaluated','results':results}
args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({'output':str(args.output),'results':[{k:r[k] for k in ['checkpoint','accuracy','prediction_counts','recall']} for r in results]}))
