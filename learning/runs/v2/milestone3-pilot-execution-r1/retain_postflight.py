"""Retain receipt-only pilot checks after the one-shot wrapper exits.

No model forward, optimizer update, environment construction, or evaluation.
The wrapper exit code is supplied from the terminal tool's observed result.
"""
import collections
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
E = ROOT / 'learning/runs/v2/milestone3-pilot-execution-r1'
R = ROOT / 'learning/runs/v2/milestone3-D1-pilot-r1'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def save(name, value):
    with (E / name).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def finite(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite(v) for v in value.values())
    if isinstance(value, list):
        return all(finite(v) for v in value)
    return True


def main():
    started = time.monotonic()
    wrapper_exit = int(sys.argv[1])
    save('wrapper-tool-exit.json', {'exit_code': wrapper_exit, 'observation_source': 'exec_command/write_stdin terminal result',
                                  'recorded_at_utc': dt.datetime.now(dt.timezone.utc).isoformat()})
    original_result = (E / 'result.json').read_bytes()
    with (E / 'wrapper-result.json').open('xb') as stream:
        stream.write(original_result)
    result = json.loads(original_result)
    checks = {}
    failures = []
    def check(name, value):
        checks[name] = bool(value)
        if not value:
            failures.append(name)

    command = read(E / 'command-terminal.json')
    plan = read(ROOT / 'learning/runs/v2-orchestration/milestone3_D1_pilot_r1-plan.json')
    identity = read(ROOT / plan['identity'])
    events = lines(E / 'wrapper-events.jsonl')
    check('exactly_one_supervisor_launch', sum(row['kind'] == 'command_launched_once' for row in events) == result['command_launch_count'] == 1)
    check('exact_registered_argv_cwd_environment', command['argv'] == plan['argv'] and command['cwd'] == plan['cwd'] and command['environment_overrides'] == plan['environment'])
    check('wrapper_source_still_pinned', digest(E / 'execute_once.py') == command['wrapper_source_sha256'])
    check('all_75_source_pins_unchanged', len(identity['sources']) == 75 and all(digest(ROOT / name) == h for name, h in identity['sources'].items()))
    check('native_binary_unchanged', digest(identity['foundation']['extension_path']) == '967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583')
    runner_hashes = {str(p.relative_to(R)): digest(p) for p in sorted(R.rglob('*')) if p.is_file()}
    declared = read(R / 'artifact-sha256.json')
    check('runner_declared_artifact_hashes_match', bool(declared) and all(runner_hashes.get(n) == h for n, h in declared.items()))
    rr, wr = read(R / 'run-result.json'), read(R / 'worker-result.json')
    metrics = lines(R / 'training-metrics.jsonl')
    episodes = lines(R / 'training-episodes.jsonl')
    collections_accepted = [x for x in episodes if x['kind'] == 'collection_accepted']
    completed = [x['info'] for x in episodes if x['kind'] == 'native_completed_episode']
    reward_errors = [abs(x['objective_return'] - (x['score_raw_fixed'] / 65536 + x['alive_frames'] / 100 - 5 * x['terminated'])) for x in completed]
    check('all_logged_metrics_finite', finite(metrics) and all(x['metrics']['finite'] for x in metrics))
    check('integer_completed_episode_score_and_frame_audits', all(type(x['alive_frames']) is int and type(x['gameplay_frames']) is int and type(x['score_raw_fixed']) is int and x['score_raw_fixed'] == x['score_delta_sum_raw_fixed'] and x['score'] == x['score_raw_fixed'] / 65536 for x in completed))
    check('completed_episode_reward_audits', all(x <= 1e-9 for x in reward_errors))
    optimizer_steps = sum(x['metrics']['optimizer_steps'] for x in metrics)
    certificate = wr.get('evaluation')
    paired = None
    if certificate is not None:
        before, after = certificate['before'], certificate['evaluations']['D1']
        seed_list = list(range(3489660928, 3489660928 + 64))
        check('single_fixed64_D_evaluation_pair', [x['seed'] for x in before['rows']] == [x['seed'] for x in after['rows']] == seed_list and len(lines(R / 'pilot-before-development.jsonl')) == 64 and len(list(R.glob('*-D1-development.jsonl'))) == 1)
        for label, evaluation in [('before', before), ('after', after)]:
            check(label + '_means_match_integer_rows', evaluation['mean_score'] == sum(x['score_raw_fixed'] / 65536 for x in evaluation['rows']) / 64 and evaluation['mean_alive_frames'] == sum(x['alive_frames'] for x in evaluation['rows']) / 64)
            check(label + '_cap_and_death_counts', evaluation['caps'] == sum(x['truncated'] for x in evaluation['rows']) and evaluation['deaths'] == sum(x['terminated'] for x in evaluation['rows']) and all(x['gameplay_frames'] <= 2000 for x in evaluation['rows']))
        paired = {label: {k: evaluation[k] for k in ('episodes', 'mean_score', 'mean_alive_frames', 'deaths', 'caps', 'elapsed_seconds')} for label, evaluation in [('before', before), ('after', after)]}
        paired['strict_improvement_both'] = after['mean_score'] > before['mean_score'] and after['mean_alive_frames'] > before['mean_alive_frames']
        paired['registered_criterion'] = plan['pilot_comparison']
        paired['runner_certificate_passed'] = certificate['passed']

    import torch
    checkpoint_records = []
    for path in sorted(R.glob('*.pt')):
        state = torch.load(path, map_location='cpu', weights_only=False)
        optimizer = state['optimizer']['state']
        actual_steps = sorted({float(v['step'].item()) if hasattr(v['step'], 'item') else float(v['step']) for v in optimizer.values() if 'step' in v})
        row = {'file': path.name, 'sha256': digest(path), 'tag': state['tag'], 'counters': state['counters'],
               'optimizer_state_entries': len(optimizer), 'actual_optimizer_step_values': actual_steps,
               'parent_checkpoint_sha256': state['parent_checkpoint_sha256'], 'update_progress': state['update_progress'],
               'model_tensors_finite': all(bool(torch.isfinite(v).all()) for v in state['model'].values()),
               'rng_components': sorted(state['rng'])}
        checkpoint_records.append(row)
        check(path.name + '_parent_none_and_finite', row['parent_checkpoint_sha256'] is None and row['model_tensors_finite'])
        if state['tag'] == 'pilot_initial':
            check('fresh_initial_optimizer_and_zero_counters', not optimizer and state['counters']['updates'] == state['counters']['optimizer_steps'] == state['counters']['raw_frames'] == 0)
        if state['tag'] == 'candidate':
            check('candidate_steps_match_metrics_and_counters', actual_steps == [float(optimizer_steps)] and state['counters']['optimizer_steps'] == optimizer_steps and state['counters']['phase_updates'] == len(metrics))
        del state
    command_count = sum(row['kind'] == 'command_launched_once' for row in events)
    raw = subprocess.check_output(['ps', '-axo', 'pid=,ppid=,pgid=,lstart=,rss=,command='], text=True, timeout=5)
    (E / 'process-inventory-final.log').write_text(raw)
    owned_ids = [command['supervisor_pid']]
    ownership = E / 'worker-ownership-observed.json'
    if ownership.exists():
        owned_ids.append(read(ownership)['process']['pid'])
    rows = [line for line in raw.splitlines() if line.strip() and (int(line.split()[0]) in owned_ids or ('dodge_rl.train_teacher' in line and plan['run_id'] in line))]
    check('no_owned_process_remains', not rows)
    check('runner_manifest_has_every_artifact_except_self', set(runner_hashes) - set(declared) == {'artifact-sha256.json'})
    check('separate_supervisor_exit_receipts_agree', command['supervisor_exit_code'] == result['supervisor_exit_code'])
    diagnostics = {'completed_training_updates': len(metrics), 'actual_optimizer_steps_from_metrics': optimizer_steps,
                   'actor_gradient_seen': any(x['metrics']['actor_grad_norm'] > 0 for x in metrics),
                   'critic_gradient_seen': any(x['metrics']['critic_grad_norm'] > 0 for x in metrics),
                   'collection_acceptances': len(collections_accepted), 'completed_native_episodes': len(completed),
                   'training_deaths': sum(x['terminated'] for x in completed), 'training_caps': sum(x['truncated'] for x in completed),
                   'maximum_completed_episode_reward_abs_error': max(reward_errors, default=None),
                   'metric_ranges': {k: {'minimum': min(x['metrics'][k] for x in metrics), 'maximum': max(x['metrics'][k] for x in metrics)} for k in ('loss','policy_loss','value_loss','entropy','approx_kl','grad_norm','actor_grad_norm','critic_grad_norm','trunk_grad_norm','explained_variance')} if metrics else {},
                   'checkpoint_records': checkpoint_records}
    check('head_gradients_recorded', diagnostics['actor_gradient_seen'] and diagnostics['critic_gradient_seen'])
    receipt = {'checks': checks, 'receipt_failures': failures, 'paired_D_evaluation': paired, 'diagnostics': diagnostics,
               'wrapper_observed_exit_code': wrapper_exit, 'supervisor_observed_exit_code': command['supervisor_exit_code'],
               'runner_status': rr['status'], 'worker_status': wr['status'], 'command_invocation_count': command_count,
               'remaining_owned_processes': rows, 'consumed_phase_wall_seconds': rr['consumed_phase_wall_seconds'],
               'postflight_script_sha256': digest(__file__), 'postflight_duration_seconds': time.monotonic() - started,
               'parent_independent_acceptance_pending': True, 'D2_D3_qualification': False,
               'scope': 'receipt arithmetic, hash checks, process inspection, CPU checkpoint deserialization only'}
    save('postflight-receipt.json', receipt)
    result.update(wrapper_observed_exit_code=wrapper_exit, postflight_receipt='postflight-receipt.json',
                  postflight_receipt_sha256=digest(E / 'postflight-receipt.json'), paired_D_evaluation=paired,
                  diagnostics_summary=diagnostics, receipt_only_verification_failures=failures,
                  supervisor_observed_exit_code=command['supervisor_exit_code'],
                  task_elapsed_seconds=(dt.datetime.now(dt.timezone.utc) - dt.datetime(2026,10,24,11,27,35,tzinfo=dt.timezone.utc)).total_seconds(),
                  parent_alone_clears_lease_and_advances=True)
    if failures:
        result['status'] = 'retained_receipt_verification_failure'
    (E / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    for directory in (E, R):
        for path in directory.rglob('*.json'):
            subprocess.run([sys.executable, '-B', '-m', 'json.tool', str(path)], stdout=subprocess.DEVNULL, check=True)
    old_manifest = (E / 'artifact-sha256.json').read_bytes()
    with (E / 'wrapper-artifact-sha256.json').open('xb') as stream:
        stream.write(old_manifest)
    manifest = {str(p.relative_to(E)): digest(p) for p in sorted(E.rglob('*')) if p.is_file() and p != E / 'artifact-sha256.json'}
    (E / 'artifact-sha256.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': result['status'], 'paired': paired, 'completed_updates': len(metrics),
                      'actual_optimizer_steps': optimizer_steps, 'wrapper_exit': wrapper_exit,
                      'supervisor_exit': command['supervisor_exit_code'], 'failures': failures,
                      'result_sha256': digest(E / 'result.json'), 'artifact_manifest_sha256': digest(E / 'artifact-sha256.json')}))
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
