def require(condition, message, outcome='identity_or_lease_failure'):
    if not condition:
        raise Stop(message, outcome)

def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())

def replace_json(path, value):
    pending = path.with_name('.' + path.name + '.pending')
    save(pending, value)
    os.replace(pending, path)

def outcome_fields(outcome, complete=False):
    passed = complete and outcome == 'D2_progress_gate_passed'
    return dict(experiment_status='complete' if complete else 'failed', outcome=outcome,
                progression_gate_passed=passed, teacher_qualified=False, training_parent_eligible=False,
                D3_parent_candidate_pending_separate_parent_audit=passed,
                B_E_student_D3_opened=False, automatic_retries=0, same_phase_resume=False,
                expected_exit_code=(0 if passed else 2) if complete else 1)

def result_code(result):
    good = result.get('experiment_status') == 'complete'
    if good and result.get('outcome') == 'D2_progress_gate_passed' and result.get('progression_gate_passed') is True:
        return 0
    if good and result.get('outcome') == 'budget_closed_below_gate' and result.get('progression_gate_passed') is False:
        return 2
    return 1

def failure_outcome(error):
    if isinstance(error, Stop):
        return error.outcome
    if isinstance(error, KeyboardInterrupt):
        return 'cancelled'
    return 'safety_stop'

def observed_failure(error, guard=None, role='unknown'):
    candidates = []
    now = time.monotonic()
    if guard is not None and guard.failure is not None and guard.failure_at is not None:
        candidates.append((guard.failure_at, guard.failure, 'safety_monitor', 'actual_guard_observation', None))
    latch = life.ACTIVE
    if latch is not None:
        if latch.first_cancel_at is not None:
            candidates.append((latch.first_cancel_at, Stop('Cancellation latched','cancelled'), 'cancel', 'signal_observed_sender_unknown', latch.requested_signal))
        if latch.first_alarm_at is not None:
            candidates.append((latch.first_alarm_at, Stop('Lifetime wall alarm','wall_guard'), 'alarm', 'signal_observed', int(signal.SIGALRM)))
        if latch.deadline is not None and now >= latch.deadline:
            candidates.append((latch.deadline, Stop('Absolute wall deadline','wall_guard'), 'deadline', 'absolute_registered_deadline', None))
    candidates.append((now, error, 'exception_observed', 'catch_observation_not_construction', None))
    at, primary, kind, basis, number = min(candidates, key=lambda item:item[0])
    descriptor = dict(timestamp=at, kind=kind, outcome=failure_outcome(primary), role=role, timing_basis=basis, signal=number)
    primary.first_failure_descriptor = descriptor
    return primary, descriptor

def optional_timing(guard, path, deadline, permission=lambda: None):
    """Best effort once; retained partial bytes are evidence, never authority."""
    global HASH_OBSERVER
    previous = HASH_OBSERVER
    try:
        if life.POOL is not None and life.POOL.until is not None:
            HASH_OBSERVER = lambda: life.remaining(life.POOL.until)
        if Path(path).exists():
            return dict(status='existing_partial_or_complete', path=str(path))
        value = guard.persist_timing(path, deadline, permission)
        return dict(status='complete', manifest=value)
    except BaseException as error:
        if life.POOL is None or life.POOL.until is None:
            if isinstance(error,Stop) and (guard.failure is not None or time.monotonic()>=deadline or life.ACTIVE is not None and (life.ACTIVE.cancellation_requests or life.ACTIVE.alarm_seen)):
                raise
        return dict(status='partial_or_unavailable', path=str(path), error=repr(error))
    finally:
        HASH_OBSERVER = previous

def provisional(result):
    return dict(authoritative=False, acceptance_authority='outer-executor-receipt',
                internal_decision=('complete_pending_outer_acceptance' if result_code(result) in (0,2) else 'failed'))

def supervise_owned(args, started, handoff, gate, *, context_provider=capsule_context,
                    command_factory=None, guard_factory=Guard):
    deadline=started+INNER_SECONDS
    process=child=guard=None
    stream=io.StringIO()
    result=outcome_fields('identity_or_lease_failure')
    try:
        p,config,base,identity,pins,lease=context_provider(ROOT,verify_inputs=False)
        require(handoff['identity_sha256']==lease['identity_sha256']
                and handoff['capsule_manifest_sha256']==lease['capsule_manifest_sha256'], 'Supervisor identity handoff differs')
        require(args.output.resolve()==ORIGINAL_ROOT/p['output']
                and args.state_path.resolve()==STATE_PATH, 'Noncanonical output/lease')
        assert_lease(args.state_path,lease)
        args.output.mkdir(parents=False,exist_ok=False)
        def lease_check():
            assert_lease(args.state_path,lease)
        def verify():
            return integrity.verify((p,config,base,identity,pins,lease), ROOT)
        guard=guard_factory(deadline,lease_check,verify,stream)
        guard.start()
        def authority(force=False):
            life.ACTIVE.check()
            guard.check()
            lease_check()
            if force:
                guard.full_check(True)
            guard.sample(full=False)
            life.ACTIVE.check()
            lease_check()
            require(time.monotonic()-guard.last_sample<=.5, 'Final resource observation age exceeded','resource_stop')
        command=([sys.executable,'-B',str(Path(__file__).resolve()),'worker',
                  '--output',str(args.output),'--state-path',str(args.state_path),
                  '--started',str(started),'--supervisor-pid',str(os.getpid()),
                  '--executor-fd',str(gate.fileno()),'--executor-pid',str(args.executor_pid)]
                 if command_factory is None else command_factory(args,started,gate.fileno()))
        result.update(run_id=p['run_id'],protocol_sha256=PROTOCOL_SHA256,required_lease=lease,
                      command=command,supervisor_started_monotonic=started,
                      absolute_deadline_monotonic=deadline,worker_deadline_monotonic=started+WORKER_SECONDS)
        with (args.output/'worker.stdout.log').open('x') as stdout, (args.output/'worker.stderr.log').open('x') as stderr:
            mask=signal.pthread_sigmask(signal.SIG_BLOCK,life.OWNED)
            try:
                require(not os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK'), 'MPS fallback forbidden')
                process=subprocess.Popen(command,stdout=stdout,stderr=stderr,cwd=ROOT,
                    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),start_new_session=True,pass_fds=(gate.fileno(),))
                child=owned.Child(process)
                life.CHANNEL.send(dict(kind='register_worker',worker_pid=process.pid,worker_pgid=process.pid,
                    command=command,t0_monotonic_hex=started.hex()),deadline)
                ack,fds=life.CHANNEL.receive(deadline,args.executor_pid)
                require(not fds and ack.get('kind')=='registered' and ack.get('worker_pid')==process.pid,
                        'Worker registration ACK missing')
                gate.close()
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK,mask)
            guard.rss=lambda:owned.group_rss([os.getpgrp(),process.pid],life.POOL.deadline(deadline))
            while child.poll() is None:
                authority(False)
                require(time.monotonic()<started+WORKER_SECONDS, 'Worker raw exit cutoff reached','wall_guard')
                time.sleep(life.remaining(started+WORKER_SECONDS,.02))
            report=child.report
            life.CHANNEL.send(dict(kind='worker_wait',report=report,t0_monotonic_hex=started.hex()),deadline)
            require(report['observed_monotonic']<started+WORKER_SECONDS, 'Worker exit late','wall_guard')
            require(owned.absent(process.pid,deadline), 'Worker descendant/group still live','publication_failure')
            wr=read_json(args.output/'long-worker-result.json')
            code=result_code(wr)
            require(report['returncode']==code and code in (0,2), 'Worker raw/outcome failure','publication_failure')
            require(wr['expected_exit_code']==code and wr['teacher_qualified'] is False
                    and wr['training_parent_eligible'] is False, 'Worker outcome/qualification invalid')
            result.update(outcome_fields(wr['outcome'],True),worker_result=wr,worker_exit_code=code,
                          worker_wait_report=report,owned_process_stop=dict(reaped=True,group_empty=True,
                            owned_pid=process.pid,owned_pgid=process.pid,termination_owner='executor',errors=[]))
        authority(True)
        with guard.lock:
            snapshot=stream.getvalue()
            guard.stream=None
        with (args.output/'supervisor-guard.jsonl').open('x') as snapshot_file:
            snapshot_file.write(snapshot)
        authority(True)
        result['supervisor_observation_log_scope']='closed prepublication snapshot; later monitor memory-only'
        code=publish_terminal(args.output,result,started,deadline,True,authority=authority)
        authority(True)
        life.ACTIVE()
        guard.close()
        guard.stream=None
        stream.close()
        authority(False)
        terminal=read_json(args.output/'finalization-result.json')
        terminal.update(supervisor_resources_final=guard.receipt(),owned_guard_handles_absent=True,
                        owned_writers_absent=True,final_authority_check_after_monitor_and_stream_close=True,
                        inherited_consumed_wall_scope='D1 historical context only; long budget uses executor T0')
        replace_json(args.output/'finalization-result.json',terminal)
        authority(False)
        life.CHANNEL.send(dict(kind='inner_ready',t0_monotonic_hex=started.hex(),expected_exit_code=code,
                               owned_guard_handles_absent=True,owned_writers_absent=True),deadline)
        def final_hash_observer():
            guard.check()
            if time.monotonic()-guard.last_sample>=.15:guard.sample(full=False)
        global HASH_OBSERVER
        HASH_OBSERVER=final_hash_observer
        authority(True)
        optional_timing(guard,ORIGINAL_ROOT/Path(p['terminal_lifecycle']['acceptance_receipt']).parent/'inner-verification.jsonl',
                             deadline,lambda: authority(False))
        return code,guard
    except BaseException as error:
        # No ordinary verification or artifact hash after first failure.
        try:
            error, descriptor=observed_failure(error,guard,'inner')
            at=descriptor['timestamp']
            until=life.notify_failure(error,at)
        except BaseException as notify_error:
            until=life.POOL.fail(error)
            result['failure_ack_unavailable']=repr(notify_error)
        life.ACTIVE.phase='FAILURE'
        result.update(outcome_fields(failure_outcome(error)),**provisional(outcome_fields('failed')),
                      error=repr(error),first_failure_monotonic=life.POOL.first,
                      cleanup_until_monotonic=until,first_local_failure=life.POOL.first_local,first_global_failure=life.POOL.first_global)
        try:
            life.remaining(until)
            if guard is not None:
                guard.event.set()
                for thread in (guard.thread,guard.verify_thread):
                    if thread is not None:
                        thread.join(timeout=life.remaining(until,.5))
                result['owned_guard_handles_absent']=all(t is None or not t.is_alive() for t in (guard.thread,guard.verify_thread))
                guard.stream=None
            stream.close()
            gate.close()
            life.remaining(until)
            if args.output.is_dir():
                optional_timing(guard,ORIGINAL_ROOT/Path(p['terminal_lifecycle']['acceptance_receipt']).parent/'inner-verification.jsonl',until)
                replace_json(args.output/'inner-failure.json',result)
            life.remaining(until)
            life.CHANNEL.sock.close()
        except BaseException:
            pass  # Partial failure evidence is not acceptance.
        return 1,guard
