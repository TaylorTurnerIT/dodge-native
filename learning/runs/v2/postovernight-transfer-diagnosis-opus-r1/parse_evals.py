"""Read-only parse of retained D1/D2 deterministic development evaluation rows."""
import json, glob, os, statistics as st, collections, sys
root = sys.argv[1]
out = {}
def load(p):
    return [json.loads(l) for l in open(p)]
files = sorted(glob.glob(f"{root}/learning/runs/v2/milestone3-D*-curriculum-r1/*-development.jsonl")) + \
        sorted(glob.glob(f"{root}/learning/runs/v2/milestone3-D1-pilot-r1/*-development.jsonl"))
for p in files:
    rows = load(p)
    ev = p.replace('-D2-development.jsonl','.pt.evaluation.json').replace('-D1-development.jsonl','.pt.evaluation.json')
    alive = [r['alive_frames'] for r in rows]; score=[r['score'] for r in rows]
    hist = collections.Counter((a//25)*25 for a in alive)
    near465 = sum(1 for a in alive if 455 <= a <= 475)
    out[os.path.relpath(p, root)] = dict(n=len(rows), mean_alive=st.mean(alive), median_alive=st.median(alive),
        min_alive=min(alive), max_alive=max(alive), mean_score=st.mean(score), caps=sum(r['truncated'] for r in rows),
        alive_455_475=near465, top_bins=hist.most_common(6),
        alive_by_seed={r['seed']: r['alive_frames'] for r in rows}, score_by_seed={r['seed']: r['score'] for r in rows})
json.dump(out, open(f"{root}/learning/runs/v2/postovernight-transfer-diagnosis-opus-r1/eval-parse.json","w"), indent=1, sort_keys=True)
for k,v in out.items():
    print(k.split('/')[-2][-18:], k.split('/')[-1][:28], {x:v[x] for x in ['n','mean_alive','median_alive','min_alive','max_alive','mean_score','caps','alive_455_475','top_bins']})
