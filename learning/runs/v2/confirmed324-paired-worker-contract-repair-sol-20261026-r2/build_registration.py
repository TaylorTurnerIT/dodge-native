"""Render an inert template. Parent alone fills gates and registers a worker."""
import argparse
import json
from pathlib import Path
import contracts as c


def template(replica,arm):
    c.need(type(replica) is int and replica in (1,2,3) and arm in c.ARMS, 'replica/arm differs')
    inputs = c.read(c.HERE/'input-manifest.json')
    vector = next(v for v in c.read(c.ROOT/c.VECTOR_PATH)['vectors'] if v['replica']==replica)
    parent = c.read(c.ROOT/c.PARENT_RECEIPT)
    reference = next(r for r in c.read(c.ROOT/c.REF_ROOT/'parent-terminal-audit.json')['references'] if r['replica']==replica)
    pair = f'{c.STUDY}-replica-{replica}'
    run = pair+('-A' if arm==c.ARMS[0] else '-B')
    return dict(schema='paired_confirmed324_worker_registration_v2',status='parent_review_required_not_launchable',
        study_id=c.STUDY,run_id=run,pair_id=pair,arm=arm,replica=replica,backend='mps',vector=vector,
        reference=dict(receipt_path=reference['path'],receipt_sha256=reference['sha256'],vector_sha256=reference['vector_sha256']),
        parent_checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256,parent_receipt_sha256=c.references.PARENT_RECEIPT_SHA256,
        expected_parent_fingerprints=c.transition.EXPECTED_PARENT,initial_episode_indices=parent['next_episode_indices'],
        exclusion_union=[list(row) for row in c.transition.EXPECTED_EXCLUSION_RANGES],ppo=c.PPO,schedule=c.SCHEDULE,limits=c.LIMITS,
        input_manifest_sha256=c.sha(c.HERE/'input-manifest.json'),source_manifest_sha256='{{PARENT_PIN_FINAL_SOURCE_MANIFEST}}',
        runtime_root=inputs['runtime_root'],runtime_versions=inputs['runtime_versions'],
        output=str(c.ROOT/'learning/runs/v2'/run),attempt_claim_path=str(c.ROOT/'learning/runs/v2'/(run+'.transition.claimed')),
        interpreter=str(c.ROOT/'python/.venv/bin/python'),import_policy=dict(dont_write_bytecode=True,pycache_prefix='{{PARENT_REGISTER_NEW_EMPTY_CACHE}}'),
        state_path='{{PARENT_STATE_PATH}}',expected_lease={'run_id':run,'study_id':c.STUDY,'parent_checkpoint_sha256':c.references.ACCEPTED_CHECKPOINT_SHA256,'owner_token':'{{PARENT_OWNED_TOKEN}}'},
        launch_marker_path='{{PARENT_SPENT_LAUNCH_MARKER_PATH}}')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replica',required=True,type=int)
    parser.add_argument('--arm',required=True,choices=c.ARMS)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    c.need(args.output.resolve().is_relative_to(c.HERE), 'template destination must be owned')
    with args.output.open('x') as stream:
        json.dump(template(args.replica,args.arm),stream,sort_keys=True,indent=2)
        stream.write('\n')


if __name__=='__main__':
    main()
