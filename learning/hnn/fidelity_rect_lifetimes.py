"""Measure complete static-rectangle lethal plateaus from consecutive observed frames."""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('data', type=Path)
    args = parser.parse_args()
    active = {}
    durations = []
    malformed = 0
    digest = hashlib.sha256()
    with args.data.open('rb') as handle:
        for raw in handle:
            digest.update(raw)
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if 'rs' not in row or 'r' not in row:
                continue
            seed, frame = row['s'], row['f']
            for i, (state, box) in enumerate(zip(row['rs'], row['r'])):
                if state[1] != 0:
                    continue
                key = (seed, i, *(round(v, 3) for v in box[:4]))
                previous = active.get(key)
                plateau = state[0] >= 1.999
                if previous is None or previous[0] + 1 != frame:
                    active[key] = (frame, plateau, 0, False)
                    continue
                _, was_plateau, length, complete_start = previous
                if plateau:
                    length = length + 1 if was_plateau else 1
                    active[key] = (frame, True, length, complete_start if was_plateau else True)
                else:
                    if was_plateau and complete_start:
                        durations.append(length)
                    active[key] = (frame, False, 0, False)
    residual = [r for duration in durations for r in range(duration)]
    print('input SHA-256:', digest.hexdigest())
    print('malformed rows skipped:', malformed)
    print('complete plateaus:', len(durations))
    print('plateau lengths:', dict(sorted(collections.Counter(durations).items())))
    if residual:
        residual.sort()
        print('observed plateau-frame residual p50/p90/max:', residual[(len(residual)-1)//2], residual[int(.9*(len(residual)-1))], residual[-1])


if __name__ == '__main__':
    main()
