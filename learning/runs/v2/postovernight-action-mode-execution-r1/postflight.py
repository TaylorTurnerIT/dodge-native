#!/usr/bin/env python3
"""Read-only stdlib verification after the sole campaign and observer have exited."""
import collections
import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
import traceback

ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
OUT = ROOT / 'learning/runs/v2/postovernight-action-mode-execution-r1'
CAMP = ROOT / 'learning/runs/v2/postovernight-action-mode-campaign-r1'
STATE = ROOT / 'learning/runs/v2-orchestration/state.json'
SEEDS = set(range(3489660928, 3489660992))
ROW_KEYS = {'episode_index','seed','score_raw_fixed','score','alive_frames','gameplay_frames',
            'terminated','truncated','objective_return'}

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def save(name, value):
    with (OUT / name).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def finite(value):
    if isinstance(value, float):
        require(math.isfinite(value), 'Nonfinite numeric output')
    elif isinstance(value, dict):
        for v in value.values():
            finite(v)
    elif isinstance(value, list):
        for v in value:
            finite(v)

def records(path):
    if path.exists():
        with path.open() as stream:
            for line in stream:
                item = json.loads(line)
                finite(item)
                yield item

def matrix_name(record):
    label, mode, seed = record['checkpoint'], record['mode'], record['controller_seed']
    require(label in ('entry','phase96','phase104'), 'Unexpected checkpoint label')
    require((mode == 'argmax' and seed is None) or
            (mode == 'sample' and seed in (64001,64002,64003)), 'Controller assignment mismatch')
    return label + ('_argmax' if mode == 'argmax' else '_sample' + str(seed))

def validate_row(row):
    require(set(row) == ROW_KEYS, 'Original row keys differ')
    require(type(row['episode_index']) is int and 0 <= row['episode_index'] < 64
            and row['seed'] == 3489660928 + row['episode_index'], 'D seed/index mismatch')
    a,g,s = row['alive_frames'],row['gameplay_frames'],row['score_raw_fixed']
    require(type(a) is int and type(g) is int and type(s) is int and 0 <= a <= g <= 18000
            and s >= 0 and row['score'] == s/65536, 'Invalid frames/score identity')
    t,c = row['terminated'],row['truncated']
    require(type(t) is bool and type(c) is bool and t != c
            and ((t and g == a+1) or (c and g == a == 18000)), 'Invalid endpoint')
    require(math.isclose(row['objective_return'],s/65536+a/100-5*t,abs_tol=1e-9,rel_tol=0),
            'Objective return mismatch')

def main():
    exit_receipt = read(OUT / 'process-exit.json')
    preflight = read(OUT / 'preflight.json')
    plan = read(ROOT / 'learning/runs/v2-orchestration/postovernight-action-mode-execution-r1-plan-r3.json')
    protocol = read(plan['protocol'])
    result = dict(status='failed', diagnostic_only=True, qualification=False,
                  actual_command_launch_count=exit_receipt['actual_command_launch_count'],
                  command=read(OUT/'command.json'), process_exit=exit_receipt,
                  no_retry=True, no_fallback=True, no_training=True, parent_lease_cleared=False,
                  postflight_inference_calls=0, preflight=preflight, postflight_checks={}, errors=[],
                  original_experiment_limit_seconds=600, separate_cleanup_reserve_seconds=10)
    checks = result['postflight_checks']
    def check(name, function):
        try:
            value = function()
            checks[name] = dict(passed=True, detail=value)
            return value
        except BaseException as error:
            checks[name] = dict(passed=False, error=repr(error), traceback=traceback.format_exc())
            result['errors'].append(name + ': ' + repr(error))
            return None

    def ownership():
        p = subprocess.run(['ps','-axo','pid=,ppid=,pgid=,lstart=,rss=,args='],
                           capture_output=True,text=True,timeout=2)
        require(p.returncode == 0, 'Cannot prove final process absence')
        ids = {exit_receipt.get('supervisor_pid'),exit_receipt['wrapper_pid'],
               exit_receipt.get('worker_identity',{}).get('pid')}-{None}
        groups = {exit_receipt.get('supervisor_pgid'),exit_receipt.get('worker_identity',{}).get('pgid')}-{None}
        remaining=[]
        for line in p.stdout.splitlines():
            f=line.split(None,3)
            if len(f)==4 and (int(f[0]) in ids or int(f[2]) in groups):
                remaining.append(line)
        value=dict(recorded_pids=sorted(ids), owned_groups=sorted(groups), remaining=remaining,
                   supervisor_reaped=exit_receipt.get('observed_exit_code') is not None,
                   checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   wrapper_stdout_stderr_closed=True)
        save('ownership-final.json',value)
        require(not remaining and value['supervisor_reaped'], 'Recorded owned processes remain or exit unknown')
        return value
    check('owned_supervisor_worker_wrapper_absent',ownership)

    def inputs():
        pins=read(OUT/'input-inventory.json')['pins']
        actual={path:sha(path) for path in pins}
        save('input-hashes-after.json',actual)
        require(actual==pins,'Postflight frozen input bytes changed')
        before=read(OUT/'protected-before.json')
        after={path:sha(path) for path in before}
        save('protected-after.json',after)
        require(after==before,'Protected original sources/checkpoints/controls/metadata bytes changed')
        result['full_input_hashes']=actual
        result['full_protected_hashes']=after
        require(read(STATE)==read(OUT/'state-before.json'),'Production ledger changed during execution')
        return dict(input_pins=len(actual),protected_files=len(after),ledger_byte_identical=True,
                    checkpoint_hashes={c['label']:c['sha256'] for c in protocol['checkpoints']})
    check('all_pinned_and_protected_bytes_unchanged',inputs)

    def tree():
        after={}
        for base in (ROOT/'learning/runs/v2',ROOT/'learning/runs/v2-orchestration'):
            for p in sorted(base.rglob('*')):
                if p.is_file() and not p.is_relative_to(OUT) and not p.is_relative_to(CAMP):
                    s=p.stat()
                    after[str(p.relative_to(ROOT))]=dict(size=s.st_size,mtime_ns=s.st_mtime_ns,
                                                        mode=s.st_mode,inode=s.st_ino)
        before=read(OUT/'tree-before.json')
        changes={k:dict(before=before.get(k),after=after.get(k)) for k in before.keys()|after.keys()
                 if before.get(k)!=after.get(k)}
        save('tree-after-differences.json',changes)
        require(not changes,'Prior run tree metadata changed or unexpected file created outside owned outputs')
        return dict(prior_files=len(before),changes=0,scope='learning/runs/v2 and v2-orchestration; excludes both owned output directories')
    check('no_other_run_file_changes',tree)

    run=read(CAMP/'run-result.json') if (CAMP/'run-result.json').exists() else None
    worker=read(CAMP/'worker-result.json') if (CAMP/'worker-result.json').exists() else None
    terminal=read(CAMP/'finalization-result.json') if (CAMP/'finalization-result.json').exists() else None
    result['retained_campaign_results']=dict(run_result=run,worker_result=worker,finalization_result=terminal)
    def terminal_binding():
        require(run is not None and worker is not None and terminal is not None,'Required campaign receipts absent')
        require(run.get('worker_result')==worker,'Supervisor embedded worker receipt mismatch')
        require(run['status']==worker['status']==terminal['status'],'Terminal/run/worker status mismatch')
        manifest=read(CAMP/'artifact-manifest.json')
        actual={str(p.relative_to(CAMP)):sha(p) for p in sorted(CAMP.rglob('*'))
                if p.is_file() and p.name not in ('artifact-manifest.json','finalization-result.json')}
        require(actual==manifest,'Retained campaign artifact manifest mismatch or unlisted payload')
        require(terminal['artifact_manifest_sha256']==sha(CAMP/'artifact-manifest.json')
                and terminal['run_result_sha256']==sha(CAMP/'run-result.json'), 'Authoritative terminal hash binding mismatch')
        result['full_campaign_artifact_hashes']={**actual,'artifact-manifest.json':sha(CAMP/'artifact-manifest.json'),
                                                'finalization-result.json':sha(CAMP/'finalization-result.json')}
        return dict(status=terminal['status'],manifest_entries=len(actual),all_hashes_bound=True)
    check('authoritative_terminal_and_manifest_binding',terminal_binding)

    def deadline_exit():
        require(exit_receipt['actual_command_launch_count']==1,'Launch count must be exactly one')
        require(exit_receipt['observed_exit_code']==0,'Actual supervisor exit was nonzero')
        require(not exit_receipt['errors'] and not exit_receipt['cleanup_actions'],'Outer observer failure or deadline cleanup')
        require(terminal['status']==run['status']==worker['status']=='complete','Campaign not complete')
        elapsed=exit_receipt['actual_outer_wall_through_exit_seconds']
        require(elapsed<=600,'Observed wall through process exit exceeds original experiment deadline')
        return dict(observed_exit_code=0,actual_outer_wall_through_exit_seconds=elapsed,
                    internal_terminal_prewrite_lower_bound_seconds=terminal['actual_total_wall_seconds'],
                    timing_caveat='Outer wall begins before Popen and ends after wait; internal monotonic origin differs across Python runtimes. Internal terminal timing excludes its write and process exit.')
    check('actual_exit_and_original_600_second_deadline',deadline_exit)

    evaluations={}
    episode_records={}
    def rows_and_controls():
        events=list(records(CAMP/'evaluations.jsonl'))
        ordered=[x for x in events if x.get('event')=='evaluation_complete']
        require([x['evaluation'] for x in ordered]==protocol['order'],'Evaluation order/matrix differs')
        for event in ordered:
            rows=event['rows']
            require(len(rows)==64 and {x['seed'] for x in rows}==SEEDS,'Incomplete evaluation seed denominator')
            for row in rows:
                validate_row(row)
            evaluations[event['evaluation']]={r['seed']:r for r in rows}
        for episode in records(CAMP/'episodes.jsonl'):
            name=matrix_name(episode)
            row=episode['row']
            validate_row(row)
            key=(name,row['seed'])
            require(key not in episode_records,'Duplicate episode')
            require(evaluations[name][row['seed']]==row,'Episode/evaluation row mismatch')
            require(episode['context']['context_presence_only'] is True
                    and episode['context']['death_cause']=='UNKNOWN','Cause/context claim changed')
            episode_records[key]=episode
        require(len(episode_records)==768 and len(evaluations)==12,'Expected 768 episodes and 12 evaluations')
        for item in protocol['checkpoints']:
            if item['control']:
                saved={x['seed']:x for x in records(ROOT/item['control'])}
                require(evaluations[item['label']+'_argmax']==saved,'Historical nine-field control mismatch')
        controls=[x for x in events if x.get('event')=='historical_control']
        require(len(controls)==2 and {x['checkpoint'] for x in controls}=={'entry','phase96'}
                and all(x['matched'] is True and x['seeds']==64 and set(x['fields'])==ROW_KEYS for x in controls),
                'Historical control events mismatch')
        require(run['episodes_completed']==worker['episodes_completed']==768
                and run['evaluations_completed']==worker['evaluations_completed']==12,'Receipt counters differ')
        require(run['control_matches']==worker['control_matches'] and set(run['control_matches'])=={'entry','phase96'}
                and all(x['matched'] for x in run['control_matches'].values()),'Receipt control counters differ')
        return dict(episodes=768,evaluations=12,historical_control_matches=2,fields_per_control=9,
                    controller_seeds=[64001,64002,64003],game_seeds=64,
                    evaluation_means={n:{m:sum(r[m] for r in rows.values())/64 for m in ('score','alive_frames')}
                                      for n,rows in evaluations.items()})
    check('complete_finite_rows_assignments_and_exact_controls',rows_and_controls)

    def decisions():
        counts=collections.Counter()
        count=0
        for row in records(CAMP/'decisions.jsonl'):
            name=matrix_name(row)
            key=(name,row['episode_seed'])
            require(key in episode_records and row['episode_seed']==3489660928+row['episode_index'],
                    'Decision has unexpected episode/seed')
            require(row['decision_index']==counts[key],'Decision sequence mismatch')
            counts[key]+=1
            count+=1
            probabilities=row['probabilities9']
            require(len(probabilities)==9 and all(0<=p<=1 for p in probabilities)
                    and math.isclose(sum(probabilities),1,abs_tol=2e-6), 'Invalid action probabilities')
            chosen,argmax=row['chosen_action'],row['argmax_action']
            require(type(chosen) is int and type(argmax) is int and 0<=chosen<9 and 0<=argmax<9,
                    'Invalid action index')
            require(probabilities[argmax]>=max(probabilities)-2e-7,'Logged argmax differs')
            require(row['mode']!='argmax' or chosen==argmax,'Argmax selected a different action')
            require(0<=row['gameplay_frames_before_step']<18000
                    and 0<=row['entropy']<=math.log(9)+1e-6,'Invalid decision diagnostics')
        require(all(counts[k]==v['decisions'] for k,v in episode_records.items()),'Episode decision counts differ')
        require(count==worker['decisions_logged']==run['decisions_logged'],'Decision receipt total differs')
        return dict(decisions=count,complete_finite_probabilities=True,episode_sequences_verified=True)
    check('decision_trace_finite_and_complete',decisions)

    def statistics():
        stats=worker['statistics']
        require(set(stats)=={'entry','phase96','phase104'},'Three statistics objects required')
        summary={}
        for label,s in stats.items():
            require(s['role']==('primary' if label=='phase104' else 'secondary')
                    and s['seed_clusters']==64 and s['sampled_episodes']==192 and s['argmax_episodes']==64
                    and s['replicates_per_seed']==3 and s['bootstrap_draws']==10000
                    and s['bootstrap_seed']==764002 and s['shared_resampled_indices'] is True,
                    'Paired statistics protocol mismatch')
            require(len(s['paired_clusters'])==64 and {x['seed'] for x in s['paired_clusters']}==SEEDS,
                    'Paired seed clusters incomplete')
            for cluster in s['paired_clusters']:
                seed=cluster['seed']
                base=[float(evaluations[label+'_argmax'][seed][m]) for m in ('alive_frames','score')]
                sampled=[sum(evaluations[label+'_sample'+str(c)][seed][m] for c in (64001,64002,64003))/3
                         for m in ('alive_frames','score')]
                require(base==cluster['argmax_alive_score'] and sampled==cluster['sampled_replicate_mean_alive_score']
                        and [a-b for a,b in zip(sampled,base)]==cluster['paired_delta_alive_score'],
                        'Paired cluster differs from raw rows')
            for m,margin in (('alive_frames',100),('score',1)):
                v=s['metrics'][m]
                b=sum(r[m] for r in evaluations[label+'_argmax'].values())/64
                a=sum(sum(evaluations[label+'_sample'+str(c)][seed][m] for c in (64001,64002,64003))/3
                      for seed in SEEDS)/64
                require(math.isclose(v['argmax_mean'],b,abs_tol=1e-10)
                        and math.isclose(v['sampled_mean'],a,abs_tol=1e-10)
                        and math.isclose(v['paired_mean_delta'],a-b,abs_tol=1e-10)
                        and v['practical_margin']==margin and len(v['ci95'])==2
                        and v['ci95'][0]<=v['ci95'][1], 'Metric mean/margin/CI mismatch')
            values=s['metrics'].values()
            if all(v['ci95'][0]>-v['practical_margin'] and v['ci95'][1]<v['practical_margin'] for v in values):
                decision='practical_similarity'
            elif all(v['ci95'][0]>v['practical_margin'] for v in values):
                decision='meaningful_stochastic_advantage'
            elif all(v['ci95'][1]<-v['practical_margin'] for v in values):
                decision='meaningful_argmax_advantage'
            else:
                decision='mixed_or_inconclusive'
            require(s['decision']==decision,'Decision differs from fixed CI/margin rule')
            summary[label]={k:v for k,v in s.items() if k!='paired_clusters'}
        finite(stats)
        result['per_checkpoint_statistics']=summary
        return summary
    check('paired_cluster_statistics_means_intervals_margins_decisions',statistics)

    def resources():
        raw={}
        for name in ('supervisor','worker'):
            rows=list(records(CAMP/(name+'-guard.jsonl')))
            require(rows,'Guard raw log empty')
            value={k:max(x[k] for x in rows) for k in ('sampled_rss_bytes','self_peak_rss_bytes','mps_driver_bytes','sample_gap_seconds')}
            value['samples']=len(rows)
            raw[name]=value
            receipt=run['supervisor_resources'] if name=='supervisor' else worker
            for key,field in (('sampled_rss_bytes','maximum_sampled_rss_bytes'),('self_peak_rss_bytes','maximum_self_peak_rss_bytes'),
                              ('mps_driver_bytes','maximum_mps_driver_bytes'),('sample_gap_seconds','maximum_sample_gap_seconds')):
                require(value[key]==receipt[field], 'Raw guard maximum differs: '+name+'/'+field)
            require(max(value['sampled_rss_bytes'],value['self_peak_rss_bytes'])<=6442450944
                    and value['mps_driver_bytes']<=6442450944 and value['sample_gap_seconds']<=0.5,
                    'Resource/cadence guard exceeded')
        observed=collections.defaultdict(int)
        rows=list(records(OUT/'outer-resources.jsonl'))
        for sample in rows:
            for process in sample['owned_processes']:
                observed[str(process['pid'])]=max(observed[str(process['pid'])],process['rss_bytes'])
        result['resources']=dict(raw_guard_maxima=raw,outer_observed_rss_maxima_by_pid=dict(observed),
                                 outer_samples=len(rows),outer_mps_probe=False,
                                 rss_limit_bytes=6442450944,mps_driver_limit_bytes=6442450944,
                                 semantics='Sampled RSS and MPS driver allocation plus self peak RSS; no OS hard memory cap.')
        return result['resources']
    check('raw_guard_and_separate_outer_resource_maxima',resources)

    def prohibitions():
        for receipt in (run,worker):
            require(receipt['gradient_updates']==0 and receipt['optimizer_instantiations']==0
                    and receipt['checkpoint_writes']==0 and receipt['gradients_observed'] is False
                    and receipt['training_eligibility_changed'] is False and receipt['B_opened'] is False
                    and receipt['E_opened'] is False and receipt['automatic_retries']==0,
                    'Forbidden work reported')
        require(not list(CAMP.rglob('*.pt')),'Unexpected campaign checkpoint output')
        return dict(runner_and_worker_report_zero_optimizer_gradient_checkpoint_writes=True,
                    pinned_source_and_checkpoint_hashes_unchanged=checks['all_pinned_and_protected_bytes_unchanged']['passed'],
                    ledger_eligibility_and_limits_unchanged=checks['all_pinned_and_protected_bytes_unchanged']['passed'],
                    retained_logs_use_only_D_cohort=True, no_extra_child_tasks=True,
                    scope='Reviewed inference-only source, runtime receipts, raw trace/row checks and before/after hashes. No independent OS syscall audit or instrumented optimizer interceptor.')
    check('no_training_checkpoint_eligibility_B_E_or_limit_changes',prohibitions)
    result['provenance_limits']=[
        'Diagnostic inference only; failed-run checkpoint weights retain all prior training/transition ineligibility.',
        'Phase104 is primary; entry and phase96 are secondary. No qualification or automatic training decision.',
        'Pattern observations describe context only; every retained death cause remains UNKNOWN.',
        'Bootstrap CI values are retained frozen-runner outputs. Postflight verified finite intervals, complete 64 paired clusters, raw means, margins and decisions without another numerical bootstrap or model call.',
        'Outer sampled RSS is separate from raw internal RSS/self-peak/MPS maxima. Outer observer did not measure MPS directly.',
        'All outer hashes are taken after the execution wrapper exited and its redirected stdout/stderr closed.',
        'No campaign retry, fallback, repair, checkpoint re-evaluation, source modification, scheduler restart, publication, or parent lease edit occurred.'
    ]
    result['status']='complete' if all(x['passed'] for x in checks.values()) and not result['errors'] else 'failed'
    result['completed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    result['outer_hashes_before_result']={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()}
    save('result.json',result)
    manifest={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()}
    save('artifact-manifest.json',manifest)
    print(json.dumps(dict(status=result['status'],actual_command_launch_count=result['actual_command_launch_count'],
                          observed_exit_code=exit_receipt.get('observed_exit_code'),
                          actual_outer_wall_through_exit_seconds=exit_receipt.get('actual_outer_wall_through_exit_seconds'),
                          checks={k:v['passed'] for k,v in checks.items()},errors=result['errors'],
                          result_sha256=sha(OUT/'result.json'),outer_manifest_sha256=sha(OUT/'artifact-manifest.json'),
                          statistics=result.get('per_checkpoint_statistics'),resources=result.get('resources')),indent=2))

if __name__=='__main__':
    main()
