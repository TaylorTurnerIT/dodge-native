"""Fit post-bounce enemy speed against game speed, per difficulty, from `bounce_probe` output.

The probe prints one line per observed axis bounce: difficulty frame moving axis speed other speed_of_game.
The curve is the median bounce speed in bins of game speed, with gaps filled by interpolation.

    python3 hnn/bounce_curve.py --spec hnn/physics_events.json --out hnn/physics_events.json hnn/data/bounce2_d?.txt
"""
import argparse, json
from pathlib import Path

BIN = 0.125


def curve(points):
    bins = {}
    for speed, value in points:
        bins.setdefault(int(speed / BIN), []).append(value)
    return [[round((k + 0.5) * BIN, 4), sorted(v)[len(v) // 2]] for k, v in sorted(bins.items()) if len(v) >= 5]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    rows = {}
    for path in a.files:
        for line in path.open():
            t = line.split()
            if len(t) != 7:
                continue
            key = (t[0], "moving" if t[2] == "1" else "static")
            rows.setdefault(key, []).append((float(t[6]), float(t[4])))
    spec = json.loads(a.spec.read_text())
    spec["bounce_curve"] = {}
    for difficulty in sorted({k[0] for k in rows}):
        entry = {}
        for kind in ("static", "moving"):
            entry[kind] = curve(rows.get((difficulty, kind), []))
            print(f"D{difficulty} {kind}: {len(rows.get((difficulty, kind), []))} bounces,",
                  " ".join(f"{s:.2f}:{v:.2f}" for s, v in entry[kind]))
        spec["bounce_curve"][difficulty] = entry
    a.out.write_text(json.dumps(spec))
    print("wrote", a.out)


main()
