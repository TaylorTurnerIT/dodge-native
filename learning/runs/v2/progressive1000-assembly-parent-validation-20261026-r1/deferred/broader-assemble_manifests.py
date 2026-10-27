"""Freeze owned source inventories and inert templates; never register or launch."""
from pathlib import Path
import difflib
import hashlib
import json
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import contracts as c


def save(name,value):
    (HERE/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def main():
    shared=dict(schema='progressive1000_shared_config_v1',batch_size=64,rollout_steps=256,global_updates=60,
        learning_rate_schedule='none',learning_rate=3e-5,ppo=c.PPO,action_repeat=4,difficulty=2,
        patterns_enabled=True,powerups_enabled=True,raw_frame_cap=18000,num_threads=4,chunk_size=8,
        render_pixels=False,auxiliary_targets=False,observation_keys=['global_feats','entity_feats','entity_types','entity_mask'],
        architecture='omniscient_entity_teacher_full_attention_v1',model_layers=2,model_width=128,model_tokens=81,
        reward='score + alive_frames/100 - 5 on true death',normalization='unchanged_no_running_normalization',
        evaluator_action_mode='sampled_categorical',formal_evaluation='terminal60_only_plus_shared_parent',
        schedule=c.SCHEDULE)
    save('shared-config.json',shared)
    runtime={'schema':'progressive1000_shared_runtime_manifest_v1','profile':'release','files':{
        str(p.relative_to(HERE/'runtime')):c.sha(p) for p in sorted((HERE/'runtime').rglob('*')) if p.is_file()}}
    save('runtime-manifest.json',runtime)
    manifest=c.read(HERE/'input-manifest.json')
    changes=[];diff=[]
    for rel,row in manifest['copies'].items():
        p=HERE/rel
        if not p.exists():continue
        if c.sha(p)!=row['sha256']:
            changes.append(dict(output=rel,input=row['source'],input_sha256=row['sha256'],output_sha256=c.sha(p)))
            try:
                diff.extend(difflib.unified_diff(Path(row['source']).read_text().splitlines(True),p.read_text().splitlines(True),
                                               fromfile=row['source'],tofile=str(p)))
            except UnicodeError:pass
    (HERE/'exact-input-diff.patch').write_text(''.join(diff))
    save('exact-input-diff.json',dict(changed_copies=changes,unchanged_copies=len(manifest['copies'])-len(changes),
         added_source_files=[str(p.relative_to(HERE)) for p in sorted(HERE.glob('*.py')) if str(p.relative_to(HERE)) not in manifest['copies']],
         note='Native R2 source and Cargo.lock unchanged. Copied checkpoint/identity/model bytes unchanged. Successor evaluator explicitly changes greedy predecessor to sampled Categorical per new design.'))
    selected=[]
    for p in HERE.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(HERE)
        if rel.parts[0] in {'native','tmp','logs','empty-pycache','extension'}:
            if rel.parts[:2]!=('native','source'):continue
        if '__pycache__' in rel.parts:continue
        if p.suffix=='.py' or str(rel) in {'shared-config.json','experiment.json','seed-vectors.json','input-manifest.json',
            'dependency-config.json','runtime-manifest.json','binary-manifest.json','exact-input-diff.json','exact-input-diff.patch'} or rel.parts[:2]==('native','source'):
            selected.append(p)
    source=dict(schema='progressive1000_shared_source_manifest_v1',authority='source inventory; NO launch authority',
                files={str(p.relative_to(HERE)):c.sha(p) for p in sorted(selected)})
    save('source-manifest.json',source)
    proposal=c.read(HERE/'seed-vectors.json')
    union=[list(row) for row in c.transition.EXPECTED_EXCLUSION_RANGES]
    for vector in proposal['vectors']:
        replica=vector['replica']
        for arm in c.ARMS:
            run_id=f'{c.STUDY}-replica-{replica}-{arm}'
            reg=dict(schema='progressive1000_worker_registration_v1',status='inert_template_NO_LAUNCH',study_id=c.STUDY,
                run_id=run_id,pair_id=f'{c.STUDY}-replica-{replica}',replica=replica,arm=arm,backend='mps',
                curriculum_enabled=arm==c.ARMS[1],vector=vector,reference=None,reference_approval=None,
                initial_episode_indices=proposal['parent']['next_episode_indices'],exclusion_union=union,
                parent_checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256,parent_receipt_sha256=c.references.PARENT_RECEIPT_SHA256,
                expected_parent_fingerprints=c.transition.EXPECTED_PARENT,runtime_root=str(HERE/'runtime'),
                runtime_versions=manifest['runtime_versions'],source_manifest_sha256=c.sha(HERE/'source-manifest.json'),
                runtime_manifest_sha256=c.sha(HERE/'runtime-manifest.json'),input_manifest_sha256=c.sha(HERE/'input-manifest.json'),
                shared_config=shared,ppo=c.PPO,schedule=c.SCHEDULE,output=None,attempt_claim_path=None,
                interpreter=str(c.ROOT/'python/.venv/bin/python3.12'),import_policy=dict(pycache_prefix=None,dont_write_bytecode=True),
                state_path=None,expected_lease=None,launch_marker_path=None,limits=None,
                cohort_state='PENDING_NOT_RESERVED',history_state='BLOCKED',reservation_state='PENDING')
            save(f'registration-template-replica-{replica}-{arm}.json',reg)
    from expanded_eval import POLICY_IDS
    save('evaluation-template.json',dict(schema='progressive1000_evaluation_registration_v1',status='inert_template_NO_LAUNCH',
        study_id=c.STUDY,backend='mps',runtime_versions=manifest['runtime_versions'],runtime_manifest_sha256=c.sha(HERE/'runtime-manifest.json'),
        source_manifest_sha256=c.sha(HERE/'source-manifest.json'),input_manifest_sha256=c.sha(HERE/'input-manifest.json'),
        cohort_state='PENDING_NOT_RESERVED',history_state='BLOCKED',reservation_state='PENDING',seeds=list(range(0xD3000000,0xD3000400)),
        exclusion_union=union,evaluation_rng_seed=None,action_mode='sampled_categorical',cutoff_enabled=False,normal_start=True,row_count=1024,
        policies=[dict(id=name,checkpoint_path=None,checkpoint_sha256=None,worker_result_path=None,worker_result_sha256=None) for name in POLICY_IDS],
        limits=None,output_root=None,claim_root=None,state_path=None,expected_lease=None,
        import_policy=dict(pycache_prefix=None,dont_write_bytecode=True),interpreter=str(c.ROOT/'python/.venv/bin/python3.12')))
    save('remaining-gates.json',dict(launch_authority=False,gates={key:'PENDING_PARENT' for key in c.GATES},
        seed_history='BLOCKED',new_vector_CPU_MPS_references='PENDING; none measured or synthesized here',
        release_build='completed; parity/runtime/MPS qualification pending',
        trusted_restore='source rebound only; no accepted checkpoint deserialization or restore executed'))
    print(json.dumps(dict(source_manifest_sha256=c.sha(HERE/'source-manifest.json'),runtime_manifest_sha256=c.sha(HERE/'runtime-manifest.json'),source_files=len(source['files']),changed_copies=len(changes))))


if __name__=='__main__':main()
