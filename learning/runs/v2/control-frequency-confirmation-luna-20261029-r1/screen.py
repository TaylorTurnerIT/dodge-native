"""Frozen-policy action-selection by control-frequency diagnostic core."""
from __future__ import annotations
import math
import random
import statistics

NEURAL_INPUTS = ('global_feats','entity_feats','entity_types','entity_mask')
CONDITIONS = ('sampled_r4', 'argmax_r4', 'sampled_r1', 'argmax_r1')
MILESTONES = tuple(range(1000, 18001, 1000))
DEATH_CAUSES = ('normal_enemy', 'kamikaze_enemy', 'kamikaze_explosion',
                'static_pattern_rect', 'moving_pattern_rect', 'unknown', 'unavailable')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_rows(rows, seeds, *, cap=18000):
    require(type(seeds) is list and len(seeds)>0 and all(type(s) is int and 0<=s<2**32 for s in seeds)
            and seeds==sorted(seeds) and len(set(seeds))==len(seeds), 'seed manifest must be sorted, unique uint32 values')
    require(type(rows) is list and len(rows) == len(seeds), 'row count must match ordered seed manifest')
    require([r.get('seed') for r in rows] == seeds, 'rows missing, reordered, duplicated, or outside manifest')
    for i, row in enumerate(rows):
        require(type(row) is dict, 'row must be an object')
        for key in ('episode_index','seed','score_raw_fixed','score_delta_sum_raw_fixed','alive_frames','gameplay_frames','startup_frames','raw_frames','policy_decisions','episode_latency_ns'):
            require(type(row.get(key)) is int and row[key] >= 0, f'{key} must be nonnegative integer')
        require(row['episode_index'] == i and row['startup_frames'] == 13, 'row identity/startup differs')
        require(row['score_delta_sum_raw_fixed'] == row['score_raw_fixed'], 'fixed score accumulation differs')
        require(row['alive_frames'] <= row['gameplay_frames'] <= cap, 'frame cap exceeded')
        require(type(row.get('action_repeat')) is int and row['action_repeat'] in (1,4)
                and row['policy_decisions']==math.ceil(row['gameplay_frames']/row['action_repeat']), 'decision/frame accounting differs')
        require(row['raw_frames'] == row['startup_frames'] + row['gameplay_frames'], 'raw frame accounting differs')
        require(type(row.get('terminated')) is bool and type(row.get('truncated')) is bool and row['terminated'] != row['truncated'], 'episode boundary flags invalid')
        if row['terminated']:
            require(row['alive_frames'] + 1 == row['gameplay_frames'], 'fatal-frame conservation differs')
            require(row.get('death_cause') in DEATH_CAUSES, 'death cause missing')
            contacts = row.get('death_observed_lethal_contacts')
            if row['death_cause'] == 'unavailable':
                require(row.get('fatal_gameplay_frame') is None and contacts is None, 'unavailable telemetry inferred')
            else:
                require(row.get('fatal_gameplay_frame') == row['gameplay_frames'] and type(contacts) is dict and set(contacts) == set(DEATH_CAUSES[:-1]) and all(type(v) is int and v >= 0 for v in contacts.values()), 'native death telemetry differs')
        else:
            require(row['gameplay_frames'] == row['alive_frames'] == cap and row.get('death_cause') is None
                    and row.get('fatal_gameplay_frame') is None and row.get('death_observed_lethal_contacts') is None, 'truncation differs')
        require(type(row.get('score')) in (int,float) and math.isfinite(row['score']) and row['score'] == row['score_raw_fixed']/65536, 'score identity differs')
        expected = row['score_raw_fixed']/65536 + row['alive_frames']/100 - 5*row['terminated']
        require(type(row.get('objective_return')) in (int,float) and math.isfinite(row['objective_return']) and math.isclose(row['objective_return'],expected,rel_tol=0,abs_tol=1e-9), 'objective identity differs')
    return rows


def metrics(values):
    x = sorted(values); n=len(x); q=n//4
    require(n >= 4 and n % 4 == 0, 'quarter-compatible cohort required')
    return dict(Worst=x[0], Q1=sum(x[:q])/q, Mean=sum(x)/n, Q4=sum(x[-q:])/q, Best=x[-1])


def summarize(rows, seeds):
    validate_rows(rows,seeds)
    alive=[r['alive_frames'] for r in rows]
    return dict(complete=True, episodes=len(rows), performance=metrics(alive),
        milestones={str(h):dict(numerator=sum(v>=h for v in alive),denominator=len(rows)) for h in MILESTONES},
        death_causes={cause:sum(r['terminated'] and r['death_cause']==cause for r in rows) for cause in DEATH_CAUSES},
        caps=sum(r['truncated'] for r in rows),
        totals=dict(raw_frames=sum(r['raw_frames'] for r in rows), policy_decisions=sum(r['policy_decisions'] for r in rows), sum_episode_latency_ns=sum(r['episode_latency_ns'] for r in rows)))


def normalize_excluded_ranges(excluded_ranges):
    require(type(excluded_ranges) is list and all(type(pair)is list and len(pair)==2 and all(type(x)is int and 0<=x<2**32 for x in pair) and pair[0]<=pair[1] for pair in excluded_ranges),'exclusion ranges must be inclusive uint32 pairs')
    return tuple(tuple(pair) for pair in excluded_ranges)


def _production_rows(model, env_factory, observation_keys, death_fields, seeds, excluded_ranges, guard,
                     *, action_repeat, action_mode, batch_size=64, event_sink=None):
    """Production loop; caller authenticates model, runtime, RNG seed and authorization."""
    import numpy as np
    import torch
    require(action_repeat in (1,4) and action_mode in ('sampled_categorical','argmax'), 'unregistered condition')
    excluded_ranges=normalize_excluded_ranges(excluded_ranges)
    rows=[]
    for offset in range(0,len(seeds),batch_size):
        chunk=seeds[offset:offset+batch_size]; envs={}; obs={}; completed={}; started={}; decisions={}; gameplay={}
        for local,seed in enumerate(chunk):
            guard(); env=env_factory(batch_size=1,action_repeat=action_repeat,difficulty=2,patterns_enabled=True,
                powerups_enabled=True,raw_frame_cap=18000,num_threads=1,chunk_size=1,render_pixels=False,
                auxiliary_targets=False,seeds_by_slot=[[seed]],excluded_seed_ranges=excluded_ranges)
            info=env.episode_info()[0]
            require(info['seed']['evaluation'] is True and info['seed']['actual_seed']==seed and info['startup_frames']==13 and info['gameplay_frames']==0, 'constructor seed/startup differs')
            if event_sink: event_sink(dict(kind='constructor',episode_index=offset+local,info=info))
            envs[local]=env;obs[local]=env.observations();started[local]=__import__('time').monotonic_ns();decisions[local]=0;gameplay[local]=0
        while envs:
            guard(); active=sorted(envs)
            tensors={name:torch.from_numpy(np.concatenate([obs[i][name] for i in active],axis=0)).to(model._expanded_eval_device) for name in observation_keys}
            with torch.no_grad(): output=model(*(tensors[name] for name in observation_keys))
            logits=output.logits
            require(tuple(logits.shape)==(len(envs),9) and bool(torch.isfinite(logits).all()),'nonfinite or malformed policy output')
            actions=(torch.distributions.Categorical(logits=logits).sample() if action_mode=='sampled_categorical' else torch.argmax(logits,dim=-1)).cpu().numpy()
            del tensors,output,logits
            for pos,i in enumerate(active):
                guard();decisions[i]+=1;result=envs[i].step(np.array([actions[pos]],dtype=np.int64));info=result['info'][0];gameplay[i]+=int(result['elapsed_raw_frames'][0])
                if event_sink: event_sink(dict(kind='step',episode_index=offset+i,elapsed_raw_frames=int(result['elapsed_raw_frames'][0]),info=info))
                terminated,truncated=bool(result['terminated'][0]),bool(result['truncated'][0])
                require(info['seed']['actual_seed']==chunk[i] and not(terminated and truncated) and info['bootstrap']==(not terminated),'seed/boundary differs')
                require(info['score_raw_fixed']==info['score_delta_sum_raw_fixed'],'score accounting differs')
                if terminated or truncated:
                    frame_count=int(info['gameplay_frames']); raw=frame_count+int(info['startup_frames'])
                    row=dict(episode_index=offset+i,seed=chunk[i],score_raw_fixed=info['score_raw_fixed'],score=info['score_raw_fixed']/65536,
                        alive_frames=info['alive_frames'],gameplay_frames=frame_count,startup_frames=info['startup_frames'],raw_frames=raw,action_repeat=action_repeat,
                        score_delta_sum_raw_fixed=info['score_delta_sum_raw_fixed'],objective_return=info['objective_return'],
                        terminated=terminated,truncated=truncated,policy_decisions=decisions[i],episode_latency_ns=__import__('time').monotonic_ns()-started[i],**death_fields(info,terminated,truncated))
                    completed[i]=row
                    if event_sink:event_sink(dict(kind='completed',row=row))
                    del envs[i],obs[i]
                else: obs[i]=result['observations']
            guard()
        rows.extend(completed[i] for i in range(len(chunk)))
    return rows


def bootstrap_clustered(conditions, seeds, *, draws, seed):
    """Resample seed clusters; all three sampler reps stay together per sampled seed."""
    rng=random.Random(seed); n=len(seeds)
    require(n>0 and draws>0,'bootstrap contract invalid')
    conditions_set=set(conditions)
    require(conditions_set==set(CONDITIONS),'all four conditions required')
    for key in ('sampled_r4','sampled_r1'):
        reps=conditions[key]
        require(type(reps) is list and len(reps)==3 and all(type(x) is list and len(x)==n for x in reps), 'three full sampler repetitions required')
    require(all(type(conditions[c]) is list and len(conditions[c])==n for c in ('argmax_r4','argmax_r1')), 'argmax cohort dimensions differ')
    # Keep one shared cluster index vector across all conditions. Each sampled seed
    # contributes all three sampled policy repetitions to the per-seed aggregate.
    contrast_names=('argmax_minus_sampled_r4','argmax_minus_sampled_r1','repeat1_minus_repeat4_sampled','repeat1_minus_repeat4_argmax','interaction')
    values={name:[] for name in contrast_names}
    def pooled(c,idx):
        arr=conditions[c]
        if c.startswith('argmax'): return [arr[i] for i in idx]
        return [arr[rep][i] for i in idx for rep in range(3)]
    def q1(v): return metrics(v)['Q1']
    for _ in range(draws):
        idx=[rng.randrange(n) for _ in range(n)]
        a4=q1(pooled('argmax_r4',idx));s4=q1(pooled('sampled_r4',idx))
        a1=q1(pooled('argmax_r1',idx));s1=q1(pooled('sampled_r1',idx))
        values['argmax_minus_sampled_r4'].append(a4-s4);values['argmax_minus_sampled_r1'].append(a1-s1)
        values['repeat1_minus_repeat4_sampled'].append(s1-s4);values['repeat1_minus_repeat4_argmax'].append(a1-a4)
        values['interaction'].append((a1-s1)-(a4-s4))
    def percentile(xs,p):
        xs=sorted(xs);pos=(len(xs)-1)*p;lo=math.floor(pos);hi=math.ceil(pos);return xs[lo]+(xs[hi]-xs[lo])*(pos-lo)
    return {k:dict(low=percentile(v,.025),median=percentile(v,.5),high=percentile(v,.975),draws=draws) for k,v in values.items()}


def analyze_conditions(row_conditions, seeds, *, bootstrap_draws, bootstrap_seed):
    """Build descriptive endpoint summaries and preregistered factorial contrasts."""
    require(set(row_conditions)==set(CONDITIONS), 'exact four registered conditions required')
    for key in ('sampled_r4','sampled_r1'):
        require(type(row_conditions[key]) is list and len(row_conditions[key])==3, 'three sampler repetitions required')
        for rep in row_conditions[key]: validate_rows(rep,seeds)
    for key in ('argmax_r4','argmax_r1'): validate_rows(row_conditions[key],seeds)
    endpoint={};values={}
    for key in CONDITIONS:
        if key.startswith('sampled'):
            reps=row_conditions[key]
            endpoint[key]=dict(pooled=_summarize_validated([r for rep in reps for r in rep]),
                sampler_repetitions=[summarize(rep,seeds) for rep in reps])
            values[key]=[[r['alive_frames'] for r in rep] for rep in reps]
        else:
            endpoint[key]=summarize(row_conditions[key],seeds)
            values[key]=[r['alive_frames'] for r in row_conditions[key]]
    boot=bootstrap_clustered(values,seeds,draws=bootstrap_draws,seed=bootstrap_seed)
    perf={key:(endpoint[key]['pooled']['performance'] if key.startswith('sampled') else endpoint[key]['performance']) for key in CONDITIONS}
    contrasts={}
    pairs=(('argmax_minus_sampled_r4','argmax_r4','sampled_r4'),
           ('argmax_minus_sampled_r1','argmax_r1','sampled_r1'),
           ('repeat1_minus_repeat4_sampled','sampled_r1','sampled_r4'),
           ('repeat1_minus_repeat4_argmax','argmax_r1','argmax_r4'))
    for name,left,right in pairs:
        contrasts[name]=dict(metric_differences={metric:perf[left][metric]-perf[right][metric] for metric in ('Worst','Q1','Mean','Q4','Best')},
            q1_cluster_bootstrap_95=boot[name])
    contrasts['selector_by_repeat_interaction']=dict(q1_difference_in_differences=contrasts['argmax_minus_sampled_r1']['metric_differences']['Q1']-contrasts['argmax_minus_sampled_r4']['metric_differences']['Q1'],
        q1_cluster_bootstrap_95=boot['interaction'])
    return dict(schema='frozen_policy_control_frequency_confirmation_v1',complete=True,conditions=endpoint,
        contrasts=contrasts,bootstrap=dict(seed=bootstrap_seed,draws=bootstrap_draws,unit='shared_game_seed_cluster',sampled_repetitions_kept_within_seed=True,results=boot),
        action_semantics=dict(argmax='torch.argmax(logits, dim=-1); lowest action index wins ties',sampled='Categorical(logits=logits), global MPS RNG seeded once per registered group'),
        automatic_selection=False,promoted=False,training_eligible=False,
        interpretation='Development diagnostic on one frozen policy and one fresh game-seed cohort; sampled policy repetitions are controller randomness, not training replicas.')


def _summarize_validated(rows):
    alive=[r['alive_frames'] for r in rows]
    return dict(complete=True,episodes=len(rows),performance=metrics(alive),
        milestones={str(h):dict(numerator=sum(v>=h for v in alive),denominator=len(rows)) for h in MILESTONES},
        death_causes={cause:sum(r['terminated'] and r['death_cause']==cause for r in rows) for cause in DEATH_CAUSES},
        caps=sum(r['truncated'] for r in rows),
        totals=dict(raw_frames=sum(r['raw_frames'] for r in rows),policy_decisions=sum(r['policy_decisions'] for r in rows),sum_episode_latency_ns=sum(r['episode_latency_ns'] for r in rows)))
