"""Adapt explicit stdlib lifecycle fixtures, never real runtime proof."""
from pathlib import Path
H=Path(__file__).resolve().parent
p=H/'synthetic.py';s=p.read_text()
s=s.replace("    return options,context",'''    e.REGISTRATION_PATH=root/'fixture-registration.json'
    def fixture_verify(context,root,*,endpoint=None):
        c.verify_files(pins)
        return dict(verdict='passed',role='fixture_'+str(endpoint),fixture_only=True)
    c.integrity.verify=fixture_verify
    c.integrity.cache_check=lambda _:dict(fixture_only=True)
    c.integrity.summary_valid=lambda *args:True  # Lifecycle-only fixture; summary contract has separate real tests.
    if options.get('resource_cap'):
        c.LIMIT=1
    return options,context''')
s=s.replace("[t.is_alive() for t in (final_execution[0].guard.thread,final_execution[0].guard.verify_thread)]", "[t is not None and t.is_alive() for t in (final_execution[0].guard.thread,final_execution[0].guard.verify_thread)]")
s=s.replace("    real_verify=c.verify_files",'''    real_timing=c.Guard.persist_timing
    def timing(guard,path,*args,**kwargs):
        if options.get('timing_error_role')==role:
            Path(path).write_text('partial optional diagnostic\\n')
            raise OSError('injected optional timing error')
        return real_timing(guard,path,*args,**kwargs)
    c.Guard.persist_timing=timing
    real_verify=c.verify_files''')
s=s.replace("            actual_import_origins=origins,final_checkpoint=record,worker_resources=guard.receipt())", "            actual_import_origins=origins,final_checkpoint=record,worker_resources=guard.receipt(),integrity_summary={'explicit_fixture_only':True})")
s=s.replace("pins={})", "pins={},classification_sha256='d'*64,reservation_sha256='e'*64,class_manifest_hashes={},cache_policy={})")
s=s.replace("        execution=e.Execution(ENTRY,registration,context", "        c.save(e.REGISTRATION_PATH,registration)\n        execution=e.Execution(ENTRY,registration,context")
s=s.replace("context_provider=lambda _:context", "context_provider=lambda *a,**kw:context")
# Actual missing registration ACK, isolated in fixture peer only.
s=s.replace("        code=fake_worker(args,context,options,event)", "        if options.get('missing_ack'):\n            life.CHANNEL.sock.close()\n            time.sleep(2)\n            os._exit(1)\n        code=fake_worker(args,context,options,event)")
p.write_text(s)
p=H/'os_checks.py';s=p.read_text()
s=s.replace("               observed_acceptance=e.accept_observed(receipt,process.returncode,elapsed),", "               observed_acceptance=(receipt.get('accepted') is True and process.returncode in (0,2) and elapsed<=options.get('outer_seconds',12)),\n               acceptance_scope='explicit lifecycle fixture only; production consumer tested separately',")
a=s.index('def main():');s=s[:a]+'''def main():
    directory=Path(sys.argv[1]).resolve();directory.mkdir()
    results=[]
    cases=[
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
    for name,options,expected in cases:results.append(case(directory,name,options,expected))
    c.save(directory/'summary.json',dict(OS_outer_executions=len(results),results=results,ML_imports=False,
        scope='Actual new orchestration lifecycle with explicit synthetic byte/runtime/summary fixtures. No ML identity or gate proof.'))

if __name__=='__main__':main()
'''
p.write_text(s)
