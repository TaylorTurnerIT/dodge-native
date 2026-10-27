"""Evaluation adapters for the existing direct-owner watchdog; stdlib only."""
from __future__ import annotations
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT/'learning/runs/v2/progressive1000-opening-maintenance-runtime-parent-20261027-r1'
SOURCE_SHA = '51aa867e43b3a047f057ef07069c9939615d4a1db2939e484d0f974cac87b85e'
RUNTIME_SHA = '84e730ee638344460fe9bda693bc986879c39621fa7ef99ba35afd50b0f78b69'
STUDY = 'progressive1000-confirmed324-20261026-r1'
POLICIES = tuple(f'replica-{r}-{arm}' for r in (1,2,3) for arm in
    ('control_constant_3e-5','progressive1000_curriculum_constant_3e-5'))+('parent324',)
SEEDS = list(range(0xD3000000,0xD3000400))
CAP = 6*1024**3
RAW_CAP = 7168*(18000+13)
LIMITS = {}
GATES = ('independent_source_review','producer_identity','inference_compatibility',
         'cohort_reservation_and_freshness','resource_calibration','registered_rng',
         'supervisor_cleanup','registration','exactly_once')


class Cancelled(RuntimeError):
    pass


def need(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def sha(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):
            result.update(block)
    return result.hexdigest()


def read(path):
    def unique(items):
        result={}
        for key,value in items:
            need(key not in result,'duplicate JSON field: '+key)
            result[key]=value
        return result
    return json.loads(Path(path).read_bytes(),object_pairs_hook=unique,
        parse_constant=lambda value:(_ for _ in ()).throw(ValueError(value)))


def save(path,value):
    """Same durable exclusive publication used by the accepted supervisor."""
    path=Path(path)
    fd,staging=tempfile.mkstemp(prefix='.'+path.name+'.pending-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(value,stream,indent=2,sort_keys=True,allow_nan=False)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.link(staging,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:os.unlink(staging)


def check_pins(pins):
    for path,digest in pins.items():
        need(sha(path)==digest,'pin drift: '+path)


def contracts():
    need(sha(SOURCE/'source-manifest.json')==SOURCE_SHA,'clean evaluator source manifest differs')
    for name,digest in read(SOURCE/'source-manifest.json')['files'].items():
        path=SOURCE/name
        need(path.resolve().is_relative_to(SOURCE) and not path.is_symlink(),'source member escapes')
        need(sha(path)==digest,'clean evaluator source differs: '+name)
    sys.path.insert(0,str(SOURCE))
    c=importlib.import_module('contracts')
    need(Path(c.__file__).resolve()==SOURCE/'contracts.py','contracts origin differs')
    return c


def analysis():
    contracts()
    module=importlib.import_module('expanded_eval')
    need(Path(module.__file__).resolve()==SOURCE/'expanded_eval.py','analysis origin differs')
    return module


def verify_dependencies(reg):
    anchor=read(HERE/'dependency-binding.json')
    check_pins({anchor['registration_path']:anchor['registration_sha256'],
                anchor['inventory_path']:anchor['inventory_sha256']})
    old=read(anchor['registration_path']);inventory=read(anchor['inventory_path'])
    need(reg['interpreter']==old['interpreter'],'dependency interpreter differs')
    for path,item in inventory['pins'].items():
        need(old['pins'].get(path)==item['sha256']==sha(path),'dependency drift: '+path)
    executable=str(Path(reg['interpreter']).resolve(strict=True))
    need(sha(executable)==old['pins'][executable],'interpreter bytes differ')
    return dict(checked=len(inventory['pins']),scope=inventory['scope'])


def validate_limits(limits):
    need(set(limits)=={'work_seconds','total_seconds','cleanup_seconds','rss_bytes','mps_bytes',
         'raw_frames','resets','retries'},'evaluation limit fields differ')
    need(all(type(value)is int for value in limits.values()),'integer limits required')
    need(0<limits['work_seconds']<=86400 and limits['total_seconds']==limits['work_seconds']+10
         and limits['cleanup_seconds']==10,'wall/cleanup bounds differ')
    need(limits['rss_bytes']==limits['mps_bytes']==CAP and limits['raw_frames']==RAW_CAP
         and limits['resets']==0 and limits['retries']==0,'memory/raw/reset/retry bounds differ')


def check_lease(reg):
    state=read(reg['state_path'])
    need(state.get('active_long_campaign')==reg['expected_lease'],'exact parent evaluation lease changed')
    need(all(state.get(key)is None for key in ('active_inference_diagnostic','active_inference_campaign',
        'active_inference_lease')),'conflicting inference lease')


def producer_policy(policy,c,*,hash_checkpoint=True):
    """Check each accepted producer separately; legacy control1 stays explicit."""
    if policy['id']=='parent324':
        need(policy['checkpoint_sha256']==c.references.ACCEPTED_CHECKPOINT_SHA256
             and policy['producer'] is None,'shared parent differs')
    else:
        p=policy['producer'];check_pins(p['pins'])
        reg=read(p['registration_path']);audit=read(p['audit_path']);worker=read(p['worker_result_path'])
        registration_digest=sha(p['registration_path'])
        need(reg['run_id']==STUDY+'-'+policy['id'] and reg['backend']=='mps','producer identity differs')
        need(audit['status']=='integrity_accepted_pending_six_arm_comparison'
             and audit['completed_updates']==60 and audit['registration_sha256']==registration_digest
             and audit['raw_worker_exit_code']==audit['raw_observer_exit_code']==0
             and audit['postflight_inputs_dependencies_cache']=='passed','producer terminal audit differs')
        endpoint=audit['formal_comparison_endpoint']
        need(worker['status']=='completed' and worker['updates']==60 and worker['run_id']==reg['run_id']
             and worker['registration_sha256']==registration_digest and worker['formal_comparison_endpoint']==endpoint,
             'producer result/audit differ')
        need(endpoint['global_update']==60 and endpoint['phase_update']==384 and endpoint['cumulative_update']==432
             and endpoint['formal_comparison_endpoint'] is True and endpoint['promoted'] is False
             and endpoint['automatic_selection'] is False and endpoint['training_eligible'] is False
             and endpoint['path']==policy['checkpoint_path'] and endpoint['sha256']==policy['checkpoint_sha256'],
             'fixed terminal60 endpoint differs')
        source=Path(reg['runtime_root']).parent
        need(p['source_manifest_sha256']==reg['source_manifest_sha256']==sha(source/'source-manifest.json')
             and p['runtime_manifest_sha256']==reg['runtime_manifest_sha256']==sha(source/'runtime-manifest.json'),
             'actual producer manifest differs')
        actual=read(source/'runtime-manifest.json')['files'];clean=read(SOURCE/'runtime-manifest.json')['files']
        need(set(actual)==set(clean),'producer runtime membership differs')
        changes={name for name in actual if actual[name]!=clean[name]}
        need(changes<= {'dodge_rl/scheduler_reference.py'},'producer inference byte mismatch')
        for name,digest in actual.items():
            need(sha(source/'runtime'/name)==digest,'producer registered runtime byte drift: '+name)
        identity=importlib.import_module('successor_identity').learner_identity(reg,registration_digest)
        need(identity==p['expected_identity'],'producer expected learner identity differs')
        need(any(low<=SEEDS[0] and high>=SEEDS[-1] for low,high in reg['exclusion_union']),
             'producer did not exclude reserved evaluation cohort')
    if hash_checkpoint:
        need(sha(policy['checkpoint_path'])==policy['checkpoint_sha256'],'endpoint bytes drift')


def validate_static(reg,*,require_registered=True,hash_checkpoints=True):
    fields={'schema','status','run_id','study_id','backend','source_manifest_sha256','evaluator_source',
        'runtime_root','runtime_manifest_sha256','input_manifest_sha256','runtime_versions','policies',
        'seeds','exclusion_union','evaluation_rng_seed','bootstrap','semantics','limits','output',
        'attempt_claim_path','launch_marker_path','state_path','expected_lease','interpreter','import_policy',
        'input_pins','calibration','cohort_state','history_state','reservation_state'}
    need(type(reg)is dict and set(reg)==fields,'registration field set differs')
    need(reg['schema']=='progressive1000_full_evaluation_registration_v2' and reg['study_id']==STUDY,
         'evaluation schema/study differs')
    if require_registered:need(reg['status']=='parent_registered','draft is not launch authority')
    need(reg['backend']=='mps' and reg['evaluator_source']==str(SOURCE)
         and reg['runtime_root']==str(SOURCE/'runtime'),'clean common evaluator required')
    need(reg['seeds']==SEEDS and reg['semantics']==dict(difficulty=2,normal_start=True,action_repeat=4,
        raw_frame_cap=18000,cutoff_enabled=False,action_mode='sampled_categorical',row_count=1024,
        parent_evaluations=1,policies=7,planned_episodes=7168),'evaluation semantics differ')
    need(type(reg['evaluation_rng_seed'])is int and 0<reg['evaluation_rng_seed']<2**63,'fixed sampling seed required')
    need(reg['bootstrap']==dict(seed=2026102701,draws=2000,confidence=.95,unit='paired_evaluation_seed',
        training_seed_uncertainty='three_training_pairs_descriptive_only'),'bootstrap contract differs')
    need(reg['cohort_state']=='reserved_parent_approved' and reg['history_state']=='freshness_parent_approved'
         and reg['reservation_state']=='parent_reserved','cohort history/reservation not bound')
    validate_limits(reg['limits']);check_pins(reg['input_pins'])
    manifest=read(HERE/'source-manifest.json')
    need(sha(HERE/'source-manifest.json')==reg['source_manifest_sha256'],'owned source manifest differs')
    check_pins({str(HERE/name):digest for name,digest in manifest['files'].items()})
    c=contracts();c.verify_inputs()
    need(reg['runtime_manifest_sha256']==RUNTIME_SHA,'common runtime pin differs')
    c.verify_manifest(SOURCE/'runtime-manifest.json',RUNTIME_SHA,SOURCE/'runtime',exact=True)
    need(sha(SOURCE/'input-manifest.json')==reg['input_manifest_sha256'],'evaluation input manifest differs')
    need(reg['runtime_versions']==c.read(SOURCE/'input-manifest.json')['runtime_versions'],'dependency versions differ')
    c.validate_union(reg['exclusion_union'])
    need([p['id'] for p in reg['policies']]==list(POLICIES),'seven fixed policies/order required')
    for p in reg['policies']:
        need(set(p)=={'id','checkpoint_path','checkpoint_sha256','producer'},'policy fields differ')
        producer_policy(p,c,hash_checkpoint=hash_checkpoints)
    for key in ('output','attempt_claim_path','launch_marker_path','state_path','interpreter'):
        need(Path(reg[key]).is_absolute(),'absolute path required: '+key)
    need(Path(reg['output'])==HERE/'worker-output' and reg['attempt_claim_path']==str(HERE/'attempt.claimed')
         and reg['launch_marker_path']==str(HERE/'launch.claimed'),'fixed owned paths required')
    need(reg['state_path']==str(ROOT/'learning/runs/v2-orchestration/state.json')
         and reg['run_id']=='progressive1000-fixed-terminal-full-evaluation-20261027-r2',
         'parent ledger/run identity differs')
    lease=reg['expected_lease']
    need(type(lease)is dict and lease.get('kind')=='progressive1000_fixed_endpoint_evaluation'
         and lease.get('run_id')==reg['run_id'] and type(lease.get('owner_token'))is str
         and len(lease['owner_token'])==32 and lease.get('RSS_bytes')==lease.get('MPS_driver_bytes')==CAP,
         'exact resource lease missing')
    c.cache_check(reg)
    verify_dependencies(reg)
    need(reg['calibration']['parent_accepted'] is True if require_registered else True,
         'parent resource calibration acceptance missing')
    return reg


def validate_checkpoint(state,policy):
    if policy['id']=='parent324':
        need(state.get('phase_update')==324,'accepted parent phase differs')
        return
    need(state.get('schema')=='progressive1000_integrity_checkpoint_v1'
         and state.get('global_update')==60 and state.get('phase_update')==384
         and state.get('cumulative_update')==432,'terminal checkpoint counters differ')
    expected=policy['producer']['expected_identity']
    need(state.get('identity')==expected and state.get('identity_sha256')==hashlib.sha256(canonical(expected)).hexdigest(),
         'terminal checkpoint differs from its actual producer identity')
    need(state.get('promoted') is False and state.get('automatic_selection') is False
         and state.get('training_eligible') is False and state.get('formal_comparison_endpoint') is True,
         'checkpoint eligibility flags differ')


def load_envelope(path,digest):
    need(sha(path)==digest,'envelope external SHA differs')
    e=read(path)
    fields={'schema','status','registration','registration_sha256','launch_approval','launch_approval_sha256',
        'source_acceptance','source_acceptance_sha256','control','cancel_path','started','pins',
        'interpreter_resolved','interpreter_sha256'}
    need(set(e)==fields and e['schema']=='progressive1000_full_evaluation_envelope_v2'
         and e['status']=='parent_bound_exactly_one_run','inert envelope')
    reg=read(e['registration']);validate_limits(reg['limits'])
    LIMITS.clear();LIMITS.update(reg['limits'])
    need(Path(e['control'])==HERE/'dispatch'/reg['run_id'],'owned dispatch path differs')
    need(Path(e['cancel_path'])==HERE/'cancel','fixed cancel path differs')
    need(type(e['started'])in (int,float) and math.isfinite(e['started']),'finite start required')
    e['self_path']=str(Path(path).resolve());e['self_sha256']=digest
    return e,reg


def verify_bound(e,reg,*,preflight):
    check_pins(e['pins'])
    check_pins({e['registration']:e['registration_sha256'],e['launch_approval']:e['launch_approval_sha256'],
                e['source_acceptance']:e['source_acceptance_sha256']})
    validate_static(reg)
    gates=read(e['launch_approval'])
    need(gates['schema']=='progressive1000_full_evaluation_gate_acceptance_v2'
         and gates['status']=='approved_exactly_once_fixed_full_run_evaluation'
         and gates['registration_sha256']==e['registration_sha256']
         and gates['gates']==dict.fromkeys(GATES,'passed'),'external parent gates missing')
    need(read(e['source_acceptance'])['source_manifest_sha256']==reg['source_manifest_sha256'],
         'independent reviewed source manifest differs')
    check_lease(reg);need(not os.path.lexists(e['cancel_path']),'parent cancellation present')
    need(str(Path(reg['interpreter']).resolve())==e['interpreter_resolved']
         and sha(e['interpreter_resolved'])==e['interpreter_sha256'],'executable differs')
    if preflight:
        need(not os.path.lexists(reg['output']) and not os.path.lexists(reg['attempt_claim_path']),
             'worker attempt already spent')
    need(read(reg['launch_marker_path'])==dict(schema='progressive1000_evaluation_spent_marker_v2',
        registration_sha256=e['registration_sha256'],run_id=reg['run_id'],started=e['started']),
        'parent spent marker differs')


def worker_command(envelope,reg):
    return [reg['interpreter'],'-B',str(HERE/'worker.py'),'--envelope',envelope['self_path'],
            '--envelope-sha256',envelope['self_sha256']]


def worker_resources(out,*,strict=False):
    path=Path(out)/'resources.jsonl';value=dict(samples=0,peak_rss_bytes=None,peak_mps_driver_bytes=None)
    if not path.is_file():return value
    for line in path.read_text().splitlines(keepends=True):
        if not line.endswith('\n'):
            need(not strict,'torn resource journal');break
        row=json.loads(line)
        need(all(type(row[k])is int and row[k]>=0 for k in ('rss_bytes','mps_driver_bytes')),
             'invalid resource row')
        value['samples']+=1
        value['peak_rss_bytes']=max(value['peak_rss_bytes'] or 0,row['rss_bytes'])
        value['peak_mps_driver_bytes']=max(value['peak_mps_driver_bytes'] or 0,row['mps_driver_bytes'])
    return value
