"""Read-only: localize deaths by alive-frame window and terminal-observation pattern context.
Terminal diagnostics admitted_rectangles/onscreen_warnings are per-observation values at the
final (pre-reset) observation; they show pattern presence at death, not the death cause."""
import json, sys, statistics as st, collections
root = sys.argv[1]
out = {}
FIRST_PATTERN = (430, 640)   # INITIAL_PATTERN_DELAY_FRAMES=420 (game.rs:25) + charge/lethal window
def windows(alive):
    n=len(alive)
    return dict(n=n, le_200=sum(a<=200 for a in alive)/n, w_201_429=sum(201<=a<430 for a in alive)/n,
                first_pattern_430_639=sum(430<=a<640 for a in alive)/n, w_640_1199=sum(640<=a<1200 for a in alive)/n,
                ge_1200=sum(a>=1200 for a in alive)/n)
for run in ["milestone3-D1-curriculum-r1", "milestone3-D2-curriculum-r1"]:
    eps=[json.loads(l) for l in open(f"{root}/learning/runs/v2/{run}/training-episodes.jsonl")]
    done=[e['info'] for e in eps if e['kind']=='native_completed_episode']
    term=[d for d in done if d['terminated']]
    alive=[d['alive_frames'] for d in term]
    pat=[d for d in term if d['diagnostics']['admitted_rectangles']>0 or d['diagnostics']['onscreen_warnings']>0]
    halves=[term[:len(term)//2], term[len(term)//2:]]
    res=dict(completed=len(done), terminated=len(term), truncated=len(done)-len(term), windows=windows(alive),
             terminal_pattern_visible_frac=len(pat)/len(term),
             terminal_pattern_visible_frac_by_half=[sum(1 for d in h if d['diagnostics']['admitted_rectangles']>0 or d['diagnostics']['onscreen_warnings']>0)/len(h) for h in halves],
             windows_by_half=[windows([d['alive_frames'] for d in h]) for h in halves],
             mean_terminal_admitted_enemies=st.mean(d['diagnostics']['admitted_enemies'] for d in term),
             mean_terminal_admitted_enemies_pattern_visible=(st.mean(d['diagnostics']['admitted_enemies'] for d in pat) if pat else None),
             max_admitted_enemies=max(d['diagnostics']['admitted_enemies'] for d in done),
             max_admitted_rectangles=max(d['diagnostics']['admitted_rectangles'] for d in done),
             unknown_phase_total=sum(d['diagnostics']['unknown_phase_samples'] for d in done),
             unknown_rect_total=sum(d['diagnostics']['unknown_rectangle_samples'] for d in done),
             unknown_enemy_total=sum(d['diagnostics']['unknown_enemy_samples'] for d in done),
             raw_history_total=sum(d['diagnostics']['raw_history_samples'] for d in done),
             score_zero_frac=sum(d['score']==0 for d in term)/len(term))
    # pattern-visible-at-death fraction by alive window
    byw=collections.defaultdict(lambda:[0,0])
    for d in term:
        a=d['alive_frames']; w='le200' if a<=200 else '201_429' if a<430 else '430_639' if a<640 else '640_1199' if a<1200 else 'ge1200'
        byw[w][0]+=1; byw[w][1]+= (d['diagnostics']['admitted_rectangles']>0 or d['diagnostics']['onscreen_warnings']>0)
    res['pattern_visible_at_death_by_window']={k:dict(n=v[0], frac=v[1]/v[0]) for k,v in sorted(byw.items())}
    out[run]=res
ev=json.load(open(f"{root}/learning/runs/v2/postovernight-transfer-diagnosis-opus-r1/eval-parse.json"))
dev={}
keys=sorted(k for k in ev if 'D2-curriculum' in k)
for k in keys:
    a=list(ev[k]['alive_by_seed'].values()); s=list(ev[k]['score_by_seed'].values())
    dev[k.split('/')[-1][:28]]=dict(windows=windows(a), sd_alive=st.pstdev(a), se_mean_alive=st.pstdev(a)/8, sd_score=st.pstdev(s), se_mean_score=st.pstdev(s)/8,
        score_zero=sum(x==0 for x in s))
# paired per-seed stability across D2 evals
seeds=sorted(ev[keys[0]]['alive_by_seed'])
mat=[[ev[k]['alive_by_seed'][sd] for k in keys] for sd in seeds]
def corr(x,y):
    mx,my=st.mean(x),st.mean(y); sx=sum((a-mx)**2 for a in x)**.5; sy=sum((b-my)**2 for b in y)**.5
    return sum((a-mx)*(b-my) for a,b in zip(x,y))/(sx*sy) if sx and sy else None
consec=[corr([m[i] for m in mat],[m[i+1] for m in mat]) for i in range(len(keys)-1)]
always_short=[sd for sd,m in zip(seeds,mat) if all(v<700 for v in m[1:])]
first_pattern_count=[sum(1 for m in mat if 430<=m[i]<640) for i in range(len(keys))]
fp_persist=collections.Counter(sum(1 for v in m[1:] if 430<=v<640) for m in mat)
improve=[sum(1 for m in mat if m[-1]>m[i]) for i in range(len(keys)-1)]
out['D2_development']=dict(per_checkpoint=dev, consecutive_per_seed_alive_pearson=consec,
    seeds_below_700_all_post_entry_evals=len(always_short), first_pattern_window_count_per_eval=first_pattern_count,
    histogram_of_post_entry_evals_in_first_pattern_window_per_seed=dict(sorted(fp_persist.items())),
    final_vs_earlier_seed_improvements=improve, entry_le200=sum(1 for m in mat if m[0]<=200))
json.dump(out, open(f"{root}/learning/runs/v2/postovernight-transfer-diagnosis-opus-r1/death-parse.json","w"), indent=1)
print(json.dumps(out, indent=1)[:9000])
