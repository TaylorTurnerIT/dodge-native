"""Measure kamikaze acceleration from consecutive observed frames."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from statistics import median

parser = argparse.ArgumentParser()
parser.add_argument('data', type=Path)
parser.add_argument('--min-distance', type=float, default=0.0)
parser.add_argument('--max-distance', type=float, default=25.0)
args = parser.parse_args()
previous = {}
values = defaultdict(list)
skipped = 0
with args.data.open() as source:
    for line in source:
        try:
            row = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        if 'ph' not in row:
            continue
        old = previous.get(row['s'])
        previous[row['s']] = row
        if old is None or row['f'] != old['f'] + 1:
            continue
        used = set()
        for e in old['ph']:
            if e[5] != 1:
                continue
            options = [(math.hypot(n[0] - e[0] - e[2] * e[6], n[1] - e[1] - e[3] * e[6]), i, n)
                       for i, n in enumerate(row['ph']) if n[5] == 1 and i not in used]
            if not options:
                continue
            distance, i, n = min(options)
            if distance > 1:
                continue
            used.add(i)
            if not args.min_distance <= math.hypot(e[0] - row['p'][0], e[1] - row['p'][1]) <= args.max_distance:
                continue
            for axis in (0, 1):
                offset = e[axis] - row['p'][axis]
                if abs(offset) < 1:
                    continue
                accel = n[axis + 2] - 0.99 * e[axis + 2]
                if abs(accel) > 0.04:
                    continue
                values['positive' if offset > 0 else 'negative'].append(accel)
for key, samples in sorted(values.items()):
    print(f'{key} offset: {len(samples)} axes; median acceleration {median(samples):.8f}; range {min(samples):.6f} to {max(samples):.6f}')
print(f'malformed rows skipped: {skipped}')
