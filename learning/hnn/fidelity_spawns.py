"""Measure candidate spawn hazards from consecutive observed trajectory frames."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('data', type=Path)
    parser.add_argument('model', type=Path)
    args = parser.parse_args()
    points = json.loads(args.model.read_text())['spawn']['points']
    last = {}
    since = {}
    exposures = Counter()
    births = Counter()
    point_births = Counter()
    kinds = Counter()
    sizes = Counter()
    velocities = []
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
            seed = row['s']
            prev = last.get(seed)
            last[seed] = row
            if prev is None or row['f'] != prev['f'] + 1:
                since.pop(seed, None)
                continue
            age = since.get(seed)
            age_bin = 'unknown' if age is None else ('0-9' if age < 10 else '10-24' if age < 25 else '25-49' if age < 50 else '50+')
            enemy_count = sum(e[5] >= 0 for e in prev['ph'])
            count_bin = '0-4' if enemy_count < 5 else '5-9' if enemy_count < 10 else '10+'
            rects = len(prev.get('r') or [])
            key = (str(rects), age_bin, count_bin)
            exposures[key] += 1
            found = []
            for enemy in row['ph']:
                if enemy[5] < 0:
                    continue
                ds = [math.hypot(enemy[0] - p['x'], enemy[1] - p['y']) for p in points]
                nearest = min(range(len(ds)), key=ds.__getitem__)
                if ds[nearest] > 1.0:
                    continue
                if any(old[5] == enemy[5] and math.hypot(old[0] - enemy[0], old[1] - enemy[1]) < 2.0 for old in prev['ph']):
                    continue
                found.append((nearest, enemy))
            if found:
                births[key] += 1
                since[seed] = 0
                for point, enemy in found:
                    point_births[point] += 1
                    kinds[int(enemy[5])] += 1
                    sizes[round(enemy[4], 3)] += 1
                    velocities.append(math.hypot(enemy[2], enemy[3]))
            elif age is not None:
                since[seed] = age + 1
    print(f'Consecutive frame pairs: {sum(exposures.values())}; event frames: {sum(births.values())}; candidate births: {sum(point_births.values())}; malformed rows: {skipped}.')
    print(f'Candidate birth kinds: {dict(sorted(kinds.items()))}; sizes: {dict(sorted(sizes.items()))}.')
    if velocities:
        velocities.sort()
        print(f'Candidate birth velocity magnitude min/median/max: {velocities[0]:.5f}/{velocities[len(velocities)//2]:.5f}/{velocities[-1]:.5f}.')
    print('\n| Spawn point | Candidate births |\n|---|---:|')
    for i, p in enumerate(points):
        print(f"| ({p['x']:.2f}, {p['y']:.2f}) | {point_births[i]} |")
    print('\n| Rectangles | Frames since candidate birth | Enemies | Frames | Event frames | Hazard |\n|---:|---|---|---:|---:|---:|')
    for key, n in sorted(exposures.items()):
        print(f'| {key[0]} | {key[1]} | {key[2]} | {n} | {births[key]} | {births[key] / n:.5f} |')


if __name__ == '__main__':
    main()
