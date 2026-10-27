"""Complete r7 sources before the single registered validation stage."""
from pathlib import Path
H=Path(__file__).resolve().parent
def replace(name,old,new):
    p=H/name;t=p.read_text();assert t.count(old)==1,(name,old[:100],t.count(old));p.write_text(t.replace(old,new))
replace('long_d2_executor.py',"            first_failure_monotonic=self.pool.first,cleanup_until_monotonic=self.pool.until,", "            executor_t0_monotonic=self.t0,\n            first_failure_monotonic=self.pool.first,cleanup_until_monotonic=self.pool.until,")
replace('long_d2.py',"        # Retain bounded diagnostics in memory/IPC where possible; never rewrite\n        # the immutable mandatory receipt or claim a delivered datagram here.",'''        # Optional bounded diagnostics follow the immutable mandatory receipt.
        # They never create an allowance, retry a send, or establish delivery.
        if 'failure_ack_unavailable' not in result:
            try:
                mandatory_failure(args.output/'inner-reap-diagnostic.json',
                    dict(optional=True,worker_wait_send_attempted=worker_wait_attempted,
                         worker_wait_send_status=result.get('worker_wait_send_status','prior_attempt_or_none'),
                         worker_reap_diagnostic=result.get('worker_reap_diagnostic'),
                         worker_reaped=child is not None and child.report is not None),
                    min(until,life.POOL.until))
            except BaseException:pass''')
# Existing process primitives unchanged; additive validator explicitly allowed.
replace('source_equality.py',"    assert (H/'processes.py').read_bytes()==(frozen/'processes.py').read_bytes()",'''    old_processes=blocks(frozen/'processes.py');new_processes=blocks(H/'processes.py')
    assert all(new_processes[k]==v for k,v in old_processes.items())
    assert set(new_processes)-set(old_processes)=={'validate_report'}''')
replace('test_repairs.py',"if rc is not None:x.child=NS(poll=lambda:dict(returncode=rc),report=dict(returncode=rc))",'''if rc is not None:
            report=dict(pid=123,reaped_by=os.getpid(),direct_child_reaped=True,
                        returncode=rc,raw_wait_status=(-rc if rc<0 else rc<<8),observed_monotonic=99.75)
            x.child=NS(process=NS(pid=123),poll=lambda:report,report=report)''')
# Replace old simplistic fixture examples with explicit full reports and class.
start=(H/'test_repairs.py').read_text().index('    def test_fixture_guards_missing_receipt_empty_owned_and_milestones(')
end=(H/'test_repairs.py').read_text().index("\nif __name__",start)
p=H/'test_repairs.py';t=p.read_text();t=t[:start]+'''    def test_fixture_guards_missing_receipt_empty_owned_and_milestones(self):
        empty=dict(ownership={},accepted=False);pre=[dict(kind='ownership',ownership={},owned_spawns=[])]
        opt=dict(resource_cap=True,expectation_class='failed_no_child')
        self.assertTrue(validate_fixture(empty,pre,{},opt,receipt_available=True))
        for available,events in ((False,pre),(True,[])):
            with self.assertRaises(AssertionError):validate_fixture(empty,events,{},opt,receipt_available=available)
        from test_r7 import fixture
        r,events,options=fixture()
        self.assertTrue(validate_fixture(r,events,{'worker':True,'supervisor':True},options,receipt_available=True))
        for extra in (dict(mode='wedged'),dict(phase='inner:spawn-before-registration')):
            with self.assertRaises(AssertionError):validate_fixture(r,events,{'worker':True,'supervisor':True},dict(options,**extra),receipt_available=True)
        with self.assertRaises(AssertionError):validate_fixture(r,events,{},options,receipt_available=True)
        bad=copy.deepcopy(r);bad.pop('worker_wait')
        with self.assertRaises(AssertionError):validate_fixture(bad,events,{'worker':True,'supervisor':True},options,receipt_available=True)
        events.append(dict(kind='wedged_entry',role='worker'))
        self.assertTrue(validate_fixture(r,events,{'worker':True,'supervisor':True},dict(options,mode='wedged'),receipt_available=True))
''' +t[end:];p.write_text(t)
# Existing cache control executes toy source in-process; no OS subprocess tests.
p=H/'test_boundary.py';t=p.read_text();start=t.index("        source=self.d/'toy.py'",t.index('def test_17_'));end=t.index('\n    def summary_fixture',start)
t=t[:start]+'''        import importlib.machinery
        import py_compile
        source=self.d/'toy.py';source.write_text('value="WRONG"\\n')
        # Patch only this fixture's cache prefix; never touch an original cache.
        with patch.object(sys,'pycache_prefix',None):
            py_compile.compile(str(source),doraise=True)
            st=source.stat();source.write_text('value="RIGHT"\\n');os.utime(source,ns=(st.st_atime_ns,st.st_mtime_ns))
            old={};exec(importlib.machinery.SourceFileLoader('toy',str(source)).get_code('toy'),old)
        cache=self.d/'fresh';cache.mkdir()
        with patch.object(sys,'pycache_prefix',str(cache)):
            fresh={};exec(importlib.machinery.SourceFileLoader('toy',str(source)).get_code('toy'),fresh)
        self.assertEqual(old['value'],'WRONG');self.assertEqual(fresh['value'],'RIGHT');self.assertFalse(any(cache.iterdir()))
        c.save(self.d/'pyc-control.json',{'old_B_only':old['value'],'fresh_prefix':fresh['value'],'in_process_only':True})
''' +t[end:];p.write_text(t)
replace('os_checks.py',"    root=directory/name;root.mkdir()",'''    # Preregister from the injected scenario, before any receipt exists.
    cls=('accepted' if expected in (0,2) else 'failed_no_child' if options.get('resource_cap')
         else 'failed_blocked_parent_crash' if name=='parent-death' else 'failed_supervisor_alive')
    options=dict(options,expectation_class=cls,expected_exit=expected)
    root=directory/name;root.mkdir()''')
# Track registration/report milestones in the existing fixture hook only.
replace('synthetic.py',"    fired=False;writers=set();final_execution=[None];owned_spawns=[]", "    fired=False;writers=set();final_execution=[None];owned_spawns=[]\n    registered_worker=[None];worker_wait_attempted=[False]")
replace('synthetic.py',"    real_poll=owned.Child.poll",'''    real_receive=life.Channel.receive
    def receiving(channel,*a,**kw):
        value,fds=real_receive(channel,*a,**kw)
        if role=='inner' and value.get('kind')=='registered':registered_worker[0]=value['worker_pid']
        return value,fds
    life.Channel.receive=receiving
    real_send=life.Channel.send
    def sending(channel,value,*a,**kw):
        if role=='inner' and value.get('kind')=='worker_wait':worker_wait_attempted[0]=True
        return real_send(channel,value,*a,**kw)
    life.Channel.send=sending
    real_poll=owned.Child.poll''')
replace('synthetic.py',"        if role=='inner' and child.process.args[3:4]==['worker']:trigger('during-worker')",'''        if role=='inner' and child.process.args[3:4]==['worker']:
            if (not fired and options.get('expectation_class')=='failed_blocked_parent_crash'):
                # Require the blocked worker's positive marker and current live
                # parent/PID census before the deliberately injected crash.
                by=life.POOL.deadline(life.POOL.t0+c.WORKER_SECONDS)
                while True:
                    life.remaining(by)
                    path=root/'worker-events.jsonl'
                    markers=[] if not path.exists() else [json.loads(line) for line in path.read_text().splitlines()]
                    if any(x['kind']=='blocked_entry' and x.get('pid')==child.process.pid for x in markers):break
                    life.ACTIVE.check();time.sleep(life.remaining(by,.01))
                rows=owned.census(by)
                live=any(x['pid']==child.process.pid and x['ppid']==os.getpid() for x in rows)
                c.require(registered_worker[0]==child.process.pid and live and child.report is None and not worker_wait_attempted[0], 'Blocked crash milestone unavailable')
                event('registered_worker_live_at_crash',worker_pid=child.process.pid,supervisor_pid=os.getpid(),
                      registered=True,live_at_crash=True,blocked_entry=True,prior_worker_wait=False)
            trigger('during-worker')''')
print('fixture classes and original 39 method contracts prepared; no validation executed')
