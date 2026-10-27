import sys, json
from pathlib import Path
run = Path(sys.argv[1])
import torch
ck = torch.load(run / "checkpoint-000072-candidate.pt", map_location="cpu", weights_only=False)
ab = ck["abandoned_current_episodes"]
print(json.dumps({"n": len(ab), "slots_ok": sorted(i["slot"] for i in ab) == list(range(64)),
                  "frames": sum(i["gameplay_frames"] for i in ab), "max_frames": max(i["gameplay_frames"] for i in ab),
                  "next": ck["next_episode_indices"][:4], "keys": sorted(ck)[:40]}))
ep = [json.loads(l) for l in (run/"training-episodes.jsonl").read_text().splitlines()]
cur = {}
for r in ep:
    if r["kind"] == "initial":
        cur = {i["seed"]["slot"]: i["seed"]["episode"] for i in r["info"]}
    if r["kind"] == "reset":
        for s, st in zip(r["info"]["indices"], r["info"]["info"]):
            cur[s] = st["seed"]["episode"]
completed = sum(1 for r in ep if r["kind"] == "completed")
print(json.dumps({"sum_current_from_resets": sum(cur.values()), "completed_rows": completed}))
