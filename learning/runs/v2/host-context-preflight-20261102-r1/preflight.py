"""One non-training SSH-host process-ownership and controlled-cancel check."""
import argparse
from datetime import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import sysconfig
from zoneinfo import ZoneInfo

ROOT=Path('/Users/taylor/Projects/dodge-native')
OUT=ROOT/'learning/runs/v2/host-context-preflight-20261102-r1'
FAILED=ROOT/'learning/runs/v2/control12-lr1e5-m1-20261102-r1'
EXPECTED_CONFIG='2909bad7f027e71238d3acd2e6b529b88ee3d0604691ad732a62d3d504062741'


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def save(path,value):
    with path.open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
    fd=os.open(path.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)


def child():
    def cancelled(*_):
        save(OUT/'child-cancelled.json',dict(pid=os.getpid(),signal='SIGTERM',controlled_preflight_only=True))
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,cancelled)
    save(OUT/'child-ready.json',dict(pid=os.getpid(),ppid=os.getppid(),pgid=os.getpgrp(),work='signal.pause only'))
    signal.pause()
    raise RuntimeError('Unexpected non-cancellation wakeup')


def main():
    started=datetime.now(ZoneInfo('America/Chicago')).isoformat()
    assert sha(FAILED/'config.json')==EXPECTED_CONFIG
    reg=json.loads((FAILED/'config.json').read_text())
    assert str(Path(sys.executable).absolute())==reg['interpreter']
    assert sys.version_info[:3]==(3,12,15) and sys.platform=='darwin' and os.uname().machine=='arm64'
    for name,version in reg['versions'].items():
        assert importlib.metadata.version(name)==version,name
    for name,digest in {**reg['source_pins'],**reg['input_pins']}.items():
        assert sha(Path(name))==digest,name
    frozen_names=['config.json','authority.json','source-manifest.json','review.json','host_driver.py',
        'terminal-report.md','result-summary.json','EXECUTION_OWNER.json','postflight.json','department-callback.json',
        'output/host-driver.claimed','output/coordinator.claimed','output/host-driver-first-failure.json',
        'output/coordinator-first-failure.json','output/host-coordinator/launch.json','output/host-coordinator/exit.json',
        'output/host-coordinator/worker.log','output/owner/launch.json','output/owner/exit.json','output/owner/worker.log']
    before={name:sha(FAILED/name) for name in frozen_names}
    ledger=Path(reg['state_path']);ledger_before=sha(ledger)
    state_before=json.loads(ledger.read_text())
    # Check both the exact failed /bin/ps operation and self inspection before spawning.
    global_ps=subprocess.run(['/bin/ps','-axo','pid=,pgid=,rss='],text=True,capture_output=True,check=True)
    own_ps=subprocess.check_output(['/bin/ps','-p',str(os.getpid()),'-o','pid=,ppid=,pgid=,rss=,comm='],text=True).strip()
    parent_ps=subprocess.check_output(['/bin/ps','-p',str(os.getppid()),'-o','pid=,ppid=,pgid=,comm='],text=True).strip()
    context=dict(pid=os.getpid(),ppid=os.getppid(),pgid=os.getpgrp(),uid=os.getuid(),euid=os.geteuid(),
        hostname=os.uname().nodename,architecture=os.uname().machine,executable=sys.executable,
        python=sys.version,SOABI=sysconfig.get_config_var('SOABI'),argv=sys.argv,
        SSH_CONNECTION=os.environ.get('SSH_CONNECTION'),SSH_CLIENT=os.environ.get('SSH_CLIENT'),
        self_ps=own_ps,parent_ps=parent_ps,global_ps_exit=global_ps.returncode,
        global_ps_rows=len(global_ps.stdout.splitlines()))
    assert context['SSH_CONNECTION'],'This preflight must execute in the actual SSH host context'
    save(OUT/'context.json',context)
    accepted_code=FAILED/'source/learning/experiments/local_performance_loop'
    sys.path.insert(0,str(accepted_code))
    import common as c
    from lifecycle import run_child,group_members
    c.RUN=OUT
    save(OUT/'preflight.claimed',dict(pid=os.getpid(),started_at_Central=started,scope='ONE CPU-nothing child; no training'))
    (OUT/'child').mkdir()
    observation={}
    def user_cancel(*_):raise c.CampaignStop('external_user_cancel')
    signal.signal(signal.SIGTERM,user_cancel);signal.signal(signal.SIGINT,user_cancel)
    def monitor(members):
        total=sum(row['rss_bytes'] for row in members)+resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        assert total<256*1024**2,'Preflight-only CPU memory guard; training6GiBcaps unchanged'
        if (OUT/'child-ready.json').exists():
            ready=json.loads((OUT/'child-ready.json').read_text())
            assert ready['ppid']==os.getpid() and ready['pid']==ready['pgid']
            assert [row['pid'] for row in members]==[ready['pid']]
            child_ps=subprocess.check_output(['/bin/ps','-p',str(ready['pid']),'-o','pid=,ppid=,pgid=,rss=,comm='],text=True).strip()
            observation.update(child_ps=child_ps,aggregate_RSS_bytes=total,ready=ready)
            # The accepted lifecycle pins the unreaped child before it signals its group.
            raise c.CampaignStop('controlled_preflight_user_cancel')
    expected_error=None
    try:
        run_child([sys.executable,'-B',str(Path(__file__).resolve()),'--child'],OUT/'child',
            dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),monitor,15,cleanup_seconds=10)
    except ValueError as error:
        expected_error=str(error)
    exit_receipt=json.loads((OUT/'child/exit.json').read_text())
    assert expected_error and 'controlled_preflight_user_cancel' in expected_error
    assert exit_receipt['raw_exit_code']==exit_receipt['observed_exit_code']==0
    assert exit_receipt['directly_reaped'] and exit_receipt['group_absent'] and not group_members(exit_receipt['pgid'])
    assert exit_receipt['cleanup_signals']==[int(signal.SIGTERM)]
    assert json.loads((OUT/'child-cancelled.json').read_text())['pid']==exit_receipt['pid']
    assert {name:sha(FAILED/name) for name in frozen_names}==before,'Frozen070 bytes changed'
    assert sha(ledger)==ledger_before,'Host ledger changed during the non-lease preflight'
    state_after=json.loads(ledger.read_text())
    assert state_before['active_long_campaign'] is None and state_after['active_long_campaign'] is None
    assert not any(name=='torch' or name.startswith('torch.') or name=='dodge_rl' or name.startswith('dodge_rl.') for name in sys.modules)
    receipt=dict(status='passed_actual_SSH_host_context_nontraining_preflight',started_at_Central=started,
        completed_at_Central=datetime.now(ZoneInfo('America/Chicago')).isoformat(),context=context,
        readonly_source_pin_count=len(reg['source_pins']),readonly_input_pin_count=len(reg['input_pins']),
        installed_versions=reg['versions'],frozen070_before_after_sha256=before,
        ledger_before_after_sha256=ledger_before,ledger_value_after=None,ledger_written=False,
        controlled_cancel_observation=observation,child_exit=exit_receipt,
        child_exit_sha256=sha(OUT/'child/exit.json'),preflight_source_sha256=sha(Path(__file__)),
        bounds='One CPU-nothing child,15second preflight watchdog and256MiBCPU guard only; no training limit changed.',
        checkpoint_loads=0,native_games=0,optimizer_steps=0,MPS_operations=0,lease_operations=0,
        limits='Proves the recorded SSH-host process inspection/ownership/cancel/resource route only. Not training qualification or launch authority.')
    save(OUT/'preflight-receipt.json',receipt)
    print(json.dumps(dict(status=receipt['status'],child_pid=exit_receipt['pid'],directly_reaped=True,group_absent=True,
        receipt_sha256=sha(OUT/'preflight-receipt.json'))),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--child',action='store_true');args=parser.parse_args()
    if args.child:child()
    else:
        try:main()
        except BaseException as error:
            save(OUT/'preflight-first-error.json',dict(error_class=type(error).__name__,reason=str(error),no_training=True,no_retry=True))
            raise
