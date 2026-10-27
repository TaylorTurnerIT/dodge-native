"""Publish retained setup-read failure only; never prepare or test a candidate."""
from pathlib import Path
import datetime
import hashlib
import json
import subprocess
import sys
import time

H = Path(__file__).resolve().parent
ROOT = H.parents[3]
AUTH = ROOT / 'learning/runs/v2-orchestration'
BASE = H.with_name('postovernight-long-D2-boundary-prepare-r12')
START = time.monotonic()

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def now():
    return datetime.datetime.now(datetime.timezone.utc)

def save(name, value):
    with (H / name).open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')

launch = AUTH / 'postovernight-long-D2-boundary-repair-r13-launch.json'
origin = datetime.datetime.fromtimestamp(launch.stat().st_mtime, datetime.timezone.utc)
error = 'cat: learning/runs/v2/postovernight-long-D2-switchinterval-probe-r1/wrapper_once.py: No such file or directory'
(H / 'setup-read-stderr.log').write_text(error + '\n')
save('setup-failure.json', dict(
    schema='r13_setup_read_failure_v1', status='stopped_before_candidate_preparation',
    failed_path='learning/runs/v2/postovernight-long-D2-switchinterval-probe-r1/wrapper_once.py',
    raw_error=error, failure_kind='agent_requested_unverified_input_filename',
    observed_shell_exit=0,
    shell_exit_qualification='The combined inspection command continued after cat and its final command returned zero. The cat error was visible and triggers stop; the individual cat exit was not separately captured.',
    no_failure_retry=True, no_postfailure_candidate_patch=True,
    followup_read_error='ls: learning/runs/v2/postovernight-long-D2-boundary-prepare-r13: No such file or directory',
    followup_read_qualification='Evidence-only directory-presence check after stop; no candidate or stage existed.',
    instruction='Stop first unexpected setup/test failure; preserve partial evidence; no patch or retry.',
    failure_observed_by_utc='2026-10-25T04:17:47+00:00'))
paths = [AUTH / name for name in (
    'postovernight-long-D2-boundary-repair-r13-task.md',
    'postovernight-long-D2-boundary-repair-r12-task.md',
    'postovernight-long-D2-r12-parent-reconciliation.json',
    'postovernight-long-D2-boundary-policy-parent-reconciliation-r1.json',
    'postovernight-long-D2-boundary-review-r11-parent-reconciliation.json',
    'postovernight-long-D2-contention-design-sonnet-r1-parent-reconciliation.json',
    'postovernight-long-D2-boundary-repair-r13-launch.json')]
paths += [ROOT/'docs'/name for name in ('implementation-plan-v2.md','SPEC_PRIVILEGED_VIT_RL.md')]
paths += [BASE/name for name in ('prepare_r12.py','PARENT-NEXT.md','run_unit_suite.py','unit_stage.py',
    'source_equality.py','long_d2.py','test_r12.py','test_r11.py','test_r10.py','test_r7.py',
    'implementation-result.json','completion-receipt.json')]
paths += [BASE.with_name('postovernight-long-D2-r12-chronology-proof-r1')/name
    for name in ('proof_once.py','result.json')]
paths += [BASE.with_name('postovernight-long-D2-contention-design-sonnet-r1')/name
    for name in ('diagnosis.md','plan.json','receipt.json')]
paths += [BASE.with_name('postovernight-long-D2-switchinterval-probe-r1')/name
    for name in ('plan.json','probe_once.py')]
paths += [BASE.with_name('postovernight-long-D2-boundary-prepare-r11')/'parent-frozen-pins.json',
    BASE.with_name('postovernight-long-D2-boundary-review-r11')/'audit.md']
save('input-manifest.json', dict(schema='r13_partial_read_input_manifest_v1',
    files={str(p.relative_to(ROOT)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in paths},
    completeness='Partial inspected inputs only. Some combined tool output was truncated. Required full authority/source reads and 229/215/514 binding verification did not complete before stop.',
    bindings_verified_against_registered_digests=False, mutable_ledger_not_snapshotted=True))
(H/'candidate.diff').write_bytes(b'')
save('source-manifest.json', dict(schema='r13_absent_candidate_source_manifest_v1', files={},
    candidate_created=False, frozen_source_bytes=0, no_r12_source_copy=True,
    note='No production, test, helper or protocol candidate was created. Empty diff means no candidate patch, not a validated candidate.'))
save('base-source-manifest.json', dict(schema='r13_uncreated_base_snapshot_v1', files={},
    exact_snapshot_created=False, required_base_bindings_verified=False))
save('test-receipt.json', dict(schema='r13_stage_not_invoked_v1',
    invocations=0, registered=False, tests_run=0, inherited_methods_executed=0,
    inherited_methods_unrun=112, new_tests_written=0, raw_exit=None,
    elapsed_seconds=None, stage_budget_seconds=300, retry=False,
    note='No test command exists. No historical result transfers.'))
(H/'PARENT-NEXT.md').write_text('''# r13 stopped during setup inspection

No r13 candidate was prepared. An inspection command requested an unverified filename, `learning/runs/v2/postovernight-long-D2-switchinterval-probe-r1/wrapper_once.py`. `cat` reported `No such file or directory`. The task requires stopping on the first unexpected setup/test failure, so implementation stopped without repairing that read, copying sources, writing candidate tests, or invoking a stage. The combined shell command eventually returned zero; that does not erase the visible cat failure. A later evidence-only directory-presence check also reported the not-yet-created r13 directory absent.

This directory contains failure publication only. No current controller, protocol-r10 proposal, source-equality verdict, base snapshot, frozen candidate, registration, or current test pass exists. The empty candidate.diff records no patch; it does not establish candidate correctness. Required 229 source / 215 input / 514 evidence revalidation was not completed. Earlier source reads included truncated tool output; full-source review was not completed.

No r12 or historical evidence was edited or rerun. No external protocol, runtime, freeze, OS, stress, startup, ML, training, lease, ledger, project, docs, scheduler, commit, PR, provider call, nested delegation, or message action occurred. Writes stayed in this new r13 directory. The sole 7200-second training authorization remains unused and parent-held.

Parent must reconcile this setup failure and authorize any distinct continuation. Do not count this handoff as the requested implementation. Source ownership is released; the failure artifacts are frozen at handoff. No candidate patch or test retry followed the failure.

Elapsed time uses the observed r13 launch-file modification timestamp through final publication. Exact agent-entry time was not independently recorded; this launch-to-publication interval includes launch/startup overhead and is explicitly identified in the completion receipt.
''')
result = dict(schema='r13_implementation_result_v1', status='stopped_setup_read_failure_no_candidate',
    intended_work_complete=False, setup_failure='setup-failure.json',
    candidate_created=False, candidate_patch=False, tests_invoked=0,
    proposed_protocol_created=False, production_freeze=False, training_launched=False,
    held_training_authorization_seconds=7200, source_ownership='released_no_candidate',
    scope_deviations=['Incorrect unverified filename requested during setup read; stopped without retry.',
                      'Requested implementation and mandatory input verification remain incomplete.'],
    immutable_historical_files_modified=False, no_runtime_or_training_acceptance=True,
    elapsed_origin_utc=origin.isoformat(), elapsed_origin_kind='observed_r13_launch_file_mtime',
    agent_entry_timestamp_recorded=False, publication_at_utc=now().isoformat(),
    elapsed_launch_to_result_seconds=(now()-origin).total_seconds(), budget_seconds=1800)
save('implementation-result.json', result)
# Validate evidence JSON using the required stdlib command; no candidate imports.
validation = []
for path in sorted(H.glob('*.json')):
    run = subprocess.run([sys.executable, '-B', '-m', 'json.tool', str(path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=30)
    validation.append(dict(path=path.name, raw_exit=run.returncode, stderr=run.stderr))
    if run.returncode:
        save('json-validation-failure.json', dict(results=validation, no_retry=True))
        raise SystemExit(run.returncode)
save('json-validation.json', dict(results=validation, all_passed=True,
    scope='Evidence JSON validation only; not the unused stdlib candidate stage.'))
files = {str(p.relative_to(H)):dict(sha256=sha(p),bytes=p.stat().st_size)
         for p in sorted(H.rglob('*')) if p.is_file()}
save('evidence-manifest.json', dict(schema='r13_failure_evidence_manifest_v1', files=files,
    exclusions=['evidence-manifest.json','completion-receipt.json'],
    acyclic=True, source_ownership_released=True))
finish = now()
save('completion-receipt.json', dict(schema='r13_failed_setup_completion_v1',
    status='stopped_setup_read_failure_no_candidate',
    evidence_manifest_sha256=sha(H/'evidence-manifest.json'),
    implementation_result_sha256=sha(H/'implementation-result.json'),
    publication_elapsed_monotonic_seconds=time.monotonic()-START,
    elapsed_launch_to_completion_seconds=(finish-origin).total_seconds(),
    elapsed_origin_utc=origin.isoformat(), elapsed_origin_kind='observed_r13_launch_file_mtime',
    exact_agent_entry_elapsed_unavailable=True, completed_at_utc=finish.isoformat(),
    in_budget=(finish-origin).total_seconds() <= 1800, budget_seconds=1800,
    validation_invocations=0, raw_test_exit=None, source_ownership_released=True,
    no_candidate_patch_or_test_retry=True, training_launched=False))
print(json.dumps(dict(status=result['status'], elapsed_launch_to_completion_seconds=(finish-origin).total_seconds(),
    tests_invoked=0, candidate_created=False, evidence_files=len(files)), sort_keys=True))
