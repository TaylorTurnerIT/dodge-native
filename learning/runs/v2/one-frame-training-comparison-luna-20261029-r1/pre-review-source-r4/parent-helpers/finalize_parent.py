"""Read-only final parent gate reconciler. It never edits parent-owned JSON or starts training."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def need(ok,message):
    if not ok: raise ValueError(message)


def validate(registration,registration_sha256,source_acceptance,source_sha256,
             runtime_acceptance,runtime_sha256,resource_acceptance,resource_sha256):
    for path,digest in ((registration,registration_sha256),(source_acceptance,source_sha256),
                        (runtime_acceptance,runtime_sha256),(resource_acceptance,resource_sha256)):
        need(sha(path)==digest,'parent gate input hash differs: '+str(path))
    protocol=read(HERE/'protocol.json'); q=read(HERE/'qualification-protocol.json'); reg=read(registration)
    need(protocol['status']=='parent_approved_pre_run_protocol' and protocol['launch_authority'] is False,
         'formal protocol no longer states pre-run approval without launch authority')
    need(reg['status']=='parent_registered' and reg['launch_authority'] is False
         and reg['run_id']==protocol['run_id'],'registration is not parent-registered')
    source=read(source_acceptance); runtime=read(runtime_acceptance); resource=read(resource_acceptance)
    need(source['status']=='accepted' and source['source_manifest_sha256']==reg['source_manifest_sha256'],
         'independent source review not accepted for exact source manifest')
    need(runtime['status']=='accepted' and runtime['runtime_manifest_sha256']==reg['runtime_manifest_sha256'],
         'runtime review not accepted for exact runtime manifest')
    need(runtime['schema']=='one_frame_training_runtime_source_acceptance_v1'
         and runtime['scope']=='source_and_native_provenance_only_actual_training_qualification_pending'
         and runtime['source_manifest_sha256']==reg['source_manifest_sha256']
         and runtime['actual_training_qualification_required_for_formal'] is True,
         'runtime acceptance overclaims native training qualification')
    runtime_pins=runtime['pins']
    need(runtime_pins.get(runtime['review_path'])==runtime['review_sha256']
         and runtime_pins.get(reg['runtime_manifest_path'])==reg['runtime_manifest_sha256']
         and {Path(name).name for name in runtime['changed_python_members']}==
             {'ppo.py','seeded_training.py','curriculum.py'},
         'runtime review/native provenance pins differ')
    for path,digest in runtime_pins.items():
        need(sha(path)==digest,'runtime acceptance evidence pin drift: '+path)
    need(q['status']=='preparation_pending_source_acceptance' and q['launch_authority'] is False,
         'qualification protocol changed or gained launch authority')
    need(resource['schema']=='one_frame_training_comparison_resource_acceptance_v1'
         and resource['status']=='accepted_measured_projection'
         and resource['formal_protocol_sha256']==sha(HERE/'protocol.json')
         and resource['qualification_protocol_sha256']==sha(HERE/'qualification-protocol.json')
         and resource['qualification_registration_sha256']!=registration_sha256,
         'resource acceptance does not bind frozen protocols and separate qualification registration')
    need(reg['input_pins'].get(str(Path(resource_acceptance).resolve()))==resource_sha256,
         'final formal registration does not pin exact measured resource acceptance')
    need(resource['limits']==reg['limits']
         and resource['accepted_work_seconds']==protocol['limits']['work_seconds']==32400
         and resource['accepted_total_seconds']==protocol['limits']['total_seconds']==32530
         and 0<=resource['margin_included_seconds']<=32400,
         'accepted resource envelope or measured cost exceeds formal protocol')
    projection=resource['projection']
    need(all(type(projection[k]) in (int,float) and projection[k]>=0 for k in
         ('per_arm_seconds_per_gameplay_frame','training_seconds','evaluation_seconds',
          'checkpoint_seconds','margin_factor','margin_included_seconds'))
         and projection['margin_factor']>=1
         and projection['margin_included_seconds']==resource['margin_included_seconds']
         and projection['training_seconds']+projection['evaluation_seconds']
             +projection['checkpoint_seconds']+projection['margin_included_seconds']<=32400,
         'measured resource projection arithmetic exceeds nine-hour work cap')
    need('measured' in resource['claim_scope'].lower()
         and 'final efficacy' in resource['claim_scope'].lower(),
         'resource acceptance claim scope exceeds measured qualification')
    for path_key,sha_key in (('qualification_receipt_path','qualification_receipt_sha256'),
            ('qualification_parent_terminal_audit_path','qualification_parent_terminal_audit_sha256')):
        need(sha(resource[path_key])==resource[sha_key],
             'qualification parent evidence pin differs: '+path_key)
    qreceipt=read(resource['qualification_receipt_path'])
    qaudit_path=Path(resource['qualification_parent_terminal_audit_path'])
    qaudit=read(qaudit_path)
    qrelease=read(qaudit_path.parent/'lease-release.json')
    need(qreceipt['run_id']==q['run_id']
         and qreceipt['registration_sha256']==resource['qualification_registration_sha256']
         and qreceipt['no_checkpoint_writes'] is True and qreceipt['no_evaluation_seed_use'] is True
         and qreceipt['checkpoint_writes']==0 and qreceipt['evaluation_calls']==0
         and qaudit['run_id']==q['run_id']
         and qaudit['status']=='parent_terminal_audit_accepted'
         and qaudit['lease_cleared'] is False
         and qaudit['evidence']['status']=='qualification_complete'
         and qaudit['worker_result_sha256']==resource['qualification_receipt_sha256']
         and qrelease['run_id']==q['run_id']
         and qrelease['registration_sha256']==resource['qualification_registration_sha256']
         and qrelease['parent_terminal_audit_sha256']==resource['qualification_parent_terminal_audit_sha256']
         and qrelease['lease_value_after_release'] is None,
         'resource acceptance lacks exact accepted qualification receipt and parent audit')
    return dict(status='all_parent_gates_exact_and_present',run_id=protocol['run_id'],
        launch_authority=False,final_parent_launch_decision_pending=True,
        registration_sha256=registration_sha256,source_acceptance_sha256=source_sha256,
        runtime_acceptance_sha256=runtime_sha256,resource_acceptance_sha256=resource_sha256)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('registration','registration-sha256','source-acceptance','source-sha256',
                 'runtime-acceptance','runtime-sha256','resource-acceptance','resource-sha256'):
        parser.add_argument('--'+name,required=True)
    a=parser.parse_args(); print(json.dumps(validate(a.registration,a.registration_sha256,
        a.source_acceptance,a.source_sha256,a.runtime_acceptance,a.runtime_sha256,
        a.resource_acceptance,a.resource_sha256),sort_keys=True))
