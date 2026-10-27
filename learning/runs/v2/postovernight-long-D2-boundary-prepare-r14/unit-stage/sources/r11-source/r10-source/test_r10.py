"""r10 source regressions: actual classes with fake time/process/IPC only."""
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from contextlib import ExitStack
import ast
import copy
import errno
import json
import os
import signal
import tempfile
import unittest
import lifecycle as life
import processes as owned
import long_d2 as c
import long_d2_executor as e
from fixture_preconditions import preregister,check_precondition,validate_injection,PHASES
from fixture_guards import validate_fixture
from test_repairs import execution,latch,desc
from test_r7 import wait,group,fixture
H=Path(__file__).resolve().parent
A=Path(os.environ['VALIDATION_DIR'])


class DeadlineExit(BaseException):pass


class R10(unittest.TestCase):
    def setUp(self):self.d=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=A))

    def supervisor(self,rc=1,*,send_error=False,probe_error=False,earlier=None,invalid=False,normal=False):
        directory=Path(tempfile.mkdtemp(prefix='supervisor-',dir=self.d))
        campaign=directory/'campaign';clock=[100.];events=[];packets=[];receipts=[]
        active=latch();active.check=lambda:None
        pool=life.FailurePool(90.)
        if earlier and earlier[0] in ('cancel','alarm'):
            setattr(active,'first_'+earlier[0]+'_at',earlier[1])
            if earlier[0]=='cancel':active.requested_signal=signal.SIGTERM;active.cancellation_requests=1
        class Guard:
            failure=None;failure_at=None;last_sample=100.;thread=verify_thread=None
            event=NS(set=lambda:events.append('guard_stop'))
            def __init__(self,*a):
                if earlier and earlier[0]=='guard':self.failure=c.Stop('earlier guard','resource_stop');self.failure_at=earlier[1]
            def start(self):pass
            def check(self):pass
            def full_check(self,*a):pass
            def sample(self,**kw):pass
        report=wait(300,200,99.75,rc)
        if invalid:report['raw_wait_status']=7<<8
        class Child:
            def __init__(self,process):self.process=process;self.report=None
            def poll(self):events.append('poll');self.report=report;return report
        class Channel:
            sock=NS(close=lambda:events.append('ipc_close'))
            def send(self,value,deadline):
                events.append(value['kind']);packets.append(copy.deepcopy(value))
                if value['kind']=='worker_wait' and send_error:raise TimeoutError('worker_wait send failure')
            def receive(self,deadline,*a):
                if packets[-1]['kind']=='register_worker':return dict(kind='registered',worker_pid=300),[]
                events.append('ACK')
                first=pool.first
                if earlier and earlier[0]=='peer':first=earlier[1]
                return dict(kind='failure_ack',t0_monotonic_hex=(90.).hex(),first_monotonic_hex=first.hex(),
                    cleanup_until_monotonic_hex=(first+10).hex(),descriptor=pool.first_global if first==pool.first else desc(first,'resource_stop','peer')),[]
        def mandatory(path,result,deadline):events.append(path.name);receipts.append((path.name,copy.deepcopy(result)))
        def probe(*a):
            events.append('probe')
            if probe_error:raise OSError('probe unavailable')
            return True
        def missing(path):events.append('result_file');return c.read_json(path)
        lease=dict(identity_sha256='id',capsule_manifest_sha256='cap')
        args=NS(output=campaign,state_path=directory/'state.json',executor_pid=150)
        with ExitStack() as stack:
            for target,key,value in [(c,'ORIGINAL_ROOT',directory),(c,'STATE_PATH',args.state_path),
                (c,'assert_lease',lambda *a:None),(c.os,'getpid',lambda:200),
                (c.subprocess,'Popen',lambda *a,**kw:NS(pid=300)),(owned,'Child',Child),(owned,'absent',probe),
                (c.signal,'pthread_sigmask',lambda *a:set()),(life,'ACTIVE',active),(life,'POOL',pool),(life,'CHANNEL',Channel()),
                (life.time,'monotonic',lambda:clock[0]),(c,'mandatory_failure',mandatory),(c,'optional_timing',lambda *a:None)]:
                stack.enter_context(patch.object(target,key,value))
            code,_=c.supervise_owned(args,90.,lease,NS(fileno=lambda:9,close=lambda:events.append('gate_close')),
                context_provider=lambda *a,**kw:(dict(output='campaign',run_id='fixture'),{},{},{},{},lease),guard_factory=Guard)
        c.save(directory/'trace.json',dict(code=code,first=pool.first,until=pool.until,events=events,packets=packets,receipts=receipts))
        return NS(code=code,pool=pool,events=events,packets=packets,receipts=receipts,campaign=campaign,report=report)

    def test_A_abnormal_rc1_and_signal_missing_result_source_before_IO(self):
        for rc in (1,-9):
            x=self.supervisor(rc)
            self.assertEqual((x.code,x.pool.first,x.pool.until),(1,99.75,109.75))
            self.assertFalse((x.campaign/'long-worker-result.json').exists())
            self.assertNotIn('probe',x.events)
            self.assertEqual(x.pool.first_global['kind'],'direct_wait_observation')
            self.assertLess(x.events.index('inner-failure.json'),x.events.index('worker_wait'))
            self.assertLess(x.events.index('ACK'),x.events.index('inner-failure.json'))
            self.assertEqual(sum(v['kind']=='worker_wait' for v in x.packets),1)
            self.assertEqual(x.receipts[0][1]['worker_wait'],x.report)

    def test_A_abnormal_send_and_probe_failures_cannot_replace_source(self):
        for flags in (dict(send_error=True),dict(probe_error=True),dict(send_error=True,probe_error=True)):
            x=self.supervisor(**flags)
            self.assertEqual((x.pool.first,x.pool.until),(99.75,109.75))
            self.assertEqual(sum(v['kind']=='worker_wait' for v in x.packets),1)
            self.assertNotIn('probe',x.events,'abnormal path must enter failure before group probing')
            if flags.get('send_error'):
                diagnostic=next(v for n,v in x.receipts if n=='inner-reap-diagnostic.json')
                self.assertIn('worker_wait send failure',diagnostic['worker_reap_diagnostic'])

    def test_A_earlier_guard_cancel_alarm_peer_keep_same_pool(self):
        for name,outcome in [('guard','resource_stop'),('cancel','cancelled'),('alarm','wall_guard'),('peer','resource_stop')]:
            x=self.supervisor(earlier=(name,99.5))
            self.assertEqual((x.pool.first,x.pool.until),(99.5,109.5))
            self.assertEqual(x.pool.first_global['outcome'],outcome)
            self.assertEqual(sum(p['kind']=='failure' for p in x.packets),1)

    def test_A_invalid_supervisor_report_never_stamps_direct_source(self):
        x=self.supervisor(invalid=True)
        self.assertEqual(x.pool.first,100.)
        self.assertNotEqual(x.pool.first_global['kind'],'direct_wait_observation')
        self.assertFalse(any(v['kind']=='worker_wait' for v in x.packets))

    def packet_case(self,rc=1,*,prior=None,bad=None,second_error=False):
        x=execution();report=wait(300,200,99.75,rc)
        if bad:report[bad[0]]=bad[1]
        x.child=NS(process=NS(pid=200));x.groups={'worker':group(300,200)}
        packet=dict(kind='worker_wait',report=report,sender=200,t0_monotonic_hex=(90.).hex())
        class Channel:
            sock=object()
            def receive(self,*a):return packet,[]
        x.super_channel=Channel()
        if second_error:
            class Broken:
                sock=object()
                def receive(self,*a):
                    # The earlier abnormal source must already be latched.
                    assert x.pool.first==99.75 and x.pool.until==109.75
                    raise OSError('later receive failure')
            x.worker_channel=Broken()
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',return_value=100.),patch.object(e.select,'select',side_effect=lambda sockets,*a:(sockets,[],[])):
            if prior:x.pool.fail(c.Stop('later first'),prior,desc(prior))
            if bad or second_error:
                with self.assertRaises((c.Stop,OSError)):e.Execution.pump(x)
            else:e.Execution.pump(x)
        return x,report

    def test_A_actual_outer_pump_recovers_source_before_next_IO(self):
        for rc in (1,-9):
            x,report=self.packet_case(rc,second_error=True)
            self.assertEqual((x.pool.first,x.pool.until),(99.75,109.75));self.assertIs(x.worker_wait,report)

    def test_A_actual_outer_late_earlier_tightens_and_prior_wins(self):
        for prior,first in [(99.9,99.75),(99.5,99.5)]:
            x,_=self.packet_case(prior=prior)
            self.assertEqual((x.pool.first,x.pool.until),(first,first+10))
            self.assertEqual(x.pool.first_local['timestamp'],prior)

    def test_A_actual_outer_invalid_reports_never_supply_source(self):
        for bad in [('pid',301),('reaped_by',201),('direct_child_reaped',False),('raw_wait_status',9),('observed_monotonic',100.1),('observed_monotonic',True)]:
            x,_=self.packet_case(bad=bad)
            self.assertIsNone(x.pool.until);self.assertIsNone(x.worker_wait)

    def test_A_actual_outer_normal_raw0_2_unchanged(self):
        for rc in (0,2):
            x,report=self.packet_case(rc);self.assertIsNone(x.pool.until);self.assertIs(x.worker_wait,report)

    def monitor(self,error,*,cleanup_error=False,late=False):
        x=execution();clock=[100.];signals=[];probes=[];polls=[];calls=[]
        x.groups={'supervisor':group(200,os.getpid()),'worker':group(300,200)}
        for record in x.groups.values():record['group_absent']=False
        x.recovery_proven=True
        report=wait(200,os.getpid(),99.75,1)
        def poll():polls.append(clock[0]);return report
        x.child=NS(process=NS(pid=200),report=report,poll=poll)
        x.super_channel=NS(sock=NS(fileno=lambda:9))
        def pump():
            calls.append(clock[0])
            if late and len(calls)==2:
                x.guard.failure=c.Stop('late earlier guard','resource_stop');x.guard.failure_at=99.5
                x.pool.fail('late earlier peer',99.25,desc(99.25,'safety_stop','peer'),peer=True)
            raise error
        x.pump=pump
        class Stop:
            def wait(self,*a):
                clock[0]+=.02
                # Resource/lease monitor is independently refreshed; no sample-age artifact.
                x.guard.last_sample=clock[0]
                if clock[0]>111.:raise AssertionError('deadline not enforced')
                return False
        x.stop=Stop()
        def sig(record,number):
            signals.append((record['pid'],int(number),clock[0]))
            if cleanup_error and record['pid']==200 and number==signal.SIGTERM:raise OSError('one cleanup duty failed')
        def absent(pid,deadline):probes.append((pid,clock[0],deadline));return True
        def leaf(code):raise DeadlineExit(code)
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',side_effect=lambda:clock[0]),patch.object(owned,'signal_once',sig),patch.object(owned,'absent',absent),patch.object(e.os,'_exit',leaf):
            with self.assertRaises(DeadlineExit):x.monitor()
        c.save(self.d/('monitor-'+str(len(list(self.d.glob('monitor-*.json'))))+'.json'),
            dict(first=x.pool.first,until=x.pool.until,clock=clock[0],events=x.events,pumps=len(calls),polls=len(polls),signals=signals,probes=probes))
        return x,clock,signals,probes,polls,calls

    def test_B_repeated_timeout_reset_destination_errors_do_not_starve_duties(self):
        for error in (TimeoutError('timed out'),ConnectionResetError(errno.ECONNRESET,'reset'),OSError(errno.EDESTADDRREQ,'Destination address required')):
            x,clock,signals,probes,polls,calls=self.monitor(error)
            self.assertEqual((x.pool.first,x.pool.until),(99.75,109.75))
            self.assertGreater(len(polls),100);self.assertGreater(len(probes),100);self.assertGreater(len(calls),100)
            for pid in (200,300):
                self.assertTrue(any(p==pid and n==signal.SIGTERM for p,n,t in signals))
                self.assertTrue(any(p==pid and n==signal.SIGKILL and t>=104.75 for p,n,t in signals))
            self.assertTrue(x.cleanup_complete);self.assertLessEqual(clock[0],109.78)
            self.assertLessEqual(len(x.events),8)
            self.assertEqual(sum(v['duty']=='IPC' for v in x.events),1)

    def test_B_one_group_cleanup_error_does_not_block_other_duties(self):
        x,clock,signals,probes,polls,calls=self.monitor(TimeoutError('timed out'),cleanup_error=True)
        self.assertTrue(any(p==300 and n==signal.SIGTERM for p,n,t in signals))
        self.assertTrue(any(p==200 and n==signal.SIGKILL for p,n,t in signals))
        self.assertEqual({pid for pid,t,d in probes},{200,300});self.assertTrue(polls)
        self.assertLessEqual(len(x.events),8);self.assertEqual(x.pool.first_global['kind'],'direct_wait_observation')

    def test_B_late_earlier_guard_and_peer_preserved_after_pool_failure(self):
        x,clock,*_=self.monitor(TimeoutError('timed out'),late=True)
        self.assertEqual((x.pool.first,x.pool.until),(99.25,109.25));self.assertEqual(x.pool.first_global['role'],'peer')
        self.assertLessEqual(clock[0],109.28)

    def test_B_cancel_guard_cutoffs_still_run_with_persistent_pump_error(self):
        x=execution();x.latch.cancellation_requests=1;x.latch.requested_signal=signal.SIGTERM
        x.latch.first_cancel_at=99.5;x.guard.failure=c.Stop('guard','resource_stop');x.guard.failure_at=99.25
        x.groups={'supervisor':group(200,os.getpid()),'worker':group(300,200)}
        x.child=NS(process=NS(pid=200),report=None,poll=lambda:None)
        x.super_channel=NS(sock=NS(fileno=lambda:9));calls=[];signals=[]
        def pump():calls.append('pump');raise TimeoutError('persistent IPC')
        x.pump=pump
        class Twice:
            count=0
            def wait(self,*a):self.count+=1;return self.count>2
        x.stop=Twice()
        def sig(record,number):
            self.assertTrue(x.forwarded);self.assertIsNotNone(x.pool.until)
            signals.append((record['pid'],number))
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',return_value=100.),patch.object(c,'WORKER_SECONDS',9.9),patch.object(c,'INNER_SECONDS',9.95),patch.object(e,'NORMAL_SECONDS',9.99),patch.object(owned,'signal_once',sig),patch.object(owned,'absent',return_value=True):
            x.monitor()
        self.assertEqual(len(calls),2);self.assertEqual((x.pool.first,x.pool.until),(99.25,109.25))
        self.assertEqual(x.pool.first_global['outcome'],'resource_stop')
        self.assertEqual(len(x.forwarded),1);self.assertEqual({pid for pid,n in signals},{200,300})
        self.assertTrue(all(r['group_absent'] for r in x.groups.values()))

    def test_B_monitor_recording_failure_is_bounded_nonrecursive(self):
        x=execution();calls=[]
        def fail(error,*a):calls.append(error);raise ValueError('bad source descriptor')
        x.fail=fail
        for _ in range(100):x.monitor_duty('pump',lambda:(_ for _ in ()).throw(TimeoutError('timed out')))
        self.assertEqual(len(calls),100);self.assertEqual(len(x.events),2)

    def gate(self,fail=True):
        x=execution();x.child=NS(process=NS(pid=200));x.registration=dict(identity_sha256='id',capsule_manifest_sha256='cap')
        x.groups={'worker':group(300,200)};x.groups['worker'].update(gate_ack_attempted=False,gate_acked=False,gate_ack_failed=False)
        x.worker_ready=dict(sender=300,supervisor_pid=200,executor_pid=os.getpid(),protocol_sha256=c.PROTOCOL_SHA256)
        calls=[]
        class Channel:
            sock=object()
            def send(self,value,*a):
                calls.append(value)
                if fail:raise TimeoutError('start_ack failed')
        x.worker_channel=Channel()
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',return_value=100.),patch.object(e.select,'select',return_value=([],[],[])):
            if fail:
                with self.assertRaises(TimeoutError):e.Execution.pump(x)
            else:e.Execution.pump(x)
            for _ in range(10):e.Execution.pump(x)
        return x,calls

    def test_C_failed_ACK_attempt_once_false_boolean_no_acceptance(self):
        x,calls=self.gate()
        self.assertEqual(len(calls),1);self.assertIs(x.groups['worker']['gate_ack_attempted'],True)
        self.assertIs(x.groups['worker']['gate_acked'],False);self.assertIs(x.groups['worker']['gate_ack_failed'],True)
        self.assertIsNotNone(x.pool.until);self.assertFalse(x.recovery_proven)
        self.assertFalse(e.accept_observed(dict(accepted=False,ownership=x.groups),0,1.))

    def test_C_success_ACK_requires_send_success_strict_booleans(self):
        x,calls=self.gate(False)
        self.assertEqual(len(calls),1);self.assertIs(x.groups['worker']['gate_acked'],True)
        self.assertIs(x.groups['worker']['gate_ack_failed'],False);self.assertTrue(x.recovery_proven);self.assertIsNone(x.pool.until)

    def test_C_failed_ACK_still_collects_valid_peer_failure(self):
        x,calls=self.gate();packets=[]
        class Channel:
            sock=object()
            def receive(self,*a):return dict(kind='failure',sender=200,t0_monotonic_hex=(90.).hex(),
                first_monotonic_hex=(99.5).hex(),reason='earlier valid peer',descriptor=desc(99.5)),[]
            def send(self,value,*a):packets.append(value)
        x.super_channel=Channel()
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',return_value=100.),patch.object(e.select,'select',side_effect=lambda sockets,*a:([x.super_channel.sock],[],[])):
            e.Execution.pump(x)
        self.assertEqual((x.pool.first,x.pool.until),(99.5,109.5));self.assertEqual(len(calls),1)
        self.assertEqual(packets[0]['kind'],'failure_ack');self.assertIs(x.groups['worker']['gate_acked'],False)

    def injection(self,phase='outer:receipt-before'):
        options=preregister(dict(phase=phase,expectation_class='failed_supervisor_alive',expected_exit=1))
        event=dict(kind='injection',role=phase.split(':')[0],phase=phase.split(':')[1],monotonic=100.,
            latch_phase=options['injection_contract']['expected_latch_phase'],precondition_passed=True,
            pool_first=None,pool_until=None,first_global_failure=None,guard_failure=None,
            first_cancel_at=None,first_alarm_at=None,milestones={k:True for k in options['injection_contract']['positive_prerequisites']})
        return options,event,dict(first_global_failure=dict(timestamp=100.01))

    def test_D_retained_r9_FAILURE_injection_and_prior_failure_rejected(self):
        path=H/'retained-r9-injection.json';value=json.loads(path.read_text())
        options,event,receipt=self.injection();event.update(value['event'])
        receipt['first_global_failure']=value['first_global_failure']
        with self.assertRaisesRegex(AssertionError,'fixture_precondition_failed'):validate_injection(options,[event],receipt)

    def test_D_missing_prerequisite_wrong_phase_explicit_failure_never_counts(self):
        options,event,receipt=self.injection()
        for key in options['injection_contract']['positive_prerequisites']:
            bad=copy.deepcopy(event);bad['milestones'].pop(key)
            with self.assertRaisesRegex(AssertionError,'fixture_precondition_failed'):validate_injection(options,[bad],receipt)
        for field,value in [('latch_phase','FAILURE'),('latch_phase','DEFER'),('precondition_passed',False),('pool_first',99.5),('first_global_failure',dict(timestamp=99.5))]:
            bad=copy.deepcopy(event);bad[field]=value
            with self.assertRaisesRegex(AssertionError,'fixture_precondition_failed'):validate_injection(options,[bad],receipt)
        with self.assertRaisesRegex(AssertionError,'fixture_precondition_failed'):
            validate_injection(options,[event,dict(kind='fixture_precondition_failed')],receipt)

    def test_D_correct_NORMAL_DEFER_and_startup_milestones_registered(self):
        for phase in PHASES:
            options,event,receipt=self.injection(phase)
            self.assertTrue(validate_injection(options,[event],receipt))
        options=preregister(dict(phase='inner:spawn-before-registration',expectation_class='failed_supervisor_alive'))
        self.assertEqual(options['injection_contract']['positive_prerequisites'],['worker_spawned'])
        self.assertEqual(preregister(dict(phase='inner:pending-before'))['injection_contract']['expected_latch_phase'],'DEFER')
        self.assertEqual(preregister(dict(phase='outer:receipt-before'))['injection_contract']['expected_latch_phase'],'NORMAL')

    def test_D_receipt_earlier_failure_rejected_order_only_attribution(self):
        options,event,receipt=self.injection();receipt['first_global_failure']['timestamp']=99.9
        with self.assertRaisesRegex(AssertionError,'earlier global failure'):validate_injection(options,[event],receipt)
        receipt['first_global_failure']['timestamp']=100.1
        self.assertTrue(validate_injection(options,[event],receipt))
        self.assertIn('not_exclusive_causality',options['injection_contract']['failure_attribution'])
        options['injection_contract']['expected_latch_phase']='FAILURE'
        with self.assertRaisesRegex(AssertionError,'contract differs'):validate_injection(options,[event],receipt)

    def test_D_all15_original_scenarios_predeclared_without_receipt_inference(self):
        source=(H/'os_checks.py').read_text();tree=ast.parse(source)
        node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CASES' for t in n.targets))
        namespace={'__builtins__':{},'dict':dict};exec(compile(ast.Module(body=[node],type_ignores=[]),'registered-cases','exec'),namespace)
        cases=namespace['CASES']
        self.assertEqual(len(cases),15)
        self.assertEqual([r[0] for r in cases],['normal-closure','normal-fake-gate','inner-optional-timing-error','outer-optional-timing-error','inner-failure-with-timing-error','outer-failure-with-timing-error','post-gate-persistent-mutation','inner-final-alarm','direct-cancel-startup','direct-cancel-wait','missing-worker-ACK','parent-death','surviving-descendant','normal-deadline-wedged','RSS-resource-cap'])
        for name,options,expected in cases:
            cls='accepted' if expected in (0,2) else 'failed_no_child' if options.get('resource_cap') else 'failed_blocked_parent_crash' if name=='parent-death' else 'failed_supervisor_alive'
            registered=preregister(dict(options,expectation_class=cls,expected_exit=expected))
            self.assertEqual(registered['expectation_class'],cls)
            if options.get('phase'):self.assertIn(registered['injection_contract']['expected_latch_phase'],('NORMAL','DEFER'))

    def test_exact_r9_transport_success_consumers_protected_blocks(self):
        from source_equality import blocks,body
        for name in ('lifecycle.py','processes.py','boundary_integrity.py','freeze.py'):
            self.assertEqual((H/name).read_bytes(),(H/'r9-source'/name).read_bytes(),name)
        old=blocks(H/'r9-source/long_d2.py');new=blocks(H/'long_d2.py')
        for name in old:
            if name!='supervise_owned':self.assertEqual(old[name],new[name],name)
        self.assertEqual(body(H/'r9-source/long_d2.py'),body(H/'long_d2.py'))
        old=blocks(H/'r9-source/long_d2_executor.py');new=blocks(H/'long_d2_executor.py')
        for name in ('validate_wait_reports','accept_observed','validate_artifacts','checked_registration','worker_command'):
            self.assertEqual(old[name],new[name],name)
        self.assertEqual(c.sha(H/'protocol-r7-proposal.json'),c.PROTOCOL_SHA256)
        self.assertIn("'gate_acked'] is True",(H/'long_d2_executor.py').read_text())
