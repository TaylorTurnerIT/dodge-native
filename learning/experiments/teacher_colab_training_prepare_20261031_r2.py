"""Freeze062 source without account calls, seed reads or lease mutation.

Recipe and engine/runtime bytes retain058 lineage. Only new owned paths receive
outputs. Existing candidates are never rewritten; no earlier preparer is run.
"""
import copy
import importlib.util
import json
from pathlib import Path,PurePosixPath
import subprocess
import tarfile
import uuid

SOURCE=Path(__file__).with_name('teacher_colab_training_dispatch_20261031_r2.py')
spec=importlib.util.spec_from_file_location('dodge062_preparation',SOURCE)
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


def prepare():
    parent=c.PARENT;owner=c.ROOT/'learning/experiments/teacher_ray_colab_training_r2'
    packet=c.ROOT/'learning/runs/v2/teacher-ray-colab-training-20261031-r2'
    old=c.read(parent/'DODGE-058-A100-training-registration-r2.json')
    old_freeze=c.read(old['owner_freeze_path']);old_source=Path(old['owner_source_root'])
    disposition=c.failed058_disposition()
    owner_pins={str(p):c.sha(p) for p in sorted(owner.rglob('*')) if p.is_file()}
    c.need(len(owner_pins)==92,'Unexpected successor source inventory')
    unchanged=0
    for path,digest in owner_pins.items():
        relative=Path(path).relative_to(owner)
        if relative.parts[0] in ['runtime','native_source']:
            c.need(old_freeze['source_pins'].get(str(old_source/relative))==digest,'Engine/runtime changed')
            unchanged+=1
    c.need(unchanged==62,'Exact46 engine and16 Python runtime source files required')
    recipe=c.read(owner/'scientific_recipe.json');old_recipe=c.read(old_source/'scientific_recipe.json')
    c.need({k:v for k,v in recipe.items() if k!='record'}=={k:v for k,v in old_recipe.items() if k!='record'},'Recipe changed')
    vendor=packet/'vendor-source';vendor.mkdir()
    manifest=c.read(old_freeze['payload_manifest_path'])['members']
    c.need(c.sha(old_freeze['payload_path'])==old_freeze['payload_sha256'],'Preserved payload changed')
    with tarfile.open(old_freeze['payload_path'],'r:') as archive:
        for item in archive.getmembers():
            path=PurePosixPath(item.name)
            c.need(item.isfile() and not path.is_absolute() and '..' not in path.parts,'Unsafe preserved member')
            if path.parts[0]!='vendor':continue
            data=archive.extractfile(item).read()
            c.need(__import__('hashlib').sha256(data).hexdigest()==manifest[item.name],'Vendor changed')
            target=vendor/Path(*path.parts[1:]);target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(data)
    c.load(owner/'common.py',owner_pins[str(owner/'common.py')],'common')
    bundle=c.load(owner/'bundle.py',owner_pins[str(owner/'bundle.py')],'dodge062_bundle')
    payload=bundle.write(packet/'source-payload.tar',vendor);c.save(packet/'payload-manifest.json',payload)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    freeze_path=packet/'owner-source-freeze-r1.json'
    c.save(freeze_path,dict(schema='dodge062_owner_source_freeze_v1',record='DODGE-062',source_commit=commit,
        source_pins=owner_pins,source_file_count=92,unchanged_native_and_runtime_files=62,
        old058_owner_freeze_sha256=old['owner_freeze_sha256'],payload_path=payload['path'],payload_sha256=payload['sha256'],
        payload_bytes=payload['bytes'],payload_members=len(payload['members']),scientific_recipe_sha256=c.sha(owner/'scientific_recipe.json'),
        declared_changes='058-to062 identity; relocated old-PPO comparison test reference. Engine/runtime/recipe unchanged.',execution_authorized=False))
    disposition_path=parent/'DODGE-058-failure-disposition-for062-r1.json';c.save(disposition_path,disposition)
    controllers=[c.BASE,SOURCE,SOURCE.with_name('teacher_colab_training_transport_20261031_r2.py'),
                 SOURCE.with_name('teacher_colab_training_budget_20261031_r2.py'),SOURCE.with_name('teacher_colab_control_channel_20261031_r1.py')]
    coordinator_pins={str(p.resolve()):c.sha(p) for p in controllers};source_pins={**owner_pins,**coordinator_pins}
    extras_source=[Path(__file__).resolve(),*[c.ROOT/('learning/tests/'+name) for name in
        ['test_teacher_colab_training_dispatch_20261031_r2.py','test_teacher_colab_training_budget_20261031_r2.py','test_teacher_colab_control_channel_20261031_r1.py']]]
    source_pins.update({str(p):c.sha(p) for p in extras_source})
    budget=c.load(controllers[3],c.sha(controllers[3]),'dodge062_budget')
    prior_basis=c.read(parent/'DODGE-058-preparation-contract-draft-r1.json')['prior_owned_assignment_allowance_basis']
    prior_upper=sum(r['cost_upper_estimate_CU'] for r in prior_basis)+disposition['prior_assignment_upper_seconds']*7/3600
    c.need(prior_upper<1.25,'Prior pending-charge allowance insufficient')
    lease=dict(kind='teacher_ray_cloud_training',owner_token='rays062-a100-20261031-first-training-r1',package=str(packet),
               promoted=False,record='DODGE-062',run_id='teacher-ray-colab-training-20261031-r2')
    authority_path=parent/'authority-DODGE062-A100-training-r1.json'
    authority=dict(schema='dodge062_parent_training_authority_v1',record='DODGE-062',accelerator='A100',allocation_attempts_authorized=1,
        limits=vars(budget.Config()),expected_lease=lease,previous_lease=old['expected_lease'],state_path=old['state_path'],
        conditional_training_after_build_admission=True,user_authority='Taylor said Go after failed058 and the proposal to diagnose then prepare another reviewed attempt.',
        no_retry=True,no_resume=True,evaluation_authorized=False,promotion=False,AC_required=False,
        failure_disposition_sha256=c.sha(disposition_path),never_clear_failed_lease_to_null=True,
        conservative_prior_owned_charge_upper_CU=prior_upper,rounded_prior_pending_allowance_CU=1.25,prior_basis=prior_basis,
        failed058_elapsed_seconds=disposition['prior_assignment_upper_seconds'],control_deadline_seconds=8,control_startup_seconds=15,
        TTL_seconds=45,refresh_seconds=15,requests_connect_read_seconds=[2,5],control_retries=0,control_restarts=0,
        required_gates=['Fresh independent joint review','Durable exact non-null058-to062 handoff','Sole owned A100 <=7CU/hour',
                        'Fresh pinned Linux build admission','Original counted first2 qualification per job'],
        reserved_cohorts_unopened=['D10','D11','D12','D13'],billing_limitations='No hard billing or freshness guarantee. max(observed,1.25+elapsed*7/3600).')
    c.save(authority_path,authority)
    input_pins={p:d for p,d in old['input_pins'].items() if p.startswith('/tmp/dodge-colab-cli-20261031-venv/')}
    packages=Path('/tmp/dodge-colab-cli-20261031-venv/lib/python3.12/site-packages')
    for name in ['requests','urllib3']:input_pins.update({str(p):c.sha(p) for p in (packages/name).rglob('*.py')})
    preserved_ppo=old_source.parents[1]/'runs/v2/teacher-ray-screen-20261030-r3/runtime/dodge_rl/ppo.py'
    extras=[freeze_path,packet/'payload-manifest.json',packet/'source-payload.tar',authority_path,disposition_path,
        parent/'DODGE-058-A100-training-registration-r2.json',parent/'blocking-incident-DODGE058-A100-training-r2.json',
        Path(old['uploads'][1]['local']),Path(old['prerequisite_path']),Path(old_freeze['vendor_provenance_path']),preserved_ppo,
        parent/'DODGE-062-saved-transport-diagnosis-r1.json',*[Path(r['receipt_path']) for r in prior_basis]]
    logs=[]
    for stem in ['DODGE-062-parent-CPU-r2','DODGE-062-budget-CPU-r1','DODGE-062-channel-CPU-r1','DODGE-062-owner-CPU-r1']:
        for suffix in ['stdout','stderr']:
            path=parent/(stem+'.'+suffix);logs.append(str(path));extras.append(path)
    for path in extras:input_pins[str(path)]=c.sha(path)
    pool=dict(old['deferred_training_pool']);pool.update(remote='/content/dodge062/inputs/training-pool512.json',preparation_opened=False)
    uploads=[dict(local=payload['path'],remote='/content/dodge062/source-input.tar',sha256=payload['sha256']),
        dict(local=old['uploads'][1]['local'],remote='/content/dodge062/inputs/checkpoint420.pt',sha256=old['checkpoint_sha256']),
        {k:pool[k] for k in ['local','remote','sha256']}]
    remote_pins={'/content/dodge062/'+p:d for p,d in payload['members'].items()};remote_pins.update({a['remote']:a['sha256'] for a in uploads[1:]})
    cache=parent/'DODGE062-parent-empty-pycache-r1';cache.mkdir()
    registration_path=parent/'DODGE-062-A100-training-registration-r1.json'
    reg=copy.deepcopy(old)
    reg.update(recipe)
    reg.update(schema='dodge_colab_native_training_registration_v1',record='DODGE-062',job_nonce=str(uuid.uuid4()),output_root='/content/dodge062',runtime_root='/content/dodge062/runtime',
        vendor_root='/content/dodge062/vendor',checkpoint_path=uploads[1]['remote'],pool_path=pool['remote'],
        source_pins=source_pins,input_pins=input_pins,coordinator_source_pins=coordinator_pins,remote_input_pins=remote_pins,
        owner_source_root=str(owner),owner_freeze_path=str(freeze_path),owner_freeze_sha256=c.sha(freeze_path),owner_source_commit=commit,
        payload_sha256=payload['sha256'],payload_bytes=payload['bytes'],unpack_script=str(owner/'unpack_launcher.py'),stage_script=str(owner/'stage_launcher.py'),
        authority_path=str(authority_path),authority_sha256=c.sha(authority_path),financial_limits=vars(budget.Config()),
        expected_lease=lease,previous_lease=old['expected_lease'],expected_lease_sha256=__import__('hashlib').sha256(c.canonical(lease)).hexdigest(),
        failure_disposition_path=str(disposition_path),failure_disposition_sha256=c.sha(disposition_path),adapter_path=str(controllers[2]),
        budget_path=str(controllers[3]),control_channel_path=str(controllers[4]),empty_pycache=str(cache),session_name='colab062-a100-training-20261031-r1',
        registration_local=str(registration_path),deferred_training_pool=pool,uploads=uploads,
        control_contract=dict(TTL_seconds=45,refresh_seconds=15,maximum_financial_permit_age_seconds=35,request_seconds=8,startup_seconds=15,
                              transport='single persistent process and HTTPS session; no retry or restart'),
        CPU_evidence=dict(parent_tests=35,budget_tests=7,channel_tests=12,owner_tests=105,logs=logs,native_games=0,VM_allocations=0),
        preparation_limits='062 CPU/source only. Same engine/runtime; fresh build/import/A100 qualification still required. No allocation or pool read.')
    c.save(registration_path,reg)
    plan=dict(record='DODGE-062',registration_path=str(registration_path),registration_sha256=c.sha(registration_path),
              authority_path=str(authority_path),authority_sha256=c.sha(authority_path),status='preparation_only_missing_independent_review')
    plan_path=parent/'DODGE-062-preparation-plan-r1.json';c.save(plan_path,plan);c.validate_plan(plan,preparation=True)
    print(json.dumps(dict(registration_path=str(registration_path),registration_sha256=c.sha(registration_path),
                         preparation_plan_sha256=c.sha(plan_path),execution_authorized=False)))


if __name__=='__main__':prepare()
