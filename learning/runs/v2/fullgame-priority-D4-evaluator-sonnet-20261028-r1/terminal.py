"""Complete D4 terminal60 receipts and returned-native-cost conservation; stdlib only."""
from __future__ import annotations
import json
from pathlib import Path
import binding as b
import comparison


def rows(path,*,strict=False):
    if not Path(path).is_file():return
    with Path(path).open() as stream:
        for line in stream:
            if not line.endswith('\n'):
                b.need(not strict,'torn evaluation journal');break
            yield json.loads(line)


def accounting(out,worker,*,strict=False,include_rows=False):
    cost=constructors=completed=steps=0;episodes={}
    for event in rows(Path(out)/'evaluation-events.jsonl',strict=strict):
        kind=event['kind'];policy=event['policy_id'];b.need(policy in b.POLICIES,'unregistered journal policy')
        if kind=='evaluation_completed':
            row=event['row'];key=(policy,row['episode_index']);entry=episodes.get(key)
            b.need(entry is not None and entry.get('row') is None,'duplicate/unconstructed completion')
            b.need(entry['gameplay_frames']==row['gameplay_frames'],'per-episode gameplay conservation differs')
            b.need(entry['seed']==row['seed'],'completed seed differs');entry['row']=row;completed+=1
        else:
            index=event['episode_index'];b.need(type(index)is int and 0<=index<1024,'journal episode index differs')
            key=(policy,index)
            if kind=='evaluation_constructor':
                b.need(key not in episodes and event['startup_frames']==13 and event['seed']==b.SEEDS[index],
                    'constructor identity/startup differs')
                episodes[key]=dict(seed=event['seed'],gameplay_frames=0,row=None)
                constructors+=1;cost+=13
            elif kind=='evaluation_step':
                entry=episodes.get(key);frames=event['elapsed_raw_frames']
                b.need(entry is not None and entry['row'] is None and type(frames)is int and 1<=frames<=4,
                    'unconstructed/post-terminal/invalid step')
                entry['gameplay_frames']+=frames;b.need(entry['gameplay_frames']<=18000,'episode raw-frame cap')
                cost+=frames;steps+=1
            else:raise ValueError('unregistered journal event')
    b.need(constructors<=b.EPISODES and steps<=b.STEP_CAP and cost<=b.RAW_CAP,'journal exceeds registered budgets')
    result=dict(constructors=constructors,completed_episodes=completed,native_steps=steps,
        raw_frames_including_startup=cost,
        evidence_limit='Returned complete journal prefix only; native exceptions without returned results have unknown cost.',
        worker_claimed_completed_policies=worker.get('completed_policies'))
    if include_rows:
        result['rows']={name:[entry['row'] for (policy,index),entry in sorted(episodes.items())
            if policy==name and entry['row'] is not None] for name in b.POLICIES}
    return result


def validate_outputs(reg,worker,registration_sha):
    out=Path(reg['output'])
    b.need(worker.get('schema')=='fullgame_priority_d4_evaluation_worker_v1'
        and worker.get('status')=='completed' and worker.get('run_id')==reg['run_id']
        and worker.get('registration_sha256')==registration_sha,'worker identity/completion differs')
    b.need(all(worker.get(k)is False for k in ('training_eligible','promoted','automatic_selection')),
        'worker eligibility differs')
    b.need(worker['completed_policies']==list(b.POLICIES) and worker['rows_completed']==b.EPISODES,
        'all seven endpoints required')
    b.need(0<=worker['elapsed_seconds']<reg['limits']['work_seconds'],'worker work deadline exceeded')
    report=accounting(out,worker,strict=True,include_rows=True);policy_rows={}
    for policy in reg['policies']:
        receipt=b.read(out/(policy['id']+'.json'));claim=b.read(out/(policy['id']+'.claim'))
        b.need(claim==dict(policy_id=policy['id'],registration_sha256=registration_sha,
            checkpoint_sha256=policy['checkpoint_sha256']),'policy claim differs')
        b.need(receipt['schema']=='fullgame_priority_d4_terminal60_evaluation_v1'
            and receipt['policy_id']==policy['id'] and receipt['registration_sha256']==registration_sha
            and receipt['checkpoint_sha256']==policy['checkpoint_sha256']
            and receipt['runtime_manifest_sha256']==reg['runtime_manifest_sha256'], 'fixed endpoint receipt identity differs')
        b.need(receipt['action_mode']=='sampled_categorical' and receipt['normal_start'] is True
            and receipt['cutoff_enabled'] is False and receipt['automatic_selection'] is False
            and receipt['promoted'] is False,'full-run inference semantics differ')
        summary=comparison.summarize(receipt['rows'],reg['seeds'])
        b.need(summary==receipt['summary'] and receipt['rows']==report['rows'][policy['id']],
            'summary/complete journal rows differ')
        b.need(receipt['raw_frames_including_startup']==sum(r['gameplay_frames']+r['startup_frames'] for r in receipt['rows']),
            'policy returned frame total differs')
        policy_rows[policy['id']]=receipt['rows']
    stored=b.read(out/'comparison.json');base=comparison.compare(policy_rows,reg['seeds'])
    b.need({k:v for k,v in stored.items() if k!='paired_conditional_seed_intervals'}==base,
        'paired descriptive comparison differs')
    intervals=stored.get('paired_conditional_seed_intervals',{})
    b.need(intervals.get('schema')=='fullgame_priority_d4_conditional_paired_seed_intervals_v1'
        and intervals.get('contract')==reg['bootstrap'] and intervals.get('automatic_selection') is False
        and intervals.get('promoted') is False,'interval contract differs')
    b.need(b.sha(out/'comparison.json')==worker['comparison_sha256'],'comparison SHA differs')
    b.need(report['constructors']==report['completed_episodes']==b.EPISODES
        and report['raw_frames_including_startup']==worker['raw_frames_including_startup']<=reg['limits']['raw_frames']
        and report['constructors']==worker['constructors']<=reg['limits']['constructors']
        and report['native_steps']==worker['native_steps']<=reg['limits']['native_steps'],
        'total episode/raw-frame/constructor/step conservation differs')
    resources=b.worker_resources(out,strict=True)
    b.need(resources['samples']>0 and resources['peak_rss_bytes']<=b.CAP
        and resources['peak_mps_driver_bytes']<=b.CAP,'terminal resources missing/over limit')
    return {k:v for k,v in report.items() if k!='rows'}
