"""r11 actual-source regressions. Synthetic clock/process/socket only."""
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from contextlib import ExitStack
import ast,copy,errno,json,os,signal,socket,tempfile,threading,unittest
import lifecycle as life
import processes as owned
import long_d2 as c
import long_d2_executor as e
from test_repairs import execution,desc
from test_r7 import group,wait
import model_r11 as model
H=Path(__file__).resolve().parent
A=Path(os.environ['VALIDATION_DIR'])

class R11(unittest.TestCase):
    def setUp(self):self.d=Path(tempfile.mkdtemp(prefix=self._testMethodName+'-',dir=A))
    def save(self,name,value):c.save(self.d/(name+'.json'),value)
    def model(self,name,**kw):
        result=model.run(**kw);self.save(name,result);return result

    def test_A01_old_same_tick_negative_and_new_actual_inner_reap_fixture(self):
        old=self.model('old',old=True);new=self.model('r11')
        self.assertEqual(old['kills']['worker'],old['kills']['supervisor'])
        self.assertIsNone(old['worker_wait']);self.assertEqual(old['fixture'],'owned direct reap missing')
        self.assertEqual(new['kills']['worker'],old['kills']['worker'])
        self.assertLess(new['kills']['worker'][0],new['worker_wait']['observed_monotonic'])
        self.assertLess(new['worker_wait']['observed_monotonic'],new['kills']['supervisor'][0])
        self.assertEqual(new['worker_wait']['reaped_by'],200)
        self.assertEqual(new['reaping']['worker'],dict(status='direct_reaped',basis='validated_direct_parent_waitpid_report'))
        self.assertEqual(new['fixture'],'passed');self.assertTrue(new['cleanup_complete']);self.assertLess(new['clock'],new['until'])
        self.assertEqual(sum(kind=='worker_wait' for at,kind in new['sent']),1)
        events=[x for x in new['events'] if x['kind']=='escalation']
        self.assertEqual({x['role']:x['reason'] for x in events},{'worker':'original_cutpoint','supervisor':'validated_worker_wait'})
        self.assertEqual(len(events),2)

    def test_A02_hung_and_lost_IPC_latest_cutpoint_truthful_unproven(self):
        for name,kw in [('hung',dict(responsive=False)),('lost',dict(lost_ipc=True))]:
            r=self.model(name,**kw)
            self.assertIsNone(r['worker_wait']);self.assertEqual(r['reaping']['worker']['status'],'unproven')
            self.assertGreaterEqual(r['kills']['supervisor'][0],r['until']-.5)
            self.assertLess(r['kills']['supervisor'][0],r['until']-.5+.021)
            self.assertLess(r['kills']['worker'][0],r['kills']['supervisor'][0]);self.assertTrue(r['cleanup_complete'])
            self.assertLess(r['clock'],r['until'])
            if name=='lost':self.assertEqual(len(r['sent']),1)

    def test_A03_late_earlier_peer_tightens_current_window(self):
        r=self.model('tightened',responsive=False,tighten=True)
        self.assertEqual((r['first'],r['until']),(99.5,109.5))
        self.assertGreaterEqual(r['kills']['worker'][0],104.5);self.assertLess(r['kills']['worker'][0],104.521)
        self.assertGreaterEqual(r['kills']['supervisor'][0],109.);self.assertLess(r['kills']['supervisor'][0],109.021)

    def test_A04_late_observation_report_window_and_cap_truncation_honest(self):
        inside=self.model('late-inside',late=106.25);late=self.model('late-at-latest',late=109.26)
        self.assertIsNotNone(inside['worker_wait']);self.assertEqual(inside['fixture'],'passed')
        self.assertEqual(late['kills']['worker'],late['kills']['supervisor']);self.assertIsNone(late['worker_wait'])
        self.assertEqual(late['reaping']['worker']['status'],'unproven')
        x=execution();x.pool=life.FailurePool(90.,outer_seconds=10.)
        with patch.object(life.time,'monotonic',return_value=109.6):
            x.pool.fail('late actual source',109.5,desc(109.5))
            self.assertEqual(x.pool.until,110.)
            self.assertEqual(x.kill_due('supervisor'),'latest_bound')
        self.assertIsNone(x.worker_wait)

    def test_A05_genuine_parent_death_preserves_signal_timeline_and_orphan(self):
        old=self.model('old-orphan',old=True,responsive=False,dead_parent=True)
        new=self.model('new-orphan',responsive=False,dead_parent=True)
        self.assertEqual(old['signals'],new['signals']);self.assertIsNone(new['worker_wait'])
        self.assertEqual(new['reaping']['worker'],dict(status='unproven',basis='supervisor_dead_before_report'))
        self.assertEqual(new['inner_wait']['raw_wait_status'],7<<8)

    def test_A06_worker_TERM_natural_exit_no_KILL(self):
        r=self.model('term-exit',term_dies=True)
        self.assertEqual(r['kills'],dict(worker=[],supervisor=[]));self.assertIsNotNone(r['worker_wait'])
        self.assertTrue(r['cleanup_complete']);self.assertEqual(r['fixture'],'passed')

    def test_A07_unknown_registration_child_None_no_early_reap(self):
        for child in (None,NS(process=NS(pid=200),report=None)):
            x=execution();x.child=child;x.groups={'supervisor':group(200,os.getpid())};x.recovery_proven=False
            with patch.object(life.time,'monotonic',return_value=105.):
                x.pool.fail('source',100.,desc(100.));self.assertIsNone(x.kill_due('supervisor'))
                self.assertEqual(x.kill_due('worker'),'original_cutpoint')
            with patch.object(life.time,'monotonic',return_value=109.5):self.assertEqual(x.kill_due('supervisor'),'latest_bound')
            self.assertIsNone(x.worker_wait)

    def test_A08_only_valid_matching_actual_direct_reports_release_supervisor(self):
        x=execution();x.groups={'supervisor':group(200,os.getpid()),'worker':group(300,200)}
        with patch.object(life.time,'monotonic',return_value=105.):
            x.pool.fail('source',100.,desc(100.))
            good=wait(200,os.getpid(),104.,7);x.child=NS(process=NS(pid=200),report=good)
            self.assertEqual(x.kill_due('supervisor'),'supervisor_reaped')
            for key,value in [('pid',201),('reaped_by',os.getpid()+1),('observed_monotonic',106.),('direct_child_reaped',False)]:
                bad=copy.deepcopy(good);bad[key]=value;x.child.report=bad
                with self.assertRaises(c.Stop):x.kill_due('supervisor')
            x.child=None;x.worker_wait=wait(300,200,104.,-9)
            self.assertEqual(x.kill_due('supervisor'),'validated_worker_wait')
            x.worker_wait['reaped_by']=201
            with self.assertRaises(c.Stop):x.kill_due('supervisor')

    def test_A09_T10_gate_exception_before_cutpoint_and_after_bounded_cleanup(self):
        x=execution();clock=[100.];signals=[];x.groups={'supervisor':group(200,os.getpid()),'worker':group(300,200)}
        x.child=NS(process=NS(pid=200),report=None,poll=lambda:None)
        class Ticks:
            count=0
            def wait(self,*a):
                self.count+=1;clock[0]=100.+self.count*.02;x.guard.last_sample=clock[0]
                if clock[0]>110.1:raise AssertionError('deadline duty lost')
                return False
        x.stop=Ticks()
        def broken(role):raise RuntimeError('T10 gate failure')
        def sig(record,number):
            if number==signal.SIGKILL:signals.append((record['pid'],clock[0]))
        def leaf(code):raise model.DeadlineExit(code)
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',side_effect=lambda:clock[0]),patch.object(x,'kill_due',broken),patch.object(owned,'signal_once',sig),patch.object(owned,'absent',return_value=False),patch.object(os,'_exit',leaf):
            x.fail(c.Stop('source'),100.)
            with self.assertRaises(model.DeadlineExit):x.monitor()
        self.assertEqual({pid for pid,t in signals},{200,300});self.assertTrue(all(t>=105. for pid,t in signals))
        self.assertLess(min(t for pid,t in signals),105.021);self.assertLessEqual(clock[0],110.021)
        self.assertEqual(sum(v['kind']=='escalation' for v in x.events),2)
        self.assertLessEqual(sum(v['kind']=='monitor_error' for v in x.events),8)
        self.assertIsNone(x.worker_wait);self.assertFalse(x.cleanup_complete)
        self.save('T10',dict(signals=signals,events=x.events,clock=clock[0],first=x.pool.first,until=x.pool.until))

    def test_A10_signal_error_one_group_does_not_starve_other(self):
        r=self.model('signal-error',signal_error=True)
        self.assertTrue(any(pid==300 and n==signal.SIGKILL for t,pid,n in r['signals']))
        self.assertIsNotNone(r['worker_wait']);self.assertTrue(r['cleanup_complete']);self.assertLess(r['clock'],r['until'])

    def endpoint_case(self,*,bad_role='supervisor',bad='reset',monitor=False,final=False,late_good=False,bad_time=99.75,good_time=99.5):
        clock=[100.];x=execution();del x.pump
        x.groups={'supervisor':group(200,os.getpid()),'worker':group(300,200)}
        x.child=NS(process=NS(pid=200),report=None,poll=lambda:None)
        x.registration=dict(identity_sha256='id',capsule_manifest_sha256='cap')
        x.recovery_proven=False;reads=[];sends=[];receive_deadlines=[];send_deadlines=[]
        def failure(role,at=99.5):return dict(schema='long_d2_owned_ipc_v1',seq=1,kind='failure',sender=200 if role=='supervisor' else 300,
            t0_monotonic_hex=(90.).hex(),first_monotonic_hex=at.hex(),reason=role+' earlier source',descriptor=desc(at,'resource_stop',role))
        sockets={};channels={}
        for role in ('supervisor','worker'):
            good=failure(role,bad_time if role==bad_role else good_time)
            raw=json.dumps(good).encode();anc=[];flags=0
            if role==bad_role:
                if bad=='empty':raw=b''
                elif bad=='data':raw=b'not-json'
                elif bad=='seq':good['seq']=2;raw=json.dumps(good).encode()
                elif bad=='schema':good['schema']='wrong';raw=json.dumps(good).encode()
                elif bad=='sender':good['sender']=301;raw=json.dumps(good).encode()
                elif bad=='clock':good['t0_monotonic_hex']=(91.).hex();raw=json.dumps(good).encode()
                elif bad=='time':good['first_monotonic_hex']=(101.).hex();raw=json.dumps(good).encode()
                elif bad=='flags':flags=socket.MSG_TRUNC
                elif bad=='fd':
                    import array
                    anc=[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[8765]).tobytes())]
            class Sock:
                def __init__(self,role,raw,anc,flags):self.role=role;self.raw=raw;self.anc=anc;self.flags=flags;self.pending=True
                def fileno(self):return 9 if self.role=='supervisor' else 10
                def settimeout(self,value):pass
                def recvmsg(self,*a):
                    reads.append(self.role);receive_deadlines.append((self.role,clock[0]))
                    if self.role==bad_role and bad=='reset':raise ConnectionResetError(errno.ECONNRESET,'synthetic actual receive reset')
                    self.pending=False
                    return self.raw,self.anc,self.flags,None
                def sendmsg(self,parts,anc):
                    value=json.loads(parts[0]);sends.append((self.role,value,clock[0]))
                    if self.role==bad_role and bad=='send':raise OSError(errno.EDESTADDRREQ,'synthetic ACK send failure')
                    return len(parts[0])
            sock=Sock(role,raw,anc,flags);channel=life.Channel.__new__(life.Channel)
            channel.sock=sock;channel.received=channel.sent=0;channel.lock=threading.RLock();channel.t0=90.
            sockets[role]=sock;channels[role]=channel
        x.super_channel=channels['supervisor'];x.worker_channel=channels['worker']
        def ready(values,*a):return [s for s in values if s.pending],[],[]
        class Ticks:
            count=0
            def wait(self,*a):
                self.count+=1;clock[0]=100.+self.count*.02;x.guard.last_sample=clock[0]
                return self.count>10
        x.stop=Ticks()
        actual_receives=[]
        for role,channel in channels.items():
            receive=channel.receive
            def observed(deadline,receive=receive,role=role):actual_receives.append((role,deadline));return receive(deadline)
            channel.receive=observed
            send=channel.send
            def observed_send(value,deadline,send=send,role=role):send_deadlines.append((role,deadline));return send(value,deadline)
            channel.send=observed_send
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',side_effect=lambda:clock[0]),patch.object(e.select,'select',ready),patch.object(owned,'signal_once'),patch.object(owned,'absent',return_value=False):
            x.pool.fail('known direct source',99.75,desc(99.75,'publication_failure','outer'))
            if monitor:x.monitor()
            else:
                with self.assertRaises((c.Stop,OSError,ValueError,json.JSONDecodeError)):
                    e.Execution.pump(x,deadline_limit=109.5 if final else None)
            if late_good:
                # A prior empty datagram must not retire a channel or consume seq1.
                peer=sockets[bad_role];peer.raw=json.dumps(failure(bad_role,99.25)).encode();peer.anc=[];peer.flags=0;peer.pending=True
                e.Execution.pump(x)
        result=dict(first=x.pool.first,until=x.pool.until,local=x.pool.first_local,global_descriptor=x.pool.first_global,
                    reads=reads,sends=sends,events=x.events,receive_deadlines=actual_receives,send_deadlines=send_deadlines,recovery=x.recovery_proven)
        self.save('endpoint-'+bad_role+'-'+bad,result)
        return x,result,channels

    def test_B01_actual_monitor_reset_S_readable_W_preserves_source_and_ACK_once(self):
        x,r,_=self.endpoint_case(monitor=True)
        self.assertEqual((r['first'],r['until']),(99.5,109.5));self.assertEqual(r['reads'].count('worker'),1)
        self.assertEqual(r['reads'].count('supervisor'),10)
        self.assertEqual(sum(role=='worker' and v['kind']=='failure_ack' for role,v,t in r['sends']),1)
        self.assertTrue(any(v.get('duty')=='IPC_supervisor' for v in r['events']))
        self.assertFalse(x.recovery_proven)
        self.assertLessEqual(sum(v['kind']=='monitor_error' for v in r['events']),8)
        source=next(v['source'] for v in r['events'] if v.get('duty')=='IPC_supervisor')
        self.assertEqual(source['endpoint'],'supervisor');self.assertEqual(source['timestamp'],100.02)

    def test_B02_actual_Channel_empty_S_and_valid_W(self):
        x,r,channels=self.endpoint_case(bad='empty')
        self.assertEqual((r['first'],r['until']),(99.5,109.5));self.assertEqual(r['reads'],['supervisor','worker'])
        self.assertEqual(len(r['sends']),1);self.assertEqual(channels['supervisor'].received,0)
        self.assertFalse(getattr(channels['supervisor'],'peer_closed',False))

    def test_B03_inverse_endpoint_errors_do_not_lose_valid_supervisor(self):
        for bad in ('reset','empty','data','send'):
            x,r,_=self.endpoint_case(bad_role='worker',bad=bad)
            self.assertEqual((r['first'],r['until']),(99.5,109.5));self.assertEqual(r['reads'],['supervisor','worker'])
            self.assertEqual(sum(role=='supervisor' and v['kind']=='failure_ack' for role,v,t in r['sends']),1)

    def test_B04_validation_and_ACKsend_errors_S_never_starve_W(self):
        for bad in ('data','seq','schema','sender','clock','time','flags','fd','send'):
            x,r,_=self.endpoint_case(bad=bad)
            self.assertEqual((r['first'],r['until']),(99.5,109.5));self.assertEqual(r['reads'],['supervisor','worker'])
            self.assertEqual(sum(role=='worker' and v['kind']=='failure_ack' for role,v,t in r['sends']),1)
            self.assertFalse(x.recovery_proven);self.assertIsNone(x.worker_wait)
            if bad!='send':self.assertFalse(any(role=='supervisor' for role,v,t in r['sends']))
            self.assertTrue(any(v.get('duty')=='IPC_supervisor' for v in r['events']))

    def test_B05_empty_endpoint_future_valid_readiness_not_dropped(self):
        x,r,ch=self.endpoint_case(bad='empty',late_good=True)
        self.assertEqual((r['first'],r['until']),(99.25,109.25))
        self.assertEqual(r['reads'],['supervisor','worker','supervisor']);self.assertEqual(ch['supervisor'].received,1)
        self.assertEqual([role for role,v,t in r['sends']],['worker','supervisor'])

    def test_B06_final_drain_current_shortened_deadline_and_one_ACK(self):
        x,r,_=self.endpoint_case(bad='send',final=True,bad_time=99.5,good_time=99.25)
        self.assertEqual((r['first'],r['until']),(99.25,109.25))
        self.assertEqual(r['receive_deadlines'],[('supervisor',109.5),('worker',109.25)])
        self.assertEqual(r['send_deadlines'],[('supervisor',109.25),('worker',109.)])
        # Each actual send checks a newly tightened until-.25; no extra allowance.
        self.assertEqual(sum(role=='worker' for role,v,t in r['sends']),1)
        self.assertEqual(r['global_descriptor']['role'],'worker')

    def test_B07_normal_failure_cannot_set_gate_ACK_or_recovery(self):
        x=execution();del x.pump;x.child=NS(process=NS(pid=200),report=None)
        x.groups={'worker':group(300,200)};x.groups['worker'].update(gate_ack_attempted=False,gate_acked=False,gate_ack_failed=False)
        x.worker_ready=dict(sender=300,supervisor_pid=200,executor_pid=os.getpid(),protocol_sha256=c.PROTOCOL_SHA256)
        sends=[]
        class Broken:
            sock=object()
            def receive(self,*a):raise OSError('bad first endpoint')
        class Worker:
            sock=object()
            def send(self,*a):sends.append(a)
        x.super_channel=Broken();x.worker_channel=Worker()
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',return_value=100.),patch.object(e.select,'select',return_value=([x.super_channel.sock],[],[])):
            with self.assertRaises(OSError):x.pump()
        self.assertFalse(sends);self.assertIs(x.groups['worker']['gate_acked'],False);self.assertFalse(x.recovery_proven)

    def test_B08_successful_expected_close_retirement_proves_no_reap(self):
        x=execution();del x.pump;x.inner_ready={};x.child=NS(process=NS(pid=200),report=None)
        class Channel:
            sock=object()
            def receive(self,*a):raise ConnectionResetError('expected completed close')
        x.super_channel=Channel()
        with patch.object(life.time,'monotonic',return_value=100.),patch.object(e.select,'select',return_value=([x.super_channel.sock],[],[])):x.pump()
        self.assertTrue(x.super_channel.peer_closed);self.assertIsNone(x.worker_wait);self.assertIsNone(x.child.report)
        self.assertFalse(x.recovery_proven);self.assertFalse(x.cleanup_complete)

    def test_B09_peer_tightening_expiry_stops_final_drain_without_new_allowance(self):
        x=execution();del x.pump;clock=[100.];calls=[]
        x.groups={'supervisor':group(200,os.getpid()),'worker':group(300,200)}
        x.child=NS(process=NS(pid=200),report=None)
        class First:
            sock=object()
            def receive(self,deadline):
                calls.append(('S_receive',deadline))
                return dict(kind='failure',sender=200,t0_monotonic_hex=(90.).hex(),first_monotonic_hex=(99.5).hex(),reason='earlier',descriptor=desc(99.5)),[]
            def send(self,value,deadline):
                calls.append(('S_ACK',deadline));clock[0]=109.3;life.remaining(deadline)
        class Second:
            sock=object()
            def receive(self,deadline):raise AssertionError('sibling read after tightened final-drain expiry')
        x.super_channel=First();x.worker_channel=Second()
        with patch.object(life,'ACTIVE',x.latch),patch.object(life.time,'monotonic',side_effect=lambda:clock[0]),patch.object(e.select,'select',side_effect=lambda sockets,*a:(sockets,[],[])):
            x.pool.fail('prior',99.75,desc(99.75))
            with self.assertRaisesRegex(c.Stop,'Absolute deadline'):x.pump(deadline_limit=109.5)
        self.assertEqual((x.pool.first,x.pool.until),(99.5,109.5))
        self.assertEqual(calls,[('S_receive',109.5),('S_ACK',109.25)]);self.assertIsNone(x.worker_wait)
        self.save('expired-tightened-drain',dict(calls=calls,clock=clock[0],first=x.pool.first,until=x.pool.until,events=x.events))

    def test_C01_exact_success_consumers_transport_inner_fixtures_and_old91(self):
        from source_equality import blocks,body
        for name in ('lifecycle.py','processes.py','boundary_integrity.py','freeze.py','fixture_guards.py','fixture_preconditions.py','os_checks.py','synthetic.py'):
            self.assertEqual((H/name).read_bytes(),(H/'r10-source'/name).read_bytes(),name)
        old=blocks(H/'r10-source/long_d2.py');new=blocks(H/'long_d2.py')
        self.assertEqual(old,new);self.assertEqual(body(H/'long_d2.py'),body(H/'r10-source/long_d2.py'))
        old=blocks(H/'r10-source/long_d2_executor.py');new=blocks(H/'long_d2_executor.py')
        for key in old:
            if key!='Execution':self.assertEqual(old[key],new[key],key)
        methods=lambda text:{n.name:ast.get_source_segment(text,n) for node in ast.parse(text).body if isinstance(node,ast.ClassDef) and node.name=='Execution' for n in node.body if isinstance(n,ast.FunctionDef)}
        a=methods((H/'r10-source/long_d2_executor.py').read_text());b=methods((H/'long_d2_executor.py').read_text())
        self.assertEqual(sorted(k for k in a if a[k]!=b[k]),['monitor','monitor_duty','pump']);self.assertEqual(set(b)-set(a),{'kill_due'})
        old_methods=[]
        for name in ('test_r10.py','test_r7.py','test_repairs.py','test_boundary.py'):
            tree=ast.parse((H/'r10-source'/name).read_text());prior=[n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
            now=[n.name for n in ast.walk(ast.parse((H/name).read_text())) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
            self.assertEqual(prior,now);old_methods.extend(prior)
        self.assertEqual(len(old_methods),91)
        self.assertEqual(c.sha(H/'protocol-r8-proposal.json'),c.PROTOCOL_SHA256)

    def test_C02_protocol_only_candidate_paths_and_qualified_semantics(self):
        original=json.loads((H/'r10-source/protocol-r7-proposal.json').read_text())
        proposed=json.loads((H/'protocol-r8-proposal.json').read_text());proposed.pop('r11_qualified_repairs')
        normalized=json.loads(json.dumps(proposed).replace('postovernight-long-D2-boundary-prepare-r11','postovernight-long-D2-boundary-prepare-r10').replace('postovernight-long-D2-r2-protocol-r8.json','postovernight-long-D2-r2-protocol-r7.json'))
        self.assertEqual(original,normalized)
        self.assertIn('r11',c.PREPARE_REL);self.assertTrue(c.PROTOCOL_REL.endswith('protocol-r8.json'))
