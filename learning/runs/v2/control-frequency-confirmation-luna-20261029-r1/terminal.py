"""Terminal journal conservation and full diagnostic receipt validation."""
from __future__ import annotations
import json
from pathlib import Path
import binding as b
import screen


def rows(path, *, strict=False):
    path=Path(path)
    if not path.is_file(): return
    with path.open() as stream:
        for line in stream:
            if not line.endswith('\n'):
                b.need(not strict,'torn event journal');break
            yield json.loads(line)


def accounting(out,worker,*,strict=False):
    out=Path(out);episodes={};constructors=completed=raw=steps=0;groups={}
    valid_groups={f"{x['condition']}-rep{x['repetition']}" for x in b.PROTOCOL['order']}
    for event in rows(out/'events.jsonl',strict=strict):
        group=event['group'];kind=event['kind'];b.need(group in valid_groups,'unregistered group journal event')
        key=(group,event.get('episode_index'))
        if kind=='constructor':
            index=event['episode_index'];b.need(type(index)is int and 0<=index<256,'constructor episode index invalid')
            b.need(key not in episodes and event['startup_frames']==13 and event['seed']==b.PROTOCOL['seeds'][index],'constructor identity/startup differs')
            episodes[key]=dict(seed=event['seed'],startup=13,row=None);constructors+=1;raw+=13
            groups.setdefault(group,dict(constructors=0,completed=0,raw_frames=0,native_steps=0));groups[group]['constructors']+=1;groups[group]['raw_frames']+=13
        elif kind=='completed':
            row=event['row'];key=(group,row['episode_index']);entry=episodes.get(key)
            b.need(entry is not None and entry['row'] is None and entry['seed']==row['seed'] and entry['startup']==row['startup_frames'],'completion does not match constructor')
            b.need(row['episode_index']==key[1] and row['startup_frames']==13,'completed episode index/startup differs')
            entry['row']=row;completed+=1;game_raw=row['gameplay_frames'];raw+=game_raw;steps+=row['policy_decisions']
            groups[group]['completed']+=1;groups[group]['raw_frames']+=game_raw;groups[group]['native_steps']+=row['policy_decisions']
        else:raise ValueError('only constructor and completed aggregates may be journaled')
    limits=b.PROTOCOL['limits'];b.need(constructors<=limits['constructors'] and steps<=limits['native_steps'] and raw<=limits['raw_frames'],'journal lower bound exceeds protocol')
    for group,item in groups.items():
        condition=group.rsplit('-rep',1)[0];lim=b.PROTOCOL['condition_limits'][condition]
        b.need(item['constructors']<=lim['constructors'] and item['native_steps']<=lim['native_steps'] and item['raw_frames']<=lim['raw_frames'],'journal condition exceeds protocol')
    b.need(len(episodes)==constructors and completed<=constructors,'journal episode accounting differs')
    complete=completed==constructors==limits['episodes']
    return dict(complete=complete,constructors=constructors,completed_episodes=completed,native_steps=steps,
        raw_frames_including_startup=raw,groups=groups,
        evidence_limit='Completed-row journal gives exact complete work. On interruption, startup and completed episodes are a lower bound; in-flight native work is unknown.')


def validate_outputs(reg,worker,registration_sha):
    out=Path(reg['output']);order=reg['order'];group_ids=[f"{g['condition']}-rep{g['repetition']}" for g in order]
    b.need(worker.get('schema')=='control_frequency_confirmation_worker_v1' and worker.get('status')=='completed'
        and worker.get('run_id')==reg['run_id'] and worker.get('registration_sha256')==registration_sha,'worker identity/completion differs')
    b.need(all(worker.get(k)is False for k in ('training_eligible','promoted','automatic_selection')),'worker eligibility differs')
    b.need(worker['completed_groups']==group_ids and worker['rows_completed']==reg['limits']['episodes'],'fixed group completion differs')
    b.need(0<=worker['elapsed_seconds']<reg['limits']['work_seconds'],'worker work deadline exceeded')
    ledger=accounting(out,worker,strict=True)
    b.need(ledger['complete'],'incomplete terminal journal')
    condition_rows={k:[] for k in screen.CONDITIONS};group_elapsed={}
    for group in order:
        gid=f"{group['condition']}-rep{group['repetition']}";receipt=b.read(out/(gid+'.json'))
        b.need(receipt.get('schema')=='control_frequency_confirmation_group_v1' and receipt.get('group')==group
            and receipt['checkpoint_sha256']==reg['checkpoint_sha256'] and receipt['runtime_manifest_sha256']==reg['runtime_manifest_sha256'],'group receipt identity differs')
        rows=receipt['rows'];summary=screen.summarize(rows,reg['seeds']);b.need(receipt['summary']==summary,'group row summary differs')
        b.need(receipt['raw_frames_including_startup']==summary['totals']['raw_frames'],'group frame total differs')
        group_elapsed[gid]=receipt['elapsed_seconds']
        if group['condition'].startswith('sampled'): condition_rows[group['condition']].append(rows)
        else: condition_rows[group['condition']]=rows
    b.need(ledger['constructors']==ledger['completed_episodes']==reg['limits']['episodes'],'all constructors must have one completed row')
    b.need(ledger['raw_frames_including_startup']==worker['raw_frames_including_startup']<=reg['limits']['raw_frames']
        and ledger['constructors']==worker['constructors']<=reg['limits']['constructors']
        and ledger['native_steps']==worker['native_steps']<=reg['limits']['native_steps'],'worker/journal conservation differs')
    report=screen.analyze_conditions(condition_rows,reg['seeds'],bootstrap_draws=reg['bootstrap']['draws'],bootstrap_seed=reg['bootstrap']['seed'])
    report['registered_contrast_names']=reg['bootstrap']['contrasts'];report['registered_group_order']=order;report['condition_wall_seconds']={c:sum(group_elapsed[f"{g['condition']}-rep{g['repetition']}"] for g in order if g['condition']==c) for c in screen.CONDITIONS}
    report['comparison_elapsed_seconds']=worker['comparison_elapsed_seconds']
    b.need(type(worker['elapsed_seconds'])in(int,float) and 0<=worker['comparison_elapsed_seconds']<=worker['elapsed_seconds']<reg['limits']['work_seconds'],'comparison timing bounds differ')
    stored=b.read(out/'comparison.json')
    b.need(stored==report and b.sha(out/'comparison.json')==worker['comparison_sha256'],'comparison report recomputation differs')
    resources=b.worker_resources(out,strict=True)
    b.need(resources['samples']>0 and resources['peak_rss_bytes']<=reg['limits']['rss_bytes']
        and resources['peak_mps_driver_bytes']<=reg['limits']['mps_bytes'],'terminal resources missing/over limit')
    return dict(status='complete',groups=group_ids,episodes=ledger['completed_episodes'],raw_frames=ledger['raw_frames_including_startup'],
        native_steps=ledger['native_steps'],comparison_sha256=worker['comparison_sha256'],resources=resources,
        automatic_selection=False,promoted=False,training_eligible=False)
