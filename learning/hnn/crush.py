"""Learn when a moving pattern rectangle destroys an enemy it overlaps.

An enemy that overlaps a moving rectangle is destroyed on 3 to 4 percent of frames (a destroyed
kamikaze then explodes). The label is what the next frame shows: the enemy is flagged dying, or
it has vanished. The features are geometry and motion that a player can see.

    uv run --with torch --with numpy python hnn/crush.py --data hnn/data/patterns_big.ndjson \
        --spec hnn/physics_events.json --out hnn/physics_events.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn


def features(e, rect, before) -> list[float]:
    """e = [x, y, vx, vy, size, personality, rate]; rect and before = [x, y, w, h] now and a frame ago."""
    x, y, w, h = rect
    ox = min(e[0] + e[4], x + w) - max(e[0], x)
    oy = min(e[1] + e[4], y + h) - max(e[1], y)
    wall = min(e[0], e[1], 128.0 - e[0] - e[4], 128.0 - e[1] - e[4])
    return [
        ox / 4.0, oy / 4.0, min(ox, oy) / 4.0,
        (x - before[0]), (y - before[1]),                  # rectangle velocity (px per frame)
        (w - before[2]), (h - before[3]),                  # rectangle growth
        w / 64.0, h / 64.0,
        e[4] / 4.0, float(int(e[5]) == 1),
        e[2] * e[6], e[3] * e[6],                          # enemy velocity (px per frame)
        wall / 16.0,
    ]


def samples(path: Path):
    xs, ys = [], []
    games: dict[int, list[dict]] = {}
    current = None
    window: list[dict] = []

    def flush(frames):
        for k in range(1, len(frames) - 1):
            z, a, b = frames[k - 1], frames[k], frames[k + 1]
            if a["f"] != z["f"] + 1 or b["f"] != a["f"] + 1:
                continue
            if not a.get("r") or len(a["r"]) != len(z.get("r", [])) or len(a.get("rs", [])) != len(a["r"]):
                continue
            for i, state in enumerate(a["rs"]):
                if state[1] < 0.5:  # moving rectangles only
                    continue
                rect, before = a["r"][i][:4], z["r"][i][:4]
                for e in a["ph"]:
                    if e[5] < 0:
                        continue
                    if not (e[0] + e[4] > rect[0] and e[1] + e[4] > rect[1]
                            and e[0] < rect[0] + rect[2] and e[1] < rect[1] + rect[3]):
                        continue
                    guess = (e[0] + e[2] * e[6], e[1] + e[3] * e[6])
                    match = [d for n, d in zip(b["ph"], b["dy"])
                             if n[5] == e[5] and abs(n[0] - guess[0]) < 4 and abs(n[1] - guess[1]) < 4]
                    positive = (not match) or bool(match[0])
                    xs.append(features(e, rect, before))
                    ys.append(1.0 if positive else 0.0)

    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            if "ph" not in row or "end" in row:
                if "end" in row and window:
                    flush(window)
                    window = []
                continue
            window.append({k: row[k] for k in ("s", "f", "ph", "dy") if k in row} | {
                "r": row.get("r", []), "rs": row.get("rs", [])})
            if len(window) > 4000:
                flush(window)
                window = window[-2:]
        if window:
            flush(window)
    return torch.tensor(xs, dtype=torch.float32), torch.tensor(ys, dtype=torch.float32)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=80)
    args = parser.parse_args()
    torch.manual_seed(0)

    x, y = samples(args.data)
    print(f"{len(y)} enemy-rectangle overlaps, {y.mean():.3f} destroyed on the next frame")
    order = torch.randperm(len(y))
    cut = int(0.8 * len(y))
    tr, va = order[:cut], order[cut:]
    mean, std = x[tr].mean(0), x[tr].std(0) + 1e-6
    net = nn.Sequential(nn.Linear(x.shape[1], 32), nn.Tanh(), nn.Linear(32, 32), nn.Tanh(), nn.Linear(32, 1))
    opt = torch.optim.Adam(net.parameters(), 3e-3)
    weight = torch.tensor(1.0 / max(y[tr].mean().item(), 1e-3)).clamp(max=10.0)
    for _ in range(args.epochs):
        perm = tr[torch.randperm(len(tr))]
        for s in range(0, len(perm), 512):
            idx = perm[s : s + 512]
            logits = net((x[idx] - mean) / std).squeeze(1)
            loss = nn.functional.binary_cross_entropy_with_logits(logits, y[idx], pos_weight=weight)
            opt.zero_grad()
            loss.backward()
            opt.step()
    with torch.no_grad():
        p = torch.sigmoid(net((x[va] - mean) / std).squeeze(1))
        truth = y[va] > 0.5
        for threshold in (0.3, 0.5, 0.7):
            pred = p > threshold
            tp = (pred & truth).sum().item()
            print(f"  threshold {threshold}: precision {tp / max(pred.sum().item(), 1):.3f}  "
                  f"recall {tp / max(truth.sum().item(), 1):.3f}  (base rate {truth.float().mean():.3f}, n={len(va)})")

    spec = json.loads(args.spec.read_text())
    layers = [m for m in net if isinstance(m, nn.Linear)]
    spec["crush"] = {
        "mean": mean.double().tolist(),
        "std": std.double().tolist(),
        "layers": [
            {"weights": l.weight.detach().double().tolist(), "bias": l.bias.detach().double().tolist()}
            for l in layers
        ],
    }
    args.out.write_text(json.dumps(spec))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
