"""Learn the enemy event layer from labelled trajectories: when two enemies collide, and how an
explosion grows. No engine code is read. The labels are what the game shows on the next frame
(an enemy flagged as dying), and the explosion law is measured from observed explosion sizes.

    uv run --with torch --with numpy python hnn/events.py --train hnn/data/events_train.ndjson \
        --physics hnn/physics.json --out hnn/physics_events.json
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn

NEAR = 14.0  # only pairs whose centres are this close (px) can collide


def kind(personality: float) -> int:
    return 1 if int(personality) == 1 else 0


def pair_features(a, b) -> list[float]:
    """Features of an enemy pair at frame t. a, b = [x, y, vx, vy, size, personality, rate]."""
    f = []
    for step in (0.0, 1.0):  # now, and one frame ahead at constant velocity
        ax, ay = a[0] + a[2] * a[6] * step, a[1] + a[3] * a[6] * step
        bx, by = b[0] + b[2] * b[6] * step, b[1] + b[3] * b[6] * step
        ox = min(ax + a[4], bx + b[4]) - max(ax, bx)   # overlap along x (negative = gap)
        oy = min(ay + a[4], by + b[4]) - max(ay, by)
        f += [ox / 4.0, oy / 4.0, min(ox, oy) / 4.0]
    f += [a[4] / 4.0, b[4] / 4.0, float(kind(a[5])), float(kind(b[5]))]
    return f


def build(path: Path):
    games = collections.defaultdict(list)
    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            if "ph" in row and "dy" in row:
                games[row["s"]].append(row)
    features, labels = [], []
    for frames in games.values():
        for k in range(len(frames) - 1):
            now, nxt = frames[k], frames[k + 1]
            if nxt["f"] != now["f"] + 1:
                continue
            old = [e for e in now["ph"]]
            new = nxt["ph"]
            new_dy = nxt["dy"]
            # match each enemy to itself on the next frame
            matched = {}
            for i, e in enumerate(old):
                if e[5] < 0:
                    continue
                guess = (e[0] + e[2] * e[6], e[1] + e[3] * e[6])
                best, best_d = None, 3.0
                for j, n in enumerate(new):
                    if n[5] != e[5]:
                        continue
                    d = max(abs(n[0] - guess[0]), abs(n[1] - guess[1]))
                    if d < best_d:
                        best, best_d = j, d
                if best is not None:
                    matched[i] = best
            for i in range(len(old)):
                for j in range(i + 1, len(old)):
                    a, b = old[i], old[j]
                    if a[5] < 0 or b[5] < 0:
                        continue
                    if not (1 <= a[0] <= 128 and 1 <= b[0] <= 128):  # both have entered the arena
                        continue
                    if np.hypot(a[0] - b[0], a[1] - b[1]) > NEAR:
                        continue
                    if i not in matched or j not in matched:
                        continue  # one vanished without a flag: unknown cause, skip
                    features.append(pair_features(a, b))
                    labels.append(1.0 if (new_dy[matched[i]] or new_dy[matched[j]]) else 0.0)
    return torch.tensor(features, dtype=torch.float32), torch.tensor(labels, dtype=torch.float32)


def blast_law(path: Path) -> dict[str, float]:
    """Measure explosion growth from observed sizes (a centre-fixed box)."""
    games = collections.defaultdict(list)
    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            if "ph" in row:
                games[row["s"]].append(row)
    starts, steps, peaks = [], [], []
    for frames in games.values():
        live: dict[tuple, list[float]] = {}
        for row in frames:
            seen = set()
            for e in row["ph"]:
                if e[5] != -1:
                    continue
                centre = (round(e[0] + e[4] / 2, 1), round(e[1] + e[4] / 2, 1))
                seen.add(centre)
                live.setdefault(centre, []).append(e[4])
            for centre in [c for c in live if c not in seen]:
                series = live.pop(centre)
                if len(series) > 10:
                    starts.append(series[0])
                    steps += [series[i + 1] - series[i] for i in range(len(series) - 1)]
                    peaks.append(max(series))
    up = [s for s in steps if s > 0]
    return {
        "start": float(np.median(starts)),
        "rate": float(np.median(up)),
        "peak": float(np.median(peaks)),
    }


def rect_law(path: Path) -> dict[str, float]:
    """Measure how a static pattern rectangle's warning progress rises and when it turns lethal."""
    games = collections.defaultdict(list)
    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            if "rs" in row and row.get("r"):
                games[row["s"]].append(row)
    steps, lethal_progress = [], []
    for frames in games.values():
        for a, b in zip(frames, frames[1:]):
            if b["f"] != a["f"] + 1 or len(a["rs"]) != len(b["rs"]):
                continue
            for ra, rb, box in zip(a["rs"], b["rs"], a["r"]):
                if ra[1] != 0:  # static patterns only
                    continue
                if 0.0 < ra[0] < 1.98 and rb[0] > ra[0]:
                    steps.append(rb[0] - ra[0])
                if box[4] > 0.5:
                    lethal_progress.append(ra[0])
    return {
        "sh_step": float(np.median(steps)),
        "lethal_at": float(np.median(lethal_progress)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--physics", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--patterns-data", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=60)
    args = parser.parse_args()
    torch.manual_seed(0)

    x, y = build(args.train)
    print(f"{len(y)} close inside pairs, {y.mean():.3f} collide next frame")
    split = int(0.8 * len(y))
    order = torch.randperm(len(y))
    tr, va = order[:split], order[split:]
    net = nn.Sequential(nn.Linear(x.shape[1], 32), nn.Tanh(), nn.Linear(32, 32), nn.Tanh(), nn.Linear(32, 1))
    opt = torch.optim.Adam(net.parameters(), 3e-3)
    for epoch in range(args.epochs):
        perm = tr[torch.randperm(len(tr))]
        for s in range(0, len(perm), 512):
            idx = perm[s : s + 512]
            loss = nn.functional.binary_cross_entropy_with_logits(net(x[idx]).squeeze(1), y[idx])
            opt.zero_grad()
            loss.backward()
            opt.step()
    with torch.no_grad():
        p = torch.sigmoid(net(x[va]).squeeze(1))
        pred = p > 0.5
        truth = y[va] > 0.5
        tp = (pred & truth).sum().item()
        print(
            f"held-out pairs {len(va)}: accuracy {(pred == truth).float().mean():.3f}  "
            f"precision {tp / max(pred.sum().item(), 1):.3f}  recall {tp / max(truth.sum().item(), 1):.3f}  "
            f"(base rate {truth.float().mean():.3f})"
        )
    blast = blast_law(args.train)
    print("explosion law measured from data:", blast)

    spec = json.loads(args.physics.read_text())
    layers = [m for m in net if isinstance(m, nn.Linear)]
    spec["collision"] = {
        "near": NEAR,
        "layers": [
            {"weights": l.weight.detach().double().tolist(), "bias": l.bias.detach().double().tolist()}
            for l in layers
        ],
    }
    spec["blast"] = blast
    if args.patterns_data:
        spec["rect"] = rect_law(args.patterns_data)
        print("pattern-rectangle law measured from data:", spec["rect"])
    args.out.write_text(json.dumps(spec))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
