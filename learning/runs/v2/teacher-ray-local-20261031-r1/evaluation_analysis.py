"""Fixed terminal marginal-quartile contrasts; no endpoint selection."""


def analyze(rows, settings, guard=lambda:None):
    import numpy as np
    from evaluate_worker import summary

    grouped={}
    for row in rows:
        grouped.setdefault((row['model'],row['condition']),[]).append(row)
    expected={(g['model'],g['condition']):g['count'] for g in settings['groups']}
    if set(grouped)!=set(expected):raise ValueError('Evaluation group set differs')
    groups=[]
    for key,count in expected.items():
        data=sorted(grouped[key],key=lambda r:r['seed'])
        lo=settings['range_inclusive'][0]
        if len(data)!=count or [r['seed'] for r in data]!=list(range(lo,lo+count)):
            raise ValueError('Group seed/count differs')
        grouped[key]=data
        values=[r['alive_frames'] for r in data]
        groups.append(dict(model=key[0],condition=key[1],games=count,**summary(values),
            milestones={str(t):sum(v>=t for v in values) for t in settings['milestones']},
            early_deaths=sum(r['terminated'] and r['alive_frames']<=settings['early_death_max_frames'] for r in data)))
    rng=np.random.default_rng(settings['bootstrap_seed'])
    # A draw is shared across all comparisons of the same seed count.
    draws={n:rng.integers(0,n,size=(settings['bootstrap_draws'],n)) for n in (256,1024)}

    def contrast(left,right,label):
        a=np.array([r['alive_frames'] for r in left],dtype=np.float64)
        b=np.array([r['alive_frames'] for r in right],dtype=np.float64)
        if [r['seed'] for r in left]!=[r['seed'] for r in right]:raise ValueError('Paired seeds differ')
        n=len(a);q=n//4;contrasts={k:[] for k in ('Q1','Mean','Q4')}
        for indices in draws[n]:
            guard();aa=np.sort(a[indices]);bb=np.sort(b[indices])
            contrasts['Q1'].append(float(aa[:q].mean()-bb[:q].mean()))
            contrasts['Mean'].append(float(aa.mean()-bb.mean()))
            contrasts['Q4'].append(float(aa[-q:].mean()-bb[-q:].mean()))
        sa,sb=summary(a.tolist()),summary(b.tolist())
        return dict(comparison=label,games=n,draws=settings['bootstrap_draws'],
            difference={k:sa[k]-sb[k] for k in contrasts},
            percentile95={k:np.percentile(v,[2.5,97.5]).tolist() for k,v in contrasts.items()})
    results=[]
    for replica in (1,2):
        results.append(contrast(grouped[(f'r{replica}-rays','clean')],grouped[(f'r{replica}-control','clean')],f'replica{replica}:rays-minus-control'))
    for model in settings['models']:
        for condition in settings['conditions'][1:]:
            results.append(contrast(grouped[(model,condition)],grouped[(model,'clean')][:256],model+':'+condition+'-minus-clean'))
    return dict(groups=groups,contrasts=results,training_replica_uncertainty_estimated=False,
        interpretation='Fixed terminal endpoints; game-seed uncertainty only, replicas separate, no promotion or selection.')
