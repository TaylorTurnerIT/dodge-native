"""Focused stdlib fixture controls. Fixtures never claim real ML identity."""
from pathlib import Path
import ast
import copy
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch
import boundary_integrity as b
import lifecycle as life
import long_d2 as c
import long_d2_executor as e
import source_equality
H=Path(__file__).resolve().parent
ATTEMPT=Path(os.environ['VALIDATION_DIR'])


def descriptor(at,outcome='safety_stop',role='test'):
    return dict(timestamp=at,kind='test_observation',outcome=outcome,role=role,timing_basis='fixture_source_clock',signal=None)


class Tests(unittest.TestCase):
    def setUp(self):
        self.d=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=ATTEMPT))
        self.stack=[]

    def fixture(self):
        original=self.d/'original';root=self.d/'capsule';root.mkdir();original.mkdir()
        for name in ('python/dodge_rl','python/tests','crates'):(original/name).mkdir(parents=True)
        active=original/'active.txt';active.write_text('active\n')
        archive=original/'archive.txt';archive.write_text('archive\n')
        native=original/'native';native.mkdir();so=native/'library.so';so.write_bytes(b'fixture native bytes, never imported')
        prepare=root/c.PREPARE_REL;prepare.mkdir(parents=True)
        B={str(active):c.sha(active)};R={str(so):c.sha(so)};A={str(archive):c.sha(archive)}
        c.save(prepare/'classification.json',{'B':B})
        c.save(prepare/'native-manifest.json',{'files':R,'roots':[str(native)],'discovered_members':[str(so)]})
        c.save(prepare/'archive-manifest.json',{'files':A})
        identity=dict(classification_sha256=c.sha(prepare/'classification.json'),class_manifest_hashes={'B':'b'*64,'R':'c'*64,'A':'d'*64},base_registered_identity={'sources':{}})
        files={str(x.relative_to(root)):c.sha(x) for x in root.rglob('*') if x.is_file()}
        c.save(root/'capsule-manifest.json',dict(version='long_d2_capsule_v1',files=files))
        for p in root.rglob('*'):
            if p.is_file():p.chmod(0o444)
        for p in sorted((x for x in root.rglob('*') if x.is_dir()),key=lambda x:len(x.parts),reverse=True):p.chmod(0o555)
        root.chmod(0o555)
        return original,root,({}, {}, {},identity,B,{}),active,archive,so

    def test_01_source_equality_and_forced_sites(self):
        source_equality.check(self.d)
        old=ast.parse((H.parent/'postovernight-long-D2-guard-prepare-r1/long_d2.py').read_text())
        new=ast.parse((H/'long_d2.py').read_text())
        def forced(tree):return sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='check' and any(k.arg=='force' and isinstance(k.value,ast.Constant) and k.value.value is True for k in n.keywords) for n in ast.walk(tree))
        self.assertEqual(forced(old),forced(new))
        text=(H/'long_d2.py').read_text()
        self.assertIn("imported['identity'].check_frozen",text)
        self.assertIn("runtime = integrity.runtime_check(identity,ORIGINAL_ROOT)",text)
        self.assertNotIn('Full input verification gap exceeded',text)

    def test_02_boundary_archive_and_native_bytes(self):
        original,root,ctx,active,archive,so=self.fixture()
        with patch.object(c,'ORIGINAL_ROOT',original):
            first=b.verify(ctx,root,endpoint='preflight');self.assertEqual(first['counts'],{'B':1,'R':1,'A':1})
            archive.write_text('corruption')
            b.verify(ctx,root) # archive is intentionally absent from hotpath
            with self.assertRaisesRegex(c.Stop,'Input hash mismatch'):b.verify(ctx,root,endpoint='postflight')
            so.write_bytes(b'corruption')
            with self.assertRaisesRegex(c.Stop,'Input hash mismatch'):b.verify(ctx,root,endpoint='preflight')

    def test_03_persistent_mutation_next_boundary(self):
        original,root,ctx,active,archive,so=self.fixture()
        with patch.object(c,'ORIGINAL_ROOT',original):
            b.verify(ctx,root);active.write_text('persistent')
            with self.assertRaisesRegex(c.Stop,'Input hash mismatch'):b.verify(ctx,root)

    def test_04_transient_revert_limitation(self):
        original,root,ctx,active,archive,so=self.fixture()
        with patch.object(c,'ORIGINAL_ROOT',original):
            b.verify(ctx,root);old=active.read_bytes();active.write_bytes(b'transient');active.write_bytes(old)
            self.assertEqual(b.verify(ctx,root)['verdict'],'passed')

    def test_05_membership_escape_conflict(self):
        original,root,ctx,active,archive,so=self.fixture()
        with patch.object(c,'ORIGINAL_ROOT',original):
            (original/'python/dodge_rl/extra.py').write_text('x=1')
            with self.assertRaisesRegex(c.Stop,'Project membership'):b.verify(ctx,root)
        with self.assertRaisesRegex(c.Stop,'Unsafe capsule member'):c.safe_member(root,'../escape')
        alias=self.d/'alias';alias.symlink_to(active)
        with self.assertRaisesRegex(c.Stop,'Conflicting canonical'):b.merge_bindings({str(active):'a'*64},{str(alias):'b'*64})
        with self.assertRaisesRegex(c.Stop,'Conflicting path'):b.merge_bindings({str(active):'a'*64},{str(active):'b'*64})

    def test_06_native_membership_addition(self):
        original,root,ctx,active,archive,so=self.fixture()
        (so.parent/'extra.so').write_bytes(b'extra')
        with patch.object(c,'ORIGINAL_ROOT',original),self.assertRaisesRegex(c.Stop,'native membership'):b.verify(ctx,root,endpoint='preflight')

    def test_07_safety_only_callbacks_and_synchronous_force(self):
        observed=[];clock=[10.0]
        g=c.Guard(100,lambda:None,lambda:observed.append('fresh'),None,clock=lambda:clock[0],rss=lambda:1,peak=lambda:1)
        g.check();g.sample(full=False);g.full_check(False);self.assertEqual(observed,[])
        g.check(force=True);g.check(force=True);self.assertEqual(observed,['fresh','fresh'])
        self.assertEqual([r['sequence'] for r in g.boundaries],[0,1]);self.assertIsNone(g.verify_thread)
        self.assertTrue(all(r['verdict']=='passed' for r in g.boundaries))

    def test_08_resource_cap_and_gap_unchanged(self):
        for rss,mps in ((c.LIMIT+1,0),(0,c.LIMIT+1)):
            g=c.Guard(time.monotonic()+5,lambda:None,lambda:None,None,rss=lambda:rss,peak=lambda:0,mps=lambda:mps)
            with self.assertRaisesRegex(c.Stop,'RSS or MPS'):g.sample(full=False)
        clock=[10.];g=c.Guard(100,lambda:None,lambda:None,None,clock=lambda:clock[0],rss=lambda:1,peak=lambda:1)
        g.sample(full=False);clock[0]+=.51
        with self.assertRaisesRegex(c.Stop,'sampling gap'):g.sample(full=False)

    def test_09_cancel_defer_guard_alarm_order(self):
        now=time.monotonic();latch=life.ProcessLatch();latch.deadline=now+100;latch.phase='DEFER'
        with patch.object(life,'ACTIVE',latch),patch.object(life.time,'monotonic',return_value=now):latch.record(signal.SIGINT)
        guard=types.SimpleNamespace(failure=c.Stop('guard','safety_stop'),failure_at=now+1)
        with patch.object(life,'ACTIVE',latch):self.assertEqual(c.primary_error(guard.failure,guard).outcome,'cancelled')
        latch.first_cancel_at=now+2;latch.first_at=now+2
        with patch.object(life,'ACTIVE',latch):self.assertEqual(c.primary_error(guard.failure,guard).outcome,'safety_stop')
        latch.first_alarm_at=now-1
        with patch.object(life,'ACTIVE',latch):self.assertEqual(c.primary_error(guard.failure,guard).outcome,'wall_guard')

    def test_10_late_earlier_ACK_tightens_without_reset(self):
        now=time.monotonic();pool=life.FailurePool(now-5)
        pool.fail('local',now-2,descriptor(now-2));first=pool.until
        pool.fail('peer',now-3,descriptor(now-3,'cancelled','peer'),peer=True)
        self.assertLess(pool.until,first);self.assertEqual(pool.first_local['timestamp'],now-2)
        self.assertEqual(pool.first_global['outcome'],'cancelled')
        until=pool.until;pool.fail('cleanup signal',now,descriptor(now,'cancelled'))
        self.assertEqual(pool.until,until)
        with self.assertRaisesRegex(c.Stop,'Absolute deadline'):life.remaining(now-1)

    def test_11_failed_ACK_forbids_persistence(self):
        result=c.outcome_fields('cancelled');permission=dict(failed=True,ack_failed=True,acknowledged_until=None)
        with patch.object(life,'POOL',life.FailurePool(time.monotonic())),self.assertRaisesRegex(c.Stop,'Unacknowledged'):
            c.worker_write_permission(types.SimpleNamespace(started=time.monotonic()),result,permission)

    def test_12_inner_outer_mandatory_before_partial_telemetry(self):
        for role in ('inner','outer'):
            directory=self.d/role;directory.mkdir();receipt=directory/'failure.json';timing=directory/'timing.jsonl'
            events=[]
            class Guard:
                failure=None
                def persist_timing(self,path,*args):
                    events.append('timing');Path(path).write_text('partial');raise OSError('injected telemetry error')
            real=c.replace_json
            def replace(path,value):events.append('mandatory');real(path,value)
            with patch.object(c,'replace_json',replace):c.failure_publication(receipt,{'accepted':False},time.monotonic()+2,Guard(),timing)
            self.assertEqual(events,['mandatory','timing']);self.assertFalse(c.read_json(receipt)['accepted']);self.assertEqual(timing.read_text(),'partial')
            self.assertIn('failure_publication(', (H/('long_d2.py' if role=='inner' else 'long_d2_executor.py')).read_text())

    def test_13_expired_normal_observer_does_not_block_failed_receipt(self):
        now=time.monotonic();pool=life.FailurePool(now);pool.fail('failure',now)
        def expired():raise c.Stop('expired normal observer','wall_guard')
        with patch.object(life,'POOL',pool),patch.object(c,'HASH_OBSERVER',expired):
            self.assertTrue(c.mandatory_failure(self.d/'failed.json',{'accepted':False},pool.until))
        self.assertFalse(c.read_json(self.d/'failed.json')['accepted'])

    def test_14_normal_optional_diagnostic_error(self):
        class Guard:
            failure=None
            def persist_timing(self,*args):raise OSError('optional error')
        with patch.object(life,'POOL',None):value=c.optional_timing(Guard(),self.d/'timing',time.monotonic()+2)
        self.assertEqual(value['status'],'partial_or_unavailable')
        c.save(self.d/'mandatory-success.json',{'mandatory':True})

    def policy(self):
        cache=self.d/'cache';cache.mkdir()
        return dict(pycache_prefix=str(cache),sys_path_before_project=list(sys.path),sys_path_after_project=list(sys.path),
                    environment={},interpreter=str(Path(sys.executable).resolve()),python=sys.version,torch='fixture',numpy='fixture')

    def test_15_wrong_lazy_native_project_paths_cache(self):
        policy=self.policy();identity=dict(runtime_policy=policy,native_origins={})
        with patch.object(sys,'pycache_prefix',policy['pycache_prefix']),patch.dict(os.environ,{'PYTHONPYCACHEPREFIX':policy['pycache_prefix'],'PYTHONDONTWRITEBYTECODE':'1'}):
            self.assertEqual(b.runtime_check(identity,self.d,modules={})['verdict'],'passed')
            with self.assertRaisesRegex(c.Stop,'sys.path'):b.runtime_check(identity,self.d,modules={},paths=['wrong'])
            with self.assertRaisesRegex(c.Stop,'Unregistered loaded native'):b.runtime_check(identity,self.d,modules={'lazy':types.SimpleNamespace(__file__='/wrong/lazy.so')})
            with self.assertRaisesRegex(c.Stop,'Project __path__'):b.runtime_check(identity,self.d,modules={'dodge_rl.lazy':types.SimpleNamespace(__path__=['/wrong'])},imported=False)
            (Path(policy['pycache_prefix'])/'pollution.pyc').write_bytes(b'x')
            with self.assertRaisesRegex(c.Stop,'cache prefix polluted'):b.cache_check(policy)

    def test_16_existing_exact_project_origin_helper(self):
        module=self.d/'module.py';module.write_text('x=1');mirror=self.d/'mirror.py';mirror.write_bytes(module.read_bytes())
        identity={'legacy_module_origins':{str(module):{'sha256':c.sha(module),'mirror':'mirror.py'}}}
        self.assertTrue(c.check_module_origins(identity,self.d,{'dodge_rl.lazy':types.SimpleNamespace(__file__=str(module))}))
        with self.assertRaisesRegex(c.Stop,'Unexpected legacy module origin'):c.check_module_origins(identity,self.d,{'dodge_rl.lazy':types.SimpleNamespace(__file__='/wrong/module.py')})

    def test_17_stale_old_pyc_fresh_prefix_control(self):
        source=self.d/'toy.py';source.write_text('value="WRONG"\n')
        code='import py_compile,sys;py_compile.compile(sys.argv[1],doraise=True)'
        subprocess.run([sys.executable,'-B','-c',code,str(source)],check=True,capture_output=True)
        stat=source.stat();source.write_text('value="RIGHT"\n');os.utime(source,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        child='import sys;sys.path.insert(0,sys.argv[1]);import toy;print(toy.value)'
        env=dict(os.environ);env.pop('PYTHONPYCACHEPREFIX',None)
        old=subprocess.run([sys.executable,'-B','-c',child,str(self.d)],env=env,check=True,text=True,capture_output=True)
        cache=self.d/'fresh';cache.mkdir();env.update(PYTHONPYCACHEPREFIX=str(cache),PYTHONDONTWRITEBYTECODE='1')
        fresh=subprocess.run([sys.executable,'-B','-c',child,str(self.d)],env=env,check=True,text=True,capture_output=True)
        self.assertEqual(old.stdout.strip(),'WRONG');self.assertEqual(fresh.stdout.strip(),'RIGHT');self.assertFalse(any(cache.iterdir()))
        c.save(self.d/'pyc-control.json',{'old_B_only':old.stdout.strip(),'fresh_prefix':fresh.stdout.strip(),'raw_exits':[old.returncode,fresh.returncode]})

    def summary_fixture(self):
        registration={k:'a'*64 for k in ('protocol_sha256','config_sha256','identity_sha256','classification_sha256','reservation_sha256')}
        registration.update(class_manifest_hashes={'B':'b'*64,'R':'c'*64,'A':'d'*64},class_counts={'B':1,'R':1,'A':1})
        worker={k:registration[k] for k in ('protocol_sha256','config_sha256','identity_sha256','classification_sha256')}
        worker.update(schema='long_d2_worker_integrity_summary_v1',manifests=registration['class_manifest_hashes'],boundary_count=1,boundaries=[dict(sequence=0,verdict='passed')],final_live_legacy=True,final_runtime=dict(verdict='passed',cache=dict(empty=True)),first_local_failure=None,first_global_failure=None)
        summary={k:registration[k] for k in ('protocol_sha256','config_sha256','identity_sha256','classification_sha256','reservation_sha256')}
        summary.update(schema='long_d2_compact_integrity_summary_v1',manifests=registration['class_manifest_hashes'],worker=worker,first_local_failure=None,first_global_failure=None)
        for label in ('preflight','postflight'):summary[label]=dict(role='outer_'+label,verdict='passed',counts=registration['class_counts'],classification_sha256=registration['classification_sha256'],manifests=registration['class_manifest_hashes'])
        return registration,summary

    def test_18_summary_discriminates_missing_postflight_and_fake_gate(self):
        registration,summary=self.summary_fixture();self.assertTrue(b.summary_valid(summary,registration))
        for field in ('postflight','worker','classification_sha256'):
            bad=copy.deepcopy(summary);bad.pop(field);self.assertFalse(b.summary_valid(bad,registration))
        bad=copy.deepcopy(summary);bad['postflight']['verdict']='failed';bad['fake_gate_passed']=True
        self.assertFalse(b.summary_valid(bad,registration))
        bad=copy.deepcopy(summary);bad['worker']['boundaries'][0]['verdict']='failed';self.assertFalse(b.summary_valid(bad,registration))

    def test_19_raw_wall_stale_receipt_and_summary_reject(self):
        receipt=dict(schema='long_d2_outer_acceptance_v2',accepted=True,expected_exit_code=0,experiment_status='complete',outcome='D2_progress_gate_passed',teacher_qualified=False,training_parent_eligible=False)
        for raw,wall in ((1,1),(None,1),(0,float('nan')),(0,7200.001),(0,1)):
            self.assertFalse(e.accept_observed(receipt,raw,wall))
        receipt['schema']='long_d2_outer_acceptance_v1';self.assertFalse(e.accept_observed(receipt,0,1))

    def test_20_lease_cancel_wrong_owner_and_normal_deadline(self):
        protocol=c.registered_protocol(c.ORIGINAL_ROOT/c.PROTOCOL_REL)
        lease=c.expected_lease(protocol,'a'*64,'b'*64,self.d,'c'*64);path=self.d/'state.json'
        c.save(path,{'active_long_campaign':lease});self.assertEqual(c.assert_lease(path,lease),lease)
        bad=dict(lease,cancel_requested=True);c.replace_json(path,{'active_long_campaign':bad})
        with self.assertRaisesRegex(c.Stop,'Parent requested cancellation'):c.assert_lease(path,lease)
        c.replace_json(path,{'active_long_campaign':None})
        with self.assertRaisesRegex(c.Stop,'lease key set'):c.assert_lease(path,lease)
        g=c.Guard(time.monotonic()-1,lambda:None,lambda:None,None)
        with self.assertRaisesRegex(c.Stop,'Absolute wall guard'):g.check()

if __name__=='__main__':unittest.main(verbosity=2,failfast=True)
