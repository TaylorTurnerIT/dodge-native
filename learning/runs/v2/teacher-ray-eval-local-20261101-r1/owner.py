"""Reviewed exact-once local admission, parent audit, then exact release."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import time
import traceback
import common as c
from lifecycle import run_child,group_members
from analysis import analyze,validate_rows,forecast


def audit_child(directory,reg):
    launch=c.read(directory/'launch.json');exit=c.read(directory/'exit.json')
    c.need(exit['raw_exit_code']==exit['observed_exit_code']==0 and exit['directly_reaped'] and exit['group_absent']
           and exit['peak_group_RSS_bytes']<reg['rss_bytes'] and exit['reason'] is None
           and exit['pid']==launch['pid'] and not group_members(exit['pgid']),'Direct child reap/group absence required')


def strict_audit(reg,digest,start):
    out=c.HERE/'output';worker=out/'worker'
    c.need(time.monotonic()-start<reg['total_seconds'],'Total evaluation/receipt deadline')
    c.verify_pins(reg);c.verify_runtime_members(reg)
    c.need(not list(Path(reg['cache']).rglob('*')),'Cache changed')
    c.need(not any('failure' in p.name or '.partial' in p.name for p in out.rglob('*')),'First failure/partial blocks acceptance')
    dispatch=c.read(out/'dispatch.json');c.need(dispatch['registration_sha256']==digest and dispatch['review_sha256']==c.review_gate(reg,digest),'Dispatch/review differs')
    for directory in [worker,out/'supervisor']:audit_child(directory,reg)
    claim=c.read(worker/'worker.claimed');c.need(claim['pid']==c.read(worker/'launch.json')['pid'] and claim['registration_sha256']==digest,'Worker claim differs')
    helper=c.read(out/'caffeinate-exit.json');helper_launch=c.read(out/'caffeinate-launch.json')
    c.need(helper['pid']==helper_launch['pid'] and helper['directly_reaped'] and helper['group_absent'] and not group_members(helper['pgid']),'Sleep helper cleanup differs')
    supervisor=c.read(out/'supervisor-result.json')
    c.need(supervisor['status']=='worker_complete_pending_parent_acceptance' and supervisor['registration_sha256']==digest,'Supervisor result differs')
    for key,file in [('worker_exit_sha256','worker/exit.json'),('caffeinate_exit_sha256','caffeinate-exit.json'),('power_sha256','power.jsonl')]:
        c.need(supervisor[key]==c.sha(out/file),'Supervisor artifact differs')
    result=c.read(worker/'result.json')
    c.need(result['status']=='complete_fixed_endpoint_development_evaluation' and result['registration_sha256']==digest
           and not result['training'] and not result['promoted'] and result['games']==reg['games'],'Worker result differs')
    for name,hash_ in result['artifacts'].items():c.need(c.sha(worker/name)==hash_,'Worker artifact differs '+name)
    c.need(set(result['artifacts'])=={'episodes.jsonl','batches.jsonl','analysis.json','prefix-qualification.json','final-forecast.json','device.json'},'Artifact inventory differs')
    rows=[json.loads(line) for line in (worker/'episodes.jsonl').read_text().splitlines()]
    frames=validate_rows(rows,reg)
    c.need(frames==result['actual_frames'] and result['actual_startup_frames']==13*len(rows),'Actual frame totals differ')
    def audit_guard():c.need(time.monotonic()-start<reg['total_seconds'],'Audit receipt deadline')
    analysis=analyze(rows,reg,audit_guard)
    c.need(analysis==c.read(worker/'analysis.json'),'Independent analysis recomputation differs')
    batches=[json.loads(line) for line in (worker/'batches.jsonl').read_text().splitlines()]
    c.need(len(batches)==10 and [(b['offset'],b['model']) for b in batches]==[(o,m['name']) for o in (0,64) for m in reg['models']],'Declared execution order differs')
    c.need(sum(b['frames'] for b in batches)==frames and all(b['games']==64 for b in batches),'Counted batch totals differ')
    for i,b in enumerate(batches,1):
        subset=[r for r in rows if r['model']==b['model'] and r['seed'] in reg['seeds'][b['offset']:b['offset']+64]]
        c.need(len(subset)==64 and sum(r['gameplay_frames'] for r in subset)==b['frames'] and b['cumulative_games']==i*64,'Batch/episode coverage differs')
    prefix=c.read(worker/'prefix-qualification.json')
    # Forecast elapsed includes the small loop boundary after batch emission.
    c.need(prefix['status']=='accepted_counted_prefix' and prefix['batches']==batches[:5] and prefix['counted_games']==320
           and prefix['actual_frames']==sum(b['frames'] for b in batches[:5]) and prefix['device']=='mps'
           and prefix['forecast_seconds']==forecast(prefix['elapsed_seconds'],batches[:5],5,240)
           and prefix['forecast_seconds']<reg['work_seconds'] and prefix['margin_factor']==1.2
           and prefix['remaining_batches']==5 and prefix['IO_analysis_reserve_seconds']==240,'Counted qualification differs')
    final=c.read(worker/'final-forecast.json')
    c.need(final['status']=='accepted_counted_prefix' and final['batches']==batches and final['counted_games']==640
           and final['actual_frames']==frames and final['remaining_batches']==0
           and final['forecast_seconds']==forecast(final['elapsed_seconds'],batches,0,240)
           and final['forecast_seconds']<reg['work_seconds'],'Final forecast differs')
    power=[json.loads(line) for line in (out/'power.jsonl').read_text().splitlines()]
    c.need(power and all(r['kind']=='passive_power_observation' and r['sleep']['helper_pid']==helper['pid'] for r in power),'Owned sleep telemetry missing')
    c.need(result['elapsed_seconds']<reg['work_seconds'] and result['resources']['peak_rss_bytes']<reg['rss_bytes']
           and result['resources']['peak_mps_driver_bytes']<reg['mps_bytes'],'Resource/work limits differ')
    device=c.read(worker/'device.json')
    c.need(device['device']=='mps' and not device['gradients_enabled'] and not device['optimizer_constructed'],'Fixed MPS evaluation proof missing')
    c.need(time.monotonic()-start<reg['total_seconds'],'Receipt deadline')
    return dict(status='accepted_fixed_endpoint_development_evaluation',record=reg['record'],registration_sha256=digest,
        games=len(rows),actual_gameplay_frames=frames,actual_startup_frames=13*len(rows),
        analysis_sha256=c.sha(worker/'analysis.json'),episodes_sha256=c.sha(worker/'episodes.jsonl'),
        worker_result_sha256=c.sha(worker/'result.json'),worker_exit_sha256=c.sha(worker/'exit.json'),
        supervisor_exit_sha256=c.sha(out/'supervisor/exit.json'),caffeinate_exit_sha256=c.sha(out/'caffeinate-exit.json'),
        prefix_sha256=c.sha(worker/'prefix-qualification.json'),all_owned_accelerator_groups_absent=True,
        elapsed_seconds=time.monotonic()-start,training=False,promoted=False)


def main():
    p=argparse.ArgumentParser();p.add_argument('--registration',required=True);p.add_argument('--sha256',required=True);p.add_argument('--check-only',action='store_true');args=p.parse_args()
    reg=c.load_registration(args.registration,args.sha256);review=c.review_gate(reg,args.sha256)
    if args.check_only:
        print('Exact source/registration/review CPU gate passed; no native constructor or admission.');return 0
    processes=subprocess.check_output(['/bin/ps','-axo','pid=,command='],text=True)
    conflicts=[line for line in processes.splitlines() if reg['project_root'] in line and any(x in line for x in ['worker.py','run_once.py','train_teacher','evaluate_worker.py','supervisor.py']) and ' -c ' not in line]
    c.need(not conflicts,'Existing project native worker conflicts with admission')
    out=c.HERE/'output';start=time.monotonic()
    c.save(out/'owner.claimed',dict(pid=os.getpid(),registration_sha256=args.sha256,started_monotonic=start))
    try:
        c.need(shutil.disk_usage(c.HERE).free>reg['minimum_free_disk_bytes'],'Local disk reserve unavailable')
        # The shared ledger, not idle hardware, admits this one accelerator run.
        c.cas_ledger(reg,None,reg['expected_lease'])
        c.save(out/'dispatch.json',dict(status='dispatched_once',stage='fixed_endpoint_evaluation',record=reg['record'],
            registration_sha256=args.sha256,review_sha256=review,authority_sha256=c.sha(c.HERE/'authority.json'),
            expected_lease=reg['expected_lease'],started_monotonic=start,owner_pid=os.getpid()))
        environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=reg['cache'])
        def monitor(members):
            c.check_lease(reg)
            c.need(time.monotonic()-start<reg['total_seconds']-70,'Supervisor/receipt hard deadline')
            c.need(sum(m['rss_bytes'] for m in members)+int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)<reg['rss_bytes'],'Owner/supervisor RSS ceiling')
        run_child([reg['interpreter'],'-B',str(c.HERE/'supervisor.py'),'--registration',args.registration,'--sha256',args.sha256],
            out/'supervisor',environment,monitor,reg['total_seconds']-70,cleanup_seconds=60)
        audit=strict_audit(reg,args.sha256,start)
        # Accepted audit is durable BEFORE exact lease-to-None, under one lock.
        path=Path(reg['state_path'])
        with (path.parent/'horizon-ledger.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);state=c.read(path)
            c.need(state['active_long_campaign']==reg['expected_lease'],'Exact terminal lease differs')
            auditsha=c.save(out/'parent-terminal-audit.json',audit)
            state['active_long_campaign']=None;tmp=path.parent/('.eval068-release-'+str(os.getpid()))
            with tmp.open('x') as f:
                json.dump(state,f,sort_keys=True);f.flush();os.fsync(f.fileno())
            os.replace(tmp,path);c.sync_directory(path.parent)
            c.save(out/'lease-release.json',dict(record=reg['record'],accepted_audit_sha256=auditsha,
                previous_lease=reg['expected_lease'],lease_value_after_release=None))
        print(c.canonical(audit).decode(),flush=True);return 0
    except BaseException as error:
        c.save(out/'owner-first-failure.json',dict(status='blocked_no_retry_preserve_lease_and_partials',error=repr(error),traceback=traceback.format_exc(),elapsed_seconds=time.monotonic()-start))
        raise


if __name__=='__main__':raise SystemExit(main())
