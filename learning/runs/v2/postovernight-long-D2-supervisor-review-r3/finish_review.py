"""Seal read-only review receipts after every owned execution has ended."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PREP=HERE.parent/'postovernight-long-D2-prepare-r3'
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(name,value):(HERE/name).write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
expanded=read(HERE/'input-sha256-manifest-expanded.json')['files']
changed={path:dict(expected=digest,observed=sha(Path(path))) for path,digest in expanded.items() if sha(Path(path))!=digest}
protected=read(PREP/'protected-before.json')
protected_changed={path:dict(expected=digest,observed=sha(Path(path))) for path,digest in protected.items() if sha(Path(path))!=digest}
write('input-sha256-verification-after.json',dict(files=len(expanded),mismatches=changed,
    manifest_sha256=sha(HERE/'input-sha256-manifest-expanded.json'),protected_files=len(protected),
    protected_mismatches=protected_changed,verified_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
assert not changed and not protected_changed
observations=[]
for directory in (HERE/'positive-controls',HERE/'targeted-controls'):
    for path in sorted(directory.glob('*/observed-command.json')):
        value=read(path)
        observations.append(dict(root=path.parent,pid=value['raw_wait']['pid'],value=value))
for root in (HERE/'final-io-unblocked-control',HERE/'final-io-blocked-diagnostic'):
    value=read(root/'observed-command.json')
    observations.append(dict(root=root,pid=value['event']['pid'],value=value))
groups={};executors={}
def absent_group(pgid):
    try:os.killpg(pgid,0)
    except ProcessLookupError:return True
    return False
def absent_pid(pid):
    try:os.kill(pid,0)
    except ProcessLookupError:return True
    return False
for item in observations:
    receipt_path=item['root']/'execution/acceptance-receipt.json'
    receipt=read(receipt_path) if receipt_path.exists() else {}
    for record in receipt.get('ownership',{}).values():
        groups[str(record['pgid'])]=dict(positive_absence=absent_group(record['pgid']),
            ownership=record,receipt=str(receipt_path.relative_to(HERE)),
            nonchild_waitpid_claimed=False)
    executors[str(item['pid'])]=dict(positive_absence=absent_pid(item['pid']),observed_command=str((item['root']/'observed-command.json').relative_to(HERE)))
write('owned-processes-after.json',dict(registered_groups=groups,direct_executors=executors,
    all_positively_absent=all(value['positive_absence'] for value in list(groups.values())+list(executors.values())),
    groups_count=len(groups),executors_count=len(executors),unregistered_or_unknown_group_count_not_inferred=True))
assert all(value['positive_absence'] for value in list(groups.values())+list(executors.values()))
assert len(executors)==33
candidate={name:sha(path) for name,path in {
    'controller_sha256':PREP/'long_d2.py','executor_sha256':PREP/'long_d2_executor.py',
    'identity_document_sha256':PREP/'long-identity.json','capsule_manifest_sha256':PREP/'capsule-final/capsule-manifest.json',
    'registration_sha256':PREP/'registration.json','protocol_sha256':ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r1-protocol-r3.json',
    'config_sha256':ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r1-config.json'}.items()}
blocked=read(HERE/'final-io-blocked-diagnostic/observed-command.json')
finding=dict(id='SUP-001-R3',severity='P1',blocking=True,
    title='Final forced authority IO begins after all independent outer monitors have stopped',
    line_refs=[dict(path=str((PREP/'long_d2_executor.py').relative_to(ROOT)),start=406,end=417),
               dict(path=str((PREP/'long_d2_executor.py').relative_to(ROOT)),start=198,end=210),
               dict(path=str((PREP/'lifecycle.py').relative_to(ROOT)),start=96,end=105)],
    trigger='An ordinary interruptible IO operation blocks inside the final forced verification after watchdog join, before finite D.',
    consequence='The executor can remain alive past T0+7200 and the entire T0+7210 failure cap; no watchdog remains and the deferred alarm only latches.',
    impact_boundary='A compliant parent rejects the absent/late raw exit and the retained harness-induced -9. No invalid-campaign acceptance is demonstrated.',
    expected='An effective independent deadline owner must cover every potentially blocking normal operation; no normal verification/probe/lease IO may begin after it stops.',
    observations=blocked,evidence=['probe_final_io.py','run_final_io.py','final-io-summary.json','final-io.log',
        'final-io-blocked-diagnostic/final-read-event.json','final-io-blocked-diagnostic/observed-command.json'],
    source_unchanged=True,retried=False,
    probe_limit='Injected os.read at verify_files entry in the owned synthetic fixture; not a claim that a real frozen file blocked.')
write('findings.json',dict(version='frozen_long_D2_supervisor_review_r3',verdict='changes_required',accepted=False,
    candidate=candidate,blocking_findings=1,nonblocking_findings=0,findings=[finding],review='review.md',
    actual_ML_Torch_project_native_import_deserialization_inference_training_gameplay=False,
    production_edits_or_lease_creation=False,children=False,provider_retries=False,
    fresh_outer_OS_executions=33,fresh_positive_acceptances=3,targeted_expected_rejections=29,
    unexpected_retained_failure=1,qualification_checks_stopped_at_first_unexpected_failure=True,
    subsequent_actions='Read-only retained-evidence/input/source audit and review receipt closure only.',
    input_SHA_manifest=dict(path='input-sha256-manifest-expanded.json',files=len(expanded),
        sha256=sha(HERE/'input-sha256-manifest-expanded.json'),final_verification='input-sha256-verification-after.json'),
    owned_registered_groups=len(groups),owned_direct_executors=len(executors),all_registered_groups_and_direct_executors_positively_absent=True,
    retained_matrix_inspected_not_executed=165,retained_unit_methods_not_executed=63,
    aggregate_stdout_loss_disclosed=True,earlier_stdout_recovered=False,
    old_unexplained_R2_raw_minus14_cause='unproven; not identically retried',
    limitations=['No actual ML/API/native/MPS runtime or qualification proof.',
        'Only 29 targeted rejection scenarios were freshly run before the blocker; the retained 165-case matrix is inspected evidence.',
        'No claim of atomic post-scan signal or transient-filesystem observation.',
        'No D3/B/E/student authority or launch recommendation.']))
write('execution-receipt.json',dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    cwd=str(ROOT),environment=dict(PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(HERE/'tmp')),
    commands=[dict(argv=[str(ROOT/'learning/.venv/bin/python'),'-B',str(PREP/'run_checks.py'),str(HERE/'positive-controls'),'--positive-only'],raw_exit=0,log='positive-controls.log'),
              dict(argv=[str(ROOT/'learning/.venv/bin/python'),'-B',str(HERE/'run_targeted.py')],raw_exit=0,log='targeted-controls.log'),
              dict(argv=[str(ROOT/'learning/.venv/bin/python'),'-B',str(HERE/'run_final_io.py')],raw_exit=1,log='final-io.log',result='Intentional contract assertion demonstrating SUP-001-R3; no API/import error'),
              dict(argv=[str(ROOT/'learning/.venv/bin/python'),'-B',str(HERE/'audit_inputs.py')],raw_exit=0,log='input-audit.log',result='Read-only retained-evidence and input audit after blocker')],
    outer_executions=len(executors),registered_groups=len(groups),fresh_unittest_methods=0,
    all_scripts_and_workers_use_B=True,temporary_workers_owned=True,
    actual_ML_execution=False,production_lease=False,external_messages=False,children=False,
    old_unresolved_raw_minus14_retried=False))
for name in ('findings.json','execution-receipt.json','input-sha256-verification-after.json','owned-processes-after.json','final-io-summary.json'):
    subprocess.run([sys.executable,'-B','-m','json.tool',str(HERE/name)],check=True,stdout=subprocess.DEVNULL)
write('delivery-validation.json',dict(required_JSON_CLI_validation_passed=True,input_mismatches=0,
    review_present=(HERE/'review.md').is_file(),findings=1,blocked_diagnostic_retained=True,
    all_owned_registered_groups_and_direct_executors_absent=True))
write('review-artifact-manifest.json',{str(path.relative_to(HERE)):sha(path) for path in sorted(HERE.rglob('*'))
    if path.is_file() and path.name!='review-artifact-manifest.json'})
print(json.dumps(dict(verdict='changes_required',blocking_findings=1,outer_executions=len(executors),registered_groups=len(groups),
    input_files=len(expanded),protected_files=len(protected),all_absent=True,input_mismatches=0)))
