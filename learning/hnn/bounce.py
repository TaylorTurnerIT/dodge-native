"""Measure how enemies bounce off a lethal pattern rectangle, from observed frames only.
Adds `bounce_static` and `bounce_moving` (post-bounce speed on the pushed axis) to the model spec.

    uv run --with numpy python hnn/bounce.py --data hnn/data/patterns_probe.ndjson \
        --spec hnn/physics_events.json --out hnn/physics_events.json
"""
import argparse, collections, json, statistics
from pathlib import Path

FR = 64880.0 / 65536.0

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--spec", type=Path, required=True); ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    frames = collections.defaultdict(list)
    for line in a.data.open():
        try: r = json.loads(line)
        except Exception: continue
        if "rs" in r and "ph" in r and r.get("r"): frames[r["s"]].append(r)
    speeds = {"static": [], "moving": []}
    for fr in frames.values():
        for p, q in zip(fr, fr[1:]):
            if q["f"] != p["f"] + 1 or len(p["r"]) != len(q["r"]): continue
            for rect, rs in zip(p["r"], p["rs"]):
                moving = rs[1] > 0.5
                if rs[0] < 1.999 and not moving: continue
                x, y, w, h = rect[:4]
                for e in p["ph"]:
                    if e[5] < 0 or e[5] > 1: continue
                    vx, vy = e[2] * FR, e[3] * FR
                    if not (e[0] + vx < x + w and e[0] + e[4] > x and e[1] + e[4] > y and e[1] + vy < y + h): continue
                    g = (e[0] + e[2] * e[6], e[1] + e[3] * e[6])
                    m = [n for n in q["ph"] if n[5] == e[5] and abs(n[0] - g[0]) < 6 and abs(n[1] - g[1]) < 6]
                    if not m: continue
                    n = m[0]
                    if max(abs(n[2] - vx), abs(n[3] - vy)) > 0.05:
                        speeds["moving" if moving else "static"].append(max(abs(n[2]), abs(n[3])))
    out = {}
    for k, v in speeds.items():
        out[k] = statistics.median(v) if v else 1.0
        print(f"{k}: {len(v)} bounces, post-bounce speed median {out[k]:.3f}, 10th-90th percentile "
              f"{sorted(v)[int(len(v)*.1)]:.2f}-{sorted(v)[int(len(v)*.9)]:.2f}" if v else f"{k}: none")
    spec = json.loads(a.spec.read_text())
    spec["rect"]["bounce_static"] = out["static"]; spec["rect"]["bounce_moving"] = out["moving"]
    a.out.write_text(json.dumps(spec)); print("wrote", a.out)

main()
