"""Predict the arrival-time field by rolling the learned enemy physics forward, and score it
against the engine's exact field. The exact field is used only as the test here.

For every cell, a player who stands still there is hit on the first frame that some enemy's
box overlaps the player's box. The enemy motion comes from `physics.Physics` (learned from
trajectories). The overlap test is the game's visible hit rule.

    uv run --with torch --with numpy python hnn/arrival_hnn.py --val hnn/data/physics_val.ndjson
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

import physics

HORIZON = 36
FIELD = 20
CELL = 128.0 / FIELD
MAX_E = 16


def load_frames(path: Path, limit: int, stride: int):
    frames = []
    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            if "ph" in row and "h" in row and row["ph"]:
                frames.append(row)
    return frames[:: max(1, stride)][:limit]


def stack(frames):
    count = len(frames)
    enemies = np.zeros((count, MAX_E, 7), dtype=np.float32)
    valid = np.zeros((count, MAX_E), dtype=bool)
    for index, row in enumerate(frames):
        ph = np.array(row["ph"], dtype=np.float32)[:MAX_E]
        enemies[index, : len(ph)] = ph
        valid[index, : len(ph)] = ph[:, 5] >= 0  # blast enemies are not simulated (as in the exact field)
    player = np.array([row["p"] for row in frames], dtype=np.float32)
    exact = (255.0 - np.array([row["h"]["a"] for row in frames], dtype=np.float32)) / 255.0
    return torch.tensor(enemies), torch.tensor(valid), torch.tensor(player), 1.0 - torch.tensor(exact)  # exact: arrival / horizon


def arrival_field(model, enemies, valid, player, use_force: bool = True) -> torch.Tensor:
    """Arrival frame (1..HORIZON) per frame and cell, from learned rollouts. [F, C]"""
    count = enemies.shape[0]
    cells = physics_cells()  # [C, 2]
    n_cells = cells.shape[0]
    q = enemies[:, None, :, 0:2].expand(count, n_cells, MAX_E, 2).reshape(-1, 2).clone()
    p = enemies[:, None, :, 2:4].expand(count, n_cells, MAX_E, 2).reshape(-1, 2).clone()
    size = enemies[:, None, :, 4].expand(count, n_cells, MAX_E).reshape(-1)
    rate = enemies[:, None, :, 6].expand(count, n_cells, MAX_E).reshape(-1)
    kind = torch.tensor(
        [[physics.kind_slot(v) for v in row] for row in enemies[:, :, 5].tolist()]
    )[:, None, :].expand(count, n_cells, MAX_E).reshape(-1)
    mask = valid[:, None, :].expand(count, n_cells, MAX_E).reshape(count, n_cells, MAX_E)
    target = cells[None, :, None, :].expand(count, n_cells, MAX_E, 2).reshape(-1, 2)
    psize = player[:, None, None, 4].expand(count, n_cells, MAX_E).reshape(-1)

    arrival = torch.full((count, n_cells), float(HORIZON))
    for frame in range(HORIZON):
        hit = (
            (target[:, 0] + psize - 1.0 > q[:, 0])
            & (target[:, 1] + psize - 1.0 > q[:, 1])
            & (target[:, 0] - psize + 1.0 < q[:, 0] + size)
            & (target[:, 1] - psize + 1.0 < q[:, 1] + size)
        ).reshape(count, n_cells, MAX_E)
        any_hit = (hit & mask).any(dim=2)
        arrival = torch.where(any_hit & (arrival == HORIZON), torch.tensor(float(frame + 1)), arrival)
        if use_force:
            with torch.enable_grad():
                p_next = p + model.force(q - target, kind).detach() - model.gamma.detach() * p
        else:
            p_next = p * physics.TRUE_FRICTION
        p = p_next
        q = q + rate[:, None] * p
    return arrival


def physics_cells() -> torch.Tensor:
    axis = (torch.arange(FIELD) + 0.5) * CELL
    gy, gx = torch.meshgrid(axis, axis, indexing="ij")
    return torch.stack([gx.reshape(-1), gy.reshape(-1)], dim=1)  # row-major: row = y, column = x


def score(name: str, predicted: torch.Tensor, exact: torch.Tensor) -> None:
    frames_p, frames_e = predicted, exact * HORIZON
    corr = torch.corrcoef(torch.stack([frames_p.flatten(), frames_e.flatten()]))[0, 1].item()
    mae = (frames_p - frames_e).abs().mean().item()
    hit_any = (frames_e < HORIZON - 0.5) | (frames_p < HORIZON - 0.5)
    mae_hit = (frames_p - frames_e).abs()[hit_any].mean().item()
    line = f"{name:28} corr {corr:.3f}  MAE all {mae:5.2f}  MAE on cells with a hit {mae_hit:5.2f} frames"
    for limit in (12, 24):
        truth, guess = frames_e <= limit, frames_p <= limit
        tp = (truth & guess).sum().item()
        precision = tp / max(guess.sum().item(), 1)
        recall = tp / max(truth.sum().item(), 1)
        line += f" | hit<={limit}: P {precision:.2f} R {recall:.2f}"
    print(line)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--val", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=Path(__file__).parent / "physics.pt")
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--stride", type=int, default=7)
    args = parser.parse_args()

    model = physics.Physics()
    model.load_state_dict(torch.load(args.model))
    frames = load_frames(args.val, args.frames, args.stride)
    enemies, valid, player, exact = stack(frames)
    print(f"{len(frames)} frames, {physics_cells().shape[0]} cells each, horizon {HORIZON}")
    started = time.time()
    learned = arrival_field(model, enemies, valid, player, use_force=True)
    print(f"learned rollouts took {time.time() - started:.0f}s")
    coast = arrival_field(model, enemies, valid, player, use_force=False)
    score("learned Hamiltonian rollout", learned, exact)
    score("coasting (no force)", coast, exact)
    # Frames where something is actually coming: exact field has a hit inside the horizon.
    busy = (exact * HORIZON < HORIZON - 0.5).flatten(1).any(dim=1)
    print(f"{int(busy.sum())} of {len(frames)} frames have a predicted hit somewhere")
    score("learned (busy frames only)", learned[busy], exact[busy])
    score("coasting (busy frames only)", coast[busy], exact[busy])


if __name__ == "__main__":
    main()
