"""Read pixel shards and create dense, per-kind entity targets."""
import json
import math
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset


class PixelDataset(Dataset):
    """Return consecutive indexed frames and dense center targets.

    Channel zero is the player. Remaining channels follow ``enemy_kinds``.
    Kinds below 2 use top-left positions; other enemies and the player use centers.
    """

    def __init__(self, directory, stack=4, stride=1, enemy_kinds=(-1, 0, 1, 2, 3)):
        if stack < 1 or stride not in (1, 2):
            raise ValueError('stack must be positive and target stride must be 1 or 2')
        self.stack, self.stride = stack, stride
        self.kinds = tuple(enemy_kinds)
        if len(set(self.kinds)) != len(self.kinds):
            raise ValueError('enemy kinds must be unique')
        self.shards, self.offsets, self.samples = [], [], []
        expected = 0
        for labels_path in sorted(Path(directory).glob('shard-*.jsonl')):
            pixels_path = labels_path.with_suffix('.bin')
            offsets = []
            with labels_path.open('rb') as labels:
                while True:
                    offset = labels.tell()
                    line = labels.readline()
                    if not line:
                        break
                    row = json.loads(line)
                    if row['index'] != expected:
                        raise ValueError('non-contiguous frame indices')
                    offsets.append(offset)
                    refs = row['previous'][:stack - 1]
                    if row['stride'] == 1 and len(refs) == stack - 1:
                        self.samples.append((len(self.shards), len(offsets) - 1, tuple(reversed(refs)) + (expected,)))
                    expected += 1
            if pixels_path.stat().st_size != len(offsets) * 128 * 128:
                raise ValueError(f'pixel and label count mismatch: {labels_path.name}')
            self.shards.append((pixels_path, labels_path, expected - len(offsets), len(offsets)))
            self.offsets.append(offsets)
        if not self.shards:
            raise ValueError('no shards found')
        self.ends = [start + count for _, _, start, count in self.shards]

    def __len__(self):
        return len(self.samples)

    def _pixel(self, index):
        from bisect import bisect_right
        shard = bisect_right(self.ends, index)
        path, _, start, count = self.shards[shard]
        return np.memmap(path, dtype=np.uint8, mode='r', shape=(count, 128, 128))[index - start]

    def __getitem__(self, item):
        shard, row, indices = self.samples[item]
        with self.shards[shard][1].open('rb') as labels:
            labels.seek(self.offsets[shard][row])
            label = json.loads(labels.readline())
        pixels = torch.from_numpy(np.stack([self._pixel(i) for i in indices]))
        size = 128 // self.stride
        channels = 1 + len(self.kinds)
        heat = torch.zeros((channels, size, size), dtype=torch.float32)
        offset = torch.zeros((channels, 2, size, size), dtype=torch.float32)
        extent = torch.zeros_like(offset)
        velocity = torch.zeros_like(offset)
        collisions = torch.zeros_like(heat, dtype=torch.bool)
        objects = [(0, label['player'], True)]
        for enemy in label['enemies']:
            if enemy['kind'] not in self.kinds:
                raise ValueError(f"unknown enemy kind {enemy['kind']}")
            objects.append((1 + self.kinds.index(enemy['kind']), enemy, False))
        for channel, obj, player in objects:
            centered = player or obj['kind'] >= 2
            width = obj['size'] * (2 if centered else 1)
            x = obj['x'] if centered else obj['x'] + width / 2
            y = obj['y'] if centered else obj['y'] + width / 2
            gx, gy = x / self.stride, y / self.stride
            ix, iy = math.floor(gx), math.floor(gy)
            if not (0 <= ix < size and 0 <= iy < size):
                continue
            if heat[channel, iy, ix]:
                collisions[channel, iy, ix] = True
                continue
            heat[channel, iy, ix] = 1
            offset[channel, :, iy, ix] = torch.tensor((gx - ix, gy - iy))
            extent[channel, :, iy, ix] = width
            velocity[channel, :, iy, ix] = torch.tensor((obj['vx'] if player else obj['vx_rate'], obj['vy'] if player else obj['vy_rate']))
        return pixels, {'heatmap': heat, 'offset': offset, 'size': extent,
                        'velocity': velocity, 'collision': collisions, 'label': label}
