#!/usr/bin/env python3
"""Noncircular r2 experiment freeze. Never freezes mutable parent state/progress."""
from pathlib import Path
import copy,json,shutil,time
import long_d2 as c
HERE=Path(__file__).resolve().parent;ROOT=c.ORIGINAL_ROOT
R4=HERE.parent/'postovernight-long-D2-prepare-r4'

def old_union():
    # Compatibility for inherited 9675-pin regression; r4 superset separately mandatory.
    return c.read_json(R4/'long-identity.json')['retained_r3_union']

def freeze():
    start=time.monotonic();p=c.registered_protocol(ROOT/c.PROTOCOL_REL)
    old=c.read_json(R4/'expanded-inventory.json')['full_pins']
    c.require(len(old)==9870 and len(old_union())==9675,'Historical pin count differs')
    sources={str(x.relative_to(ROOT)):c.sha(x) for x in sorted(HERE.iterdir()) if x.is_file() and x.suffix in ('.py','.md','.txt')}
    pins=dict(old)
    additions={c.PROTOCOL_REL:c.PROTOCOL_SHA256,p['config_path']:c.CONFIG_SHA256,
               p['guard_repair_plan']:p['guard_repair_plan_sha256'],p['guard_diagnosis']:p['guard_diagnosis_sha256'],
               'learning/runs/v2/postovernight-long-D2-guard-diagnosis-opus-r1/diagnosis.md':'55ea4fc91a6ff33ea4bebd88c9713b15316105685460fccf3cb968d51f082c2d'}
    for name,digest in additions.items():
        path=str(ROOT/name);c.require(path not in pins or pins[path]==digest,'Immutable pin conflict');pins[path]=digest
    c.require(str(c.STATE_PATH) not in pins and str(ROOT/'docs/v2-foundation-progress.md') not in pins,'Mutable parent pin forbidden')
    c.verify_files(pins)
    identity=copy.deepcopy(c.read_json(R4/'long-identity.json'))
    identity.update(protocol_sha256=c.PROTOCOL_SHA256,controller_sources=sources,original_input_pins=pins,
        original_only_historical_reference_pins=dict(pins),retained_r4_union=dict(old),
        controller_source_scope='complete new owned root Python and README; retained R4 full-pin union unchanged',
        terminal_lifecycle=p['terminal_lifecycle'],guard_repair_plan_sha256=p['guard_repair_plan_sha256'],
        guard_timing_output_policy=dict(worker='campaign/worker-verification.jsonl and .manifest.json are manifest-bound',
            inner='execution/inner-verification.jsonl and .manifest.json are separate execution evidence',
            outer='execution/outer-verification.jsonl and .manifest.json are separate execution evidence',
            buffering='bounded memory; persist only after owned Guard threads absent; deadline-owned main-thread IO',
            abrupt_exit='unflushed rows may be lost; no new telemetry thread or independent deadline'))
    c.save(HERE/'long-identity.json',identity)
    capsule=HERE/'capsule-final';capsule.mkdir()
    files={}
    previous=c.read_json(R4/'capsule-final/capsule-manifest.json')['files']
    for name,digest in previous.items():
        target=capsule/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R4/'capsule-final'/name,target);files[name]=digest
    for name,digest in {**sources,**additions,c.PREPARE_REL+'/long-identity.json':c.sha(HERE/'long-identity.json')}.items():
        target=capsule/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);files[name]=digest
    c.verify_files({str(capsule/k):v for k,v in files.items()})
    c.save(capsule/'capsule-manifest.json',dict(version='long_d2_capsule_v1',files=files,manifest_excludes_itself=True,original_package_imports=True))
    for x in capsule.rglob('*'):
        if x.is_file():x.chmod(0o444)
    for x in sorted((x for x in capsule.rglob('*') if x.is_dir()),key=lambda x:len(x.parts),reverse=True):x.chmod(0o555)
    capsule.chmod(0o555)
    preflight=c.pure_preflight(capsule);c.save(HERE/'freeze-receipt.json',preflight);c.save(HERE/'required-lease.json',preflight['required_lease'])
    registration=dict(schema='long_d2_executor_registration_v1',capsule_path=str(capsule),controller=str(capsule/c.PREPARE_REL/'long_d2.py'),
        executor=str(capsule/c.PREPARE_REL/'long_d2_executor.py'),output=str(ROOT/p['output']),receipt=str(ROOT/p['terminal_lifecycle']['acceptance_receipt']),
        state_path=str(c.STATE_PATH),protocol_sha256=c.PROTOCOL_SHA256,config_sha256=c.CONFIG_SHA256,
        identity_sha256=c.sha(HERE/'long-identity.json'),capsule_manifest_sha256=c.sha(capsule/'capsule-manifest.json'),
        pins={str(capsule/name):c.sha(capsule/name) for name in (c.PREPARE_REL+'/long_d2.py',c.PREPARE_REL+'/long_d2_executor.py',
            c.PREPARE_REL+'/long-identity.json','capsule-manifest.json',c.PROTOCOL_REL,p['config_path'])})
    c.save(HERE/'registration.json',registration)
    c.save(HERE/'invocation.json',dict(argv=[str(ROOT/'learning/.venv/bin/python'),'-B',registration['executor'],'run','--registration',str(HERE/'registration.json')],
        cwd=str(capsule),environment={'PYTHONDONTWRITEBYTECODE':'1'},unset_environment=['PYTORCH_ENABLE_MPS_FALLBACK'],
        registration_sha256=c.sha(HERE/'registration.json'),no_launch_performed=True,parent_frozen_review_required=True,lease_not_published=True))
    context=c.capsule_context(capsule)
    c.require(all(context[4].get(k)==v for k,v in old.items()),'R4 union lost')
    c.require(all(context[4].get(k)==v for k,v in old_union().items()),'R3 union lost')
    c.save(HERE/'expanded-inventory.json',dict(retained_r4_union_count=9870,retained_older_union_count=9675,new_full_pin_count=len(context[4]),full_pins=context[4],
        capsule_files=len(files),source_inventory=sources,identity_raw_sha256=c.sha(HERE/'long-identity.json'),
        identity_semantic_sha256=c.semantic_hash(identity),capsule_manifest_sha256=registration['capsule_manifest_sha256'],freeze_elapsed_seconds=time.monotonic()-start))
    print(json.dumps(dict(status='frozen_preparation_only',pins=len(context[4]),capsule_files=len(files),sources=len(sources))))

if __name__=='__main__':freeze()
