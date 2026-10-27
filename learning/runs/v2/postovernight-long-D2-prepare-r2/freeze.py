#!/usr/bin/env python3
"""Stdlib-only single-use capsule freeze. Never imports Torch/project/native.

Raw document SHA256 binds byte serialization. Semantic SHA256 is JSON canonical
identity_hash-compatible and is the unchanged checkpoint container's identity
field. Neither is the capsule manifest's raw document hash. Identity excludes
itself and the capsule manifest, avoiding a hash cycle; manifest includes identity
and all execution/test source bytes and excludes itself.
"""
from pathlib import Path
import json
import os
import shutil
import sys
import long_d2 as controller

ROOT=controller.ORIGINAL_ROOT
OUT=ROOT/controller.PREPARE_REL


def make_identity():
    p=controller.registered_protocol(ROOT/controller.PROTOCOL_REL)
    base=controller.read_json(ROOT/p['base_config_path'])
    config=controller.read_json(ROOT/p['config_path'])
    controller.validate_long_config(config,base,p,controller.read_json(ROOT/'docs/v2-m3-run-protocol.json'))
    pins={str(ROOT/k):v for k,v in p['base_identity']['sources'].items()}
    files={p['base_config_path']:p['base_config_sha256'],
           p['base_identity_path']:p['base_identity_sha256'],
           controller.PROTOCOL_REL:controller.PROTOCOL_SHA256,
           p['config_path']:controller.CONFIG_SHA256,
           p['parent_checkpoint']:p['parent_checkpoint_sha256'],
           p['parent_audit']:p['parent_audit_sha256'],p['entry_control']:p['entry_control_sha256'],
           p['design']:p['design_sha256'],p['api_audit']:p['api_audit_sha256']}
    # Retain the full terminal proof and independently observed parent exit.
    run=(ROOT/p['parent_checkpoint']).parent
    for name in ('run-result.json','worker-result.json','identity.json','registered-config.json',
                 'artifact-sha256.json','checkpoint-000009-candidate.pt.evaluation.json'):
        path=run/name;files[str(path.relative_to(ROOT))]=controller.sha(path)
    for name in ('learning/runs/v2/milestone3-D1-execution-r1/result.json',
                 'learning/runs/v2/milestone3-D1-execution-r1/artifact-sha256.json',
                 'learning/runs/v2-orchestration/milestone3_D1_curriculum_r1-result.json',
                 'learning/runs/v2-orchestration/postovernight-long-D2-design-parent-reconciliation-r1.json',
                 'learning/runs/v2-orchestration/milestone2-acceptance-r2.json',
                 'learning/runs/v2/milestone2-campaign-freeze-r4/frozen-identity.json',
                 'docs/v2-action-mode-results-2026-10-24.md'):
        files[name]=controller.sha(ROOT/name)
    for folder in (ROOT/'learning/runs/v2/postovernight-long-D2-design-opus-r1',
                   ROOT/'learning/runs/v2/postovernight-long-D2-api-audit-r1'):
        for path in folder.rglob('*'):
            if path.is_file():files[str(path.relative_to(ROOT))]=controller.sha(path)
    # Keep the complete rejected preparation and both independent reviews as
    # original-only immutable references. Never copy the old capsule or logs
    # into the new execution capsule and never relabel historical evidence.
    references={}
    for name in ('postovernight-long-D2-prepare-r1',
                 'postovernight-long-D2-supervisor-review-r1',
                 'postovernight-long-D2-learner-review-r1'):
        for path in sorted((ROOT/'learning/runs/v2'/name).rglob('*')):
            if path.is_file():references[str(path)]=controller.sha(path)
    reconciliation='learning/runs/v2-orchestration/postovernight-long-D2-review-parent-reconciliation-r1.json'
    files[reconciliation]=controller.sha(ROOT/reconciliation)
    old_protocol='learning/runs/v2-orchestration/postovernight-long-D2-r1-protocol.json'
    files[old_protocol]=controller.sha(ROOT/old_protocol)
    pins.update(references)
    pins.update({str(ROOT/k):v for k,v in files.items()})
    pins.update(p['base_identity']['foundation']['binary_and_receipt_sha256'])
    runtime=p['base_identity']['runtime']
    pins[runtime['interpreter']]=runtime['interpreter_sha256']
    controller.verify_files(pins)
    anchor=p['parent_terminal_receipt']
    audit=controller.read_json(ROOT/p['parent_audit'])
    execution=controller.read_json(ROOT/'learning/runs/v2/milestone3-D1-execution-r1/result.json')
    controller.require(audit['status']=='passed' and audit['parent_terminal_receipt']==anchor
                       and execution['supervisor_exit_code']==0,'D1 audit/observed execution mismatch')
    for name,key in [('run-result.json','run_result_sha256'),
                     ('checkpoint-000009-candidate.pt.evaluation.json','evaluation_sha256')]:
        controller.require(controller.sha(run/name)==anchor[key],'D1 exact terminal anchor differs')
    sources={str(path.relative_to(ROOT)):controller.sha(path) for path in sorted(OUT.glob('*.py'))
             if not {'capsule','__pycache__'}.intersection(path.relative_to(OUT).parts)}
    controller.require(controller.PREPARE_REL+'/long_d2.py' in sources,'Controller absent')
    return dict(version='teacher_long_D2_identity_v1',config=config,
                config_sha256=controller.CONFIG_SHA256,config_semantic_sha256=controller.semantic_hash(config),
                base_registered_identity_sha256=p['base_identity_sha256'],base_registered_identity=p['base_identity'],
                base_registered_identity_semantic_sha256=controller.semantic_hash(p['base_identity']),
                parent_checkpoint_sha256=p['parent_checkpoint_sha256'],parent_terminal_receipt=anchor,
                parent_terminal_receipt_semantic_sha256=controller.semantic_hash(anchor),
                protocol_sha256=controller.PROTOCOL_SHA256,controller_sources=sources,
                original_input_pins=pins,original_only_historical_reference_pins=references,
                controller_source_scope='all active root helper/test Python files; retained attempts and mutants are historical evidence only',
                runtime_import_policy=p['runtime_import_policy'],
                legacy_module_origins={str(ROOT/k):dict(sha256=v,mirror=k)
                    for k,v in p['base_identity']['sources'].items() if k.startswith('python/dodge_rl/')},
                hash_semantics=dict(config_sha256='raw registered config document bytes',
                    base_registered_identity_sha256='raw historical identity document bytes',
                    protocol_sha256='raw registered long protocol document bytes',
                    checkpoint_identity_sha256='canonical JSON semantic hash of this complete envelope',
                    self_document_sha256='external receipt only; excluded from identity to avoid circularity'),
                all_checkpoints_training_parent_eligible=False,same_phase_resume=False)


def freeze():
    identity=make_identity()
    identity_path=OUT/'long-identity.json'
    controller.save(identity_path,identity)
    capsule=OUT/'capsule-final'
    capsule.mkdir(exist_ok=False)
    files={}
    for original,digest in identity['original_input_pins'].items():
        if original in identity['original_only_historical_reference_pins']:
            continue
        source=Path(original)
        mirror=(source.relative_to(ROOT) if source.is_relative_to(ROOT)
                else Path('external')/digest/source.name)
        target=capsule/mirror;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        files[str(mirror)]=digest
    for relative,digest in identity['controller_sources'].items():
        target=capsule/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/relative,target);files[relative]=digest
    target=capsule/controller.PREPARE_REL/'long-identity.json'
    shutil.copyfile(identity_path,target);files[str(target.relative_to(capsule))]=controller.sha(identity_path)
    controller.verify_files({str(capsule/k):v for k,v in files.items()})
    controller.save(capsule/'capsule-manifest.json',dict(version='long_d2_capsule_v1',files=files,
                    manifest_excludes_itself=True,original_package_imports=True))
    for path in capsule.rglob('*'):
        if path.is_file():path.chmod(0o444)
    for path in sorted((x for x in capsule.rglob('*') if x.is_dir()),key=lambda x:len(x.parts),reverse=True):
        path.chmod(0o555)
    capsule.chmod(0o555)
    receipt=controller.pure_preflight(capsule)
    controller.save(OUT/'freeze-receipt.json',receipt)
    controller.save(OUT/'required-lease.json',receipt['required_lease'])
    command=[str(ROOT/'learning/.venv/bin/python'),'-B',str(capsule/controller.PREPARE_REL/'long_d2.py'),
             'run','--output',str(ROOT/controller.registered_protocol(ROOT/controller.PROTOCOL_REL)['output'])]
    controller.save(OUT/'invocation.json',dict(argv=command,cwd=str(capsule),
                    environment={'PYTHONDONTWRITEBYTECODE':'1'},unset_environment=['PYTORCH_ENABLE_MPS_FALLBACK'],
                    execute_only_after_parent_frozen_review_and_lease=True,no_launch_performed=True))
    print(json.dumps({k:v for k,v in receipt.items() if k!='required_lease'},sort_keys=True,indent=2))


if __name__=='__main__':
    freeze()
