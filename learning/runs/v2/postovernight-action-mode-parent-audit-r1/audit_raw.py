"""Retained-data audit only. NumPy bootstrap; no Torch/native/model/gameplay."""
import collections
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import time

import numpy as np

ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
HERE = Path(__file__).resolve().parent
OUTER = ROOT / 'learning/runs/v2/postovernight-action-mode-execution-r1'
CAMP = ROOT / 'learning/runs/v2/postovernight-action-mode-campaign-r1'
PROTO = ROOT / 'learning/runs/v2-orchestration/postovernight-action-mode-r3-protocol.json'
LEDGER = ROOT / 'learning/runs/v2-orchestration/state.json'
started = time.monotonic()
inspected = {}


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read(path):
    inspected[str(Path(path).relative_to(ROOT))] = digest(path)
    return json.loads(Path(path).read_text())


def rows(path):
    inspected[str(Path(path).relative_to(ROOT))] = digest(path)
    with Path(path).open() as stream:
        for line in stream:
            yield json.loads(line)


def save(name, value):
    with (HERE / name).open('x') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


protocol = read(PROTO)
result = read(OUTER / 'result.json')
worker = read(CAMP / 'worker-result.json')
run = read(CAMP / 'run-result.json')
terminal = read(CAMP / 'finalization-result.json')
exit_record = read(OUTER / 'process-exit.json')
seal = read(OUTER / 'final-seal.json')
checker_failure = read(OUTER / 'extra-verifier-failure.json')
assert result['status'] == run['status'] == worker['status'] == terminal['status'] == 'complete'
assert result['actual_command_launch_count'] == exit_record['actual_command_launch_count'] == 1
assert exit_record['observed_exit_code'] == 0
assert 0 < exit_record['actual_outer_wall_through_exit_seconds'] < 600
assert terminal['actual_total_wall_seconds'] < 600 and 0 <= terminal['cleanup_seconds'] <= 10
assert seal['result_sha256'] == digest(OUTER / 'result.json')

outer_manifest = read(OUTER / 'artifact-manifest-final.json')
for name, expected in outer_manifest.items():
    assert digest(OUTER / name) == expected, name
campaign_manifest = read(CAMP / 'artifact-manifest.json')
assert terminal['artifact_manifest_sha256'] == digest(CAMP / 'artifact-manifest.json')
assert terminal['run_result_sha256'] == digest(CAMP / 'run-result.json')
for name, expected in campaign_manifest.items():
    assert digest(CAMP / name) == expected, name
assert run['worker_result'] == worker
for name, expected in result['full_campaign_artifact_hashes'].items():
    assert digest(CAMP / name) == expected, name
live_inputs = 0
for name, expected in result['full_input_hashes'].items():
    if Path(name) != LEDGER:
        assert digest(name) == expected, name
        live_inputs += 1
assert checker_failure['campaign_launches'] == checker_failure['inference_calls'] == 0

seeds = tuple(range(0xD0000000, 0xD0000040))
controllers = (64001, 64002, 64003)
labels = ('entry', 'phase96', 'phase104')
order = protocol['order']
row_keys = {'episode_index', 'seed', 'score_raw_fixed', 'score', 'alive_frames',
            'gameplay_frames', 'terminated', 'truncated', 'objective_return'}
episodes = {}
groups = collections.defaultdict(dict)
totals = {'raw_frames': 0, 'deaths': 0, 'caps': 0, 'terminal_pattern_context': 0}
for episode in rows(CAMP / 'episodes.jsonl'):
    label, mode, controller = episode['checkpoint'], episode['mode'], episode['controller_seed']
    name = label + ('_argmax' if mode == 'argmax' else '_sample' + str(controller))
    assert name in order
    assert controller is None if mode == 'argmax' else controller in controllers
    row = episode['row']
    assert set(row) == row_keys and row['seed'] == seeds[row['episode_index']]
    assert type(row['alive_frames']) is int and type(row['gameplay_frames']) is int
    assert 0 <= row['alive_frames'] <= row['gameplay_frames'] <= 18000
    assert row['terminated'] != row['truncated']
    assert (row['terminated'] and row['gameplay_frames'] == row['alive_frames'] + 1) or (
        row['truncated'] and row['gameplay_frames'] == row['alive_frames'] == 18000)
    assert math.isfinite(row['score']) and row['score'] == row['score_raw_fixed'] / 65536
    assert abs(row['objective_return'] - (row['score'] + row['alive_frames'] / 100 - 5 * row['terminated'])) < 1e-9
    context = episode['context']
    assert context['context_presence_only'] is True and context['death_cause'] == 'UNKNOWN'
    assert context['observations'] == episode['decisions'] + 1
    observed = context['first_observed_pattern_gameplay_frame']
    assert (observed is None) == (context['pattern_presence_observations'] == 0)
    if observed is not None:
        assert 0 <= observed <= row['gameplay_frames']
        assert observed % 4 == 0 or observed == row['gameplay_frames']
    counts = context['terminal_observation_counts']
    assert all(type(value) is int and value >= 0 for value in counts.values())
    key = name, row['seed']
    assert key not in episodes
    episodes[key] = episode
    groups[name][row['seed']] = row
    totals['raw_frames'] += row['gameplay_frames']
    totals['deaths'] += row['terminated']
    totals['caps'] += row['truncated']
    totals['terminal_pattern_context'] += int(counts['admitted_rectangles'] > 0 or counts['onscreen_warnings'] > 0)
assert len(episodes) == 768 and len(groups) == 12
assert all(tuple(sorted(group)) == seeds for group in groups.values())

events = list(rows(CAMP / 'evaluations.jsonl'))
completed = [event for event in events if event['event'] == 'evaluation_complete']
assert [event['evaluation'] for event in completed] == order
for event in completed:
    assert {row['seed']: row for row in event['rows']} == groups[event['evaluation']]
assert [event['checkpoint'] for event in events if event['event'] == 'historical_control'] == ['entry', 'phase96']
sample_position = next(i for i, event in enumerate(events)
                       if event.get('evaluation', '').find('_sample') >= 0)
assert all(i < sample_position for i, event in enumerate(events) if event['event'] == 'historical_control')
for checkpoint in protocol['checkpoints']:
    if checkpoint['control']:
        historical = {row['seed']: row for row in rows(ROOT / checkpoint['control'])}
        assert len(historical) == 64 and historical == groups[checkpoint['label'] + '_argmax']

trace_counts = collections.Counter()
trace_groups = []
last_in_group = None
max_errors = collections.defaultdict(float)
for trace in rows(CAMP / 'decisions.jsonl'):
    label, mode, controller = trace['checkpoint'], trace['mode'], trace['controller_seed']
    name = label + ('_argmax' if mode == 'argmax' else '_sample' + str(controller))
    if not trace_groups or trace_groups[-1] != name:
        trace_groups.append(name)
        last_in_group = None
    assert trace['episode_seed'] == seeds[trace['episode_index']]
    key = name, trace['episode_seed']
    assert key in episodes and trace['decision_index'] == trace_counts[key]
    position = trace['decision_index'], trace['episode_index']
    assert last_in_group is None or position > last_in_group
    last_in_group = position
    assert trace['gameplay_frames_before_step'] == 4 * trace['decision_index']
    assert 0 <= trace['chosen_action'] < 9 and 0 <= trace['argmax_action'] < 9
    probabilities = trace['probabilities9']
    assert len(probabilities) == 9 and all(math.isfinite(p) and 0 <= p <= 1 for p in probabilities)
    norm_error = abs(sum(probabilities) - 1)
    expected_entropy = -sum(p * math.log(p) for p in probabilities if p)
    entropy_error = abs(trace['entropy'] - expected_entropy)
    largest = sorted(probabilities, reverse=True)[:2]
    margin_error = abs(trace['top1_top2_margin'] - (largest[0] - largest[1]))
    assert norm_error < 2e-6 and entropy_error < 2e-5 and margin_error < 2e-6
    assert abs(trace['top1_probability'] - largest[0]) < 2e-6
    assert abs(probabilities[trace['argmax_action']] - largest[0]) < 2e-6
    max_errors['probability_sum'] = max(max_errors['probability_sum'], norm_error)
    max_errors['entropy'] = max(max_errors['entropy'], entropy_error)
    max_errors['margin'] = max(max_errors['margin'], margin_error)
    if mode == 'argmax':
        assert controller is None and trace['chosen_action'] == trace['argmax_action']
    else:
        assert controller in controllers
    trace_counts[key] += 1
assert trace_groups == order
assert sum(trace_counts.values()) == worker['decisions_logged'] == worker['native_step_calls'] == 184280
assert all(trace_counts[key] == episode['decisions'] for key, episode in episodes.items())
assert all(math.ceil(episode['row']['gameplay_frames'] / 4) == episode['decisions'] for episode in episodes.values())
inference_calls = sum(max(episodes[(name, seed)]['decisions'] for seed in seeds) for name in order)
assert inference_calls == worker['inference_calls'] == 8339

indices = np.random.default_rng(764002).integers(0, 64, size=(10000, 64))
statistics_output = {}
for label in labels:
    base = np.array([[groups[label + '_argmax'][seed][metric] for metric in ('alive_frames', 'score')] for seed in seeds], dtype=np.float64)
    sampled = np.array([[[groups[label + '_sample' + str(controller)][seed][metric]
                         for metric in ('alive_frames', 'score')] for seed in seeds] for controller in controllers], dtype=np.float64).mean(axis=0)
    delta = sampled - base
    boot = delta[indices].mean(axis=1)
    interval = np.percentile(boot, [2.5, 97.5], axis=0)
    metrics = {}
    for j, metric in enumerate(('alive_frames', 'score')):
        actual = worker['statistics'][label]['metrics'][metric]
        expected = dict(argmax_mean=float(base[:, j].mean()), sampled_mean=float(sampled[:, j].mean()),
                        paired_mean_delta=float(delta[:, j].mean()), ci95=interval[:, j].tolist(),
                        practical_margin=100 if j == 0 else 1)
        for key, value in expected.items():
            assert np.allclose(value, actual[key], rtol=0, atol=1e-10), (label, metric, key)
            assert np.allclose(value, result['per_checkpoint_statistics'][label]['metrics'][metric][key], rtol=0, atol=1e-10)
        metrics[metric] = expected
    margins = np.array([100, 1])
    if np.all(interval[0] > -margins) and np.all(interval[1] < margins):
        decision = 'practical_similarity'
    elif np.all(interval[0] > margins):
        decision = 'meaningful_stochastic_advantage'
    elif np.all(interval[1] < -margins):
        decision = 'meaningful_argmax_advantage'
    else:
        decision = 'mixed_or_inconclusive'
    assert decision == worker['statistics'][label]['decision'] == result['per_checkpoint_statistics'][label]['decision']
    role = 'primary' if label == 'phase104' else 'secondary'
    assert worker['statistics'][label]['role'] == role
    statistics_output[label] = dict(role=role, seed_clusters=64, sampled_episodes=192,
                                   argmax_episodes=64, replicates_per_seed=3, metrics=metrics, decision=decision)

resources = {}
for label in ('worker', 'supervisor'):
    samples = list(rows(CAMP / (label + '-guard.jsonl')))
    assert samples and all(sample['sample_gap_seconds'] <= .5 for sample in samples)
    maxima = {key: max(sample[key] for sample in samples) for key in
              ('sampled_rss_bytes', 'self_peak_rss_bytes', 'mps_driver_bytes', 'sample_gap_seconds')}
    expected = result['resources']['raw_guard_maxima'][label]
    for key, value in maxima.items():
        assert value == expected[key]
        if key != 'sample_gap_seconds':
            assert value <= 6 * 1024 ** 3
    assert len(samples) == expected['samples']
    resources[label] = dict(samples=len(samples), **maxima)
outer_samples = list(rows(OUTER / 'outer-resources.jsonl'))
outer_maxima = collections.defaultdict(int)
for sample in outer_samples:
    for process in sample['owned_processes']:
        pid = str(process['pid'])
        outer_maxima[pid] = max(outer_maxima[pid], process['rss_bytes'])
assert dict(outer_maxima) == result['resources']['outer_observed_rss_maxima_by_pid']
assert len(outer_samples) == result['resources']['outer_samples']
ownership = read(OUTER / 'ownership-final.json')
processes = subprocess.run(['ps', '-p', ','.join(map(str, ownership['recorded_pids'])), '-o', 'pid=,ppid=,pgid=,command='], text=True, capture_output=True)
assert processes.returncode == 1 and not processes.stdout.strip()
for key, value in dict(gradient_updates=0, optimizer_instantiations=0, checkpoint_writes=0,
                       training_eligibility_changed=False, B_opened=False, E_opened=False,
                       automatic_retries=0, gradients_observed=False, qualification=False).items():
    assert worker[key] == value and run[key] == value
assert result['no_training'] and result['no_retry'] and result['no_fallback']
assert result['postflight_inference_calls'] == 0

raw = dict(episodes=len(episodes), groups=len(groups), decisions=sum(trace_counts.values()),
           inference_calls_reconstructed=inference_calls, **totals,
           exact_controls=2, fixed_group_order=trace_groups,
           statistics=statistics_output, resources=resources,
           trace_maximum_float_errors=dict(max_errors),
           outer_rss_maxima=dict(outer_maxima), outer_samples=len(outer_samples),
           command_launch_count=1, observed_exit=0,
           actual_outer_wall_seconds=exit_record['actual_outer_wall_through_exit_seconds'],
           terminal_lower_bound_wall_seconds=terminal['actual_total_wall_seconds'],
           cleanup_seconds=terminal['cleanup_seconds'], absent_owned_pids=ownership['recorded_pids'],
           outer_manifest_entries=len(outer_manifest), campaign_manifest_entries=len(campaign_manifest),
           current_input_hashes_verified=live_inputs,
           retained_file_verifier_failure=checker_failure['error'])
save('raw-checks.json', raw)
save('inspected-inputs.json', inspected)
audit = dict(status='passed_retained_diagnostic_audit', findings=[],
             finished_at_utc=datetime.now(timezone.utc).isoformat(),
             elapsed_seconds=time.monotonic() - started,
             scope='Read-only saved JSON/JSONL/hash/process checks and independent NumPy bootstrap; no Torch/native/model/gameplay/inference/tests/training.',
             raw_checks=str((HERE / 'raw-checks.json').relative_to(ROOT)),
             raw_checks_sha256=digest(HERE / 'raw-checks.json'),
             script=str(Path(__file__).relative_to(ROOT)), script_sha256=digest(__file__),
             inspected_inputs=str((HERE / 'inspected-inputs.json').relative_to(ROOT)),
             inspected_inputs_sha256=digest(HERE / 'inspected-inputs.json'),
             verified={key: raw[key] for key in ('episodes', 'groups', 'decisions', 'inference_calls_reconstructed',
                       'exact_controls', 'command_launch_count', 'observed_exit', 'actual_outer_wall_seconds',
                       'outer_manifest_entries', 'campaign_manifest_entries', 'current_input_hashes_verified', 'absent_owned_pids')},
             interpretation=['Entry sampled policy improves both point estimates and both zero-null confidence intervals, but score lower interval0.9453 is below predefined1-score material margin; fixed joint decision remains mixed/inconclusive.',
                             'At phase96 both paired intervals include zero. At primary phase104 sampling lowers survival point estimate and its interval excludes zero; score interval includes zero. No general late sampled advantage is supported.',
                             'None of the fixed joint material-margin decisions establishes practical similarity or two-metric material superiority; no automatic entropy/training/qualification conclusion follows.'],
             caveats=['The mutable parent ledger may change after campaign completion; its saved execution before/after comparison is retained, not a claim that the live ledger remains byte-identical during parent bookkeeping.',
                      'This audit recomputes statistics on the same fixed seed cohort; it is independent arithmetic, not replication gameplay or a qualification set.',
                      'Resource measurements remain sampled/cooperative; outer observer did not independently measure MPS driver allocation.',
                      'No training/eligibility/optimizer/checkpoint change is supported by reviewed inference-only code, runtime counters and immutable inputs; no OS syscall or optimizer interceptor audit was performed.',
                      'Terminal pattern observations are context, not killer labels. The retained hashlib.file_digest API checker failure occurred after the one campaign and caused no inference retry.'])
save('audit.json', audit)
print(json.dumps({'status': audit['status'], 'verified': audit['verified'], 'audit_sha256': digest(HERE / 'audit.json')}, indent=2))
