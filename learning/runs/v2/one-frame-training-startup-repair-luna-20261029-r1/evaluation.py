"""Paired seed-cluster summaries for the fixed six-condition DODGE-013 evaluation."""
from __future__ import annotations
import math
import random
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True, allow_nan=False).encode('ascii')).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def q1(values):
    ordered = sorted(values)
    require(len(ordered) >= 4 and len(ordered) % 4 == 0, 'Q1 requires a quarter-compatible complete cohort')
    n = len(ordered)//4
    return sum(ordered[:n])/n


def describe(rows, seeds):
    require(len(rows) == len(seeds), 'evaluation row count differs')
    by_seed = {}
    for row in rows:
        seed = row['seed']
        require(type(seed) is int and seed not in by_seed, 'duplicate or invalid evaluation seed')
        value = row['alive_frames']
        require(type(value) is int and value >= 0, 'invalid survival value')
        by_seed[seed] = value
    require(set(by_seed) == set(seeds), 'evaluation cohort differs')
    values = [by_seed[seed] for seed in seeds]
    ordered = sorted(values)
    n = len(values)//4
    return dict(episodes=len(values), Q1=sum(ordered[:n])/n, Worst=ordered[0],
                Mean=sum(values)/len(values), Q4=sum(ordered[-n:])/n, Best=ordered[-1])


def _percentile(values, p):
    ordered = sorted(values)
    pos = (len(ordered)-1)*p
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(pos-lo)


def analyze(groups, seeds, *, draws, seed):
    """All groups share one index vector per bootstrap draw, preserving D9 pairing."""
    expected = {
        'starting420_repeat1_sampled', 'starting420_repeat4_sampled',
        'repeat4_final_repeat1_sampled', 'repeat4_final_repeat4_sampled',
        'repeat1_final_repeat1_sampled', 'repeat1_final_repeat4_sampled'
    }
    require(set(groups) == expected and type(draws) is int and draws > 0,
            'fixed six-condition evaluation groups required')
    require(len(seeds) == 1024 and len(set(seeds)) == len(seeds), 'exact reserved D9 seed set required')
    descriptions = {name: describe(rows, seeds) for name, rows in groups.items()}
    by_seed = {name: {row['seed']: row['alive_frames'] for row in rows} for name, rows in groups.items()}
    rng = random.Random(seed)
    boot = {name: [] for name in (
        'primary_repeat1_final_minus_repeat4_final_repeat1',
        'repeat1_final_minus_starting420_repeat1',
        'repeat4_final_minus_starting420_repeat1',
        'repeat1_final_minus_starting420_repeat4',
        'repeat4_final_minus_starting420_repeat4'
    )}
    for _ in range(draws):
        sampled = [seeds[rng.randrange(len(seeds))] for _ in seeds]
        stats = {name: q1([by_seed[name][item] for item in sampled]) for name in expected}
        boot['primary_repeat1_final_minus_repeat4_final_repeat1'].append(
            stats['repeat1_final_repeat1_sampled']-stats['repeat4_final_repeat1_sampled'])
        boot['repeat1_final_minus_starting420_repeat1'].append(
            stats['repeat1_final_repeat1_sampled']-stats['starting420_repeat1_sampled'])
        boot['repeat4_final_minus_starting420_repeat1'].append(
            stats['repeat4_final_repeat1_sampled']-stats['starting420_repeat1_sampled'])
        boot['repeat1_final_minus_starting420_repeat4'].append(
            stats['repeat1_final_repeat4_sampled']-stats['starting420_repeat4_sampled'])
        boot['repeat4_final_minus_starting420_repeat4'].append(
            stats['repeat4_final_repeat4_sampled']-stats['starting420_repeat4_sampled'])
    contrasts = {}
    for name, values in boot.items():
        contrasts[name] = dict(observed=values[0] if draws == 1 else None,
                               low=_percentile(values, .025), median=_percentile(values, .5),
                               high=_percentile(values, .975), draws=draws)
    primary = contrasts['primary_repeat1_final_minus_repeat4_final_repeat1']
    primary['observed'] = (descriptions['repeat1_final_repeat1_sampled']['Q1']
                           - descriptions['repeat4_final_repeat1_sampled']['Q1'])
    primary['success'] = primary['observed'] > 0 and primary['low'] > 0
    for name, contrast, left, right in (
        ('repeat1_final_minus_starting420_repeat1', 'repeat1_final_minus_starting420_repeat1',
         'repeat1_final_repeat1_sampled', 'starting420_repeat1_sampled'),
        ('repeat4_final_minus_starting420_repeat1', 'repeat4_final_minus_starting420_repeat1',
         'repeat4_final_repeat1_sampled', 'starting420_repeat1_sampled'),
        ('repeat1_final_minus_starting420_repeat4', 'repeat1_final_minus_starting420_repeat4',
         'repeat1_final_repeat4_sampled', 'starting420_repeat4_sampled'),
        ('repeat4_final_minus_starting420_repeat4', 'repeat4_final_minus_starting420_repeat4',
         'repeat4_final_repeat4_sampled', 'starting420_repeat4_sampled')):
        contrasts[contrast]['observed'] = descriptions[left]['Q1']-descriptions[right]['Q1']
    return dict(schema='one_frame_training_comparison_paired_evaluation_v1',
        cohort='D9', seeds=seeds, groups=descriptions, contrasts=contrasts,
        bootstrap=dict(draws=draws, seed=seed, unit='shared D9 game-seed cluster',
                       paired_indices_shared_across_models_and_repeats=True),
        primary='repeat1_final minus repeat4_final Q1 under the same sampled repeat1 controller',
        primary_success=primary['success'], automatic_selection=False, promoted=False,
        training_eligible=False,
        interpretation='One paired training trajectory comparison on a frozen checkpoint family; no equal-compute or repeated-training-replica claim.')
