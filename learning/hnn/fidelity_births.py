"""Measure velocity of observed size-one explosions."""
import argparse
from collections import Counter
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('data', type=Path)
args = parser.parse_args()
velocities = Counter()
skipped = 0
with args.data.open() as source:
    for line in source:
        try:
            row = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        for enemy in row.get('ph', []):
            if enemy[5] == -1 and enemy[4] == 1:
                velocities[(enemy[2], enemy[3])] += 1
count = sum(velocities.values())
print(f'Size-one explosion observations: {count}; zero velocity: {velocities[(0, 0)]}; nonzero: {count - velocities[(0, 0)]}; malformed rows: {skipped}.')
