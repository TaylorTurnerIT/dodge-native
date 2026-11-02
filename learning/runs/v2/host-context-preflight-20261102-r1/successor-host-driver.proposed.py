"""Host caller: launch the reviewed coordinator once and directly reap it."""
import json
import os
from pathlib import Path
import resource
import signal
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

RUN=Path(__file__).resolve().parent
CODE=RUN/'source/learning/experiments/local_performance_loop/continuation'
sys.path.insert(0,str(CODE))
import common as c
from lifecycle import run_child,group_members
DIGEST='222e17c7127b8acf17bb008f2c47e0fc6eb41f7bd79e3e9ad8290504f459d611'
reg=c.load_registration(RUN/'config.json',DIGEST)
c.review_gate(reg,DIGEST);c.verify_environment(reg)
out=RUN/'output'
c.need(not (out/'coordinator.claimed').exists() and not (out/'owner.claimed').exists(),'No launch retry')
c.save(out/'host-driver.claimed',dict(pid=os.getpid(),registration_sha256=DIGEST,
       started_at_Central=datetime.now(ZoneInfo('America/Chicago')).isoformat()))
(out/'host-coordinator').mkdir()
def cancel(*_):raise c.CampaignStop('User cancelled host caller')
signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
announced=False
def monitor(members):
    global announced
    c.need(sum(r['rss_bytes'] for r in members)+resource.getrusage(resource.RUSAGE_SELF).ru_maxrss<reg['rss_bytes'],
           'Host caller/coordinator RSS ceiling')
    c.need(not (RUN/'cancel.requested').exists(),'User cancelled host caller')
    if not announced:
        launch=c.read(out/'host-coordinator/launch.json')
        print(json.dumps(dict(status='coordinator_launched',pid=launch['pid'],pgid=launch['pgid'],
              registration_sha256=DIGEST,source_commit=c.read(RUN/'SOURCE_COMMIT.json')['commit'])),flush=True)
        announced=True
try:
    exit_receipt=run_child([reg['interpreter'],'-B',str(CODE/'coordinator.py'),'--registration',str(RUN/'config.json'),
        '--sha256',DIGEST],out/'host-coordinator',dict(os.environ,PYTHONDONTWRITEBYTECODE='1',
        PYTHONPYCACHEPREFIX=reg['cache'],PYTORCH_ENABLE_MPS_FALLBACK='0'),monitor,None,cleanup_seconds=180)
    c.need(exit_receipt['directly_reaped'] and exit_receipt['group_absent'] and not group_members(exit_receipt['pgid']),
           'Host coordinator direct reap/group proof missing')
    accepted=c.read(out/'parent-terminal-audit.json');release=c.read(out/'lease-release.json')
    c.need(accepted['status']=='accepted_local_control_continuation'
        and release['accepted_audit_sha256']==c.sha(out/'parent-terminal-audit.json')
        and release['previous_lease']==reg['expected_lease'] and release['lease_value_after_release'] is None,
        'Strict accepted audit and exact release required')
    for name in ['owner','supervisor','worker','acceptance']:
        e=c.read(out/name/'exit.json');c.need(e['directly_reaped'] and e['group_absent']
            and not group_members(e['pgid']),'Owned group remains: '+name)
    c.save(out/'host-driver-complete.json',dict(status='complete_accepted_released_coordinator_directly_reaped',
        coordinator_exit_sha256=c.sha(out/'host-coordinator/exit.json'),audit_sha256=c.sha(out/'parent-terminal-audit.json'),
        release_sha256=c.sha(out/'lease-release.json'),finished_at_Central=datetime.now(ZoneInfo('America/Chicago')).isoformat()))
    print(json.dumps(dict(status='complete_accepted_released',best=accepted['arms'][0]['best'],
        stop_reason=accepted['arms'][0]['stop_reason'])),flush=True)
except BaseException as error:
    c.save(out/'host-driver-first-failure.json',dict(status='blocked_preserve_first_failure_no_retry_no_lease_clear',
        error_class=type(error).__name__,reason=str(error)))
    raise
