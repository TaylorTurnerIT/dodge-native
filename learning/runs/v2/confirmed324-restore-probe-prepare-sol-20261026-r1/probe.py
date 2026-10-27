"""Replica-1 accepted restore probe contract. Imports are stdlib only.

This module is not launch authority. The supervisor requires a separately frozen,
parent-approved registration and exact lease before consuming its outer marker.
"""
from __future__ import annotations
import builtins
import gc
import hashlib
import inspect
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import sys
import time
import types

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BASE=HERE.parent
R3=BASE/'confirmed324-worker-event-repair-sol-20261026-r3'
R3_SHA='5cb2cdf6bb857473600c7671caa579bb9d49bd3b3bc573ee4c76d635508757ab'
R5=BASE/'confirmed324-private-bindings-r5-parent-validation-20261026-r1/source-manifest.json'
R5_SHA='2b0caf00a5d5e765726d080fd5647211190e472d74ffb33b3466e477cb2906a9'
STUDY='paired-lr-confirmed324-20261026-r1'
ARM='A_constant_3e-5'
PARENT='c10d90ec0e67503afef8f4d90c4968581d430ef2065117a75e81c445a04c8ddc'
PARENT_RECEIPT='76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08'
ACCEPTANCE='3e84979c4c8da76d0f98666a23f90eb15c1e813ca5edf1001e19daebaf4d5bbd'
EXPECTED={'model':'3b72815fef4d8fa0084044739f5a5eaf9f74971b36dff9d8b26ed3bea5c562bc','Adam':'cf5e2a7ac5d3f7f131a26f7c2b8b778b7692850cff606a0ea9080941b960451c','RNG':'cb96ee8d2c40114a51abb8031dc7457a6da6d1be7262c6a4859bd34cab5813af'}
SCHEMA='confirmed324_claimed_restore_probe_registration_v1'
RESULT_SCHEMA='confirmed324_claimed_restore_probe_result_v1'
LIMITS={'work_seconds':45,'outer_seconds':55,'cleanup_seconds':10,'startup_grace_seconds':12,'RSS_bytes':6442450944,'MPS_driver_bytes':6442450944,'guard_poll_seconds':.2,'heartbeat_stale_seconds':2.0}
SCOPE={'model_constructed':True,'Adam_constructed':True,'checkpoint_deserialized':True,'replicas':[1],'environment_constructions':0,'rollouts':0,'forwards':0,'optimizer_steps':0,'candidate_saves':0,'training_updates':0,'qualification':'replica-1 only; parent audit required','automatic_retry':False}
FIELDS={'schema','status','authority','run_id','study_id','source','runtime','vectors_path','vectors_sha256','vectors','checkpoint_path','checkpoint_sha256','parent_receipt_path','parent_receipt_sha256','acceptance_path','acceptance_sha256','state_path','expected_lease','one_shot_marker','cancel_path','output_dir','limits','references','replica','arm','pair_id','vector','reference','attempt_claim_path','input_manifest_path','input_manifest_sha256','expected_parent_fingerprints','scope','budget_semantics'}
MODULES=('fingerprints','rng_reference','attempt_claim','transition','driver_binding','contracts','runtime_adapter')
RESULT_FIELDS={'schema','status','run_id','registration_sha256','study_id','replica','arm','vector_sha256','reference','parent_fingerprints','snapshots','transition','events','counts','runtime','cleanup','scope','resources'}

def need(ok,message):
    if not ok: raise ValueError(message)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()
def read(path):
    def unique(pairs):
        d={}
        for k,v in pairs:
            need(k not in d,'duplicate JSON field: '+k); d[k]=v
        return d
    return json.loads(Path(path).read_bytes(),object_pairs_hook=unique,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def verified(path,digest):
    raw=Path(path).read_bytes(); need(hashlib.sha256(raw).hexdigest()==digest,'source buffer pin mismatch: '+str(path)); return raw

def private_modules():
    """Load exact R3 source buffers under private identities, including local imports.

    No sys.path insertion for worker modules, no worker/worker_cli execution, no
    edits to accepted code objects, globals, classes or API contracts.
    """
    manifest=json.loads(verified(R3/'source-manifest.json',R3_SHA))
    authoritative=json.loads(verified(R5,R5_SHA))
    for name in ('attempt_claim','driver_binding','fingerprints','rng_reference','transition'):
        original=next(h for p,h in authoritative['files'].items() if Path(p).name==name+'.py')
        need(manifest['files'][name+'.py']==original,'R5 binding differs')
    loaded={}
    original_import=builtins.__import__
    def local_import(name,globals=None,locals=None,fromlist=(),level=0):
        if level==0 and name in MODULES: return load(name)
        return original_import(name,globals,locals,fromlist,level)
    def load(name):
        if name in loaded: return loaded[name]
        path=R3/(name+'.py'); raw=verified(path,manifest['files'][name+'.py'])
        module=types.ModuleType('_restore_probe_r3_'+name); module.__file__=str(path)
        module.__dict__['__builtins__']=dict(vars(builtins),__import__=local_import)
        loaded[name]=module; sys.modules[module.__name__]=module
        exec(compile(raw,str(path),'exec'),module.__dict__)
        return module
    for name in MODULES: load(name)
    return loaded

def verify_immutable(reg):
    manifest=json.loads(verified(reg['input_manifest_path'],reg['input_manifest_sha256']))
    need(manifest['schema']=='confirmed324_restore_probe_read_only_inputs_v1' and manifest['root']==str(ROOT),'input manifest binding')
    for p,h in manifest['pins'].items(): need(sha(p)==h,'immutable input drift: '+p)
    need(sha(R3/'source-manifest.json')==R3_SHA and sha(R5)==R5_SHA,'accepted source manifest drift')
    for p,h in read(R5)['files'].items(): need(sha(p)==h,'authoritative R5 member drift: '+p)
    r3=read(R3/'source-manifest.json')
    for name,h in r3['files'].items(): need(sha(R3/name)==h,'accepted R3 member drift: '+name)
    review=read(BASE/'confirmed324-worker-events-r3-review-sol-20261026-r2/receipt.json')
    need(review['findings']==[] and review['test_evidence']['parent_reported_tests']==43,'accepted R3 review gate differs')
    runtime=read(R3/'input-manifest.json')
    root=Path(runtime['runtime_root'])
    expected={p:h for p,h in runtime['pins'].items() if p.startswith(str(root.relative_to(ROOT))+'/')}
    actual={str(p.relative_to(ROOT)) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    need(set(expected)==actual,'runtime member set differs')
    for p,h in expected.items(): need(sha(ROOT/p)==h,'runtime member drift: '+p)
    producing=read(BASE/'D2-retained300-continuation-freeze-20261026-r5/registration.json')
    need({str((ROOT/p).relative_to(root)):h for p,h in expected.items()}==producing['runtime_continuity']['member_sha256'],'accepted runtime lineage differs')
    need(reg['runtime']['runtime_root']==str(root) and runtime['runtime_versions']==producing['runtime_versions']=={'python':reg['runtime']['python_version'],'numpy':reg['runtime']['numpy_version'],'torch':reg['runtime']['torch_version']},'runtime versions/root differ')
    need(sha(reg['vectors_path'])==reg['vectors_sha256']=='33ada951394fd3ce674955d43de1919b1cd3c2192e066722e33d5b49549c070b','vector source drift')
    vectors=read(reg['vectors_path']); need(vectors==reg['vectors'] and vectors['study_id']==STUDY,'vector content/study differs')
    vector=next(v for v in vectors['vectors'] if type(v['replica']) is int and v['replica']==1)
    need(reg['vector']==vector,'replica-1 full vector differs')
    parent=read(reg['parent_receipt_path']); acceptance=read(reg['acceptance_path'])
    for name,h in (('checkpoint',PARENT),('parent_receipt',PARENT_RECEIPT),('acceptance',ACCEPTANCE)):
        need(reg[name+'_sha256']==h and sha(reg[name+'_path'])==h,'accepted '+name+' pin differs')
    need(acceptance['status']=='accepted_checkpoint324_replaces348_by_registered_fresh_confirmation' and acceptance['retained_update']==324 and acceptance['checkpoint_sha256']==PARENT and acceptance['source_integrity_receipt_sha256']==PARENT_RECEIPT and acceptance['candidate_cumulative_counters']==parent['candidate_cumulative_counters'],'accepted confirmation binding differs')
    need(parent['checkpoint_sha256']==PARENT and parent['candidate_phase_update']==324 and parent['candidate_cumulative_counters']['updates']==372,'accepted parent counters differ')
    need(parent['learner_fingerprints']=={'model':EXPECTED['model'],'optimizer':EXPECTED['Adam'],'rng':EXPECTED['RNG']} and vector['env_control']['episode_indices']==parent['next_episode_indices'],'accepted parent state differs')
    refroot=BASE/'confirmed324-rng-reference-parent-20261026-r3'
    audit=read(refroot/'parent-terminal-audit.json')
    need(audit['status']=='accepted_three_initial_CPU_MPS_generator_references' and audit['registration_sha256']=='0150cfcdbec53ff4322f72e5fa224cb6a914f3505ea732c0722511b5e031c398','reference parent gate differs')
    accepted=next(r for r in audit['references'] if r['replica']==1)
    reference={'receipt_path':accepted['path'],'receipt_sha256':accepted['sha256'],'vector_sha256':accepted['vector_sha256']}
    need(reg['reference']==reference and reg['references']=={'required_replicas':[1],'kind':'existing_initial_CPU_MPS_state_reference'},'replica-1 reference binding differs')
    m=private_modules(); c=m['contracts']; c.binding.verify_pinned_sources(ROOT)
    c.transition.validate_seeds(vector['seeds'])
    m['rng_reference'].load_bound_reference(receipt_path=reference['receipt_path'],expected_receipt_sha256=reference['receipt_sha256'],expected_study_id=STUDY,expected_replica=1,expected_seed_vector=vector['seeds'],expected_vector_sha256=vector['vector_sha256'],expected_torch_version=reg['runtime']['torch_version'])
    return m,dict(manifest=runtime,parent=parent,vector=vector)

def preflight(rp,rsha,reg,worker,*,worker_phase=False):
    need(sha(rp)==rsha and read(rp)==reg,'external registration SHA/content mismatch')
    need(type(reg) is dict and set(reg)==FIELDS,'restore-probe registration fields mismatch')
    need(reg['schema']==SCHEMA and reg['status']=='parent_registered' and reg['authority']=='parent_approved_one_shot','parent registration/approval absent')
    need(type(reg['replica']) is int and reg['replica']==1 and reg['arm']==ARM and reg['study_id']==STUDY and reg['pair_id']==STUDY+'-replica-1','replica-1 paired LR identity required')
    need(reg['expected_parent_fingerprints']==EXPECTED and reg['scope']==SCOPE and reg['limits']==LIMITS,'probe state/scope/limits differ')
    need(reg['budget_semantics']=='45s work within 55s outer decisions; cleanup <=10s remaining; no hard filesystem watchdog','budget semantics differ')
    need(type(reg['run_id']) is str and reg['run_id'].startswith('confirmed324-restore-probe-') and 'PENDING' not in reg['run_id'],'new unique probe run identity required')
    need(Path(worker)==HERE/'worker_cli.py','dedicated restore worker required')
    for name,path in {'worker':HERE/'worker_cli.py','supervisor':HERE/'supervisor_cli.py','probe':HERE/'probe.py','fingerprint':R3/'fingerprints.py'}.items():
        need(Path(reg['source'][name+'_path'])==path and sha(path)==reg['source'][name+'_sha256'],'probe source pin differs: '+name)
    need(reg['source']['cleanup_primitives_sha256']=='4a5d084359ee48fe5351c96e0ec4455fdcd95a428a17bbcf59d0653f6922de98','cleanup pin differs')
    rt=reg['runtime']; exe=ROOT/'python/.venv/bin/python'
    need(Path(rt['python_path'])==exe and Path(sys.executable).absolute()==exe and sys.prefix==rt['expected_venv_prefix']==str(exe.parent.parent) and sys.version.split()[0]==rt['python_version']=='3.12.15' and sha(exe)==rt['interpreter_sha256'],'interpreter invocation/prefix/version differs')
    cache=Path(rt['empty_cache_path'])
    need(cache.is_dir() and not any(cache.iterdir()) and sys.dont_write_bytecode and sys.pycache_prefix==str(cache) and os.environ.get('PYTHONPYCACHEPREFIX')==str(cache),'owned empty cache policy differs')
    need(rt['torch_version']=='2.14.1' and rt['numpy_version']=='2.5.4','dependency versions differ')
    paths=[Path(reg[k]) for k in ('one_shot_marker','cancel_path','output_dir','attempt_claim_path')]
    need(all(p.is_absolute() and p.resolve()==p for p in paths) and len(set(paths))==4,'probe destinations must be distinct absolute paths')
    marker,cancel,out,claim=paths
    need(out.parent.is_dir() and marker.parent==claim.parent==cancel.parent==out.parent,'parent registration directory must exist')
    need(claim.name==reg['run_id']+'.restore.claimed' and marker.name==reg['run_id']+'.outer.claimed' and out.name==reg['run_id'],'unique registered destination names differ')
    need(not cancel.exists(),'cancel present')
    if worker_phase:
        mark=read(marker); need(mark.get('run_id')==reg['run_id'] and mark.get('registration_sha256')==rsha,'outer marker binding differs')
        allowed={'worker.log','worker-heartbeat.json','events.jsonl','resources.jsonl','worker-failure.json'}
        need(out.is_dir() and all(p.name in allowed or p.name.startswith('worker-heartbeat.json.tmp.') for p in out.iterdir()),'worker output collision')
    else: need(not marker.exists() and not claim.exists() and not out.exists(),'spent marker/subclaim or output collision')
    state=read(reg['state_path']); lease=reg['expected_lease']
    need(type(lease) is dict and lease.get('run_id')==reg['run_id'] and lease.get('study_id')==STUDY and lease.get('kind')=='confirmed324_claimed_restore_probe' and lease.get('parent_checkpoint_sha256')==PARENT and type(lease.get('owner_token')) is str and lease['owner_token'] and 'PENDING' not in lease['owner_token'],'restore-probe lease identity differs')
    need(state.get('active_inference_diagnostic')==lease and all(state.get(k) in (None,False) for k in ('active_long_campaign','active_long','active_inference')),'exact probe lease absent/conflicting')
    verify_immutable(reg)
    return state

def adapter_subset(reg,context):
    """Only fields read by R3 __init__/validate_parent/bootstrap/source.

    This is explicitly not a paired_confirmed324_worker_registration_v2. R3's
    training verify_registration and 1790/1800 limits are never called or reused.
    """
    return dict(runtime_root=reg['runtime']['runtime_root'],runtime_versions={'python':reg['runtime']['python_version'],'numpy':reg['runtime']['numpy_version'],'torch':reg['runtime']['torch_version']},initial_episode_indices=context['parent']['next_episode_indices'],vector=reg['vector'])

def snapshot(adapter,modules):
    fp=modules['fingerprints'].fingerprint; raw=adapter.callbacks['rng_capture']()
    need(type(raw) is dict and set(raw)==modules['driver_binding'].RAW_RNG_KEYS and raw['numpy_generator'] is None and raw['sampling_backend']=='torch_global_mps','raw six-key RNG contract differs')
    return dict(model=fp(adapter.model.state_dict()),Adam=fp(adapter.optimizer.state_dict()),RNG=fp(raw),raw_components={k:fp(v) for k,v in raw.items()},lr=[g['lr'] for g in adapter.optimizer.param_groups])

def run_claimed(reg,context,modules,adapter,event):
    """Exactly one accepted transition; no environment or training entrypoint."""
    t=modules['transition']; fp=modules['fingerprints'].fingerprint
    need(type(adapter) is modules['runtime_adapter'].RuntimeAdapter,'exact pinned RuntimeAdapter class required')
    need(not Path(reg['attempt_claim_path']).exists(),'transition subclaim already spent')
    counts=dict(restores=0,environment_constructions=0,rollouts=0,forwards=0,optimizer_steps=0,candidate_saves=0,training_updates=0)
    snapshots={}; old=sys.getprofile()
    adapter._probe_partial=dict(counts=counts,snapshots=snapshots)
    forbidden={'make_env':'environment_constructions','VecDodgeEnv':'environment_constructions','collect_rollout':'rollouts','ppo_update':'training_updates','forward':'forwards','step':'optimizer_steps','candidate':'candidate_saves','save_checkpoint':'candidate_saves','update':'training_updates'}
    def profile(frame,kind,arg):
        name=frame.f_code.co_name if kind in ('call','return') else getattr(arg,'__name__','')
        # Only the accepted adapter/runtime methods and learner methods are banned;
        # stdlib dict.update is harmless and must not be classified as PPO.
        if kind=='call' and name in forbidden and (name!='update' or frame.f_code is modules['runtime_adapter'].RuntimeAdapter.update.__code__):
            counts[forbidden[name]]+=1; raise RuntimeError('forbidden probe call: '+name)
        if kind=='call' and name=='restore_learner':
            counts['restores']+=1
            need(counts['restores']==1,'multiple accepted restore calls')
            claim_record=claim_identity(reg)
            need(Path(reg['attempt_claim_path']).read_bytes()==modules['attempt_claim'].canonical_claim(claim_record),'durable subclaim required before restore')
            event('accepted_restore_enter')
        callbacks=getattr(adapter,'callbacks',None)
        if kind=='return' and callbacks and frame.f_code is callbacks['restore_trusted'].__code__:
            snapshots['restored_before_reseed']=snapshot(adapter,modules)
            need({k:snapshots['restored_before_reseed'][k] for k in EXPECTED}==EXPECTED,'live accepted restore fingerprint differs')
            event('accepted_restore_verified')
        if kind=='call' and frame.f_code is t.controller_lr.__code__ and 'reseeded_before_lr' not in snapshots:
            snapshots['reseeded_before_lr']=snapshot(adapter,modules); event('study_reseed_verified_before_lr')
    sys.setprofile(profile)
    try:
        adapter.bootstrap(); event('disposable_bootstrap_complete')
        snapshots['disposable_bootstrap']=snapshot(adapter,modules)
        need(not Path(reg['attempt_claim_path']).exists(),'bootstrap must precede subclaim')
        need(not inspect.signature(adapter.callbacks['restore_trusted']).parameters,'trusted restore must be zero argument')
        seeds=reg['vector']['seeds']
        result=t.transition(session=t.TransitionSession(),attempt_claim=modules['attempt_claim'].AttemptClaim(reg['attempt_claim_path'],claim_identity(reg)),backend='mps',seeds=seeds,pair=dict(pair_id=reg['pair_id'],A=dict(seeds),B=dict(seeds)),verify_trusted_source=adapter.source,restore_trusted=adapter.callbacks['restore_trusted'],model=adapter.model,optimizer=adapter.optimizer,rng_capture=adapter.callbacks['rng_capture'],pinned_rng_reference=reg['reference'],python_api=random,numpy_api=adapter.np.random,torch_api=adapter.torch,pair_id=reg['pair_id'],arm=reg['arm'],study_id=STUDY,replica=1,torch_version=reg['runtime']['torch_version'],run_id=reg['run_id'])
    finally: sys.setprofile(old)
    need(counts['restores']==1 and all(v==0 for k,v in counts.items() if k!='restores'),'probe call counts differ')
    snapshots['post_lr']=snapshot(adapter,modules)
    need(result['parent_fingerprints']==EXPECTED and result['fingerprint_contract_status']=='concrete state_dict fingerprints verified','R5 result contract differs')
    ref=read(reg['reference']['receipt_path'])
    for name in ('reseeded_before_lr','post_lr'):
        snap=snapshots[name]
        need(snap['model']==EXPECTED['model'] and snap['Adam']==EXPECTED['Adam'],'model/Adam changed through reseed/no-op LR')
        need(snap['raw_components']['torch_cpu']==ref['cpu_rng_state_sha256'] and snap['raw_components']['torch_mps']==ref['mps_rng_state_sha256'],'initial CPU/MPS reference mismatch')
        need(snap['raw_components']['python']==fp(random.Random(seeds['python_random_seed']).getstate()) and snap['raw_components']['numpy_global']==fp(adapter.np.random.RandomState(seeds['numpy_global_seed']).get_state()),'Python/NumPy initial readback mismatch')
        need(snap['lr'] and all(type(v) in (int,float) and v==3e-5 for v in snap['lr']),'3e-5 no-op LR mismatch')
    need(snapshots['reseeded_before_lr']==snapshots['post_lr'],'no-op LR changed learner/raw RNG state')
    need(adapter.env is None,'probe environment must remain absent')
    event('lr_noop_verified_stop_before_environment')
    return dict(transition=result,snapshots=snapshots,counts=counts)

def claim_identity(reg):
    return dict(run_id=reg['run_id'],study_id=STUDY,replica=1,arm=ARM,vector_sha256=reg['vector']['vector_sha256'],parent_checkpoint_sha256=PARENT)

def runtime_identity(adapter,modules):
    rows=[]
    for name,module in sorted(sys.modules.items()):
        if name in ('torch','numpy','dodge_rl') or name.startswith('dodge_rl.'):
            path=getattr(module,'__file__',None)
            rows.append(dict(name=name,path=path,sha256=sha(path) if path and Path(path).is_file() else None,version=str(getattr(module,'__version__','not_declared'))))
    cls=type(adapter.model); optimizer=type(adapter.optimizer)
    dependencies=[]
    for requirement in importlib.metadata.requires('torch') or []:
        name=requirement.split(';',1)[0].strip().split(' ',1)[0]
        for delimiter in ('>=','==','<=','!=','~=','>','<','['): name=name.split(delimiter,1)[0]
        try: version=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: version='not_installed_or_inactive_marker'
        dependencies.append(dict(requirement=requirement,distribution=name,installed_version=version))
    return dict(trusted_callback_sources=adapter.callbacks['verified_sources'],authoritative_R5_manifest_sha256=R5_SHA,R3_manifest_sha256=R3_SHA,torch_dependencies=dependencies,python=sys.version,executable=sys.executable,prefix=sys.prefix,torch=str(adapter.torch.__version__),numpy=str(adapter.np.__version__),backend='mps',model_class=cls.__module__+'.'+cls.__qualname__,model_class_source=inspect.getsourcefile(cls),optimizer_class=optimizer.__module__+'.'+optimizer.__qualname__,adapter_source=str(R3/'runtime_adapter.py'),adapter_sha256=sha(R3/'runtime_adapter.py'),loaded_modules=rows)

def release(adapter):
    """Attempt every cleanup stage, including partially initialized adapters."""
    stages={}
    def attempt(name,fn):
        try: fn(); stages[name]={'status':'pass'}
        except BaseException as e: stages[name]={'status':'fail','error':type(e).__name__+':'+str(e)}
    torch=getattr(adapter,'torch',None)
    if torch is not None: attempt('synchronize_before_release',torch.mps.synchronize)
    def drop():
        for name in ('callbacks','parent','optimizer','model','runner','env'):
            if hasattr(adapter,name): setattr(adapter,name,None)
    attempt('release_learner_and_parent',drop); attempt('gc_collect',gc.collect)
    if torch is not None:
        attempt('synchronize_after_release',torch.mps.synchronize)
        attempt('empty_mps_cache',torch.mps.empty_cache)
        attempt('synchronize_after_cache',torch.mps.synchronize)
    return stages

def validate_result(reg,row,rsha):
    need(type(row) is dict and set(row)==RESULT_FIELDS,'restore result fields differ')
    need(row['schema']==RESULT_SCHEMA and row['status']=='verified_pending_parent_audit' and row['run_id']==reg['run_id'] and row['registration_sha256']==rsha,'restore result identity differs')
    need(row['study_id']==STUDY and type(row['replica']) is int and row['replica']==1 and row['arm']==ARM and row['vector_sha256']==reg['vector']['vector_sha256'] and row['reference']==reg['reference'] and row['scope']==SCOPE,'restore result study/reference/scope differs')
    need(type(row['counts']) is dict,'counts must be a mapping')
    need(all(type(v) is int for v in row['counts'].values()),'probe counts must be strict integers')
    need(row['parent_fingerprints']==EXPECTED and row['counts']==dict(restores=1,environment_constructions=0,rollouts=0,forwards=0,optimizer_steps=0,candidate_saves=0,training_updates=0),'restore result fingerprints/counts differ')
    snaps=row['snapshots']; need(set(snaps)=={'disposable_bootstrap','restored_before_reseed','reseeded_before_lr','post_lr'},'state stage inventory differs')
    raw_keys={'python','numpy_global','numpy_generator','torch_cpu','torch_mps','sampling_backend'}
    def digest(value): return type(value) is str and len(value)==64 and all(ch in '0123456789abcdef' for ch in value)
    for stage,state in snaps.items():
        need(set(state)=={'model','Adam','RNG','raw_components','lr'} and all(digest(state[k]) for k in EXPECTED) and set(state['raw_components'])==raw_keys and all(digest(v) for v in state['raw_components'].values()),'snapshot/raw RNG schema differs')
    need({k:snaps['restored_before_reseed'][k] for k in EXPECTED}==EXPECTED,'restored parent state differs')
    reference=read(reg['reference']['receipt_path'])
    need(snaps['post_lr']==snaps['reseeded_before_lr'],'LR no-op state differs')
    for name in ('reseeded_before_lr','post_lr'):
        s=snaps[name]
        need(s['model']==EXPECTED['model'] and s['Adam']==EXPECTED['Adam'] and s['lr'] and all(type(v) in (int,float) and v==3e-5 for v in s['lr']),'post-reseed model/Adam/LR differs')
        need(s['raw_components']['torch_cpu']==reference['cpu_rng_state_sha256'] and s['raw_components']['torch_mps']==reference['mps_rng_state_sha256'],'result reference state mismatch')
    transition_fields={'pair_id','arm','backend','study_id','replica','seed_vector','vector_sha256','constructor_seed_status','environment_seed_status','seed_evidence','parent_fingerprints','post_lr_fingerprints','required_fingerprint_contract','fingerprint_contract_status','old_controller_provenance','new_controller'}
    tr=row['transition']
    need(type(tr) is dict and set(tr)==transition_fields,'accepted transition result schema differs')
    need(tr['pair_id']==reg['pair_id'] and tr['arm']==ARM and tr['backend']=='mps' and tr['study_id']==STUDY and type(tr['replica']) is int and tr['replica']==1 and tr['vector_sha256']==reg['vector']['vector_sha256'],'accepted transition identity differs')
    need(tr['constructor_seed_status']==tr['environment_seed_status']=='driver_deferred_not_applied' and tr['fingerprint_contract_status']=='concrete state_dict fingerprints verified','accepted R5 deferred-seed contract differs')
    need(set(tr['seed_evidence'])=={'torch_cpu_initial_seed','torch_cpu_rng_state_sha256','torch_mps_rng_state_sha256'} and type(tr['seed_evidence']['torch_cpu_initial_seed']) is int,'transition seed evidence schema differs')
    need(set(tr['post_lr_fingerprints'])=={'model','Adam','Adam_content_excluding_lr'} and digest(tr['post_lr_fingerprints']['Adam_content_excluding_lr']),'transition post-LR schema differs')
    need(tr['old_controller_provenance']=={'origin':372,'horizon':60,'completed':0,'saved_lr':3e-5,'schedule':'none'} and tr['new_controller']=={'kind':'constant','origin':372,'horizon':60,'first_update':373,'last_update':432,'start_lr':3e-5,'end_lr':3e-5},'paired LR controller provenance differs')
    need(tr['required_fingerprint_contract']=='full model and Adam exact through reseed; post-LR optimizer content exact excluding only param_groups[].lr','accepted fingerprint contract differs')
    need(tr['post_lr_fingerprints']['model']==EXPECTED['model'] and tr['post_lr_fingerprints']['Adam']==EXPECTED['Adam'] and tr['seed_evidence']['torch_cpu_initial_seed']==reg['vector']['seeds']['torch_cpu_global_seed'],'transition learner/CPU seed readback differs')
    need(row['transition']['parent_fingerprints']==EXPECTED and row['transition']['seed_vector']==reg['vector']['seeds'] and row['transition']['seed_evidence']['torch_cpu_rng_state_sha256']==reference['cpu_rng_state_sha256'] and row['transition']['seed_evidence']['torch_mps_rng_state_sha256']==reference['mps_rng_state_sha256'],'accepted transition result differs')
    runtime=row['runtime']
    need(runtime.get('R3_manifest_sha256')==R3_SHA and runtime.get('authoritative_R5_manifest_sha256')==R5_SHA,'loaded source manifest evidence differs')
    need(runtime.get('model_class')=='dodge_rl.models.teacher.OmniscientEntityTeacher' and runtime.get('optimizer_class')=='torch.optim.adam.Adam','loaded learner class evidence differs')
    need(runtime.get('model_class_source')==str(Path(reg['runtime']['runtime_root'])/'dodge_rl/models/teacher.py'),'loaded model source differs')
    loaded={v['name']:v for v in runtime.get('loaded_modules',[])}
    runtime_pins=read(R3/'input-manifest.json')['pins']
    for name,relative in {'dodge_rl':'dodge_rl/__init__.py','dodge_rl._native':'dodge_rl/_native.cpython-312-darwin.so','dodge_rl.checkpoints':'dodge_rl/checkpoints.py','dodge_rl.ppo':'dodge_rl/ppo.py','dodge_rl.models.teacher':'dodge_rl/models/teacher.py','dodge_rl.identity':'dodge_rl/identity.py'}.items():
        path=Path(reg['runtime']['runtime_root'])/relative
        need(name in loaded and loaded[name]['path']==str(path) and loaded[name]['sha256']==runtime_pins[str(path.relative_to(ROOT))],'loaded native/runtime identity differs: '+name)
    need({'torch','numpy'}<=set(loaded) and type(runtime.get('torch_dependencies')) is list and runtime['torch_dependencies'],'loaded dependency evidence missing')
    need(runtime.get('trusted_callback_sources')==private_modules()['driver_binding'].verify_pinned_sources(ROOT),'trusted callback source identities differ')
    need(row['runtime']['backend']=='mps'  and row['runtime']['torch']==reg['runtime']['torch_version'] and row['runtime']['numpy']==reg['runtime']['numpy_version'] and row['runtime']['adapter_sha256']==sha(R3/'runtime_adapter.py'),'loaded runtime evidence differs')
    expected_cleanup={'synchronize_before_release','release_learner_and_parent','gc_collect','synchronize_after_release','empty_mps_cache','synchronize_after_cache'}
    need(set(row['cleanup'])==expected_cleanup and all(v=={'status':'pass'} for v in row['cleanup'].values()),'cleanup incomplete')
    names=[e['event'] for e in row['events']]
    need(names==['runtime_authenticated_checkpoint_validated','disposable_bootstrap_complete','accepted_restore_enter','accepted_restore_verified','study_reseed_verified_before_lr','lr_noop_verified_stop_before_environment','cleanup_complete'],'restore event order/count differs')
    need(all(set(e)=={'event','sequence','monotonic_ns'} and type(e['sequence']) is int and e['sequence']==i and type(e['monotonic_ns']) is int and e['monotonic_ns']>=0 for i,e in enumerate(row['events'])),'event result schema differs')
    need(all(a['monotonic_ns']<=b['monotonic_ns'] for a,b in zip(row['events'],row['events'][1:])),'event timestamps out of order')
    need(row['resources'] and all(set(v)=={'phase','elapsed_seconds','rss_high_water_bytes','mps_driver_bytes'} and type(v['phase']) is str and type(v['elapsed_seconds']) in (int,float) and math.isfinite(v['elapsed_seconds']) and 0<=v['elapsed_seconds']<=LIMITS['work_seconds'] and type(v['rss_high_water_bytes']) is int and 0<=v['rss_high_water_bytes']<=LIMITS['RSS_bytes'] and type(v['mps_driver_bytes']) is int and 0<=v['mps_driver_bytes']<=LIMITS['MPS_driver_bytes'] for v in row['resources']),'resource samples invalid')
    return row

def committed_check(reg,rsha):
    out=Path(reg['output_dir']); commit=read(out/'COMMITTED.json')
    allowed={'worker.log','worker-heartbeat.json','events.jsonl','resources.jsonl','result.json','COMMITTED.json','outer-receipt.json'}
    need(all(v.is_file() and v.name in allowed for v in out.iterdir()),'unexpected output/candidate/failure artifact')
    need(set(commit)=={'schema','result_sha256','registration_sha256'} and commit['schema']=='confirmed324_restore_probe_commit_v1' and commit['registration_sha256']==rsha,'restore commit schema/binding differs')
    raw=verified(out/'result.json',commit['result_sha256']); row=json.loads(raw)
    validate_result(reg,row,rsha)
    claim=read(reg['attempt_claim_path']); need(claim==claim_identity(reg),'persistent restore subclaim differs')
    events=[json.loads(line) for line in (out/'events.jsonl').read_text().splitlines()]
    need(events==row['events'],'durable event journal differs')
    resources=[json.loads(line) for line in (out/'resources.jsonl').read_text().splitlines()]
    need(resources==row['resources'],'durable resource journal differs')
    return {'replicas':1,'restores':1,'qualification':'pending_parent_audit'}
