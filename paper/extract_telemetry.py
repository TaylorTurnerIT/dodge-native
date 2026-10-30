"""Condense the death-telemetry report (DODGE-014, branch t3/death-telemetry-fyou-patterns)
into paper/telemetry.json. Read-only on the source worktree. Run once; make_figures.py
reads only telemetry.json."""
import json, math, sys
from pathlib import Path
import numpy as np

SRC = Path("/Users/taylor/.t3/worktrees/dodge-native/t3-death-telemetry-fyou-patterns/learning")
REP = SRC / "reports/death-telemetry-fyou-patterns-20261029"
P = 65536.0
tabs = json.loads((REP / "tables-fresh.json").read_text())
out = {"phases": ["0-1k", "1k-2k", "2k-3k", "3k-5k", "5k+"]}

def est(d): return [d["est"], d["lo"], d["hi"]]

for name in ("argmax_r1", "argmax_r4"):
    t = tabs["settings"][name]["tables"]
    out[name] = {
        "hazard": {r["phase"]: est(r["hazard"]) for r in t["phase_overview"]},
        "pattern_rate": {r["phase"]: {"active": est(r["per_10k_active"]), "inactive": est(r["per_10k_inactive"]),
                                      "death_share_active": None}
                         for r in t["hazard_by_pattern_state"]},
        "patterns": [{"id": r["id"], "type": r["pattern_type"], "family": r["family"],
                      "enc": r["by_start_phase"]["all"]["encounters"],
                      "death": est(r["by_start_phase"]["all"]["death_per_encounter"]),
                      "rect": est(r["by_start_phase"]["all"]["rect_death_per_encounter"])}
                     for r in t["encounter_rates_by_pattern_id"]],
    }
    for r in t["pattern_at_death"]:
        out[name]["pattern_rate"][r["phase"]]["death_share_active"] = est(r["pattern_active"])
    out[name]["fyou_any"] = {r["phase"]: est(r["fy_any"]) for r in t["fyou_in_deaths"]}

# second-pass (4-frame argmax) approach and path data
rows = json.loads((SRC / "runs/death-trace-ckpt420-r1/fresh2/argmax_r4.json").read_text())["rows"]
NMAX = 60
gaps, pv, ev = [], [], []
for r in rows:
    if r["death_cause"] not in ("normal_enemy", "kamikaze_enemy"):
        continue
    d = r["trace"]["death"]; rc = d["recent"]
    kp = {a: (x / P, y / P) for a, x, y in d["killer_path"]}
    n = len(rc["x"])
    g = np.full(NMAX, np.nan); v1 = g.copy(); v2 = g.copy()
    for o in range(1, NMAX):
        if o >= n or o not in kp or (o + 1) not in kp:
            continue
        i = n - o
        dx, dy = kp[o][0] - rc["x"][i] / P, kp[o][1] - rc["y"][i] / P
        dd = math.hypot(dx, dy)
        if dd < 1e-6:
            continue
        ux, uy = dx / dd, dy / dd
        g[o] = dd
        v1[o] = rc["vx"][i] / P * ux + rc["vy"][i] / P * uy
        v2[o] = -((kp[o][0] - kp[o + 1][0]) * ux + (kp[o][1] - kp[o + 1][1]) * uy)
    gaps.append(g); pv.append(v1); ev.append(v2)
gaps, pv, ev = map(np.array, (gaps, pv, ev))
def r4(a): return [None if not np.isfinite(x) else round(float(x), 3) for x in a]
out["approach"] = {
    "n": int(len(gaps)),
    "gap_med": r4(np.nanmedian(gaps, 0)), "gap_q1": r4(np.nanpercentile(gaps, 25, 0)),
    "gap_q3": r4(np.nanpercentile(gaps, 75, 0)),
    "player_toward": r4(np.nanmedian(pv, 0)), "killer_toward": r4(np.nanmedian(ev, 0)),
}
paths = {}
for pid in (3, 4, 28, 39):
    sel = [r for r in rows if r["trace"]["death"] and r["trace"]["death"]["active_pattern"]
           and r["trace"]["death"]["active_pattern"]["id"] == pid
           and r["death_cause"] != "moving_pattern_rect"
           and r["trace"]["death"]["rects"] and all(x["lethal"] for x in r["trace"]["death"]["rects"])]
    ex = sel[0]["trace"]["death"]["rects"] if sel else []
    paths[str(pid)] = {
        "n": len(sel),
        "rects": [[x["x"] / P, x["y"] / P, x["width"] / P, x["height"] / P] for x in ex if x["lethal"]],
        "paths": [{"cause": "rect" if r["death_cause"] == "static_pattern_rect" else "enemy",
                   "xy": [[round(a / P, 2), round(b / P, 2)] for a, b in
                          zip(r["trace"]["death"]["recent"]["x"][-60:], r["trace"]["death"]["recent"]["y"][-60:])]}
                  for r in sel[:45]],
    }
out["paths"] = paths
Path("telemetry.json").write_text(json.dumps(out))
print({k: (len(v) if hasattr(v, "__len__") else v) for k, v in out.items()}, out["approach"]["n"], {k: v["n"] for k, v in paths.items()})
