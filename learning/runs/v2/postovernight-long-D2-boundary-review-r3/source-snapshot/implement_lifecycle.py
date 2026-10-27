from pathlib import Path
p=Path(__file__).with_name('lifecycle.py');s=p.read_text()
s=s.replace('        self.reason = None','        self.reason = None\n        self.first_local = self.first_global = None')
s=s.replace('    def fail(self, reason, at=None):','    def fail(self, reason, at=None, descriptor=None, *, peer=False):')
s=s.replace('        with self.lock:\n            self.first = min', '''        if descriptor is None:
            descriptor = getattr(reason, 'first_failure_descriptor', None)
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
            self.first = min''')
s=s.replace('            self.reason = self.reason or str(reason)\n','')
s=s.replace('        self.first_at = None','        self.first_at = None\n        self.first_cancel_at = self.first_alarm_at = None')
s=s.replace("            self.first_at = time.monotonic()", "            self.first_at = self.first_alarm_at = time.monotonic()")
s=s.replace('        self.first_at = self.first_at or time.monotonic()\n        if number == signal.SIGALRM:\n            self.alarm_seen = True\n        else:', '''        now = time.monotonic()
        self.first_at = now if self.first_at is None else self.first_at
        if number == signal.SIGALRM:
            self.first_alarm_at = now if self.first_alarm_at is None else self.first_alarm_at
            self.alarm_seen = True
        else:
            self.first_cancel_at = now if self.first_cancel_at is None else self.first_cancel_at''')
# check chooses earliest signal, not arbitrary cancel precedence.
a=s.index('    def check(self):');b=s.index('    def pending_once',a)
s=s[:a]+'''    def check(self):
        if self.first_cancel_at is not None and (self.first_alarm_at is None or self.first_cancel_at <= self.first_alarm_at):
            raise Stop('Cancellation latched', 'cancelled')
        if self.alarm_seen or time.monotonic() >= self.deadline:
            raise Stop('Lifetime wall deadline reached', 'wall_guard')

'''+s[b:]
s=s.replace("                          t0_monotonic_hex=POOL.t0.hex(), reason=str(error)), until)","                          t0_monotonic_hex=POOL.t0.hex(), reason=str(error), descriptor=POOL.first_global), until)")
s=s.replace('        POOL.fail(error, first)',"        POOL.fail(error, first, value.get('descriptor'), peer=True)")
p.write_text(s)
