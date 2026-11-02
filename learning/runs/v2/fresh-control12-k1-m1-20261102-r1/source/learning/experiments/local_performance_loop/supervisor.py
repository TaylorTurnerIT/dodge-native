"""Bounded worker ownership and directly reaped sleep prevention."""
import argparse
import os
import resource
import signal
import subprocess
import time
import traceback
import common as c
from lifecycle import run_child,group_members,observe,waitid_function


def main():
    p=argparse.ArgumentParser();p.add_argument('--registration',required=True);p.add_argument('--sha256',required=True);args=p.parse_args()
    reg=c.load_registration(args.registration,args.sha256);c.review_gate(reg,args.sha256);c.check_lease(reg)
    out=c.RUN/'output';launch=c.read(out/'dispatch.json');start=launch['started_monotonic']
    helper=None;power=None;last=-1.;helper_proof=None
    def cancelled(*_):raise c.CampaignStop('Supervisor cancellation')
    signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
    def monitor(members):
        nonlocal last
        c.check_lease(reg)
        rss=sum(m['rss_bytes'] for m in members)+int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)+c.process_rss(os.getppid())+c.process_rss(helper.pid)
        c.need(rss<reg['rss_bytes'],'Aggregate owner/supervisor/helper/worker RSS cap')
        c.need(observe(helper,waitid_function()) is None,'Owned sleep helper exited early')
        if time.monotonic()-last>=5:
            c.record_power(power,sleep=c.power_assertions(os.getpid()));power.sync();last=time.monotonic()
    def finish_helper():
        nonlocal helper_proof,helper
        if helper is None:return
        fn=waitid_function();observed=observe(helper,fn);signals=[]
        if observed is None:
            # Direct child is unreaped, so this cannot signal a reused PID/group.
            os.killpg(helper.pid,signal.SIGTERM);signals.append(int(signal.SIGTERM))
        deadline=time.monotonic()+5
        while observed is None and time.monotonic()<deadline:
            time.sleep(.05);observed=observe(helper,fn)
        if observed is None:
            os.killpg(helper.pid,signal.SIGKILL);signals.append(int(signal.SIGKILL))
        code=helper.wait(timeout=3)
        absent=not group_members(helper.pid)
        helper_proof=dict(pid=helper.pid,pgid=helper.pid,directly_reaped=True,observed_exit_code=code,group_absent=absent,signals=signals)
        helper=None
        c.save(out/'caffeinate-exit.json',helper_proof);c.need(absent,'Owned caffeinate group remains')
    try:
        power=c.Journal(out/'power.jsonl')
        helper=subprocess.Popen(['/usr/bin/caffeinate','-ims','-w',str(os.getpid())],start_new_session=True)
        c.save(out/'caffeinate-launch.json',dict(pid=helper.pid,pgid=helper.pid,parent_pid=os.getpid()))
        environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=reg['cache'])
        child=run_child([reg['interpreter'],'-B',str(c.CODE/'worker.py'),'--registration',args.registration,'--sha256',args.sha256],
            out/'worker',environment,monitor,None)
        finish_helper();helper=None;power.close();power=None
        c.save(out/'supervisor-result.json',dict(status='worker_complete_pending_parent_acceptance',registration_sha256=args.sha256,
            worker_exit_sha256=c.sha(out/'worker/exit.json'),caffeinate_exit_sha256=c.sha(out/'caffeinate-exit.json'),
            power_sha256=c.sha(out/'power.jsonl'),elapsed_seconds=time.monotonic()-start))
        return 0
    except BaseException as error:
        if helper is not None:finish_helper();helper=None
        if power is not None:power.close()
        c.save(out/'supervisor-first-failure.json',dict(status='blocked_preserve_exact_lease',error=repr(error),traceback=traceback.format_exc()))
        raise


if __name__=='__main__':raise SystemExit(main())
