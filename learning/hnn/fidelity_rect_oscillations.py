"""Count repeated rectangle size reversals in observed consecutive frames."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('data', type=Path)
    args = parser.parse_args()
    history = {}
    transitions = reversals = continued = malformed = 0
    with args.data.open() as source:
        for line in source:
            try:
                row = json.loads(line)
            except ValueError:
                malformed += 1
                continue
            if 'rs' not in row or 'r' not in row:
                continue
            previous = history.get(row['s'], [])
            history[row['s']] = (previous + [row])[-4:]
            if len(previous) < 3:
                continue
            a, b, c = previous[-3:]
            if [a['f'] + 1, b['f'] + 1, c['f'] + 1] != [b['f'], c['f'], row['f']]:
                continue
            if not len(a['r']) == len(b['r']) == len(c['r']) == len(row['r']):
                continue
            for w, x, y, z in zip(a['r'], b['r'], c['r'], row['r']):
                for axis in (2, 3):
                    first, second, third = x[axis] - w[axis], y[axis] - x[axis], z[axis] - y[axis]
                    if abs(first) > 0.05 and abs(first + second) < 0.001:
                        reversals += 1
                        continued += abs(third - first) < 0.001
                    transitions += 1
    print(f'axis transitions={transitions} reversals={reversals} continued={continued} malformed={malformed}')


if __name__ == '__main__':
    main()
