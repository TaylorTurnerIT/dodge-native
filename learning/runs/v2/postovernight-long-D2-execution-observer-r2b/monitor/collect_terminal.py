"""Collect existing terminal evidence with stdlib only; write exclusively here."""
import collections
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
OBSERVER = OUT.parent
CAMPAIGN = OBSERVER.with_name('postovernight-long-D2-campaign-r2')
EXECUTION = OBSERVER.with_name('postovernight-long-D2-execution-r2')
ROOT = OBSERVER.parents[3]


def read(path):
    return json.loads(path.read_text())


def rows(path):
    if path.is_file():
        with path.open() as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def save(name, value):
    with (OUT / name).open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


result = read(OBSERVER / 'execution-result.json')
absence = read(OBSERVER / 'postflight-owned-absence.json')
assert set(absence) == {'outer', 'supervisor', 'worker'}
assert all(item['group_absent'] for item in absence.values())
groups = {item['pgid'] for item in absence.values()}
identities = groups | {result['observer_pid']}
census = subprocess.run(['ps', '-axo', 'pid=,ppid=,pgid=,lstart=,rss=,args='],
    capture_output=True, text=True, timeout=5, check=True)
matches = []
for line in census.stdout.splitlines():
    fields = line.split(None, 9)
    if len(fields) == 10 and (int(fields[0]) in identities or int(fields[2]) in groups):
        matches.append(line)
assert not matches, 'Required writers are still present; no stable collection permitted'
save('terminal-process-census.json', dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    command=['ps', '-axo', 'pid=,ppid=,pgid=,lstart=,rss=,args='],
    recorded_pids=sorted(identities), recorded_pgids=sorted(groups), matches=matches,
    observation_only=True, absence_is_not_a_direct_wait=True))

worker = read(CAMPAIGN / 'long-worker-result.json')
inner = read(CAMPAIGN / 'inner-failure.json')
receipt = read(EXECUTION / 'acceptance-receipt.json')
index = read(CAMPAIGN / 'checkpoint-index.json')
indexed = {item['checkpoint']: item for item in index}
evaluations = []
for path in sorted(CAMPAIGN.glob('*.long-evaluation.json')):
    certificate = read(path)
    if not certificate.get('complete'):
        continue
    checkpoint = path.name.removesuffix('.long-evaluation.json')
    checkpoint_path = CAMPAIGN / checkpoint
    actual_sha = sha(checkpoint_path)
    assert actual_sha == certificate['checkpoint_sha256']
    entry = indexed[checkpoint]
    assert actual_sha == entry['sha256']
    for stage, value in certificate['evaluations'].items():
        if value.get('complete'):
            evaluations.append(dict(certificate=str(path), certificate_sha256=sha(path),
                checkpoint=checkpoint, checkpoint_sha256=actual_sha, stage=stage,
                phase_updates=entry['counters']['phase']['updates'],
                actual_Adam_parameter_step_values=entry.get('actual_Adam_parameter_step_values'),
                initial_entry_control=entry['counters']['phase']['updates'] == 0,
                progression_gate_passed=certificate['progression_gate_passed'],
                **{key: value[key] for key in ('mean_score', 'mean_alive_frames',
                    'episodes', 'deaths', 'caps', 'raw_frames', 'elapsed_seconds', 'action_mode')}))
learned = [item for item in evaluations if not item['initial_entry_control']]
last = max(learned, key=lambda item: item['phase_updates'])
best_score = max(learned, key=lambda item: (item['mean_score'], item['mean_alive_frames']))
best_alive = max(learned, key=lambda item: (item['mean_alive_frames'], item['mean_score']))

resource = dict(samples=0, maximum_rss_bytes=0, maximum_mps_driver_bytes=0,
    maximum_sample_gap_seconds=0, maximum_self_peak_rss_bytes=0)
for item in rows(CAMPAIGN / 'worker-resources.jsonl'):
    resource['samples'] += 1
    for source, target in (('rss_bytes', 'maximum_rss_bytes'),
        ('mps_driver_bytes', 'maximum_mps_driver_bytes'),
        ('sample_gap_seconds', 'maximum_sample_gap_seconds'),
        ('self_peak_rss_bytes', 'maximum_self_peak_rss_bytes')):
        resource[target] = max(resource[target], item.get(source, 0))
role_rss = collections.defaultdict(int)
aggregate_rss = 0
observations = 0
for sample in rows(OBSERVER / 'process-observations.jsonl'):
    observations += 1
    sums = collections.defaultdict(int)
    for process in sample['owned']:
        sums[process['role']] += process['rss_bytes']
    for role, value in sums.items():
        role_rss[role] = max(role_rss[role], value)
    aggregate_rss = max(aggregate_rss, sum(sums.values()))
current = read(OBSERVER / 'current-input-hashes.json')
signals = list(rows(OBSERVER / 'signals.jsonl'))
errors = list(rows(OBSERVER / 'observer-errors.jsonl'))
summary_path = EXECUTION / 'integrity-summary.json'
missing = [str(path) for path in (summary_path, CAMPAIGN / 'long-run-result.json',
    CAMPAIGN / 'finalization-result.json') if not path.exists()]
worker_summary = {key: worker.get(key) for key in ('experiment_status', 'outcome',
    'expected_exit_code', 'progression_gate_passed', 'teacher_qualified',
    'training_parent_eligible', 'worker_wall_seconds_lower_bound',
    'worker_result_write_and_process_exit_not_timed', 'counters', 'final_checkpoint', 'schedule')}
worker_summary['worker_resources'] = {key: value for key, value in worker['worker_resources'].items()
    if key != 'boundary_verdicts'}
worker_summary['integrity_summary'] = {key: worker['integrity_summary'].get(key)
    for key in ('schema', 'boundary_count', 'first_global_failure', 'first_local_failure')}
evidence = dict(schema='r2b_monitor_terminal_evidence_v1',
    collected_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    authorization='Monitor existing one-shot only; no launches, signals, ML imports or checkpoint decoding by monitor.',
    actual_command_launch_count=result['actual_command_launch_count'],
    parent_tool_session_unavailable='write_stdin failed: Unknown process id 66682',
    observer_pid=result['observer_pid'], original_outer_pid=10178,
    observed_raw_exit=result['raw_exit'], raw_wait_status=result['raw_wait_status'],
    observed_wall_seconds=result['observed_wall_seconds'], raw_wait=read(OBSERVER / 'raw-wait.json'),
    worker=worker_summary, evaluations=evaluations, completed_certificate_count=len(evaluations),
    learned_evaluation_count=len(learned), last_completed_learned=last,
    best_completed_learned_score=best_score, best_completed_learned_alive=best_alive,
    resources=dict(worker_log=resource, worker_terminal_summary=worker_summary['worker_resources'],
        observer_process_samples=observations, observer_maximum_group_rss_bytes=dict(role_rss),
        observer_maximum_aggregate_group_rss_bytes=aggregate_rss,
        independent_cap_bytes=6442450944, maximum_allowed_sample_gap_seconds=.5,
        limitation='Observed samples are bounded evidence, not continuous OS/memory attestation.'),
    failure_lineage=dict(primary_observer_error=errors[0] if errors else None,
        observer_errors=errors, observer_forwarded_signals=signals,
        outer_receipt_primary_failure=receipt.get('first_global_failure'),
        inner_primary_failure=inner.get('first_global_failure'),
        cleanup_errors=receipt.get('cleanup_errors'),
        worker_outcome=worker.get('outcome'),
        note='Worker retained complete budget_closed_below_gate with expected/raw exit 2. Observer identity error precedes its SIGTERM; outer cancellation and subsequent IPC loss are separately retained. The exact changed worker census row is not retained, so its cause is unproven.'),
    direct_waits=dict(outer=result['outer_wait'], supervisor=receipt.get('inner_wait'),
        worker=receipt.get('worker_wait'), reaping=receipt.get('reaping'),
        monitor_is_not_direct_parent=True, observer_wait_unavailable_to_monitor=True),
    owned_absence=absence, current_source_rechecks=dict(count=len(current['current']),
        mismatches=current['mismatches'], observer_sha256=sha(OBSERVER / 'execute_once.py')),
    entry_restoration=read(CAMPAIGN / 'entry-restoration.json'),
    entry_control=read(CAMPAIGN / 'entry-control.json'),
    acceptance=dict(frozen_accept_observed=result['frozen_accept_observed'],
        receipt_accepted=receipt.get('accepted'), experiment_status=receipt.get('experiment_status'),
        mandatory_integrity_summary_present=summary_path.exists(),
        mandatory_integrity_summary_sha256=result['mandatory_integrity_summary_sha256'],
        owned_groups_positive_absence=result['owned_groups_positive_absence'],
        cleanup_complete=receipt.get('cleanup_complete'), recovery_proven=receipt.get('recovery_proven'),
        missing_paths=missing, teacher_qualified=False, training_parent_eligible=False,
        lease_retained_by_observer=result['lease_retained'], lease_clearing_owner='parent',
        followon_authorized=False),
    limitations=receipt.get('limitations', []) + [
        'Worker exit 2 is budget closed below gate, not score/survival success.',
        'No successful outer mandatory integrity summary or accepted supervisor terminal result exists.',
        'No parent-death scenario was exercised; direct-wait reports cover this actual parent chain only.',
        'No extra evaluation, teacher/D3/student qualification or follow-on execution is authorized.'])
save('terminal-evidence.json', evidence)
report = f'''The single launched command failed outer acceptance: raw exit {result['raw_exit']}, raw wait status {result['raw_wait_status']}, direct-parent observed wall {result['observed_wall_seconds']} seconds. Frozen accept_observed is false; the mandatory execution integrity-summary.json is absent. The lease remains retained for the parent.

The worker retained budget_closed_below_gate and was directly reaped with exit 2 after 384 D2 updates. The observer recorded RuntimeError('Owned identity changed: worker') at monotonic 532106.958840125, then sent SIGTERM to the exact outer at 532107.009341416. Outer cancellation and later private IPC loss remain failure/cleanup evidence. The changed worker census row was not retained; its cause is unproven.

There are {len(evaluations)} completed D2 certificates: one initial entry control and {len(learned)} learned evaluations. Last learned score/alive frames: {last['mean_score']} / {last['mean_alive_frames']}; best score and best alive frames: {best_score['mean_score']} / {best_alive['mean_alive_frames']}. Each reported point includes episodes/deaths/caps and checkpoint hashes in terminal-evidence.json. No completed progression gate passed.

D2 counters: {worker['counters']['phase']['updates']} updates, {worker['counters']['phase']['optimizer_steps']} optimizer steps, {worker['counters']['phase']['raw_frames']} raw frames. Cumulative counters: {worker['counters']['cumulative']['updates']} updates, {worker['counters']['cumulative']['optimizer_steps']} optimizer steps, {worker['counters']['cumulative']['raw_frames']} raw frames; final Adam parameter step values {worker['final_checkpoint']['actual_Adam_parameter_step_values']}. Resource log peaks: RSS {resource['maximum_rss_bytes']} bytes, MPS driver {resource['maximum_mps_driver_bytes']} bytes, sample gap {resource['maximum_sample_gap_seconds']} seconds.

Outer, supervisor and worker have retained direct-parent wait reports and positive group absence. A fresh census found all three groups and observer PID absent. Current input rechecks report {len(current['mismatches'])} mismatches across {len(current['current'])} bindings. Stable file hashes follow writer absence; they do not confer acceptance. Teacher and training parent remain unqualified; no follow-on was launched. Detailed evidence, JSON validation and the acyclic manifest are retained here.
'''
with (OUT / 'terminal-report.md').open('x') as stream:
    stream.write(report)

# Validation outputs do not refer to their own hash; manifest is written last.
validation = dict(schema='monitor_json_validation_v1', json=[], jsonl=[], errors=[])
paths = sorted(set(OBSERVER.glob('*.json')) | set(CAMPAIGN.glob('*.json')) |
    set(EXECUTION.glob('*.json')) | set(OUT.glob('*.json')))
for path in paths:
    check = subprocess.run([sys.executable, '-B', '-m', 'json.tool', str(path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=30)
    validation['json'].append(dict(path=str(path), exit_code=check.returncode))
    if check.returncode:
        validation['errors'].append(dict(path=str(path), error=check.stderr))
for path in (OUT / 'live-observations.jsonl', CAMPAIGN / 'worker-resources.jsonl',
    CAMPAIGN / 'training-metrics.jsonl', OBSERVER / 'process-observations.jsonl',
    OBSERVER / 'signals.jsonl', OBSERVER / 'observer-errors.jsonl'):
    count = sum(1 for _ in rows(path))
    validation['jsonl'].append(dict(path=str(path), rows=count, parsed=True))
validation['passed'] = not validation['errors']
save('json-validation.json', validation)
assert validation['passed']
inventory = []
for directory in (OBSERVER, CAMPAIGN, EXECUTION):
    for path in sorted(directory.rglob('*')):
        if path.is_file() and not path.is_symlink() and path != OUT / 'manifest.json':
            inventory.append(dict(path=str(path), size_bytes=path.stat().st_size, sha256=sha(path)))
save('manifest.json', dict(schema='monitor_terminal_acyclic_manifest_v1',
    stable_after_owned_writer_absence=True, partial=False,
    excludes=['manifest.json'], no_self_hash=True,
    direction='manifest -> files; terminal evidence -> retained source evidence; no source file references this monitor manifest',
    files=inventory))
print(json.dumps(dict(raw_exit=result['raw_exit'], wall=result['observed_wall_seconds'],
    last=last, best_score=best_score, best_alive=best_alive, resources=resource,
    worker_schedule=worker['schedule'], validated_json=len(validation['json']),
    manifest_files=len(inventory), report=str(OUT / 'terminal-report.md')), sort_keys=True))
