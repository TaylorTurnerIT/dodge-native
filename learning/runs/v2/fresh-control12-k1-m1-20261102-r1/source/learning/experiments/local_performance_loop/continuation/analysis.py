"""Deterministic descriptive paired uncertainty on reused development games."""
def compare(rows, reference, np):
    left=sorted(rows,key=lambda r:r['seed']);right=sorted(reference,key=lambda r:r['seed'])
    if [r['seed'] for r in left] != [r['seed'] for r in right]:raise ValueError('Paired seed coverage differs')
    a=np.array([r['alive_frames'] for r in left],dtype=np.float64)
    b=np.array([r['alive_frames'] for r in right],dtype=np.float64)
    n=len(a)
    if n!=512:raise ValueError('Fixed512 panel required')
    random=np.random.default_rng(20261102)
    indices=random.integers(0,n,size=(1000,n))
    aa=a[indices];bb=b[indices]
    means=(aa-bb).mean(axis=1)
    quarters=np.partition(aa,n//4-1,axis=1)[:,:n//4].mean(axis=1)-np.partition(bb,n//4-1,axis=1)[:,:n//4].mean(axis=1)
    return dict(games=n,mean_difference_frames=float((a-b).mean()),
        Q1_difference_frames=float(np.sort(a)[:n//4].mean()-np.sort(b)[:n//4].mean()),
        mean_paired_bootstrap95_frames=[float(x) for x in np.quantile(means,[.025,.975])],
        Q1_paired_bootstrap95_frames=[float(x) for x in np.quantile(quarters,[.025,.975])],
        bootstrap_resamples=1000,analysis_seed=20261102,development_selection=True,
        limits='Descriptive paired seed uncertainty after repeated development selection; no training-replica or fresh-confirmation claim. Not a selection/significance gate.')
