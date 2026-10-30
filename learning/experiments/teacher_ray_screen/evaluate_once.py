"""One coordinator-dispatched D13 observer; never changes global lease."""

import argparse
import json
import os
import resource
import signal
import subprocess
import time
import traceback

import common as c
from lifecycle import run_child,group_members
from run_once import validate_dispatch
from evaluate_worker import training_binding


def audit(reg,digest,out):
    result=c.read(out/'result.json');exit=c.read(out/'exit.json')
    launch=c.read(out/'launch.json');claim=c.read(out/'worker.claimed')
    c.need(exit['raw_exit_code']==exit['observed_exit_code']==0 and exit['directly_reaped']
           and exit['group_absent'] and not group_members(exit['pgid'])
           and launch['pid']==claim['pid']==exit['pid'],'Evaluation lifecycle differs')
    c.need(result['registration_sha256']==claim['registration_sha256']==digest
           and result['status']=='complete_D13_evaluation_no_promotion' and result['games']==10240
           and not result['promoted'],'Evaluation result differs')
    for name in ('episodes','analysis','prefix'):
        file=out/({'episodes':'episodes.jsonl','analysis':'analysis.json','prefix':'prefix-qualification.json'}[name])
        c.need(c.sha(file)==result[name+'_sha256'],'Evaluation evidence hash differs')
    prefix=c.read(out/'prefix-qualification.json')
    c.need(prefix['counted_games']==64 and prefix['forecast_seconds']<7200,'D13 counted-prefix forecast differs')
    with (out/'episodes.jsonl').open() as f:rows=[json.loads(line) for line in f]
    c.need(len(rows)==10240 and sum(r['gameplay_frames'] for r in rows)==result['actual_frames'],'Evaluation actual counts differ')
    from evaluation_analysis import analyze
    recomputed=analyze(rows,reg['evaluation'])
    c.need(recomputed==c.read(out/'analysis.json'),'Independent recomputation of summary/bootstrap differs')
    c.need(result['elapsed_seconds']<7200 and result['resources']['peak_rss_bytes']<reg['rss_bytes']
           and result['resources']['peak_mps_driver_bytes']<reg['mps_bytes'],'Evaluation limits differ')
    c.need(not (out/'first-failure.json').exists() and not list(out.glob('*.partial')),'Evaluation partial/failure present')
    return dict(result_sha256=c.sha(out/'result.json'),exit_sha256=c.sha(out/'exit.json'),games=10240,
                actual_frames=result['actual_frames'],analysis_sha256=result['analysis_sha256'])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dispatch',required=True);parser.add_argument('--sha256',required=True)
    args=parser.parse_args();gate,reg=validate_dispatch(args.dispatch,args.sha256,stage='evaluation')
    training_binding(reg,gate)
    out=c.HERE/'evaluation-output';c.need(not list(out.iterdir()),'Evaluation output already consumed')
    c.ac_power();helper=subprocess.Popen(['/usr/bin/caffeinate','-ims','-w',str(os.getpid())])
    started=time.monotonic();claimed=False;last_power=float('-inf')
    try:
        power=None
        for _ in range(20):
            try:power=c.power_assertions(os.getpid());break
            except ValueError:time.sleep(.1)
        c.need(power is not None,'Evaluation caffeinate assertions absent')
        c.save(out/'observer.claimed',dict(pid=os.getpid(),dispatch_sha256=args.sha256,power=power));claimed=True

        def deadline(*_):raise TimeoutError('D13 observer deadline')
        signal.signal(signal.SIGALRM,deadline);signal.signal(signal.SIGTERM,deadline);signal.signal(signal.SIGINT,deadline)
        signal.setitimer(signal.ITIMER_REAL,7370)

        def monitor(members):
            nonlocal last_power
            c.check_lease(reg);now=time.monotonic()
            c.need(now-started<7380 and helper.poll() is None,'Evaluation observer deadline/helper')
            c.need(sum(x['rss_bytes'] for x in members)+int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)+c.process_rss(helper.pid)<reg['rss_bytes'],'Evaluation aggregate RSS')
            if now-last_power>=5:c.power_assertions(os.getpid());last_power=now

        argv=[reg['interpreter'],'-B',str(c.HERE/'evaluate_worker.py'),'--registration',gate['registration_path'],
              '--sha256',gate['registration_sha256'],'--dispatch',args.dispatch,'--dispatch-sha256',args.sha256]
        environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(c.HERE/'empty-pycache'))
        run_child(argv,out,environment,monitor,7380)
        evidence=audit(reg,gate['registration_sha256'],out)
        c.verify_pins(reg);monitor([])
        c.need(not list((c.HERE/'empty-pycache').iterdir()),'Cache changed')
        c.save(out/'parent-terminal-audit.json',dict(status='D13_complete_pending_coordinator_acceptance',
            registration_sha256=gate['registration_sha256'],dispatch_sha256=args.sha256,evidence=evidence,
            elapsed_seconds=time.monotonic()-started,lease_cleared=False,promoted=False))
        return 0
    except BaseException as error:
        if claimed and not (out/'observer-first-failure.json').exists():
            c.save(out/'observer-first-failure.json',dict(status='first_failure_preserved_lease_held',error=repr(error),traceback=traceback.format_exc()))
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);helper.terminate();helper.wait(timeout=5)


if __name__=='__main__':raise SystemExit(main())
