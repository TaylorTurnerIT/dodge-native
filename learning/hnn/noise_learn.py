"""Train a pooled observation estimator with synthetic detector noise.

Inputs and rollout targets come from visible geometry. Engine labels are not read.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn

import learn_observed as base

HISTORY = 9
DELTAS = 2 * (HISTORY - 1)
FEATURES = DELTAS + 8
HORIZON = base.HORIZON


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
        factor = torch.where(x[..., DELTAS + 2] > 0.5, 2 * torch.sigmoid(local[..., 2]), torch.ones_like(local[..., 2]))
        displacement = x[..., DELTAS - 6:DELTAS].reshape(*x.shape[:-1], 3, 2).mean(-2)
        velocity = displacement / (rate[:, None, :] * factor[..., None]).clamp_min(0.05) + 0.1 * torch.tanh(local[..., :2])
        return rate, factor, velocity


def augment(x, position, target, mask, valid, level):
    """Perturb geometry independently; all targets remain observation-derived."""
    x, position, target, mask, valid = (v.clone() for v in (x, position, target, mask, valid))
    delta = x[..., :DELTAS].reshape(*x.shape[:-1], HISTORY - 1, 2)
    backwards = torch.flip(torch.cumsum(torch.flip(delta, [-2]), -2), [-2])
    history = torch.cat((position[..., None, :] - backwards, position[..., None, :]), -2)
    sigma = 0.5 * level
    history = history + sigma * torch.randn_like(history)
    target = target + sigma * torch.randn_like(target)
    quantize = torch.rand((*x.shape[:-1], 1, 1), device=x.device) < level
    history = torch.where(quantize, history.round(), history)
    target = torch.where(quantize, target.round(), target)
    for i in range(1, HISTORY):
        missed = torch.rand((*x.shape[:-1], 1), device=x.device) < 0.01 * level
        history[..., i, :] = torch.where(missed, history[..., i - 1, :], history[..., i, :])
    last = history[..., -1, :]
    shift = last - position
    x[..., :DELTAS] = (history[..., 1:, :] - history[..., :-1, :]).reshape(*x.shape[:-1], DELTAS)
    x[..., DELTAS:DELTAS + 2] += shift / 128
    x[..., DELTAS + 4:DELTAS + 6] += shift / 128
    confused = torch.rand(x.shape[:-1], device=x.device) < 0.01 * level
    x[..., DELTAS + 2] = torch.where(confused, 1 - x[..., DELTAS + 2], x[..., DELTAS + 2])
    missed = torch.rand(mask.shape, device=x.device) < 0.01 * level
    mask = mask * (~missed)
    valid = valid * (~missed)
    return x, last, target, mask, valid


def train(path, physics, output, epochs):
    torch.set_num_threads(4)
    torch.manual_seed(1847)
    data = np.load(path)
    arrays = [torch.from_numpy(data[k]) for k in ('features', 'position', 'future', 'mask', 'player', 'valid')]
    if arrays[0].shape[-1] != FEATURES:
        raise SystemExit('Dataset history does not match this estimator')
    train_ids = torch.from_numpy(np.flatnonzero(~data['validation']))
    val_ids = torch.from_numpy(np.flatnonzero(data['validation']))
    if not len(train_ids) or not len(val_ids):
        raise SystemExit('Need separate training and validation episodes')
    model, force = Estimator(), base.Force(physics)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    generator = torch.Generator().manual_seed(1847)

    def loss(ids, level):
        x, pos, target, mask, player, valid = [a[ids] for a in arrays]
        x, pos, target, mask, valid = augment(x, pos, target, mask, valid, level)
        rate, factor, velocity = model(x, mask)
        q = pos
        result = 0
        for k in range(HORIZON):
            velocity = velocity + force(q - player[:, None, k], x[..., DELTAS + 2]) - force.gamma * velocity
            q = q + rate[:, None, :] * factor[..., None] * velocity
            err = ((q - target[:, :, k]) ** 2).sum(-1)
            result = result + (err * valid).sum() / valid.sum().clamp_min(1)
        return result / HORIZON + 0.0001 * ((factor - 1) ** 2 * mask).sum() / mask.sum().clamp_min(1)

    for epoch in range(epochs):
        level = epoch / max(1, epochs - 1)
        model.train()
        perm = train_ids[torch.randperm(len(train_ids), generator=generator)]
        losses = []
        for ids in perm.split(128):
            value = loss(ids, level)
            optimizer.zero_grad()
            value.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1)
            optimizer.step()
            losses.append(value.item())
        model.eval()
        with torch.no_grad():
            torch.manual_seed(9847)
            validation = [loss(ids, 1.0).item() for ids in val_ids.split(128)]
        print('epoch', epoch + 1, 'noise', round(level, 3), 'loss', sum(losses) / len(losses), 'pixel_validation', sum(validation) / len(validation), flush=True)
    state = {key: value.detach().tolist() for key, value in model.state_dict().items()}
    Path(output).write_text(json.dumps({'format': 'observed_estimator_v2', 'history': HISTORY, 'state': state}))
    print('wrote', output, flush=True)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='action', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--out', required=True)
    prep.add_argument('files', nargs='+')
    fit = commands.add_parser('train')
    fit.add_argument('--data', required=True)
    fit.add_argument('--physics', required=True)
    fit.add_argument('--out', required=True)
    fit.add_argument('--epochs', type=int, default=12)
    args = parser.parse_args()
    if args.action == 'prepare':
        base.HISTORY, base.FEATURES = HISTORY, FEATURES
        base.prepare(args.files, args.out)
    else:
        train(args.data, args.physics, args.out, args.epochs)


if __name__ == '__main__':
    main()
