"""Summarize the stratified fidelity probe, including identity-matched snapshots."""
import argparse
import gzip
import json
import math
from pathlib import Path

HORIZONS = (4, 8, 12, 24, 36)


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    return values[math.ceil(q * len(values)) - 1]


def number(value):
    return '—' if value is None else f'{value:.3f}'


def mean(values):
    return sum(values) / len(values) if values else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('data', type=Path)
    args = parser.parse_args()
    opener = gzip.open if args.data.suffix == '.gz' else open
    with opener(args.data, 'rt') as f:
        rows = [json.loads(line) for line in f]
    states = {(r['difficulty'], r['seed'], r['frame']): r for r in rows}
    speeds = [r['speed'] for r in states.values()]
    cuts = [percentile(speeds, q) for q in (0.25, 0.5, 0.75)]
    if not states:
        raise SystemExit('No states')
    groups = [('all', lambda r: True), ('near wall', lambda r: r['near_wall']),
              ('near rectangle', lambda r: r['near_rectangle']),
              ('enemy contact', lambda r: r['enemy_contact']),
              ('kamikaze near', lambda r: r['kamikaze_near']),
              ('pre-death', lambda r: r['pre_death'])]
    def speed_bin(r):
        return sum(r['speed'] > cut for cut in cuts)
    groups.extend((f'speed {i + 1}', lambda r, i=i: speed_bin(r) == i) for i in range(4))
    print(f"States: {len(states)}. Speed bin cut points: {', '.join(number(c) for c in cuts)}.")
    print('Situation labels overlap. Speed bins use state-weighted quartiles. A dash means no observations.')
    print('\n| Situation | Horizon | Cases | Engine hits | Model hits | Precision | Recall | Hit MAE |')
    print('|---|---:|---:|---:|---:|---:|---:|---:|')
    for name, select in groups:
        selected = [r for r in rows if select(r)]
        for h in HORIZONS:
            positives = [(r['engine_hit'] is not None and r['engine_hit'] <= h,
                          r['model_hit'] is not None and r['model_hit'] <= h) for r in selected]
            true = sum(a for a, _ in positives)
            predicted = sum(p for _, p in positives)
            tp = sum(a and p for a, p in positives)
            errors = [abs(r['engine_hit'] - r['model_hit']) for r, (a, p) in zip(selected, positives) if a and p]
            print(f'| {name} | {h} | {len(selected)} | {true} | {predicted} | '
                  f'{number(tp / predicted if predicted else None)} | {number(tp / true if true else None)} | {number(mean(errors))} |')
    print('\nSnapshots exclude cases where either rollout has already hit. Positions match initial enemies by engine birth identity.')
    print('\n| Situation | Horizon | Snapshots | Matched enemies | Position p50 | p95 | max | Mean absolute count error | Blast sizes | Blast size MAE |')
    print('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    for name, select in groups:
        selected = [r for r in rows if select(r)]
        for h in HORIZONS:
            snapshots = [s for r in selected for s in r['snapshots'] if s['horizon'] == h]
            pos = [x for s in snapshots for x in s['position_errors']]
            blast = [x for s in snapshots for x in s['explosion_size_errors']]
            counts = [abs(s['engine_count'] - s['model_count']) for s in snapshots]
            print(f'| {name} | {h} | {len(snapshots)} | {len(pos)} | {number(percentile(pos, .5))} | '
                  f'{number(percentile(pos, .95))} | {number(max(pos) if pos else None)} | '
                  f'{number(mean(counts))} | {len(blast)} | {number(mean(blast))} |')


    if any('rect_errors' in snap for row in rows for snap in row['snapshots']):
        print('\nRectangle boxes are paired by order only when initial, engine, and model counts match. '
              'A same-count pattern replacement may be paired incorrectly.')
        print('\n| Situation | Horizon | Snapshots | Count mismatch | Paired boxes | Box error p50 | p95 | max | Lethal disagreements |')
        print('|---|---:|---:|---:|---:|---:|---:|---:|---:|')
        for name, select in groups:
            selected = [r for r in rows if select(r)]
            for h in HORIZONS:
                snapshots = [s for r in selected for s in r['snapshots'] if s['horizon'] == h]
                errors = [e for s in snapshots for e in s['rect_errors']]
                mismatches = sum(s['engine_rect_count'] != s['model_rect_count'] for s in snapshots)
                disagreements = sum(s['rect_lethal_disagreements'] for s in snapshots)
                print(f'| {name} | {h} | {len(snapshots)} | {mismatches} | {len(errors)} | '
                      f'{number(percentile(errors, .5))} | {number(percentile(errors, .95))} | '
                      f'{number(max(errors) if errors else None)} | {disagreements} |')


    if any('engine_spawn_survivors' in snap for row in rows for snap in row['snapshots']):
        print('\nMean signed count components per snapshot. Initial-only differences have an unknown removal cause.')
        print('\n| Situation | Horizon | Snapshots | Engine spawn survivors | Engine new explosions | Model new explosions | Engine-only initial | Model-only initial |')
        print('|---|---:|---:|---:|---:|---:|---:|---:|')
        keys = ('engine_spawn_survivors', 'engine_new_explosions', 'model_new', 'engine_only_initial', 'model_only_initial')
        for name, select in groups:
            selected = [r for r in rows if select(r)]
            for h in HORIZONS:
                snapshots = [s for r in selected for s in r['snapshots'] if s['horizon'] == h]
                for s in snapshots:
                    assert s['engine_count'] - s['model_count'] == (s[keys[0]] + s[keys[1]] - s[keys[2]] + s[keys[3]] - s[keys[4]])
                values = ' | '.join(number(mean([s[key] for s in snapshots])) for key in keys)
                print(f'| {name} | {h} | {len(snapshots)} | {values} |')


if __name__ == '__main__':
    main()
