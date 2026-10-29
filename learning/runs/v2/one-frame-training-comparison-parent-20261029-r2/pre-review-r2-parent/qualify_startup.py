"""Read-only validator for a separately executed DODGE-013 resource qualification."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
CAPSULE=ROOT/'learning/runs/v2/one-frame-training-comparison-luna-20261029-r2'
PROTOCOL=HERE/'protocol.json'
QUALIFICATION=HERE/'qualification-protocol.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def need(ok,message):
    if not ok: raise ValueError(message)


def validate(registration, registration_sha256, receipt_path, receipt_sha256,
             source_acceptance_path, source_acceptance_sha256, runtime_acceptance_path,
             runtime_acceptance_sha256):
    need(sha(registration)==registration_sha256,'registration pin differs')
    need(sha(receipt_path)==receipt_sha256,'qualification receipt pin differs')
    need(sha(source_acceptance_path)==source_acceptance_sha256,'source acceptance pin differs')
    need(sha(runtime_acceptance_path)==runtime_acceptance_sha256,'runtime acceptance pin differs')
    reg=read(registration); protocol=read(PROTOCOL); q=read(QUALIFICATION)
    source_acceptance=read(source_acceptance_path); runtime_acceptance=read(runtime_acceptance_path)
    need(reg.get('phase')=='qualification' and reg.get('formal_run_id')==protocol['run_id']
         and reg['run_id']==q['run_id'] and reg['launch_authority'] is False,
         'registration identity or authority differs')
    need(reg['runtime_manifest_sha256']==sha(reg['runtime_manifest_path'])
         and reg['source_manifest_sha256']==sha(reg['source_manifest_path']),
         'capsule source/runtime manifest drift')
    need(source_acceptance['status']=='accepted'
         and source_acceptance['source_manifest_sha256']==reg['source_manifest_sha256'],
         'independent source acceptance missing or stale')
    need(runtime_acceptance['status']=='accepted'
         and runtime_acceptance['schema']=='one_frame_training_runtime_source_acceptance_v1'
         and runtime_acceptance['scope']=='source_and_native_provenance_only_actual_training_qualification_pending'
         and runtime_acceptance['runtime_manifest_sha256']==reg['runtime_manifest_sha256'],
         'independent runtime acceptance missing or stale')
    need(q['status']=='preparation_pending_source_acceptance' and q['launch_authority'] is False
         and q['no_checkpoint_writes'] is True and q['no_formal_weight_reuse'] is True
         and q['no_evaluation_seed_use'] is True and q['no_retry'] is True,
         'resource qualification contract changed or became launch authority')
    need(reg['qualification_protocol_sha256']==sha(QUALIFICATION)
         and q['gameplay_frame_target_per_arm']==458816 and q['gameplay_frame_cap_per_arm']==524544
         and q['max_PPO_updates_per_arm']==8 and q['wall_cap_seconds']==1800
         and reg['limits']==q['limits'],
         'bounded qualification envelope differs')
    receipt=read(receipt_path)
    need(receipt['schema']=='one_frame_training_resource_qualification_receipt_v1'
         and receipt['status']=='completed' and receipt['run_id']==q['run_id'],
         'separate resource qualification receipt is not complete')
    need(receipt['registration_sha256']==registration_sha256
         and receipt['qualification_protocol_sha256']==sha(QUALIFICATION)
         and receipt['checkpoint_sha256']==q['checkpoint_sha256'], 'qualification lineage differs')
    if str(CAPSULE) not in sys.path: sys.path.insert(0,str(CAPSULE))
    import terminal
    terminal.validate_qualification_outputs(reg,receipt,registration_sha256)
    need(receipt['no_checkpoint_writes'] is True and receipt['no_evaluation_seed_use'] is True
         and receipt['no_formal_weight_reuse'] is True and receipt['no_retry'] is True
         and receipt['promoted'] is False and receipt['training_eligible'] is False,
         'qualification disposition differs')
    need('evaluations' not in receipt and 'evaluation_groups' not in receipt
         and all('checkpoint' not in arm for arm in receipt['arms']),
         'qualification receipt contains a checkpoint write or evaluation output')
    need(len(receipt['arms'])==2 and {a['id'] for a in receipt['arms']}==set(q['arms']),
         'qualification arm set differs')
    for arm in receipt['arms']:
        need(q['gameplay_frame_target_per_arm']<=arm['gameplay_frames']<=q['gameplay_frame_cap_per_arm']
             and arm['updates']<=q['max_PPO_updates_per_arm']
             and arm['policy_decisions']<=q['max_policy_decisions_per_arm']
             and arm['vector_calls']<=q['max_vector_calls_per_arm']
             and arm['startup_frames']<=q['max_startup_frames_per_arm']
             and arm['gameplay_frames']+arm['startup_frames']<=q['max_raw_frames_including_startup_per_arm']
             and arm['peak_rss_bytes']<=q['RSS_bytes']
             and arm['peak_mps_driver_bytes']<=q['MPS_driver_bytes'],
             'qualification arm exceeded its registered resource boundary')
        updates=arm['update_metrics']
        need(len(updates)==arm['updates'] and [x['update'] for x in updates]==list(range(1,arm['updates']+1))
             and updates[-1]['budget_reached'] is True
             and sum(x['gameplay_frames'] for x in updates)==arm['gameplay_frames']
             and sum(x['startup_frames'] for x in updates)==arm['startup_frames'],
             'qualification did not close target through the common final partial update')
    return dict(status='qualification_source_and_receipt_valid',
        qualification_receipt_sha256=receipt_sha256,
        launch_authority=False,resource_acceptance_pending_independent_parent_review=True)


def execute_registered_qualification(registration, registration_sha256, runtime, guard, journal):
    """Fakeable dispatcher into the capsule's no-save/no-eval qualification core."""
    need(sha(registration)==registration_sha256,'registration pin differs')
    reg=read(registration); protocol=read(PROTOCOL); q=read(QUALIFICATION)
    need(reg['status']=='parent_registered' and reg.get('phase')=='qualification'
         and reg['formal_run_id']==protocol['run_id'] and reg['run_id']==q['run_id'],
         'parent registration is not accepted for qualification')
    need(reg['source_manifest_sha256']==sha(reg['source_manifest_path'])
         and reg['runtime_manifest_sha256']==sha(reg['runtime_manifest_path']),
         'source/runtime manifests drifted before qualification')
    need(q['launch_authority'] is False and q['no_checkpoint_writes'] is True
         and q['no_evaluation_seed_use'] is True and q['no_formal_weight_reuse'] is True
         and q['no_retry'] is True,'qualification no-write/no-evaluation contract differs')
    need(reg['limits']==q['limits']
         and reg['update_bounds']['qualification_max_updates_per_arm']==q['max_PPO_updates_per_arm'],
         'registration qualification target/capacity/update contract differs')
    if str(CAPSULE) not in sys.path: sys.path.insert(0,str(CAPSULE))
    import worker
    return worker.qualification_campaign(reg,q,runtime,guard,journal,registration_sha256)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('registration','registration-sha256','receipt','receipt-sha256',
                 'source-acceptance','source-acceptance-sha256','runtime-acceptance','runtime-acceptance-sha256'):
        parser.add_argument('--'+name,required=True)
    a=parser.parse_args()
    print(json.dumps(validate(a.registration,a.registration_sha256,a.receipt,a.receipt_sha256,
        a.source_acceptance,a.source_acceptance_sha256,a.runtime_acceptance,a.runtime_acceptance_sha256),sort_keys=True))
