import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'runtime'))
from dodge_rl import VecDodgeEnv
seed=json.loads(Path(sys.argv[1]).read_text())['seeds'][0]
rows=[]
for repeat in ([4] if sys.argv[2]=='accepted' else [4,1]):
    try:
        VecDodgeEnv(batch_size=1,action_repeat=0,raw_frame_cap=8,seeds_by_slot=[[seed]])
        raise AssertionError('action_repeat=0 was accepted')
    except ValueError:
        pass
    env=VecDodgeEnv(batch_size=1,action_repeat=repeat,difficulty=2,patterns_enabled=True,powerups_enabled=True,raw_frame_cap=8,num_threads=1,chunk_size=1,seeds_by_slot=[[seed]])
    trace=[]
    for _ in range(8):
        result=env.step([0]); trace.append(result)
        if bool(result['terminated'][0]) or bool(result['truncated'][0]): break
    info=trace[-1]['info'][0]
    assert info['gameplay_frames']==8 and info['truncated'] and not info['terminated']
    assert sum(int(x['elapsed_raw_frames'][0]) for x in trace)==8
    rows.append({'action_repeat':repeat,'calls':len(trace),'gameplay_frames':info['gameplay_frames'],'truncated':info['truncated']})
Path(sys.argv[3]).write_text(json.dumps({'rows':rows},sort_keys=True)+'\n')
