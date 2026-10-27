#!/usr/bin/env python3
"""Stdlib discovery and acyclic freeze. No ML import or checkpoint decoding."""
from pathlib import Path
import ast
import copy
import datetime
import importlib.metadata
import json
import os
import shutil
import sys
import sysconfig
import time
import long_d2 as c
import boundary_integrity as integrity

H=Path(__file__).resolve().parent
ROOT=c.ORIGINAL_ROOT
BASE=H.parent/'postovernight-long-D2-guard-prepare-r1'
RESERVATION='learning/runs/v2-orchestration/postovernight-long-D2-r2-input-ownership-reservation.json'
RESERVATION_SHA='d6a2e38bb180427ec373ec5b5df3e7b6904c9b1cd77041f00d2881dc17ed7857'
ROOT_EXCLUSIONS=['classification.json','long-identity.json','capsule-manifest.json','registration.json']


def freeze():
    start=time.monotonic()
    p=c.registered_protocol(ROOT/c.PROTOCOL_REL)
    old=c.read_json(BASE/'expanded-inventory.json')['full_pins']
    c.require(len(old)==10091,'Historical union count changed')
    prior=c.read_json(BASE/'long-identity.json')
    c.require(all(old.get(k)==v for k,v in prior['retained_r4_union'].items()) and len(prior['retained_r4_union'])==9870,'R4 coverage changed')
    c.require(all(old.get(k)==v for k,v in prior['retained_r3_union'].items()) and len(prior['retained_r3_union'])==9675,'R3 coverage changed')
    capsule=H/'capsule-final';capsule.mkdir()
    cache=H/'production-pycache-prefix';cache.mkdir()
    # Metadata/file discovery, never import torch/numpy/native code.
    roots=[];distributions={}
    native_at=time.monotonic()
    for name in ('torch','numpy'):
        dist=importlib.metadata.distribution(name)
        root=Path(dist.locate_file(name)).resolve()
        roots.append(str(root))
        distributions[name]=dict(version=dist.version,root=str(root),metadata_path=str(dist._path),
            metadata_files={str(Path(dist._path)/n):c.sha(Path(dist._path)/n) for n in ('METADATA','WHEEL','RECORD') if (Path(dist._path)/n).is_file()})
    roots.append(str(Path(sysconfig.get_config_var('DESTSHARED')).resolve()))
    native_paths=integrity.native_members(roots)
    for folder in (Path(sys.base_prefix)/'lib',Path(sys.base_prefix)/'Python.framework'):
        if folder.exists():
            for path in folder.glob('libpython*'):
                if path.is_file():native_paths.add(str(path))
    lib=Path(sysconfig.get_config_var('LIBDIR') or '')/str(sysconfig.get_config_var('LDLIBRARY') or '')
    if lib.is_file():native_paths.add(str(lib))
    native_all={name:c.sha(name) for name in sorted(native_paths)}
    for value in distributions.values():native_all=integrity.merge_bindings(native_all,value['metadata_files'])
    # Normal-read foundation dependency closure, taken from unchanged foundation_identity.
    active={str(ROOT/name):digest for name,digest in p['base_identity']['sources'].items()}
    def add(path,digest=None):
        nonlocal active
        path=Path(path);digest=c.sha(path) if digest is None else digest
        active=integrity.merge_bindings(active,{str(path):digest})
    for key in ('base_identity_path','base_config_path','config_path','entry_control','parent_checkpoint','parent_audit','api_audit','guard_repair_plan'):
        add(ROOT/p[key])
    add(ROOT/c.PROTOCOL_REL,c.PROTOCOL_SHA256)
    add(ROOT/RESERVATION,RESERVATION_SHA)
    for name in ('postovernight-long-D2-boundary-policy-parent-reconciliation-r1.json',):add(ROOT/'learning/runs/v2-orchestration'/name)
    add(ROOT/p['integrity_policy']['design'],p['integrity_policy']['design_sha256'])
    for name in ('learning/runs/v2-orchestration/milestone2-acceptance-r2.json',
                 'learning/runs/v2/milestone2-campaign-freeze-r4/frozen-identity.json'):
        add(ROOT/name)
    for name,digest in p['base_identity']['foundation']['binary_and_receipt_sha256'].items():add(name,digest)
    add(Path(sys.executable).resolve(),p['base_identity']['runtime']['interpreter_sha256'])
    parent=(ROOT/p['parent_checkpoint']).parent
    for name in ('run-result.json','worker-result.json','registered-config.json','identity.json','artifact-sha256.json',Path(p['parent_checkpoint']).name+'.evaluation.json'):
        add(parent/name)
    sources={str(path.relative_to(ROOT)):c.sha(path) for path in sorted(H.iterdir()) if path.is_file() and path.suffix in {'.py','.md'}}
    for name,digest in sources.items():add(ROOT/name,digest)
    # Only B leaves get execution mirrors; historical capsules remain archive members.
    mirrors={}
    for name,digest in active.items():
        path=Path(name)
        if path.is_relative_to(ROOT):
            rel=str(path.relative_to(ROOT));target=capsule/rel
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
            mirrors[str(target)]=digest
    active=integrity.merge_bindings(active,mirrors)
    # One class per canonical path; keep every original alias/hash binding.
    active_canonical={str(Path(n).resolve()) for n in active}
    runtime={n:v for n,v in native_all.items() if str(Path(n).resolve()) not in active_canonical}
    runtime_canonical={str(Path(n).resolve()) for n in runtime}
    archive={n:v for n,v in old.items() if str(Path(n).resolve()) not in active_canonical|runtime_canonical}
    for name,digest in old.items():
        canonical=str(Path(name).resolve())
        if canonical in active_canonical:active=integrity.merge_bindings(active,{name:digest})
        elif canonical in runtime_canonical:runtime=integrity.merge_bindings(runtime,{name:digest})
    integrity.merge_bindings(active,runtime,archive)
    c.require(str(c.STATE_PATH) not in active|runtime|archive,'Mutable parent state frozen')
    # Endpoint manifests are themselves B leaves. They do not include their own bytes.
    archive_manifest=dict(schema='long_d2_archive_manifest_v1',files=archive,original_union_count=10091,
        retained_R4_count=9870,retained_R3_count=9675,classification_rule='canonical B precedence, then R, remaining A',
        original_bindings={n:dict(sha256=v,classification=('B' if n in active else 'R' if n in runtime else 'A')) for n,v in old.items()})
    # discovered_members excludes any separately added libpython outside scanned roots.
    native_manifest=dict(schema='long_d2_native_manifest_v1',files=runtime,roots=roots,
        discovered_members=sorted(integrity.native_members(roots)),all_native_origins={str(Path(n).resolve()):v for n,v in native_all.items() if Path(n).suffix in {'.so','.dylib','.pyd','.dll'}},
        distributions=distributions,discovery_no_ML_imports=True,
        native_file_count=len(native_paths),native_bytes=sum(Path(n).stat().st_size for n in native_paths),
        discovery_hash_seconds=time.monotonic()-native_at,
        limitation='Bounded native distribution/CPython/libpython provenance; no whole OS/transitive dylib or memory attestation')
    for name,value in (('archive-manifest.json',archive_manifest),('native-manifest.json',native_manifest)):
        c.save(H/name,value)
        target=capsule/c.PREPARE_REL/name;shutil.copyfile(H/name,target)
        for file in (H/name,target):add(file)
    classification=dict(schema='long_d2_input_classification_v1',B=active,R_manifest_sha256=c.sha(H/'native-manifest.json'),
        A_manifest_sha256=c.sha(H/'archive-manifest.json'),class_counts=dict(B=len(active),R=len(runtime),A=len(archive)),
        root_envelope_exclusions=ROOT_EXCLUSIONS,mutable_controls=[str(c.STATE_PATH)],
        outputs=[str(ROOT/p['output']),str(ROOT/Path(p['terminal_lifecycle']['acceptance_receipt']).parent),str(cache)],
        guarantee='Persistent mutations fail at next declared boundary; transient edit/revert may pass; cooperative ownership only')
    c.save(H/'classification.json',classification)
    identity={k:copy.deepcopy(prior[k]) for k in ('base_registered_identity','base_registered_identity_sha256','base_registered_identity_semantic_sha256','config','config_semantic_sha256','config_sha256','legacy_module_origins','parent_checkpoint_sha256','parent_terminal_receipt','parent_terminal_receipt_semantic_sha256','same_phase_resume','all_checkpoints_training_parent_eligible')}
    path_before=[str(capsule/c.PREPARE_REL)]+list(sys.path[1:])
    envkeys=('PYTHONPATH','PYTHONHOME','PYTHONSAFEPATH','PYTORCH_ENABLE_MPS_FALLBACK','OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','VECLIB_MAXIMUM_THREADS','DYLD_LIBRARY_PATH','DYLD_FALLBACK_LIBRARY_PATH')
    policy=dict(pycache_prefix=str(cache),sys_path_before_project=path_before,sys_path_after_project=[str(ROOT/'python')]+path_before,
        environment={name:os.environ.get(name) for name in envkeys},interpreter=str(Path(sys.executable).resolve()),
        python=sys.version,torch=distributions['torch']['version'],numpy=distributions['numpy']['version'],threads=4,mps_required=True)
    identity.update(version='teacher_long_D2_boundary_identity_v1',protocol_sha256=c.PROTOCOL_SHA256,
        classification_sha256=c.sha(H/'classification.json'),controller_sources=sources,
        reservation_path=RESERVATION,reservation_sha256=RESERVATION_SHA,
        class_manifest_hashes=dict(B=c.sha(H/'classification.json'),R=c.sha(H/'native-manifest.json'),A=c.sha(H/'archive-manifest.json')),
        runtime_policy=policy,native_origins=native_manifest['all_native_origins']|{str((ROOT/'python/dodge_rl/_native.cpython-312-darwin.so').resolve()):p['base_identity']['foundation']['extension_sha256']},
        terminal_lifecycle=p['terminal_lifecycle'],runtime_import_policy=p['runtime_import_policy'],
        hash_semantics='Leaf manifests then classification then identity then capsule manifest then external registration then parent-held invocation digest',
        root_envelope_exclusions=ROOT_EXCLUSIONS)
    c.save(H/'long-identity.json',identity)
    for name in ('classification.json','long-identity.json'):shutil.copyfile(H/name,capsule/c.PREPARE_REL/name)
    files={str(path.relative_to(capsule)):c.sha(path) for path in sorted(capsule.rglob('*')) if path.is_file()}
    c.save(capsule/'capsule-manifest.json',dict(version='long_d2_capsule_v1',files=files,manifest_excludes_itself=True,original_package_imports=True,root_exclusions=ROOT_EXCLUSIONS))
    for path in capsule.rglob('*'):
        if path.is_file():path.chmod(0o444)
    for path in sorted((n for n in capsule.rglob('*') if n.is_dir()),key=lambda n:len(n.parts),reverse=True):path.chmod(0o555)
    capsule.chmod(0o555)
    registration=dict(schema='long_d2_executor_registration_v2',capsule_path=str(capsule),controller=str(capsule/c.PREPARE_REL/'long_d2.py'),
        executor=str(capsule/c.PREPARE_REL/'long_d2_executor.py'),output=str(ROOT/p['output']),receipt=str(ROOT/p['terminal_lifecycle']['acceptance_receipt']),state_path=str(c.STATE_PATH),
        protocol_sha256=c.PROTOCOL_SHA256,config_sha256=c.CONFIG_SHA256,identity_sha256=c.sha(H/'long-identity.json'),
        capsule_manifest_sha256=c.sha(capsule/'capsule-manifest.json'),classification_sha256=identity['classification_sha256'],
        reservation_sha256=RESERVATION_SHA,class_manifest_hashes=identity['class_manifest_hashes'],class_counts=classification['class_counts'],cache_policy=policy,root_exclusions=ROOT_EXCLUSIONS,
        pins={str(capsule/name):c.sha(capsule/name) for name in (c.PREPARE_REL+'/long_d2.py',c.PREPARE_REL+'/long_d2_executor.py',c.PREPARE_REL+'/long-identity.json',c.PREPARE_REL+'/classification.json','capsule-manifest.json',c.PROTOCOL_REL,p['config_path'])})
    c.save(H/'registration.json',registration)
    lease=c.expected_lease(p,c.sha(capsule/p['controller']),registration['capsule_manifest_sha256'],capsule,registration['identity_sha256'])
    c.save(H/'required-lease.json',dict(lease))
    c.save(H/'invocation.json',dict(argv=[str(ROOT/'learning/.venv/bin/python'),'-B',registration['executor'],'run','--registration',str(H/'registration.json'),'--registration-sha256',c.sha(H/'registration.json')],
        cwd=str(capsule),environment={'PYTHONDONTWRITEBYTECODE':'1','PYTHONPYCACHEPREFIX':str(cache)},unset_environment=['PYTORCH_ENABLE_MPS_FALLBACK'],
        registration_sha256=c.sha(H/'registration.json'),lease_PROPOSAL_ONLY=True,parent_review_required=True,launch_performed=False))
    c.save(H/'hash-DAG.json',dict(schema='long_d2_hash_DAG_v1',edges={'archive-manifest':[],'native-manifest':[],
        'classification':['B-leaf-bytes','archive-manifest','native-manifest'],'identity':['classification','archive-manifest','native-manifest','controller-source-bytes','protocol','reservation'],
        'capsule-manifest':['identity','classification','B-mirror-bytes'],'external-registration':['capsule-manifest','identity','classification','protocol','config'],
        'parent-held-invocation':['external-registration']},root_exclusions=ROOT_EXCLUSIONS,
        actual_member_verification='B+root envelopes each declared barrier; B/R/A actual bytes once pre-spawn and once after reap/group absence before success',
        registration_self_hash=False,classification_self_hash=False,identity_self_hash=False,counts=classification['class_counts'],old_bindings_covered=10091,
        freeze_seconds=time.monotonic()-start,native_discovery=native_manifest|{'files':'native-manifest.json'}))
    print(json.dumps({'status':'frozen_unvalidated_review_required','class_counts':classification['class_counts'],'capsule_files':len(files),'registration_sha256':c.sha(H/'registration.json')}))

if __name__=='__main__':freeze()
