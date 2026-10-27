import json, hashlib, os, sys
from pathlib import Path
root = Path(sys.argv[1]); out = Path(sys.argv[2])
run = root / "D2-training-v3-20261025-r1"
obs = root / "D2-training-v3-execution-observer-20261025-r1"
res = {}
def J(p): return json.loads(Path(p).read_text())
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""): h.update(c)
    return h.hexdigest()
er = J(run/"execution-result.json"); wr = J(run/"worker-result.json")
ep = [json.loads(l) for l in (run/"training-episodes.jsonl").read_text().splitlines()]
met = [json.loads(l) for l in (run/"training-metrics.jsonl").read_text().splitlines()]
# 1 next = current+1, 64 slots
cur = {int(k): v for k, v in er["evidence_checks"]["episode_journal"]["current_episode_indices"].items()}
nxt = er["evidence_checks"]["episode_journal"]["next_episode_indices"]
res["next_eq_current_plus_1"] = all(nxt[s] == cur[s] + 1 for s in range(64))
res["worker_next_eq_journal"] = wr["final_resume_next_episode_indices"] == nxt
# 2 journal kinds and completed frames
kinds = {}
for r in ep: kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
res["journal_kinds"] = kinds
completed_frames = sum(r["info"]["gameplay_frames"] for r in ep if r["kind"] == "completed")
ck = J(run/"checkpoint-000072-candidate.pt.json")
res["sidecar_keys"] = sorted(ck)
# 3 metrics: per-update steps and counters
steps = [m["metrics"]["optimizer_steps"] for m in met]
res["steps_min_max_sum"] = [min(steps), max(steps), sum(steps)]
res["steps_gt_128"] = sum(1 for s in steps if s > 128)
res["update_count"] = len(met)
res["transitions_all_16384"] = all(m["metrics"]["transitions"] == 16384 for m in met)
res["last_counters"] = met[-1]["counters"]
res["worker_counters"] = wr["counters"]
# 4 eval quartiles & death attribution
for u in (0, 72):
    d = J(run/f"development-{u:06d}.json"); rows = d["evaluation"]["rows"]
    af = sorted(r["alive_frames"] for r in rows); sc = sorted(r["score"] for r in rows)
    res[f"eval{u}"] = {
        "n": len(rows), "seeds_ok": [r["seed"] for r in rows] == list(range(0xD0000000, 0xD0000040)),
        "alive_Q1": sum(af[:16]) / 16, "alive_Q4": sum(af[-16:]) / 16, "alive_mean": sum(af) / 64,
        "alive_Q2Q3_mean": sum(af[16:48]) / 32,
        "score_mean": sum(sc) / 64,
        "terminated": sum(1 for r in rows if r["terminated"]), "truncated": sum(1 for r in rows if r["truncated"]),
        "death_causes_rows": {k: sum(1 for r in rows if r.get("terminated") and r.get("death_cause") == k)
                              for k in sorted({r.get("death_cause") for r in rows if r.get("terminated")}, key=str)},
        "death_causes_summary": d["evaluation"]["death_causes"],
        "deaths_caps": [d["evaluation"]["deaths"], d["evaluation"]["caps"]],
        "competence": d["competence_passed"],
        "ev_pass": all(r["terminated"] != r["truncated"] for r in rows),
    }
# 5 raw frame conservation: abandoned + completed, per last checkpoint
ab = ck  # placeholder
state_ab = J(run/"checkpoint-000072-candidate.pt.json")
res["sidecar_has_abandoned"] = "abandoned_current_episodes" in state_ab
res["completed_frames"] = completed_frames
res["counter_raw_frames"] = wr["counters"]["raw_frames"]
res["cumulative_raw"] = wr["cumulative_counters"]["raw_frames"]
# 6 manifest hashes
man = J(run/"artifact-manifest.json")
bad = {n: h for n, h in man.items() if sha(run/n) != h}
res["manifest_mismatch"] = bad
res["manifest_count"] = len(man)
res["files_not_in_manifest"] = sorted(p.name for p in run.iterdir() if p.is_file() and p.name not in man)
# 7 observer resources maxima
def maxes(path, keys):
    m = {k: 0 for k in keys}
    for l in Path(path).read_text().splitlines():
        if not l.strip(): continue
        o = json.loads(l)
        for k in keys:
            if isinstance(o.get(k), (int, float)): m[k] = max(m[k], o[k])
    return m
res["worker_resources_max"] = maxes(run/"resources.jsonl", ["peak_rss_bytes", "mps_driver_bytes"])
res["observer_resources_keys"] = sorted(json.loads(Path(obs/"resources.jsonl").read_text().splitlines()[0]).keys())
res["observer_resources_max"] = maxes(obs/"resources.jsonl", ["aggregate_rss_bytes", "rss_bytes", "peak_rss_bytes", "mps_driver_bytes"])
# 8 timing
res["timing"] = {"launcher_elapsed": er["elapsed_seconds"], "worker_work": wr["work_elapsed_seconds"],
                 "worker_elapsed": wr["elapsed_seconds"]}
res["sha_final"] = sha(run/"checkpoint-000072-candidate.pt")
res["sha_reg"] = sha(root/"d2-training-v3-parent-prepare-20261025-r2/registration-r8.json")
json.dump(res, sys.stdout, indent=1, sort_keys=True, default=str)
