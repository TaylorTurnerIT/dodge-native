import json, os, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
from dodge_rl import VecDodgeEnv
seeds=json.loads(Path(sys.argv[2]).read_text())['seeds']
repeat1=bool(int(sys.argv[3]))

def clean(x):
    if isinstance(x,np.ndarray): return x.tolist()
    if isinstance(x,dict): return {k:clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)): return [clean(v) for v in x]
    if isinstance(x,np.generic): return x.item()
    return x

def snap(d): return clean(d)

def run(seed, repeat):
    e=VecDodgeEnv(batch_size=1,action_repeat=repeat,difficulty=2,patterns_enabled=True,powerups_enabled=True,raw_frame_cap=1024,num_threads=1,chunk_size=1,seeds_by_slot=[[seed]])
    initial=snap(e.observations())
    trace=[]
    for j in range(256):
        action=j%9
        r=e.step([action])
        trace.append(snap(r))
        if bool(r['terminated'][0]) or bool(r['truncated'][0]): break
    return e, initial, trace

rows=[]
for seed in seeds:
    e, initial, trace=run(seed,4)
    row={'seed':seed,'initial':initial,'repeat4_trace':trace,'batch_info':snap(e.batch_info())}
    if repeat1:
        f=VecDodgeEnv(batch_size=1,action_repeat=1,difficulty=2,patterns_enabled=True,powerups_enabled=True,raw_frame_cap=1024,num_threads=1,chunk_size=1,seeds_by_slot=[[seed]])
        frame_trace=[]; grouped=[]
        for j, r4 in enumerate(trace):
            actions=[]
            for _ in range(int(r4['elapsed_raw_frames'][0])):
                action=j%9; actions.append(action)
                rr=f.step([action]); frame_trace.append(snap(rr))
                if bool(rr['terminated'][0]) or bool(rr['truncated'][0]): break
            grouped.append({'actions':actions,'result':frame_trace[-1]})
            if len(actions)!=int(r4['elapsed_raw_frames'][0]): raise AssertionError('repeat1 stopped at different raw frame')
            if snap(r4['observations'])!=snap(grouped[-1]['result']['observations']): raise AssertionError(f'observation/history mismatch seed={seed} decision={j}')
            if snap(r4['info'])!=snap(grouped[-1]['result']['info']): raise AssertionError(f'episode info mismatch seed={seed} decision={j}')
            if sum(int(x['score_delta_raw_fixed'][0]) for x in frame_trace[-len(actions):])!=int(r4['score_delta_raw_fixed'][0]): raise AssertionError('score delta mismatch')
            if sum(int(x['elapsed_raw_frames'][0]) for x in frame_trace[-len(actions):])!=int(r4['elapsed_raw_frames'][0]): raise AssertionError('raw frame count mismatch')
            if sum(int(x['alive_raw_frames'][0]) for x in frame_trace[-len(actions):])!=int(r4['alive_raw_frames'][0]): raise AssertionError('alive frame count mismatch')
        row['repeat1_frame_trace']=frame_trace
        row['repeat1_groups']=grouped
        row['repeat1_batch_info']=snap(f.batch_info())
    rows.append(row)
Path(sys.argv[4]).write_text(json.dumps({'binary_role':os.environ['BINARY_ROLE'],'repeat1_equivalence':repeat1,'seeds':rows},sort_keys=True,separators=(',',':'))+'\n')
