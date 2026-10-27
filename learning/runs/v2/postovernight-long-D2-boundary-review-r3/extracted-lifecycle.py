class Stop(RuntimeError):
    def __init__(self, message, outcome='identity_or_lease_failure'):
        self.outcome = outcome
        super().__init__(message)

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
