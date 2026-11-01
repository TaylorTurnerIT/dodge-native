"""Paired development-seed uncertainty, never checkpoint selection."""
import math


def summary(values):
    values=sorted(values); n=len(values)
    if n==0 or n%4: raise ValueError('Whole nonempty quartiles required')
    return dict(Worst=values[0],Q1=sum(values[:n//4])/(n//4),Mean=sum(values)/n,
                Q4=sum(values[-n//4:])/(n//4),Best=values[-1])


def validate_rows(rows,reg):
    expected={(m['name'],s) for m in reg['models'] for s in reg['seeds']}
    seen=set()
    for row in rows:
        key=(row['model'],row['seed'])
        if key not in expected or key in seen: raise ValueError('Unexpected/duplicate game')
        seen.add(key)
        n=row['gameplay_frames'];term=row['terminated'];trunc=row['truncated']
        if (type(term) is not bool or type(trunc) is not bool or term==trunc
            or type(n) is not int or not 1<=n<=18000 or row['decisions']!=n
            or row['alive_frames']!=n-int(term) or (trunc and n!=18000)
            or row['condition']!='clean' or row['action_repeat']!=1
            or row['startup_frames']!=13 or row['checkpoint_sha256']!=next(m['sha256'] for m in reg['models'] if m['name']==row['model'])):
            raise ValueError('Terminal game identity differs')
    if seen!=expected: raise ValueError('Missing declared games')
    return sum(r['gameplay_frames'] for r in rows)


def analyze(rows,reg,guard=lambda:None):
    import numpy as np
    validate_rows(rows,reg)
    grouped={m['name']:sorted((r for r in rows if r['model']==m['name']),key=lambda r:r['seed']) for m in reg['models']}
    n=len(reg['seeds']);q=n//4
    draws=np.random.default_rng(reg['bootstrap_seed']).integers(0,n,size=(reg['bootstrap_draws'],n))
    groups=[]
    for name,data in grouped.items():
        v=[r['alive_frames'] for r in data]
        groups.append(dict(model=name,games=n,**summary(v),early_deaths=sum(r['terminated'] and r['alive_frames']<=600 for r in data),
            early_death_max_frames=600,capped=sum(r['truncated'] for r in data),
            mean_survival_seconds=sum(v)/n/60))
    contrasts=[]
    for left,right in [('r1-rays','r1-control'),('r2-rays','r2-control')]+[(m['name'],'420') for m in reg['models'] if m['name']!='420']:
        a=np.array([r['alive_frames'] for r in grouped[left]],dtype=np.float64)
        b=np.array([r['alive_frames'] for r in grouped[right]],dtype=np.float64)
        sa,sb=summary(a.tolist()),summary(b.tolist());samples={k:[] for k in ('Mean','Q1')}
        for ix in draws:
            guard();aa=np.sort(a[ix]);bb=np.sort(b[ix])
            samples['Mean'].append(float(aa.mean()-bb.mean()))
            samples['Q1'].append(float(aa[:q].mean()-bb[:q].mean()))
        contrasts.append(dict(comparison=left+'-minus-'+right,paired_game_seeds=n,
            difference_frames={k:sa[k]-sb[k] for k in samples},
            percentile95_frames={k:np.percentile(v,[2.5,97.5]).tolist() for k,v in samples.items()}))
    return dict(groups=groups,contrasts=contrasts,bootstrap_draws=reg['bootstrap_draws'],
        interpretation='Exploratory consumed development seeds; conditional game-seed intervals only. Two training replicas do not establish general superiority. No selection or promotion.',
        noise_evaluated=False,training_replica_uncertainty_estimated=False)


def forecast(elapsed,batches,remaining_batches,reserve=240):
    if not batches or any(b['rounds']<=0 or b['frames']<=0 for b in batches): raise ValueError('Real counted prefix required')
    # Max full-path observed round cost covers shrinking-batch tails, load,
    # construction, native stepping, CPU geometry, MPS, sampling and durable IO.
    rate=max(max(b['max_window_seconds_per_round'],b['wall_seconds']/b['rounds']) for b in batches)
    return elapsed+1.2*rate*18000*remaining_batches+reserve
