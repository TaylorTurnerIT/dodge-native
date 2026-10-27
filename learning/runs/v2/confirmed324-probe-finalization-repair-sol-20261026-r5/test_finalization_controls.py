"""Real handled signals at the finalization boundary; synthetic worker only."""
import inspect
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import supervisor_cli as supervisor
from test_failure_controls import fixture, sha, write

RUN=Path(__file__).absolute().parent
SIGNALS=(signal.SIGTERM,signal.SIGHUP,signal.SIGINT)
PHASES=('before_freeze','before_serialization','after_serialization','after_fsync','handler_restoration')


def driver(root,phase,signame):
    """Instrument real call sites without changing production source or receipts."""
    sig=signal.Signals[signame]
    rp=root/'registration.json'; reg=json.loads(rp.read_text())
    receipt_path=Path(reg['output_dir'])/'outer-receipt.json'
    old_handlers={s:signal.getsignal(s) for s in SIGNALS}
    old_trace=sys.gettrace()
    # Keep even the cleanup-source pathname owned; verify its unchanged pinned bytes.
    cleanup=root/'cleanup-source.py'; shutil.copyfile(supervisor.PRIMITIVES,cleanup)
    supervisor.PRIMITIVES=cleanup
    original_exclusive=supervisor.exclusive_json
    original_mkdir=Path.mkdir
    original_open=os.open
    original_fsync=os.fsync
    original_signal=signal.signal
    evidence={'phase':phase,'signal':signame,'injections':0}
    publishing=False
    receipt_fds=set()

    def inject():
        if evidence['injections']: raise AssertionError('signal injected twice')
        evidence['injections']+=1
        # This invokes the installed production Python handler through the OS.
        os.kill(os.getpid(),sig)

    def exclusive(path,obj,on_created=None):
        nonlocal publishing
        if Path(path)!=receipt_path: return original_exclusive(path,obj,on_created)
        publishing=True
        try: result=original_exclusive(path,obj,on_created)
        finally: publishing=False
        evidence['publication_sha256']=sha(receipt_path)
        return result

    def mkdir(path,*args,**kwargs):
        if publishing and Path(path)==receipt_path.parent and phase=='before_serialization': inject()
        return original_mkdir(path,*args,**kwargs)

    def opened(path,*args,**kwargs):
        fd=original_open(path,*args,**kwargs)
        if publishing and Path(path)==receipt_path:
            receipt_fds.add(fd)
            # exclusive_json has already constructed its complete encoded raw bytes.
            if phase=='after_serialization': inject()
        return fd

    def fsync(fd):
        result=original_fsync(fd)
        if publishing and fd in receipt_fds and phase=='after_fsync': inject()
        return result

    def restore(s,handler):
        if phase=='handler_restoration' and s==sig and handler==old_handlers[s]: inject()
        return original_signal(s,handler)

    # A line trace stops immediately BEFORE the actual flag assignment, after all
    # inventory/check decisions. It neither replaces nor invokes the handler itself.
    lines,start=inspect.getsourcelines(supervisor.execute)
    freeze_line=[start+i for i,line in enumerate(lines) if line.strip()=='outcome_frozen=True']
    assert len(freeze_line)==1

    def trace(frame,event,arg):
        if frame.f_code is supervisor.execute.__code__:
            if event=='line' and frame.f_lineno==freeze_line[0] and phase=='before_freeze': inject()
            return trace
        return None

    try:
        with patch.object(supervisor,'exclusive_json',exclusive),patch.object(Path,'mkdir',mkdir),patch.object(os,'open',opened),patch.object(os,'fsync',fsync),patch.object(signal,'signal',restore):
            if phase=='before_freeze': sys.settrace(trace)
            try:
                evidence['returned_result']=supervisor.execute(rp,sha(rp),RUN/'worker_cli.py')
                evidence['returned']=True
            except Exception as exc:
                evidence['returned']=False
                evidence['error_type']=type(exc).__name__
                evidence['error']=str(exc)
            finally: sys.settrace(old_trace)
    finally:
        evidence['handlers_restored']=all(signal.getsignal(s)==h for s,h in old_handlers.items())
        evidence['trace_restored']=sys.gettrace() is old_trace
    evidence['receipt_sha256_after_return']=sha(receipt_path)
    # Independently re-sample the actual worker process group after execute ended.
    pid=json.loads((Path(reg['output_dir'])/'worker-heartbeat.json').read_text())['pid']
    rows,error=supervisor.verified_primitives()['sample_procs'](pid)
    evidence.update(worker_pid=pid,post_return_group_rows=rows,post_return_group_error=error)
    write(root/'driver-result.json',evidence)


class FinalizationControls(unittest.TestCase):
    def check_phase(self,phase,sig):
        root=Path(tempfile.mkdtemp(prefix=f'finalization-{phase}-{sig.name}-',dir=RUN/'test-tmp'))
        fixture(root,'normal')
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(root/'cache'),RNG_PROBE_SYNTHETIC_TEST='1')
        process=subprocess.run([sys.executable,'-B',str(Path(__file__).absolute()),'--driver',str(root),phase,sig.name],env=env,capture_output=True,text=True,timeout=22)
        (root/'driver.log').write_text(process.stdout+process.stderr)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)
        evidence=json.loads((root/'driver-result.json').read_text())
        rec=json.loads((root/'out'/'outer-receipt.json').read_text())
        self.assertEqual(evidence['injections'],1)
        self.assertTrue(evidence['handlers_restored'])
        self.assertTrue(evidence['trace_restored'])
        self.assertEqual(evidence['publication_sha256'],evidence['receipt_sha256_after_return'])
        self.assertEqual(evidence['post_return_group_rows'],[])
        self.assertFalse(evidence['post_return_group_error'])
        self.assertEqual(rec['raw_worker_exit_code'],0)
        self.assertTrue(rec['process_group_absent'])
        self.assertEqual(rec['process_group_remaining'],[])
        self.assertEqual(len(rec['postflight']),19)
        self.assertTrue(all(row['status']=='pass' for row in rec['postflight'].values()))
        self.assertEqual(rec['failed_checks'],[])
        self.assertEqual(rec['inventory_errors'],[])
        self.assertEqual(rec['errors'],[])
        self.assertTrue(rec['claim_created'] and rec['claim_write_completed'])
        self.assertEqual(list((root/'cache').iterdir()),[])
        if phase=='before_freeze':
            self.assertFalse(evidence['returned'])
            self.assertNotIn('returned_result',evidence)
            self.assertEqual(evidence['error_type'],'RuntimeError')
            self.assertEqual(evidence['error'],f'probe failed: supervisor_signal:{sig.name}; partial receipt preserved')
            self.assertEqual(rec['status'],'partial_failure_preserved')
            self.assertEqual(rec['stop_reason'],'supervisor_signal:'+sig.name)
            self.assertEqual(rec['handled_signals'],[sig.name])
        else:
            self.assertTrue(evidence['returned'])
            self.assertNotIn('error',evidence)
            self.assertEqual(evidence['returned_result'],rec)
            self.assertEqual(rec['status'],'accepted_pending_parent_postflight')
            self.assertIsNone(rec['stop_reason'])
            self.assertEqual(rec['handled_signals'],[])


def control(phase,sig):
    def test(self): self.check_phase(phase,sig)
    test.__doc__=f'First {sig.name} at {phase}; verdict, history, return and restoration agree.'
    return test


for _phase in PHASES:
    for _sig in SIGNALS:
        setattr(FinalizationControls,f'test_first_{_sig.name}_{_phase}',control(_phase,_sig))


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--driver': driver(Path(sys.argv[2]),sys.argv[3],sys.argv[4])
    else: unittest.main()
