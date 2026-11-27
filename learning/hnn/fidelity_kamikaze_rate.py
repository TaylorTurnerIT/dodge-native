"""Measure kamikaze rate changes relative to normal enemies in observed frames."""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from statistics import median

parser = argparse.ArgumentParser()
parser.add_argument('data', type=Path)
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
        a = [e[6] for e in old['ph'] if e[5] == 0]
        b = [e[6] for e in row['ph'] if e[5] == 0]
        if not a or not b:
            continue
        old_global, new_global = median(a), median(b)
        if old_global <= 0 or new_global <= 0:
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
            old_rate, new_rate = e[6] / old_global, n[6] / new_global
            if old_rate > 1.02:
                continue
            delta = new_rate - old_rate
            if abs(delta) > 0.05:
                continue
            close = math.hypot(e[0] - row['p'][0], e[1] - row['p'][1]) <= 25
            key = 'near' if close else ('far below one' if old_rate < 0.98 else 'far near one')
            values[key].append(delta)
for key, samples in sorted(values.items()):
    print(f'{key}: {len(samples)} transitions; median factor change {median(samples):.8f}; range {min(samples):.6f} to {max(samples):.6f}')
print(f'malformed rows skipped: {skipped}')
