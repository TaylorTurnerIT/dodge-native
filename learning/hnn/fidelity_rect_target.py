"""Measure reversals of 24-by-64 rectangles in observed frame records."""
import collections
import json
import sys

history = {}
last = {}
turns = collections.defaultdict(list)
with open(sys.argv[1]) as records:
    for line in records:
        try:
            row = json.loads(line)
            seed, frame = row['s'], row['f']
        except (ValueError, KeyError):
            continue
        rects = row.get('r', [])
        previous = history.get(seed)
        history[seed] = (frame, rects)
        if not previous or previous[0] != frame - 1 or len(previous[1]) != len(rects):
            continue
        for index, (old, new) in enumerate(zip(previous[1], rects)):
            if len(old) < 4 or len(new) < 4 or any(abs(old[i] - new[i]) > 0.01 for i in (2, 3)):
                continue
            shape = (round(new[2]), round(new[3]))
            if shape not in ((24, 64), (64, 24)):
                continue
            for axis in (0, 1):
                delta = new[axis] - old[axis]
                key = (seed, index, shape, axis)
                prior = last.get(key)
                if abs(delta) > 0.05:
                    if prior and prior[0] == frame - 1 and prior[1] * delta < 0:
                        turns[(shape, axis)].append((seed, round(old[axis], 2)))
                    last[key] = (frame, delta)
for key, samples in sorted(turns.items()):
    positions = collections.Counter(position for _, position in samples)
    print(key, 'turns', len(samples), 'seeds', len({seed for seed, _ in samples}), 'positions', positions.most_common())
