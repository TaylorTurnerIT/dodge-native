"""Retain receipt-only D1 curriculum checks after the one-shot wrapper exits.

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
E = ROOT / 'learning/runs/v2/milestone3-D1-execution-r1'
R = ROOT / 'learning/runs/v2/milestone3-D1-curriculum-r1'


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
    plan = read(ROOT / 'learning/runs/v2-orchestration/milestone3_D1_curriculum_r1-plan.json')
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
    import torch
    import numpy as np
    def equal_tree(a, b):
        if isinstance(a, torch.Tensor):
            return isinstance(b, torch.Tensor) and a.dtype == b.dtype and a.shape == b.shape and torch.equal(a, b)
        if isinstance(a, np.ndarray):
            return isinstance(b, np.ndarray) and a.dtype == b.dtype and np.array_equal(a, b)
        if isinstance(a, dict):
            return isinstance(b, dict) and set(a) == set(b) and all(equal_tree(a[k], b[k]) for k in a)
        if isinstance(a, (list, tuple)):
            return type(a) is type(b) and len(a) == len(b) and all(equal_tree(x,y) for x,y in zip(a,b))
        return type(a) is type(b) and a == b
    def tensor_tree_finite(a):
        if isinstance(a, torch.Tensor):
            return bool(torch.isfinite(a).all())
        if isinstance(a, dict):
            return all(tensor_tree_finite(x) for x in a.values())
        if isinstance(a, (list,tuple)):
            return all(tensor_tree_finite(x) for x in a)
        return True
    parent_path = ROOT / plan['parent_checkpoint']
    parent = torch.load(parent_path, map_location='cpu', weights_only=False)
    inherited = parent['counters']
    check('exact_parent_hash', digest(parent_path) == plan['parent_checkpoint_sha256'])
    checkpoint_records = []
    states = {}
    for path in sorted(R.glob('*.pt')):
        state = torch.load(path, map_location='cpu', weights_only=False)
        states[path.name] = state
        actual_steps = sorted({float(v['step'].item()) if hasattr(v['step'], 'item') else float(v['step']) for v in state['optimizer']['state'].values() if 'step' in v})
        row = {'file':path.name, 'sha256':digest(path), 'tag':state['tag'], 'counters':state['counters'],
               'optimizer_state_entries':len(state['optimizer']['state']), 'actual_optimizer_step_values':actual_steps,
               'parent_checkpoint_sha256':state['parent_checkpoint_sha256'], 'update_progress':state['update_progress'],
               'model_tensors_finite':tensor_tree_finite(state['model']), 'optimizer_tensors_finite':tensor_tree_finite(state['optimizer']),
               'rng_components':sorted(state['rng']), 'next_episode_indices':state['next_episode_indices']}
        checkpoint_records.append(row)
        check(path.name+'_identity_parent_and_finite', state['identity']==identity and row['parent_checkpoint_sha256']==plan['parent_checkpoint_sha256'] and row['model_tensors_finite'] and row['optimizer_tensors_finite'])
        complete_metrics=metrics[:state['counters']['phase_updates']]
        check(path.name+'_Adam_counters_match', actual_steps==[float(inherited['optimizer_steps']+sum(x['metrics']['optimizer_steps'] for x in complete_metrics))] and state['counters']['optimizer_steps']==int(actual_steps[0]))
        check(path.name+'_inherited_update_counts',state['counters']['updates']==inherited['updates']+state['counters']['phase_updates'])
        check(path.name+'_complete_update_boundary',not state['update_progress'].get('in_update',False) and (not state['update_progress'] or state['update_progress'].get('complete') is True))
    first_name=checkpoint_records[0]['file']; entry=states[first_name]
    check('entry_exact_inherited_model_Adam_RNG', all(equal_tree(entry[k],parent[k]) for k in ('model','optimizer','rng')))
    check('entry_inherited_counters_new_phase_zero',entry['counters']['phase_updates']==0 and all(entry['counters'][k]==inherited[k] for k in ('updates','optimizer_steps','environment_decisions','raw_frames')))
    initial=[x for x in episodes if x['kind']=='initial']
    check('one_fresh_registered_D1_namespace_all_zero',len(initial)==1 and initial[0]['batch_info']['initial_episode_indices']==[0]*64 and initial[0]['batch_info']['run_seed']==5562881586070242561 and initial[0]['batch_info']['difficulty']==1 and initial[0]['batch_info']['patterns_enabled'] is False and initial[0]['batch_info']['powerups_enabled'] is True and len(initial[0]['info'])==64 and all(x['seed']['episode']==0 and x['gameplay_frames']==0 for x in initial[0]['info']))
    abandoned=[{k:v for k,v in x.items() if k!='reason'} for x in episodes if x.get('reason')=='curriculum_namespace_transition']
    check('all_parent_abandoned_episodes_logged',abandoned==parent['abandoned_episodes'])
    lineage=read(R/'parent-lineage.json')
    check('immutable_eight_field_parent_lineage',lineage['parent_terminal_receipt']==plan['parent_terminal_receipt'] and len(lineage['parent_terminal_receipt'])==8 and lineage['parent_sha256']==plan['parent_checkpoint_sha256'] and lineage['transition_to']=='D1')
    check('eight_field_lease_unchanged',read(ROOT/'learning/runs/v2-orchestration/state.json')['active_long_campaign']['parent_terminal_receipt']==plan['parent_terminal_receipt'])
    seed_infos=initial[0]['info']+[v for x in episodes if x['kind']=='native_reset' for v in x['info']]
    check('training_seed_exclusions_logged',all(not s['seed']['evaluation'] and not any(lo<=s['seed']['actual_seed']<=hi for lo,hi in identity['config']['excluded_seed_ranges']) for s in seed_infos))
    check('unique_training_slot_episode_starts',len({(s['seed']['slot'],s['seed']['episode']) for s in seed_infos})==len(seed_infos))
    paired=[]
    for path in sorted(R.glob('*.pt.evaluation.json')):
        certificate=read(path)
        checkpoint_name=path.name.removesuffix('.evaluation.json')
        state=states[checkpoint_name]
        check(path.name+'_complete_D1_exact_hash',certificate['phase']=='D1' and certificate['complete'] is True and set(certificate['evaluations'])=={'D1'} and certificate['checkpoint_sha256']==digest(R/checkpoint_name))
        evaluation=certificate['evaluations']['D1']; rows=evaluation['rows']
        log=R/(Path(checkpoint_name).stem+'-D1-development.jsonl')
        check(path.name+'_exact_fixed64_raw_rows',evaluation['episodes']==len(rows)==64 and [x['seed'] for x in rows]==list(range(3489660928,3489660992)) and sorted(lines(log),key=lambda x:x['episode_index'])==rows)
        check(path.name+'_means_deaths_caps',evaluation['mean_score']==sum(x['score_raw_fixed']/65536 for x in rows)/64 and evaluation['mean_alive_frames']==sum(x['alive_frames'] for x in rows)/64 and evaluation['deaths']==sum(x['terminated'] for x in rows) and evaluation['caps']==sum(x['truncated'] for x in rows) and evaluation['caps']+evaluation['deaths']==64)
        check(path.name+'_cap_objective_integers',all(type(x['alive_frames']) is int and type(x['score_raw_fixed']) is int and x['score']==x['score_raw_fixed']/65536 and x['gameplay_frames']<=2000 and abs(x['objective_return']-(x['score']+x['alive_frames']/100-5*x['terminated']))<=1e-9 for x in rows))
        passed=evaluation['mean_score']>=10 and evaluation['mean_alive_frames']>=1500
        check(path.name+'_exact_registered_gate',certificate['passed']==passed and evaluation['action_mode']=='deterministic_argmax' and evaluation['gradients'] is False)
        paired.append({'checkpoint':checkpoint_name,'checkpoint_sha256':certificate['checkpoint_sha256'],'phase_updates':state['counters']['phase_updates'],'certificate_sha256':digest(path),'passed':certificate['passed'], **{k:evaluation[k] for k in ('episodes','mean_score','mean_alive_frames','deaths','caps','elapsed_seconds')}})
    check('entry_every16_no_reselection', [x['phase_updates'] for x in paired]==list(range(0,len(metrics)+1,16)))
    successful=[x for x in paired if x['passed']]
    check('stop_at_first_successful_exact_terminal_candidate',bool(successful) and len(successful)==1 and successful[0]==paired[-1] and paired[-1]['phase_updates']==len(metrics) and paired[-1]['checkpoint']==wr['checkpoint'] and paired[-1]['checkpoint_sha256']==wr['checkpoint_sha256'])
    check('terminal_certificate_and_counters_exact',read(R/(wr['checkpoint']+'.evaluation.json'))==wr['evaluation'] and wr['counters']==states[wr['checkpoint']]['counters'])
    check('inherited_plus_new_Adam_and_updates',wr['counters']['optimizer_steps']==inherited['optimizer_steps']+optimizer_steps and wr['counters']['updates']==inherited['updates']+len(metrics) and wr['counters']['phase_updates']==len(metrics))
    check('raw_collection_frames_accounted',wr['counters']['raw_frames']==inherited['raw_frames']+sum(x['returned_raw_frames'] for x in collections_accepted))
    check('phase_budget_observed_exit_success',command['supervisor_exit_code']==wrapper_exit==rr['worker_exit_code']==0 and rr['status']==wr['status']=='passed' and rr['consumed_phase_wall_seconds']<=1800 and not command['timed_out'])
    check('full_budget_reserve_fit_actual_launch',command['seconds_to_cutoff_at_launch']>=2400 and command['outer_timeout_seconds']==1830)
    check('B_E_and_next_stage_absent',rr['B_opened'] is False and wr['B_opened'] is False and not rr.get('E_opened',False) and not list(R.glob('*-D2-*')) and not list(R.glob('*-D3-*')))
    command_count = sum(row['kind'] == 'command_launched_once' for row in events)
    raw = subprocess.check_output(['ps', '-axo', 'pid=,ppid=,pgid=,lstart=,rss=,command='], text=True, timeout=5)
    (E / 'process-inventory-final.log').write_text(raw)
    owned_ids = [command['wrapper_pid'], command['supervisor_pid']]
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
                   'checkpoint_records': checkpoint_records,
                   'inherited_updates': inherited['updates'], 'inherited_Adam_steps': inherited['optimizer_steps'],
                   'new_updates':len(metrics), 'new_Adam_steps':optimizer_steps, 'total_updates':wr['counters']['updates'], 'total_Adam_steps':wr['counters']['optimizer_steps'],
                   'new_training_raw_frames':wr['counters']['raw_frames']-inherited['raw_frames'],
                   'parent_abandoned_episodes_logged':len(abandoned), 'new_training_episode_starts':len(seed_infos),
                   'completed_episode_reward':{'minimum':min(x['objective_return'] for x in completed),'maximum':max(x['objective_return'] for x in completed),'mean':sum(x['objective_return'] for x in completed)/len(completed),'sum':sum(x['objective_return'] for x in completed)},
                   'completed_episode_mean_score':sum(x['score'] for x in completed)/len(completed), 'completed_episode_mean_alive_frames':sum(x['alive_frames'] for x in completed)/len(completed)}
    check('head_gradients_recorded', diagnostics['actor_gradient_seen'] and diagnostics['critic_gradient_seen'])
    check('runner_artifacts_unchanged_after_CPU_receipt_inspection', all(digest(R/n)==h for n,h in runner_hashes.items()))
    receipt = {'checks': checks, 'receipt_failures': failures, 'development_evaluations': paired, 'diagnostics': diagnostics,
               'wrapper_observed_exit_code': wrapper_exit, 'supervisor_observed_exit_code': command['supervisor_exit_code'],
               'runner_status': rr['status'], 'worker_status': wr['status'], 'command_invocation_count': command_count,
               'remaining_owned_processes': rows, 'consumed_phase_wall_seconds': rr['consumed_phase_wall_seconds'],
               'signal_events': [x for x in events if 'signal' in x['kind'] or x['kind']=='outer_timeout'], 'outer_timed_out':command['timed_out'],
               'supervisor_command_wall_seconds':command['duration_seconds'], 'wrapper_wall_seconds':result['wrapper_duration_seconds'],
               'postflight_script_sha256': digest(__file__), 'postflight_duration_seconds': time.monotonic() - started,
               'parent_independent_acceptance_pending': True, 'D2_D3_qualification': False,
               'scope': 'receipt arithmetic, hash checks, process inspection, CPU checkpoint deserialization only'}
    save('postflight-receipt.json', receipt)
    result.update(wrapper_observed_exit_code=wrapper_exit, postflight_receipt='postflight-receipt.json',
                  postflight_receipt_sha256=digest(E / 'postflight-receipt.json'), development_evaluations=paired,
                  diagnostics_summary=diagnostics, receipt_only_verification_failures=failures,
                  supervisor_observed_exit_code=command['supervisor_exit_code'],
                  task_elapsed_seconds=(dt.datetime.now(dt.timezone.utc) - dt.datetime(2026,10,24,11,42,42,tzinfo=dt.timezone.utc)).total_seconds(),
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
