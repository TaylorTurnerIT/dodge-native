"""Parent glue for the explicitly authorized second attempt; never retries."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SUPERVISOR = ROOT / 'learning/runs/v2/progressive1000-ps-timeout-repair-sol-20261027-r6'
sys.path.insert(0, str(SUPERVISOR))
import binding as b


def update_ledger(state):
    path = ROOT / 'learning/runs/v2-orchestration/state.json'
    staging = path.with_name('state.retry-authorized.pending.json')
    b.save(staging, state)
    os.replace(staging, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main():
    registration = HERE / 'registration-final-candidate.json'
    digest = '779c83406dc95e8e142f4bd79d6ed91a4eb8f8e2add6beb635d26c1f1a6333ec'
    b.need(b.sha(registration) == digest, 'candidate registration changed')
    reg = b.read(registration)
    accepted = b.read(HERE / 'source-review-acceptance.json')
    b.need(b.sha(SUPERVISOR / 'source-manifest.json') == accepted['source_manifest_sha256'], 'supervisor drift')
    for relative, expected in b.read(SUPERVISOR / 'source-manifest.json')['files'].items():
        b.need(b.sha(SUPERVISOR / relative) == expected, 'supervisor member drift: ' + relative)
    for field in ('parent_replay', 'review_receipt'):
        b.need(b.sha(accepted[field + '_path']) == accepted[field + '_sha256'], field + ' drift')
    state = b.read(reg['state_path'])
    b.need(state['active_long_campaign'] is None and state['active_inference_diagnostic'] is None, 'conflicting lease')
    for path in (reg['output'], reg['attempt_claim_path'], reg['launch_marker_path'], SUPERVISOR / 'dispatch' / reg['run_id']):
        b.need(not os.path.lexists(path), 'fresh attempt already spent: ' + str(path))
    proposal = b.read(HERE / 'proposal.json')
    original = b.read(proposal['original_registration'])
    for field in proposal['unchanged_learning_fields']:
        b.need(reg[field] == original[field], 'learning field changed: ' + field)
    prior_audit = b.read(proposal['original_terminal_audit'])
    b.need(prior_audit['completed_updates'] == 41 and prior_audit['immutable_inputs_dependencies_and_cache_postflight_pass'], 'prior audit differs')
    b.need(all(group['absent'] for group in prior_audit['independent_process_groups']), 'prior cleanup not established')
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    b.save(HERE / 'user-retry-authorization.json', dict(
        schema='parent_explicit_fresh_attempt_authorization_v1', at_utc=now,
        user_messages=['Resume', 'In other words, yes'],
        scope='Exactly one fresh control attempt from checkpoint324, same seeds,60updates,unchanged caps',
        registration_sha256=digest, original_attempt_preserved=True, automatic_retry=False))
    state['active_long_campaign'] = reg['expected_lease']
    work = state['progressive1000_curriculum_work']
    work.update(active_registered_run=str(registration), active_registered_run_sha256=digest,
                current_launch_authorized=True, retry_requires_explicit_user_authorization=False,
                retry_authorization=str(HERE / 'user-retry-authorization.json'),
                status='authorized_fresh_control_attempt2_preflight',
                supervisor_latest_source=str(SUPERVISOR),
                supervisor_latest_source_manifest_sha256=accepted['source_manifest_sha256'])
    state['last_update_at_utc'] = now
    update_ledger(state)
    c = b.contracts()
    c.validate_static(reg)
    c.cache_check(reg)
    dependency = b.verify_dependencies(reg)
    approval = dict(schema='progressive1000_parent_launch_approval_v1',
        status='approved_exactly_one_registered_run', registration_sha256=digest,
        source_manifest_sha256=reg['source_manifest_sha256'],
        runtime_manifest_sha256=reg['runtime_manifest_sha256'], run_id=reg['run_id'],
        gates=dict.fromkeys(c.GATES, 'passed'))
    approval_path = HERE / 'launch-approval.json'
    b.save(approval_path, approval)
    envelope = b.read(SUPERVISOR / 'templates' / (reg['run_id'] + '.envelope.json'))
    envelope.update(status='parent_bound_exactly_one_run', registration=str(registration),
        registration_sha256=digest, launch_approval=str(approval_path),
        launch_approval_sha256=b.sha(approval_path),
        control=str(SUPERVISOR / 'dispatch' / reg['run_id']), cancel_path=str(HERE / 'cancel'))
    b.check_pins(envelope)
    b.check_lease(reg)
    b.save(HERE / 'parent-preflight.json', dict(schema='parent_retry_preflight_v1',
        registration_sha256=digest, static_registration='passed', cache='passed', dependencies=dependency,
        prior_restore_and_resource_evidence=proposal['original_terminal_audit'],
        gate_scope=str(ROOT / 'learning/runs/v2/progressive1000-matched-run-parent-assembly-20261026-r1/prelaunch-evidence-scope.json'),
        supervisor_acceptance=str(HERE / 'source-review-acceptance.json'), marker_unspent=True))
    started = time.monotonic()
    envelope['started'] = started
    envelope_path = HERE / 'launch-envelope.json'
    b.save(envelope_path, envelope)
    envelope_sha = b.sha(envelope_path)
    b.load_envelope(envelope_path, envelope_sha)
    b.save(reg['launch_marker_path'], dict(schema='progressive1000_parent_spent_launch_marker_v1',
        registration_sha256=digest, run_id=reg['run_id'], started=started))
    # From marker publication through terminal parent audit, do not write ledger.
    command = [reg['interpreter'], '-B', str(SUPERVISOR / 'observe.py'),
               '--envelope', str(envelope_path), '--envelope-sha256', envelope_sha]
    with (HERE / 'observer.log').open('xb') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        b.save(HERE / 'parent-execution.json', dict(command=command, observer_pid=process.pid,
            observer_pgid=process.pid, registration_sha256=digest, envelope_sha256=envelope_sha, started=started))
        print(json.dumps(dict(status='launched_exactly_once', observer_pid=process.pid, registration_sha256=digest)), flush=True)
        result = process.wait()
    b.save(HERE / 'execution-exit.json', dict(raw_observer_exit_code=result,
        elapsed_seconds=time.monotonic()-started, observer_directly_reaped=True,
        registration_sha256=digest, envelope_sha256=envelope_sha, parent_terminal_audit_pending=True))
    print(json.dumps(dict(status='observer_terminal_parent_audit_pending', raw_exit=result)), flush=True)
    return 0 if result == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
