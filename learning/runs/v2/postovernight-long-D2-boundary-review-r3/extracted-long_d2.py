def outcome_fields(outcome, complete=False):
    passed = complete and outcome == 'D2_progress_gate_passed'
    return dict(experiment_status='complete' if complete else 'failed', outcome=outcome,
                progression_gate_passed=passed, teacher_qualified=False, training_parent_eligible=False,
                D3_parent_candidate_pending_separate_parent_audit=passed,
                B_E_student_D3_opened=False, automatic_retries=0, same_phase_resume=False,
                expected_exit_code=(0 if passed else 2) if complete else 1)

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

def primary_error(error, guard):
    return observed_failure(error, guard, 'worker')[0]

def record_primary_failure(result, error):
    descriptor = getattr(error, 'first_failure_descriptor', None)
    if descriptor is None:
        error, descriptor = observed_failure(error)
    if 'first_local_failure' not in result:
        result['first_local_failure'] = descriptor
    current = result.get('first_global_failure')
    if current is None or descriptor['timestamp'] < current['timestamp']:
        result['first_global_failure'] = descriptor
        primary = dict(outcome=failure_outcome(error), error=repr(error), descriptor=descriptor)
        result.update(outcome_fields(primary['outcome']), error=primary['error'], primary_failure=primary)
    else:
        result.setdefault('secondary_failures', []).append(descriptor)

def worker_failure(error, args, guard, learner, result, permission):
    """Memory-first failure latch; a failed ACK permanently forbids new writes."""
    error = primary_error(error, guard)
    record_primary_failure(result, error)
    permission['failed'] = True
    permission['acknowledged_until'] = None
    now = time.monotonic()
    candidates = [now]
    if guard is not None and guard.failure_at is not None:
        candidates.append(guard.failure_at)
    if life.ACTIVE is not None:
        if life.ACTIVE.first_at is not None:
            candidates.append(life.ACTIVE.first_at)
        if now >= life.ACTIVE.deadline:
            candidates.append(life.ACTIVE.deadline)
        life.ACTIVE.phase = 'FAILURE'
    local_until = life.POOL.fail(error, min(candidates))
    if learner is not None:
        learner.api.absolute_deadline = local_until
    if permission.get('ack_failed'):
        return False  # No recursive ACK retry or new cleanup allowance.
    try:
        require(life.CHANNEL is not None, 'Worker failure requires executor ACK')
        deadline = life.notify_failure(error, life.POOL.first)
        require(type(deadline) in (float, int) and math.isfinite(deadline)
                and deadline == life.POOL.until and deadline <= local_until,
                'Worker failure ACK deadline differs')
        life.remaining(deadline)
        if learner is not None:
            learner.api.absolute_deadline = deadline
        permission['acknowledged_until'] = deadline
        result['first_global_failure'] = life.POOL.first_global
        if life.POOL.first_global is not None:
            result.update(outcome_fields(life.POOL.first_global['outcome']))
        return True
    except BaseException as ack_error:
        permission['ack_failed'] = True
        if learner is not None:
            learner.api.absolute_deadline = life.POOL.until
        result['failure_ack_unavailable'] = repr(ack_error)
        return False
