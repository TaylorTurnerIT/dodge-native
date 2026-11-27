"""Train a self-supervised state estimator from stripped visible geometry.

Only fields s, f, p, e and r from observed_dataset.py are read. Engine velocities,
rates, states and actions are never inputs or targets. Track matching uses geometry.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np
import torch
from torch import nn

MAX_ENTITIES = 24
HISTORY = 5
HORIZON = 8
FEATURES = 16


def prepare(paths, out):
    examples = []
    for path in paths:
        frames = []
        def episode():
            if len(frames) < HISTORY + HORIZON:
                return
            tracks = {}
            active = {}
            next_id = 0
            frame_ids = []
            for row in frames:
                current = [e for e in row['e'] if e[3] in (0, 1)]
                candidates = []
                for ident, hist in active.items():
                    old = hist[-1]
                    dx = old[1] - hist[-2][1] if len(hist) > 1 else 0.0
                    dy = old[2] - hist[-2][2] if len(hist) > 1 else 0.0
                    for j, e in enumerate(current):
                        if e[3] == old[4]:
                            dist = np.hypot(e[0] - old[1] - dx, e[1] - old[2] - dy)
                            if dist <= 2.0:
                                candidates.append((dist, ident, j))
                candidates.sort()
                used = set()
                matches = {}
                for _, ident, j in candidates:
                    if ident not in used and j not in matches:
                        used.add(ident)
                        matches[j] = ident
                new_active = {}
                ids = []
                for j, e in enumerate(current):
                    if j in matches:
                        ident = matches[j]
                    else:
                        ident = next_id
                        next_id += 1
                        tracks[ident] = []
                    # f,x,y,size,kind,px,py,age
                    hist = tracks[ident]
                    hist.append((row['f'], e[0], e[1], e[2], e[3], row['p'][0], row['p'][1], len(hist) + 1))
                    new_active[ident] = hist
                    ids.append((ident, len(hist) - 1))
                active = new_active
                frame_ids.append(ids)
            for t in range(HISTORY - 1, len(frames) - HORIZON, 8):
                selected = []
                for ident, i in frame_ids[t]:
                    h = tracks[ident]
                    if i < HISTORY - 1:
                        continue
                    span = h[i-HISTORY+1:i+1]
                    if any(span[k+1][0] != span[k][0] + 1 for k in range(len(span)-1)):
                        continue
                    delta = np.diff(np.array([[v[1], v[2]] for v in span]), axis=0)
                    now = span[HISTORY-1]
                    feature = [*delta[:HISTORY-1].reshape(-1),
                               (now[1]-now[5])/128, (now[2]-now[6])/128,
                               now[4], min(now[7]/300, 3), now[1]/128, now[2]/128,
                               now[3]/30, min(now[0]/8000, 1.5)]
                    after = h[i+1:i+HORIZON+1]
                    valid = len(after) == HORIZON and all(after[k][0] == now[0] + k + 1 for k in range(len(after)))
                    future = [[v[1], v[2]] for v in after] if valid else [[0, 0]] * HORIZON
                    if valid:
                        changes = np.diff(np.concatenate((delta[-1:], np.diff(np.array([[now[1], now[2]], *future]), axis=0))), axis=0)
                        valid = np.max(np.linalg.norm(changes, axis=1)) <= 0.18
                    selected.append((feature, [now[1], now[2]], future, valid))
                if not selected:
                    continue
                selected = selected[:MAX_ENTITIES]
                features = np.zeros((MAX_ENTITIES, FEATURES), np.float32)
                position = np.zeros((MAX_ENTITIES, 2), np.float32)
                future = np.zeros((MAX_ENTITIES, HORIZON, 2), np.float32)
                mask = np.zeros(MAX_ENTITIES, np.float32)
                valid = np.zeros(MAX_ENTITIES, np.float32)
                for j, (feat, pos, target, keep) in enumerate(selected):
                    features[j], position[j], future[j], mask[j], valid[j] = feat, pos, target, 1, keep
                if not valid.any():
                    continue
                players = np.array([frames[t+k]['p'][:2] for k in range(1, HORIZON+1)], np.float32)
                examples.append((features, position, future, mask, players, valid, frames[t]['s'] % 8 == 7))
        with open(path) as handle:
            for line in handle:
                row = json.loads(line)
                if 'end' in row:
                    episode()
                    frames = []
                else:
                    frames.append(row)
        if frames:
            episode()
        print(path, 'examples', len(examples), flush=True)
    if not examples:
        raise SystemExit('No complete observation sequences')
    arrays = list(zip(*examples))
    np.savez_compressed(out, features=np.stack(arrays[0]), position=np.stack(arrays[1]),
                        future=np.stack(arrays[2]), mask=np.stack(arrays[3]), player=np.stack(arrays[4]),
                        valid=np.stack(arrays[5]), validation=np.array(arrays[6]))
    print('wrote', out, len(examples), flush=True)


class Estimator(nn.Module):
    def __init__(self):
        super().__init__()
        self.entity = nn.Linear(FEATURES, 24)
        self.global_hidden = nn.Linear(24, 16)
        self.global_output = nn.Linear(16, 1)
        self.local_hidden = nn.Linear(24, 16)
        self.local_output = nn.Linear(16, 3)
        nn.init.zeros_(self.local_output.weight)
        nn.init.zeros_(self.local_output.bias)

    def forward(self, x, mask):
        h = torch.tanh(self.entity(x))
        pooled = (h * mask[..., None]).sum(1) / mask.sum(1, keepdim=True).clamp_min(1)
        rate = 0.3 + 3.7 * torch.sigmoid(self.global_output(torch.tanh(self.global_hidden(pooled))))
        local = self.local_output(torch.tanh(self.local_hidden(h)))
        factor = torch.where(x[..., 10] > 0.5, 2 * torch.sigmoid(local[..., 2]), torch.ones_like(local[..., 2]))
        velocity = x[..., 6:8] / (rate[:, None, :] * factor[..., None]).clamp_min(0.05) + 0.1 * torch.tanh(local[..., :2])
        return rate, factor, velocity


class Force(nn.Module):
    def __init__(self, path):
        super().__init__()
        spec = json.loads(Path(path).read_text())
        self.gamma = spec['gamma']
        self.weights = nn.ParameterList([nn.Parameter(torch.tensor(l['weights'], dtype=torch.float32), requires_grad=False) for l in spec['layers']])
        self.bias = nn.ParameterList([nn.Parameter(torch.tensor(l['bias'], dtype=torch.float32), requires_grad=False) for l in spec['layers']])

    def forward(self, offset, kind):
        kind = kind.long().clamp(0, 1)
        x = torch.cat((offset / 64, torch.nn.functional.one_hot(kind, 5).to(offset.dtype)), -1)
        activations = []
        for i, (w, b) in enumerate(zip(self.weights, self.bias)):
            x = x @ w.T + b
            if i + 1 < len(self.weights):
                x = torch.tanh(x)
                activations.append(x)
        grad = self.weights[-1].expand(*offset.shape[:-1], -1, -1).squeeze(-2)
        for i in range(len(self.weights)-2, -1, -1):
            grad = (grad * (1 - activations[i] ** 2)) @ self.weights[i]
        return -grad[..., :2] / 64


def train(data, physics, output, epochs):
    torch.set_num_threads(4)
    torch.manual_seed(1847)
    data = np.load(data)
    arrays = [torch.from_numpy(data[k]) for k in ('features', 'position', 'future', 'mask', 'player', 'valid')]
    model, force = Estimator(), Force(physics)
    opt = torch.optim.Adam(model.parameters(), lr=0.001)
    train_ids = torch.from_numpy(np.flatnonzero(~data['validation']))
    val_ids = torch.from_numpy(np.flatnonzero(data['validation']))
    if not len(train_ids) or not len(val_ids):
        raise SystemExit('Need separate training and validation episodes')
    generator = torch.Generator().manual_seed(1847)
    def prediction_loss(ids):
        x, pos, target, mask, player, valid = [a[ids] for a in arrays]
        rate, factor, velocity = model(x, mask)
        q = pos
        loss = 0
        for k in range(HORIZON):
            velocity = velocity + force(q - player[:, None, k], x[..., 10]) - force.gamma * velocity
            q = q + rate[:, None, :] * factor[..., None] * velocity
            err = ((q - target[:, :, k]) ** 2).sum(-1)
            loss = loss + (err * valid).sum() / valid.sum().clamp_min(1)
        return loss / HORIZON + 0.0001 * ((factor - 1) ** 2 * mask).sum() / mask.sum().clamp_min(1)
    for epoch in range(epochs):
        model.train()
        perm = train_ids[torch.randperm(len(train_ids), generator=generator)]
        losses = []
        for ids in perm.split(128):
            loss = prediction_loss(ids)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1)
            opt.step()
            losses.append(loss.item())
        model.eval()
        with torch.no_grad():
            validation = [prediction_loss(ids).item() for ids in val_ids.split(128)]
        print('epoch', epoch+1, 'loss', sum(losses)/len(losses), 'validation', sum(validation)/len(validation), flush=True)
    state = {key: value.detach().tolist() for key, value in model.state_dict().items()}
    Path(output).write_text(json.dumps({'format': 'observed_estimator_v1', 'history': HISTORY, 'state': state}))
    print('wrote', output, flush=True)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='action', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--out', required=True)
    prep.add_argument('files', nargs='+')
    fit = sub.add_parser('train')
    fit.add_argument('--data', required=True)
    fit.add_argument('--physics', required=True)
    fit.add_argument('--out', required=True)
    fit.add_argument('--epochs', type=int, default=10)
    args = p.parse_args()
    if args.action == 'prepare':
        prepare(args.files, args.out)
    else:
        train(args.data, args.physics, args.out, args.epochs)


if __name__ == '__main__':
    main()
