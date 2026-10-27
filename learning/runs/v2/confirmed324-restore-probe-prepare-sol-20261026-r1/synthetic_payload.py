"""Fabricated semantic fixtures, never actual runtime evidence or launch inputs."""
import copy
import json
from pathlib import Path
import time
import probe as p

def runtime_fixture(reg):
    root=Path(reg['runtime']['runtime_root']); pins=p.read(p.R3/'input-manifest.json')['pins']
    rows=[]
    for name,rel in {'dodge_rl':'dodge_rl/__init__.py','dodge_rl._native':'dodge_rl/_native.cpython-312-darwin.so','dodge_rl.checkpoints':'dodge_rl/checkpoints.py','dodge_rl.ppo':'dodge_rl/ppo.py','dodge_rl.models.teacher':'dodge_rl/models/teacher.py','dodge_rl.identity':'dodge_rl/identity.py'}.items():
        path=root/rel; rows.append(dict(name=name,path=str(path),sha256=pins[str(path.relative_to(p.ROOT))],version='synthetic'))
    rows.extend([dict(name=n,path='synthetic',sha256='0'*64,version='synthetic') for n in ('torch','numpy')])
    return dict(backend='mps',torch='2.14.1',numpy='2.5.4',adapter_sha256=p.sha(p.R3/'runtime_adapter.py'),R3_manifest_sha256=p.R3_SHA,authoritative_R5_manifest_sha256=p.R5_SHA,model_class='dodge_rl.models.teacher.OmniscientEntityTeacher',optimizer_class='torch.optim.adam.Adam',model_class_source=str(root/'dodge_rl/models/teacher.py'),loaded_modules=rows,torch_dependencies=[dict(requirement='synthetic',distribution='synthetic',installed_version='synthetic')],trusted_callback_sources=p.private_modules()['driver_binding'].verify_pinned_sources(p.ROOT))

def semantic_fixture(reg,rsha):
    reference=p.read(reg['reference']['receipt_path'])
    raw={k:'0'*64 for k in ('python','numpy_global','numpy_generator','torch_cpu','torch_mps','sampling_backend')}
    raw.update(torch_cpu=reference['cpu_rng_state_sha256'],torch_mps=reference['mps_rng_state_sha256'])
    snap=dict(**p.EXPECTED,raw_components=raw,lr=[3e-5])
    events=['runtime_authenticated_checkpoint_validated','disposable_bootstrap_complete','accepted_restore_enter','accepted_restore_verified','study_reseed_verified_before_lr','lr_noop_verified_stop_before_environment','cleanup_complete']
    tr=dict(pair_id=reg['pair_id'],arm=p.ARM,backend='mps',study_id=p.STUDY,replica=1,seed_vector=reg['vector']['seeds'],vector_sha256=reg['vector']['vector_sha256'],constructor_seed_status='driver_deferred_not_applied',environment_seed_status='driver_deferred_not_applied',seed_evidence=dict(torch_cpu_initial_seed=reg['vector']['seeds']['torch_cpu_global_seed'],torch_cpu_rng_state_sha256=reference['cpu_rng_state_sha256'],torch_mps_rng_state_sha256=reference['mps_rng_state_sha256']),parent_fingerprints=p.EXPECTED,post_lr_fingerprints=dict(model=p.EXPECTED['model'],Adam=p.EXPECTED['Adam'],Adam_content_excluding_lr='0'*64),required_fingerprint_contract='full model and Adam exact through reseed; post-LR optimizer content exact excluding only param_groups[].lr',fingerprint_contract_status='concrete state_dict fingerprints verified',old_controller_provenance={'origin':372,'horizon':60,'completed':0,'saved_lr':3e-5,'schedule':'none'},new_controller={'kind':'constant','origin':372,'horizon':60,'first_update':373,'last_update':432,'start_lr':3e-5,'end_lr':3e-5})
    return copy.deepcopy(dict(schema=p.RESULT_SCHEMA,status='verified_pending_parent_audit',run_id=reg['run_id'],registration_sha256=rsha,study_id=p.STUDY,replica=1,arm=p.ARM,vector_sha256=reg['vector']['vector_sha256'],reference=reg['reference'],parent_fingerprints=p.EXPECTED,snapshots={k:copy.deepcopy(snap) for k in ('disposable_bootstrap','restored_before_reseed','reseeded_before_lr','post_lr')},transition=tr,events=[dict(event=e,sequence=i,monotonic_ns=i) for i,e in enumerate(events)],counts=dict(restores=1,environment_constructions=0,rollouts=0,forwards=0,optimizer_steps=0,candidate_saves=0,training_updates=0),runtime=runtime_fixture(reg),cleanup={k:{'status':'pass'} for k in ('synchronize_before_release','release_learner_and_parent','gc_collect','synchronize_after_release','empty_mps_cache','synchronize_after_cache')},scope=p.SCOPE,resources=[dict(phase='synthetic',elapsed_seconds=0.1,rss_high_water_bytes=0,mps_driver_bytes=0)]))

def publish_fixture(reg,rsha,row=None):
    out=Path(reg['output_dir']); out.mkdir(exist_ok=True)
    row=row or semantic_fixture(reg,rsha)
    (out/'result.json').write_text(json.dumps(row))
    for name in ('events','resources'):
        (out/(name+'.jsonl')).write_text(''.join(json.dumps(x)+'\n' for x in row[name]))
    (out/'COMMITTED.json').write_text(json.dumps(dict(schema='confirmed324_restore_probe_commit_v1',result_sha256=p.sha(out/'result.json'),registration_sha256=rsha)))
    return row
