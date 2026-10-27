"""Read-only parse of retained D2 (and D1) training-episodes.jsonl / training-metrics.jsonl."""
import json, statistics as st, collections, sys, math
root, run = sys.argv[1], sys.argv[2]
base = f"{root}/learning/runs/v2/{run}"
rows = [json.loads(l) for l in open(f"{base}/training-episodes.jsonl")]
metrics = [json.loads(l) for l in open(f"{base}/training-metrics.jsonl")]
# Assign completed episodes to the update whose collection_accepted follows them.
per_update = collections.defaultdict(list); pending=[]; boundaries=[]; acc=[]
abandoned=[]
for r in rows:
    k=r['kind']
    if k=='native_completed_episode': pending.append(r['info'])
    elif k=='collection_accepted':
        per_update[r['update']] = pending; pending=[]; acc.append(r)
    elif k=='checkpoint_resume_boundary':
        ab=r.get('abandoned_on_resume',[])
        boundaries.append(dict(n=len(ab), frames=[a['gameplay_frames'] for a in ab], keys=sorted(r.keys())))
    elif k=='abandoned_on_fresh_env_resume': abandoned.append(r)
unassigned=len(pending)
ups=sorted(per_update)
def summ(eps):
    a=[e['alive_frames'] for e in eps]; s=[e['score'] for e in eps]
    if not a: return None
    return dict(n=len(a), mean_alive=st.mean(a), median_alive=st.median(a), mean_score=st.mean(s),
                frac_le_200=sum(x<=200 for x in a)/len(a), frac_455_475=sum(455<=x<=475 for x in a)/len(a),
                truncated=sum(e['truncated'] for e in eps), unknown_enemy=sum(e['diagnostics']['unknown_enemy_samples'] for e in eps),
                dropped=sum(e['diagnostics']['dropped_enemies'] for e in eps), inverted=sum(e['diagnostics']['inverted_boxes'] for e in eps))
# blocks of 8 updates
blocks=[]
for i in range(0,len(ups),8):
    eps=[e for u in ups[i:i+8] for e in per_update[u]]
    s=summ(eps); s['updates']=[ups[i],ups[min(i+7,len(ups)-1)]]; blocks.append(s)
allep=[e for u in ups for e in per_update[u]]
alive=[e['alive_frames'] for e in allep]
hist=collections.Counter((a//25)*25 for a in alive)
# metrics series
ms=[dict(update=m['counters']['updates'], phase=m['counters'].get('phase_updates'), **{k:m['metrics'].get(k) for k in
     ['entropy','explained_variance','approx_kl','clip_fraction','value_loss','policy_loss','early_stop_kl','epochs_completed','grad_norm']}) for m in metrics]
# action counts, if logged
out=dict(run=run, kinds=collections.Counter(r['kind'] for r in rows), n_updates_with_episodes=len(ups), first_update=ups[0] if ups else None,
  last_update=ups[-1] if ups else None, unassigned_completed_after_last_accept=unassigned,
  total_completed_assigned=len(allep), checkpoint_resume_boundaries=boundaries, abandoned_rows=len(abandoned),
  abandoned_frames_summary=dict(n=len(abandoned), mean=st.mean([a['gameplay_frames'] for a in abandoned]) if abandoned else None),
  blocks_of_8_updates=blocks, overall=summ(allep), alive_hist_top=hist.most_common(12),
  collection_accepted_sample=acc[:2], metrics_first=ms[:3], metrics_last=ms[-3:],
  metric_blocks=[{k:(st.mean([x[k] for x in ms[i:i+8] if isinstance(x[k],(int,float))]) if k not in ('update','phase') else ms[i][k]) for k in ['update','entropy','explained_variance','approx_kl','clip_fraction','value_loss']} for i in range(0,len(ms),8)],
  early_stop_count=sum(1 for x in ms if x['early_stop_kl']), metric_keys=sorted(metrics[0]['metrics'].keys()))
json.dump(out, open(f"{root}/learning/runs/v2/postovernight-transfer-diagnosis-opus-r1/training-parse-{run}.json","w"), indent=1, default=str)
print(json.dumps({k:v for k,v in out.items() if k not in ('checkpoint_resume_boundaries',)}, indent=0, default=str)[:7000])
print('boundaries', [(b['n'], round(st.mean(b['frames']),1) if b['frames'] else None, max(b['frames']) if b['frames'] else None) for b in boundaries])
