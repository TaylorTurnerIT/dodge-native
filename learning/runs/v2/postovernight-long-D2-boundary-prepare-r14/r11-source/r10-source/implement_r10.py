"""Apply only parent-confirmed repairs to the owned r9 source copy."""
from pathlib import Path
import hashlib,json
H=Path(__file__).resolve().parent
p=H/'long_d2.py';s=p.read_text()
s=s.replace("PREPARE_REL = 'learning/runs/v2/postovernight-long-D2-boundary-prepare-r9'","PREPARE_REL = 'learning/runs/v2/postovernight-long-D2-boundary-prepare-r10'")
s=s.replace('postovernight-long-D2-r2-protocol-r6.json','postovernight-long-D2-r2-protocol-r7.json')
needle='def supervise_owned(args, started, handoff, gate, *, context_provider=capsule_context,'
helper='''def worker_raw_failure(report, pid, parent, started, role):
    """Use only a validated direct wait observation; physical exit time is unknown."""
    if report['returncode'] in (0,2):
        return None
    owned.validate_report(report,pid,parent,started,time.monotonic())
    error=Stop('Worker raw/outcome failure','publication_failure')
    error.first_failure_descriptor=dict(timestamp=report['observed_monotonic'],
        kind='direct_wait_observation',outcome='publication_failure',role=role,
        timing_basis='successful_direct_waitpid_observation',signal=None,
        pid=report['pid'],reaped_by=report['reaped_by'])
    return error


'''
assert s.count(needle)==1;s=s.replace(needle,helper+needle)
needle='''            report=child.report
            worker_wait_attempted=True'''
replacement='''            report=child.report
            error=worker_raw_failure(report,process.pid,os.getpid(),started,'inner')
            if error is not None:raise error  # Before IPC, group probes or result-file IO.
            worker_wait_attempted=True'''
assert s.count(needle)==1;s=s.replace(needle,replacement);p.write_text(s)
p=H/'long_d2_executor.py';s=p.read_text();start=s.index('    def monitor(self):');end=s.index('    def pump(',start)
s=s[:start]+'''    def monitor_duty(self, name, action):
        """A fallible duty cannot suppress its independent peers or deadline check."""
        try:
            action()
        except BaseException as error:
            # Fixed-size, deduplicated diagnostics. Recording errors never recurses.
            errors=[x for x in self.events if x.get('kind')=='monitor_error']
            detail=repr(error)[:512]
            if len(errors)<8 and not any(x['duty']==name and x['error']==detail for x in errors):
                self.events.append(dict(kind='monitor_error',duty=name,error=detail))
            try:self.fail(error)  # Late earlier source evidence still tightens the pool.
            except BaseException as recording_error:
                errors=[x for x in self.events if x.get('kind')=='monitor_error']
                if len(errors)<8 and not any(x['duty']=='failure_recording' for x in errors):
                    self.events.append(dict(kind='monitor_error',duty='failure_recording',error=repr(recording_error)[:512]))

    def monitor(self):
        # Bind this watchdog's stop request. A failure during normal join must
        # not revive a retiring watchdog or inherit its requested stop.
        stop=self.stop
        while not stop.wait(.02):
            # Outside every fallible duty: persistent IPC/cleanup errors cannot
            # hide the existing absolute failure-only exit bound.
            if self.pool.until is not None and time.monotonic()>=self.pool.until:os._exit(1)
            def cancellation():
                if self.latch.cancellation_requests:
                    number=self.latch.requested_signal
                    if not self.forwarded:
                        self.forwarded.append(dict(signal=int(number),recorded_monotonic=time.monotonic(),
                                                   record_precedes_forward=True))
                        self.fail(c.Stop('Executor recorded cancellation','cancelled'),self.latch.first_cancel_at)
                        for role,record in tuple(self.groups.items()):
                            def forward(record=record):
                                if number==signal.SIGTERM:owned.signal_once(record,number)
                                else:
                                    try:os.killpg(record['pgid'],number)
                                    except ProcessLookupError:pass
                            self.monitor_duty('cancel_forward_'+role,forward)
                    else:
                        self.fail(c.Stop('Executor recorded cancellation','cancelled'),self.latch.first_cancel_at)
            self.monitor_duty('cancellation',cancellation)
            def latch_sources():
                if self.latch.first_alarm_at is not None:
                    self.fail(c.Stop('Lifetime wall alarm','wall_guard'),self.latch.first_alarm_at)
                if self.latch.deadline is not None and time.monotonic()>=self.latch.deadline:
                    self.fail(c.Stop('Absolute wall deadline','wall_guard'),self.latch.deadline)
            self.monitor_duty('latch_sources',latch_sources)
            self.monitor_duty('guard_failure',lambda:self.fail(self.guard.failure,self.guard.failure_at)
                              if self.guard is not None and self.guard.failure is not None else None)
            now=time.monotonic()
            for name,condition,at in (
                    ('Worker cutoff',now>=self.t0+c.WORKER_SECONDS and self.worker_wait is None,self.t0+c.WORKER_SECONDS),
                    ('Inner cutoff',now>=self.t0+c.INNER_SECONDS and (self.child is None or self.child.report is None),self.t0+c.INNER_SECONDS),
                    ('Outer cutoff',now>=self.t0+NORMAL_SECONDS,self.t0+NORMAL_SECONDS)):
                if condition:self.monitor_duty(name,lambda name=name,at=at:self.fail(c.Stop(name,'wall_guard'),at))
            self.monitor_duty('sample_age',lambda:self.fail(c.Stop('Outer sample age','resource_stop'))
                              if self.guard is not None and time.monotonic()-self.guard.last_sample>.5 else None)
            def direct_reap():
                report=self.child.poll() if self.child is not None else None
                if report is not None:
                    error=self.raw_inner_failure(report)
                    if error is not None:self.fail(error)
            self.monitor_duty('direct_reap',direct_reap)
            if self.pool.until is not None:
                for role,record in tuple(self.groups.items()):
                    self.monitor_duty('TERM_'+role,lambda record=record:owned.signal_once(record,signal.SIGTERM))
                    if time.monotonic()>=min(self.pool.first+5,self.pool.until-.5):
                        self.monitor_duty('KILL_'+role,lambda record=record:owned.signal_once(record,signal.SIGKILL))
                    def absence(record=record):
                        record['group_absent']=owned.absent(record['pgid'],self.pool.until)
                    self.monitor_duty('absence_'+role,absence)
                self.monitor_duty('cleanup_complete',lambda:setattr(self,'cleanup_complete',
                    self.recovery_proven and self.child is not None and self.child.report is not None
                    and all(r['group_absent'] for r in self.groups.values())))
            if self.pool.until is not None and time.monotonic()>=self.pool.until:os._exit(1)
            def ipc():
                if self.super_channel is not None and self.super_channel.sock.fileno()>=0:
                    with self.ipc_lock:self.pump()
            self.monitor_duty('IPC',ipc)
            if self.pool.until is not None and time.monotonic()>=self.pool.until:os._exit(1)

'''+s[end:]
needle="                self.worker_wait=report\n"
assert s.count(needle)==1
s=s.replace(needle,needle+"                error=c.worker_raw_failure(report,worker.get('pid'),sender,self.t0,'outer')\n                if error is not None:self.fail(error)  # Before the next packet or ACK IO.\n")
s=s.replace("self.groups['worker']=owned.verify_session(pid,sender,command,deadline)","self.groups['worker']=owned.verify_session(pid,sender,command,deadline)\n                self.groups['worker'].update(gate_ack_attempted=False,gate_acked=False,gate_ack_failed=False)")
s=s.replace("and not self.groups['worker'].get('gate_acked'):","and not self.groups['worker'].get('gate_ack_attempted',False):")
start=s.index("            self.worker_channel.send(dict(kind='start_ack'")
end=s.index('\n    def recover_registration_race',start)
s=s[:start]+'''            worker['gate_ack_attempted']=True  # One attempt, including a failed send.
            worker['gate_acked']=False
            try:
                self.worker_channel.send(dict(kind='start_ack',worker_pid=worker['pid'],
                    t0_monotonic_hex=self.t0.hex(),protocol_sha256=c.PROTOCOL_SHA256,
                    identity_sha256=self.registration['identity_sha256'],
                    capsule_manifest_sha256=self.registration['capsule_manifest_sha256']),deadline)
            except BaseException as error:
                worker['gate_ack_failed']=True
                self.fail(error)  # Failure latched before any later channel retirement.
                raise
            worker['gate_acked']=True
            worker['gate_ack_failed']=False
            self.recovery_proven=True
'''+s[end:]
# Strengthen the actual run gate; external successful consumers remain byte equal.
s=s.replace("self.groups['worker']['gate_acked'], 'Owned group registration incomplete'","self.groups['worker']['gate_acked'] is True, 'Owned group registration incomplete'")
p.write_text(s)
# Existing surviving-descendant / normal-send fixture explicitly exercises raw 0/2.
p=H/'test_r7.py';s=p.read_text().replace("self.report=wait(300,200,clock[0],1)","self.report=wait(300,200,clock[0],2 if normal_report else 1)")
s=s.replace("H/'protocol-r6-proposal.json'","H/'protocol-r7-proposal.json'");p.write_text(s)
# Exact r6 proposal base; only candidate paths and parent-confirmed semantics.
p=H/'r9-source/protocol-r6-current.json';v=json.loads(p.read_text())
def paths(x):
 if isinstance(x,str):return x.replace('postovernight-long-D2-boundary-prepare-r9','postovernight-long-D2-boundary-prepare-r10')
 if isinstance(x,list):return [paths(y) for y in x]
 if isinstance(x,dict):return {k:paths(y) for k,y in x.items()}
 return x
v=paths(v)
v['terminal_lifecycle']['r10_proven_failure_semantics']={
 'abnormal_worker_wait':'Validate successful direct waitpid observation before IPC/group/result IO; physical exit time unknown. Propagate source timestamp through supervisor failure and validated outer worker_wait; late earlier evidence tightens the same pool.',
 'monitor_duties':'Cancellation, latch, guard, cutoffs, direct reap, per-group TERM/KILL/absence and cleanup run independently; IPC last; absolute deadline outside fallible duties. Bounded deduplicated diagnostics preserve earlier sources.',
 'start_ack':'Separate boolean attempted/acked/failed; mark attempt before send; acked true only after successful send. No resend; failed send latches failure. Channel loss proves neither reap nor absence.',
 'fixture_preconditions':'Preregister phase and named positive milestones independently of receipt; NORMAL/DEFER entry rejects any earlier global failure. Record pre-mutation pool/phase/milestones; explicit fixture_precondition_failed cannot count as injection.'}
out=H/'protocol-r7-proposal.json';out.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
p=H/'long_d2.py';s=p.read_text().replace('96c170a5adb37829c2a8530d13b85d1d9c5f983a2b3582263893aa470b1ba3a4',hashlib.sha256(out.read_bytes()).hexdigest());p.write_text(s)
