"""Summarize the first-hit fidelity probe's newline-delimited JSON output."""
import argparse
import gzip
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('data', type=Path)
    args = parser.parse_args()
    opener = gzip.open if args.data.suffix == ".gz" else open
    with opener(args.data, "rt") as f:
        rows = [json.loads(line) for line in f]
    groups = [('all', None), ('near wall', 'near_wall'), ('near rectangle', 'near_rectangle'),
              ('enemy contact', 'enemy_contact'), ('kamikaze near', 'kamikaze_near')]
    print('| Situation | Horizon | Cases | Engine hits | Model hits | Precision | Recall | First-hit MAE |')
    print('|---|---:|---:|---:|---:|---:|---:|---:|')
    for name, key in groups:
        selected = [r for r in rows if key is None or r[key]]
        for horizon in (4, 8, 12, 24, 36):
            actual = [r['engine_hit'] is not None and r['engine_hit'] <= horizon for r in selected]
            predicted = [r['model_hit'] is not None and r['model_hit'] <= horizon for r in selected]
            tp = sum(a and p for a, p in zip(actual, predicted))
            a_count, p_count = sum(actual), sum(predicted)
            errors = [abs(r['engine_hit'] - r['model_hit']) for r, a, p in zip(selected, actual, predicted) if a and p]
            fmt = lambda n, d: f'{n / d:.3f}' if d else '—'
            print(f'| {name} | {horizon} | {len(selected)} | {a_count} | {p_count} | {fmt(tp, p_count)} | {fmt(tp, a_count)} | {fmt(sum(errors), len(errors))} |')


if __name__ == '__main__':
    main()
