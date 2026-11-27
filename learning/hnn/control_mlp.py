"""Control experiment: same data, same inputs, same loss, but the nine logits come straight
from a network instead of from the slope of V. If this beats the potential model by a lot,
the limit is the gradient structure, not the data or the inputs."""
import argparse, time
from pathlib import Path
import torch
from torch import nn
import train

class Direct(nn.Module):
    def __init__(self, width=64):
        super().__init__()
        self.entity = train.mlp([13, width, width])      # per-entity embedding, summed
        self.rect = train.mlp([7, 32, width])
        self.head = train.mlp([width + 4, 128, 128, 9])
    def logits(self, batch, create_graph=True):
        player = batch["player"]; q = player[:, 0:2]; pv = player[:, 2:4]
        e = batch["enemies"]; n = e.shape[1]
        kinds = torch.zeros(e.shape[0], n, 5)
        p = e[..., 5].round().long(); slot = torch.zeros_like(p)
        slot = torch.where(p == 1, 1, slot); slot = torch.where(p == -1, 2, slot)
        slot = torch.where(p == 2, 3, slot); slot = torch.where((p == 3) | (p == 4), 4, slot)
        kinds.scatter_(2, slot.unsqueeze(-1), 1.0)
        rel = (e[..., 0:2] - q.unsqueeze(1)) / 32.0; vel = (e[..., 2:4] - pv.unsqueeze(1)) / 3.0
        f = torch.cat([kinds, rel, vel, e[..., 4:5] / 8.0, (player[:, 4:5] / 8.0).unsqueeze(1).expand(-1, n, 1), (rel.norm(dim=-1, keepdim=True)), (vel.norm(dim=-1, keepdim=True))], -1)
        ev = (self.entity(f) * batch["enemy_mask"].unsqueeze(-1)).sum(1)
        r = batch["rects"]; low = r[..., 0:2]; high = low + r[..., 2:4]
        near = torch.maximum(torch.minimum(q.unsqueeze(1), high), low)
        off = (near - q.unsqueeze(1)) / 32.0
        rf = torch.cat([r[..., 4:5], off, r[..., 2:4] / 64.0, off.norm(dim=-1, keepdim=True), torch.ones_like(r[..., 4:5])], -1)
        rv = (self.rect(rf) * batch["rect_mask"].unsqueeze(-1)).sum(1)
        h = torch.cat([ev + rv, q / 64.0 - 1.0, pv / 3.0], -1)
        return self.head(h), None

parser = argparse.ArgumentParser(); parser.add_argument("--train", type=Path, nargs="+"); parser.add_argument("--val", type=Path)
parser.add_argument("--epochs", type=int, default=25); parser.add_argument("--regret-weight", type=float, default=3.0)
a = parser.parse_args(); torch.manual_seed(0)
tr, va = train.load(a.train), train.load([a.val])
m = Direct(); opt = torch.optim.Adam(m.parameters(), 2e-3); sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, a.epochs)
w = 1.0 + 3.0 * train.danger_frames(tr).float(); n = tr["label"].shape[0]; t0 = time.time()
for ep in range(a.epochs):
    order = torch.randperm(n)
    for s in range(0, n, 512):
        idx = order[s:s+512]; b = train.subset(tr, idx); lg, _ = m.logits(b)
        loss = (nn.functional.cross_entropy(lg, b["label"], reduction="none") * w[idx]).mean()
        c = b["costs"]; reg = ((c - c.min(1, keepdim=True).values) / 1000.0).clamp(max=5.0)
        loss = loss + a.regret_weight * (torch.softmax(lg, 1) * reg).sum(1).mean()
        opt.zero_grad(); loss.backward(); opt.step()
    sch.step()
    if ep % 5 == 4 or ep == a.epochs - 1:
        with torch.no_grad():
            lg, _ = m.logits(va); pick = lg.argmax(1); c = va["costs"]
            fatal = ((c.gather(1, pick[:, None])[:, 0] - c.min(1).values) > 2500).float().mean()
            print(f"epoch {ep+1}  acc {(pick == va['label']).float().mean():.3f}  fatal {fatal:.3f}  ({time.time()-t0:.0f}s)", flush=True)
