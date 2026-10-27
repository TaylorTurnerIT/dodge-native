"""Focused R4 outer OS matrix; fail-fast, exact current source snapshots.

Actual Guard/outer/inner/private IPC/real separate fake worker sessions execute.
Fixtures and outputs exist only below this preparation's unique attempts.
"""
from pathlib import Path
import json
import shutil
import sys
import long_d2 as c
import run_checks
HERE=Path(__file__).resolve().parent

def main():
    directory=Path(sys.argv[1]).resolve();directory.mkdir()
    (directory/'sources').mkdir()
    sources={p.name:c.sha(p) for p in HERE.glob('*.py')}
    c.save(directory/'tested-sources.json',sources)
    for p in HERE.glob('*.py'):shutil.copyfile(p,directory/'sources'/p.name)
    results=[]
    def run(name,options,expected):
        value=run_checks.case(directory,name,options,expected)
        results.append(value)
    for mode,code in (('closure',2),('pass',0)):
        # Same final post-watchdog verifier seam must accept when unblocked.
        base=dict(mode=mode,worker_seconds=2.5,inner_seconds=3,outer_seconds=4)
        run(mode+'-final-IO-control',dict(base,phase='outer:final-IO',mutation='none'),code)
        for mutation,delay in (('read',0),('none',4.5)):
            run(mode+'-final-IO-'+('read' if mutation=='read' else 'sleep'),dict(base,phase='outer:final-IO',mutation=mutation,delay=delay),1)
        for phase in ('receipt-before','receipt-close-before','receipt-close-after','final-lease','final-sample','watchdog-join-before','watchdog-join-after'):
            run(mode+'-late-'+phase,dict(base,phase='outer:'+phase,mutation='none',delay=4.5),1)
        for phase in ('guard-close-before','guard-close-after','watchdog-join-before','watchdog-join-after','final-IO'):
            for mutation in ('SIGINT','SIGTERM'):
                run(mode+'-'+phase+'-'+mutation,dict(mode=mode,phase='outer:'+phase,mutation=mutation),1)
        run(mode+'-join-failure-persistence-bound',dict(mode=mode,phase='outer:watchdog-join-before',mutation='SIGINT',failure_persistence_delay=11),1)
        for phase in ('blocked-before-disarm','pending-before'):
            run(mode+'-'+phase+'-SIGALRM',dict(mode=mode,phase='outer:'+phase,mutation='SIGALRM'),1)
        for phase,mutation in (('final-lease','cancel'),('final-IO','input'),('final-sample','cancel')):
            run(mode+'-'+phase+'-'+mutation,dict(mode=mode,phase='outer:'+phase,mutation=mutation),1)
        # Retain affected prior critical controls without repeating full 165 cases.
        for phase,mutation in (('inner:hash-after','cancel'),('inner:terminal-after','input'),('inner:before-D','binding')):
            run(mode+'-'+phase.replace(':','-')+'-'+mutation,dict(mode=mode,phase=phase,mutation=mutation),1)
    for mode in ('blocked','wedged'):
        run('owned-'+mode,dict(mode=mode,worker_seconds=.6,inner_seconds=1,outer_seconds=1.5),1)
    run('registration-race',dict(mode='blocked',phase='inner:spawn-before-registration',mutation='crash',worker_seconds=1,inner_seconds=1.5,outer_seconds=2),1)
    run('inner-dies-worker-lives',dict(mode='blocked',phase='inner:during-worker',mutation='crash',worker_seconds=1,inner_seconds=1.5,outer_seconds=2),1)
    c.save(directory/'summary.json',dict(OS_subprocesses=len(results),results=results,old_R3_negative_reruns=0,scope='focused_r4_only'))

if __name__=='__main__':main()
