"""Independent worker-output conservation and comparison recomputation."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import binding as b
import evaluation
import seeds as seed_tools


def read_jsonl(path, *, strict):
    rows=[]; path=Path(path)
    if not path.is_file():
        b.need(not strict, 'required journal missing')
        return rows
    with path.open() as stream:
        for line in stream:
            if not line.endswith('\n'):
                b.need(not strict, 'torn journal row')
                break
            rows.append(json.loads(line))
    return rows


def validate_recovery_episode_metadata(payload, reg, pool):
    indices=payload.get('native_episode_indices'); actual_seeds=payload.get('native_episode_seeds')
    rows=payload.get('in_flight_metadata')
    slots={str(slot) for slot in range(64)}
    b.need(type(indices) is dict and set(indices)==slots and type(actual_seeds) is dict
        and set(actual_seeds)==slots and type(rows) is list and len(rows)==64,
        'recovery sidecar must preserve exactly64 native slot indices and seeds')
    seen=set()
    for row in rows:
        b.need(type(row) is dict and type(row.get('slot')) is int and 0<=row['slot']<64
            and row['slot'] not in seen,'recovery native slot metadata is missing or duplicated')
        slot=row['slot']; key=str(slot); seen.add(slot); info=row.get('native_info')
        b.need(type(info) is dict and type(info.get('seed')) is dict,'recovery native info is malformed')
        seed=info['seed']; episode=indices[key]; actual=actual_seeds[key]
        b.need(type(episode) is int and 0<=episode<reg['streams']['capacity_per_slot']
            and type(actual) is int and 0<=actual<=0xffffffff
            and type(seed.get('slot')) is int and seed.get('slot')==slot
            and type(seed.get('episode')) is int and seed.get('episode')==episode
            and seed.get('actual_seed')==actual and seed.get('evaluation') is False
            and actual==seed_tools.stream_seed(pool,reg['training_pair_seed'],slot,episode),
            'recovery native episode index/seed differs from registered stream')
        b.need(type(row.get('episode_index')) is int and row['episode_index']==episode
            and row.get('actual_seed')==actual
            and row.get('in_flight') is (not (info.get('terminated') or info.get('truncated'))),
            'recovery in-flight slot summary differs from native info')
    binding=dict(episode_indices=indices,actual_seeds=actual_seeds)
    b.need(len(seen)==64
        and payload.get('in_flight_slots')==sum(bool(row['in_flight']) for row in rows)
        and payload.get('in_flight_metadata_sha256')==hashlib.sha256(b.canonical(rows)).hexdigest()
        and payload.get('slot_seed_binding_sha256')==hashlib.sha256(b.canonical(binding)).hexdigest(),
        'recovery sidecar in-flight/seed binding digest differs')
    return True


def accounting(out, worker, *, strict=False):
    events=read_jsonl(Path(out)/'training.jsonl',strict=strict)
    updates={arm['id']:[] for arm in b.design()['arms']}
    recoveries={arm['id']:[] for arm in b.design()['arms']}
    for event in events:
        if event.get('kind') == 'update':
            arm=event.get('arm'); b.need(arm in updates,'unregistered arm update in journal')
            updates[arm].append({k:v for k,v in event.items() if k not in ('kind','arm')})
        elif event.get('kind') == 'recovery_checkpoint':
            arm=event.get('arm'); b.need(arm in recoveries,'unregistered arm recovery snapshot in journal')
            recoveries[arm].append(event.get('snapshot'))
    results={}
    for arm, rows in updates.items():
        b.need([r['update'] for r in rows] == list(range(1,len(rows)+1)), 'update journal order differs')
        results[arm]=dict(updates=len(rows), gameplay_frames=sum(r['gameplay_frames'] for r in rows),
            startup_frames=sum(r['startup_frames'] for r in rows),
            policy_decisions=sum(r['decisions']*64 for r in rows),
            optimizer_steps=sum(r['optimizer_steps'] for r in rows),
            budget_closed=sum(bool(r['budget_reached']) for r in rows))
    return dict(arms=results,recoveries=recoveries,
        updates=sum(x['updates'] for x in results.values()), events=len(events))


def validate_outputs(reg, worker, registration_sha):
    out=Path(reg['output'])
    b.need(worker.get('schema')=='one_frame_training_comparison_worker_v1'
        and worker.get('status')=='completed' and worker.get('run_id')==reg['run_id']
        and worker.get('registration_sha256')==registration_sha, 'worker completion identity differs')
    b.need(all(worker.get(k) is False for k in ('training_eligible','promoted','automatic_selection')),
           'worker eligibility boundary differs')
    b.need(type(worker.get('elapsed_seconds')) in (int,float)
        and 0 <= worker['elapsed_seconds'] < reg['limits']['work_seconds'], 'worker wall deadline differs')
    b.need([x.get('id') for x in worker['arms']]==[x['id'] for x in reg['arms']], 'fixed arm order differs')
    ledger=accounting(out,worker,strict=True)
    pool=seed_tools.validate_pool(b.read(b.TRAINING_POOL))
    seed_tools.verify_exclusions(pool,reg['exclusion_union'])
    by_id={x['id']:x for x in worker['arms']}
    for arm in reg['arms']:
        item=by_id[arm['id']]; observed=ledger['arms'][arm['id']]
        b.need(item['updates']==observed['updates'] and item['gameplay_frames']==observed['gameplay_frames']
            and item['startup_frames']==observed['startup_frames']
            and item['policy_decisions']==observed['policy_decisions']
            and item['optimizer_steps']==observed['optimizer_steps'], 'arm journal/receipt totals differ')
        target=reg['gameplay_frame_target_per_arm']
        b.need(target <= item['gameplay_frames'] <= reg['limits']['per_arm_gameplay_frames']
            and item['gameplay_frames']-target < 64*arm['action_repeat'], 'arm frame budget/overshoot differs')
        formal_bound=reg['update_bounds']['formal_by_arm'][arm['id']]
        b.need(item['update_bound']==formal_bound and 0 < item['updates'] <= formal_bound,
            'formal arm update count/bound differs')
        ck=item['checkpoint']; b.need(b.sha(ck['path'])==ck['sha256'], 'final arm checkpoint bytes differ')
        interval=reg['recovery_checkpoint_gameplay_interval']
        expected_boundaries=list(range(interval,target+1,interval))
        snapshots=item.get('recovery_checkpoints')
        b.need(type(snapshots) is list
            and [x.get('recovery_boundary_gameplay_frames') for x in snapshots]==expected_boundaries
            and ledger['recoveries'][arm['id']]==snapshots,
            'formal recovery snapshot cadence/journal differs')
        cumulative=0; boundary_update={}
        for row in item['update_metrics']:
            cumulative+=row['gameplay_frames']
            for crossed in expected_boundaries:
                if crossed not in boundary_update and cumulative>=crossed:
                    boundary_update[crossed]=(cumulative,row['update'])
        for snap in snapshots:
            b.need(Path(snap['path']).resolve().parent==out.resolve()
                and Path(snap['sidecar_path']).resolve().parent==out.resolve(),
                'formal recovery artifact escapes worker output')
            payload=b.read(snap['sidecar_path'])
            b.need(b.sha(snap['path'])==snap['sha256']==payload.get('sha256')
                and b.sha(snap['sidecar_path'])==snap['sidecar_sha256'],
                'formal recovery snapshot or sidecar hash differs')
            actual,updates_at_crossing=boundary_update[snap['recovery_boundary_gameplay_frames']]
            b.need(payload.get('schema')=='one_frame_training_formal_recovery_sidecar_v1'
                and payload.get('run_id')==reg['run_id']
                and payload.get('registration_sha256')==registration_sha
                and payload.get('arm')==arm['id'] and payload.get('path')==snap['path']
                and payload.get('recovery_boundary_gameplay_frames')==snap['recovery_boundary_gameplay_frames']
                and payload.get('actual_gameplay_frames')==actual==snap['actual_gameplay_frames']
                and payload.get('completed_updates')==updates_at_crossing==snap['completed_updates']
                and payload.get('global_update')==reg['checkpoint_global_update']+updates_at_crossing
                and type(payload.get('model_fingerprint')) is str and len(payload['model_fingerprint'])==64
                and type(payload.get('adam_fingerprint')) is str and len(payload['adam_fingerprint'])==64
                and type(payload.get('native_episode_indices')) is dict
                and type(payload.get('in_flight_slots')) is int
                and payload.get('model_optimizer_rng_included') is True
                and payload.get('full_environment_state_captured') is False
                and payload.get('automatic_resume_authorized') is False
                and payload.get('training_eligible') is False and payload.get('promoted') is False
                and payload.get('automatic_selection') is False,
                'formal recovery sidecar identity/eligibility differs')
            validate_recovery_episode_metadata(payload,reg,pool)
    b.need(abs(by_id[reg['arms'][0]['id']]['gameplay_frames']-
        by_id[reg['arms'][1]['id']]['gameplay_frames'])<=256, 'paired frame totals differ')
    import screen
    groups={}; seeds=reg['evaluation_seeds']
    model_pins={'starting420':(reg['checkpoint_path'],reg['checkpoint_sha256'])}
    for arm in worker['arms']:
        model_pins[arm['id'].replace('_training','_final')]=(arm['checkpoint']['path'],arm['checkpoint']['sha256'])
    expected_names={f'{model}_repeat{repeat}_sampled' for model in reg['evaluation']['models']
                    for repeat in reg['evaluation']['control_repeats']}
    expected_artifacts={'training.jsonl','resources.jsonl','worker-result.json','comparison.json'}
    expected_artifacts.update(f'{name}.json' for name in expected_names)
    expected_artifacts.update(Path(by_id[arm['id']]['checkpoint']['path']).name for arm in reg['arms'])
    for arm in reg['arms']:
        for snap in by_id[arm['id']]['recovery_checkpoints']:
            expected_artifacts.update((Path(snap['path']).name,Path(snap['sidecar_path']).name))
    b.need({path.name for path in out.iterdir()}==expected_artifacts,
        'formal worker output artifact set differs from registration')
    for name in expected_names:
        path=out/(name+'.json'); receipt=b.read(path)
        b.need(receipt.get('schema')=='one_frame_training_comparison_evaluation_group_v1'
            and receipt.get('group')==name and receipt.get('seeds_sha256')==evaluation.digest(seeds),
            'evaluation group identity/seed set differs')
        model_id=name.rsplit('_repeat',1)[0]; repeat=int(name.rsplit('_repeat',1)[1].removesuffix('_sampled'))
        pinned_path,pinned_digest=model_pins[model_id]
        b.need(receipt.get('model')==model_id and receipt.get('action_repeat')==repeat
            and receipt.get('checkpoint_sha256')==pinned_digest and b.sha(pinned_path)==pinned_digest,
            'evaluation model/checkpoint binding differs')
        screen.validate_rows(receipt['rows'],seeds)
        groups[name]=receipt['rows']
    recomputed=evaluation.analyze(groups,seeds,draws=reg['evaluation']['bootstrap_draws'],
        seed=reg['evaluation']['bootstrap_seed'])
    stored=b.read(out/'comparison.json')
    b.need(stored==recomputed and worker.get('comparison_sha256')==b.sha(out/'comparison.json'),
           'stored evaluation analysis differs from row recomputation')
    resources=b.worker_resources(out,strict=True)
    b.need(worker.get('resource_summary')=={key:resources[key] for key in
        ('samples','peak_rss_bytes','peak_mps_driver_bytes')},
        'worker resource summary differs from strict journal parse')
    b.need(resources['peak_rss_bytes']<=reg['limits']['rss_bytes']
        and resources['peak_mps_driver_bytes']<=reg['limits']['mps_bytes'], 'worker resource samples exceed limits')
    return dict(status='complete',arms=ledger['arms'],evaluation_groups=sorted(expected_names),
        comparison_sha256=b.sha(out/'comparison.json'),resources=resources,
        automatic_selection=False,promoted=False,training_eligible=False)


def qualification_accounting(out, worker):
    events=read_jsonl(Path(out)/'training.jsonl',strict=True)
    arms={arm['id']:[] for arm in b.design()['arms']}
    for event in events:
        if event.get('kind') == 'qualification_update':
            arm=event.get('arm'); b.need(arm in arms,'unregistered qualification arm update')
            arms[arm].append({k:v for k,v in event.items() if k not in ('kind','arm')})
        else:
            b.need(event.get('kind') in ('qualification_arm_complete',),
                'qualification journal contains formal/evaluation event')
    totals={}
    for arm,rows in arms.items():
        b.need([r.get('update') for r in rows]==list(range(1,len(rows)+1)),
            'qualification update journal order differs')
        totals[arm]=dict(updates=len(rows),gameplay_frames=sum(r['gameplay_frames'] for r in rows),
            startup_frames=sum(r['startup_frames'] for r in rows),
            vector_calls=sum(r['vector_calls'] for r in rows),
            policy_decisions=sum(r['vector_calls']*64 for r in rows),
            optimizer_steps=sum(r['optimizer_steps'] for r in rows),
            budget_closed=sum(bool(r['budget_reached']) for r in rows))
    return dict(arms=totals,updates=sum(v['updates'] for v in totals.values()),events=len(events))


def validate_qualification_outputs(reg, worker, registration_sha):
    q=b.read(b.PARENT/'qualification-protocol.json'); out=Path(reg['output'])
    b.need(worker.get('schema')=='one_frame_training_resource_qualification_receipt_v1'
        and worker.get('status')=='completed' and worker.get('run_id')==q['run_id']
        and worker.get('registration_sha256')==registration_sha,
        'qualification completion identity differs')
    b.need(worker.get('qualification_protocol_sha256')==b.sha(b.PARENT/'qualification-protocol.json')
        and worker.get('checkpoint_sha256')==q['checkpoint_sha256'],
        'qualification protocol/checkpoint lineage differs')
    b.need(all(worker.get(k) is True for k in ('no_checkpoint_writes','no_evaluation_seed_use',
        'no_formal_weight_reuse','no_retry')) and all(worker.get(k) is False
        for k in ('promoted','training_eligible','automatic_selection')),
        'qualification no-write/no-evaluation authority boundary differs')
    b.need(worker.get('checkpoint_writes')==0 and worker.get('evaluation_calls')==0
        and 'evaluations' not in worker and 'comparison_sha256' not in worker,
        'qualification receipt records checkpoint/evaluation activity')
    b.need(type(worker.get('elapsed_seconds')) in (int,float)
        and 0<=worker['elapsed_seconds']<q['wall_cap_seconds'],'qualification work deadline differs')
    b.need({p.name for p in out.iterdir()}=={'training.jsonl','resources.jsonl','worker-result.json'},
        'qualification output contains unexpected artifact or checkpoint/evaluation file')
    ledger=qualification_accounting(out,worker); by_id={x['id']:x for x in worker['arms']}
    b.need(set(by_id)==set(q['arms']) and len(by_id)==2,'qualification arm set differs')
    for arm_id,item in by_id.items():
        observed=ledger['arms'][arm_id]; repeat=item['action_repeat']
        for key in ('updates','gameplay_frames','startup_frames','vector_calls','policy_decisions','optimizer_steps'):
            b.need(item[key]==observed[key],'qualification journal/receipt totals differ: '+arm_id+'/'+key)
        b.need(0<item['updates']<=q['max_PPO_updates_per_arm']
            and q['gameplay_frame_target_per_arm']<=item['gameplay_frames']<=q['gameplay_frame_cap_per_arm']
            and item['gameplay_frames']-q['gameplay_frame_target_per_arm']<64*repeat,
            'qualification arm frame/update bound differs')
        b.need(item['startup_frames']<=q['max_startup_frames_per_arm']
            and item['policy_decisions']<=q['max_policy_decisions_per_arm']
            and item['vector_calls']<=q['max_vector_calls_per_arm']
            and item['gameplay_frames']+item['startup_frames']<=q['max_raw_frames_including_startup_per_arm'],
            'qualification arm startup/raw/decision/vector cap differs')
        rows=item['update_metrics']
        b.need(len(rows)==item['updates'] and [r['update'] for r in rows]==list(range(1,item['updates']+1))
            and sum(r['gameplay_frames'] for r in rows)==item['gameplay_frames']
            and sum(r['startup_frames'] for r in rows)==item['startup_frames']
            and sum(r['vector_calls'] for r in rows)==item['vector_calls']
            and sum(r['optimizer_steps'] for r in rows)==item['optimizer_steps']
            and [r['budget_reached'] for r in rows]==[False]*(len(rows)-1)+[True],
            'qualification final partial-update closure differs')
        b.need(item['peak_rss_bytes']<=q['RSS_bytes']
            and item['peak_mps_driver_bytes']<=q['MPS_driver_bytes'],
            'qualification arm measured resource cap differs')
    resources=b.worker_resources(out,strict=True)
    b.need(worker.get('resource_summary')=={key:resources[key] for key in
        ('samples','peak_rss_bytes','peak_mps_driver_bytes')},
        'qualification resource summary differs from strict journal parse')
    b.need(resources['peak_rss_bytes']<=q['RSS_bytes']
        and resources['peak_mps_driver_bytes']<=q['MPS_driver_bytes'],
        'qualification worker resource samples exceed limits')
    return dict(status='qualification_complete',arms=ledger['arms'],resources=resources,
        checkpoint_writes=0,evaluation_calls=0,no_checkpoint_writes=True,
        no_evaluation_seed_use=True,automatic_selection=False,promoted=False,training_eligible=False)


def main(registration, registration_sha, *, exit_code=0):
    reg=b.read(registration); b.validate_static(reg,require_registered=True)
    b.need(type(exit_code) is int and exit_code==0, 'supervisor did not observe successful worker exit')
    worker=b.read(Path(reg['output'])/'worker-result.json')
    report=(validate_qualification_outputs(reg,worker,registration_sha)
        if reg.get('phase')=='qualification' else validate_outputs(reg,worker,registration_sha))
    target=b.phase_path(reg,'local-terminal-audit.json')
    b.save(target,dict(schema=b.AUDIT_SCHEMA,run_id=reg['run_id'],registration_sha256=registration_sha,
        source_manifest_sha256=reg['source_manifest_sha256'],audit=report,launch_authority=False,
        automatic_selection=False,promoted=False,training_eligible=False))
    return 0


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--registration',required=True)
    parser.add_argument('--registration-sha256',required=True);parser.add_argument('--exit-code',type=int,required=True)
    args=parser.parse_args();raise SystemExit(main(args.registration,args.registration_sha256,exit_code=args.exit_code))
