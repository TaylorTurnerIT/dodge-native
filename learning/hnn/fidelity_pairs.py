"""Score the collision classifier on observed, fixed-action replay transitions.

Pair labels require both enemies to become dying, stable engine order, no nearby
third new dying enemy, and no overlapping rectangle. Results are teacher-forced:
each prediction uses the observed frame, not the model's previous rollout.
"""
import collections
import json
import math
import pathlib
import sys

spec = json.load(open(sys.argv[1]))['collision']
counts = {h: collections.Counter() for h in (4, 8, 12, 24, 36)}
transitions = 0

def probability(a, b):
    if math.hypot(a[0] - b[0], a[1] - b[1]) > spec['near']:
        return 0.0
    features = []
    for step in (0, 1):
        ax, ay = a[0] + a[2] * a[6] * step, a[1] + a[3] * a[6] * step
        bx, by = b[0] + b[2] * b[6] * step, b[1] + b[3] * b[6] * step
        sa, sb = max(a[4], 3), max(b[4], 3)
        ox = min(ax + sa, bx + sb) - max(ax, bx)
        oy = min(ay + sa, by + sb) - max(ay, by)
        features.extend((ox / 4, oy / 4, min(ox, oy) / 4))
    features.extend((max(a[4], 3) / 4, max(b[4], 3) / 4, int(a[5] == 1), int(b[5] == 1)))
    for index, layer in enumerate(spec['layers']):
        values = [bias + sum(w * x for w, x in zip(row, features)) for row, bias in zip(layer['weights'], layer['bias'])]
        features = values if index == len(spec['layers']) - 1 else [math.tanh(x) for x in values]
    return 1 / (1 + math.exp(-max(-700, min(700, features[0]))))

def overlaps(e, rect):
    return e[0] + e[4] > rect[0] and e[1] + e[4] > rect[1] and e[0] < rect[0] + rect[2] and e[1] < rect[1] + rect[3]

paths = sorted(pathlib.Path(sys.argv[2]).glob('*.log'))
if not paths:
    raise ValueError('no replay logs')
for path in paths:
    frames = collections.defaultdict(list)
    for line in path.open():
        if line.startswith('pair-data '):
            row = json.loads(line[10:])
            frames[row['action']].append(row)
    if len(frames) != 9:
        raise ValueError(f'incomplete actions: {path}')
    for seq in frames.values():
        for old, new in zip(seq, seq[1:]):
            a, b = old['enemies'], new['enemies']
            if new['frame'] != old['frame'] + 1 or len(a) != len(b):
                continue
            if any(x[5] != y[5] or math.hypot(x[0] - y[0], x[1] - y[1]) > 8 for x, y in zip(a, b)):
                continue
            transitions += 1
            newly = [i for i, (x, y) in enumerate(zip(a, b)) if x[5] >= 0 and not x[7] and y[7]]
            for i in range(len(a)):
                for j in range(i + 1, len(a)):
                    x, y = a[i], a[j]
                    if x[5] < 0 or y[5] < 0 or x[7] or y[7] or not (1 <= x[0] <= 128 and 1 <= y[0] <= 128):
                        continue
                    if any(overlaps(e, rect) for e in (b[i], b[j]) for rect in new['rects']):
                        continue
                    ni, nj = i in newly, j in newly
                    if ni != nj:
                        continue
                    if ni and any(k not in (i, j) and (math.hypot(a[k][0] - x[0], a[k][1] - x[1]) < 14 or math.hypot(a[k][0] - y[0], a[k][1] - y[1]) < 14) for k in newly):
                        continue
                    predicted, actual = probability(x, y) > 0.3, ni and nj
                    for h, c in counts.items():
                        if new['frame'] <= h:
                            c['tp' if predicted and actual else 'fp' if predicted else 'fn' if actual else 'tn'] += 1
print('stable transitions', transitions)
for h, c in counts.items():
    tp, fp, fn = c['tp'], c['fp'], c['fn']
    precision = f'{tp / (tp + fp):.3f}' if tp + fp else 'undefined'
    recall = f'{tp / (tp + fn):.3f}' if tp + fn else 'undefined'
    print(f'h={h}: precision={precision} recall={recall} tp/fp/fn/tn={tp}/{fp}/{fn}/{c["tn"]}')
