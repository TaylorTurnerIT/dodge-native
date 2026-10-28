"""Synthetic-only tests; never import Torch, native modules, or checkpoints."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import screen


def row(i,alive):
    dead=alive<18000; frames=alive+int(dead)
    cause='unknown' if dead else None
    contacts={k:0 for k in screen.DEATH_CAUSES[:-1]} if dead else None
    if dead: contacts['unknown']=1
    rawscore=65536*(i+1)
    return dict(episode_index=i,seed=100+i,score_raw_fixed=rawscore,score_delta_sum_raw_fixed=rawscore,
      alive_frames=alive,gameplay_frames=frames,startup_frames=13,raw_frames=frames+13,
      policy_decisions=frames,action_repeat=1,episode_latency_ns=1000,terminated=dead,truncated=not dead,
      death_cause=cause,fatal_gameplay_frame=frames if dead else None,
      death_observed_lethal_contacts=contacts,score=rawscore/65536,
      objective_return=rawscore/65536+alive/100-5*int(dead))


def test_exclusion_ranges_convert_to_native_tuples():
    values=[[1,2],[10,20]]
    converted=screen.normalize_excluded_ranges(values)
    assert converted==((1,2),(10,20)) and type(converted)is tuple and all(type(pair)is tuple for pair in converted)
    try:screen.normalize_excluded_ranges([[3,2]])
    except ValueError:pass
    else:raise AssertionError('reversed exclusion range accepted')


def test_summary():
    seeds=[100+i for i in range(8)]
    rows=[row(i,i*1000) for i in range(8)]
    summary=screen.summarize(rows,seeds)
    assert summary['performance']==dict(Worst=0,Q1=500,Mean=3500,Q4=6500,Best=7000)
    assert summary['milestones']['1000']==dict(numerator=7,denominator=8)
    assert summary['totals']['policy_decisions']==sum(r['policy_decisions'] for r in rows)


def test_bootstrap_shared_seed_clusters():
    n=8; vals=list(range(n))
    conditions={'sampled_r4':[vals,[v+10 for v in vals],[v+20 for v in vals]],
      'argmax_r4':[v+2 for v in vals], 'sampled_r1':[vals,[v+10 for v in vals],[v+20 for v in vals]],
      'argmax_r1':[v+4 for v in vals]}
    result=screen.bootstrap_clustered(conditions,list(range(n)),draws=16,seed=7)
    assert set(result)=={'argmax_minus_sampled_r4','argmax_minus_sampled_r1',
      'repeat1_minus_repeat4_sampled','repeat1_minus_repeat4_argmax','interaction'}
    assert result['argmax_minus_sampled_r4']['draws']==16
    assert abs(result['interaction']['low']-2)<1e-12 and abs(result['interaction']['high']-2)<1e-12


def test_rejects_reordered_seeds():
    rows=[row(0,0),row(1,1000)]
    try: screen.validate_rows(rows,[101,100])
    except ValueError as e: assert 'sorted' in str(e)
    else: raise AssertionError('reordered rows accepted')


def test_analyze_conditions():
    seeds=[100+i for i in range(8)]
    sampled4=[[row(i,i*1000+j*10) for i in range(8)] for j in range(3)]
    sampled1=[[row(i,i*1000+j*10) for i in range(8)] for j in range(3)]
    result=screen.analyze_conditions({'sampled_r4':sampled4,'argmax_r4':[row(i,i*1000+20) for i in range(8)],
      'sampled_r1':sampled1,'argmax_r1':[row(i,i*1000+40) for i in range(8)]},seeds,bootstrap_draws=8,bootstrap_seed=11)
    assert result['conditions']['sampled_r4']['pooled']['episodes']==24
    assert len(result['conditions']['sampled_r4']['sampler_repetitions'])==3
    assert result['automatic_selection'] is False and result['promoted'] is False


if __name__=='__main__':
    test_exclusion_ranges_convert_to_native_tuples();test_summary();test_bootstrap_shared_seed_clusters();test_rejects_reordered_seeds();test_analyze_conditions()
    print('synthetic screen tests passed')
