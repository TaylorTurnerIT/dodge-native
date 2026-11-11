"""Learn the enemy physics as a port-Hamiltonian system from trajectories alone.

State of one enemy: position q and velocity p (mass 1). The model is

    H(q, p) = 1/2 |p|^2 + U(q_enemy - q_player, kind)
    dq/dt   = rate * dH/dp                     (rate = game speed x freeze x enemy speed)
    dp/dt   = -dH/dq - Gamma * p               (Gamma > 0: dissipation, a learned scalar)

U is a small network and Gamma is a learned number. Nothing here sees a danger value, an
arrival time, or engine code. The only training signal is the next frame of an enemy.
Afterwards the learned force and Gamma are compared with the engine's constants
(friction 0.99, acceleration 0.01 toward the player on each axis).

    uv run --with torch --with numpy python hnn/physics.py \
        --train hnn/data/physics_train.ndjson --val hnn/data/physics_val.ndjson --out hnn/physics.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

KINDS = 5  # normal, kamikaze, (blast is excluded: it does not move), bomb, bonus -> slots below
TRUE_FRICTION = 64880.0 / 65536.0
TRUE_ACCEL = 655.0 / 65536.0


def kind_slot(personality: float) -> int:
    return {0: 0, 1: 1, 2: 2, 3: 3, 4: 3}.get(int(personality), 0)


def transitions(path: Path) -> dict[str, np.ndarray]:
    """Pair each enemy with itself on the next frame. Skips pairs it cannot match cleanly."""
    rows: list[list[float]] = []  # q(2) p(2) player(2) rate size kind | q'(2) p'(2) next_player(2) flags
    games: dict[int, list[dict]] = {}
    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            if "ph" not in row:
                continue
            games.setdefault(row["s"], []).append(row)
    dropped = matched = 0
    for frames in games.values():
        for previous, current in zip(frames, frames[1:]):
            if current["f"] != previous["f"] + 1:
                continue
            old = np.array(previous["ph"], dtype=np.float64).reshape(-1, 7)
            new = np.array(current["ph"], dtype=np.float64).reshape(-1, 7)
            if len(old) == 0 or len(new) == 0:
                continue
            taken: set[int] = set()
            for enemy in old:
                if enemy[5] < 0:  # blast enemies do not move
                    continue
                guess = enemy[0:2] + enemy[2:4] * enemy[6]
                distance = np.linalg.norm(new[:, 0:2] - guess, axis=1)
                distance[new[:, 5] != enemy[5]] = np.inf
                for used in taken:
                    distance[used] = np.inf
                best = int(np.argmin(distance))
                if not np.isfinite(distance[best]) or distance[best] > 2.0:
                    dropped += 1
                    continue
                taken.add(best)
                after = new[best]
                matched += 1
                rows.append(
                    [
                        *enemy[0:2], *enemy[2:4], previous["p"][0], previous["p"][1],
                        enemy[6], enemy[4], kind_slot(enemy[5]),
                        *after[0:2], *after[2:4], current["p"][0], current["p"][1],
                    ]
                )
    print(f"  {path.name}: {matched} enemy transitions matched, {dropped} dropped")
    return {"data": np.array(rows, dtype=np.float32)}


class Physics(nn.Module):
    def __init__(self, width: int = 64) -> None:
        super().__init__()
        self.potential = nn.Sequential(
            nn.Linear(2 + KINDS, width), nn.Tanh(), nn.Linear(width, width), nn.Tanh(), nn.Linear(width, 1)
        )
        self.raw_gamma = nn.Parameter(torch.tensor(-3.0))

    @property
    def gamma(self) -> torch.Tensor:
        return nn.functional.softplus(self.raw_gamma)

    def energy(self, offset: torch.Tensor, kind: torch.Tensor) -> torch.Tensor:
        """U(q_enemy - q_player, kind). `offset` is in pixels."""
        onehot = nn.functional.one_hot(kind, KINDS).float()
        return self.potential(torch.cat([offset / 64.0, onehot], dim=1)).squeeze(1)

    def force(self, offset: torch.Tensor, kind: torch.Tensor) -> torch.Tensor:
        """-dU/dq for the enemy (dq_enemy = d offset)."""
        offset = offset.clone().requires_grad_(True)
        (gradient,) = torch.autograd.grad(self.energy(offset, kind).sum(), offset, create_graph=True)
        return -gradient

    def step(self, q, p, player, rate, kind):
        """One frame: p' = p + dp/dt, q' = q + rate * dH/dp(p') (kinetic term is 1/2 |p|^2)."""
        p_next = p + self.force(q - player, kind) - self.gamma * p
        return q + rate[:, None] * p_next, p_next


def unpack(data: torch.Tensor):
    q, p, player = data[:, 0:2], data[:, 2:4], data[:, 4:6]
    rate, size, kind = data[:, 6], data[:, 7], data[:, 8].long()
    q_next, p_next, player_next = data[:, 9:11], data[:, 11:13], data[:, 13:15]
    return q, p, player, rate, size, kind, q_next, p_next, player_next


def clean_mask(data: torch.Tensor) -> torch.Tensor:
    """Drop transitions with a wall reflection or another jump that a smooth force cannot make."""
    q, p, player, rate, size, kind, q_next, p_next, _ = unpack(data)
    jump = (p_next - p).abs().amax(dim=1)
    return jump < 0.05


def evaluate(model: Physics, data: torch.Tensor) -> dict[str, float]:
    q, p, player, rate, size, kind, q_next, p_next, _ = unpack(data)
    clean = clean_mask(data)
    q, p, player, rate, kind, q_next, p_next = (x[clean] for x in (q, p, player, rate, kind, q_next, p_next))
    with torch.enable_grad():
        q_hat, p_hat = model.step(q, p, player, rate, kind)
    # baseline: friction only (no force) with the engine's friction, to show what the force adds
    friction_only = p * TRUE_FRICTION
    return {
        "p_rmse": ((p_hat - p_next) ** 2).mean().sqrt().item(),
        "p_rmse_no_force": ((friction_only - p_next) ** 2).mean().sqrt().item(),
        "q_rmse": ((q_hat - q_next) ** 2).mean().sqrt().item(),
        "kept": clean.float().mean().item(),
    }


def report_force(model: Physics) -> None:
    """Force the model applies along the x axis (player fixed at the origin), against +-0.01."""
    print("learned force on a normal enemy, offset (x, 0) from the player; engine: -0.0100 * sign(x)")
    for x in (-60.0, -30.0, -10.0, -3.0, -1.0, 1.0, 3.0, 10.0, 30.0, 60.0):
        offset = torch.tensor([[x, 0.0]])
        kind = torch.tensor([0])
        fx, fy = model.force(offset, kind)[0].tolist()
        print(f"  x={x:6.1f}  fx={fx:+.5f}  fy={fy:+.5f}")
    print(f"learned friction 1-Gamma = {1 - float(model.gamma):.5f}   engine: {TRUE_FRICTION:.5f}")


@torch.no_grad()
def rollout_error(model: Physics, path: Path, horizon: int = 30, limit: int = 3000) -> dict[str, float]:
    """Predict an enemy `horizon` frames ahead using the real player path, no engine."""
    games: dict[int, list[dict]] = {}
    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            if "ph" in row:
                games.setdefault(row["s"], []).append(row)
    errors_model, errors_const = [], []
    count = 0
    for frames in games.values():
        for start in range(0, len(frames) - horizon, 25):
            first, last = frames[start], frames[start + horizon]
            if last["f"] != first["f"] + horizon:
                continue
            old = np.array(first["ph"], dtype=np.float32).reshape(-1, 7)
            # track one enemy through the window: only windows with a stable enemy count
            if any(len(frames[start + k]["ph"]) != len(old) for k in range(horizon + 1)):
                continue
            q = torch.tensor(old[:, 0:2]); p = torch.tensor(old[:, 2:4])
            rate = torch.tensor(old[:, 6]); kind = torch.tensor([kind_slot(v) for v in old[:, 5]])
            move = torch.tensor(old[:, 5] >= 0)
            q0 = q.clone(); p0 = p.clone()
            for k in range(horizon):
                player = torch.tensor(frames[start + k]["p"][0:2]).expand_as(q)
                with torch.enable_grad():
                    q, p = model.step(q, p, player, rate, kind)
            truth = torch.tensor(np.array(last["ph"], dtype=np.float32).reshape(-1, 7)[:, 0:2])
            constant = q0 + p0 * rate[:, None] * sum(TRUE_FRICTION ** (k + 1) for k in range(horizon))
            # skip windows where an enemy bounced (the learned smooth force has no wall)
            if (truth - constant).abs().amax() > 40:
                continue
            errors_model.append((q - truth)[move].norm(dim=1))
            errors_const.append((constant - truth)[move].norm(dim=1))
            count += 1
            if count >= limit:
                break
    model_error = torch.cat(errors_model)
    const_error = torch.cat(errors_const)
    return {
        "windows": float(count),
        "mean_px_error_model": model_error.mean().item(),
        "mean_px_error_coast": const_error.mean().item(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--val", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch", type=int, default=2048)
    parser.add_argument("--lr", type=float, default=3e-3)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    torch.manual_seed(args.seed)

    started = time.time()
    print("matching enemies across frames")
    train = torch.tensor(transitions(args.train)["data"])
    val = torch.tensor(transitions(args.val)["data"])
    clean = clean_mask(train)
    print(f"{train.shape[0]} train transitions, {clean.float().mean():.3f} free-flight; {val.shape[0]} val ({time.time() - started:.0f}s)")
    data = train[clean]

    model = Physics()
    optimiser = torch.optim.Adam(model.parameters(), lr=args.lr)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, args.epochs)
    for epoch in range(args.epochs):
        order = torch.randperm(data.shape[0])
        total = 0.0
        for start in range(0, data.shape[0], args.batch):
            batch = data[order[start : start + args.batch]]
            q, p, player, rate, size, kind, q_next, p_next, _ = unpack(batch)
            q_hat, p_hat = model.step(q, p, player, rate, kind)
            # velocities change by ~0.01 per frame, so scale the error up before squaring
            loss = nn.functional.huber_loss(100.0 * p_hat, 100.0 * p_next, delta=1.0)
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            total += loss.item() * batch.shape[0]
        schedule.step()
        if epoch % 5 == 4 or epoch == 0:
            report = evaluate(model, val)
            print(
                f"epoch {epoch + 1:2d} loss {total / data.shape[0]:.4f}  val p-rmse {report['p_rmse']:.5f} "
                f"(friction only {report['p_rmse_no_force']:.5f})  Gamma {float(model.gamma):.5f}  ({time.time() - started:.0f}s)",
                flush=True,
            )
    report_force(model)
    print("rollout (30 frames, real player path, no engine):", rollout_error(model, args.val))
    torch.save(model.state_dict(), args.out.with_suffix(".pt"))
    print("saved", args.out.with_suffix(".pt"))


if __name__ == "__main__":
    main()
