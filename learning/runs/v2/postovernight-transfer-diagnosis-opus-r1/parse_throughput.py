"""Read-only: D2 update wall time, metric trends, and linear trend of per-update training means."""
import json, sys, statistics as st
from datetime import datetime
root=sys.argv[1]; b=f"{root}/learning/runs/v2/milestone3-D2-curriculum-r1"
m=[json.loads(l) for l in open(f"{b}/training-metrics.jsonl")]
t=[datetime.fromisoformat(x['at_utc']).timestamp() for x in m]
dt=[t[i+1]-t[i] for i in range(len(t)-1)]
rows=[json.loads(l) for l in open(f"{b}/training-episodes.jsonl")]
pend=[];per={}
for r in rows:
    if r['kind']=='native_completed_episode': pend.append(r['info'])
    elif r['kind']=='collection_accepted': per[r['update']]=pend; pend=[]
ups=sorted(u for u in per if u<152)  # 104 complete updates use collections 48..151
xs=[u-48 for u in ups]; ya=[st.mean(e['alive_frames'] for e in per[u]) for u in ups]; ys=[st.mean(e['score'] for e in per[u]) for u in ups]
pw=[sum(1 for e in per[u] if 430<=e['alive_frames']<640)/len(per[u]) for u in ups]
def ols(x,y):
    mx,my=st.mean(x),st.mean(y); sxx=sum((a-mx)**2 for a in x); b1=sum((a-mx)*(c-my) for a,c in zip(x,y))/sxx
    res=[c-(my+b1*(a-mx)) for a,c in zip(x,y)]; s2=sum(r*r for r in res)/(len(x)-2); return b1, (s2/sxx)**.5, my-b1*mx
half=len(ups)//2
out=dict(update_interval_seconds=dict(n=len(dt), median=st.median(dt), mean=st.mean(dt), max=max(dt), min=min(dt)),
  first_metric_utc=m[0]['at_utc'], last_metric_utc=m[-1]['at_utc'], span_seconds=t[-1]-t[0],
  alive_slope_per_update_all=ols(xs,ya), alive_slope_first_half=ols(xs[:half],ya[:half]), alive_slope_second_half=ols(xs[half:],ya[half:]),
  score_slope_per_update_all=ols(xs,ys), score_slope_second_half=ols(xs[half:],ys[half:]),
  first_pattern_window_frac_slope=ols(xs,pw), first_pattern_window_frac_first8=st.mean(pw[:8]), first_pattern_window_frac_last8=st.mean(pw[-8:]),
  episodes_per_update_first8=st.mean(len(per[u]) for u in ups[:8]), episodes_per_update_last8=st.mean(len(per[u]) for u in ups[-8:]),
  entropy_first8=st.mean(x['metrics']['entropy'] for x in m[:8]), entropy_last8=st.mean(x['metrics']['entropy'] for x in m[-8:]),
  ev_max=max(x['metrics']['explained_variance'] for x in m), ev_last8=st.mean(x['metrics']['explained_variance'] for x in m[-8:]),
  kl_first8=st.mean(x['metrics']['approx_kl'] for x in m[:8]), kl_last8=st.mean(x['metrics']['approx_kl'] for x in m[-8:]),
  clip_last8=st.mean(x['metrics']['clip_fraction'] for x in m[-8:]), early_stops=sum(x['metrics']['early_stop_kl'] for x in m),
  max_kl=max(x['metrics']['approx_kl'] for x in m))
d1=[json.loads(l) for l in open(f"{root}/learning/runs/v2/milestone3-D1-curriculum-r1/training-metrics.jsonl")]
out['D1_entropy_last']=d1[-1]['metrics']['entropy']; out['D1_ev_last']=d1[-1]['metrics']['explained_variance']
json.dump(out, open(f"{root}/learning/runs/v2/postovernight-transfer-diagnosis-opus-r1/throughput-trend.json","w"), indent=1)
print(json.dumps(out, indent=0))
