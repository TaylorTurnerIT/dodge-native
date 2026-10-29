"""Independent worker-output conservation and comparison recomputation."""
from __future__ import annotations
import json
from pathlib import Path
import binding as b
import evaluation


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


def accounting(out, worker, *, strict=False):
    events=read_jsonl(Path(out)/'training.jsonl',strict=strict)
    updates={arm['id']:[] for arm in b.design()['arms']}
    for event in events:
        if event.get('kind') == 'update':
            arm=event.get('arm'); b.need(arm in updates,'unregistered arm update in journal')
            updates[arm].append({k:v for k,v in event.items() if k not in ('kind','arm')})
    results={}
    for arm, rows in updates.items():
        b.need([r['update'] for r in rows] == list(range(1,len(rows)+1)), 'update journal order differs')
        results[arm]=dict(updates=len(rows), gameplay_frames=sum(r['gameplay_frames'] for r in rows),
            startup_frames=sum(r['startup_frames'] for r in rows),
            policy_decisions=sum(r['decisions']*64 for r in rows),
            optimizer_steps=sum(r['optimizer_steps'] for r in rows),
            budget_closed=sum(bool(r['budget_reached']) for r in rows))
    return dict(arms=results, updates=sum(x['updates'] for x in results.values()), events=len(events))


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
        b.need(item['updates'] <= reg['limits']['max_updates_per_arm'] if reg.get('qualification_mode')
            else item['updates'] > 0, 'arm update count differs')
        ck=item['checkpoint']; b.need(b.sha(ck['path'])==ck['sha256'], 'final arm checkpoint bytes differ')
    b.need(abs(by_id[reg['arms'][0]['id']]['gameplay_frames']-
        by_id[reg['arms'][1]['id']]['gameplay_frames'])<=256, 'paired frame totals differ')
    import screen
    groups={}; seeds=reg['evaluation_seeds']
    model_pins={'starting420':(reg['checkpoint_path'],reg['checkpoint_sha256'])}
    for arm in worker['arms']:
        model_pins[arm['id'].replace('_training','_final')]=(arm['checkpoint']['path'],arm['checkpoint']['sha256'])
    expected_names={f'{model}_repeat{repeat}_sampled' for model in reg['evaluation']['models']
                    for repeat in reg['evaluation']['control_repeats']}
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
    b.need(resources['peak_rss_bytes']<=reg['limits']['rss_bytes']
        and resources['peak_mps_driver_bytes']<=reg['limits']['mps_bytes'], 'worker resource samples exceed limits')
    return dict(status='complete',arms=ledger['arms'],evaluation_groups=sorted(expected_names),
        comparison_sha256=b.sha(out/'comparison.json'),resources=resources,
        automatic_selection=False,promoted=False,training_eligible=False)


def main(registration, registration_sha, *, exit_code=0):
    reg=b.read(registration); b.validate_static(reg,require_registered=True)
    b.need(type(exit_code) is int and exit_code==0, 'supervisor did not observe successful worker exit')
    worker=b.read(Path(reg['output'])/'worker-result.json')
    report=validate_outputs(reg,worker,registration_sha)
    target=b.HERE/'local-terminal-audit.json'
    b.save(target,dict(schema=b.AUDIT_SCHEMA,run_id=reg['run_id'],registration_sha256=registration_sha,
        source_manifest_sha256=reg['source_manifest_sha256'],audit=report,launch_authority=False,
        automatic_selection=False,promoted=False,training_eligible=False))
    return 0


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--registration',required=True)
    parser.add_argument('--registration-sha256',required=True);parser.add_argument('--exit-code',type=int,required=True)
    args=parser.parse_args();raise SystemExit(main(args.registration,args.registration_sha256,exit_code=args.exit_code))
