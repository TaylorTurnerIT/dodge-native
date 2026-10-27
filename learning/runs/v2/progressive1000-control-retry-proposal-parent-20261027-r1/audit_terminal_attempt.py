"""Preserve the failed second attempt and release only its exact parent lease."""
import datetime
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SUPERVISOR = ROOT / 'learning/runs/v2/progressive1000-ps-timeout-repair-sol-20261027-r6'
sys.path.insert(0, str(SUPERVISOR))
import binding as b
import terminal


def main():
    reg_path = HERE / 'registration-final-candidate.json'
    reg = b.read(reg_path)
    execution = b.read(HERE / 'parent-execution.json')
    exit_receipt = b.read(HERE / 'execution-exit.json')
    envelope = b.read(HERE / 'launch-envelope.json')
    control = Path(envelope['control'])
    observation = b.read(control / 'observation.json')
    b.need(exit_receipt['observer_directly_reaped'] and observation['directly_reaped'], 'direct reaping not established')
    b.need(b.sha(reg_path) == execution['registration_sha256'] == observation['registration_sha256'], 'registration drift')
    b.need(b.sha(HERE / 'launch-envelope.json') == execution['envelope_sha256'], 'envelope drift')
    # Preserve and independently verify both groups, including observer cleanup.
    process_table = subprocess.run(['/bin/ps', '-axo', 'pid=,ppid=,pgid=,command='], check=True, capture_output=True, text=True).stdout
    parsed = [line.split(None, 3) for line in process_table.splitlines() if line.strip()]
    groups = []
    for role, pgid in [('worker', observation['owned_pgid']), ('observer', execution['observer_pgid'])]:
        matches = [line for line in parsed if int(line[2]) == pgid]
        b.need(not matches, role + ' process group remains')
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            pass
        else:
            raise ValueError(role + ' process group absence unproven')
        groups.append(dict(role=role, pgid=pgid, absent=True))
    b.verify_bound(envelope, reg, preflight=False)
    out = Path(reg['output'])
    metrics = list(terminal.rows(out / 'training-metrics.jsonl', strict=True))
    b.need([row['global_update'] for row in metrics] == list(range(1, 45)), 'completed prefix differs')
    b.need(all(row['metrics']['finite'] for row in metrics), 'nonfinite completed metrics')
    checkpoints = []
    for local in (12, 24, 36):
        path = out / f'checkpoint-global-{local:03d}-integrity.pt'
        sidecar = b.read(str(path) + '.json')
        b.need(b.sha(path) == sidecar['sha256'] and sidecar['global_update'] == local, 'partial checkpoint drift')
        checkpoints.append(dict(path=str(path), sha256=sidecar['sha256'], global_update=local, accepted_for_comparison=False))
    b.need(not (out / 'checkpoint-global-060-integrity.pt').exists(), 'unexpected terminal endpoint')
    resources = b.worker_resources(out, strict=True)
    b.need(resources['peak_rss_bytes'] <= reg['limits']['rss_bytes'] and resources['peak_mps_driver_bytes'] <= reg['limits']['mps_bytes'], 'resource cap exceeded')
    accounting = terminal.accounting(out, {})
    elapsed = [row['elapsed_seconds'] for row in metrics]
    durations = [right-left for left, right in zip([0] + elapsed, elapsed)]
    timing = dict(completed_updates=44, last_completed_elapsed_seconds=elapsed[-1],
        seconds_per_update_mean=statistics.mean(durations), seconds_per_update_max=max(durations),
        first12_seconds=elapsed[11], last12_seconds=elapsed[-1]-elapsed[-13],
        linear_projection_60_seconds=elapsed[-1]*60/44,
        scope='Descriptive timings only. Cause of throughput variation not established.')
    b.save(HERE / 'timing-diagnostic.json', timing)
    audit = dict(schema='parent_progressive1000_partial_campaign_terminal_audit_v1',
        at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        status='failed_registered_work_deadline_partial_preserved_no_retry',
        run_id=reg['run_id'], registration_sha256=b.sha(reg_path), attempt_number=2,
        envelope_sha256=execution['envelope_sha256'], raw_observer_exit_code=exit_receipt['raw_observer_exit_code'],
        raw_worker_exit_code=observation['observed_worker_raw_exit'], completed_updates=44,
        completed_counters=metrics[-1]['counters'], elapsed_seconds=exit_receipt['elapsed_seconds'],
        first_failure=observation['first_observed_failure'], directly_reaped=True,
        independent_process_groups=groups, immutable_inputs_dependencies_and_cache_postflight_pass=True,
        marker_and_transition_claim_preserved=True, partial_checkpoints=checkpoints,
        embedded_partial_checkpoints_deserialized=False, checkpoint_acceptance='none; partial hashes establish preservation only',
        resource_samples=resources, all_completed_metrics_finite=True,
        comparison_endpoint_complete=False, formal_evaluation_run=False, promoted=False,
        training_eligible=False, automatic_selection=False,
        cleanup_errors_preserved=observation['cleanup']['errors'],
        evidence_limits=['No worker final snapshot. Partial PPO work after update44 remains unknown.',
            'Update45 collection returned, but no completed PPO boundary was published.',
            'Cleanup recorded PermissionError on escalation. Both groups independently verified absent.',
            'No terminal60 endpoint or performance comparison. No cause assigned to runtime slowdown.'])
    b.save(HERE / 'parent-terminal-audit.json', audit)
    file_hashes = {str(path.relative_to(HERE)): b.sha(path) for path in out.iterdir() if path.is_file()}
    compact = dict(schema='parent_progressive1000_compact_campaign_receipt_v1', run_id=reg['run_id'],
        scope='Source and compact evidence. Checkpoint bytes remain local. No accepted comparison endpoint.',
        terminal_audit=audit, raw_execution_exit=exit_receipt, raw_observation=observation,
        raw_observer_finalization=b.read(control / 'observer-finalization.json'),
        worker_launch=b.read(control / 'worker-launch.json'),
        entry_restoration=b.read(out / 'entry-restoration.json'), completed_training_metrics=metrics,
        partial_checkpoint_sidecars=[b.read(row['path'] + '.json') for row in checkpoints],
        resource_samples=list(terminal.rows(out / 'resources.jsonl', strict=True)),
        terminal_accounting=accounting, timing=timing, source_files=file_hashes)
    b.save(HERE / 'compact-campaign-receipt.json', compact)
    # Terminal audit is durably published before the exact matching lease clears.
    state = b.read(reg['state_path'])
    b.need(state['active_long_campaign'] == reg['expected_lease'], 'refusing to clear another lease')
    state['active_long_campaign'] = None
    work = state['progressive1000_curriculum_work']
    work.update(active_registered_run=None, current_launch_authorized=False,
        actual_training_launches=2, retry_requires_explicit_user_authorization=True,
        latest_attempt_completed_updates=44, latest_attempt_terminal_audit=str(HERE / 'parent-terminal-audit.json'),
        latest_attempt_failure='external_work_deadline_at1790seconds',
        remaining_registered_runs_launched=0,
        status='attempt2_deadline_failure_preserved; remaining5held_for_wall_budget_disposition')
    state['last_update_at_utc'] = audit['at_utc']
    staging = Path(reg['state_path']).with_name('state.retry-terminal.pending.json')
    b.save(staging, state)
    os.replace(staging, reg['state_path'])
    descriptor = os.open(Path(reg['state_path']).parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    b.save(HERE / 'lease-release.json', dict(status='exact_matching_lease_cleared_after_terminal_audit',
        registration_sha256=b.sha(reg_path), terminal_audit_sha256=b.sha(HERE / 'parent-terminal-audit.json')))
    print(json.dumps(dict(status=audit['status'], completed_updates=44, lease_cleared=True, timing=timing)))


if __name__ == '__main__':
    main()
