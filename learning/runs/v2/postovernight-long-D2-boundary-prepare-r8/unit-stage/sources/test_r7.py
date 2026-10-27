"""r7 actual call-path regressions. Fake children/clocks/channels, no OS lifecycle."""
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import ast
import copy
import json
import math
import os
import signal
import tempfile
import threading
import unittest
import lifecycle as life
import processes as owned
import long_d2 as c
import long_d2_executor as e
from fixture_guards import validate_fixture
from test_repairs import execution, latch, desc
H=Path(__file__).resolve().parent
A=Path(os.environ['VALIDATION_DIR'])


def wait(pid=200,parent=None,at=99.75,rc=1):
    return dict(pid=pid,reaped_by=os.getpid() if parent is None else parent,
                observed_monotonic=at,returncode=rc,raw_wait_status=-rc if rc<0 else rc<<8,
                direct_child_reaped=True)


def group(pid,parent):
    return dict(pid=pid,pgid=pid,parent_at_registration=parent,new_session_verified=True,group_absent=True)


def fixture(cls='failed_supervisor_alive'):
    receipt=dict(accepted=False,executor_t0_monotonic=90.,cleanup_until_monotonic=110.,
                 ownership={'supervisor':group(200,150),'worker':group(300,200)},
                 inner_wait=wait(200,150,102.,1),worker_wait=wait(300,200,101.,-15),
                 reaping={'worker':dict(status='direct_reaped',basis='validated_direct_parent_waitpid_report')})
    events=[dict(kind='owned_spawn',owned_role=role,pid=pid,monotonic=99.) for role,pid in [('supervisor',200),('worker',300)]]
    options=dict(expectation_class=cls,expected_exit=1)
    if cls=='failed_blocked_parent_crash':
        options.update(mode='blocked',phase='inner:during-worker',mutation='crash')
        receipt.update(inner_wait=wait(200,150,102.,7),worker_wait=None,
                       reaping={'worker':dict(status='unproven',basis='supervisor_dead_before_report')})
        events.extend([dict(kind='injection',role='inner',phase='during-worker'),
                       dict(kind='registered_worker_live_at_crash',worker_pid=300,supervisor_pid=200,
                            registered=True,live_at_crash=True,blocked_entry=True,prior_worker_wait=False)])
    return receipt,events,options


class EndRun(BaseException):pass


class R7(unittest.TestCase):
    def setUp(self):self.d=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=A))

    def monitor(self,*,alarm=None,cancel=None,guard_at=None,peer_at=None,rc=1):
        x=execution();report=wait(rc=rc);x.child=NS(process=NS(pid=200),report=report,poll=lambda:report)
        x.groups={'supervisor':group(200,os.getpid())};x.recovery_proven=True
        class Once:
            n=0
            def wait(self,*a):self.n+=1;return self.n>1
        x.stop=Once()
        if alarm is not None:x.latch.first_alarm_at=x.latch.first_at=alarm
        if cancel is not None:
            x.latch.first_cancel_at=cancel;x.latch.first_at=min(cancel,x.latch.first_at or cancel)
            x.latch.cancellation_requests=1;x.latch.requested_signal=signal.SIGTERM
        if guard_at is not None:x.guard.failure=c.Stop('guard','resource_stop');x.guard.failure_at=guard_at
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',return_value=100.),patch.object(owned,'signal_once'),patch.object(owned,'absent',return_value=True):
            if peer_at is not None:x.pool.fail('peer',peer_at,desc(peer_at,'safety_stop','peer'),peer=True)
            x.monitor()
        c.save(self.d/'monitor-result.json',dict(first=x.pool.first,until=x.pool.until,descriptor=x.pool.first_global))
        return x

    def test_A_monitor_retained_9975_handled_100(self):
        x=self.monitor();self.assertEqual((x.pool.first,x.pool.until),(99.75,109.75))
        self.assertEqual(x.pool.first_global['timing_basis'],'successful_direct_waitpid_observation')

    def test_A_monitor_earlier_guard_peer_and_cancel_win(self):
        for kwargs,outcome in [(dict(guard_at=99.5),'resource_stop'),(dict(peer_at=99.5),'safety_stop'),(dict(cancel=99.5),'cancelled')]:
            with self.subTest(kwargs=kwargs):
                x=self.monitor(**kwargs);self.assertEqual((x.pool.first,x.pool.until),(99.5,109.5));self.assertEqual(x.pool.first_global['outcome'],outcome)

    def test_A_report_source_identity_and_time_negatives(self):
        x=execution();report=wait();x.child=NS(process=NS(pid=200),report=report)
        with patch.object(life.time,'monotonic',return_value=100.):
            for key,value in [('pid',201),('reaped_by',999999),('direct_child_reaped',False),('observed_monotonic',100.1),('observed_monotonic',89.),('observed_monotonic',float('nan')),('observed_monotonic',True),('raw_wait_status',7<<8),('raw_wait_status',65536)]:
                bad=copy.deepcopy(report);bad[key]=value;x.child.report=bad
                with self.subTest(key=key,value=value),self.assertRaises(c.Stop):x.raw_inner_failure(bad)
            x.child.report=report
            with self.assertRaisesRegex(c.Stop,'not retained'):x.raw_inner_failure(dict(report))

    def main_path(self,guard_at=None,peer_at=None):
        x=execution();x.registration=dict(receipt=str(self.d/'receipt.json'),output=str(self.d/'campaign'),state_path='fake',controller='fake',pins={},identity_sha256='identity-fixture',capsule_manifest_sha256='capsule-fixture')
        x.context=({},{},{},{},{},{})
        x.stop=threading.Event();x.closed=False;x.supervisor_factory=lambda *a:['fake','-B','fake','run']
        x.guard_factory=lambda *a:x.guard;x.guard.start=lambda:None
        x.guard.event=NS(set=lambda:None)
        if guard_at is not None:x.guard.failure=c.Stop('older guard','resource_stop');x.guard.failure_at=guard_at
        x.authority=lambda *a:None
        pumps=[];x.pump=lambda *a,**kw:pumps.append('pump')
        def retain_failure(path,error):
            c.save(self.d/'main-trigger.json',dict(error=repr(error),error_type=type(error).__name__,pool_reason=x.pool.reason,descriptor=getattr(error,'first_failure_descriptor',None)))
        x.publish_failed=retain_failure
        x.watchdog=None
        report=wait();child=NS(process=NS(pid=200),report=report,poll=lambda:report)
        class Socket:
            def fileno(self):return 9
            def close(self):pass
        class Channel:
            sock=Socket()
            def __init__(self,*a):pass
            def send(self,*a):
                if peer_at is not None:x.pool.fail('peer',peer_at,desc(peer_at,'cancelled','peer'),peer=True)
        thread=NS(is_alive=lambda:True,join=lambda **kw:None)
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',return_value=100.),patch.object(c,'assert_lease'),patch.object(c,'sha',return_value='fixture'),patch.object(e.integrity,'verify',return_value={}),patch.object(life,'pair',side_effect=lambda:(Socket(),Socket())),patch.object(life,'Channel',Channel),patch.object(life,'start_thread'),patch.object(e.threading,'Thread',return_value=thread),patch.object(e.subprocess,'Popen',return_value=child.process),patch.object(owned,'Child',return_value=child),patch.object(owned,'verify_session',return_value=group(200,os.getpid())),patch.object(e.signal,'pthread_sigmask',return_value=set()),patch.object(life,'final_exit',side_effect=EndRun):
            with self.assertRaises(EndRun):x.run()
        self.assertEqual(pumps,[],'nonzero raw source must be stamped before terminal drain')
        c.save(self.d/'main-result.json',dict(first=x.pool.first,until=x.pool.until,descriptor=x.pool.first_global,pumps=pumps))
        return x

    def test_A_actual_main_branch_9975_before_drain(self):
        x=self.main_path();self.assertEqual((x.pool.first,x.pool.until),(99.75,109.75))

    def test_A_actual_main_earlier_guard_and_ACK_win(self):
        # Separate owned fixtures because the run path opens no real campaign.
        for kwargs,outcome in [(dict(guard_at=99.5),'resource_stop'),(dict(peer_at=99.5),'cancelled')]:
            x=self.main_path(**kwargs);self.assertEqual((x.pool.first,x.pool.until),(99.5,109.5));self.assertEqual(x.pool.first_global['outcome'],outcome)

    def test_A_late_earlier_peer_packet_tightens_actual_pool(self):
        x=execution();report=wait();x.child=NS(process=NS(pid=200),report=report)
        x.groups={'supervisor':group(200,os.getpid())}
        packet=dict(kind='failure',sender=200,t0_monotonic_hex=(90.).hex(),
                    first_monotonic_hex=(99.5).hex(),reason='earlier peer',descriptor=desc(99.5,'resource_stop','inner'))
        sent=[]
        class Channel:
            sock=object()
            def receive(self,*a):return packet,[]
            def send(self,value,deadline):sent.append((value,deadline))
        x.super_channel=Channel()
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',return_value=100.),patch.object(e.select,'select',side_effect=lambda sockets,*a:(sockets,[],[])):
            x.fail(x.raw_inner_failure(report));self.assertEqual(x.pool.until,109.75)
            e.Execution.pump(x)
        self.assertEqual((x.pool.first,x.pool.until),(99.5,109.5));self.assertEqual(x.pool.first_local['timestamp'],99.75)
        self.assertEqual(sent[0][0]['cleanup_until_monotonic_hex'],(109.5).hex())
        c.save(self.d/'late-earlier-pump.json',dict(local=x.pool.first_local,global_failure=x.pool.first_global,until=x.pool.until,ACK=sent))

    def test_B_alarm_then_cancel_actual_monitor(self):
        x=self.monitor(alarm=99.5,cancel=99.75,rc=0)
        self.assertEqual(x.pool.first_global['kind'],'alarm');self.assertEqual(x.pool.first_global['outcome'],'wall_guard')
        self.assertEqual((x.pool.first,x.pool.until),(99.5,109.5))

    def test_B_cancel_then_alarm_and_equal_tie_stable(self):
        for alarm,cancel in [(99.75,99.5),(99.5,99.5)]:
            x=self.monitor(alarm=alarm,cancel=cancel,rc=0)
            self.assertEqual(x.pool.first_global['outcome'],'cancelled');self.assertEqual(x.pool.first,cancel)
        # Pool preserves its first global descriptor for exact ties.
        x=self.monitor(peer_at=99.5,alarm=99.5,cancel=99.5,rc=0)
        self.assertEqual(x.pool.first_global['role'],'peer')

    def inner(self,*,ack=True,never=False,cap=None,constructor_failures=0,normal_report=False,send_error=False,earlier_ack=None,mandatory_error=False):
        clock=[100.];events=[];packets=[];receipts=[];construct=[0];polls=[0]
        active=latch();active.check=lambda:None
        pool=life.FailurePool(90.)
        if cap is not None:pool.cap=cap
        class Guard:
            failure=None;failure_at=None;thread=verify_thread=None;last_sample=100.;stream=None
            event=NS(set=lambda:events.append('guard_stop'))
            def __init__(self,*a):pass
            def start(self):events.append('guard_start')
            def check(self):pass
            def full_check(self,*a):pass
            def sample(self,**kw):pass
        class Child:
            def __init__(self,process):
                construct[0]+=1;events.append('constructor')
                if construct[0]<=constructor_failures:raise RuntimeError('constructor failed bounded')
                self.process=process;self.report=None
            def poll(self):
                polls[0]+=1;events.append('poll');clock[0]+=.01
                if not never:self.report=wait(300,200,clock[0],1)
                return self.report
        class Channel:
            sock=NS(close=lambda:events.append('ipc_close'))
            def send(self,value,deadline):
                events.append(value['kind']);packets.append(copy.deepcopy(value))
                if value['kind']=='register_worker' and not normal_report:raise c.Stop('startup cancel','cancelled')
                if value['kind']=='worker_wait' and send_error:raise OSError('send failed once')
            def receive(self,deadline,*a):
                if packets[-1]['kind']=='register_worker':return dict(kind='registered',worker_pid=300),[]
                events.append('ACK' if ack else 'no_ACK')
                if not ack:raise c.Stop('missing ACK')
                first=pool.first if earlier_ack is None else earlier_ack
                return dict(kind='failure_ack',t0_monotonic_hex=(90.).hex(),first_monotonic_hex=first.hex(),
                            cleanup_until_monotonic_hex=min(first+10,pool.cap).hex(),descriptor=pool.first_global if earlier_ack is None else desc(first,'resource_stop','outer')),[]
        def mandatory(path,result,deadline):
            events.append('mandatory' if path.name=='inner-failure.json' else 'reap_diagnostic')
            receipts.append((path.name,copy.deepcopy(result),clock[0]))
            if mandatory_error and path.name=='inner-failure.json':raise OSError('mandatory publication failed')
        def sleep(value):clock[0]+=max(.001,value)
        lease=dict(identity_sha256='id',capsule_manifest_sha256='cap')
        args=NS(output=self.d/'campaign',state_path=self.d/'state.json',executor_pid=150)
        p=dict(output='campaign',run_id='fake')
        with patch.object(c,'ORIGINAL_ROOT',self.d),patch.object(c,'STATE_PATH',args.state_path),patch.object(c,'assert_lease'),patch.object(c.os,'getpid',return_value=200),patch.object(c.subprocess,'Popen',side_effect=lambda *a,**kw:(events.append('Popen') or NS(pid=300))),patch.object(owned,'Child',Child),patch.object(owned,'absent',return_value=False),patch.object(c.signal,'pthread_sigmask',return_value=set()),patch.object(life,'ACTIVE',active),patch.object(life,'POOL',pool),patch.object(life,'CHANNEL',Channel()),patch.object(life.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c.time,'sleep',sleep),patch.object(c,'mandatory_failure',mandatory),patch.object(c,'optional_timing',side_effect=lambda *a:events.append('optional')):
            code,_=c.supervise_owned(args,90.,lease,NS(fileno=lambda:9,close=lambda:events.append('gate_close')),context_provider=lambda *a,**kw:(p,{},{},{},{},lease),guard_factory=Guard)
        self.assertEqual(code,1)
        c.save(self.d/'inner-trace.json',dict(events=events,packets=packets,receipts=receipts,clock=clock[0],pool_first=pool.first,pool_until=pool.until,constructors=construct[0],polls=polls[0]))
        return NS(events=events,packets=packets,receipts=receipts,clock=clock[0],pool=pool,constructors=construct[0],polls=polls[0])

    def test_C_actual_inner_ACK_mandatory_before_poll_and_send(self):
        x=self.inner();events=x.events
        self.assertLess(events.index('ACK'),events.index('mandatory'))
        self.assertLess(events.index('mandatory'),events.index('guard_stop'))
        self.assertLess(events.index('gate_close'),events.index('poll'))
        self.assertLess(events.index('poll'),events.index('worker_wait'));self.assertLess(events.index('worker_wait'),events.index('optional'))
        initial=x.receipts[0][1];self.assertIsNone(initial['worker_wait']);self.assertFalse(initial['owned_worker_reaped'])
        self.assertEqual(sum(p['kind']=='worker_wait' for p in x.packets),1)
        self.assertEqual(sum(n=='inner-failure.json' for n,_,_ in x.receipts),1)

    def test_C_mandatory_attempt_failure_does_not_suppress_reap(self):
        x=self.inner(mandatory_error=True)
        self.assertLess(x.events.index('mandatory'),x.events.index('poll'))
        self.assertEqual(sum(p['kind']=='worker_wait' for p in x.packets),1)
        self.assertEqual(sum(n=='inner-failure.json' for n,_,_ in x.receipts),1)

    def test_C_no_ACK_skips_extended_wait_and_retry(self):
        x=self.inner(ack=False);self.assertEqual(x.polls,0)
        self.assertEqual([p['kind'] for p in x.packets],['register_worker','failure'])
        self.assertIn('failure_ack_unavailable',x.receipts[0][1]);self.assertEqual(x.clock,100.)

    def test_C_guarded_fallback_after_constructor_failure(self):
        x=self.inner(constructor_failures=1);self.assertEqual(x.constructors,2);self.assertEqual(x.polls,1)
        self.assertEqual(sum(p['kind']=='worker_wait' for p in x.packets),1)

    def test_C_fallback_constructor_failure_honest_bounded_diagnostic(self):
        x=self.inner(constructor_failures=2);self.assertEqual(x.constructors,2);self.assertEqual(x.polls,0)
        diagnostic=next(value for name,value,_ in x.receipts if name=='inner-reap-diagnostic.json')
        self.assertIn('constructor failed',diagnostic['worker_reap_diagnostic']);self.assertLessEqual(len(diagnostic['worker_reap_diagnostic']),512)
        self.assertFalse(diagnostic['worker_report_retained'])

    def test_C_expiry_no_fabricated_wait_same_pool(self):
        x=self.inner(never=True);self.assertLessEqual(x.clock,109.021);self.assertGreaterEqual(x.clock,109.)
        self.assertEqual((x.pool.first,x.pool.until),(100.,110.));self.assertFalse(any(p['kind']=='worker_wait' for p in x.packets))
        diagnostic=next(v for n,v,_ in x.receipts if n=='inner-reap-diagnostic.json');self.assertFalse(diagnostic['worker_report_retained'])
        self.assertIn('unproven',diagnostic['worker_reap_diagnostic'])

    def test_C_cap_truncated_window_unproven_no_allowance(self):
        x=self.inner(never=True,cap=100.5);self.assertEqual(x.pool.until,100.5);self.assertEqual(x.polls,0)
        self.assertEqual(x.clock,100.);self.assertFalse(any(p['kind']=='worker_wait' for p in x.packets))

    def test_C_earlier_ACK_tightens_inner_window(self):
        x=self.inner(never=True,earlier_ack=99.5);self.assertEqual(x.pool.until,109.5)
        self.assertLessEqual(x.clock,108.521);self.assertGreaterEqual(x.clock,108.5)

    def test_C_surviving_descendant_no_duplicate_report(self):
        x=self.inner(normal_report=True)
        self.assertEqual(sum(p['kind']=='worker_wait' for p in x.packets),1)
        self.assertEqual(x.polls,1)
        self.assertTrue(x.receipts[0][1]['owned_worker_reaped'])

    def test_C_normal_send_failure_marked_before_no_retry(self):
        x=self.inner(normal_report=True,send_error=True)
        self.assertEqual(sum(p['kind']=='worker_wait' for p in x.packets),1)
        self.assertEqual(x.receipts[0][1]['worker_wait_send_status'],'failed')
        self.assertIn('send failed once',x.receipts[0][1]['worker_wait_send_error'])

    def test_C_failure_send_failure_recorded_once(self):
        x=self.inner(send_error=True);self.assertEqual(sum(p['kind']=='worker_wait' for p in x.packets),1)
        diagnostic=next(v for n,v,_ in x.receipts if n=='inner-reap-diagnostic.json')
        self.assertTrue(diagnostic['worker_wait_send_attempted']);self.assertIn('send failed once',diagnostic['worker_reap_diagnostic'])

    def drain(self,report=None,clock_at=101.):
        x=execution();x.groups={'supervisor':group(200,os.getpid()),'worker':group(300,200)}
        inner=wait(200,os.getpid(),100.5);x.child=NS(process=NS(pid=200),report=inner)
        x.guard=None;x.cleanup_complete=True;x.recovery_proven=True
        x.stop=NS(set=lambda:None);x.watchdog=NS(join=lambda **kw:None)
        x.recover_registration_race=lambda *a:None
        calls=[];queue=[] if report is None else [dict(kind='worker_wait',sender=200,report=report,t0_monotonic_hex=(90.).hex())]
        class Channel:
            sock=NS(close=lambda:None)
            def receive(self,deadline):
                calls.append(deadline)
                if queue:return queue.pop(0),[]
                raise ConnectionResetError(54,'retained diagnostic')
        x.super_channel=Channel();x.pump=lambda **kw:e.Execution.pump(x,**kw)
        captured=[]
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',return_value=clock_at),patch.object(e.select,'select',side_effect=lambda sockets,*a:(sockets,[],[])),patch.object(c,'mandatory_failure',side_effect=lambda p,r,d:captured.append(copy.deepcopy(r))):
            x.pool.fail(c.Stop('source'),100.,desc(100.));result=x.publish_failed(self.d/'receipt.json',c.Stop('later'))
        self.assertEqual(len(captured),1);self.assertFalse(result['accepted'])
        c.save(self.d/'drain-result.json',dict(receipt=result,receive_deadlines=calls))
        return result,calls

    def test_C_actual_pump_final_drain_valid_report_then_reset(self):
        r,calls=self.drain(wait(300,200,100.25))
        self.assertEqual(r['reaping']['worker']['status'],'direct_reaped');self.assertEqual(r['reaping']['supervisor']['status'],'direct_reaped')
        self.assertEqual(len(calls),4);self.assertTrue(all(at==109.75 for at in calls))
        self.assertTrue(r['cleanup_errors'],'unexpected private reset diagnostic remains retained')

    def test_C_actual_drain_rejects_invalid_reports(self):
        for field,value in [('pid',999),('reaped_by',999),('observed_monotonic',float('nan')),('raw_wait_status',65536),('direct_child_reaped',False)]:
            report=wait(300,200,100.25);report[field]=value
            r,_=self.drain(report);self.assertIsNone(r['worker_wait']);self.assertEqual(r['reaping']['worker']['status'],'unproven')

    def test_C_final_drain_stops_at_existing_reserve(self):
        r,calls=self.drain(wait(300,200,100.25),clock_at=109.8)
        self.assertEqual(calls,[]);self.assertEqual(r['reaping']['worker']['status'],'unproven');self.assertTrue(r['cleanup_complete'])

    def test_D_alive_supervisor_missing_worker_wait_fails(self):
        r,events,options=fixture();r['worker_wait']=None
        with self.assertRaisesRegex(AssertionError,'direct reap missing'):validate_fixture(r,events,dict(supervisor=True,worker=True),options,receipt_available=True)

    def test_D_deliberate_orphan_requires_all_positive_milestones(self):
        r,events,options=fixture('failed_blocked_parent_crash');absence=dict(supervisor=True,worker=True)
        self.assertTrue(validate_fixture(r,events,absence,options,receipt_available=True))
        for bad_events,bad_absence in [(events,{}),(events,dict(supervisor=True,worker=False)),([x for x in events if x['kind']!='registered_worker_live_at_crash'],absence)]:
            with self.assertRaises(AssertionError):validate_fixture(r,bad_events,bad_absence,options,receipt_available=True)
        bad=copy.deepcopy(r);bad['inner_wait']=wait(200,150,102.,1)
        with self.assertRaisesRegex(AssertionError,'crash not observed'):validate_fixture(bad,events,absence,options,receipt_available=True)

    def test_D_fabricated_blocked_live_crash_wait_rejected(self):
        r,events,options=fixture('failed_blocked_parent_crash');r['worker_wait']=wait(300,200,101.)
        with self.assertRaisesRegex(AssertionError,'fabricated wait'):validate_fixture(r,events,dict(supervisor=True,worker=True),options,receipt_available=True)

    def test_D_prior_legitimate_report_then_parent_death_is_not_globally_fabricated(self):
        r,events,options=fixture('failed_with_prior_worker_reap');r['inner_wait']=wait(200,150,102.,7)
        options.update(phase='inner:terminal-after',mutation='crash');events.append(dict(kind='injection',role='inner',phase='terminal-after'))
        self.assertTrue(validate_fixture(r,events,dict(supervisor=True,worker=True),options,receipt_available=True))

    def test_D_accepted_fixture_both_exact_waits(self):
        r,events,options=fixture();r.update(accepted=True,t0_monotonic_hex=(90.).hex(),expected_exit_code=2)
        r['inner_wait']=wait(200,150,92.,2);r['worker_wait']=wait(300,200,91.5,2)
        for event in events:event['monotonic']=91.
        options.update(expectation_class='accepted',expected_exit=2)
        self.assertTrue(validate_fixture(r,events,dict(supervisor=True,worker=True),options,receipt_available=True))
        for key,field,value in [('inner_wait','pid',201),('worker_wait','reaped_by',999),('worker_wait','observed_monotonic',98.),('worker_wait','raw_wait_status',15)]:
            bad=copy.deepcopy(r);bad[key][field]=value
            with self.assertRaises((AssertionError,c.Stop)):validate_fixture(bad,events,dict(supervisor=True,worker=True),options,receipt_available=True)

    def test_D_accepted_missing_wait_still_rejected(self):
        r,events,options=fixture();r.update(accepted=True,t0_monotonic_hex=(90.).hex(),expected_exit_code=2)
        r['inner_wait']=wait(200,150,92.,2);r['worker_wait']=None
        for event in events:event['monotonic']=91.
        options.update(expectation_class='accepted',expected_exit=2)
        with self.assertRaises(AssertionError):validate_fixture(r,events,dict(supervisor=True,worker=True),options,receipt_available=True)
        self.assertFalse(e.accept_observed(r,2,3.))

    def test_D_preregistered_class_and_mandatory_failure_required(self):
        r,events,options=fixture()
        with self.assertRaisesRegex(AssertionError,'unregistered'):validate_fixture(r,events,dict(supervisor=True,worker=True),{},receipt_available=True)
        with self.assertRaisesRegex(AssertionError,'mandatory'):validate_fixture(r,events,dict(supervisor=True,worker=True),options,receipt_available=False)
        r['accepted']=True
        with self.assertRaisesRegex(AssertionError,'acceptance/class'):validate_fixture(r,events,dict(supervisor=True,worker=True),options,receipt_available=True)

    def test_success_consumers_and_protected_failure_helpers_byte_equal(self):
        from source_equality import blocks,body
        old=blocks(H/'r6-source/long_d2_executor.py');new=blocks(H/'long_d2_executor.py')
        for key in ('validate_wait_reports','accept_observed','validate_artifacts','checked_registration','worker_command'):
            self.assertEqual(old[key],new[key],key)
        before=blocks(H/'r6-source/long_d2.py');after=blocks(H/'long_d2.py')
        for key in before:
            if key!='supervise_owned':self.assertEqual(before[key],after[key],key)
        self.assertEqual(body(H/'r6-source/long_d2.py'),body(H/'long_d2.py'))
        for name in ('lifecycle.py','boundary_integrity.py'):self.assertEqual((H/name).read_bytes(),(H/'r6-source'/name).read_bytes())
        proposed=c.read_json(H/'protocol-r6-proposal.json')
        self.assertEqual(c.sha(H/'protocol-r6-proposal.json'),c.PROTOCOL_SHA256)
        self.assertEqual(proposed['config_sha256'],c.CONFIG_SHA256)
        self.assertEqual(proposed['config']['phase_settings']['run_seed'],5562873868232098305)
        self.assertEqual(proposed['parent_checkpoint_sha256'],'ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f')
