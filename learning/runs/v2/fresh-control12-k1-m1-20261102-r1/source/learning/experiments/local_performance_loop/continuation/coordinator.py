"""Exactly once: own the root, directly reap, then audit and release."""
import argparse
import os
import resource
import signal
import traceback
import common as c
from lifecycle import run_child, group_members


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--registration',required=True);parser.add_argument('--sha256',required=True)
    args=parser.parse_args();reg=c.load_registration(args.registration,args.sha256);c.review_gate(reg,args.sha256);c.verify_environment(reg)
    out=c.RUN/'output'
    def cancel(*_):raise c.CampaignStop('User cancelled coordinator')
    signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
    c.save(out/'coordinator.claimed',dict(pid=os.getpid(),pgid=os.getpgrp(),registration_sha256=args.sha256))
    environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=reg['cache'],PYTORCH_ENABLE_MPS_FALLBACK='0')
    def monitor(members):
        state=c.read(reg['state_path']);c.machine_state(reg,state)
        if (out/'dispatch.json').exists():c.check_lease(reg)
        c.need(sum(m['rss_bytes'] for m in members)+resource.getrusage(resource.RUSAGE_SELF).ru_maxrss<reg['rss_bytes'],
               'Coordinator/root RSS ceiling')
        c.need(not (c.RUN/'cancel.requested').exists(),'User cancelled run')
    try:
        root=run_child([reg['interpreter'],'-B',str(c.CODE/'owner.py'),'--registration',args.registration,'--sha256',args.sha256],
            out/'owner',environment,monitor,None,cleanup_seconds=120)
        owned=[root]+[c.read(out/name) for name in ['worker/exit.json','supervisor/exit.json','caffeinate-exit.json']]
        c.need(all(e['directly_reaped'] and e['group_absent'] and not group_members(e['pgid']) for e in owned),
               'Owned accelerator groups remain after direct owner reap')
        c.save(out/'coordinator-exit.json',dict(observed_exit_code=0,directly_reaped=True,owner_pid=root['pid'],
            local_groups_absent=True,owner_exit_sha256=c.sha(out/'owner/exit.json'),groups=[e['pgid'] for e in owned]))
        def acceptance_monitor(members):
            c.need(sum(m['rss_bytes'] for m in members)+resource.getrusage(resource.RUSAGE_SELF).ru_maxrss<reg['rss_bytes'],
                   'Receipt process RSS ceiling')
        run_child([reg['interpreter'],'-B',str(c.CODE/'owner.py'),'--registration',args.registration,'--sha256',args.sha256,'--accept-terminal'],
            out/'acceptance',environment,acceptance_monitor,None)
        release=c.read(out/'lease-release.json')
        c.need(release['previous_lease']==reg['expected_lease'] and release['lease_value_after_release'] is None
            and release['accepted_audit_sha256']==c.sha(out/'parent-terminal-audit.json'),'Exact accepted release receipt differs')
        c.save(out/'coordinator-complete.json',dict(status='accepted_released_no_live_accelerator_groups',
            audit_sha256=c.sha(out/'parent-terminal-audit.json'),release_sha256=c.sha(out/'lease-release.json'),
            acceptance_exit_sha256=c.sha(out/'acceptance/exit.json')))
        print('Accepted, directly reaped, exact lease released.',flush=True)
    except BaseException as error:
        c.save(out/'coordinator-first-failure.json',dict(status='blocked_no_retry_no_reset',error=repr(error),traceback=traceback.format_exc()))
        raise


if __name__=='__main__':main()
