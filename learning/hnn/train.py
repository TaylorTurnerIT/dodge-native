"""Train a learned potential V so that descending it copies the lookahead teacher.

The model sees only the observation (player, enemies, pattern rectangles). The
teacher's nine costs are used only to build labels. Feature definitions must match
`dodge-native/crates/dodge-danger/src/learned.rs`.

    uv run --with torch --with numpy python hnn/train.py \
        --train hnn/data/train.ndjson --val hnn/data/val.ndjson --out hnn/model.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

ACTIONS = ["neutral", "left", "right", "up", "down", "up_left", "up_right", "down_left", "down_right"]
ACTION_INDEX = {name: index for index, name in enumerate(ACTIONS)}
DIRECTIONS = torch.tensor(
    [[0, 0], [-1, 0], [1, 0], [0, -1], [0, 1], [-1, -1], [1, -1], [-1, 1], [1, 1]],
    dtype=torch.float32,
)
# Each axis is "move" or "hold". Holding an axis scores `axis_bias`, so a pure cardinal
# move wins when one slope component is strong and the other is below the threshold.
HELD_AXES = (DIRECTIONS == 0).float().sum(dim=1)
PATH_FRAMES = 36  # the player's own path is scored this far ahead,
PATH_STEP = 4  # every PATH_STEP frames (matches learned.rs)
MOVE_PENALTY = 0.0005
MAX_ENEMIES = 24
MAX_RECTS = 16
FIELD = 20  # coarse arrival-field grid is FIELD x FIELD over the 128 px playfield
CELL = 128.0 / FIELD


# -- data -----------------------------------------------------------------


def kind_slot(personality: float) -> int:
    value = int(personality)
    return {1: 1, -1: 2, 2: 3, 3: 4, 4: 4}.get(value, 0)


def load(paths: list[Path], limit: int | None = None) -> dict[str, torch.Tensor]:
    """Read one or more NDJSON training sets into padded tensors."""
    players, enemies, rects, labels, costs, games = [], [], [], [], [], []
    fields, has_field = [], []
    for path in paths:
        with path.open() as handle:
            for line in handle:
                row = json.loads(line)
                if "end" in row:
                    continue
                players.append(row["p"])
                enemies.append(row["e"][:MAX_ENEMIES])
                rects.append(row.get("r", [])[:MAX_RECTS])
                labels.append(ACTION_INDEX[row["a"]])
                costs.append(row["c"])
                games.append(row["s"])
                heat = row.get("h")
                has_field.append(heat is not None)
                fields.append(heat["a"] if heat is not None else [0] * (FIELD * FIELD))
                if limit and len(players) >= limit:
                    break
    count = len(players)
    enemy_array = np.zeros((count, MAX_ENEMIES, 6), dtype=np.float32)
    enemy_mask = np.zeros((count, MAX_ENEMIES), dtype=np.float32)
    rect_array = np.zeros((count, MAX_RECTS, 5), dtype=np.float32)
    rect_mask = np.zeros((count, MAX_RECTS), dtype=np.float32)
    for index in range(count):
        for slot, enemy in enumerate(enemies[index]):
            enemy_array[index, slot] = enemy
            enemy_mask[index, slot] = 1.0
        for slot, rect in enumerate(rects[index]):
            rect_array[index, slot] = rect
            rect_mask[index, slot] = 1.0
    return {
        "player": torch.tensor(np.array(players, dtype=np.float32)),
        "enemies": torch.tensor(enemy_array),
        "enemy_mask": torch.tensor(enemy_mask),
        "rects": torch.tensor(rect_array),
        "rect_mask": torch.tensor(rect_mask),
        "label": torch.tensor(labels, dtype=torch.long),
        "costs": torch.tensor(np.array(costs, dtype=np.float32)),
        "game": torch.tensor(games, dtype=torch.long),
        # Target danger per cell: 1 = a stationary player is hit at once, 0 = never inside the horizon.
        "field": 1.0 - torch.tensor(np.array(fields, dtype=np.float32)) / 255.0,
        "has_field": torch.tensor(has_field),
    }


def subset(data: dict[str, torch.Tensor], index: torch.Tensor) -> dict[str, torch.Tensor]:
    return {key: value[index] for key, value in data.items()}


# -- model ----------------------------------------------------------------


def mlp(sizes: list[int]) -> nn.Sequential:
    layers: list[nn.Module] = []
    for position in range(len(sizes) - 1):
        layers.append(nn.Linear(sizes[position], sizes[position + 1]))
        if position < len(sizes) - 2:
            layers.append(nn.Tanh())
    return nn.Sequential(*layers)


class LearnedPotential(nn.Module):
    """V(q) = sum_enemies k + sum_rects r + b. Actions come from the slope of V."""

    def __init__(self, width: int = 64) -> None:
        super().__init__()
        self.entity = mlp([11, width, width, 1])
        self.rect = mlp([5, 32, 1])
        self.base = mlp([4, 32, 32, 1])
        self.raw_beta = nn.Parameter(torch.tensor(0.0))
        self.axis_bias = nn.Parameter(torch.tensor(0.0))
        # Field head: danger logit = gamma * V + delta. Used only by the field loss.
        self.raw_gamma = nn.Parameter(torch.tensor(0.0))
        self.delta = nn.Parameter(torch.tensor(-1.0))
        # Controller strength grows with the danger level at the player:
        # strength = softplus(gate_w * danger_logit + gate_c), applied to the normalised slope.
        self.use_path = False
        self.raw_temp = nn.Parameter(torch.tensor(-2.0))  # logit = -path_cost / temperature
        self.gate_w = nn.Parameter(torch.tensor(1.0))
        self.gate_c = nn.Parameter(torch.tensor(0.0))

    @property
    def beta(self) -> torch.Tensor:
        return nn.functional.softplus(self.raw_beta) + 1e-3

    def value(self, batch: dict[str, torch.Tensor], q: torch.Tensor) -> torch.Tensor:
        player = batch["player"]
        pv = player[:, 2:4]
        psize = player[:, 4:5]

        enemies = batch["enemies"]
        count = enemies.shape[1]
        kinds = torch.zeros(enemies.shape[0], count, 5, device=enemies.device)
        slot = torch.zeros(enemies.shape[:2], dtype=torch.long, device=enemies.device)
        personality = enemies[..., 5].round().long()
        slot = torch.where(personality == 1, 1, slot)
        slot = torch.where(personality == -1, 2, slot)
        slot = torch.where(personality == 2, 3, slot)
        slot = torch.where((personality == 3) | (personality == 4), 4, slot)
        kinds.scatter_(2, slot.unsqueeze(-1), 1.0)
        relative = (enemies[..., 0:2] - q.unsqueeze(1)) / 32.0
        velocity = (enemies[..., 2:4] - pv.unsqueeze(1)) / 3.0
        size = enemies[..., 4:5] / 8.0
        own = (psize / 8.0).unsqueeze(1).expand(-1, count, 1)
        features = torch.cat([kinds, relative, velocity, size, own], dim=-1)
        enemy_value = (self.entity(features).squeeze(-1) * batch["enemy_mask"]).sum(dim=1)

        rects = batch["rects"]
        low = rects[..., 0:2]
        high = rects[..., 0:2] + rects[..., 2:4]
        query = q.unsqueeze(1)
        nearest = torch.maximum(torch.minimum(query, high), low)
        offset = (nearest - query) / 32.0
        rect_features = torch.cat(
            [rects[..., 4:5], offset, rects[..., 2:4] / 64.0], dim=-1
        )
        rect_value = (self.rect(rect_features).squeeze(-1) * batch["rect_mask"]).sum(dim=1)

        base_features = torch.cat([q / 64.0 - 1.0, pv / 3.0], dim=-1)
        return enemy_value + rect_value + self.base(base_features).squeeze(-1)

    def field_logits(self, batch: dict[str, torch.Tensor], cells: torch.Tensor) -> torch.Tensor:
        """Danger logit at `cells` ([B, K, 2] positions) for a stationary player."""
        count = cells.shape[1]
        repeated = {
            key: batch[key].repeat_interleave(count, dim=0)
            for key in ("player", "enemies", "enemy_mask", "rects", "rect_mask")
        }
        repeated["player"] = repeated["player"].clone()
        repeated["player"][:, 2:4] = 0.0
        v = self.value(repeated, cells.reshape(-1, 2)).reshape(-1, count)
        return nn.functional.softplus(self.raw_gamma) * v + self.delta

    def path_costs(self, batch: dict[str, torch.Tensor]) -> torch.Tensor:
        """Mean predicted danger along the player's own path for each action ([B, 9]).
        Same rule as `Model::path_costs` in learned.rs."""
        player = batch["player"]
        count = player.shape[0]
        q = player[:, None, 0:2].expand(count, 9, 2)
        v = player[:, None, 2:4].expand(count, 9, 2)
        accel = (DIRECTIONS * 0.5).to(player.device)[None]
        samples = []
        for frame in range(1, PATH_FRAMES + 1):
            v = 0.8 * v + accel
            q = (q + v).clamp(2.0, 125.0)
            if frame % PATH_STEP == 0:
                samples.append(q)
        cells = torch.stack(samples, dim=2).reshape(count, 9 * len(samples), 2)
        danger = torch.sigmoid(self.field_logits(batch, cells)).reshape(count, 9, len(samples))
        held = HELD_AXES.to(player.device)[None]
        return danger.mean(dim=2) + MOVE_PENALTY * (2.0 - held)

    def logits(self, batch: dict[str, torch.Tensor], create_graph: bool = True):
        if self.use_path:
            temperature = nn.functional.softplus(self.raw_temp) + 1e-3
            return -self.path_costs(batch) / temperature, None
        return self.slope_logits(batch, create_graph)

    def slope_logits(self, batch: dict[str, torch.Tensor], create_graph: bool = True):
        q = batch["player"][:, 0:2].clone().requires_grad_(True)
        v = self.value(batch, q)
        (gradient,) = torch.autograd.grad(v.sum(), q, create_graph=create_graph)
        direction = gradient / (gradient.norm(dim=1, keepdim=True) + 1e-3)
        slope = direction @ DIRECTIONS.T.to(gradient.device)
        danger_logit = nn.functional.softplus(self.raw_gamma) * v.detach() + self.delta.detach()
        strength = nn.functional.softplus(self.gate_w * danger_logit + self.gate_c)
        logits = -strength[:, None] * slope + self.axis_bias * HELD_AXES.to(slope.device)
        return logits, v

    def export(self) -> dict:
        def dump(net: nn.Sequential) -> dict:
            layers = [m for m in net if isinstance(m, nn.Linear)]
            return {
                "layers": [
                    {"weights": layer.weight.detach().double().tolist(), "bias": layer.bias.detach().double().tolist()}
                    for layer in layers
                ]
            }

        return {
            "entity": dump(self.entity),
            "rect": dump(self.rect),
            "base": dump(self.base),
            "beta": float(self.beta),
            "axis_bias": float(self.axis_bias),
            "temp": float(nn.functional.softplus(self.raw_temp) + 1e-3),
            "gamma": float(nn.functional.softplus(self.raw_gamma)),
            "gate_w": float(self.gate_w),
            "gate_c": float(self.gate_c),
            "delta": float(self.delta),
        }


def load_export(model: LearnedPotential, spec: dict) -> None:
    """Load an exported model back into PyTorch."""
    def put(net: nn.Sequential, layers: dict) -> None:
        linear = [m for m in net if isinstance(m, nn.Linear)]
        for module, entry in zip(linear, layers["layers"]):
            module.weight.data = torch.tensor(entry["weights"], dtype=torch.float32)
            module.bias.data = torch.tensor(entry["bias"], dtype=torch.float32)

    put(model.entity, spec["entity"])
    put(model.rect, spec["rect"])
    put(model.base, spec["base"])
    model.raw_beta.data = torch.log(torch.expm1(torch.tensor(spec["beta"] - 1e-3)))
    model.axis_bias.data = torch.tensor(spec["axis_bias"])
    if "gamma" in spec:
        model.raw_gamma.data = torch.log(torch.expm1(torch.tensor(spec["gamma"])))
        model.delta.data = torch.tensor(spec["delta"])
    if "temp" in spec:
        model.raw_temp.data = torch.log(torch.expm1(torch.tensor(max(spec["temp"] - 1e-3, 1e-4))))
    if "gate_w" in spec:
        model.gate_w.data = torch.tensor(spec["gate_w"])
        model.gate_c.data = torch.tensor(spec["gate_c"])


# -- training -------------------------------------------------------------


def danger_frames(data: dict[str, torch.Tensor]) -> torch.Tensor:
    """Frames that need a dodge: standing still ends in a collision inside the lookahead
    horizon (a collision adds at least 3,500 to an action's cost), and a better action exists."""
    costs = data["costs"]
    return (costs[:, 0] - costs.min(dim=1).values) > 2500.0


CELL_CENTRES = torch.stack(
    torch.meshgrid(
        (torch.arange(FIELD) + 0.5) * CELL, (torch.arange(FIELD) + 0.5) * CELL, indexing="xy"
    ),
    dim=-1,
).reshape(-1, 2)  # row-major: index = row * FIELD + column, columns run along x


def field_usable(data: dict[str, torch.Tensor]) -> torch.Tensor:
    """Frames with an arrival field and no pattern rectangles (the field models enemies only)."""
    return data["has_field"] & (data["rect_mask"].sum(dim=1) == 0)


def sample_cells(batch: dict[str, torch.Tensor], uniform: int, near: int, generator=None):
    """Random cells over the playfield plus the cells closest to the player."""
    count = batch["player"].shape[0]
    pick = torch.randint(0, FIELD * FIELD, (count, uniform), generator=generator)
    distance = (CELL_CENTRES.unsqueeze(0) - batch["player"][:, None, 0:2]).norm(dim=-1)
    closest = distance.topk(near, dim=1, largest=False).indices
    return torch.cat([pick, closest], dim=1)


def field_loss(model: LearnedPotential, batch: dict[str, torch.Tensor], uniform: int = 24, near: int = 8, generator=None):
    cells = sample_cells(batch, uniform, near, generator)
    target = batch["field"].gather(1, cells)
    logit = model.field_logits(batch, CELL_CENTRES[cells])
    loss = nn.functional.binary_cross_entropy_with_logits(logit, target)
    return loss, torch.sigmoid(logit), target


@torch.no_grad()
def evaluate_field(model: LearnedPotential, data: dict[str, torch.Tensor], limit: int = 4000) -> dict[str, float]:
    index = field_usable(data).nonzero().squeeze(1)[:limit]
    if index.numel() == 0:
        return {"field_bce": float("nan"), "field_corr": float("nan"), "field_base": float("nan")}
    batch = subset(data, index)
    generator = torch.Generator().manual_seed(1)
    loss, predicted, target = field_loss(model, batch, 32, 8, generator)
    mean = target.mean()
    base = nn.functional.binary_cross_entropy(mean.expand_as(target).clamp(1e-4, 1 - 1e-4), target)
    corr = torch.corrcoef(torch.stack([predicted.flatten(), target.flatten()]))[0, 1]
    return {"field_bce": loss.item(), "field_corr": corr.item(), "field_base": base.item()}


@torch.no_grad()
def evaluate(model: LearnedPotential, data: dict[str, torch.Tensor], batch_size: int = 4096) -> dict[str, float]:
    hits, fatal_hits, loss_sum = [], [], 0.0
    for start in range(0, data["label"].shape[0], batch_size):
        batch = {key: value[start : start + batch_size] for key, value in data.items()}
        with torch.enable_grad():
            logits, _ = model.logits(batch, create_graph=False)
        loss_sum += nn.functional.cross_entropy(logits, batch["label"], reduction="sum").item()
        pick = logits.argmax(dim=1)
        hits.append((pick == batch["label"]).float())
        costs = batch["costs"]
        chosen = costs.gather(1, pick[:, None])[:, 0]
        fatal_hits.append(((chosen - costs.min(dim=1).values) > 2500.0).float())
    hit = torch.cat(hits)
    danger = danger_frames(data)
    return {
        "loss": loss_sum / hit.numel(),
        "accuracy": hit.mean().item(),
        "accuracy_danger": hit[danger].mean().item() if danger.any() else float("nan"),
        "danger_share": danger.float().mean().item(),
        "fatal": torch.cat(fatal_hits).mean().item(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, nargs="+", required=True)
    parser.add_argument("--init", type=Path, default=None, help="start from an exported model")
    parser.add_argument("--val", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=512)
    parser.add_argument("--lr", type=float, default=2e-3)
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--danger-weight", type=float, default=4.0, help="loss weight on frames where the choice matters")
    parser.add_argument("--regret-weight", type=float, default=0.0, help="weight on expected regret under the student's softmax")
    parser.add_argument("--field-weight", type=float, default=0.0, help="weight on the arrival-field loss")
    parser.add_argument("--action-weight", type=float, default=1.0, help="weight on the action losses (0 = field only)")
    parser.add_argument("--freeze-v", action="store_true", help="train only beta and axis_bias")
    parser.add_argument("--path", action="store_true", help="score the nine paths through V instead of the local slope")
    parser.add_argument("--ce-weight", type=float, default=1.0, help="weight on cross-entropy to the teacher's action")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    started = time.time()
    train, val = load(args.train, args.limit), load([args.val], args.limit)
    print(f"loaded {train['label'].shape[0]} train / {val['label'].shape[0]} val frames in {time.time() - started:.0f}s")
    teacher_share = torch.bincount(train["label"], minlength=9).float()
    print(f"critical frames: train {danger_frames(train).float().mean():.3f}  val {danger_frames(val).float().mean():.3f}")
    print("teacher action share:", {name: round(float(v), 3) for name, v in zip(ACTIONS, teacher_share / teacher_share.sum())})

    model = LearnedPotential(args.width)
    if args.init:
        load_export(model, json.loads(args.init.read_text()))
    model.use_path = args.path
    trainable = [model.gate_w, model.gate_c, model.axis_bias] if args.freeze_v else list(model.parameters())
    optimiser = torch.optim.Adam(trainable, lr=args.lr)
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, args.epochs)
    weights = 1.0 + (args.danger_weight - 1.0) * danger_frames(train).float()
    count = train["label"].shape[0]
    field_pool = field_usable(train).nonzero().squeeze(1)
    print(f"frames with a usable arrival field: {field_pool.numel()}")

    for epoch in range(args.epochs):
        order = torch.randperm(count)
        total = 0.0
        for start in range(0, count, args.batch):
            index = order[start : start + args.batch]
            batch = subset(train, index)
            logits, _ = model.logits(batch)
            loss = args.ce_weight * (nn.functional.cross_entropy(logits, batch["label"], reduction="none") * weights[index]).mean()
            if args.regret_weight > 0:
                costs = batch["costs"]
                regret = ((costs - costs.min(dim=1, keepdim=True).values) / 1000.0).clamp(max=5.0)
                loss = loss + args.regret_weight * (torch.softmax(logits, dim=1) * regret).sum(dim=1).mean()
            loss = args.action_weight * loss
            if args.field_weight > 0 and field_pool.numel() > 0:
                chosen = field_pool[torch.randint(0, field_pool.numel(), (128,))]
                loss = loss + args.field_weight * field_loss(model, subset(train, chosen))[0]
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            total += loss.item() * index.numel()
        schedule.step()
        report = evaluate(model, val)
        if args.field_weight > 0:
            field = evaluate_field(model, val)
            print(f"           field BCE {field['field_bce']:.4f} (constant {field['field_base']:.4f})  corr {field['field_corr']:.3f}")
        print(
            f"epoch {epoch + 1:2d}  train {total / count:.4f}  val loss {report['loss']:.4f}  "
            f"acc {report['accuracy']:.3f}  danger-acc {report['accuracy_danger']:.3f}  fatal {report['fatal']:.3f}  "
            f"beta {float(model.beta):.3f}  ({time.time() - started:.0f}s)",
            flush=True,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(model.export()))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
