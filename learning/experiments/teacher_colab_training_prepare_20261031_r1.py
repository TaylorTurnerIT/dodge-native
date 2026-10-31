"""Freeze parent058 bindings without account calls, engine imports or pool reads.

Run once for this candidate. Existing candidates are never rewritten. The
generated preparation plan omits a review and cannot launch an assignment.
"""
import importlib.util
import json
from pathlib import Path
import sys
import uuid

SOURCE = Path(__file__).with_name('teacher_colab_training_dispatch_20261031_r1.py')
spec = importlib.util.spec_from_file_location('dodge058_preparation', SOURCE)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


def prepare():
    owner_root = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-teacher-ray-geometry-20261030')
    owner = owner_root/'learning/experiments/teacher_ray_colab_training_r1'
    packet = owner_root/'learning/runs/v2/teacher-ray-colab-training-20261031-r1'
    freeze_path = packet/'owner-source-freeze-r1.json'
    c.need(c.sha(freeze_path) == 'e176a67cc5e1143264d11b81ac28a9b40137f92ffa7d10a164e9ec13da09483f', 'Owner freeze differs')
    freeze = c.read(freeze_path)
    for path,digest in freeze['source_pins'].items():
        c.need(c.sha(path) == digest, 'Owner frozen source changed')
    c.need(c.sha(freeze['payload_path']) == freeze['payload_sha256'], 'Owner payload changed')
    recipe = c.read(owner/'scientific_recipe.json')
    old_path = owner_root/'learning/runs/v2/teacher-ray-screen-20261030-r4/registration-r4.json'
    old = c.read(old_path)
    c.need(c.sha(old_path) == '1881aad8554a0841246248c2cb0e6ae49dc425716f924b6824b440eeaa53a94e', 'Scientific predecessor differs')
    controller_paths = [c.BASE, SOURCE, SOURCE.with_name('teacher_colab_training_transport_20261031_r1.py'),
                        SOURCE.with_name('teacher_colab_training_budget_20261031_r1.py')]
    coordinator_pins = {str(p.resolve()): c.sha(p) for p in controller_paths}
    source_pins = dict(freeze['source_pins'], **coordinator_pins)
    for path in [Path(__file__).resolve(), c.ROOT/'learning/tests/test_teacher_colab_training_dispatch_20261031_r1.py',
                 c.ROOT/'learning/tests/test_teacher_colab_training_budget_20261031_r1.py']:
        source_pins[str(path)] = c.sha(path)
    budget = c.load(controller_paths[-1], c.sha(controller_paths[-1]), 'dodge058_prepare_budget')
    lease = dict(kind='teacher_ray_cloud_training', owner_token='rays058-a100-20261031-first-training-r2',
                 package=str(packet), promoted=False, record='DODGE-058', run_id='teacher-ray-colab-training-20261031-r1')
    authority_path = c.PARENT/'authority-DODGE058-A100-training-r2.json'
    authority = dict(schema='dodge058_parent_training_authority_v1', record='DODGE-058', accelerator='A100',
        allocation_attempts_authorized=1, limits=vars(budget.Config()), expected_lease=lease,
        state_path=str(c.ROOT/'learning/runs/v2-orchestration/state.json'),
        conditional_training_after_build_admission=True,
        user_authority='Taylor directed Colab migration and said Go. Cheaper GPUs were permitted for non-training checks; actual training remains A100.',
        required_gates=['Fresh independent exact joint review', 'Accepted061 prerequisite and free shared lease',
                        'Fresh zero assignments, sole persisted UUID, exact A100 response and admitted live price',
                        'Pinned actual image and isolated Linux build certificate before engine constructor',
                        'Counted first2 native CUDA updates per job with original full-path/resource gates'],
        no_retry=True, no_resume=True, evaluation_authorized=False, promotion=False, AC_required=False,
        scientific_recipe_sha256=freeze['scientific_recipe_sha256'],
        billing_limitations='Rate/clock/balance admission bounds are best effort; meter has no server timestamp or refresh guarantee. No hard billing guarantee.',
        cost_accounting='max(observed debit, 1CU prior pending allowance + elapsed*7/3600); remaining horizon at7CU/hour. No double counting.',
        failed_records_preserved=['DODGE-051','DODGE-055','DODGE-056','DODGE-057','DODGE-059','DODGE-060'],
        training_updates=36, total_actual_gameplay_frames=9437184,
        reserved_cohorts_unopened=['D10','D11','D12','D13'],
        authority_alone_is_not_dispatch=True)
    authority_sha = c.save(authority_path, authority)
    registration_path = c.PARENT/'DODGE-058-A100-training-registration-r2.json'
    cli = c.read(c.PARENT/'DODGE-057-A100-registration-r2.json')
    input_pins = {p:d for p,d in cli['input_pins'].items()
                  if p.startswith('/tmp/dodge-colab-cli-20261031-venv/')}
    prerequisite = c.PARENT/'dispatch-DODGE061-archive-r1/coordinator-terminal-audit.json'
    for path in [freeze_path, packet/'payload-manifest.json', packet/'source-payload.tar', packet/'CPU-tests.json',
                 old_path, Path(old['checkpoint_path']), authority_path, prerequisite,
                 Path(freeze['vendor_provenance_path'])]:
        input_pins[str(path)] = c.sha(path)
    logs = []
    for stem in ['DODGE-058-parent-CPU-tests-r3','DODGE-058-budget-CPU-tests-r2','DODGE-058-owner-CPU-tests-parent-r1']:
        for suffix in ['stdout','stderr']:
            path = c.PARENT/(stem+'.'+suffix);input_pins[str(path)] = c.sha(path);logs.append(str(path))
    pool = dict(local=old['pool_path'], remote='/content/dodge058/inputs/training-pool512.json',
                sha256=recipe['pool_sha256'], preparation_opened=False, admission='Read/hash/upload only after reviewed exact058 lease acquisition')
    uploads = [dict(local=freeze['payload_path'],remote='/content/dodge058/source-input.tar',sha256=freeze['payload_sha256']),
               dict(local=old['checkpoint_path'],remote='/content/dodge058/inputs/checkpoint420.pt',sha256=recipe['checkpoint_sha256']),
               {k:pool[k] for k in ['local','remote','sha256']}]
    manifest = c.read(packet/'payload-manifest.json')
    remote_pins = {'/content/dodge058/'+p:d for p,d in manifest['members'].items()}
    remote_pins.update({asset['remote']:asset['sha256'] for asset in uploads[1:]})
    cache = c.PARENT/'DODGE058-parent-empty-pycache-r2';cache.mkdir()
    reg = dict(recipe)
    reg.update(schema='dodge_colab_native_training_registration_v1', record='DODGE-058',
        job_nonce=str(uuid.uuid4()), accelerator='A100', device='cuda:0',
        no_retry=True, no_resume=True, promotion=False, training_stage_authorized=True,
        output_root='/content/dodge058', runtime_root='/content/dodge058/runtime', vendor_root='/content/dodge058/vendor',
        checkpoint_path=uploads[1]['remote'], pool_path=pool['remote'],
        native_setup_work_seconds=900, stage_timeout_seconds={'build':1100,'train':22320},linux_toolchain=None,
        source_pins=source_pins, input_pins=input_pins, coordinator_source_pins=coordinator_pins,
        remote_input_pins=remote_pins, owner_source_root=str(owner),owner_freeze_path=str(freeze_path),
        owner_freeze_sha256=c.sha(freeze_path), owner_source_commit=freeze['source_commit'],
        payload_sha256=freeze['payload_sha256'],payload_bytes=freeze['payload_bytes'],
        unpack_script=str(owner/'unpack_launcher.py'),stage_script=str(owner/'stage_launcher.py'),
        authority_path=str(authority_path),authority_sha256=authority_sha,financial_limits=vars(budget.Config()),
        expected_lease=lease,expected_lease_sha256=__import__('hashlib').sha256(c.canonical(lease)).hexdigest(),
        state_path=authority['state_path'],prerequisite_path=str(prerequisite),prerequisite_sha256=c.PREREQUISITE_SHA,
        adapter_path=str(controller_paths[2]),budget_path=str(controller_paths[3]),
        cli_path=cli['cli_path'],sdk_python=cli['sdk_python'],cli_config_path=cli['cli_config_path'],
        empty_pycache=str(cache),session_name='colab058-a100-training-20261031-r2',
        registration_local=str(registration_path),deferred_training_pool=pool,uploads=uploads,
        control_contract=dict(TTL_seconds=45,refresh_seconds=15,maximum_financial_permit_age_seconds=35,
                              numeric_unix_UTC=True, serialized_stage_transition=True),
        execution_authorized_by_registration_alone=False,launch_authority=False,
        evaluation_authorized=False, reserved_cohorts_unopened=['D10','D11','D12','D13'],
        preparation_limits='CPU/source tests only. Linux build, actual extension import/ABI, A100/counting/throughput remain unobserved.',
        CPU_evidence=dict(parent_tests=33,budget_tests=7,owner_tests=105,logs=logs,
                          native_imports=0,native_games=0,VM_allocations=0,seed_pool_opened=False))
    reg_sha = c.save(registration_path, reg)
    plan = dict(record='DODGE-058',registration_path=str(registration_path),registration_sha256=reg_sha,
                authority_path=str(authority_path),authority_sha256=authority_sha,
                status='preparation_only_missing_independent_review')
    plan_path=c.PARENT/'DODGE-058-preparation-plan-r2.json';c.save(plan_path,plan)
    c.validate_plan(plan,preparation=True)
    print(json.dumps(dict(registration_path=str(registration_path),registration_sha256=reg_sha,
                          preparation_plan_sha256=c.sha(plan_path),execution_authorized=False)))


if __name__=='__main__':prepare()
