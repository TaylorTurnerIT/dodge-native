"""Recheck the existing finite future sample against expanded historical coverage."""
import json
from pathlib import Path

from close_history import independent_seed
import seed_controls as controls

HERE=Path(__file__).resolve().parent

def load(name):return json.loads((HERE/name).read_bytes())

def main():
    vectors=load('seed-vectors.json')
    previous=load('future-controls.json')
    merged=set(load('merged-conservative-seeds.json')['sorted_unique_seed_values'])
    observed=set(load('observed-seeds.json')['real_observed_sorted_unique_seeds'])
    observed.update(load('additional-observed-seeds.json')['new_sorted_unique_seed_values'])
    ranges=load('proposed-exclusions.json')['canonical_sorted_merged_union']
    reports=[]
    for vector,old in zip(vectors['vectors'],previous['replicas']):
        rows=[];hits=[]
        for slot,start in enumerate(vectors['parent']['next_episode_indices']):
            for episode in range(start,start+512):
                counter,seed=independent_seed(vector['seeds']['env_master_seed'],slot,episode,ranges)
                row=dict(slot=slot,episode=episode,counter=counter,actual_seed=seed,evaluation=False)
                rows.append(row)
                if seed in merged:
                    hits.append({**row,'observed_historical':seed in observed,'only_possible_or_envelope':seed not in observed})
        assert controls.digest(rows)==old['rows_canonical_sha256']
        assert not any(0xD3000000<=r['actual_seed']<=0xD30003FF for r in rows)
        reports.append({'replica':vector['replica'],'draws':len(rows),'rows_canonical_sha256':controls.digest(rows),'historical_value_intersections':hits})
    output={'entire_future_stream_covered':False,'draws':98304,'replicas':reports,'proposal_retained':True,
            'interpretation':'Historical training-value overlap is reported, not automatically forbidden. Cohort freshness and native six-range exclusions remain separate parent gates. Matched origins do not imply equal realized reset counts.'}
    (HERE/'future-merged-recheck.json').write_text(json.dumps(output,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'draws':98304,'historical_intersections':sum(len(r['historical_value_intersections']) for r in reports),'cohort_hits':0}))

if __name__=='__main__':main()
