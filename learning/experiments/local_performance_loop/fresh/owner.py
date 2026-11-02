"""Single admission and autonomous strict audit before exact release."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import resource
import signal
import shutil
import subprocess
import time
import traceback
import common as c
from lifecycle import run_child,group_members
from policy import advance,summarize
from analysis import compare


def audit_child(directory,reg):
    launch=c.read(directory/'launch.json');exit=c.read(directory/'exit.json')
    c.need(exit['raw_exit_code']==exit['observed_exit_code']==0 and exit['directly_reaped'] and exit['group_absent']
       and exit['pid']==launch['pid'] and exit['reason'] is None and exit['peak_group_RSS_bytes']<reg['rss_bytes']
       and not group_members(exit['pgid']),'Direct reap/group/resource proof differs')


def play_rows(path,seeds):
    rows=[json.loads(s) for s in Path(path).read_text().splitlines()]
    c.need(sorted(r['seed'] for r in rows)==seeds,'Full fixed development coverage differs')
    for r in rows:
        n=r['gameplay_frames'];term=r['terminated'];trunc=r['truncated']
        c.need(type(n) is int and 1<=n<=18000 and type(term) is bool and type(trunc) is bool and term!=trunc
           and r['alive_frames']==n-int(term) and r['decisions']==n and r['startup_frames']==13
           and r['condition']=='clean' and (not trunc or n==18000),'Native play receipt identity differs')
    return rows


def strict_audit(reg,digest,start):
    out=c.RUN/'output';worker=out/'worker';c.check_lease(reg);c.verify_pins(reg);c.verify_runtime_members(reg)
    c.need(not any('failure' in p.name or '.partial' in p.name for p in out.rglob('*')),'Failure/partial forbids acceptance')
    c.need(not list(Path(reg['cache']).rglob('*')),'Cache changed')
    dispatch=c.read(out/'dispatch.json');c.need(dispatch['registration_sha256']==digest and dispatch['review_sha256']==c.review_gate(reg,digest),'Dispatch binding differs')
    for directory in [worker,out/'supervisor']:audit_child(directory,reg)
    claim=c.read(worker/'worker.claimed');c.need(claim['pid']==c.read(worker/'launch.json')['pid'] and claim['registration_sha256']==digest,'Worker identity differs')
    helper=c.read(out/'caffeinate-exit.json');c.need(helper['pid']==c.read(out/'caffeinate-launch.json')['pid'] and helper['directly_reaped'] and helper['group_absent'] and not group_members(helper['pgid']),'Sleep helper cleanup differs')
    supervisor=c.read(out/'supervisor-result.json')
    for key,file in [('worker_exit_sha256','worker/exit.json'),('caffeinate_exit_sha256','caffeinate-exit.json'),('power_sha256','power.jsonl')]:c.need(supervisor[key]==c.sha(out/file),'Supervisor receipt differs')
    result=c.read(worker/'result.json');c.need(result['status']=='complete_performance_loop' and result['registration_sha256']==digest and not result['promoted'] and not result['held_confirmation_opened'],'Worker terminal status differs')
    c.need(result['resources']['peak_rss_bytes']<reg['rss_bytes'] and result['resources']['peak_mps_driver_bytes']<reg['mps_bytes'],'Resources exceeded')
    baseline_receipt=c.read(worker/'baseline.json');baseline=baseline_receipt['metrics']
    for label,expected_fp in [('420',reg['model_fingerprint']),('control12',reg['warmstart']['model_fingerprint'])]:
        directory=worker/('baseline-'+label);rows=play_rows(directory/'episodes.jsonl',reg['evaluation_seeds']);ev=c.read(directory/'result.json')
        expected_metrics=baseline if label=='control12' else baseline_receipt['context420']
        c.need(ev['metrics']==summarize(rows)==expected_metrics and ev['model_fingerprint']==expected_fp
               and ev['episodes_sha256']==c.sha(directory/'episodes.jsonl')
               and baseline_receipt['baseline_results'][label]==c.sha(directory/'result.json'),'Same-machine baseline identity/hash differs')
    c.need(baseline_receipt['cached_games']==1024 and baseline_receipt['new_games']==0
           and c.sha(worker/'baseline.json')==result['baseline_sha256'],'Only exact same-M1 baseline cache reuse')
    import numpy as np
    control12_rows=play_rows(worker/'baseline-control12/episodes.jsonl',reg['evaluation_seeds'])
    c.need(c.read(worker/'baseline-paired-uncertainty.json')==compare(control12_rows,play_rows(worker/'baseline-420/episodes.jsonl',reg['evaluation_seeds']),np)
        and baseline_receipt['paired_uncertainty_sha256']==c.sha(worker/'baseline-paired-uncertainty.json'),'Baseline paired uncertainty differs')
    reference=baseline;arms=[]
    c.need([r['arm'] for r in result['arms']]==reg['job_order'],'Exactly one control continuation required')
    for terminal in result['arms']:
        arm=terminal['arm'];directory=worker/arm
        c.need(c.read(directory/'result.json')==terminal,'Arm result differs')
        for name,h in terminal['artifacts'].items():c.need(c.sha(directory/name)==h,'Arm journal hash differs '+name)
        migration=c.read(directory/'migration.json');prefix=c.read(directory/'prefix-qualification.json')
        c.need(migration['optimizer_unchanged'] and migration['source_rng_restored']
            and migration['source_model_fingerprint']==reg['warmstart']['model_fingerprint']
            and migration['source_adam_fingerprint']==reg['warmstart']['adam_fingerprint']
            and migration['actual_LR_before']==3e-5 and migration['actual_LR_after']==3e-5,'Warm-start migration differs')
        c.need(prefix['status']=='accepted_counted_M1_training_prefix' and prefix['counted_updates']==2
            and prefix['counted_frames']==131072 and prefix['passive_GAE_and_return_identity_checks']==[True,True]
            and prefix['migration_sha256']==c.sha(directory/'migration.json')
            and prefix['estimate_is_not_admission_or_stopping_rule'],'Real counted M1 qualification missing')
        rows=[json.loads(s) for s in (directory/'updates.jsonl').read_text().splitlines()]
        counts=c.validate_telemetry(rows,dict(reg,updates=terminal['updates']),dict(id=arm,arm=arm))
        c.need(all(row['entropy_coefficient'] == reg['ppo']['ent_coef'] for row in rows),
               'Actual entropy coefficient differs from the registered objective')
        c.need(terminal['training_exposure_role'] == reg['fresh_stream']['role']
               and terminal['objective_delta'] == reg.get('objective_delta'), 'Training exposure/objective receipt differs')
        c.need(counts==dict(updates=terminal['updates'],frames=terminal['actual_gameplay_frames'],Adam_steps=terminal['Adam_steps']),'Actual completed training counts differ')
        frames=0;steps=0;initials=0
        with (directory/'native-events.jsonl').open() as f:
            for line in f:
                event=json.loads(line)
                if event['kind']=='returned_step_cost':
                    c.need(len(event['elapsed_raw_frames'])==64 and set(event['elapsed_raw_frames'])=={1},'Training native K1 vector differs')
                    frames+=sum(event['elapsed_raw_frames']);steps+=1
                if event['kind']=='initial_assignments':initials+=1
        c.need(frames==counts['frames'] and steps==terminal['updates']*1024 and initials==len(terminal['simulator_segments']),'Native/complete-update coverage differs')
        with (directory/'native-events.jsonl').open() as stream:
            fresh_counts=c.audit_assignments((json.loads(line) for line in stream),c.specification(reg),reg['fresh_stream']['bank_episodes_per_slot'])
        c.need(fresh_counts['simulator_segments']==initials,'Fresh assignment coverage differs')
        activity=[json.loads(s) for s in (directory/'activity.jsonl').read_text().splitlines()]
        c.need([r['update'] for r in activity]==list(range(1,terminal['updates']+1)),'Branch diagnostic coverage differs')
        if arm=='rays':c.need(all('ray_gate' in r and 'branch_changed_from_initial' in r and 'branch_Adam_step_min' in r for r in activity),'Ray activity missing')
        policy_state={'best':dict(update=0,**baseline)};evaluations=[]
        decisions=[json.loads(s) for s in (directory/'decisions.jsonl').read_text().splitlines()]
        expected_updates=list(range(12,terminal['updates']+1,12))
        c.need([d['update'] for d in decisions]==expected_updates and terminal['updates']<=reg['max_updates'],'Decision cadence differs')
        checkpoints=terminal['checkpoints'];c.need([x['update'] for x in checkpoints]==[0]+expected_updates,'Checkpoint coverage differs')
        for meta in checkpoints:
            path=Path(meta['path']);c.need(path.parent.resolve()==(directory/'checkpoints').resolve() and c.sha(path)==meta['sha256'] and path.stat().st_mode&0o222==0,'Learner+Adam checkpoint path/hash/immutability differs')
            c.need(c.read(path.with_suffix('.json'))==meta,'Checkpoint metadata differs')
        for index,d in enumerate(decisions):
            u=d['update'];evdir=directory/'evaluations'/f'{u:06d}';ev=c.read(evdir/'result.json');data=play_rows(evdir/'episodes.jsonl',reg['evaluation_seeds'])
            c.need(d['paired_uncertainty_sha256']==c.sha(evdir/'paired-vs-control12.json')
                and c.read(evdir/'paired-vs-control12.json')==compare(data,control12_rows,np),'Paired uncertainty hash/recalculation differs')
            c.need(ev['metrics']==summarize(data) and ev['episodes_sha256']==c.sha(evdir/'episodes.jsonl') and d['evaluation_result_sha256']==c.sha(evdir/'result.json'),'Play metrics/hash differs')
            meta=checkpoints[index+1];c.need(meta['performance']==ev['metrics'] and meta['model_fingerprint']==ev['model_fingerprint'] and d['checkpoint_sha256']==meta['sha256'],'Play-to-learner binding differs')
            policy_state,replayed=advance(policy_state,ev['metrics'],u,reference,reg['policy'])
            c.need(all(d[k]==v for k,v in replayed.items()),'Prospective selection/continuation policy differs')
            c.need(d['continue_training']==(index<len(decisions)-1),'Post-stop work/missing continuation')
            evaluations.append(dict(update=u,metrics=ev['metrics'],evaluation_sha256=c.sha(evdir/'result.json')))
        c.need(decisions and decisions[-1]['stop_reason']==terminal['stop_reason'],'Terminal performance disposition differs')
        best=next(m for m in checkpoints if m['update']==policy_state['best']['update']);c.need(best==terminal['best'],'Best checkpoint preservation differs')
        arms.append(dict(arm=arm,counts=counts,fresh_seed_counts=fresh_counts,
            training_exposure_role=reg['fresh_stream']['role'],objective_delta=reg.get('objective_delta'),
            stop_reason=terminal['stop_reason'],best=best,evaluations=evaluations))
    return dict(status='accepted_local_control_continuation',record=reg['record'],registration_sha256=digest,baseline=baseline,baseline420=baseline_receipt['context420'],arms=arms,
        worker_result_sha256=c.sha(worker/'result.json'),worker_exit_sha256=c.sha(worker/'exit.json'),supervisor_exit_sha256=c.sha(out/'supervisor/exit.json'),
        caffeinate_exit_sha256=c.sha(out/'caffeinate-exit.json'),resources=result['resources'],elapsed_seconds=time.monotonic()-start,
        development_selection=True,public_promotion=False,held_large_evaluation_opened=False,all_owned_accelerator_groups_absent=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--registration',required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--check-only',action='store_true');p.add_argument('--accept-terminal',action='store_true');a=p.parse_args()
    def cancel(*_):raise c.CampaignStop('User cancelled owner')
    signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
    reg=c.load_registration(a.registration,a.sha256);review=c.review_gate(reg,a.sha256);c.verify_environment(reg)
    if a.check_only:print('Source/config/review/interpreter verified; no native work.');return 0
    out=c.RUN/'output'
    if a.accept_terminal:
        c.need(not (out/'parent-terminal-audit.json').exists() and not (out/'lease-release.json').exists(),'Never overwrite or repeat terminal acceptance')
        root=c.read(out/'owner/exit.json');audit_child(out/'owner',reg)
        proof=c.read(out/'coordinator-exit.json')
        c.need(proof['directly_reaped'] and proof['local_groups_absent'] and proof['observed_exit_code']==0
            and proof['owner_exit_sha256']==c.sha(out/'owner/exit.json'),'Coordinator direct owner reap proof missing')
        audit=strict_audit(reg,a.sha256,c.read(out/'dispatch.json')['started_monotonic'])
        c.need(c.read(out/'pending-terminal-audit.json')['arms']==audit['arms'],'Pending terminal result drift')
        path=Path(reg['state_path'])
        with (path.parent/'horizon-ledger.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);state=c.read(path);c.machine_state(reg,state)
            c.need(state['active_long_campaign']==reg['expected_lease'],'Exact terminal lease lost')
            audit.update(owner_exit_sha256=c.sha(out/'owner/exit.json'),coordinator_exit_sha256=c.sha(out/'coordinator-exit.json'))
            h=c.save(out/'parent-terminal-audit.json',audit)
            state['active_long_campaign']=None;tmp=path.parent/('.continuation-release-'+str(os.getpid()))
            with tmp.open('x') as f:json.dump(state,f,sort_keys=True);f.flush();os.fsync(f.fileno())
            os.replace(tmp,path);c.sync_directory(path.parent)
            c.save(out/'lease-release.json',dict(accepted_audit_sha256=h,machine=reg['machine'],previous_lease=reg['expected_lease'],lease_value_after_release=None))
        print(c.canonical(audit).decode(),flush=True);return 0
    processes=subprocess.check_output(['/bin/ps','-axo','pid=,command='],text=True)
    conflicts=[line for line in processes.splitlines() if reg['project_root'] in line and any(x in line for x in ['worker.py','run_once.py','train_teacher','evaluate_worker.py','supervisor.py']) and ' -c ' not in line]
    c.need(not conflicts,'Another project native worker present')
    pressure=subprocess.check_output(['/usr/bin/memory_pressure','-Q'],text=True)
    import re
    percent=re.search(r'System-wide memory free percentage:\s*(\d+)%',pressure)
    c.need(percent is not None and int(percent.group(1))>=20,'Host headroom unavailable at admission')
    start=time.monotonic();c.save(out/'owner.claimed',dict(pid=os.getpid(),pgid=os.getpgrp(),registration_sha256=a.sha256))
    try:
        c.need(shutil.disk_usage(c.RUN).free>reg['minimum_free_disk_bytes'],'Disk reserve unavailable')
        c.cas_ledger(reg,None,reg['expected_lease'])
        c.save(out/'dispatch.json',dict(status='dispatched_once',registration_sha256=a.sha256,review_sha256=review,
            expected_lease=reg['expected_lease'],started_monotonic=start,protected_processes=c.protected_identities(),memory_pressure=pressure))
        def monitor(members):
            c.check_lease(reg);c.need(sum(x['rss_bytes'] for x in members)+int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)+c.process_rss(os.getppid())<reg['rss_bytes'],'Owner/supervisor/coordinator RSS ceiling')
        run_child([reg['interpreter'],'-B',str(c.CODE/'supervisor.py'),'--registration',a.registration,'--sha256',a.sha256],
            out/'supervisor',dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=reg['cache'],PYTORCH_ENABLE_MPS_FALLBACK='0'),monitor,None,cleanup_seconds=60)
        audit=strict_audit(reg,a.sha256,start);audit['status']='training_complete_pending_coordinator_acceptance'
        c.save(out/'pending-terminal-audit.json',audit)
        print('Worker/supervisor complete; exact lease remains held pending coordinator direct reap and acceptance.',flush=True);return 0
    except BaseException as error:
        c.save(out/'owner-first-failure.json',dict(status='blocked_no_retry_preserve_exact_lease',error=repr(error),traceback=traceback.format_exc()));raise


if __name__=='__main__':raise SystemExit(main())
