"""Summarize paired, fixed-driver explain_death replays."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

parser = argparse.ArgumentParser()
parser.add_argument('deaths', type=Path)
parser.add_argument('logs', type=Path)
args = parser.parse_args()
rows = [json.loads(line) for line in args.deaths.open()]
pattern = re.compile(r'^\s+(\w+)\s+[-0-9]+ \| (None|Some\(\d+\)) \| (None|Some\(\d+\))', re.M)
def frame(value):
    return None if value == 'None' else int(value[5:-1])
def read(seed, model):
    text = (args.logs / f'{seed}-{model}.log').read_text()
    candidate = re.search(r'^candidate action (\w+)', text, re.M)
    state = re.search(r'^state at frame (\d+): player \(([^)]+)\) planner action (\w+)', text, re.M)
    replay = re.search(r'^replay: dead=true at frame (\d+) \(recorded death frame (\d+)\)', text, re.M)
    actions = {m[1]: (frame(m[2]), frame(m[3])) for m in pattern.finditer(text)}
    if not candidate or not state or not replay or len(actions) != 9:
        raise ValueError(f'incomplete replay: {seed} {model}')
    return candidate[1], state.groups(), tuple(map(int, replay.groups())), actions

parsed = []
for r in rows:
    old, new = read(r['seed'], 'original'), read(r['seed'], 'candidate')
    if old[1:] and (old[1] != new[1] or old[2] != new[2]):
        raise ValueError(f'driver mismatch: {r["seed"]}')
    if old[2][0] != r['death_frame'] + 1:
        raise ValueError(f'death did not replay: {r["seed"]}')
    for action in old[3]:
        if old[3][action][1] != new[3][action][1]:
            raise ValueError(f'engine action mismatch: {r["seed"]} {action}')
    parsed.append((r, old, new))
print(f'Paired states: {len(parsed)}; all recorded deaths replayed with one-based frame offset 1.')
for label, select in [('all', lambda r: True), ('model-blind kamikaze/explosion', lambda r: r['class']=='model-blind' and r['cause'] in ('kamikaze_enemy','kamikaze_explosion')), ('chose-known-risk', lambda r: r['class']=='chose-known-risk')]:
    selected = [(r,a,b) for r,a,b in parsed if select(r)]
    print(f'\n{label}: {len(selected)} states')
    for h in (4,8,12,24,36):
        parts=[]
        for name, idx in [('original',1),('candidate',2)]:
            counts=Counter()
            for item in selected:
                model=item[idx]
                for pred, actual in model[3].values():
                    p=pred is not None and pred<=h
                    a=actual is not None and actual<=h
                    counts['tp']+=p and a
                    counts['fp']+=p and not a
                    counts['fn']+=not p and a
            tp,fp,fn=counts['tp'],counts['fp'],counts['fn']
            parts.append(f'{name} P={tp/(tp+fp):.3f} R={tp/(tp+fn):.3f} tp/fp/fn={tp}/{fp}/{fn}' if tp+fp and tp+fn else f'{name} P/R undefined')
        print(f'h={h}: '+ '; '.join(parts))
    for name, idx in [('original',1),('candidate',2)]:
        changed=avoids=0
        for r,old,new in selected:
            model=(old,new)[idx-1]
            action=model[0]
            changed+=action!=old[0]
            avoids+=model[3][action][1] is None
        print(f'{name}: changed actions {changed}; selected action survives 36 frames {avoids}/{len(selected)}')
