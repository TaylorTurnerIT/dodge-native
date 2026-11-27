import json, sys, collections
rows=[json.loads(l) for f in sys.argv[1:] for l in open(f)]
print(len(rows),"deaths")
def tab(key):
    c=collections.Counter(r[key] for r in rows); print(f"  by {key}:", dict(c.most_common()))
for k in ("difficulty","cause","class","worst_error_kind","blast_near","kamikaze_near"): tab(k)
print("  lost before window:", sum(r["lost_before_window"] for r in rows))
fb=sorted(r["frames_before_death"] for r in rows); print("  frames between last recoverable state and death: median",fb[len(fb)//2],"max",fb[-1])
mb=[r for r in rows if r["class"]=="model-blind"]
print("  model-blind: engine hit frame for chosen action:", collections.Counter(r["engine_hit"] for r in mb).most_common(6))
print("  enemy-pair contact (gap<1) at last recoverable state:", sum(r["enemy_pair_gap"]<1 for r in rows),"of",len(rows))
