"""Fail-closed successor identity and parent-owned launch preflight; stdlib only."""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import rng_reference as references
import transition

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
STUDY = 'progressive1000-confirmed324-20261026-r1'
ARMS = ('control_constant_3e-5', 'progressive1000_curriculum_constant_3e-5')
PARENT_RECEIPT = 'learning/runs/v2/D2-retained300-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json'
PPO = dict(gamma=.995, gae_lambda=.95, learning_rate=3e-5, adam_eps=1e-5,
           clip_coef=.2, vf_coef=.5, ent_coef=.01, max_grad_norm=.5,
           update_epochs=4, minibatch_size=512, target_kl=.03, reward_scale=.1)
SCHEDULE = dict(updates=60, cumulative_origin=372, cumulative_first=373,
                cumulative_last=432, phase_start=325, phase_end=384,
                integrity_local_updates=[12,24,36,48,60], formal_evaluation_local_updates=[60],
                candidate_selection=False, promotion=False, final_drain=False)
PROBE_SCHEDULE = dict(SCHEDULE,updates=24,cumulative_last=396,phase_end=348,
    integrity_local_updates=[12,24],formal_evaluation_local_updates=[])
GATES = ('independent_source_review','trusted_restore_qualification','new_vector_CPU_MPS_references',
         'seed_history_freshness','seed_reservation','disabled_cutoff_release_parity',
         'release_runtime_qualification','resource_calibration','supervisor_cleanup',
         'registration','one_shot_launch')
REG_FIELDS = {'schema','status','study_id','run_id','pair_id','replica','arm','backend','curriculum_enabled',
              'vector','reference','reference_approval','initial_episode_indices','exclusion_union',
              'parent_checkpoint_sha256','parent_receipt_sha256','expected_parent_fingerprints',
              'runtime_root','runtime_versions','source_manifest_sha256','runtime_manifest_sha256',
              'input_manifest_sha256','shared_config','ppo','schedule','output','attempt_claim_path',
              'interpreter','import_policy','state_path','expected_lease','launch_marker_path',
              'limits','cohort_state','history_state','reservation_state','purpose'}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    def unique(items):
        result={}
        for key,value in items:
            need(key not in result,'duplicate JSON field: '+key)
            result[key]=value
        return result
    return json.loads(Path(path).read_bytes(),object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def validate_union(ranges):
    need(type(ranges) is list and len(ranges)>=6,'full future exclusion union requires at least six ranges')
    rows=[]
    for row in ranges:
        need(type(row) is list and len(row)==2 and all(type(v) is int for v in row)
             and 0<=row[0]<=row[1]<=2**32-1,'invalid exclusion range')
        rows.append(tuple(row))
    need(rows==sorted(rows) and all(a[1]+1<b[0] for a,b in zip(rows,rows[1:])),
         'exclusion union must be sorted, disjoint and merged')
    need(all(any(lo<=a and hi>=b for lo,hi in rows) for a,b in transition.EXPECTED_EXCLUSION_RANGES),
         'historical/new-cohort union missing')
    need(rows!=[(0,2**32-1)],'exclusion union exhausts u32')
    return rows


def episode_controls(vector,indices,ranges):
    """Same native SplitMix64 domain; reject the full union before construction."""
    ranges=validate_union(ranges)
    transition.validate_seeds(vector['seeds'])
    need(type(indices) is list and len(indices)==64 and all(type(v)is int and 0<=v<2**64-1 for v in indices),
         'exact 64 parent next episode indices required')
    master=vector['seeds']['env_master_seed']
    result=[dict(slot=slot,episode_index=episode,**seed_metadata(master,slot,episode,ranges))
            for slot,episode in enumerate(indices)]
    need(len({r['first_actual_seed'] for r in result})==64,'initial actual seed collision')
    return result


def seed_metadata(master,slot,episode,ranges):
    """Exact native high32 tuple hash, including counter rejection; no RNG draws."""
    need(type(master)is int and 0<=master<2**64 and type(slot)is int and 0<=slot<64
         and type(episode)is int and 0<=episode<2**64,'invalid seed tuple')
    mask=(1<<64)-1
    def mix(value):
        value &= mask
        value=((value^(value>>30))*0xBF58476D1CE4E5B9)&mask
        value=((value^(value>>27))*0x94D049BB133111EB)&mask
        return value^(value>>31)
    base=mix(master ^ 0x444F4447455F5632) ^ mix(slot+0x9E3779B97F4A7C15) ^ mix(episode+0xD1B54A32D192ED03)
    for counter in range(100000):
        seed=mix(base ^ mix(counter+0x94D049BB133111EB))>>32
        if not any(lo<=seed<=hi for lo,hi in ranges):
            return dict(first_actual_seed=seed,rejection_counter=counter)
    raise ValueError('bounded seed rejection exhausted; no alternate tuple or retry')


def verify_manifest(path,expected,root,exact=False):
    need(sha(path)==expected,'manifest SHA differs: '+str(path))
    value=read(path)
    files=value['files']
    for rel,digest in files.items():
        member=Path(root)/rel
        need(member.resolve().is_relative_to(Path(root).resolve()) and not member.is_symlink(), 'member escapes root')
        need(sha(member)==digest,'source/native pin drift: '+rel)
    if exact:
        actual={str(p.relative_to(root)) for p in Path(root).rglob('*') if p.is_file()}
        need(actual==set(files),'runtime member set drift')
    return value


def verify_inputs():
    manifest=read(HERE/'input-manifest.json')
    need(manifest['root']==str(ROOT),'checkout identity changed')
    for path,digest in manifest['pins'].items():
        need(sha(path)==digest,'frozen input drift: '+path)
    import driver_binding
    driver_binding.verify_pinned_sources(ROOT)
    # Checkpoint and identity bytes are copied unchanged, though origins are new.
    for rel in ('dodge_rl/checkpoints.py','dodge_rl/identity.py','dodge_rl/models/teacher.py'):
        need(sha(HERE/'runtime'/rel)==sha(Path(manifest['parent_runtime_root'])/rel),
             'unchanged accepted definition differs: '+rel)
    return manifest


def validate_static(reg):
    """All pending/unapproved state fails before imports, bootstrap, claim or restore."""
    need(type(reg) is dict and set(reg)==REG_FIELDS,'registration fields differ')
    need(reg['schema']=='progressive1000_worker_registration_v1' and reg['status']=='parent_registered',
         'inert template is not parent registration')
    need(reg['purpose'] in ('matched_comparison','timing_probe24'),'unregistered run purpose')
    if reg['purpose']=='timing_probe24':
        need(reg['replica']==1 and reg['arm']==ARMS[0],'timing probe requires fixed replica1 control')
    need(reg['study_id']==STUDY and type(reg['replica'])is int and 1<=reg['replica']<=3,'study/replica differs')
    need(reg['arm'] in ARMS and reg['curriculum_enabled'] is (reg['arm']==ARMS[1]),'arm/enablement differs')
    need(reg['run_id']==f"{STUDY}-replica-{reg['replica']}-{reg['arm']}"
         and reg['pair_id']==f"{STUDY}-replica-{reg['replica']}",'declared run/pair identity differs')
    # Accepted parent RNG contains MPS state. CPU is supported by PreparedUpdates
    # for controls; restoring this accepted MPS parent on CPU is not qualified.
    need(reg['backend']=='mps','accepted324 restore requires registered MPS backend')
    need(reg['cohort_state']=='reserved_parent_approved' and reg['history_state']=='freshness_parent_approved'
         and reg['reservation_state']=='parent_reserved','pending/unreserved/unapproved cohort/history state')
    need(reg['parent_checkpoint_sha256']==references.ACCEPTED_CHECKPOINT_SHA256
         and reg['parent_receipt_sha256']==references.PARENT_RECEIPT_SHA256
         and reg['expected_parent_fingerprints']==transition.EXPECTED_PARENT,'accepted parent identity differs')
    manifest=verify_inputs()
    need(sha(HERE/'input-manifest.json')==reg['input_manifest_sha256'],'input manifest pin drift')
    verify_manifest(HERE/'source-manifest.json',reg['source_manifest_sha256'],HERE)
    runtime=verify_manifest(HERE/'runtime-manifest.json',reg['runtime_manifest_sha256'],HERE/'runtime',exact=True)
    need(reg['runtime_root']==str(HERE/'runtime') and reg['runtime_versions']==manifest['runtime_versions'],
         'shared runtime/version differs')
    need(read(HERE/'binary-manifest.json')['profile']=='release'
         and read(HERE/'binary-manifest.json')['sha256']==runtime['files']['dodge_rl/_native.cpython-312-darwin.so'],
         'release binary missing or differs')
    proposal=read(HERE/'seed-vectors.json'); vector=proposal['vectors'][reg['replica']-1]
    need(reg['vector']==vector and references.canonical_vector_sha256(STUDY,reg['replica'],vector['seeds'])==vector['vector_sha256'],
         'new full vector differs; LR references forbidden')
    need(reg['initial_episode_indices']==proposal['parent']['next_episode_indices'],'accepted324 slot offsets differ')
    expected_schedule=PROBE_SCHEDULE if reg['purpose']=='timing_probe24' else SCHEDULE
    expected_config=read(HERE/'shared-config.json')
    expected_config.update(schedule=expected_schedule,global_updates=expected_schedule['updates'])
    need(reg['ppo']==PPO and reg['schedule']==expected_schedule and reg['shared_config']==expected_config,
         'shared optimization/config/budget differs')
    controls=episode_controls(vector,reg['initial_episode_indices'],reg['exclusion_union'])
    reference=reg['reference']; need(type(reference)is dict and set(reference)=={'receipt_path','receipt_sha256','vector_sha256'},'independent reference missing')
    need(reference['vector_sha256']==vector['vector_sha256'],'reference vector differs')
    references.load_bound_reference(receipt_path=reference['receipt_path'],expected_receipt_sha256=reference['receipt_sha256'],
        expected_study_id=STUDY,expected_replica=reg['replica'],expected_seed_vector=vector['seeds'],
        expected_vector_sha256=vector['vector_sha256'],expected_torch_version=reg['runtime_versions']['torch'])
    approval=reg['reference_approval']
    need(type(approval)is dict and set(approval)=={'path','sha256'},'independent reference parent approval missing')
    need(sha(approval['path'])==approval['sha256'],'reference approval pin drift')
    need(read(approval['path'])==dict(schema='progressive1000_independent_reference_approval_v1',
         status='parent_approved_independent_measurement',study_id=STUDY,replica=reg['replica'],
         vector_sha256=vector['vector_sha256'],receipt_sha256=reference['receipt_sha256']), 'unapproved reference')
    limits=reg['limits']; keys={'work_seconds','total_seconds','cleanup_seconds','rss_bytes','mps_bytes','raw_frames','resets','retries'}
    need(type(limits)is dict and set(limits)==keys and limits['retries']==0,'resource limits missing')
    need(all(type(limits[k])is int and limits[k]>0 for k in keys-{'retries'})
         and limits['work_seconds']+limits['cleanup_seconds']<=limits['total_seconds'],'unmeasured/invalid resource limits')
    for key in ('output','attempt_claim_path','launch_marker_path','state_path'):
        need(type(reg[key])is str and Path(reg[key]).is_absolute(),'absolute parent path required: '+key)
    need(not Path(reg['output']).exists() and not Path(reg['attempt_claim_path']).exists(),'one-shot output/claim spent')
    need(reg['expected_lease'] is not None and read(reg['state_path']).get('active_long_campaign')==reg['expected_lease'],
         'parent lease missing/changed')
    parent=read(ROOT/PARENT_RECEIPT)
    need(parent['checkpoint_sha256']==references.ACCEPTED_CHECKPOINT_SHA256,'parent receipt checkpoint differs')
    return dict(manifest=manifest,parent=parent,controls=controls,runtime_manifest=runtime)


def cache_check(reg):
    policy=reg['import_policy']
    need(type(policy)is dict and set(policy)=={'pycache_prefix','dont_write_bytecode'}
         and policy['dont_write_bytecode'] is True,'import policy differs')
    path=Path(policy['pycache_prefix'])
    need(path.is_absolute() and path.is_dir() and not any(path.iterdir()),'registered cache must exist empty')
    need(sys.dont_write_bytecode and sys.pycache_prefix==str(path)
         and os.environ.get('PYTHONPYCACHEPREFIX')==str(path),'process cache policy differs')
    need(str(Path(sys.executable).absolute())==reg['interpreter'],'registered interpreter differs')


def preflight(path,digest,approval_path,approval_sha,started):
    need(sha(path)==digest and sha(approval_path)==approval_sha,'external parent gate SHA differs')
    reg=read(path)
    context=validate_static(reg)
    approval=read(approval_path)
    need(approval==dict(schema='progressive1000_parent_launch_approval_v1',status='approved_exactly_one_registered_run',
         registration_sha256=digest,source_manifest_sha256=reg['source_manifest_sha256'],
         runtime_manifest_sha256=reg['runtime_manifest_sha256'],run_id=reg['run_id'],gates=dict.fromkeys(GATES,'passed')),
         'later parent gates missing; NO launch authority')
    need(type(started) in (int,float) and math.isfinite(started)
         and 0<=time.monotonic()-started<reg['limits']['work_seconds'],'parent monotonic start differs')
    need(read(reg['launch_marker_path'])==dict(schema='progressive1000_parent_spent_launch_marker_v1',
         registration_sha256=digest,run_id=reg['run_id'],started=started),'parent-spent launch marker differs')
    cache_check(reg)
    need(sha(path)==digest and sha(approval_path)==approval_sha,'parent gate changed during preflight')
    return reg,context
