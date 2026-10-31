"""Freeze one fresh064 successor. No account, allocation, native or pool read."""
import copy,importlib.util,json,os,subprocess,tarfile,uuid
from pathlib import Path,PurePosixPath

SOURCE=Path(__file__).with_name('teacher_colab_durable_dispatch_20261031_r1.py')
spec=importlib.util.spec_from_file_location('durable_prepare_parent',SOURCE);c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


def prepare():
    parent=c.PARENT;owner=c.ROOT/'learning/experiments/teacher_ray_colab_training_r3'
    packet=c.ROOT/'learning/runs/v2/teacher-ray-colab-training-20261031-r4';packet.mkdir()
    old=c.read(c.OLD_PARENT/'DODGE-062-A100-training-registration-r2.json');old_source=Path(old['owner_source_root'])
    disposition=c.failed062_disposition();old_freeze=c.read(old['owner_freeze_path'])
    owner_pins={str(p):c.sha(p) for p in sorted(owner.rglob('*')) if p.is_file()}
    need=c.need;need(not any('__pycache__' in Path(p).parts for p in owner_pins),'Source cache forbidden')
    unchanged=0
    for filename,digest in owner_pins.items():
        relative=Path(filename).relative_to(owner)
        if relative.parts[0] in ('runtime','native_source'):
            need(old['source_pins'].get(str(old_source/relative))==digest,'Science runtime/engine changed')
            unchanged+=1
    need(unchanged==62,'Exact46 engine plus16 runtime members required')
    recipe=c.read(owner/'scientific_recipe.json');old_recipe=c.read(old_source/'scientific_recipe.json')
    for key,value in old_recipe.items():
        if key not in ('record','pool_path','campaign_total_seconds'):need(recipe[key]==value,'Scientific recipe changed: '+key)
    need(recipe['campaign_total_seconds']==21320,'Hardened total work cap differs')
    vendor=packet/'vendor-source';vendor.mkdir()
    need(c.sha(old_freeze['payload_path'])==old_freeze['payload_sha256'],'Preserved vendor payload changed')
    with tarfile.open(old_freeze['payload_path'],'r:') as archive:
        manifest=json.loads(archive.extractfile('source-manifest.json').read())
        for member in archive.getmembers():
            path=PurePosixPath(member.name)
            need(member.isfile() and not path.is_absolute() and '..' not in path.parts,'Unsafe vendor archive')
            if path.parts[0]!='vendor':continue
            data=archive.extractfile(member).read();need(__import__('hashlib').sha256(data).hexdigest()==manifest[member.name],'Locked vendor bytes changed')
            target=vendor/Path(*path.parts[1:]);target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(data)
    c.load(owner/'common.py',owner_pins[str(owner/'common.py')],'common')
    bundle=c.load(owner/'bundle.py',owner_pins[str(owner/'bundle.py')],'durable_source_bundle')
    payload=bundle.write(packet/'source-payload.tar',vendor);c.save(packet/'payload-manifest.json',payload)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    freeze=packet/'owner-source-freeze-r1.json'
    c.save(freeze,dict(schema='dodge064_owner_source_freeze_v1',record='DODGE-064',source_commit=commit,
        source_pins=owner_pins,source_file_count=len(owner_pins),unchanged_native_and_runtime_files=62,
        old062_registration_sha256=c.OLD_REG_SHA,payload_path=payload['path'],payload_sha256=payload['sha256'],
        payload_bytes=payload['bytes'],payload_members=len(payload['members']),execution_authorized=False))
    disposition_path=parent/'DODGE-062-failure-disposition-for064-r2.json';c.save(disposition_path,disposition)
    controllers=[c.BASE,SOURCE,SOURCE.with_name('teacher_colab_durable_transport_20261031_r1.py'),SOURCE.with_name('teacher_colab_durable_budget_20261031_r1.py'),SOURCE.with_name('teacher_colab_durable_channel_20261031_r1.py')]
    coordinator_pins={str(p.resolve()):c.sha(p) for p in controllers};source_pins={**owner_pins,**coordinator_pins}
    tests=[c.ROOT/'learning/tests'/name for name in ['test_teacher_colab_durable_dispatch_20261031_r1.py','test_teacher_colab_durable_budget_20261031_r1.py','test_teacher_colab_durable_service_20261031_r1.py','test_teacher_colab_durable_channel_20261031_r1.py','test_teacher_colab_durable_custody_20261031_r1.py','fixtures/durable_colab_cpu.py']]
    tests += [c.ROOT/'learning/tests/test_teacher_colab_result_safety_20261031_r1.py',c.ROOT/'AGENTS.md',Path(__file__).resolve()]
    source_pins.update({str(p):c.sha(p) for p in tests})
    budget=c.load(controllers[3],c.sha(controllers[3]),'durable_budget_preparation')
    safety=dict(challenge_bytes=33554432,chunk_bytes=1048576,checkpoint_ack_seconds=60,job_ack_seconds=60,
                recovery_seconds=180,teardown_seconds=180,transfer_request_seconds=15,no_transfer_retry=True)
    lease=dict(kind='teacher_ray_cloud_training',owner_token='rays064-a100-durable-20261031-r1',package=str(packet),
               promoted=False,record='DODGE-064',run_id='teacher-ray-colab-training-20261031-r4')
    authority_path=parent/'authority-DODGE064-A100-durable-r2.json'
    authority=dict(schema='dodge064_durable_authority_v1',record='DODGE-064',accelerator='A100',allocation_attempts_authorized=1,
        limits=vars(budget.Config()),expected_lease=lease,previous_lease=old['expected_lease'],state_path=old['state_path'],
        result_safety=safety,user_authority='Taylor said Go after the replacement recovery path and mandatory independent-review/real-VM rehearsal gates.',
        conditional_training_after_storage_and_build_admission=True,no_training_retry=True,no_resume=True,evaluation_authorized=False,
        promotion=False,battery_allowed=True,prior_pending_charge_upper_CU=disposition['conservative_unreported_charge_upper_CU'],
        rounded_pending_allowance_CU=3.0,financial_scope='At most48 existingCU for this fresh assignment including3CU possible delayed charges; no purchase or cap increase.',
        maximum_assigned_seconds=23000,original_job_work_seconds=5400,original_job_receipt_seconds=180,
        hardened_training_stage_seconds=21320,setup_inclusive_seconds=1200,retrieval_teardown_reserve_seconds=480,
        recovery_export_sequence=900000,recovery_copy_attempts=1,
        transfer_retry_scope='No repeat/reset of an export or chunk. One separate declared900000 failure inventory copy; never repeat training.',
        exposure='Original four ABBA jobs,36updates and2359296actualK1frames each; backup waits count inside all work/campaign caps.',
        snapshot_scope='Model/Adam/RNG+adapter only; no full simulator restore or automatic resume.',
        reserved_cohorts_unopened=['D10','D11','D12','D13'],
        billing_limitations='Server meter has no freshness or hard billing guarantee. max(observed debit,3+elapsed*7/3600).',
        normal_release='Every required result copied and strictly validated before VM release; global lease accepted/released separately after coordinator direct reap.',
        emergency_release='Only registered guard failure or finite recovery deadline; cancel first, preserve backups and explicit data-at-risk incident before exact-owned cleanup.')
    c.save(authority_path,authority)
    # Only the pinned SDK/interpreter and immutable evidence are ordinary input pins.
    inputs={p:d for p,d in old['input_pins'].items() if p.startswith('/tmp/dodge-colab-cli-20261031-venv/')}
    extras=[freeze,packet/'payload-manifest.json',packet/'source-payload.tar',authority_path,disposition_path,
            c.OLD_PARENT/'DODGE-062-A100-training-registration-r2.json',c.OLD_PARENT/'dispatch-DODGE062-A100-training-r2/monitor-blocking-incident.json',
            Path(old['uploads'][1]['local']),Path(old['prerequisite_path']),c.ROOT/'learning/runs/v2/teacher-cloud-result-safety-20261031-r1/source-manifest-r1.json']
    for label in ('owner','integrated','budget','service','channel','custody'):
        for suffix in ('stdout','stderr'):extras.append(parent/('DODGE064-'+label+'-CPU-final.'+suffix))
    for p in extras:inputs[str(p)]=c.sha(p)
    challenge=packet/'storage-challenge';challenge.mkdir();whole=__import__('hashlib').sha256();chunks=[]
    for index in range(32):
        data=os.urandom(1048576);whole.update(data);p=challenge/('chunk-%02d.bin'%index)
        with p.open('xb') as stream:stream.write(data)
        item=dict(local=str(p),remote='/content/dodge064/inputs/challenge/'+p.name,sha256=c.sha(p));chunks.append(item);inputs[str(p)]=item['sha256']
    pool=dict(old['deferred_training_pool']);pool.update(remote='/content/dodge064/inputs/training-pool512.json',preparation_opened=False)
    uploads=[dict(local=payload['path'],remote='/content/dodge064/source-input.tar',sha256=payload['sha256']),
             dict(local=old['uploads'][1]['local'],remote='/content/dodge064/inputs/checkpoint420.pt',sha256=old['checkpoint_sha256']),
             {key:pool[key] for key in ('local','remote','sha256')},*chunks]
    remote_pins={'/content/dodge064/'+p:d for p,d in payload['members'].items()}
    remote_pins.update({item['remote']:item['sha256'] for item in uploads[1:]})
    cache=parent/'DODGE064-parent-empty-pycache-r2';cache.mkdir()
    path=parent/'DODGE-064-A100-durable-registration-r2.json';reg=copy.deepcopy(old);reg.update(recipe)
    reg.update(schema='dodge_colab_native_training_registration_v1',record='DODGE-064',job_nonce=str(uuid.uuid4()),output_root='/content/dodge064',runtime_root='/content/dodge064/runtime',vendor_root='/content/dodge064/vendor',
        checkpoint_path=uploads[1]['remote'],pool_path=pool['remote'],source_pins=source_pins,input_pins=inputs,coordinator_source_pins=coordinator_pins,
        remote_input_pins=remote_pins,owner_source_root=str(owner),owner_freeze_path=str(freeze),owner_freeze_sha256=c.sha(freeze),owner_source_commit=commit,
        payload_sha256=payload['sha256'],payload_bytes=payload['bytes'],unpack_script=str(owner/'unpack_launcher.py'),stage_script=str(owner/'stage_launcher.py'),
        authority_path=str(authority_path),authority_sha256=c.sha(authority_path),financial_limits=vars(budget.Config()),result_safety=safety,
        storage_challenge=dict(sha256=whole.hexdigest(),bytes=33554432,chunks=chunks),expected_lease=lease,previous_lease=old['expected_lease'],
        expected_lease_sha256=__import__('hashlib').sha256(c.canonical(lease)).hexdigest(),failure_disposition_path=str(disposition_path),failure_disposition_sha256=c.sha(disposition_path),
        adapter_path=str(controllers[2]),budget_path=str(controllers[3]),control_channel_path=str(controllers[4]),empty_pycache=str(cache),
        session_name='colab064-a100-durable-20261031-r1',registration_local=str(path),deferred_training_pool=pool,uploads=uploads,
        stage_timeout_seconds=dict(preflight=180,build=1100,train=21320),
        preparation_limits='Fresh064 exact-once successor. Source/CPU preparation never opens pool, allocates or imports native; launch requires exact independent review.',
        CPU_evidence=dict(owner='104passed1skipped',integrated=2,budget=7,service=7,channel=12,custody=39,
                          scope='CPU dummy metrics/weights do not qualify production decoder; actual native/CUDA stages remain conditional.'))
    c.save(path,reg)
    plan=dict(record='DODGE-064',registration_path=str(path),registration_sha256=c.sha(path),authority_path=str(authority_path),authority_sha256=c.sha(authority_path),
              status='prepared_missing_exact_independent_review')
    plan_path=parent/'DODGE-064-preparation-plan-r2.json';c.save(plan_path,plan)
    c.validate_plan(plan,preparation=True)
    print(json.dumps(dict(registration_path=str(path),registration_sha256=c.sha(path),source_pins=len(source_pins),input_pins=len(inputs),payload_members=len(payload['members']),
                         pool_opened=False,execution_authorized=False)))


if __name__=='__main__':prepare()
