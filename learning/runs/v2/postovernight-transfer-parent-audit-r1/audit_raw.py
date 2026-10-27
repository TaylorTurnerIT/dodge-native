import json,hashlib,statistics as st,collections,datetime
from pathlib import Path
base=Path("learning/runs/v2/postovernight-transfer-parent-audit-r1")
r=Path("learning/runs/v2/milestone3-D2-curriculum-r1")
rows=[json.loads(l) for l in (r/"training-episodes.jsonl").read_text().splitlines()]
metrics=[json.loads(l) for l in (r/"training-metrics.jsonl").read_text().splitlines()]
pending=[];collections_by_update={};first_done=[]
for row in rows:
 if row["kind"]=="native_completed_episode":pending.append(row["info"])
 elif row["kind"]=="collection_accepted":
  collections_by_update[row["update"]]=pending
  if row["update"]==48:first_done=list(pending)
  pending=[]
done=[row["info"] for row in rows if row["kind"]=="native_completed_episode"]
complete=[e for u,es in collections_by_update.items() if u<152 for e in es]
partial=[e for u,es in collections_by_update.items() if u>=152 for e in es]
first=[e for e in first_done if e["seed"]["episode"]==0]
ev=[json.loads(l) for l in (r/"checkpoint-000010-candidate-D2-development.jsonl").read_text().splitlines()]
window=[e for e in done if 430<=e["alive_frames"]<640]
visible=lambda e:e["diagnostics"]["admitted_rectangles"]>0 or e["diagnostics"]["onscreen_warnings"]>0
counts={"stream_rows":len(rows),"kinds":dict(collections.Counter(x["kind"] for x in rows)),"metrics_complete_updates":len(metrics),"complete_optimizer_update_collection_count":sum(u<152 for u in collections_by_update),"all_accepted_collection_count":len(collections_by_update),"completed_native_episodes_total":len(done),"episodes_in_complete_update_collections":len(complete),"episodes_in_unfinished_optimizer_collection":len(partial),"all_terminated":all(e["terminated"] for e in done),"selected_430_639_time_bucket_count":len(window),"selected_bucket_terminal_pattern_visible_count":sum(visible(e) for e in window),"terminal_pattern_visible_count_all":sum(visible(e) for e in done),"argmax_entry_evaluations":len(ev),"argmax_entry_le200":sum(e["alive_frames"]<=200 for e in ev),"sampled_entry_completed_initial_episodes":len(first),"sampled_entry_completed_initial_le200":sum(e["alive_frames"]<=200 for e in first),"sampled_entry_completed_initial_mean_alive":st.mean(e["alive_frames"] for e in first),"sampled_entry_completed_initial_median_alive":st.median(e["alive_frames"] for e in first),"sampled_entry_initial_slots_without_completion_in_first_collection":sorted(set(range(64))-{e["seed"]["slot"] for e in first}),"sampled_entry_right_censored_initial_episodes":64-len(first),"sampled_entry_seed_overlap_with_D_eval":len({e["seed"]["actual_seed"] for e in first}&{e["seed"] for e in ev})}
assert counts["metrics_complete_updates"]==104 and counts["completed_native_episodes_total"]==7915
assert len(complete)==7863 and len(partial)==52 and counts["sampled_entry_seed_overlap_with_D_eval"]==0
assert counts["argmax_entry_le200"]==42 and counts["sampled_entry_completed_initial_le200"]==1
out={"observed_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"scope":"plain Python retained JSONL parsing and source review; no Torch, model inference, gameplay, tests or source mutation","counts":counts,"input_sha256":{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (r/"training-episodes.jsonl",r/"training-metrics.jsonl",r/"checkpoint-000010-candidate-D2-development.jsonl")}}
(base/"raw-checks.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
print(json.dumps(counts,indent=2,sort_keys=True))
