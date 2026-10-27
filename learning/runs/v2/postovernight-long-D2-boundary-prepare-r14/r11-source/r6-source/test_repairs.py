"""Targeted stdlib repair discriminators. No OS lifecycle campaign or ML imports."""
from pathlib import Path
import ast
import copy
import errno
import json
import math
import os
import signal
import socket
import stat
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
import lifecycle as life
import long_d2 as c
import long_d2_executor as e
import boundary_integrity as b
from fixture_guards import validate_fixture
H=Path(__file__).resolve().parent
A=Path(os.environ['VALIDATION_DIR'])
NS=types.SimpleNamespace


def desc(at,outcome='publication_failure',role='worker'):
    return dict(timestamp=at,kind='source',outcome=outcome,role=role,timing_basis='test_actual_observation',signal=None)


def latch(deadline=10000.):
    return NS(first_at=None,first_cancel_at=None,first_alarm_at=None,deadline=deadline,
              cancellation_requests=0,requested_signal=None,alarm_seen=False,phase='NORMAL')


def execution(t0=90.):
    x=e.Execution.__new__(e.Execution)
    x.t0=t0;x.pool=life.FailurePool(t0);x.latch=latch();x.guard=NS(failure=None,failure_at=None,last_sample=100.)
    x.groups={};x.child=None;x.worker_wait=None;x.inner_ready=None;x.worker_ready=None
    x.forwarded=[];x.events=[];x.ipc_lock=threading.RLock();x.super_channel=x.worker_channel=None
    x.recovery_proven=False;x.cleanup_complete=False;x.pump=lambda:None
    return x


class Repairs(unittest.TestCase):
    def setUp(self):
        self.d=Path(tempfile.mkdtemp(dir=A,prefix=self._testMethodName+'-'))

    def test_all_sources_parse_and_forced_checks_unchanged(self):
        for path in H.glob('*.py'):
            compile(path.read_text(),str(path),'exec')
        old=(H/'original-source/long_d2.py').read_text();new=(H/'long_d2.py').read_text()
        for text in ("imported['identity'].check_frozen",'runtime = integrity.runtime_check(identity,ORIGINAL_ROOT)',"legacy_module_origins"):
            self.assertEqual(old.count(text),new.count(text))
        self.assertEqual((H/'boundary_integrity.py').read_bytes(),(H/'original-source/boundary_integrity.py').read_bytes())

    def test_worker_plain_exception_observation_uses_actual_call(self):
        pool=life.FailurePool(90.);permission=dict(failed=False,ack_failed=False,acknowledged_until=None)
        result=c.outcome_fields('failed')
        class Peer:
            def send(self,*a):pass
            def receive(self,*a):
                return dict(kind='failure_ack',t0_monotonic_hex=(90.).hex(),first_monotonic_hex=(100.).hex(),
                            cleanup_until_monotonic_hex=(110.).hex(),descriptor=pool.first_global),[]
        with patch.object(life,'ACTIVE',None),patch.object(life,'POOL',pool),patch.object(life,'CHANNEL',Peer()),patch.object(life.time,'monotonic',return_value=100.):
            self.assertTrue(c.worker_failure(RuntimeError('ordinary source'),None,None,None,result,permission))
            self.assertEqual(pool.first,100.);self.assertEqual(result['outcome'],'safety_stop')

    def test_worker_real_calls_preserve_descriptor_and_ACK(self):
        x=execution();error=c.Stop('source','resource_stop');error.first_failure_descriptor=desc(95.,'resource_stop')
        calls=[]
        class Peer:
            def send(self,value,deadline):calls.append((value,deadline))
            def receive(self,deadline):
                return dict(kind='failure_ack',t0_monotonic_hex=(90.).hex(),first_monotonic_hex=(94.).hex(),
                            cleanup_until_monotonic_hex=(104.).hex(),descriptor=desc(94.,'cancelled','peer')),[]
        result=c.outcome_fields('identity_or_lease_failure');permission=dict(failed=False,ack_failed=False,acknowledged_until=None)
        learner=NS(api=NS(absolute_deadline=None))
        with patch.object(life,'ACTIVE',latch()),patch.object(life,'POOL',x.pool),patch.object(life,'CHANNEL',Peer()),patch.object(life.time,'monotonic',return_value=100.):
            self.assertTrue(c.worker_failure(error,None,None,learner,result,permission))
            self.assertEqual(x.pool.first_local,error.first_failure_descriptor)
            self.assertEqual(x.pool.first_global['timestamp'],94.)
            self.assertEqual(learner.api.absolute_deadline,104.)
            self.assertEqual(permission['acknowledged_until'],104.)
            self.assertEqual(result['outcome'],'cancelled')
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0][0]['descriptor'],error.first_failure_descriptor)
            self.assertEqual(c.worker_write_permission(NS(started=90.),result,permission),104.)

    def test_notify_descriptor_conflict_and_no_resampling(self):
        error=c.Stop('source');error.first_failure_descriptor=desc(95.)
        pool=life.FailurePool(90.)
        with patch.object(life,'ACTIVE',None),patch.object(life,'CHANNEL',None),patch.object(life,'POOL',pool),patch.object(life.time,'monotonic',return_value=100.):
            self.assertEqual(life.notify_failure(error),105.)
            with self.assertRaisesRegex(c.Stop,'descriptor timestamp differs'):life.notify_failure(error,96.)
            self.assertEqual(pool.first,95.)

    def test_failed_ACK_no_retry_no_write(self):
        calls=[]
        class Peer:
            def send(self,*a):calls.append('send')
            def receive(self,*a):raise c.Stop('missing ACK')
        pool=life.FailurePool(90.);permission=dict(failed=False,ack_failed=False,acknowledged_until=None)
        result=c.outcome_fields('failed');error=c.Stop('first');error.first_failure_descriptor=desc(95.)
        with patch.object(life,'ACTIVE',None),patch.object(life,'POOL',pool),patch.object(life,'CHANNEL',Peer()),patch.object(life.time,'monotonic',return_value=100.):
            self.assertFalse(c.worker_failure(error,None,None,None,result,permission))
            self.assertFalse(c.worker_failure(error,None,None,None,result,permission))
            self.assertEqual(calls,['send'])
            with self.assertRaisesRegex(c.Stop,'Unacknowledged'):c.worker_write_permission(NS(started=90.),result,permission)
            self.assertEqual(pool.until,105.)

    def test_execution_nonexception_and_conflict(self):
        x=execution()
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',return_value=100.):
            x.fail('string reason');self.assertEqual(x.pool.first,100.)
            error=c.Stop('older','resource_stop');error.first_failure_descriptor=desc(95.,'resource_stop')
            with self.assertRaisesRegex(c.Stop,'descriptor timestamp differs'):x.fail(error,96.)
            x.fail(error);self.assertEqual(x.pool.first,95.)
            x.fail(c.Stop('cleanup','publication_failure'));self.assertEqual(x.pool.first_global['outcome'],'resource_stop')

    def test_cancellation_first_then_cleanup_and_alarm(self):
        x=execution();x.latch.first_cancel_at=x.latch.first_at=92.;x.latch.requested_signal=signal.SIGINT;x.latch.first_alarm_at=98.
        guard=NS(failure=c.Stop('guard','resource_stop'),failure_at=95.);x.guard=guard
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',return_value=100.):
            x.fail(c.Stop('cleanup','publication_failure'))
            self.assertEqual(x.pool.first,92.);self.assertEqual(x.pool.first_global['outcome'],'cancelled')

    def monitor_case(self,rc=None,cancel=False,guard=False,cutoff=None,sample=False,prior=False):
        now=100.;x=execution(0.)
        x.latch.deadline=10000.;x.guard.last_sample=now-1 if sample else now
        if cancel:
            x.latch.cancellation_requests=1;x.latch.requested_signal=signal.SIGTERM;x.latch.first_at=x.latch.first_cancel_at=99.
        if guard:x.guard.failure=c.Stop('resource','resource_stop');x.guard.failure_at=99.
        if rc is not None:x.child=NS(poll=lambda:dict(returncode=rc),report=dict(returncode=rc))
        if cutoff=='worker':x.worker_wait=None
        else:x.worker_wait={}
        if cutoff=='inner':x.child=None
        x.groups={'supervisor':dict(pgid=123,pid=123,group_absent=False)};x.recovery_proven=True
        class Once:
            def __init__(self):self.n=0
            def wait(self,*a):self.n+=1;return self.n>1
        x.stop=Once();signals=[]
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',return_value=now),patch.object(e.c,'WORKER_SECONDS',99. if cutoff=='worker' else 1000.),patch.object(e.c,'INNER_SECONDS',99. if cutoff=='inner' else 1000.),patch.object(e,'NORMAL_SECONDS',99. if cutoff=='outer' else 7200),patch.object(e.owned,'signal_once',lambda record,n:signals.append(n)),patch.object(e.owned,'absent',return_value=True):
            if prior:x.pool.fail(c.Stop('original','resource_stop'),98.,desc(98.,'resource_stop'))
            x.monitor()
        return x,signals

    def test_monitor_raw_1_7_negative15_preserves_first(self):
        for rc in (1,7,-15):
            for prior in (False,True):
                with self.subTest(rc=rc,prior=prior):
                    x,signals=self.monitor_case(rc,prior=prior)
                    self.assertIsNotNone(x.pool.until);self.assertIn(signal.SIGTERM,signals);self.assertTrue(x.cleanup_complete)
                    self.assertEqual(x.pool.first_global['outcome'],'resource_stop' if prior else 'publication_failure')

    def test_monitor_all_typed_sites(self):
        for kwargs,outcome,at in [({'cancel':True},'cancelled',99.),({'guard':True},'resource_stop',99.),({'sample':True},'resource_stop',100.),({'cutoff':'worker'},'wall_guard',99.),({'cutoff':'inner'},'wall_guard',99.),({'cutoff':'outer'},'wall_guard',99.)]:
            with self.subTest(kwargs=kwargs):
                x,signals=self.monitor_case(**kwargs);self.assertEqual(x.pool.first,at);self.assertEqual(x.pool.first_global['outcome'],outcome);self.assertTrue(signals)

    def test_monitor_valid_raw_0_2_no_failure(self):
        for rc in (0,2):
            x,signals=self.monitor_case(rc);self.assertIsNone(x.pool.until);self.assertEqual(signals,[])

    def test_stalled_cleanup_mandatory_false_before_deadline(self):
        x=execution();clock=[100.];x.child=NS(report=None);x.recover_registration_race=lambda *a:None
        x.stop=NS(set=lambda:None);x.watchdog=NS(join=lambda **kw:None)
        path=self.d/'execution/receipt.json';attempts=[]
        real=c.mandatory_failure
        def publish(p,result,deadline):
            attempts.append(clock[0]);self.assertFalse(result['cleanup_complete']);self.assertEqual(result['experiment_status'],'failed_partial')
            return real(p,result,deadline)
        def sleep(seconds):clock[0]+=max(.001,seconds)
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',side_effect=lambda:clock[0]),patch.object(e.time,'sleep',sleep),patch.object(c,'mandatory_failure',publish):
            x.fail(c.Stop('source','resource_stop'))
            with self.assertRaisesRegex(c.Stop,'Absolute deadline'):x.publish_failed(path,c.Stop('cleanup'))
        receipt=c.read_json(path)
        self.assertEqual(len(attempts),1);self.assertLess(attempts[0],110.);self.assertGreaterEqual(clock[0],110.)
        self.assertFalse(receipt['accepted']);self.assertFalse(receipt['cleanup_complete']);self.assertIsNone(receipt['inner_wait'])
        self.assertEqual(receipt['first_global_failure']['outcome'],'resource_stop')

    def test_inner_real_failure_mandatory_before_close_and_optional(self):
        events=[];pool=life.FailurePool(90.);active=latch();output=self.d/'campaign'
        class Guard:
            failure=None;failure_at=None;thread=verify_thread=None;stream=None
            event=NS(set=lambda:events.append('event_set'))
            def __init__(self,*a):pass
            def start(self):raise ValueError('inner source')
        class Stream:
            def close(self):events.append('stream_close');raise OSError('closure')
        def mandatory(path,result,deadline):events.append('mandatory');c.replace_json(path,result)
        p=dict(output='campaign',terminal_lifecycle={'acceptance_receipt':'execution/receipt.json'})
        lease=dict(identity_sha256='x',capsule_manifest_sha256='y')
        args=NS(output=output,state_path=self.d/'state.json',executor_pid=123)
        with patch.object(c,'ORIGINAL_ROOT',self.d),patch.object(c,'STATE_PATH',args.state_path),patch.object(c,'assert_lease',lambda *a:None),patch.object(c.io,'StringIO',Stream),patch.object(life,'ACTIVE',active),patch.object(life,'POOL',pool),patch.object(life,'CHANNEL',None),patch.object(life.time,'monotonic',return_value=100.),patch.object(c,'mandatory_failure',mandatory),patch.object(c,'optional_timing',lambda *a:events.append('optional')):
            code,_=c.supervise_owned(args,90.,lease,NS(close=lambda:events.append('gate_close')),context_provider=lambda *a,**kw:(p,{},{},{},{},lease),guard_factory=Guard)
        self.assertEqual(code,1);self.assertEqual(events[0],'mandatory');self.assertIn('optional',events)
        self.assertTrue((output/'inner-failure.json').exists());self.assertFalse(c.read_json(output/'inner-failure.json')['cleanup_complete'])

    def consumer_fixture(self,raw):
        original=self.d/'original';original.mkdir();prepare=original/'prepare';prepare.mkdir();output=original/'output';output.mkdir()
        reg={k:'a'*64 for k in ('protocol_sha256','config_sha256','identity_sha256','classification_sha256','reservation_sha256')}
        reg.update(output=str(output),class_counts={'B':1,'R':1,'A':1},class_manifest_hashes={'B':'b'*64,'R':'c'*64,'A':'d'*64},pins={})
        worker={k:reg[k] for k in ('protocol_sha256','config_sha256','identity_sha256','classification_sha256')}
        worker.update(schema='long_d2_worker_integrity_summary_v1',manifests=reg['class_manifest_hashes'],boundary_count=1,boundaries=[dict(sequence=0,verdict='passed')],final_live_legacy=True,final_runtime=dict(verdict='passed',cache=dict(empty=True)),first_local_failure=None,first_global_failure=None)
        summary={k:reg[k] for k in ('protocol_sha256','config_sha256','identity_sha256','classification_sha256','reservation_sha256')}
        summary.update(schema='long_d2_compact_integrity_summary_v1',manifests=reg['class_manifest_hashes'],worker=worker,first_local_failure=None,first_global_failure=None)
        for endpoint in ('preflight','postflight'):summary[endpoint]=dict(role='outer_'+endpoint,verdict='passed',counts=reg['class_counts'],classification_sha256=reg['classification_sha256'],manifests=reg['class_manifest_hashes'])
        registration_path=original/'registration.json';summary_path=original/'summary.json';c.save(registration_path,reg);c.save(summary_path,summary);c.save(prepare/'required-lease.json',{'lease':'fixture'})
        bindings=dict(artifacts={},integrity_summary_path=str(summary_path),integrity_summary_sha256=c.sha(summary_path))
        for name,key in (('artifact-manifest.json','artifact_manifest_sha256'),('long-run-result.json','run_result_sha256'),('finalization-result.json','terminal_sha256'),('long-worker-result.json','worker_result_sha256')):
            c.save(output/name,{});bindings[key]=c.sha(output/name)
        leaf=output/'leaf.txt';leaf.write_text('fixture artifact bytes');bindings['artifacts']['leaf.txt']=c.sha(leaf)
        receipt=dict(schema='long_d2_outer_acceptance_v2',accepted=True,expected_exit_code=raw,experiment_status='complete',outcome='D2_progress_gate_passed' if raw==0 else 'budget_closed_below_gate',teacher_qualified=False,training_parent_eligible=False,registration=reg,registration_sha256=c.sha(registration_path),integrity_summary=summary,required_lease={'lease':'fixture'},bindings=bindings,t0_monotonic_hex=(100.).hex(),ownership={role:dict(pid=pid,pgid=pid,parent_at_registration=parent,new_session_verified=True,group_absent=True) for role,pid,parent in (('supervisor',200,150),('worker',300,200))})
        for key,pid,parent,at in (('inner_wait',200,150,102.),('worker_wait',300,200,101.)):
            receipt[key]=dict(pid=pid,reaped_by=parent,direct_child_reaped=True,raw_wait_status=raw<<8,returncode=raw,observed_monotonic=at)
        return original,registration_path,receipt

    def test_consumer_valid_0_and_2(self):
        for raw in (0,2):
            sub=self.d/str(raw);sub.mkdir();previous=self.d;self.d=sub
            original,rp,r=self.consumer_fixture(raw);self.d=previous
            with patch.object(c,'ORIGINAL_ROOT',original),patch.object(c,'PREPARE_REL','prepare'),patch.object(e,'REGISTRATION_PATH',rp):
                self.assertTrue(e.accept_observed(r,raw,3.,registration_sha256=c.sha(rp),summary_sha256=r['bindings']['integrity_summary_sha256']))

    def test_consumer_wait_negatives_and_existing_byte_raw_wall_checks(self):
        original,rp,r=self.consumer_fixture(2)
        with patch.object(c,'ORIGINAL_ROOT',original),patch.object(c,'PREPARE_REL','prepare'),patch.object(e,'REGISTRATION_PATH',rp):
            def accept(item,raw=2,wall=3.):return e.accept_observed(item,raw,wall,registration_sha256=c.sha(rp),summary_sha256=r['bindings']['integrity_summary_sha256'])
            self.assertTrue(accept(r));count=0
            for key in ('inner_wait','worker_wait'):
                bad=copy.deepcopy(r);bad.pop(key);self.assertFalse(accept(bad));count+=1
                for field,value in [('direct_child_reaped',False),('returncode',1),('raw_wait_status',256),('raw_wait_status',15),('raw_wait_status',-1),('raw_wait_status',True),('pid',999),('reaped_by',999),('observed_monotonic',99.),('observed_monotonic',float('nan')),('observed_monotonic','101'),('observed_monotonic',float('inf')),('observed_monotonic',104.),('observed_monotonic',100.+(c.INNER_SECONDS if key=='inner_wait' else c.WORKER_SECONDS))]:
                    bad=copy.deepcopy(r);bad[key][field]=value;self.assertFalse(accept(bad),(key,field,value));count+=1
            for field,value in [('pid',200),('pgid',999),('parent_at_registration',999),('group_absent',False),('new_session_verified',False)]:
                bad=copy.deepcopy(r);bad['ownership']['worker'][field]=value;self.assertFalse(accept(bad));count+=1
            for stamp in ('nan','inf','wrong','-0x1.0p+0'):
                bad=copy.deepcopy(r);bad['t0_monotonic_hex']=stamp;self.assertFalse(accept(bad));count+=1
            self.assertFalse(accept(r,1));self.assertFalse(accept(r,2,7200.01));self.assertFalse(accept(r,2,float('nan')))
            (original/'output/leaf.txt').write_text('changed');self.assertFalse(accept(r))
            c.save(self.d/'consumer-negative-count.json',dict(wait_ownership_time_negatives=count,valid_control=2,actual_bytes_mutation_rejected=True))

    def scan_fixture(self):
        root=self.d/'capsule';(root/'dir').mkdir(parents=True);(root/'dir/leaf').write_text('x');(root/'capsule-manifest.json').write_text('{}')
        (root/'dir/leaf').chmod(0o444);(root/'capsule-manifest.json').chmod(0o444);(root/'dir').chmod(0o555);root.chmod(0o555)
        return root,dict(version='long_d2_capsule_v1',files={'dir/leaf':'bytes hashed separately'})

    def test_scan_fresh_single_traversal_no_per_member_resolve(self):
        root,m=self.scan_fixture();real=os.scandir;calls=[];resolve=Path.resolve;resolves=[]
        def scanned(path):calls.append(str(path));return real(path)
        def resolved(path,*a,**kw):resolves.append(str(path));return resolve(path,*a,**kw)
        with patch.object(os,'scandir',scanned),patch.object(Path,'resolve',resolved):c.assert_readonly_capsule(root,m)
        self.assertEqual(len(calls),2);self.assertEqual(resolves,[str(root)])
        (root/'dir/leaf').chmod(0o644)
        with self.assertRaisesRegex(c.Stop,'writable'):c.assert_readonly_capsule(root,m)

    def test_scan_negative_files_dirs_aliases_special_names(self):
        root,m=self.scan_fixture()
        def fail():
            with self.assertRaises((c.Stop,OSError)):c.assert_readonly_capsule(root,m)
        for name in ('../escape','/absolute','dir/../leaf','dir//leaf','./dir/leaf','dir/./leaf','', 'dir/leaf/'):
            bad=dict(m,files={name:'x'})
            with self.subTest(name=name),self.assertRaises(c.Stop):c.assert_readonly_capsule(root,bad)
        (root/'dir').chmod(0o755);fail();(root/'dir').chmod(0o555)
        root.chmod(0o755);fail()
        (root/'extra').write_text('x');(root/'extra').chmod(0o444);root.chmod(0o555);fail()
        root.chmod(0o755);(root/'extra').unlink();(root/'dir').chmod(0o755);(root/'dir/leaf').unlink();root.chmod(0o555);fail()
        (root/'dir/leaf').symlink_to(root/'capsule-manifest.json');(root/'dir').chmod(0o555);fail()
        (root/'dir').chmod(0o755);(root/'dir/leaf').unlink();(root/'dir/leaf').write_text('x');(root/'dir/leaf').chmod(0o444);(root/'dir').chmod(0o555)
        root.chmod(0o755);(root/'alias-dir').symlink_to(root/'dir',target_is_directory=True);root.chmod(0o555);fail()
        root.chmod(0o755);(root/'alias-dir').unlink();os.mkfifo(root/'fifo');root.chmod(0o555);fail()
        alias=self.d/'alias';alias.symlink_to(root,target_is_directory=True)
        with self.assertRaises(c.Stop):c.assert_readonly_capsule(alias,m)
        parent=self.d/'alias-parent';parent.symlink_to(self.d,target_is_directory=True)
        with self.assertRaises(c.Stop):c.assert_readonly_capsule(parent/'capsule',m)

    def test_IPC_bounded_length_flags_errno_context_no_payload(self):
        class Sock:
            def __init__(self,result=None,error=None):self.result=result;self.error=error;self.calls=0
            def fileno(self):return 123
            def settimeout(self,*a):pass
            def recvmsg(self,*a):
                self.calls+=1
                if self.error:raise self.error
                return self.result
        for raw,flags in ((b'',0),(b'SECRET'*10001,0),(b'SECRET',socket.MSG_TRUNC),(b'SECRET',socket.MSG_CTRUNC),(b'SECRET',0)):
            channel=life.Channel.__new__(life.Channel);channel.received=0;channel.sock=Sock((raw,[],flags,None))
            with patch.object(life.time,'monotonic',return_value=100.),self.assertRaises(Exception) as raised:channel.receive(101.,sender=777)
            diagnostic=channel.last_receive_failure
            self.assertEqual(diagnostic['raw_length'],len(raw));self.assertEqual(diagnostic['flags'],flags);self.assertEqual(diagnostic['expected_sender'],777)
            self.assertNotIn('SECRET',json.dumps(diagnostic));self.assertNotIn('SECRET',str(raised.exception));self.assertEqual(channel.sock.calls,1)
        channel=life.Channel.__new__(life.Channel);channel.received=0;channel.sock=Sock(error=OSError(errno.EIO,'failure'))
        with patch.object(life.time,'monotonic',return_value=100.),self.assertRaises(c.Stop):channel.receive(101.)
        self.assertEqual(channel.last_receive_failure['errno'],errno.EIO);self.assertEqual(channel.sock.calls,1)

    def test_fixture_guards_missing_receipt_empty_owned_and_milestones(self):
        empty=dict(ownership={});pre=[dict(kind='ownership',ownership={},owned_spawns=[])]
        self.assertTrue(validate_fixture(empty,pre,{},dict(resource_cap=True),receipt_available=True))
        for receipt,events,absence,options,available in [(empty,pre,{},dict(resource_cap=True),False),(empty,[],{},dict(resource_cap=True),True),(empty,pre,{},dict(mode='wedged'),True)]:
            with self.assertRaises(AssertionError):validate_fixture(receipt,events,absence,options,receipt_available=available)
        r=dict(ownership={'worker':dict(pid=300)},worker_wait=dict(pid=300,direct_child_reaped=True))
        events=[dict(kind='owned_spawn',owned_role='worker',pid=300,monotonic=1.)]
        self.assertTrue(validate_fixture(r,events,{'worker':True},{},receipt_available=True))
        for options in (dict(mode='wedged'),dict(phase='inner:spawn-before-registration')):
            with self.assertRaises(AssertionError):validate_fixture(r,events,{'worker':True},options,receipt_available=True)
        with self.assertRaises(AssertionError):validate_fixture(r,events,{}, {},receipt_available=True)
        bad=copy.deepcopy(r);bad.pop('worker_wait')
        with self.assertRaises(AssertionError):validate_fixture(bad,events,{'worker':True},{},receipt_available=True)
        events.append(dict(kind='wedged_entry',role='worker'));self.assertTrue(validate_fixture(r,events,{'worker':True},dict(mode='wedged'),receipt_available=True))

if __name__=='__main__':unittest.main(verbosity=2,failfast=True)
