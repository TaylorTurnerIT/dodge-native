class Stop(RuntimeError):
    def __init__(self, message, outcome='identity_or_lease_failure'):
        self.outcome = outcome
        super().__init__(message)

def remaining(deadline, maximum=None):
    value = deadline - time.monotonic()
    if not math.isfinite(value) or value <= 0:
        raise Stop('Absolute deadline expired', 'wall_guard')
    return value if maximum is None else min(value, maximum)

class FailurePool:
    def __init__(self, t0, outer_seconds=7200, cleanup_seconds=10):
        self.t0, self.cap = t0, t0 + outer_seconds + cleanup_seconds
        self.allowance = cleanup_seconds
        self.first = self.until = None
        self.reason = None
        self.first_local = self.first_global = None
        self.lock = threading.RLock()

    def fail(self, reason, at=None, descriptor=None, *, peer=False):
        now = time.monotonic()
        if descriptor is None:
            descriptor = getattr(reason, 'first_failure_descriptor', None)
        if at is None:
            at = now if descriptor is None else descriptor.get('timestamp')
        if type(at) not in (float, int) or not math.isfinite(at) or not self.t0 <= at <= now:
            raise Stop('Invalid owned failure timestamp')
        if descriptor is None:
            descriptor = dict(timestamp=at, kind='failure_observed', outcome=getattr(reason,'outcome','identity_or_lease_failure'),
                              role='unknown', timing_basis='explicit_source_or_catch_observation', signal=None)
        if descriptor.get('timestamp') != at:
            raise Stop('Failure descriptor timestamp differs')
        with self.lock:
            if not peer and self.first_local is None:
                self.first_local = dict(descriptor)
            if self.first_global is None or at < self.first_global['timestamp']:
                self.first_global = dict(descriptor)
                self.reason = str(reason)
            self.first = min(now, at, self.first if self.first is not None else now)
            candidate = min(self.first + self.allowance, self.cap)
            self.until = min(candidate, self.until if self.until is not None else candidate)
            return self.until

    def deadline(self, normal):
        return normal if self.until is None else self.until

def notify_failure(error, at=None):
    """ACK before failure persistence. Never creates a second cleanup pool."""
    if POOL is None:
        raise Stop('Failure without owned cleanup pool')
    now = time.monotonic()
    candidates = [now] if at is None else [now, at]
    if ACTIVE is not None:
        if ACTIVE.first_at is not None:candidates.append(ACTIVE.first_at)
        if now >= ACTIVE.deadline:candidates.append(ACTIVE.deadline)
    until = POOL.fail(error, min(candidates))
    if ACTIVE is not None:
        ACTIVE.phase = 'FAILURE'
    if CHANNEL is not None:
        CHANNEL.send(dict(kind='failure', first_monotonic_hex=POOL.first.hex(),
                          t0_monotonic_hex=POOL.t0.hex(), reason=str(error), descriptor=POOL.first_global), until)
        value, fds = CHANNEL.receive(until)
        if fds or value.get('kind') != 'failure_ack' or value.get('t0_monotonic_hex') != POOL.t0.hex():
            raise Stop('Missing owned failure acknowledgment')
        first = float.fromhex(value['first_monotonic_hex'])
        POOL.fail(error, first, value.get('descriptor'), peer=True)
        if value.get('cleanup_until_monotonic_hex') != POOL.until.hex():
            raise Stop('Shared cleanup deadline differs')
    return POOL.until
