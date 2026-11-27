"""Measure where and how often new enemies appear, from observed frames only.
A birth is an enemy on frame t+1 that no enemy on frame t explains. Adds `spawn` to the model spec:
points with a per-frame birth rate, split by whether a pattern is active.

    uv run --with numpy python hnn/spawns.py --data hnn/data/patterns_probe.ndjson \
        --spec hnn/physics_events.json --out hnn/physics_events.json
"""
import argparse, collections, json
from pathlib import Path

FR = 64880.0 / 65536.0

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--spec", type=Path, required=True); ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    games = collections.defaultdict(list)
    for line in a.data.open():
        try: r = json.loads(line)
        except Exception: continue
        if "ph" in r: games[r["s"]].append(r)
    births = []   # (x, y, rect_count)
    frames_by_count = collections.Counter()
    total_frames = 0
    for fr in games.values():
        for p, q in zip(fr, fr[1:]):
            if q["f"] != p["f"] + 1: continue
            count = len(p.get("r", []))
            frames_by_count[count] += 1; total_frames += 1
            for n in q["ph"]:
                if n[5] < 0: continue
                if any(e[5] == n[5] and abs(n[0] - (e[0] + e[2] * FR * e[6])) < 8 and abs(n[1] - (e[1] + e[3] * FR * e[6])) < 8 for e in p["ph"]):
                    continue
                births.append((n[0], n[1], count))
    cells = collections.defaultdict(list)
    for x, y, count in births:
        cells[(round(x / 16), round(y / 16))].append((x, y, count))
    points = []
    for key, items in cells.items():
        if len(items) < 8: continue
        cx = sum(i[0] for i in items) / len(items); cy = sum(i[1] for i in items) / len(items)
        per_count = collections.Counter(i[2] for i in items)
        # A point whose births all happen under one visible rectangle count is a pattern spawn point.
        top_count, top_n = per_count.most_common(1)[0]
        concentrated = top_n >= 0.9 * len(items) and top_count > 0
        rate_by_rects = {str(top_count): top_n / frames_by_count[top_count]} if concentrated else {}
        points.append({"x": cx, "y": cy,
                       "rate_default": 0.0 if concentrated else len(items) / total_frames,
                       "rate_by_rects": rate_by_rects})
    points.sort(key=lambda p: (p["x"], p["y"]))
    for p in points: print({k: (round(v, 5) if isinstance(v, float) else v) for k, v in p.items()})
    print(f"frames observed {total_frames}; births {len(births)}")
    spec = json.loads(a.spec.read_text()); spec["spawn"] = {"points": points, "radius": 10.0}
    a.out.write_text(json.dumps(spec)); print("wrote", a.out)

main()
