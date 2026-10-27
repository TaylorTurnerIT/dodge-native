"""Fail-fast stdlib OS validation. Every subprocess/log/source attempt retained."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import long_d2 as c
import long_d2_executor as e
import processes as owned
from fixture_guards import validate_fixture
from fixture_preconditions import preregister
HERE=Path(__file__).resolve().parent


def case(directory,name,options,expected):
    # Preregister from the injected scenario, before any receipt exists.
    cls=('accepted' if expected in (0,2) else 'failed_no_child' if options.get('resource_cap')
         else 'failed_blocked_parent_crash' if name=='parent-death' else 'failed_supervisor_alive')
    options=preregister(dict(options,expectation_class=cls,expected_exit=expected))
    root=directory/name;root.mkdir()
    (root/'capsule-manifest.json').write_text('{"files":{}}')
    (root/'options.json').write_text(json.dumps(options,sort_keys=True,indent=2)+'\n')
    (root/'watched.txt').write_text('frozen input\n');(root/'module.py').write_text('# synthetic origin bytes only\n')
    pins={str(root/k):c.sha(root/k) for k in ('watched.txt','module.py')}
    (root/'pins.json').write_text(json.dumps(pins))
    import synthetic
    # Setup in runner is avoided: only construct the same strict fixture lease.
    p={**synthetic.P,'output':'campaign'}
    lease=c.expected_lease(p,'a'*64,'b'*64,root,'c'*64)
    (root/'state.json').write_text(json.dumps({'active_long_campaign':lease}))
    argv=[sys.executable,'-B',str(HERE/'synthetic.py'),'executor','--root',str(root)]
    started=time.monotonic();harness_kill=False
    with (root/'stdout.log').open('x') as stdout,(root/'stderr.log').open('x') as stderr:
        process=subprocess.Popen(argv,stdout=stdout,stderr=stderr,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        child=owned.Child(process)
        while child.poll() is None:
            if time.monotonic()-started>options.get('outer_seconds',12)+10+.5:
                harness_kill=True;process.kill();process.wait();break
            time.sleep(.01)
    if child.report is None:child.report=dict(returncode=process.returncode,direct_child_reaped=True)
    elapsed=time.monotonic()-started
    receipt_path=root/'execution/acceptance-receipt.json'
    receipt=c.read_json(receipt_path) if receipt_path.exists() else {}
    events=[]
    for path in root.glob('*-events.jsonl'):
        events.extend(json.loads(line) for line in path.read_text().splitlines())
    fired=any(x['kind']=='injection' for x in events)
    groups=receipt.get('ownership',{})
    if not groups:
        witnesses=[x['ownership'] for x in events if x['kind']=='ownership']
        if witnesses:groups=witnesses[-1]
    absent={key:owned.absent(record['pgid'],time.monotonic()+.2) for key,record in groups.items()}
    value=dict(argv=argv,raw_wait=child.report,elapsed_seconds=elapsed,expected=expected,harness_kill_required=harness_kill,
               maximum_wall_seconds=options.get("outer_seconds",12)+10+.5,
               observed_acceptance=(receipt.get('accepted') is True and process.returncode in (0,2) and elapsed<=options.get('outer_seconds',12)),
               acceptance_scope='explicit lifecycle fixture only; production consumer tested separately',
               injection_reached=fired,positive_group_absence=absent,receipt_available=bool(receipt),
               writer_checks=[x for x in events if x['kind']=='hash' and x['role']!='worker'],ML_imports=False)
    (root/'observed-command.json').write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
    assert not harness_kill,(name,"external harness kill required")
    assert elapsed<=value["maximum_wall_seconds"],(name,"normal plus shared cleanup exceeded")
    assert process.returncode==expected,(name,process.returncode,receipt.get('error'),(root/'stderr.log').read_text())
    assert value['observed_acceptance']==(expected in (0,2)),(name,receipt)
    if options.get('phase'):assert fired,(name,'injection missed')
    if options.get('mode') in ('closure','pass') and options.get('phase','').startswith('outer:'):
        assert set(absent)=={'supervisor','worker'},(name,'missing independent owned group witness')
    validate_fixture(receipt,events,absent,options,receipt_available=receipt_path.exists())
    assert all(not event['open_writers'] for event in value['writer_checks']),(name,'open manifest-bound writer')
    for role in ('outer','inner','worker'):
        arms=[x for x in events if x['role']==role and x['kind']=='timer' and x['seconds']>0]
        assert len(arms)<=1,(name,'multiple nonzero arms',role)
    print(json.dumps(dict(name=name,exit=process.returncode,seconds=elapsed,injection_reached=fired,groups=absent)),flush=True)
    return value


CASES=[
    ('normal-closure',dict(mode='closure'),2),
    ('normal-fake-gate',dict(mode='pass'),0),
    ('inner-optional-timing-error',dict(mode='closure',timing_error_role='inner'),2),
    ('outer-optional-timing-error',dict(mode='pass',timing_error_role='outer'),0),
    ('inner-failure-with-timing-error',dict(mode='closure',phase='inner:terminal-after',mutation='SIGTERM',timing_error_role='inner'),1),
    ('outer-failure-with-timing-error',dict(mode='pass',phase='outer:receipt-after',mutation='SIGINT',timing_error_role='outer'),1),
    ('post-gate-persistent-mutation',dict(mode='pass',phase='outer:receipt-before',mutation='input'),1),
    ('inner-final-alarm',dict(mode='closure',phase='inner:pending-before',mutation='SIGALRM'),1),
    ('direct-cancel-startup',dict(mode='closure',phase='inner:spawn-before-registration',mutation='SIGINT'),1),
    ('direct-cancel-wait',dict(mode='closure',phase='inner:during-worker',mutation='SIGTERM'),1),
    ('missing-worker-ACK',dict(mode='closure',missing_ack=True,worker_seconds=.7,inner_seconds=1.2,outer_seconds=2),1),
    ('parent-death',dict(mode='blocked',phase='inner:during-worker',mutation='crash',worker_seconds=.7,inner_seconds=1.2,outer_seconds=2),1),
    ('surviving-descendant',dict(mode='descendant',worker_seconds=.8,inner_seconds=1.2,outer_seconds=2),1),
    ('normal-deadline-wedged',dict(mode='wedged',worker_seconds=.6,inner_seconds=1,outer_seconds=1.5),1),
    ('RSS-resource-cap',dict(mode='closure',resource_cap=True),1),
]


def main():
    directory=Path(sys.argv[1]).resolve();directory.mkdir()
    results=[]
    for name,options,expected in CASES:results.append(case(directory,name,options,expected))
    c.save(directory/'summary.json',dict(OS_outer_executions=len(results),results=results,ML_imports=False,
        scope='Actual new orchestration lifecycle with explicit synthetic byte/runtime/summary fixtures. No ML identity or gate proof.'))

if __name__=='__main__':main()
