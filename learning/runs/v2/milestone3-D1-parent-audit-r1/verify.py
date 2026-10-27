from __future__ import annotations
import collections, datetime, hashlib, json, math, pathlib, subprocess, time
import numpy as np
import torch
from dodge_rl import checkpoints as ckpt

ROOT = pathlib.Path.cwd()
OUT = ROOT / 'learning/runs/v2/milestone3-D1-parent-audit-r1'
RUN = ROOT / 'learning/runs/v2/milestone3-D1-curriculum-r1'
EXE = ROOT / 'learning/runs/v2/milestone3-D1-execution-r1'
START = datetime.datetime.now(datetime.timezone.utc)
AT = time.monotonic()
inputs = {}

def raw(path):
    path = pathlib.Path(path)
    value = path.read_bytes()
    digest = hashlib.sha256(value).hexdigest()
    name = str(path.relative_to(ROOT))
    if name in inputs:
        assert inputs[name] == digest, ('input changed', name)
    inputs[name] = digest
    return value

def digest(path): return hashlib.sha256(raw(path)).hexdigest()
def data(path): return json.loads(raw(path))
def rows(path): return [json.loads(line) for line in raw(path).splitlines()]

def finite(value):
    if isinstance(value, torch.Tensor):
        return not value.is_floating_point() or bool(torch.isfinite(value).all())
    if isinstance(value, dict): return all(finite(x) for x in value.values())
    if isinstance(value, (tuple, list)): return all(finite(x) for x in value)
    return not isinstance(value, float) or math.isfinite(value)

def equal(a, b):
    if isinstance(a, torch.Tensor):
        return isinstance(b, torch.Tensor) and a.dtype == b.dtype and a.shape == b.shape and torch.equal(a, b)
    if isinstance(a, np.ndarray):
        return isinstance(b, np.ndarray) and a.dtype == b.dtype and np.array_equal(a, b)
    if isinstance(a, dict):
        return isinstance(b, dict) and set(a) == set(b) and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b

plan_path = ROOT / 'learning/runs/v2-orchestration/milestone3_D1_curriculum_r1-plan.json'
assert digest(plan_path) == '9872325c5ad1714b32d3491870c29912e92b91ff246025adade171e82c744433'
plan = data(plan_path)
counts = {}
for directory, label in [(EXE, 'execution'), (RUN, 'runner')]:
    manifest = data(directory / 'artifact-sha256.json')
    for name, expected in manifest.items():
        assert digest(directory / name) == expected, (label, name)
    inventory = {str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()}
    assert inventory == set(manifest) | {'artifact-sha256.json'}, (label, 'inventory')
    counts[label] = len(manifest)
assert counts['runner'] == 23
identity = data(ROOT / plan['identity'])
config = data(ROOT / plan['config'])
assert digest(ROOT / plan['identity']) == plan['identity_sha256'] == '7df70937ae7ced6f993277dae2d02f22c6ffee4a0ddfa0fcb26ef8388e6f1e63'
assert digest(ROOT / plan['config']) == plan['config_sha256'] == '624c491ce59881e232ff25750a5a13e312b08bfdea39cc4c86bd17149a19f789'
canonical = json.dumps(config, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
assert hashlib.sha256(canonical).hexdigest() == plan['semantic_config_sha256'] == identity['config_sha256']
assert len(identity['sources']) == 75
for name, expected in identity['sources'].items(): assert digest(ROOT / name) == expected, name
assert config['phase'] == 'D1' and config['device'] == 'mps'
assert config['phase_settings']['run_seed'] == 5562881586070242561
assert config['phase_settings']['difficulty'] == 1 and config['phase_settings']['patterns_enabled'] is False
assert config['phase_settings']['budget_seconds'] == 1800
assert data(RUN / 'registered-config.json') == config and data(RUN / 'identity.json') == identity
command = data(EXE / 'command-terminal.json')
start = data(EXE / 'command-start.json')
assert command['argv'] == start['argv'] == plan['argv']
assert command['environment_overrides'] == plan['environment'] and command['cwd'] == plan['cwd']
assert type(command['supervisor_exit_code']) is int and command['supervisor_exit_code'] == 0
assert command['timed_out'] is False and command['duration_seconds'] < 1830
assert command['seconds_to_cutoff_at_launch'] >= 2400
assert digest(EXE / 'execute_once.py') == command['wrapper_source_sha256']
assert data(EXE / 'wrapper-tool-exit.json')['exit_code'] == 0
postflight_tool = data(EXE / 'postflight-tool-exit.json')
assert postflight_tool['exit_code'] == 0 and postflight_tool['wrapper_observed_exit_code'] == 0
assert digest(EXE / 'retain_postflight.py') == postflight_tool['script_sha256']
events = rows(EXE / 'wrapper-events.jsonl')
assert sum(x['kind'] == 'command_launched_once' for x in events) == 1
assert not any('signal' in x['kind'].lower() or 'timeout' in x['kind'].lower() for x in events)
rr = data(RUN / 'run-result.json'); wr = data(RUN / 'worker-result.json'); er = data(EXE / 'result.json')
assert rr['status'] == wr['status'] == 'passed' and rr['worker_result'] == wr
assert rr['worker_exit_code'] == 0 and 0 < rr['consumed_phase_wall_seconds'] < 1800
assert abs(rr['consumed_phase_wall_seconds'] - 554.3451906670234) < 1e-9
assert rr['automatic_retries'] == 0 and rr['limits_relaxed'] is False and rr['B_opened'] is False
assert er['command_launch_count'] == 1 and er['B_E_opened'] is False and er['automatic_retries'] == 0
postflight = data(EXE / 'postflight-receipt.json')
assert len(postflight['checks']) == 66 and all(value is True for value in postflight['checks'].values())
assert postflight['receipt_failures'] == [] and postflight['signal_events'] == [] and postflight['remaining_owned_processes'] == []
assert er['evidence_verification_failures'] == [] and er['receipt_only_verification_failures'] == []

expected_seeds = list(range(3489660928, 3489660992))
evaluations = []
expected_values = [(0, 3.921875, 990.296875, 61, 3, False), (16, 7.90625, 1347.421875, 44, 20, False), (32, 12.109375, 1917.53125, 7, 57, True)]
for proof_path, expected in zip(sorted(RUN.glob('*.evaluation.json')), expected_values, strict=True):
    proof = data(proof_path)
    checkpoint = pathlib.Path(str(proof_path)[:-len('.evaluation.json')])
    stream = sorted(rows(RUN / (checkpoint.stem + '-D1-development.jsonl')), key=lambda x: x['episode_index'])
    value = proof['evaluations']['D1']
    assert stream == value['rows'] and len(stream) == 64
    assert [x['seed'] for x in stream] == expected_seeds and [x['episode_index'] for x in stream] == list(range(64))
    assert value['action_mode'] == 'deterministic_argmax' and value['gradients'] is False and value['complete'] is True
    assert proof['complete'] is True and proof['phase'] == 'D1' and proof['checkpoint_sha256'] == digest(checkpoint)
    for row in stream:
        assert row['score'] == row['score_raw_fixed'] / 65536
        assert row['terminated'] != row['truncated'] and 0 < row['gameplay_frames'] <= 2000
        assert row['alive_frames'] == row['gameplay_frames'] - int(row['terminated'])
        assert abs(row['objective_return'] - (row['score'] + row['alive_frames'] / 100 - 5 * int(row['terminated']))) <= 1e-9
    score = sum(x['score_raw_fixed'] for x in stream) / (64 * 65536)
    alive = sum(x['alive_frames'] for x in stream) / 64
    deaths = sum(x['terminated'] for x in stream); caps = sum(x['truncated'] for x in stream)
    phase_updates, want_score, want_alive, want_deaths, want_caps, want_pass = expected
    assert (score, alive, deaths, caps, proof['passed']) == (want_score, want_alive, want_deaths, want_caps, want_pass)
    assert score == value['mean_score'] and alive == value['mean_alive_frames']
    assert proof['passed'] == (score >= 10 and alive >= 1500)
    evaluations.append({'phase_updates': phase_updates, 'checkpoint': checkpoint.name, 'checkpoint_sha256': digest(checkpoint), 'mean_score': score, 'mean_alive_frames': alive, 'deaths': deaths, 'caps': caps, 'passed': proof['passed']})
assert evaluations[-1]['checkpoint_sha256'] == 'ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f'
assert wr['checkpoint'] == evaluations[-1]['checkpoint'] and wr['evaluation'] == data(RUN / (wr['checkpoint'] + '.evaluation.json'))

metrics = rows(RUN / 'training-metrics.jsonl')
assert len(metrics) == 32 and finite(metrics)
assert [x['counters']['phase_updates'] for x in metrics] == list(range(1, 33))
assert all(x['metrics']['finite'] and x['metrics']['actor_grad_norm'] > 0 and x['metrics']['critic_grad_norm'] > 0 for x in metrics)
assert all(x['metrics']['entropy'] >= .3 and x['metrics']['approx_kl'] < .1 for x in metrics)
assert sum(x['metrics']['optimizer_steps'] for x in metrics) == 4096
assert all(x['metrics']['transitions'] == 16384 and x['metrics']['epochs_completed'] == 4 for x in metrics)
assert wr['counters']['updates'] == 48 and wr['counters']['phase_updates'] == 32 and wr['counters']['optimizer_steps'] == 6144
training = rows(RUN / 'training-episodes.jsonl')
completed = [x['info'] for x in training if x['kind'] == 'native_completed_episode']
assert len(completed) == 982 and len({(x['seed']['slot'], x['seed']['episode']) for x in completed}) == 982
errors = []
for info in completed:
    assert info['score_raw_fixed'] == info['score_delta_sum_raw_fixed'] and info['score'] == info['score_raw_fixed'] / 65536
    assert info['alive_frames'] == info['gameplay_frames'] - int(info['terminated'])
    error = abs(info['objective_return'] - (info['score_delta_sum_raw_fixed'] / 65536 + info['alive_frames'] / 100 - 5 * int(info['terminated'])))
    errors.append(error); assert error <= 1e-9
accepts = [x for x in training if x['kind'] == 'collection_accepted']
assert len(accepts) == 32 and sum(x['completed_episodes'] for x in accepts) == 982
assert sum(x['returned_raw_frames'] for x in accepts) == wr['counters']['raw_frames'] - 1043929 == 2095623
initial = [x for x in training if x['kind'] == 'initial']; assert len(initial) == 1
assert initial[0]['batch_info']['run_seed'] == 5562881586070242561
assert initial[0]['batch_info']['initial_episode_indices'] == [0] * 64
ranges = [(2952790016, 2952791015), (3489660928, 3489661055), (3758096384, 3758097383)]
assert initial[0]['batch_info']['effective_excluded_seed_ranges'] == [list(x) for x in ranges]
infos = list(initial[0]['info'])
for row in training:
    if row['kind'] == 'native_reset': infos.extend(row['info'])
seen = set(); last = {}
for info in infos:
    seed = info['seed']; slot = seed['slot']; episode = seed['episode']; actual = seed['actual_seed']
    assert type(actual) is int and 0 <= actual < 2**32 and not any(a <= actual <= b for a, b in ranges)
    assert seed['evaluation'] is False and (slot, episode) not in seen
    seen.add((slot, episode)); assert episode == last.get(slot, -1) + 1; last[slot] = episode
resources = {}
for filename in ['supervisor-resources.jsonl', 'worker-resources.jsonl']:
    values = rows(RUN / filename); assert values and finite(values)
    resources[filename] = {'samples': len(values), 'maximum_rss_bytes': max(x.get('rss_bytes', 0) for x in values), 'maximum_self_peak_rss_bytes': max(x.get('self_peak_rss_bytes', 0) for x in values), 'maximum_mps_driver_bytes': max(x.get('mps_driver_bytes', 0) for x in values), 'maximum_worker_rss_bytes': max(x.get('worker_rss_bytes', 0) for x in values)}
    assert all(value <= 6442450944 for name, value in resources[filename].items() if name != 'samples')
assert resources == data(EXE / 'resource-summary.json') == er['actual_resource_series_maxima']
assert max(resources['worker-resources.jsonl']['maximum_rss_bytes'], resources['worker-resources.jsonl']['maximum_self_peak_rss_bytes']) == wr['maximum_observed_RSS_bytes'] == 950599680
assert resources['worker-resources.jsonl']['maximum_mps_driver_bytes'] == wr['maximum_MPS_driver_bytes'] == 2451243008
owned = data(RUN / 'owned-process.json'); pids = [command['wrapper_pid'], command['supervisor_pid'], owned['owned_pid']]
check = subprocess.run(['ps', '-p', ','.join(map(str, pids)), '-o', 'pid=,pgid=,command='], capture_output=True, text=True, timeout=5)
assert check.returncode == 1 and not check.stdout.strip(), check.stdout
assert data(EXE / 'process-ownership-after.json')['remaining_owned'] == []

parent_path = ROOT / plan['parent_checkpoint']
assert digest(parent_path) == plan['parent_checkpoint_sha256']
parent = torch.load(parent_path, map_location='cpu', weights_only=False)
lineage = data(RUN / 'parent-lineage.json')
assert lineage['parent_sha256'] == plan['parent_checkpoint_sha256'] and lineage['parent_terminal_receipt'] == plan['parent_terminal_receipt'] and lineage['transition_to'] == 'D1'
states = []; tensor_summary = []
for path in sorted(RUN.glob('*.pt')):
    raw(path); state = torch.load(path, map_location='cpu', weights_only=False); states.append(state)
    assert state['identity'] == identity and state['parent_checkpoint_sha256'] == plan['parent_checkpoint_sha256']
    assert finite(state['model']) and finite(state['optimizer'])
    steps = sorted({float(value['step']) for value in state['optimizer']['state'].values()})
    assert steps == [float(state['counters']['optimizer_steps'])]
    if state['counters']['phase_updates']:
        assert state['update_progress']['complete'] is True and not state['update_progress']['in_update']
    tensor_summary.append({'file': path.name, 'phase_updates': state['counters']['phase_updates'], 'total_updates': state['counters']['updates'], 'Adam_steps': steps, 'tag': state['tag']})
entry, final = states[0], states[-1]
assert equal(entry['model'], parent['model']) and equal(entry['optimizer'], parent['optimizer']) and equal(entry['rng'], parent['rng'])
assert entry['counters']['updates'] == 16 and entry['counters']['optimizer_steps'] == 2048 and entry['counters']['phase_updates'] == 0
assert final['counters']['updates'] == 48 and final['counters']['optimizer_steps'] == 6144 and final['counters']['phase_updates'] == 32
assert any(not torch.equal(value, final['model'][name]) for name, value in entry['model'].items())
abandoned = [x for x in training if x['kind'] == 'abandoned_on_fresh_env_resume']
assert len(abandoned) == 64
expected_abandoned = [dict(x, reason='curriculum_namespace_transition') for x in parent['abandoned_episodes']]
assert abandoned == expected_abandoned
anchor = {'run_id': rr['run_id'], 'phase': 'D1', 'run_result_sha256': digest(RUN / 'run-result.json'), 'checkpoint_sha256': digest(RUN / wr['checkpoint']), 'evaluation_sha256': digest(RUN / (wr['checkpoint'] + '.evaluation.json')), 'identity_sha256': plan['identity_sha256'], 'config_sha256': plan['config_sha256'], 'supervisor_exit_code': command['supervisor_exit_code']}
validated_rr, validated_wr = ckpt.validate_terminal_receipt(RUN, anchor)
assert validated_rr == rr and validated_wr == wr
for name, expected in inputs.items(): assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
(OUT / 'inspected-inputs.json').write_text(json.dumps(inputs, indent=2, sort_keys=True) + '\n')
report = {'status': 'passed', 'findings': [], 'started_at_utc': START.isoformat(), 'finished_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'elapsed_seconds': time.monotonic() - AT, 'scope': 'retained_receipts_raw_rows_CPU_checkpoint_deserialization_and_read_only_terminal_validator;no_model_execution_update_gameplay_or_tests', 'verified': {'execution_artifacts': counts['execution'], 'runner_artifacts': counts['runner'], 'current_source_pins': 75, 'command_invocations': 1, 'supervisor_exit_code': 0, 'worker_exit_code': 0, 'source_phase_wall_seconds': rr['consumed_phase_wall_seconds'], 'postflight_checks': 66, 'all_inspected_inputs_unchanged': len(inputs), 'terminal_validator': 'passed', 'completed_training_episodes': len(completed), 'maximum_reward_error': max(errors), 'training_seed_starts_and_resets_checked': len(infos), 'new_updates': 32, 'new_Adam_steps': 4096, 'inherited_updates': 16, 'inherited_Adam_steps': 2048, 'total_updates': 48, 'total_Adam_steps': 6144, 'entry_model_Adam_RNG_equal_parent': True, 'abandoned_parent_episodes_logged': 64, 'no_owned_processes': pids}, 'development_evaluations': evaluations, 'resource_maxima': resources, 'checkpoint_tensor_summary': tensor_summary, 'parent_terminal_receipt': anchor, 'parent_checkpoint': str((RUN / wr['checkpoint']).relative_to(ROOT)), 'parent_checkpoint_sha256': digest(RUN / wr['checkpoint']), 'D1_competence_passed': True, 'D2_D3_qualified': False, 'caveats': ['D1 evaluation cap is 2000 frames; 57 of 64 final episodes are censored. No uncapped survival or D2/D3 qualification follows.', 'Entry model, Adam and saved RNG tensors equal the accepted pilot checkpoint exactly; no gameplay or initializer replay was performed.', 'RSS and MPS driver peaks are separate sampled/cooperative measurements, not unsampled hard OS limits.']}
(OUT / 'audit.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print(json.dumps(report))
