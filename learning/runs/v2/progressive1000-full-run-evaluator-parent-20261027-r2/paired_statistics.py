"""Fixed paired seed bootstrap; three training replicas remain descriptive."""
from __future__ import annotations
import math
import random
from bisect import bisect_left

KEYS=('Worst','Q1','Mean','Q4','Best')


def metrics(values):
    x=sorted(values);n=len(x);quarter=n//4
    if n<4 or n%4:raise ValueError('quarter-compatible sample required')
    return dict(Worst=x[0],Q1=sum(x[:quarter])/quarter,Mean=sum(x)/n,
                Q4=sum(x[-quarter:])/quarter,Best=x[-1])


def percentile(values,p):
    x=sorted(values);position=(len(x)-1)*p;lo=math.floor(position);hi=math.ceil(position)
    return x[lo]+(x[hi]-x[lo])*(position-lo)


def paired_intervals(policy_rows,contract):
    """Resample matched evaluation seeds, never treat training pairs as 7168 trials.

    The same bootstrap indices apply to every policy. Intervals condition on the
    three trained policy pairs and this one sampled-action realization. Extrema
    bootstrap intervals describe the empirical seed distribution, not unseen
    population bounds. No training-seed superiority inference is made.
    """
    ids=tuple(policy_rows);n=len(next(iter(policy_rows.values())))
    if n!=1024 or any(len(rows)!=n for rows in policy_rows.values()):raise ValueError('full cohort required')
    if contract!=dict(seed=2026102701,draws=2000,confidence=.95,unit='paired_evaluation_seed',
        training_seed_uncertainty='three_training_pairs_descriptive_only'):raise ValueError('unregistered bootstrap')
    values={name:[r['alive_frames'] for r in policy_rows[name]] for name in ids}
    pairs=[]
    for replica in (1,2,3):
        control=f'replica-{replica}-control_constant_3e-5'
        curriculum=f'replica-{replica}-progressive1000_curriculum_constant_3e-5'
        for label,left,right in [('curriculum_minus_control',curriculum,control),
            ('control_minus_parent',control,'parent324'),('curriculum_minus_parent',curriculum,'parent324')]:
            pairs.append((f'replica-{replica}-{label}',left,right))
    samples={label:{key:[] for key in KEYS} for label,_,_ in pairs}
    milestones={label:{str(h):[] for h in range(1000,18001,1000)} for label,_,_ in pairs}
    rng=random.Random(contract['seed'])
    for _ in range(contract['draws']):
        indices=[rng.randrange(n) for _ in range(n)]
        sampled={name:sorted(values[name][i] for i in indices) for name in ids}
        calculated={name:metrics(v) for name,v in sampled.items()}
        for label,left,right in pairs:
            for key in KEYS:samples[label][key].append(calculated[left][key]-calculated[right][key])
            for h in range(1000,18001,1000):
                milestones[label][str(h)].append((bisect_left(sampled[right],h)-bisect_left(sampled[left],h))/n)
    interval=lambda x:dict(low=percentile(x,.025),high=percentile(x,.975))
    return dict(schema='progressive1000_conditional_paired_seed_intervals_v1',contract=contract,
        comparisons={label:dict(performance={key:interval(x) for key,x in samples[label].items()},
            milestone_rate_differences={h:interval(x) for h,x in milestones[label].items()}) for label,_,_ in pairs},
        interpretation='Conditional evaluation-seed uncertainty only; three training pairs remain descriptive. '
            'Common global sampling seed does not imply per-seed common action draws after trajectories diverge. '
            'Extrema intervals are empirical-distribution bootstrap intervals, not population bounds.',
        method='paired percentile bootstrap; shared index draws across policies; linear-interpolated quantiles',
        automatic_selection=False,promoted=False)
