from pathlib import Path
H=Path(__file__).resolve().parent
p=H/'long_d2.py';s=p.read_text().replace('import socket\n','import socket\nimport stat\n')
s=s.replace("PREPARE_REL = 'learning/runs/v2/postovernight-long-D2-boundary-prepare-r3'","PREPARE_REL = 'learning/runs/v2/postovernight-long-D2-boundary-prepare-r4'")
# Protocol remains deliberately unusable until the parent publishes and pins r5.
s=s.replace("postovernight-long-D2-r2-protocol-r4.json","postovernight-long-D2-r2-protocol-r5.json").replace("78ade5cb0c27b54319b22dd1287ec99ac9e2b27828424b2953b7238508b007c3","PARENT_MUST_PUBLISH_AND_PIN_PROTOCOL_R5_BEFORE_FREEZE")
a=s.index('def assert_readonly_capsule(');z=s.index('\n\ndef check_module_origins',a)
s=s[:a]+'''def assert_readonly_capsule(root, manifest):
    """One fresh metadata traversal per pass; no stat/content cache across passes.

    This checks declared disk state under the cooperative no-writer assumption.
    It does not attest loaded memory or defeat concurrent same-user replacement.
    """
    root = Path(root)
    canonical_root = root.resolve(strict=True)  # Exactly one canonicalization.
    require(root.is_absolute() and root == canonical_root and root != ORIGINAL_ROOT
            and manifest['version'] == 'long_d2_capsule_v1', 'Execute readonly canonical capsule only')
    # resolve() can leave a self-pointing alias lexically unchanged: inspect every
    # ancestor for symlinks as well. Ancestors outside root need not be readonly.
    for ancestor in (root, *root.parents):
        mode = ancestor.lstat().st_mode
        require(stat.S_ISDIR(mode), 'Capsule root/ancestor is not a real directory')
    expected = set(manifest['files']) | {'capsule-manifest.json'}
    for name in expected:
        require(type(name) is str and name and not Path(name).is_absolute()
                and str(Path(name)) == name and all(x not in ('', '.', '..') for x in name.split('/')),
                'Unsafe capsule member')
    require(not root.lstat().st_mode & 0o222, 'Capsule directory is writable')
    actual = set()
    def walk(directory, prefix):
        with os.scandir(directory) as entries:
            for entry in entries:
                name = prefix + entry.name
                mode = entry.stat(follow_symlinks=False).st_mode
                require(not stat.S_ISLNK(mode), 'Capsule contains symlink')
                if stat.S_ISDIR(mode):
                    require(not mode & 0o222, 'Capsule directory is writable')
                    walk(entry.path, name + '/')
                else:
                    require(stat.S_ISREG(mode), 'Capsule contains special file')
                    require(not mode & 0o222, 'Capsule file is writable')
                    require(name in expected, 'Capsule file inventory differs')
                    actual.add(name)
    walk(root, '')
    require(actual == expected, 'Capsule file inventory differs')
''' +s[z:]
s=s.replace("    candidates = []\n    now = time.monotonic()\n    if guard is not None", "    if not isinstance(error, BaseException):\n        error = Stop(str(error), 'safety_stop')\n    candidates = []\n    now = time.monotonic()\n    existing = getattr(error, 'first_failure_descriptor', None)\n    if existing is not None:\n        candidates.append((existing['timestamp'], error, existing['kind'], existing['timing_basis'], existing.get('signal')))\n    if guard is not None",1)
s=s.replace("    descriptor = dict(timestamp=at, kind=kind, outcome=failure_outcome(primary), role=role, timing_basis=basis, signal=number)","    descriptor = (dict(existing) if existing is not None and primary is error and at == existing['timestamp'] else\n                  dict(timestamp=at, kind=kind, outcome=failure_outcome(primary), role=role, timing_basis=basis, signal=number))")
a=s.index('    now = time.monotonic()\n    candidates = [now]',s.index('def worker_failure'));z=s.index('    if learner is not None:',a)
s=s[:a]+'''    if life.ACTIVE is not None:
        life.ACTIVE.phase = 'FAILURE'
    local_until = life.POOL.fail(error)
'''+s[z:]
s=s.replace('deadline = life.notify_failure(error, life.POOL.first)','deadline = life.notify_failure(error)')
a=s.index('        try:\n            life.remaining(until)',s.index('def supervise_owned'));z=s.index('        return 1,guard',a)
s=s[:a]+'''        # Publish before guard joins, stream/gate closure, or optional telemetry.
        # Unproven handles/children remain explicit; this is never acceptance.
        result.update(cleanup_complete=False, experiment_status='failed_partial',
                      owned_guard_handles_absent=False,
                      owned_worker_reaped=child is not None and child.report is not None,
                      worker_wait=None if child is None else child.report)
        try:
            if args.output.is_dir():
                mandatory_failure(args.output/'inner-failure.json',result,until)
        except BaseException as publication_error:
            result['mandatory_failure_publication_error']=repr(publication_error)
        for action in (
            lambda: guard.event.set() if guard is not None else None,
            lambda: setattr(guard,'stream',None) if guard is not None else None,
            stream.close, gate.close):
            try: action()
            except BaseException: pass
        try:
            if guard is not None:
                for thread in (guard.thread,guard.verify_thread):
                    if thread is not None:thread.join(timeout=life.remaining(until,.5))
        except BaseException: pass
        try:
            if guard is not None:
                optional_timing(guard,args.output.parent/'inner-verification.jsonl',until)
        except BaseException: pass
        try: life.CHANNEL.sock.close()
        except BaseException: pass
'''+s[z:]
p.write_text(s)
p=H/'lifecycle.py';s=p.read_text();a=s.index('    now = time.monotonic()\n    candidates = [now]',s.index('def notify_failure'));z=s.index("    if ACTIVE is not None:\n        ACTIVE.phase",a)
s=s[:a]+'''    descriptor = getattr(error, 'first_failure_descriptor', None)
    if descriptor is not None and at is not None and descriptor.get('timestamp') != at:
        raise Stop('Failure descriptor timestamp differs')
    now = time.monotonic()
    candidates = []
    if descriptor is not None:
        candidates.append((descriptor['timestamp'], error, descriptor))
    else:
        observed = now if at is None else at
        candidates.append((observed, error, None))
    if ACTIVE is not None:
        for stamp, outcome, kind in ((ACTIVE.first_cancel_at, 'cancelled', 'cancel'),
                                     (ACTIVE.first_alarm_at, 'wall_guard', 'alarm'),
                                     (ACTIVE.deadline if now >= ACTIVE.deadline else None, 'wall_guard', 'deadline')):
            if stamp is not None:
                reason = Stop('Cancellation latched' if outcome == 'cancelled' else 'Absolute wall deadline', outcome)
                source = dict(timestamp=stamp, kind=kind, outcome=outcome, role='local',
                              timing_basis='latched_signal_or_absolute_deadline', signal=None)
                candidates.append((stamp, reason, source))
    at, primary, source = min(candidates, key=lambda item:item[0])
    until = POOL.fail(primary, at, source)
'''+s[z:]
# Receive diagnostics: one attempt, no payload or speculative transport change.
a=s.index('    def receive(self, deadline, sender=None):');z=s.index('\n\ndef notify_failure',a)
old=s[a:z];old=old.replace('        raw, ancillary, flags, _ = self.sock.recvmsg(60001, socket.CMSG_SPACE(4))','''        context = dict(operation='recvmsg', expected_sender=sender, received_sequence=self.received,
                       next_sequence=self.received+1, fd=self.sock.fileno(),
                       buffer_bytes=60001, ancillary_capacity=socket.CMSG_SPACE(4),
                       raw_length=None, flags=None, errno=None)
        try:
            raw, ancillary, flags, _ = self.sock.recvmsg(60001, socket.CMSG_SPACE(4))
        except OSError as error:
            context['errno'] = error.errno
            self.last_receive_failure = context
            reason = Stop('Owned IPC receive failed: '+json.dumps(context,sort_keys=True))
            reason.ipc_receive_diagnostic = context
            raise reason from error
        context.update(raw_length=len(raw), flags=flags, ancillary_records=len(ancillary))''')
old=old.replace("            raise Stop('Truncated owned IPC packet')","            self.last_receive_failure = context\n            reason = Stop('Truncated owned IPC packet: '+json.dumps(context,sort_keys=True))\n            reason.ipc_receive_diagnostic = context\n            raise reason")
# Record context also for parse, schema and sender errors, with no raw bytes.
start=old.index('        remaining(deadline)\n',old.index('context.update'))
prefix=old[:start];tail=old[start:];old=prefix+"        try:\n"+''.join('    '+line if line.strip() else line for line in tail.splitlines(True))+'''        except BaseException as error:
            self.last_receive_failure = context
            try: error.ipc_receive_diagnostic = context
            except (AttributeError, TypeError): pass
            raise
'''
s=s[:a]+old+s[z:];p.write_text(s)
p=H/'long_d2_executor.py';s=p.read_text();a=s.index('    def fail(self,error,at=None):');z=s.index('\n    def authority',a)
s=s[:a]+'''    def fail(self,error,at=None):
        if not isinstance(error,BaseException):
            error=c.Stop(str(error),'safety_stop')
        existing=getattr(error,'first_failure_descriptor',None)
        if existing is not None and at is not None:
            c.require(existing.get('timestamp')==at,'Failure descriptor timestamp differs')
        if at is not None and existing is None:
            error.first_failure_descriptor=dict(timestamp=at,kind='peer_or_source_failure',
                outcome=c.failure_outcome(error),role='outer',timing_basis='explicit_source_timestamp',signal=None)
        primary,descriptor=c.observed_failure(error,self.guard,'outer')
        self.pool.fail(primary,descriptor['timestamp'],descriptor)
        self.latch.phase='FAILURE'
'''+s[z:]
for msg,outcome in [('Executor recorded cancellation','cancelled'),('Worker cutoff','wall_guard'),('Inner cutoff','wall_guard'),('Outer cutoff','wall_guard'),('Outer sample age','resource_stop'),('Inner raw failure','publication_failure')]:
 s=s.replace("self.fail('"+msg+"'","self.fail(c.Stop('"+msg+"','"+outcome+"')")
s=s.replace("self.fail(error,self.guard.failure_at if self.guard is not None else None)","self.fail(error)")
a=s.index('            try:\n                if self.child is not None:',s.index('        except BaseException as error:',s.index('    def run(self)')));z=s.index('            code=1',a)
s=s[:a]+'''            self.publish_failed(receipt_path,error)
'''+s[z:]
# Isolate the actual failure handler for direct real-class tests, preserving the same watchdog.
a=s.index('\n    def run(self):')
s=s[:a]+'''
    def publish_failed(self,receipt_path,error):
        """Reserve the final .25s of the same pool for a mandatory attempt.

        The watchdog keeps killing/probing owned groups through the unchanged
        absolute deadline. An unproven cleanup cannot cause an early exit.
        """
        cleanup_errors=[]
        try:
            if self.child is not None:self.recover_registration_race()
            else:self.recovery_proven=True;self.cleanup_complete=True
        except BaseException as cleanup_error:
            cleanup_errors.append(repr(cleanup_error))
        while not self.cleanup_complete and time.monotonic()<self.pool.until-.25:
            try:
                with self.ipc_lock:self.pump()
            except BaseException as cleanup_error:
                if len(cleanup_errors)<8:cleanup_errors.append(repr(cleanup_error))
            time.sleep(max(0,min(.02,self.pool.until-.25-time.monotonic())))
        result=dict(schema='long_d2_outer_acceptance_v2',accepted=False,
            experiment_status='failed' if self.cleanup_complete else 'failed_partial',expected_exit_code=1,
            error=self.pool.reason,trigger_error=repr(error),traceback=traceback.format_exc(),
            first_failure_monotonic=self.pool.first,cleanup_until_monotonic=self.pool.until,
            cleanup_complete=self.cleanup_complete,recovery_proven=self.recovery_proven,
            cleanup_errors=cleanup_errors,first_local_failure=self.pool.first_local,
            first_global_failure=self.pool.first_global,ownership=self.groups,
            inner_wait=None if self.child is None else self.child.report,
            worker_wait=self.worker_wait,forwarded_cancellation=self.forwarded,events=self.events,
            teacher_qualified=False,training_parent_eligible=False,limitations=LIMITATIONS)
        try:
            receipt_path.parent.mkdir(parents=False,exist_ok=True)
            c.mandatory_failure(receipt_path,result,self.pool.until)
        except BaseException as publication_error:
            result['mandatory_failure_publication_error']=repr(publication_error)
        # Optional IO and joins run only after positive absence. If survivors
        # remain, leave the watchdog active and spend no extra cleanup allowance.
        while not self.cleanup_complete:
            life.remaining(self.pool.until)
            try:
                with self.ipc_lock:self.pump()
            except BaseException:pass
            time.sleep(life.remaining(self.pool.until,.02))
        try:
            if self.guard is not None:
                self.guard.event.set()
                for thread in (self.guard.thread,self.guard.verify_thread):
                    if thread is not None:thread.join(timeout=life.remaining(self.pool.until,.5))
        except BaseException:pass
        try:
            c.optional_timing(self.guard,receipt_path.parent/'outer-verification.jsonl',self.pool.until) if self.guard is not None else None
        except BaseException:pass
        self.stop.set()
        try:self.watchdog.join(timeout=life.remaining(self.pool.until,.5))
        except BaseException:pass
        for channel in (self.super_channel,self.worker_channel):
            try:
                if channel is not None:channel.sock.close()
            except BaseException:pass
        return result
''' +s[a:]
s=s.replace('            self.publish_failed(receipt_path,error)','            try:self.publish_failed(receipt_path,error)\n            except BaseException:pass')
# Strict normal direct wait report predicate shared by producer/consumer.
a=s.index('\ndef accept_observed(')
s=s[:a]+'''
def validate_wait_reports(receipt, raw_exit, elapsed_seconds):
    groups=receipt['ownership']
    c.require(set(groups)=={'supervisor','worker'},'Ownership incomplete')
    t0=float.fromhex(receipt['t0_monotonic_hex'])
    c.require(math.isfinite(t0) and t0>=0,'Invalid T0')
    for role,key,seconds in (('supervisor','inner_wait',c.INNER_SECONDS),('worker','worker_wait',c.WORKER_SECONDS)):
        group=groups[role];report=receipt[key]
        pid=group['pid'];parent=group['parent_at_registration']
        c.require(type(pid) is int and pid>1 and type(parent) is int and parent>1
                  and group['pgid']==pid and group['new_session_verified'] is True
                  and group['group_absent'] is True,'Invalid owned group')
        c.require(type(report['pid']) is int and report['pid']==pid
                  and type(report['reaped_by']) is int and report['reaped_by']==parent
                  and report['direct_child_reaped'] is True,'Direct-parent reap missing')
        status=report['raw_wait_status'];rc=report['returncode'];at=report['observed_monotonic']
        c.require(type(status) is int and 0<=status<=65535 and os.WIFEXITED(status)
                  and type(rc) is int and rc==raw_exit and os.waitstatus_to_exitcode(status)==rc,
                  'Raw wait/outcome differs')
        c.require(type(at) in (int,float) and math.isfinite(at)
                  and t0<=at<t0+seconds and at<=t0+elapsed_seconds,'Direct reap time invalid')
    c.require(groups['worker']['parent_at_registration']==groups['supervisor']['pid']
              and groups['worker']['pid']!=groups['supervisor']['pid']
              and receipt['worker_wait']['observed_monotonic']<=receipt['inner_wait']['observed_monotonic'],
              'Owned parent/order differs')
    return True

''' +s[a:]
s=s.replace("        output=Path(registration['output'])","        validate_wait_reports(receipt,raw_exit,elapsed_seconds)\n        output=Path(registration['output'])")
s=s.replace('except (KeyError, TypeError, OSError, c.Stop):','except (KeyError, TypeError, ValueError, OverflowError, OSError, c.Stop):')
p.write_text(s)
