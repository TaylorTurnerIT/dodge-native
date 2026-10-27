"""Real owned stdlib processes, synthetic gates only; no campaign authority."""
import json
import errno
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

OWN=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(OWN))
import binding as b
import observe

PYTHON=str(b.ROOT/'python/.venv/bin/python')  # Preserve the lexical project path.
HELPER=str(OWN/'tests/stdlib_child.py')
EVIDENCE_ROOT=OWN/'real-evidence'
EVIDENCE=[]
OWNED={}

def wait_for(path,seconds=4):
    end=time.monotonic()+seconds
    while not path.exists():
        if time.monotonic()>=end: raise TimeoutError(str(path))
        time.sleep(.005)

def command(mode,home): return [PYTHON,'-I','-B',HELPER,mode,str(home)]

def spawn(argv,**kwargs):
    assert argv[:4]==[PYTHON,'-I','-B',HELPER],argv
    assert Path(argv[-1]).resolve().is_relative_to(OWN/'tests')
    proc=subprocess.Popen(argv,**kwargs)
    OWNED[proc.pid]=proc
    return proc

class RealProcesses(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=OWN/'tests',prefix='real-')
        self.home=Path(self.temp.name)
        self.events=[]
        self.case=dict(test=self.id(),processes=[],checks={})
        EVIDENCE.append(self.case)
    def tearDown(self):
        for pid,proc in list(OWNED.items()):
            if proc.returncode is None:
                # The audit guard permits only unreaped direct child handles.
                try: os.killpg(pid,signal.SIGKILL)
                except (ProcessLookupError, PermissionError) as error:
                    # Darwin may deny signaling a zombie-only pinned group.
                    # Still wait and check actual group absence below.
                    self.case['checks'].setdefault('teardown_signal_errors',[]).append(repr(error))
                proc.wait(timeout=2)
            self.case['processes'].append(dict(pid=pid,raw_exit=proc.returncode,
                directly_reaped=proc.returncode is not None,group_absent=not observe.group_exists(pid)))
            self.assertFalse(observe.group_exists(pid),'leftover owned group')
            del OWNED[pid]
        self.case['checks']['no_worker_output_created']=not (self.home/'worker-output').exists()
        # Preserve test receipts and staging files, including first failures.
        retained=EVIDENCE_ROOT/self._testMethodName
        retained.parent.mkdir(exist_ok=True)
        self.home.rename(retained)
        self.temp.cleanup()
    def fixture(self):
        reg=dict(output=str(self.home/'worker-output'),runtime_root=str(self.home),
                 import_policy=dict(pycache_prefix=str(OWN/'empty-cache')))
        envelope=dict(started=time.monotonic(),registration_sha256='synthetic-no-registration',
                      control=str(self.home/'control'),cancel_path=str(self.home/'cancel'))
        return envelope,reg
    def run_controller(self,mode='wait',*,before_return=None,save_hook=None,rows=None,limits=None,verify_hook=None):
        envelope,reg=self.fixture()
        original_save=b.save
        def launch(argv,**kwargs):
            self.assertEqual(argv,command(mode,self.home))
            proc=spawn(argv,**kwargs)
            wait_for(self.home/'ready')
            identity=b.read(self.home/'ready')
            self.assertEqual(identity,dict(pid=proc.pid,ppid=os.getpid(),pgid=proc.pid))
            self.case['checks']['direct_parent_identity']=identity
            if before_return: before_return(proc,envelope)
            return proc
        def save(path,value):
            if save_hook: save_hook(Path(path),value)
            return original_save(path,value)
        with patch.object(b,'load_envelope',return_value=(envelope,reg)), \
             patch.object(b,'verify_bound',side_effect=verify_hook),patch.object(b,'check_lease'), \
             patch.object(b,'worker_command',return_value=command(mode,self.home)), \
             patch.object(b,'save',side_effect=save):
            with patch.object(observe,'process_rows',side_effect=rows) if rows else patch.object(b,'LIMITS',b.LIMITS if limits is None else limits):
                code=observe.main('synthetic-not-an-envelope','synthetic-no-registration',popen=launch)
        self.assertEqual(code,1)
        receipt=b.read(self.home/'control/observation.json')
        self.assertEqual(receipt['actual_worker_launch_count'],1)
        self.assertTrue(receipt['directly_reaped'])
        self.assertTrue(receipt['worker_group_absent'])
        self.assertFalse(receipt['promoted'])
        self.case['observation']=receipt
        return receipt,envelope
    def test_direct_owner_cancellation_during_popen_return(self):
        def cancel(proc,envelope): os.kill(os.getpid(),signal.SIGTERM)
        receipt,_=self.run_controller(before_return=cancel)
        self.assertEqual(receipt['first_event']['kind'],'observer_cancelled')
        self.assertEqual(receipt['observed_worker_raw_exit'],-15)
        self.assertEqual(receipt['cleanup_signals'][0]['ownership'],
            'unreaped directly owned Popen with start_new_session=True')
    def test_failure_before_receipt_or_first_snapshot_keeps_ownership(self):
        def fail(path,value):
            if path.name=='worker-launch.json': raise RuntimeError('injected pre-publication failure')
        def no_snapshot(): self.fail('snapshot must not establish birth ownership')
        receipt,envelope=self.run_controller(save_hook=fail,rows=no_snapshot)
        self.assertIn('injected pre-publication failure',receipt['first_event']['error'])
        self.assertFalse((self.home/'control/worker-launch.json').exists())
        self.assertEqual(receipt['observed_worker_raw_exit'],-15)
        # The real one-use control claim rejects a second dispatch before Popen.
        with patch.object(b,'load_envelope',return_value=(envelope,dict(output=str(self.home/'worker-output')))):
            with self.assertRaises(FileExistsError): observe.main('unused','unused',popen=lambda *a,**k:self.fail('retry'))
    def test_empty_anchors_term_exiting_leader_stubborn_descendant(self):
        def fail(path,value):
            if path.name=='worker-launch.json': raise RuntimeError('injected combined pre-receipt failure')
        def no_snapshot(): self.fail('empty anchors must not require a snapshot')
        def snapshot_failure(): raise RuntimeError('injected combined pre-snapshot failure')
        base=self.home
        try:
            for stage in ('receipt','snapshot'):
                with self.subTest(stage=stage):
                    self.home=base/stage;self.home.mkdir()
                    start=time.monotonic()
                    receipt,_=self.run_controller('orphan-family',save_hook=fail if stage=='receipt' else None,rows=no_snapshot if stage=='receipt' else snapshot_failure)
                    child=b.read(self.home/'descendant.json')
                    self.assertEqual(receipt['observed_worker_raw_exit'],-15)
                    self.assertEqual(child['pgid'],receipt['worker_pid'])
                    self.assertEqual([item['signal'] for item in receipt['cleanup_signals']],['SIGTERM','SIGKILL'])
                    self.assertTrue(all(item['ownership']=='unreaped directly owned Popen with start_new_session=True'
                                        for item in receipt['cleanup_signals']))
                    self.assertTrue(receipt['cleanup']['reaped'])
                    self.assertNotIn(child['pid'],observe.process_rows())
                    self.assertFalse(observe.group_exists(child['pgid']))
                    self.assertIn('injected combined pre-'+stage+' failure',receipt['first_event']['error'])
                    self.assertEqual((self.home/'control/worker-launch.json').exists(),stage=='snapshot')
                    self.case['checks'].setdefault('empty_anchor_stages',[]).append(dict(stage=stage,descendant=child,descendant_absent_from_process_table=True,
                        descendant_reap_scope='orphan reaped by OS; direct leader reaped by Popen.wait',
                        actual_return_elapsed_seconds=time.monotonic()-start))
                    self.assertLess(time.monotonic()-start,10)
        finally:
            self.home=base
    def test_real_term_kill_deadline_and_raw_reap(self):
        def cancel(proc,envelope): Path(envelope['cancel_path']).touch()
        start=time.monotonic()
        receipt,_=self.run_controller('ignore-term',before_return=cancel)
        self.assertEqual(receipt['first_event']['kind'],'cancel_marker')
        self.assertEqual(receipt['observed_worker_raw_exit'],-9)
        self.assertEqual([v['signal'] for v in receipt['cleanup_signals']],['SIGTERM','SIGKILL'])
        self.assertLess(time.monotonic()-start,10)
    def test_fork_after_first_snapshot_retains_pin_through_kill(self):
        original_rows = observe.process_rows
        original_exit = observe.observe_exit
        original_signal = observe.signal_owned
        trace = []; first = True; handle = []; raw_wait = []
        def prepare(proc, envelope):
            handle.append(proc)
            original_wait = proc.wait
            raw_wait.append(original_wait)
            def wait(timeout=None):
                # The observer must kill the surviving group before its first reap.
                self.assertIn('SIGKILL', trace)
                child = b.read(self.home/'descendant.json')
                self.assertNotIn(child['pid'], original_rows())
                self.assertIsNone(proc.returncode)
                self.assertEqual(original_exit(proc, observe.nonreaping_waitid()), 23)
                code = original_wait(timeout=timeout)
                trace.append('reaped')
                return code
            proc.wait = wait
        def rows():
            nonlocal first
            snapshot = original_rows()
            if first:
                first = False
                self.assertEqual([r['pid'] for r in snapshot.values() if r['pgid']==handle[0].pid], [handle[0].pid])
                self.assertFalse((self.home/'descendant-ready').exists())
                trace.append('snapshot_leader_only')
                (self.home/'fork-now').touch()
                wait_for(self.home/'descendant.json')
                trace.append('fork_completed')
            return snapshot
        def exited(proc, waitid):
            end = time.monotonic()+4
            code = original_exit(proc, waitid)
            while code is None and len(trace)==2:
                if time.monotonic()>=end: self.fail('leader exit timeout')
                time.sleep(.005)
                code = original_exit(proc, waitid)
            self.assertEqual(code, 23)
            self.assertIsNone(proc.returncode)
            if len(trace)==2: trace.append('nonreaping_exit_23')
            return code
        def send(proc, anchors, sig, record):
            if sig == signal.SIGTERM:
                child = b.read(self.home/'descendant.json')
                self.assertNotIn(child['pid'], anchors, 'descendant must have no earlier anchor')
            self.assertIsNone(proc.returncode)
            self.assertEqual(original_exit(proc, observe.nonreaping_waitid()), 23)
            original_signal(proc, anchors, sig, record)
            trace.append(signal.Signals(sig).name)
        start = time.monotonic()
        try:
            with patch.object(observe,'observe_exit',side_effect=exited), patch.object(observe,'signal_owned',side_effect=send):
                receipt, envelope = self.run_controller('fork-after-snapshot',before_return=prepare,rows=rows)
        finally:
            if handle: handle[0].wait = raw_wait[0]
        child = b.read(self.home/'descendant.json')
        self.assertEqual(receipt['first_event']['kind'],'owned_group_survived_worker')
        self.assertEqual(receipt['observed_worker_raw_exit'],23)
        self.assertEqual(trace,['snapshot_leader_only','fork_completed','nonreaping_exit_23','SIGTERM','SIGKILL','reaped'])
        self.assertTrue(all(v['ownership']=='unreaped directly owned Popen with start_new_session=True'
                            for v in receipt['cleanup_signals']))
        self.assertNotIn(child['pid'],original_rows())
        self.assertNotIn(handle[0].pid,original_rows())
        self.assertFalse(observe.group_exists(child['pgid']))
        with self.assertRaises(ChildProcessError): os.waitpid(handle[0].pid,os.WNOHANG)
        with patch.object(b,'load_envelope',return_value=(envelope,dict(output=str(self.home/'worker-output')))):
            with self.assertRaises(FileExistsError): observe.main('unused','unused',popen=lambda *a,**k:self.fail('retry'))
        elapsed = time.monotonic()-start
        self.assertLess(elapsed,10)
        self.case['checks'].update(trace=trace,descendant=child,leader_raw_exit=23,
            no_earlier_descendant_anchor=True,leader_and_descendant_absent=True,group_absent=True,
            direct_reap_confirmed_by_ECHILD=True,retry_rejected_before_Popen=True,
            actual_return_elapsed_seconds=elapsed,descendant_reap_scope='orphan reaped by OS')
    def test_real_nonreaping_waitid_running_exited_and_wrong_pid(self):
        waitid = observe.nonreaping_waitid()
        with (self.home/'api.log').open('x') as log:
            proc = spawn(command('exit-on-release',self.home),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            wait_for(self.home/'ready')
            self.assertIsNone(observe.observe_exit(proc,waitid))
            self.assertIsNone(proc.returncode)
            # Claiming our own non-child PID must produce ECHILD, never an exit.
            with self.assertRaises(OSError) as wrong:
                observe.observe_exit(SimpleNamespace(pid=os.getpid(),returncode=None),waitid)
            self.assertEqual(wrong.exception.errno,errno.ECHILD)
            (self.home/'release').touch()
            end = time.monotonic()+4
            while observe.observe_exit(proc,waitid) is None:
                if time.monotonic()>=end: self.fail('waitid exit timeout')
                time.sleep(.005)
            self.assertEqual(observe.observe_exit(proc,waitid),37)
            self.assertEqual(observe.observe_exit(proc,waitid),37)
            self.assertIsNone(proc.returncode)
            self.assertIn(proc.pid,observe.process_rows())
            self.assertEqual(proc.wait(timeout=0),37)
            with self.assertRaises(OSError) as reaped:
                observe.observe_exit(SimpleNamespace(pid=proc.pid,returncode=None),waitid)
            self.assertEqual(reaped.exception.errno,errno.ECHILD)
            self.assertNotIn(proc.pid,observe.process_rows())
        # Unsupported API/ABI must fail before any Popen, preserving a receipt.
        with patch.object(observe,'nonreaping_waitid',side_effect=OSError('injected waitid unavailable')):
            envelope,reg = self.fixture()
            with patch.object(b,'load_envelope',return_value=(envelope,reg)), patch.object(b,'verify_bound'):
                self.assertEqual(observe.main('unused','unused',popen=lambda *a,**k:self.fail('unavailable API launch')),1)
        receipt = b.read(self.home/'control/observation.json')
        self.assertEqual(receipt['actual_worker_launch_count'],0)
        self.assertIn('injected waitid unavailable',receipt['first_event']['error'])
        self.case['checks'].update(running_returns_none=True,repeated_exited_status=37,true_reap_exit=37,
            wrong_pid_errno=wrong.exception.errno,reaped_pid_errno=reaped.exception.errno,
            unreaped_exited_child_present=True,after_reap_absent=True,unavailable_API_launches=0)
    def test_real_group_descendant_is_signalled_and_reaped(self):
        def cancel(proc,envelope):
            wait_for(self.home/'descendant.json')
            Path(envelope['cancel_path']).touch()
        receipt,_=self.run_controller('family',before_return=cancel)
        child=b.read(self.home/'descendant.json'); reap=b.read(self.home/'descendant-reap.json')
        self.assertEqual(child['pgid'],receipt['worker_pid'])
        self.assertEqual(reap,dict(pid=child['pid'],raw_exit=-15,directly_reaped=True))
        self.assertNotIn(child['pid'],observe.process_rows())
        self.case['descendant_reap']=reap
    def test_watchdog_work_deadline_real_child(self):
        limits=dict(b.LIMITS,work_seconds=.4,total_seconds=10.4)
        receipt,_=self.run_controller(limits=limits)
        self.assertEqual(receipt['first_event']['kind'],'external_work_deadline')
        self.assertEqual(receipt['observed_worker_raw_exit'],-15)
        self.assertLess(receipt['elapsed_seconds'],10.4)
    def test_total_deadline_interrupts_postflight_after_direct_reap(self):
        limits=dict(b.LIMITS,work_seconds=.4,total_seconds=.8)
        original=b.read
        def read(path):
            if Path(path).name=='worker-result.json': return dict(status='synthetic-no-training')
            return original(path)
        def prepare(proc,envelope):
            out=self.home/'worker-output';out.mkdir()
            (out/'training-metrics.jsonl').write_text('{"metrics":{"optimizer_steps":1}}\n'*100000)
        def verify(envelope,reg,*,preflight):
            if not preflight: time.sleep(3)
        def slow_accounting(*args):
            time.sleep(3)
            self.fail('full journal accounting after deadline')
        start=time.monotonic()
        with patch.object(b,'read',side_effect=read),patch.object(observe.terminal,'validate_outputs',return_value={'synthetic':True}), patch.object(observe.terminal,'accounting',side_effect=slow_accounting) as accounting:
            receipt,_=self.run_controller('exit-zero',limits=limits,verify_hook=verify,before_return=prepare)
        elapsed=time.monotonic()-start
        accounting.assert_not_called()
        self.assertLess(elapsed,1.5)
        self.case['checks'].update(actual_return_elapsed_seconds=elapsed,
            journal_bytes=(self.home/'worker-output/training-metrics.jsonl').stat().st_size,
            accounting_calls=accounting.call_count)
        self.assertTrue(receipt['deadline_consumed'])
        self.assertEqual(receipt['terminal_accounting_deferred'],'total_deadline_consumed')
        self.assertEqual(receipt['first_event']['kind'],'external_total_deadline')
        self.assertEqual(receipt['observed_worker_raw_exit'],0)
        self.assertLess(receipt['elapsed_seconds'],1.5)
        self.assertNotIn('postflight_inputs_unchanged',receipt)
    def test_total_deadline_during_final_result_read_skips_large_accounting(self):
        limits=dict(b.LIMITS,work_seconds=.4,total_seconds=.8)
        original_read=b.read
        reads=[]
        def prepare(proc,envelope):
            # Valid large journal; the expired finalizer must never open it.
            out=self.home/'worker-output';out.mkdir()
            (out/'worker-result.json').write_text('{}')
            (out/'training-metrics.jsonl').write_text('{"metrics":{"optimizer_steps":1}}\n'*100000)
            proc.wait(timeout=2)
        def read(path):
            if Path(path).name=='worker-result.json':
                reads.append(time.monotonic())
                time.sleep(3)  # Interrupted by the real one-shot total alarm.
            return original_read(path)
        def slow_accounting(*args):
            time.sleep(3)
            return {'should_never_run':True}
        # The exited child takes no cleanup time. Resource sampling fails first;
        # the final result read then consumes the total alarm.
        start=time.monotonic()
        with patch.object(b,'read',side_effect=read), patch.object(b,'worker_resources',side_effect=RuntimeError('first failure before final result read')), patch.object(observe.terminal,'accounting',side_effect=slow_accounting) as accounting:
            receipt,_=self.run_controller('exit-zero',limits=limits,before_return=prepare,
                verify_hook=lambda *a,**k:None)
        elapsed=time.monotonic()-start
        accounting.assert_not_called()
        self.assertEqual(len(reads),1)
        self.assertIn('first failure before final result read',receipt['first_event']['error'])
        self.assertTrue(receipt['deadline_consumed'])
        self.assertEqual(receipt['terminal_accounting_deferred'],'total_deadline_consumed')
        self.assertLess(elapsed,1.5)
        self.assertNotIn('terminal_accounting',receipt)
        self.case['checks'].update(actual_return_elapsed_seconds=elapsed,worker_result_read_count=len(reads),
            journal_bytes=(self.home/'worker-output/training-metrics.jsonl').stat().st_size,
            accounting_calls=accounting.call_count)
    def test_atomic_partial_publication_real_writer(self):
        with (self.home/'writer.log').open('x') as log:
            proc=spawn(command('publish',self.home),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            wait_for(self.home/'partial-ready')
            pending=list(self.home.glob('.committed.json.pending-*'))
            self.assertEqual(len(pending),1)
            self.assertEqual(pending[0].read_text(),'{"payload":')
            self.assertFalse((self.home/'committed.json').exists())
            self.case['checks']['partial_visible_only_at_staging_path']=True
            (self.home/'continue').touch()
            reads=0;end=time.monotonic()+4
            while not (self.home/'committed.json').exists():
                if time.monotonic()>=end: self.fail('publication timeout')
                time.sleep(.001)
            while proc.poll() is None:
                self.assertEqual(b.read(self.home/'committed.json'),dict(payload='complete',writer_pid=proc.pid));reads+=1
                if time.monotonic()>=end: self.fail('writer exit timeout')
            self.assertEqual(proc.wait(timeout=0),0)
            self.assertEqual(b.read(self.home/'committed.json'),dict(payload='complete',writer_pid=proc.pid))
            self.case['checks']['strict_concurrent_reads']=reads+1
            self.assertEqual(list(self.home.glob('.committed.json.pending-*')),[])
    def test_interrupted_partial_publication_never_commits(self):
        with (self.home/'writer.log').open('x') as log:
            proc=spawn(command('publish',self.home),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            wait_for(self.home/'partial-ready')
            observe.signal_owned(proc,{},signal.SIGKILL,dict(cleanup_signals=self.events))
            self.assertEqual(proc.wait(timeout=2),-9)
            self.assertFalse((self.home/'committed.json').exists())
            self.assertEqual(len(list(self.home.glob('.committed.json.pending-*'))),1)
            self.case['checks']['interrupted_staging_retained']=True
    def test_malformed_committed_receipt_fails_closed_without_overwrite(self):
        def malformed(path,value):
            if path.name=='supervisor.claimed': (path.parent/'worker-launch.json').write_text('{malformed')
        receipt,_=self.run_controller(save_hook=malformed)
        path=self.home/'control/worker-launch.json'
        self.assertEqual(path.read_text(),'{malformed')
        with self.assertRaises(json.JSONDecodeError): b.read(path)
        self.assertIn('FileExistsError',receipt['first_event']['error'])
        self.assertEqual(receipt['observed_worker_raw_exit'],-15)
        # A second actual writer also cannot replace any committed first bytes.
        committed=self.home/'committed.json';committed.write_text('{malformed')
        with (self.home/'collision.log').open('x') as log:
            proc=spawn(command('collision',self.home),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            self.assertEqual(proc.wait(timeout=4),1)
        self.assertIn('FileExistsError',(self.home/'collision.log').read_text())
        self.assertEqual(committed.read_text(),'{malformed')
    def test_source_pins_and_strict_committed_json(self):
        manifest=b.read(OWN/'source-manifest.json')
        for name,digest in manifest['files'].items(): self.assertEqual(b.sha(OWN/name),digest)
        paths=[self.home/name for name in ('code','registration','approval','acceptance')]
        for path in paths: path.write_text('{}')
        envelope=dict(pins={str(paths[0]):b.sha(paths[0])},registration=str(paths[1]),registration_sha256=b.sha(paths[1]),
            launch_approval=str(paths[2]),launch_approval_sha256=b.sha(paths[2]),source_acceptance=str(paths[3]),source_acceptance_sha256=b.sha(paths[3]))
        b.check_pins(envelope)
        paths[0].write_text('{"drift":true}')
        with self.assertRaisesRegex(ValueError,'envelope pin drift'): b.check_pins(envelope)
        for content in ('{partial','{"x":1,"x":2}','{"x":NaN}'):
            paths[1].write_text(content)
            with self.assertRaises(ValueError): b.read(paths[1])
        self.case['checks']['manifest_files_checked']=len(manifest['files'])
