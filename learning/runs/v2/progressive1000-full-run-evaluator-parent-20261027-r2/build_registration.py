"""Hash-only builder: inert draft unless a parent explicitly finalizes its gates."""
from __future__ import annotations
import argparse
import importlib
import math
from pathlib import Path
import uuid
import binding as b


def build(rng_seed,work_seconds=None):
    c=b.contracts();identity=importlib.import_module('successor_identity')
    integrated=b.ROOT/'learning/runs/v2/progressive1000-opening-maintenance-integrated-parent-20261027-r1'
    completion=integrated/'six-endpoint-completion.json';completed=b.read(completion)
    b.need(len(completed['endpoints'])==6 and completed['performance_evaluation_executed'] is False,
        'all predetermined training endpoints required before evaluation')
    pins={str(completion):b.sha(completion)};policies=[]
    for entry in sorted(completed['endpoints'],key=lambda x:b.POLICIES.index(x['run_id'].removeprefix(b.STUDY+'-'))):
        audit=Path(entry['audit']);registration=audit.parent/'registration-final.json'
        reg=b.read(registration);result=audit.parent/'worker-output/worker-result.json'
        source=Path(reg['runtime_root']).parent
        producer=dict(registration_path=str(registration),audit_path=str(audit),worker_result_path=str(result),
            source_manifest_sha256=reg['source_manifest_sha256'],runtime_manifest_sha256=reg['runtime_manifest_sha256'],
            expected_identity=identity.learner_identity(reg,b.sha(registration)),
            pins={str(path):b.sha(path) for path in [registration,audit,result,source/'source-manifest.json',source/'runtime-manifest.json']})
        policies.append(dict(id=reg['run_id'].removeprefix(b.STUDY+'-'),checkpoint_path=entry['endpoint']['path'],
            checkpoint_sha256=entry['endpoint']['sha256'],producer=producer))
    parent=c.read(b.ROOT/c.PARENT_RECEIPT)
    policies.append(dict(id='parent324',checkpoint_path=parent['checkpoint_path'],
        checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256,producer=None))
    for path in [integrated/'control-baseline-acceptance.json',integrated/'source-review-acceptance.json',
        b.ROOT/c.PARENT_RECEIPT,b.SOURCE/'source-manifest.json',b.SOURCE/'runtime-manifest.json',
        b.SOURCE/'input-manifest.json',b.ROOT/'learning/runs/v2/progressive1000-full-run-evaluation-parent-20261027-r1/producer-compatibility.json']:
        pins[str(path)]=b.sha(path)
    old=b.ROOT/'learning/runs/v2/expanded-confirmation-parent-20261026-r1/registration-final.json'
    measure=b.read(old)['benchmark_measurement'];pins[str(old)]=b.sha(old)
    proposal=math.ceil(2*measure['elapsed_seconds']/measure['raw_frames']*b.RAW_CAP+10)
    benchmark=Path(measure['receipt_path']);pins[str(benchmark)]=b.sha(benchmark)
    run_id='progressive1000-fixed-terminal-full-evaluation-20261027-r2'
    current=b.read(Path(completed['endpoints'][-1]['audit']).parent/'registration-final.json')
    reg=dict(schema='progressive1000_full_evaluation_registration_v2',status='source_review_pending',
        run_id=run_id,study_id=b.STUDY,backend='mps',source_manifest_sha256=b.sha(b.HERE/'source-manifest.json'),
        evaluator_source=str(b.SOURCE),runtime_root=str(b.SOURCE/'runtime'),runtime_manifest_sha256=b.RUNTIME_SHA,
        input_manifest_sha256=b.sha(b.SOURCE/'input-manifest.json'),runtime_versions=current['runtime_versions'],
        policies=policies,seeds=b.SEEDS,exclusion_union=current['exclusion_union'],evaluation_rng_seed=rng_seed,
        bootstrap=dict(seed=2026102701,draws=2000,confidence=.95,unit='paired_evaluation_seed',
            training_seed_uncertainty='three_training_pairs_descriptive_only'),
        semantics=dict(difficulty=2,normal_start=True,action_repeat=4,raw_frame_cap=18000,cutoff_enabled=False,
            action_mode='sampled_categorical',row_count=1024,parent_evaluations=1,policies=7,planned_episodes=7168),
        limits=dict(work_seconds=proposal if work_seconds is None else work_seconds,
            total_seconds=(proposal if work_seconds is None else work_seconds)+10,cleanup_seconds=10,
            rss_bytes=b.CAP,mps_bytes=b.CAP,raw_frames=b.RAW_CAP,resets=0,retries=0),
        output=str(b.HERE/'worker-output'),attempt_claim_path=str(b.HERE/'attempt.claimed'),
        launch_marker_path=str(b.HERE/'launch.claimed'),state_path=str(b.ROOT/'learning/runs/v2-orchestration/state.json'),
        expected_lease=dict(kind='progressive1000_fixed_endpoint_evaluation',run_id=run_id,
            owner_token=uuid.uuid4().hex,RSS_bytes=b.CAP,MPS_driver_bytes=b.CAP),
        interpreter=current['interpreter'],import_policy=dict(current['import_policy'],pycache_prefix=str(b.HERE/'empty-pycache')),
        input_pins=pins,calibration=dict(parent_accepted=False,prior_registration=str(old),prior_measurement=measure,
            proposed_work_seconds=proposal,projection='ceil(2*prior_elapsed/prior_raw_frames*maximum_raw_frames+10)',
            limitation='Prior sampler/native runtime differs. This is a conservative historical projection, not a fresh same-runtime MPS calibration.'),
        cohort_state='reserved_parent_approved',history_state='freshness_parent_approved',reservation_state='parent_reserved')
    b.validate_static(reg,require_registered=False,hash_checkpoints=False)
    return reg


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--rng-seed',required=True,type=int)
    parser.add_argument('--work-seconds',type=int);parser.add_argument('--output',required=True)
    args=parser.parse_args();path=Path(args.output).resolve()
    b.need(path.parent==b.HERE,'builder output must be owned')
    b.save(path,build(args.rng_seed,args.work_seconds))
    print(str(path),flush=True)
