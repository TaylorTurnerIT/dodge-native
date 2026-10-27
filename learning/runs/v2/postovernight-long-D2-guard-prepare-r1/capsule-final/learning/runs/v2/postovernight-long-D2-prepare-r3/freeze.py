#!/usr/bin/env python3
"""Noncircular r3 freeze. Stdlib only; no ML/native imports/deserialization."""
from pathlib import Path
import copy
import json
import shutil
import sys
import time
import long_d2 as c
HERE=Path(__file__).resolve().parent
ROOT=c.ORIGINAL_ROOT
R2=HERE.parent/'postovernight-long-D2-prepare-r2'


def old_union():
    identity=c.read_json(R2/'long-identity.json');manifest=c.read_json(R2/'capsule-final/capsule-manifest.json')
    pins={str(R2/'capsule-final'/k):v for k,v in manifest['files'].items()}
    pins.update(identity['original_input_pins'])
    pins.update({str(ROOT/k):v for k,v in identity['controller_sources'].items()})
    pins[str(R2/'capsule-final/capsule-manifest.json')]=c.sha(R2/'capsule-final/capsule-manifest.json')
    pins[str(R2/'long-identity.json')]=c.sha(R2/'long-identity.json')
    c.require(len(pins)==793,'Exact retained r2 union count differs')
    return pins


def source_inventory():
    return {str(p.relative_to(ROOT)):c.sha(p) for p in sorted(HERE.iterdir())
            if p.is_file() and p.suffix in ('.py','.txt','.md')}


def freeze():
    start=time.monotonic()
    p=c.registered_protocol(ROOT/c.PROTOCOL_REL)
    prior=c.read_json(R2/'long-identity.json')
    protected=c.read_json(HERE/'protected-before.json')
    immutable={k:v for k,v in protected.items() if k not in
               {str(ROOT/'learning/runs/v2-orchestration/state.json'),str(ROOT/'docs/v2-foundation-progress.md')}}
    pins=old_union()
    for path,digest in immutable.items():
        c.require(path not in pins or pins[path]==digest,'Retained old digest differs')
        pins[path]=digest
    sources=source_inventory()
    pins[str(ROOT/c.PROTOCOL_REL)]=c.PROTOCOL_SHA256
    c.verify_files(pins)
    identity=copy.deepcopy(prior)
    identity.update(protocol_sha256=c.PROTOCOL_SHA256,controller_sources=sources,original_input_pins=pins,
        original_only_historical_reference_pins=dict(pins),
        controller_source_scope='exact complete active r3 root Python/text/README inventory; old evidence original-only',
        retained_r2_union=old_union(),terminal_lifecycle=p['terminal_lifecycle'],
        terminal_parent_addendum_sha256=c.sha(ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-terminal-design-parent-addendum-r1.json'))
    c.require(len(identity['base_registered_identity']['sources'])==75,'Original legacy inventory differs')
    c.save(HERE/'long-identity.json',identity)
    capsule=HERE/'capsule-final';capsule.mkdir()
    previous=c.read_json(R2/'capsule-final/capsule-manifest.json')['files']
    files={}
    for name,digest in previous.items():
        source=R2/'capsule-final'/name;target=capsule/name
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);files[name]=digest
    additions=dict(sources)
    for name in (c.PROTOCOL_REL,p['design'],
        'learning/runs/v2/postovernight-long-D2-terminal-design-codex-r1/design.md',
        'learning/runs/v2/postovernight-long-D2-terminal-design-codex-r1/inputs-sha256.json',
        'learning/runs/v2-orchestration/postovernight-long-D2-terminal-design-parent-addendum-r1.json',
        'learning/runs/v2-orchestration/postovernight-long-D2-terminal-design-parent-reconciliation-r1.json',
        c.PREPARE_REL+'/long-identity.json'):
        additions[name]=c.sha(ROOT/name)
    for name,digest in additions.items():
        target=capsule/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target);files[name]=digest
    c.verify_files({str(capsule/k):v for k,v in files.items()})
    c.save(capsule/'capsule-manifest.json',dict(version='long_d2_capsule_v1',files=files,
                manifest_excludes_itself=True,original_package_imports=True))
    for path in capsule.rglob('*'):
        if path.is_file():path.chmod(0o444)
    for path in sorted((p for p in capsule.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):path.chmod(0o555)
    capsule.chmod(0o555)
    preflight=c.pure_preflight(capsule)
    c.save(HERE/'freeze-receipt.json',preflight);c.save(HERE/'required-lease.json',preflight['required_lease'])
    registration=dict(schema='long_d2_executor_registration_v1',capsule_path=str(capsule),
        controller=str(capsule/c.PREPARE_REL/'long_d2.py'),executor=str(capsule/c.PREPARE_REL/'long_d2_executor.py'),
        output=str(ROOT/p['output']),receipt=str(ROOT/p['terminal_lifecycle']['acceptance_receipt']),state_path=str(c.STATE_PATH),
        protocol_sha256=c.PROTOCOL_SHA256,config_sha256=c.CONFIG_SHA256,
        identity_sha256=c.sha(HERE/'long-identity.json'),capsule_manifest_sha256=c.sha(capsule/'capsule-manifest.json'),
        pins={str(capsule/name):c.sha(capsule/name) for name in
            (c.PREPARE_REL+'/long_d2.py',c.PREPARE_REL+'/long_d2_executor.py',c.PREPARE_REL+'/long-identity.json',
             'capsule-manifest.json',c.PROTOCOL_REL,p['config_path'])})
    c.save(HERE/'registration.json',registration)
    command=[str(ROOT/'learning/.venv/bin/python'),'-B',registration['executor'],'run','--registration',str(HERE/'registration.json')]
    c.save(HERE/'invocation.json',dict(argv=command,cwd=str(capsule),environment={'PYTHONDONTWRITEBYTECODE':'1'},
        unset_environment=['PYTORCH_ENABLE_MPS_FALLBACK'],registration_sha256=c.sha(HERE/'registration.json'),
        registration=registration,no_launch_performed=True,execute_only_after_fresh_parent_frozen_review_and_exact_lease=True,
        parent_must_observe_outer_raw_exit_and_wall=True))
    context=c.capsule_context(capsule)
    c.require(all(context[4].get(k)==v for k,v in old_union().items()),'Retained 793-pin union changed')
    c.save(HERE/'expanded-inventory.json',dict(retained_old_union_count=793,new_full_pin_count=len(context[4]),
        all_old_exact_digests_retained=True,full_pins=context[4],source_inventory=sources,
        identity_raw_sha256=c.sha(HERE/'long-identity.json'),identity_semantic_sha256=c.semantic_hash(identity),
        capsule_manifest_sha256=registration['capsule_manifest_sha256'],freeze_elapsed_seconds=time.monotonic()-start))
    print(json.dumps(dict(status='frozen_preparation_only',pins=len(context[4]),capsule_files=len(files),
                         sources=len(sources),elapsed_seconds=time.monotonic()-start),sort_keys=True))


if __name__=='__main__':freeze()
