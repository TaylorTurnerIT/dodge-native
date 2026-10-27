"""Parent terminal audit: immutable evidence, evaluation arithmetic and exact lease cleanup."""
from pathlib import Path
import datetime
import hashlib
import json
import math
import os
import subprocess

ROOT = Path(__file__).resolve().parents[3]
ORCH = ROOT / 'learning/runs/v2-orchestration'
OBSERVER = ROOT / 'learning/runs/v2/postovernight-long-D2-execution-observer-r2b'
CAMPAIGN = ROOT / 'learning/runs/v2/postovernight-long-D2-campaign-r2'
PREP = ROOT / 'learning/runs/v2/postovernight-long-D2-boundary-prepare-r14'
OUT = ROOT / 'learning/runs/v2/postovernight-long-D2-r2-parent-audit-r1'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def main():
    OUT.mkdir()
    result = read(OBSERVER / 'execution-result.json')
    worker = read(CAMPAIGN / 'long-worker-result.json')
    lease = read(PREP / 'required-lease.json')
    assert result['actual_command_launch_count'] == 1 and result['raw_exit'] == 1
    assert not result['frozen_accept_observed'] and result['owned_groups_positive_absence']
    assert not (ROOT / 'learning/runs/v2/postovernight-long-D2-execution-r2/integrity-summary.json').exists()
    absence = {}
    for pgid in (10178, 10188, 10203):
        try:
            os.killpg(pgid, 0)
            absence[str(pgid)] = False
        except ProcessLookupError:
            absence[str(pgid)] = True
    try:
        os.kill(10177, 0)
        observer_absent = False
    except ProcessLookupError:
        observer_absent = True
    assert all(absence.values()) and observer_absent, 'Owned work remains; retain lease'
    source_pins = read(OBSERVER / 'sourcehashes-before.json')
    for name, digest in source_pins.items():
        assert sha(Path(name)) == digest, name
    monitor_manifest = read(OBSERVER / 'monitor/manifest.json')
    assert monitor_manifest['stable_after_owned_writer_absence'] and not monitor_manifest['partial']
    for row in monitor_manifest['files']:
        path = Path(row['path'])
        assert sha(path) == row['sha256'] and path.stat().st_size == row['size_bytes'], str(path)
    inventory = read(OBSERVER / 'command-artifact-inventory.json')
    assert inventory['stable_after_owned_absence'] and not inventory['partial']
    artifact_count = 0
    for directory, entries in inventory['artifacts'].items():
        for name, row in entries.items():
            path = Path(directory) / name
            assert sha(path) == row['sha256'] and path.stat().st_size == row['size_bytes'], str(path)
            artifact_count += 1
    evaluations = []
    for path in sorted(CAMPAIGN.glob('*.long-evaluation.json')):
        cert = read(path)
        ev = cert['evaluations']['D2']
        rows = ev['rows']
        assert cert['complete'] and ev['complete'] and len(rows) == ev['episodes'] == 64
        assert not cert['progression_gate_passed'] and not cert['training_parent_eligible'] and not cert['teacher_qualified']
        assert [row['episode_index'] for row in rows] == list(range(64))
        assert [row['seed'] for row in rows] == list(range(3489660928, 3489660992))
        assert sum(row['alive_frames'] for row in rows) / 64 == ev['mean_alive_frames']
        assert sum(row['score_raw_fixed'] for row in rows) / (64 * 65536) == ev['mean_score']
        assert sum(row['terminated'] for row in rows) == ev['deaths']
        assert sum(row['truncated'] for row in rows) == ev['caps']
        assert sum(row['gameplay_frames'] for row in rows) == ev['raw_frames']
        for row in rows:
            assert row['score_raw_fixed'] / 65536 == row['score']
            expected = row['score'] + .01 * row['alive_frames'] - 5 * row['terminated']
            assert math.isclose(row['objective_return'], expected, abs_tol=1e-7)
        checkpoint = CAMPAIGN / path.name.removesuffix('.long-evaluation.json')
        assert sha(checkpoint) == cert['checkpoint_sha256']
        evaluations.append(dict(certificate=path.name, certificate_sha256=sha(path),
                                checkpoint=checkpoint.name, checkpoint_sha256=cert['checkpoint_sha256'],
                                mean_alive_frames=ev['mean_alive_frames'], mean_score=ev['mean_score'],
                                episodes=64, deaths=ev['deaths'], caps=ev['caps'],
                                progression_gate_passed=False, evidence_scope='retained development metrics; outer run failed'))
    assert len(evaluations) == 25
    resources = worker['worker_resources']
    assert resources['latched_failure'] is None and resources['maximum_sample_gap_seconds'] <= .5
    assert max(resources['maximum_rss_bytes'], resources['maximum_mps_driver_bytes']) <= 6442450944
    assert len(worker['integrity_summary']['boundaries']) == 1355
    assert all(row['verdict'] == 'passed' for row in worker['integrity_summary']['boundaries'])
    assert worker['outcome'] == 'budget_closed_below_gate' and worker['expected_exit_code'] == 2
    assert result['command_receipt']['worker_wait']['returncode'] == 2
    assert result['command_receipt']['worker_wait']['direct_child_reaped']
    assert result['command_receipt']['inner_wait']['direct_child_reaped'] and result['outer_wait']['direct_child_reaped']
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report = dict(schema='parent_r2_terminal_audit_v1', at_utc=stamp,
                  status='failed_outer_acceptance;retained_learning_evidence_verified',
                  actual_launches=1, outer_raw_exit=1, observer_shell_exit_is_not_outer_exit=True,
                  outer_wall_seconds=result['observed_wall_seconds'], mandatory_summary_present=False,
                  worker_raw_exit=2, worker_outcome=worker['outcome'], progression_gate_passed=False,
                  evaluations=evaluations, best_completed=max(evaluations, key=lambda x:x['mean_score']),
                  last_completed=evaluations[-1], phase_counters=worker['counters']['phase'],
                  cumulative_counters=worker['counters']['cumulative'], partial_optimizer_steps=worker['counters']['partial_optimizer_steps'],
                  resource_peaks={key:resources[key] for key in
                      ('maximum_rss_bytes','maximum_mps_driver_bytes','maximum_sample_gap_seconds')},
                  worker_integrity_boundaries_passed=1355, source_bindings_rehashed=len(source_pins),
                  monitor_manifest_members_rehashed=len(monitor_manifest['files']), command_artifacts_rehashed=artifact_count,
                  independently_absent_groups=absence, observer_pid_absent=observer_absent,
                  direct_waits=dict(outer=result['outer_wait'],supervisor=result['command_receipt']['inner_wait'],worker=result['command_receipt']['worker_wait']),
                  failure_lineage=dict(observer_error=result['observer_errors'],
                      observer_signal_records=[json.loads(line) for line in (OBSERVER/'signals.jsonl').read_text().splitlines()],
                      outer_first_global_failure=result['command_receipt']['first_global_failure']),
                  limitations=['The changed worker census row was not retained; its exact identity-change cause is unproven.',
                               'Worker completed below gate, but observer cancellation interrupted outer finalization; no acceptance or qualification is granted.',
                               'Best of24 learned development evaluations is selected evidence, not an independent held-out qualification.',
                               'No checkpoint decoded, metadata changed, additional evaluation/training or retry performed.'],
                  single_use_consumed=True, teacher_qualified=False, training_parent_eligible=False,
                  source_receipts_preserved=True)
    save(OUT / 'parent-reconciliation.json', report)
    state = read(ORCH / 'state.json')
    assert state['active_long_campaign'] == lease
    task = state['tasks']['postovernight_long_D2_execution_r2b']
    assert not task['result_ingested']
    task.update(status='completed', workState='result_available', result_ingested=True,
                ingested_at_utc=stamp, actual_command_launch_count=1,
                parent_reconciliation=str((OUT/'parent-reconciliation.json').relative_to(ROOT)),
                experiment_outcome='failed_outer_finalization_after_observer_identity_error')
    run = state['post_overnight_long_D2_r2']
    run.update(status='failed_outer_finalization;parent_audited;lease_cleared;no_retry',
               active_long_campaign=None, campaign_launched=True, single_use_consumed=True,
               terminal_parent_reconciliation=str((OUT/'parent-reconciliation.json').relative_to(ROOT)),
               terminal_parent_reconciliation_sha256=sha(OUT/'parent-reconciliation.json'),
               actual_wall_seconds=result['observed_wall_seconds'], raw_outer_exit=1,
               worker_raw_exit=2, worker_phase_updates=384,
               best_retained_evaluation=report['best_completed'], last_retained_evaluation=report['last_completed'],
               no_automatic_retry_resume_or_followon=True, lease_cleared_at_utc=stamp)
    state.update(active_long_campaign=None, status='postovernight_long_D2_r2_terminal_failed;lease_cleared;no_training_active',
                 last_update_at_utc=stamp,
                 next_actions=['Preserve all failed-run checkpoints and actual metrics; no retry, resume or advancement.',
                               'Read-only diagnosis may assess observer exit handling and next learning hypothesis; proposals only.'])
    pending = ORCH / '.state-r2-terminal.pending.json'
    save(pending, state)
    os.replace(pending, ORCH / 'state.json')
    save(OUT/'lease-clear-receipt.json', dict(at_utc=stamp, exact_prior_lease=lease,
        raw_exit_observed=1, direct_waits_verified=True, all_owned_groups_absent=True,
        observer_absent=True, lease_cleared_by_parent=True, single_use_consumed=True))
    for path in (OUT/'parent-reconciliation.json', OUT/'lease-clear-receipt.json', ORCH/'state.json'):
        completed = subprocess.run(['python3','-m','json.tool',str(path)],stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE,text=True,timeout=10)
        assert completed.returncode == 0, completed.stderr
    save(OUT/'manifest.json', dict(files={str(path.relative_to(OUT)):dict(sha256=sha(path),bytes=path.stat().st_size)
        for path in sorted(OUT.rglob('*')) if path.is_file()}, excludes_itself=True))
    print(json.dumps(dict(status=report['status'], best=report['best_completed'], last=report['last_completed'],
                          source_bindings_rehashed=len(source_pins), artifacts_rehashed=artifact_count, lease_cleared=True)))


if __name__ == '__main__':
    main()
