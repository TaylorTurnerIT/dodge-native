"""Fixed paired evaluation-seed bootstrap; three training replicas remain descriptive."""
from __future__ import annotations
import math
import random
from bisect import bisect_left

import binding as b

KEYS = ('Worst', 'Q1', 'Mean', 'Q4', 'Best')
MEAN3 = 'mean_of_three_priority_minus_uniform'


def metrics(values):
    x = sorted(values); n = len(x); quarter = n//4
    if n < 4 or n % 4:
        raise ValueError('quarter-compatible sample required')
    return dict(Worst=x[0], Q1=sum(x[:quarter])/quarter, Mean=sum(x)/n,
                Q4=sum(x[-quarter:])/quarter, Best=x[-1])


def percentile(values, p):
    x = sorted(values); position = (len(x)-1)*p; lo = math.floor(position); hi = math.ceil(position)
    return x[lo]+(x[hi]-x[lo])*(position-lo)


def pair_labels():
    labels = []
    for replica in (1, 2, 3):
        uniform = f'replica-{replica}-uniform'; priority = f'replica-{replica}-opening_priority'
        labels += [(f'replica-{replica}-priority_minus_uniform', priority, uniform),
                   (f'replica-{replica}-uniform_minus_parent', uniform, b.PARENT_ID),
                   (f'replica-{replica}-priority_minus_parent', priority, b.PARENT_ID)]
    return labels


def paired_intervals(policy_rows, contract):
    """Resample matched evaluation seeds only; the same indices apply to every policy.

    Intervals condition on the three trained policy pairs and this one sampled-action
    realization. Seeds are not training replicates: no training-seed superiority
    inference is made. Extrema intervals describe the empirical seed distribution.
    """
    ids = tuple(policy_rows); n = len(next(iter(policy_rows.values())))
    if n != 1024 or any(len(rows) != n for rows in policy_rows.values()) or set(ids) != set(b.POLICIES):
        raise ValueError('full cohort for seven fixed policies required')
    if contract != b.BOOTSTRAP:
        raise ValueError('unregistered bootstrap')
    values = {name: [r['alive_frames'] for r in policy_rows[name]] for name in ids}
    pairs = pair_labels()
    names = [label for label, _, _ in pairs]+[MEAN3]
    samples = {label: {key: [] for key in KEYS} for label in names}
    milestones = {label: {str(h): [] for h in b.MILESTONES} for label in names}
    rng = random.Random(contract['seed'])
    for _ in range(contract['draws']):
        indices = [rng.randrange(n) for _ in range(n)]
        sampled = {name: sorted(values[name][i] for i in indices) for name in ids}
        calculated = {name: metrics(v) for name, v in sampled.items()}
        draw = {}
        for label, left, right in pairs:
            draw[label] = (
                {key: calculated[left][key]-calculated[right][key] for key in KEYS},
                {str(h): (bisect_left(sampled[right], h)-bisect_left(sampled[left], h))/n for h in b.MILESTONES})
        primary = [draw[f'replica-{r}-priority_minus_uniform'] for r in (1, 2, 3)]
        draw[MEAN3] = ({key: sum(p[0][key] for p in primary)/3 for key in KEYS},
                       {str(h): sum(p[1][str(h)] for p in primary)/3 for h in b.MILESTONES})
        for label, (performance, rates) in draw.items():
            for key in KEYS:
                samples[label][key].append(performance[key])
            for h in b.MILESTONES:
                milestones[label][str(h)].append(rates[str(h)])
    tail = (1-contract['confidence'])/2
    interval = lambda x: dict(low=percentile(x, tail), high=percentile(x, 1-tail))
    return dict(schema='fullgame_priority_d4_conditional_paired_seed_intervals_v1', contract=contract,
        comparisons={label: dict(role='primary_priority_minus_uniform' if 'priority_minus_uniform' in label
                                 else 'descriptive_parent_comparison' if 'parent' in label else 'descriptive',
            performance={key: interval(x) for key, x in samples[label].items()},
            milestone_rate_differences={h: interval(x) for h, x in milestones[label].items()}) for label in names},
        interpretation='Conditional evaluation-seed uncertainty only; three training pairs remain descriptive and '
            '1024 matched seeds are not 1024 independent training replicates. Common global sampling seed does not '
            'imply per-seed common action draws after trajectories diverge. Extrema intervals are empirical-distribution '
            'bootstrap intervals, not population bounds. D4 ranking is development evidence, not D5 confirmation.',
        method='paired percentile bootstrap; shared index draws across policies; linear-interpolated quantiles',
        automatic_selection=False, promoted=False)
