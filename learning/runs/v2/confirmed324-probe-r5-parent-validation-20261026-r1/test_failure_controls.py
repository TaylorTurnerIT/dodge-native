"""Synthetic-only failure controls. Every writable fixture stays below test-tmp."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import build_registration
import probe
import supervisor_cli as supervisor
from test_probe import FakeTorch

RUN=Path(__file__).absolute().parent
BASE=RUN.parent

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,obj): Path(path).write_text(json.dumps(obj,sort_keys=True))
def fixture(root,mode='normal'):
    cache=root/'cache'; cache.mkdir()
    reg=build_registration.build(state_path=root/'state.json',expected_lease={'lease_id':'synthetic-owned'},marker_path=root/'marker',cancel_path=root/'cancel',output_path=root/'out',python_path=sys.executable,runtime_root=root,empty_cache_path=cache,expected_venv_prefix=sys.prefix)
    reg.update(status='synthetic_test_only',authority='synthetic_test_only',run_id='synthetic-owned')
    # Frozen files are read/copy sources only. Faults always hit these owned copies.
    for name in ('checkpoint','parent_receipt','vectors','acceptance'):
        dest=root/(name+'.input'); shutil.copyfile(reg[name+'_path'],dest); reg[name+'_path']=str(dest)
    fp=root/'fingerprints.py'; shutil.copyfile(reg['source']['fingerprint_path'],fp); reg['source']['fingerprint_path']=str(fp)
    runtime=root/'fake_runtime.py'
    runtime.write_text((RUN/'fake_runtime.py').read_text()+'''\nimport json,signal,time,threading
from pathlib import Path
_ROOT=Path(__file__).parent
_MODE='''+repr(mode)+'''
_BaseTorch=Torch
class Torch(_BaseTorch):
    def get_rng_state(self):
        if _MODE in ('signals','malformed'):
            if not (_ROOT/'ready').exists():
                def term(sig,frame):
                    with (_ROOT/'child-signals').open('a') as f: f.write(str(sig)+'\\n')
                signal.signal(signal.SIGTERM,term)
                (_ROOT/'ready').write_text('ready')
                if _MODE=='malformed':
                    (_ROOT/'checkpoint.input').unlink()
                    (_ROOT/'out'/'worker-heartbeat.json').write_text('{malformed')
                time.sleep(30)
        if _MODE=='cache-file': (_ROOT/'cache'/'unexpected').write_text('unexpected')
        if _MODE=='cache-remove' and (_ROOT/'cache').exists(): (_ROOT/'cache').rmdir()
        if _MODE in ('final-rss','final-mps'): (_ROOT/'captured').write_text('yes')
        return super().get_rng_state()
def memory_sample():
    if (_ROOT/'captured').exists():
        return (6442450945,0) if _MODE=='final-rss' else (0,6442450945)
    return (0,0)
''')
    reg['synthetic_test_dependencies']={'runtime_path':str(runtime),'runtime_sha256':sha(runtime)}
    write(root/'state.json',{'active_inference_diagnostic':reg['expected_lease'],'active_long_campaign':None,'active_long':None,'active_inference':None})
    write(root/'registration.json',reg)
    return reg

def driver(root,mode):
    """Run real supervisor/worker with test-only Python instrumentation, never CLI hooks."""
    rp=root/'registration.json'; reg=json.loads(rp.read_text()); regsha=sha(rp)
    original_handlers={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT)}
    original_primitive_loader=supervisor.verified_primitives
    original_inventory=supervisor.inventory
    original_postflight=supervisor.integrity_postflight
    cleanup_copy=root/'cleanup-source.py'; shutil.copyfile(supervisor.PRIMITIVES,cleanup_copy); supervisor.PRIMITIVES=cleanup_copy
    original_exclusive=supervisor.exclusive_json
    evidence={'mode':mode}
    def send_all():
        for sig in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT): os.kill(os.getpid(),sig)
    def load():
        ns=original_primitive_loader()
        if mode=='signals':
            aggregate=ns['aggregate_rss']; terminate=ns['terminate_bounded']
            def trigger(pid):
                deadline=time.monotonic()+4
                while not (root/'ready').exists() and time.monotonic()<deadline: time.sleep(.01)
                if not (root/'ready').exists(): raise RuntimeError('synthetic child not ready')
                os.kill(os.getpid(),signal.SIGTERM)
                return aggregate(pid)
            def cleanup(proc,deadline):
                send_all()
                # More real signals arrive during the imported polling/reap primitive.
                sender=subprocess.Popen([sys.executable,'-B','-c','import os,signal,time; time.sleep(.15); os.kill('+str(os.getpid())+',signal.SIGHUP); time.sleep(.15); os.kill('+str(os.getpid())+',signal.SIGINT)'],env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(root/'cache')))
                try: return terminate(proc,deadline)
                finally: sender.wait(timeout=2)
            ns['aggregate_rss']=trigger; ns['terminate_bounded']=cleanup
        if mode=='malformed':
            aggregate=ns['aggregate_rss']
            def malformed(pid):
                deadline=time.monotonic()+4
                while (root/'checkpoint.input').exists() and time.monotonic()<deadline: time.sleep(.01)
                (root/'out'/'worker-heartbeat.json').write_text('{malformed')
                return aggregate(pid)
            ns['aggregate_rss']=malformed
        return ns
    def postflight(*args):
        if mode=='post-cache-file': (root/'cache'/'unexpected').write_text('unexpected')
        if mode=='post-cache-remove': (root/'cache').rmdir()
        if mode=='post-integrity':
            (root/'checkpoint.input').unlink(); cleanup_copy.unlink()
            (root/'fingerprints.py').write_text('changed owned fingerprint')
        return original_postflight(*args)
    def inv(path):
        if mode=='signals': send_all()
        if mode=='inventory':
            # Exercise the real per-file inventory guard, not a replacement receipt.
            original_sha=supervisor.sha
            def damaged(p):
                if Path(p).name=='worker.log': raise OSError('synthetic inventory read failure')
                return original_sha(p)
            with patch.object(supervisor,'sha',damaged): return original_inventory(path)
        return original_inventory(path)
    def exclusive(path,obj,on_created=None):
        if Path(path)==Path(reg['one_shot_marker']):
            if mode=='preexisting': Path(path).write_text('preexisting-race')
            if mode in ('claim-open-signal','claim-write','claim-fsync'):
                real_open=os.open; real_fdopen=os.fdopen; real_fsync=os.fsync
                marker_fd=[]
                def opened(p,flags,*args,**kwargs):
                    fd=real_open(p,flags,*args,**kwargs)
                    if Path(p)==Path(path):
                        marker_fd.append(fd)
                        if mode=='claim-open-signal': send_all()
                    return fd
                class BrokenWrite:
                    def __init__(self,f): self.f=f
                    def __enter__(self): return self
                    def __exit__(self,*args): self.f.close()
                    def write(self,raw): self.f.write(raw[:11]); self.f.flush(); raise OSError('synthetic marker write failure')
                def fdopen(fd,*args,**kwargs):
                    f=real_fdopen(fd,*args,**kwargs)
                    return BrokenWrite(f) if fd in marker_fd and mode=='claim-write' else f
                def fsync(fd):
                    if fd in marker_fd and mode=='claim-fsync': raise OSError('synthetic marker fsync failure')
                    return real_fsync(fd)
                with patch.object(os,'open',opened),patch.object(os,'fdopen',fdopen),patch.object(os,'fsync',fsync):
                    return original_exclusive(path,obj,on_created)
        if mode=='signals' and Path(path).name=='outer-receipt.json': send_all()
        return original_exclusive(path,obj,on_created)
    try:
        with patch.object(supervisor,'verified_primitives',load),patch.object(supervisor,'inventory',inv),patch.object(supervisor,'integrity_postflight',postflight),patch.object(supervisor,'exclusive_json',exclusive):
            supervisor.execute(rp,regsha,RUN/'worker_cli.py')
        evidence['returned']=True
    except Exception as e: evidence['error']=str(e)
    evidence['handlers_restored']=all(signal.getsignal(s)==h for s,h in original_handlers.items())
    write(root/'driver-result.json',evidence)

class FailureControls(unittest.TestCase):
    def run_case(self,mode,worker_mode=None):
        # Retain each control's inputs, logs, marker and partial receipts as evidence.
        root=Path(tempfile.mkdtemp(prefix=mode+'-',dir=RUN/'test-tmp'))
        reg=fixture(root,worker_mode or mode)
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=str(root/'cache'),RNG_PROBE_SYNTHETIC_TEST='1')
        result=subprocess.run([sys.executable,'-B',str(Path(__file__).absolute()),'--driver',str(root),mode],env=env,capture_output=True,text=True,timeout=22)
        (root/'driver.log').write_text(result.stdout+result.stderr)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        evidence=json.loads((root/'driver-result.json').read_text()); self.assertTrue(evidence['handlers_restored'])
        outer=root/'out'/'outer-receipt.json'
        return root,reg,evidence,(json.loads(outer.read_text()) if outer.exists() else None)
    def test_repeated_signals_cleanup_finalization_real_child(self):
        root,reg,evidence,rec=self.run_case('signals')
        self.assertEqual(rec['raw_worker_exit_code'],-signal.SIGKILL)
        self.assertTrue(rec['process_group_absent'])
        self.assertEqual(rec['stop_reason'],'supervisor_signal:SIGTERM')
        # Nine pre-boundary signals remain observations. Three receipt-publication
        # signals are deliberately ignored after the finalization commit boundary.
        self.assertEqual(rec['handled_signals'],['SIGTERM','SIGTERM','SIGHUP','SIGINT','SIGHUP','SIGINT','SIGTERM','SIGHUP','SIGINT'])
        self.assertIn('probe failed: supervisor_signal:SIGTERM',evidence['error'])
        self.assertEqual((root/'child-signals').read_text().splitlines(),[str(signal.SIGTERM)])
        self.assertEqual(rec['postflight']['cleanup_source']['status'],'pass')
        self.assertEqual(rec['postflight']['interpreter_identity']['status'],'pass')
        self.assertEqual(rec['status'],'partial_failure_preserved')
    def test_claim_signal_between_open_and_assignment(self):
        root,reg,evidence,rec=self.run_case('claim-open-signal')
        self.assertTrue(rec['claim_created']); self.assertTrue(rec['claim_write_completed'])
        self.assertIsNone(rec['raw_worker_exit_code']); self.assertIn('supervisor_signal',rec['stop_reason'])
        self.assertTrue((root/'marker').exists())
    def test_claim_partial_write_preserves_receipt(self):
        root,reg,evidence,rec=self.run_case('claim-write')
        self.assertTrue(rec['claim_created']); self.assertFalse(rec['claim_write_completed'])
        self.assertEqual((root/'marker').stat().st_size,11)
        self.assertEqual(rec['postflight']['marker']['status'],'fail')
        self.assertIn('synthetic marker write failure',rec['stop_reason'])
    def test_claim_fsync_failure_preserves_receipt(self):
        root,reg,evidence,rec=self.run_case('claim-fsync')
        self.assertTrue(rec['claim_created']); self.assertFalse(rec['claim_write_completed'])
        self.assertEqual(rec['postflight']['marker']['status'],'pass')
        self.assertIn('synthetic marker fsync failure',rec['stop_reason'])
    def test_preexisting_marker_not_claimed(self):
        root,reg,evidence,rec=self.run_case('preexisting')
        self.assertIsNone(rec); self.assertEqual((root/'marker').read_text(),'preexisting-race')
        self.assertIn('marker not claimed',evidence['error'])
    def test_cache_file_worker_and_outer_reject(self):
        root,reg,evidence,rec=self.run_case('cache-file')
        self.assertEqual(rec['postflight']['cache']['status'],'fail')
        self.assertFalse((root/'out'/'COMMITTED.json').exists())
        self.assertIn('owned empty cache check failed',(root/'out'/'worker.log').read_text())
    def test_cache_removal_worker_and_outer_reject(self):
        root,reg,evidence,rec=self.run_case('cache-remove')
        self.assertEqual(rec['postflight']['cache']['status'],'fail')
        self.assertFalse((root/'out'/'COMMITTED.json').exists())
        self.assertIn('owned empty cache check failed',(root/'out'/'worker.log').read_text())
    def test_malformed_heartbeat_missing_pin_all_checks_continue(self):
        root,reg,evidence,rec=self.run_case('malformed')
        self.assertIn('supervisor_exception:',rec['stop_reason'])
        self.assertEqual(rec['postflight']['input:checkpoint']['status'],'unavailable')
        for name in ('input:parent_receipt','input:vectors','input:acceptance','cleanup_source','cache','marker','interpreter','lease','cancel','process_absence'):
            self.assertEqual(rec['postflight'][name]['status'],'pass',name)
        self.assertIn('input:checkpoint',rec['failed_checks'])
        self.assertEqual(len(rec['postflight']),19)
    def test_outer_cache_file_after_successful_worker(self):
        root,reg,evidence,rec=self.run_case('post-cache-file','normal')
        self.assertEqual(rec['raw_worker_exit_code'],0)
        self.assertEqual(rec['postflight']['committed_output']['status'],'pass')
        self.assertEqual(rec['postflight']['cache']['status'],'fail')
        self.assertEqual(rec['status'],'partial_failure_preserved')
    def test_outer_cache_removal_after_successful_worker(self):
        root,reg,evidence,rec=self.run_case('post-cache-remove','normal')
        self.assertEqual(rec['raw_worker_exit_code'],0)
        self.assertEqual(rec['postflight']['committed_output']['status'],'pass')
        self.assertEqual(rec['postflight']['cache']['status'],'fail')
        self.assertEqual(rec['status'],'partial_failure_preserved')
    def test_cleanup_source_and_other_missing_pins_all_recorded(self):
        root,reg,evidence,rec=self.run_case('post-integrity','normal')
        self.assertEqual(rec['postflight']['input:checkpoint']['status'],'unavailable')
        self.assertEqual(rec['postflight']['cleanup_source']['status'],'unavailable')
        self.assertEqual(rec['postflight']['source:fingerprint']['status'],'fail')
        self.assertEqual(rec['postflight']['lease']['status'],'pass')
        self.assertEqual(rec['postflight']['process_absence']['status'],'pass')
        self.assertEqual(len(rec['postflight']),19)
        self.assertEqual(rec['status'],'partial_failure_preserved')
    def test_inventory_failure_does_not_suppress_receipt(self):
        root,reg,evidence,rec=self.run_case('inventory','normal')
        self.assertEqual(rec['stop_reason'],'inventory_failed'); self.assertTrue(rec['inventory_errors'])
        self.assertTrue(rec['process_group_absent'])
    def test_final_forced_rss_sample_blocks_publication(self):
        root,reg,evidence,rec=self.run_case('final-rss')
        self.assertFalse((root/'out'/'COMMITTED.json').exists()); self.assertNotEqual(rec['raw_worker_exit_code'],0)
        self.assertIn('heartbeat resource cap exceeded',(root/'out'/'worker.log').read_text())
    def test_final_forced_mps_sample_blocks_publication(self):
        root,reg,evidence,rec=self.run_case('final-mps')
        self.assertFalse((root/'out'/'COMMITTED.json').exists()); self.assertNotEqual(rec['raw_worker_exit_code'],0)
        self.assertIn('heartbeat resource cap exceeded',(root/'out'/'worker.log').read_text())
    def test_prefix_asserted_before_claim(self):
        with tempfile.TemporaryDirectory(dir=RUN/'test-tmp') as d:
            root=Path(d); reg=fixture(root); reg['runtime']['expected_venv_prefix']=str(root/'wrong-venv'); write(root/'registration.json',reg)
            with patch.dict(os.environ,RNG_PROBE_SYNTHETIC_TEST='1'):
                with self.assertRaisesRegex(RuntimeError,'prefix/version'): supervisor.execute(root/'registration.json',sha(root/'registration.json'),RUN/'worker_cli.py')
            self.assertFalse((root/'marker').exists())
    def test_production_cannot_enable_synthetic_dependencies(self):
        with tempfile.TemporaryDirectory(dir=RUN/'test-tmp') as d:
            root=Path(d); reg=fixture(root); reg.update(status='parent_registered',authority='parent_approved_one_shot'); write(root/'registration.json',reg)
            with patch.dict(os.environ,RNG_PROBE_SYNTHETIC_TEST='1'):
                with self.assertRaisesRegex(RuntimeError,'top-level fields'): supervisor.execute(root/'registration.json',sha(root/'registration.json'),RUN/'worker_cli.py')
            self.assertFalse((root/'marker').exists())

class ConsumerControls(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='consumer-',dir=RUN/'test-tmp'))
        self.reg=fixture(self.root)
        self.good=probe.capture_references(vectors=self.reg['vectors'],study_id=self.reg['study_id'],torch_api=FakeTorch(),numpy_version='2.5.4',python_version=sys.version.split()[0],torch_version='2.14.1',backend_available=True,fingerprint=lambda raw:hashlib.sha256(raw).hexdigest())
    def bundle(self,mutate=None):
        obj=copy.deepcopy(self.good)
        if mutate: mutate(obj)
        out=Path(self.reg['output_dir']); probe.atomic_publish(out,obj)
        # Manifest hashes are recomputed after substitution, as an independent writer could do.
        return out
    def rehash(self,out):
        commit=json.loads((out/'COMMITTED.json').read_text())
        for item in commit['files']: item['sha256']=sha(out/item['path'])
        write(out/'COMMITTED.json',commit)
    def test_valid_bundle_passes(self):
        self.bundle(); self.assertEqual(supervisor.committed_check(self.reg)['replicas'],3)
    def test_substituted_checkpoint_binding(self):
        self.bundle(lambda obj:[row.update(accepted_checkpoint_sha256='0'*64) for row in obj['references']])
        with self.assertRaisesRegex(ValueError,'parent binding'): supervisor.committed_check(self.reg)
    def test_substituted_parent_receipt_binding(self):
        self.bundle(lambda obj:[row.update(parent_receipt_sha256='0'*64) for row in obj['references']])
        with self.assertRaisesRegex(ValueError,'parent binding'): supervisor.committed_check(self.reg)
    def test_substituted_backend_binding(self):
        self.bundle(lambda obj:[row.update(backend='cpu') for row in obj['references']])
        with self.assertRaisesRegex(ValueError,'backend/torch'): supervisor.committed_check(self.reg)
    def test_substituted_torch_binding(self):
        self.bundle(lambda obj:[row.update(torch_version='substituted') for row in obj['references']])
        with self.assertRaisesRegex(ValueError,'backend/torch'): supervisor.committed_check(self.reg)
    def aggregate_fault(self,key,value,error):
        out=self.bundle(); agg=json.loads((out/'receipt.json').read_text()); agg[key]=value; write(out/'receipt.json',agg); self.rehash(out)
        with self.assertRaisesRegex(ValueError,error): supervisor.committed_check(self.reg)
    def test_aggregate_reference_mismatch_rehashed(self): self.aggregate_fault('references',list(reversed(self.good['references'])),'references differ')
    def test_aggregate_runtime_mismatch_rehashed(self): self.aggregate_fault('runtime',dict(self.good['runtime'],numpy='wrong'),'runtime mismatch')
    def test_aggregate_study_mismatch_rehashed(self): self.aggregate_fault('study_id','wrong','schema/status/study')
    def test_aggregate_schema_mismatch_rehashed(self): self.aggregate_fault('schema','wrong','schema/status/study')
    def test_extra_replica_rejected(self):
        out=self.bundle(); shutil.copyfile(out/'replica-1.json',out/'replica-4.json')
        with self.assertRaisesRegex(ValueError,'replica inventory'): supervisor.committed_check(self.reg)

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--driver': driver(Path(sys.argv[2]),sys.argv[3])
    else: unittest.main()
