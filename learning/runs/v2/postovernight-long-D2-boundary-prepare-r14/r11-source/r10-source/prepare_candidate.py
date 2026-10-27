"""One owned source preparation; never executes the candidate or validation."""
from pathlib import Path
import hashlib, json, shutil, datetime
H=Path(__file__).resolve().parent
ROOT=H.parents[3]
BASE=H.parent/'postovernight-long-D2-boundary-prepare-r6'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,sort_keys=True,indent=2,allow_nan=False)+'\n')
def replace(p,old,new):
    text=p.read_text()
    assert text.count(old)==1,(p,old[:120],text.count(old))
    p.write_text(text.replace(old,new))
pins=json.loads((BASE/'parent-frozen-pins.json').read_text())
assert len(pins)==8
for n,v in pins.items():assert sha(ROOT/n)==v,(n,v)
required={
'learning/runs/v2-orchestration/postovernight-long-D2-boundary-review-r6-parent-reconciliation.json':'80fadbc613945121bed2e4d191ca43eace6962c6d7bea79929fed12fa1905838',
'learning/runs/v2-orchestration/postovernight-long-D2-startup-reap-sonnet-r1-parent-reconciliation.json':'57547930fe3f0e167fb2068d21f0e61e861b458415abbcfea41045f407539b75',
'learning/runs/v2-orchestration/postovernight-long-D2-boundary-policy-parent-reconciliation-r1.json':'95977b36b45ad1ea670a601b51bb70198d0c0f37bb76c237b6ac032e535ebe9d',
'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r5.json':'2296154b2d06ae7c43eff0dd34c0c8908d90b5e5611a9e336a65dc2e37c48379'}
for n,v in required.items():assert sha(ROOT/n)==v,n
inputs={**pins,**required}
for n in ['docs/implementation-plan-v2.md','docs/SPEC_PRIVILEGED_VIT_RL.md','learning/runs/v2-orchestration/state.json','learning/runs/v2-orchestration/postovernight-long-D2-boundary-repair-r4-task.md','learning/runs/v2-orchestration/postovernight-long-D2-boundary-repair-r7-task.md']:
    inputs[n]=sha(ROOT/n)
for folder in ['postovernight-long-D2-boundary-review-r6','postovernight-long-D2-boundary-startup-reap-diagnosis-sonnet-r1']:
    for p in (H.parent/folder).rglob('*'):
        if p.is_file():inputs[str(p.relative_to(ROOT))]=sha(p)
save(H/'input-pins.json',dict(schema='r7_input_pins_v1',files=inputs,base_pins_verified=8,context_only_mutable_state='learning/runs/v2-orchestration/state.json',at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
(H/'r6-source').mkdir()
for p in BASE.glob('*.py'):
    shutil.copyfile(p,H/p.name);shutil.copyfile(p,H/'r6-source'/p.name)
shutil.copytree(BASE/'original-source',H/'original-source')
assert {p.name:sha(p) for p in (BASE/'original-source').iterdir()}=={p.name:sha(p) for p in (H/'original-source').iterdir()}
# Exact current external r5, with only candidate paths and specified semantics.
p=json.loads((ROOT/'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r5.json').read_text())
p['controller']=str((H/'long_d2.py').relative_to(ROOT))
t=p['terminal_lifecycle'];t['executor']=str((H/'long_d2_executor.py').relative_to(ROOT))
t.update(failure_observation_time='Successful direct waitpid observation time, never inferred process-exit time; retained source timestamp/PID/parent/raw coherence validated before drain. Earlier guard/latch/peer descriptors win; equal-time stable existing/source then guard then cancel then alarm then deadline, and first-global ties retain prior entry.',
    failed_inner_reap_reserve_seconds=1.0,
    failed_inner_direct_reaping='Mandatory immutable inner failure receipt first; after executor failure ACK and nonblocking closes, exact owned child is polled until min(current shared pool,acknowledged pool)-1.0. No signals, reset, extra allowance or ACK retry; one worker_wait send attempt marked before send on either path. Missing ACK skips extended wait.',
    failed_outer_direct_reaping='At most four existing IPC pumps before constructing failed receipt, each bounded by current shared until-.25; invalid reports reject. No queued-message delivery guarantee. Derived reaping statuses use validated direct reports only; group absence is independent cleanup fact. Missing/cap-truncated/uninterruptible reap stays unproven; no extra IO allowance.')
save(H/'protocol-r6-proposal.json',p)
controller=H/'long_d2.py';executor=H/'long_d2_executor.py'
replace(controller,"PREPARE_REL = 'learning/runs/v2/postovernight-long-D2-boundary-prepare-r6'","PREPARE_REL = 'learning/runs/v2/postovernight-long-D2-boundary-prepare-r7'")
replace(controller,"PROTOCOL_REL = 'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r5.json'","PROTOCOL_REL = 'learning/runs/v2-orchestration/postovernight-long-D2-r2-protocol-r6.json'")
replace(controller,"PROTOCOL_SHA256 = '2296154b2d06ae7c43eff0dd34c0c8908d90b5e5611a9e336a65dc2e37c48379'","PROTOCOL_SHA256 = '"+sha(H/'protocol-r6-proposal.json')+"'")
replace(executor,"    def monitor(self):",'''    def raw_inner_failure(self, report):
        if report['returncode'] in (0,2):
            return None
        # This is the retained successful direct waitpid observation, not the
        # process exit time and not this later handler's construction time.
        owned.validate_report(report, self.child.process.pid, os.getpid(), self.t0,
                              time.monotonic())
        c.require(report is self.child.report, 'Inner raw report is not retained direct observation')
        error=c.Stop('Inner raw failure','publication_failure')
        error.first_failure_descriptor=dict(timestamp=report['observed_monotonic'],
            kind='direct_wait_observation', outcome='publication_failure', role='outer',
            timing_basis='successful_direct_waitpid_observation', signal=None,
            pid=report['pid'], reaped_by=report['reaped_by'])
        return error

    def monitor(self):''')
replace(executor,"self.fail(c.Stop('Executor recorded cancellation','cancelled'),self.latch.first_at)","self.fail(c.Stop('Executor recorded cancellation','cancelled'),self.latch.first_cancel_at)")
replace(executor,"                if report is not None and report['returncode'] not in (0,2):self.fail(c.Stop('Inner raw failure','publication_failure'))",'''                if report is not None:
                    error=self.raw_inner_failure(report)
                    if error is not None:self.fail(error)''')
replace(executor,'''            for _ in range(4):
                with self.ipc_lock:self.pump()  # Finite drain of bounded terminal records.
            inner=self.child.report''','''            inner=self.child.report
            error=self.raw_inner_failure(inner)
            if error is not None:raise error  # Preserve source time before any terminal IO/drain.
            for _ in range(4):
                with self.ipc_lock:self.pump()  # Finite drain of bounded terminal records.''')
replace(executor,"    def pump(self):\n        deadline=self.pool.until or self.t0+c.INNER_SECONDS",'''    def pump(self, deadline_limit=None):
        deadline=min(self.pool.until or self.t0+c.INNER_SECONDS,
                     deadline_limit if deadline_limit is not None else math.inf)
        life.remaining(deadline)''')
replace(executor,"select.select([x.sock for x in channels],[],[],.005)","select.select([x.sock for x in channels],[],[],life.remaining(deadline,.005))")
replace(executor,"            deadline=self.pool.until or self.t0+c.INNER_SECONDS",'''            deadline=min(self.pool.until or self.t0+c.INNER_SECONDS,
                         deadline_limit if deadline_limit is not None else math.inf)
            life.remaining(deadline)''')
replace(executor,"                self.worker_wait=report",'''                owned.validate_report(report,worker.get('pid'),sender,self.t0,time.monotonic(),
                                      before=self.pool.until or self.t0+c.WORKER_SECONDS)
                self.worker_wait=report''')
replace(executor,"        result=dict(schema='long_d2_outer_acceptance_v2',accepted=False,",'''        # Finite best-effort drain inside the existing publication reserve.
        # No promise that queued datagrams will arrive or be schedulable here.
        for _ in range(4):
            try:
                with self.ipc_lock:
                    life.remaining(self.pool.until-.25)
                    self.pump(deadline_limit=self.pool.until-.25)
            except BaseException as cleanup_error:
                if len(cleanup_errors)<8:cleanup_errors.append(repr(cleanup_error))
        reaping={}
        for role,report,parent in (
                ('supervisor',None if self.child is None else self.child.report,os.getpid()),
                ('worker',self.worker_wait,self.groups.get('supervisor',{}).get('pid'))):
            status='unproven' if role in self.groups else 'not_registered'
            basis='direct_wait_report_missing'
            if report is not None:
                try:
                    owned.validate_report(report,self.groups[role]['pid'],parent,self.t0,
                                          time.monotonic(),before=self.pool.until)
                    if role=='supervisor':
                        c.require(report is self.child.report and report['pid']==self.child.process.pid,
                                  'Supervisor direct observation source differs')
                    status='direct_reaped';basis='validated_direct_parent_waitpid_report'
                except BaseException as report_error:
                    if len(cleanup_errors)<8:cleanup_errors.append(repr(report_error))
            elif role=='worker' and self.child is not None and self.child.report is not None:
                basis='supervisor_dead_before_report'
            reaping[role]=dict(status=status,basis=basis)
        result=dict(schema='long_d2_outer_acceptance_v2',accepted=False,''')
replace(executor,"            cleanup_complete=self.cleanup_complete,recovery_proven=self.recovery_proven,", "            cleanup_complete=self.cleanup_complete,recovery_proven=self.recovery_proven,reaping=reaping,")
# Own-child validation helper is additive. Existing process ownership functions stay byte equal.
with (H/'processes.py').open('a') as f:f.write('''

def validate_report(report, pid, parent, t0, now, *, before=None):
    """Validate direct observation evidence; absence never supplies a report."""
    import math
    if (not isinstance(report,dict) or type(pid) is not int or pid<=1
            or type(parent) is not int or parent<=1
            or type(report.get('pid')) is not int or report['pid']!=pid
            or type(report.get('reaped_by')) is not int or report['reaped_by']!=parent
            or report.get('direct_child_reaped') is not True
            or type(report.get('raw_wait_status')) is not int or report['raw_wait_status']<0
            or type(report.get('returncode')) is not int):
        raise life.Stop('Invalid direct wait report identity/status')
    raw=report['raw_wait_status'];stamp=report.get('observed_monotonic')
    if (not (os.WIFEXITED(raw) or os.WIFSIGNALED(raw))
            or os.waitstatus_to_exitcode(raw)!=report['returncode']
            or type(stamp) not in (int,float) or not math.isfinite(stamp)
            or not t0<=stamp<=now or before is not None and stamp>=before):
        raise life.Stop('Invalid direct wait report observation')
    return report
''')
replace(controller,"    process=child=guard=None\n    stream=io.StringIO()", "    process=child=guard=None\n    worker_wait_attempted=False\n    stream=io.StringIO()")
replace(controller,"            life.CHANNEL.send(dict(kind='worker_wait',report=report,t0_monotonic_hex=started.hex()),deadline)", "            worker_wait_attempted=True  # Mark before send: even failed sends are never retried.\n            life.CHANNEL.send(dict(kind='worker_wait',report=report,t0_monotonic_hex=started.hex()),deadline)")
needle="""        try:
            if guard is not None:
                for thread in (guard.thread,guard.verify_thread):"""
new="""        # The first inner receipt stays immutable. Later reap evidence travels
        # only over the existing IPC, with the executor still sole signal owner.
        if process is not None and child is None:
            try:child=owned.Child(process)
            except BaseException as child_error:
                result['worker_reap_diagnostic']=repr(child_error)[:512]
        result['worker_wait_send_attempted']=worker_wait_attempted
        if 'failure_ack_unavailable' not in result and child is not None:
            try:
                reap_by=min(until,life.POOL.until)-1.0
                while child.report is None and time.monotonic()<reap_by:
                    child.poll()
                    if child.report is None:
                        time.sleep(life.remaining(reap_by,.02))
                    reap_by=min(reap_by,life.POOL.until-1.0)
                if child.report is not None and not worker_wait_attempted:
                    owned.validate_report(child.report,process.pid,os.getpid(),started,
                                          time.monotonic(),before=min(until,life.POOL.until))
                    worker_wait_attempted=True
                    result['worker_wait_send_attempted']=True
                    life.CHANNEL.send(dict(kind='worker_wait',report=child.report,
                        t0_monotonic_hex=started.hex()),min(until,life.POOL.until))
                    result['worker_wait_send_status']='sent'
                elif child.report is None:
                    result['worker_reap_diagnostic']='unproven: internal reap window exhausted'
            except BaseException as reap_error:
                result['worker_reap_diagnostic']=repr(reap_error)[:512]
                if worker_wait_attempted:result['worker_wait_send_status']='failed_or_prior_attempt'
        # Retain bounded diagnostics in memory/IPC where possible; never rewrite
        # the immutable mandatory receipt or claim a delivered datagram here.
        try:
            if guard is not None:
                for thread in (guard.thread,guard.verify_thread):"""
replace(controller,needle,new)
# Keep fallback/send diagnostics bounded and visible to outer receipt through
# the same existing failure notification? No second ACK or new IPC schema.
# Diagnostic memory is returned only for pure instrumentation; immutable first receipt stays honest.
save(H/'preparation-copy.json',dict(base=str(BASE),copied_sources={p.name:sha(p) for p in (H/'r6-source').iterdir()},original_fixture_files={p.name:sha(p) for p in (H/'original-source').iterdir()},old_envelopes_copied=False,production_freeze=False))
print('eight parent pins and four authority pins verified; owned candidate sources copied and repaired')
