"""Affected Guard controls, timing provenance and first-failure discriminators."""
import ast,copy,io,json,os,signal,threading,time,types,unittest
from pathlib import Path
from unittest.mock import patch
import long_d2 as c
import lifecycle as life
H=Path(__file__).resolve().parent
E=Path(os.environ['LONG_D2_TEST_EVIDENCE'])

class Clock:
    def __init__(self):self.at=0.0
    def __call__(self):return self.at

def guard(clock,verify=lambda:None):
    return c.Guard(100,lambda:None,verify,None,clock=clock,rss=lambda:0,peak=lambda:0)

class TriggerTests(unittest.TestCase):
    def test_two_second_trigger_and_strict_completion(self):
        rows=[]
        for duration in (.9,1.5,2.9,3.1):
            clock=Clock();g=guard(clock);g.full_check(True)
            clock.at=1.999;g.full_check();self.assertEqual(len(g.timings),1)
            clock.at=2;g.verify=lambda: setattr(clock,'at',2+duration)
            if duration>3:
                with self.assertRaisesRegex(c.Stop,'Full input verification gap exceeded 5s'):g.full_check()
            else:g.full_check();self.assertAlmostEqual(g.maximum_full_gap,2+duration)
            rows.append(dict(duration=duration,timings=g.timings))
        c.save(E/'fake-clock-rows.json',rows)
    def test_old_four_second_guard_negative_discriminator(self):
        source=(H.parent/'postovernight-long-D2-prepare-r4/long_d2.py').read_text()
        node=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='Guard')
        ns=dict(vars(c));exec(compile(ast.Module(body=[node],type_ignores=[]),'original_r4_Guard','exec'),ns)
        clock=Clock();calls=[];g=ns['Guard'](100,lambda:None,lambda:calls.append(clock.at),None,clock=clock,rss=lambda:0,peak=lambda:0)
        g.full_check(True);clock.at=2;g.full_check();self.assertEqual(calls,[0.0])
        clock.at=4;g.verify=lambda:setattr(clock,'at',5.5)
        with self.assertRaisesRegex(c.Stop,'Full input verification gap exceeded 5s'):g.full_check()
        c.save(E/'old4-negative.json',dict(source_sha256=c.sha(H.parent/'postovernight-long-D2-prepare-r4/long_d2.py'),trigger2_missed=True,gap5_5_rejected=True))
    def test_scheduling_delay_and_lock_wait_are_distinct(self):
        clock=Clock();g=guard(clock);g.full_check(True);clock.at=2.25
        class Lock:
            def __enter__(self):clock.at+=.4
            def __exit__(self,*a):pass
        g.verify_lock=Lock();g.verify=lambda:setattr(clock,'at',clock.at+1.5);g.full_check()
        r=g.timings[-1];self.assertAlmostEqual(r['trigger_delay_seconds'],.25)
        self.assertAlmostEqual(r['verify_lock_wait_seconds'],.4);self.assertAlmostEqual(r['full_gap_seconds'],4.15)
        clock.at=7.8
        with self.assertRaises(c.Stop):g.full_check()
        c.save(E/'delay-rows.json',g.timings)
    def test_forced_pass_unchanged_at_every_boundary(self):
        clock=Clock();calls=[];g=guard(clock,lambda:calls.append(clock.at))
        g.check(force=True);clock.at=.1;g.check(force=True);clock.at=.2;g.check(force=True)
        self.assertEqual(calls,[0,.1,.2]);self.assertTrue(all(r['forced'] for r in g.timings))
    def test_monitor_rejects_while_verifier_in_flight(self):
        clock=[0.0];entered=threading.Event();release=threading.Event()
        g=c.Guard(100,lambda:None,lambda:None,None,clock=lambda:clock[0],rss=lambda:0,peak=lambda:0)
        g.start()
        def verify():entered.set();release.wait(1)
        g.verify=verify;clock[0]=2.0;g.last_sample=2.0
        self.assertTrue(entered.wait(.3));clock[0]=5.01;g.last_sample=5.01
        until=time.monotonic()+.3
        while g.failure is None and time.monotonic()<until:time.sleep(.005)
        try:
            self.assertIsNotNone(g.failure);self.assertTrue(g.verify_thread.is_alive())
            self.assertIn('Full input verification gap exceeded 5s',str(g.failure))
        finally:release.set();g.event.set();g.verify_thread.join(.5);g.thread.join(.5)
        c.save(E/'inflight-monitor.json',dict(failure=repr(g.failure),failure_at=g.failure_at,timings=g.timings))

class TimingTests(unittest.TestCase):
    def test_schema_integrity_components_bytes_and_teardown(self):
        pin=E/'timing-pin';pin.write_bytes(b'abc')
        def verify():
            for name in ('full_pins','capsule_walks','legacy_frozen_rebuild','origins'):
                with c.verification_component(name):c.verify_files({str(pin):c.sha(pin)})
        g=c.Guard(time.monotonic()+3,lambda:None,verify,None,rss=lambda:0,peak=lambda:0)
        g.start();g.close();r=g.timings[0]
        self.assertEqual(r['files'],8);self.assertEqual(r['bytes'],24)
        self.assertEqual(set(r['components']),{'full_pins','capsule_walks','legacy_frozen_rebuild','origins'})
        self.assertGreaterEqual(r['duration_seconds'],sum(v['duration_seconds'] for v in r['components'].values()))
        self.assertEqual(r['duration_seconds'],r['end_monotonic']-r['start_monotonic'])
        self.assertGreaterEqual(r['thread_cpu_seconds'],0)
        m=g.persist_timing(E/'timing-output.jsonl',time.monotonic()+1)
        self.assertEqual(m['sha256'],c.sha(E/'timing-output.jsonl'));self.assertEqual(m['rows'],1)
    def test_failure_and_interrupted_components_retained(self):
        def verify():
            with c.verification_component('full_pins'):raise OSError('injected verification failure')
        g=guard(Clock(),verify)
        with self.assertRaises(OSError):g.full_check(True)
        r=g.timings[0];self.assertEqual(r['status'],'failed');self.assertIsNotNone(r['end_monotonic'])
        self.assertIn('full_pins',r['components']);self.assertIn('injected verification failure',r['error'])
    def test_telemetry_IO_failure_cannot_block_monitor_or_claim_success(self):
        g=c.Guard(time.monotonic()+3,lambda:None,lambda:None,None,rss=lambda:0,peak=lambda:0)
        g.start()
        with self.assertRaisesRegex(c.Stop,'thread absence'):g.persist_timing(E/'unsafe-timing.jsonl',time.monotonic()+1)
        g.close()
        with patch.object(Path,'open',side_effect=OSError('injected timing write failure')):
            with self.assertRaises(OSError):g.persist_timing(E/'IO-failure.jsonl',time.monotonic()+1)
        self.assertFalse(g.thread.is_alive());self.assertFalse(g.verify_thread.is_alive())
        self.assertEqual(len(g.timings),1)
    def test_telemetry_expired_deadline_and_permission_forbid_persistence(self):
        g=guard(Clock());g.full_check(True)
        with self.assertRaises(c.Stop):g.persist_timing(E/'expired.jsonl',time.monotonic()-1)
        def reject():raise c.Stop('ACK unavailable')
        with self.assertRaises(c.Stop):g.persist_timing(E/'no-ack.jsonl',time.monotonic()+1,reject)
        self.assertFalse((E/'no-ack.jsonl').exists())
        self.assertFalse((E/'expired.jsonl').exists())

class MutationTests(unittest.TestCase):
    def test_pin_capsule_legacy_and_module_mirror_detected_before5(self):
        results=[]
        for kind in ('pin','capsule','legacy','module'):
            root=E/('mutation-'+kind);root.mkdir();pin=root/'source.py';pin.write_text('frozen')
            mirror=root/'mirror.py';mirror.write_text('frozen');digest=c.sha(pin)
            manifest={'version':'long_d2_capsule_v1','files':{'source.py':digest,'mirror.py':digest}}
            (root/'capsule-manifest.json').write_text('{}')
            for p in root.iterdir():p.chmod(0o444)
            root.chmod(0o555)
            clock=Clock()
            def verify():
                if kind=='module':c.check_module_origins({'legacy_module_origins':{str(pin):dict(sha256=digest,mirror='mirror.py')}},root,{'dodge_rl.fake':types.SimpleNamespace(__file__=str(pin))})
                else:
                    c.verify_files({str(pin):digest,str(mirror):digest})
                    c.assert_readonly_capsule(root,manifest)
            g=guard(clock,verify);g.full_check(True)
            try:
                target=mirror if kind=='module' else pin;target.chmod(0o644);target.write_text('mutate');target.chmod(0o444)
                clock.at=2
                with self.assertRaises(c.Stop):g.full_check()
                self.assertLessEqual(g.timings[-1]['end_monotonic'],5)
                results.append(dict(kind=kind,timing=g.timings[-1]))
            finally:root.chmod(0o755)
        c.save(E/'mutation-rows.json',results)

class PrecedenceTests(unittest.TestCase):
    def test_primary_failure_then_cleanup_TERM_stays_primary(self):
        r=c.outcome_fields('identity_or_lease_failure');c.record_primary_failure(r,c.Stop('pin failed','identity_or_lease_failure'))
        original=copy.deepcopy(r);c.record_primary_failure(r,c.Stop('Cancellation latched','cancelled'))
        self.assertEqual(r['outcome'],original['outcome']);self.assertEqual(r['error'],original['error'])
        self.assertEqual(r['secondary_failures'][0]['outcome'],'cancelled')
        c.save(E/'precedence.json',r)
    def test_user_cancellation_first_remains_primary(self):
        r={};c.record_primary_failure(r,c.Stop('Cancellation latched','cancelled'));c.record_primary_failure(r,c.Stop('later guard'))
        self.assertEqual(r['outcome'],'cancelled');self.assertEqual(r['error'],"Stop('Cancellation latched')")
        self.assertEqual(c.result_code(r),1)
    def test_latched_monitor_failure_vs_first_signal_order(self):
        g=types.SimpleNamespace(failure=c.Stop('guard first'),failure_at=1.0)
        with patch.object(life,'ACTIVE',types.SimpleNamespace(first_at=2.0)):
            self.assertIs(c.primary_error(c.Stop('TERM','cancelled'),g),g.failure)
        with patch.object(life,'ACTIVE',types.SimpleNamespace(first_at=.5)):
            self.assertEqual(c.primary_error(c.Stop('user','cancelled'),g).outcome,'cancelled')
    def test_original_overwrite_negative_discriminator(self):
        r=c.outcome_fields('identity_or_lease_failure');r['error']="Stop('pin failed')"
        # Exact original R4 cancellation update AST, not a reimplementation.
        source=(H.parent/'postovernight-long-D2-prepare-r4/long_d2.py').read_text();tree=ast.parse(source)
        worker=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='worker')
        condition=next(n for n in worker.body if isinstance(n,ast.If) and ast.unparse(n.test)=='cancel.cancellation_requests')
        node=condition.body[-1]
        ns=dict(vars(c),result=r,cancel=types.SimpleNamespace(cancellation_requests=1,requested_signal=signal.SIGTERM))
        exec(compile(ast.Module(body=[node],type_ignores=[]),'original_r4_cancel_update','exec'),ns)
        self.assertEqual(r['outcome'],'cancelled')
        c.save(E/'overwrite-negative.json',dict(original_overwrites=True,exact_ast=ast.dump(node),result=r))
