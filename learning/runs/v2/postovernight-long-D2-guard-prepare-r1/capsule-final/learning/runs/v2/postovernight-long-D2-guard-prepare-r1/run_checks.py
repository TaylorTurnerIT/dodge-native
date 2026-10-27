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
HERE=Path(__file__).resolve().parent


def case(directory,name,options,expected):
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
               observed_acceptance=e.accept_observed(receipt,process.returncode,elapsed),
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
    assert all(absent.values()),(name,'owned group survived',absent)
    assert all(not event['open_writers'] for event in value['writer_checks']),(name,'open manifest-bound writer')
    for role in ('outer','inner','worker'):
        arms=[x for x in events if x['role']==role and x['kind']=='timer' and x['seconds']>0]
        assert len(arms)<=1,(name,'multiple nonzero arms',role)
    print(json.dumps(dict(name=name,exit=process.returncode,seconds=elapsed,injection_reached=fired,groups=absent)),flush=True)
    return value


def main():
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);parser.add_argument('--positive-only',action='store_true')
    args=parser.parse_args();directory=args.directory.resolve();directory.mkdir()
    source={p.name:c.sha(p) for p in HERE.glob('*.py')}
    import shutil
    (directory/'sources').mkdir()
    for p in HERE.glob('*.py'):shutil.copyfile(p,directory/'sources'/p.name)
    (directory/'tested-sources.json').write_text(json.dumps(source,sort_keys=True,indent=2)+'\n')
    results=[]
    def run(name,options,expected):results.append(case(directory,name,options,expected))
    for mode,code in (('closure',2),('pass',0)):run('positive-'+mode,dict(mode=mode),code)
    if args.positive_only:return
    for mode in ('closure','pass'):
        for phase in ('inner:hash-before','inner:hash-after','inner:manifest-before','inner:manifest-after',
                      'inner:terminal-before','inner:terminal-after','inner:guard-close-before','inner:guard-close-after',
                      'inner:stream-close-before','inner:stream-close-after','inner:before-D',
                      'outer:receipt-before','outer:receipt-after','outer:guard-close-before','outer:guard-close-after',
                      'outer:watchdog-join-before','outer:watchdog-join-after','outer:before-D'):
            for mutation in ('cancel','input'):
                run(mode+'-'+phase.replace(':','-')+'-'+mutation,dict(mode=mode,phase=phase,mutation=mutation),1)
        for role in ('inner','outer'):
            for phase in ('terminal-after' if role=='inner' else 'receipt-after','guard-close-before','guard-close-after','before-D','blocked-before-disarm','pending-before'):
                for mutation in ('SIGINT','SIGTERM'):
                    run(mode+'-'+role+'-'+phase+'-'+mutation,dict(mode=mode,phase=role+':'+phase,mutation=mutation),1)
        for mutation in ('extra','symlink','pending','binding'):
            run(mode+'-inventory-'+mutation,dict(mode=mode,phase='inner:before-D',mutation=mutation),1)
        for mutation,delay in (('cancel',.65),('input',5.1)):
            run(mode+'-late-delay-'+mutation,dict(mode=mode,phase='inner:guard-close-after',mutation=mutation,delay=delay),1)
        run(mode+'-slow-full-hash',dict(mode=mode,phase='outer:full-verify-before',mutation='none',delay=.7),0 if mode=='pass' else 2)
        run(mode+'-r3-late-terminal',dict(mode=mode,phase='inner:terminal-after',mutation='none',delay=1.1,
            worker_seconds=.65,inner_seconds=.8,outer_seconds=1.2),1)
        for mutation in ('cancel','input'):
            run(mode+'-inner-exit-gap-'+mutation,dict(mode=mode,phase='inner:exit-gap',mutation=mutation),1)
        run(mode+'-inner-exit-gap-wall',dict(mode=mode,phase='inner:exit-gap',mutation='none',delay=1.2,
            worker_seconds=.65,inner_seconds=.8,outer_seconds=1.2),1)
        run(mode+'-pending-alarm',dict(mode=mode,phase='inner:blocked-before-disarm',mutation='SIGALRM'),1)
    for mode in ('wrong-exit','descendant','blocked','wedged','raw-SIGINT','raw-SIGTERM','raw-SIGALRM','raw-SIGKILL'):
        run('group-'+mode,dict(mode=mode,worker_seconds=.6,inner_seconds=1,outer_seconds=1.5),1)
    run('registration-race',dict(mode='blocked',phase='inner:spawn-before-registration',mutation='crash',
        worker_seconds=1,inner_seconds=1.5,outer_seconds=2),1)
    run('inner-dies-worker-lives',dict(mode='blocked',phase='inner:during-worker',mutation='crash',
        worker_seconds=1,inner_seconds=1.5,outer_seconds=2),1)
    for mode in ('closure','pass'):
        for mutation in ('forward_SIGINT','forward_SIGTERM'):
            run(mode+'-forwarded-after-inner-D-'+mutation,dict(mode=mode,phase='inner:exit-gap',mutation=mutation,delay=.1),1)
        run(mode+'-outer-blocked-receipt',dict(mode=mode,phase='outer:receipt-after',mutation='none',delay=1.3,worker_seconds=.7,inner_seconds=1,outer_seconds=1.2),1)
    run('blocked-failure-persistence',dict(mode='closure',phase='outer:receipt-after',mutation='cancel',failure_persistence_delay=11),1)
    # A direct third-party signal after scan can be unobserved. Retain, never promise otherwise.
    for mutation in ('SIGINT','SIGTERM'):
        run('documented-direct-postscan-'+mutation,dict(mode='closure',phase='inner:exit-gap',mutation=mutation),2)
    (directory/'summary.json').write_text(json.dumps(dict(OS_subprocesses=len(results),results=results),sort_keys=True,indent=2)+'\n')


if __name__=='__main__':main()
