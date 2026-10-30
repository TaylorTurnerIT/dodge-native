"""Build figs/death_paths.html, an interactive version of Fig. 9, from the saved
4-frame argmax death traces (read-only). Keeps every death that happened while a
pattern was active (all 39 ids), including moving-rectangle deaths.

Run: /tmp/paperenv/bin/python build_interactive.py
"""
import json
from pathlib import Path

SRC = Path("/Users/taylor/.t3/worktrees/dodge-native/t3-death-telemetry-fyou-patterns/learning")
P = 65536.0
T = json.loads(Path("telemetry.json").read_text())
rows = json.loads((SRC / "runs/death-trace-ckpt420-r1/fresh2/argmax_r4.json").read_text())["rows"]

def r1(v): return round(v / P, 1)

def clean(v):
    return None if isinstance(v, float) and v != v else v

lay_sets, runs = {}, []
for r in rows:
    d = r["trace"]["death"]
    if not d or not d["active_pattern"]:
        continue
    pid = d["active_pattern"]["id"]
    rects = [[round(x["x"] / P, 1), round(x["y"] / P, 1), round(x["width"] / P, 1), round(x["height"] / P, 1), int(x["lethal"])]
             for x in d["rects"]]
    lay_sets.setdefault(pid, set()).add(tuple((a, b, c, e) for a, b, c, e, _ in rects))
    rc, n = d["recent"], len(d["recent"]["x"])
    kill = [None] * n
    for o, x, y in d["killer_path"]:
        if 1 <= o <= n:
            kill[n - o] = [r1(x), r1(y)]
    k = d["killer"]
    runs.append({
        "seed": r["seed"], "pid": pid, "cause": "rect" if "pattern_rect" in r["death_cause"] else "enemy",
        "kind": r["death_cause"], "frames": r["alive_frames"],
        "since": d["active_pattern"]["frames_since_start"],
        "killer": None if k is None else {"p": k["personality"], "size": r1(k["size"]), "age": k["age_frames"],
                                          "fyou": k["fyou_spawned"]},
        "alive": [d["enemies_alive_normal"], d["enemies_alive_kamikaze"], d["enemies_alive_explosion"]],
        "psize": r1(d["player_size_raw"]),
        "x": [r1(v) for v in rc["x"]], "y": [r1(v) for v in rc["y"]],
        "gap": [None if g < 0 else r1(g) for g in rc["enemy_gap"]],
        "n": rc["enemies"],
        "st": [0 if p != pid else (2 if lg != -1 else 1) for p, lg in zip(rc["pattern_id"], rc["lethal_rect_gap"])],
        "score": round(r["score_raw_fixed"] / P),
        "armed": any(x["lethal"] for x in d["rects"]),
        "rects": rects,
        "kp": kill, "f0": rc["frame"][0],
    })

# One fixed layout per pattern id when every game agrees; otherwise rectangles are kept per run
# (moving patterns, and ids whose layout is randomised) and drawn only at the death frame.
layouts = {}
for pid, ls in lay_sets.items():
    if len(ls) == 1:
        layouts[str(pid)] = next(q["rects"] for q in runs if q["pid"] == pid)
for q in runs:
    if str(q["pid"]) in layouts:
        del q["rects"]

pids = sorted({x["id"] for k in ("argmax_r1", "argmax_r4") for x in T[k]["patterns"]})
def stat(k, pid):
    q = next((x for x in T[k]["patterns"] if x["id"] == pid), None)
    if not q or clean(q["death"][0]) is None:
        return None
    return [int(q["enc"]), round(q["death"][0] * 100, 1)]
info = {str(p): {"r1": stat("argmax_r1", p), "r4": stat("argmax_r4", p),
                 "type": next((x["type"] for x in T["argmax_r4"]["patterns"] if x["id"] == p), "")} for p in pids}
runs.sort(key=lambda q: (q["pid"], q["frames"]))
data = {"pids": pids, "layouts": layouts, "runs": runs, "stats": info}
tpl = Path("death_paths.template.html").read_text()
Path("figs").mkdir(exist_ok=True)
Path("figs/death_paths.html").write_text(tpl.replace("/*DATA*/null", json.dumps(data, separators=(",", ":"))))
print(len(runs), len(pids), Path("figs/death_paths.html").stat().st_size)
