"""Stdlib process lifetime ownership. No ML imports and no production restoration.

Every timeout is an absolute deadline. The executor is the only group signal
owner. Direct signals after the finite pending scan may remain unobserved; the
parent must additionally observe executor raw exit and elapsed wall time.
"""
import array
import json
import math
import os
import signal
import socket
import stat
import threading
import time

OWNED = {signal.SIGINT, signal.SIGTERM, signal.SIGALRM}
ACTIVE = None
CHANNEL = None
POOL = None


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


class ProcessLatch:
    def __init__(self):
        self.phase = 'NORMAL'
        self.cancellation_requests = 0
        self.requested_signal = None
        self.alarm_seen = self.raised = False
        self.first_at = None
        self.first_cancel_at = self.first_alarm_at = None
        self.installed = False
        self.deadline = None

    def install(self, deadline):
        global ACTIVE
        if self.installed or ACTIVE is not None or threading.current_thread() is not threading.main_thread():
            raise Stop('One lifetime alarm owner required')
        if signal.getitimer(signal.ITIMER_REAL)[0] != 0:
            raise Stop('Existing process timer owner')
        ACTIVE = self
        self.installed, self.deadline = True, deadline
        for number in OWNED:
            signal.signal(number, self.handle)
        delay = deadline - time.monotonic()
        if delay <= 0 or not math.isfinite(delay):
            self.alarm_seen = True
            self.first_at = self.first_alarm_at = time.monotonic()
            self.phase = 'FAILURE'
            raise Stop('Expired before alarm installation', 'wall_guard')
        signal.setitimer(signal.ITIMER_REAL, delay)  # Only nonzero arm.

    def record(self, number):
        now = time.monotonic()
        self.first_at = now if self.first_at is None else self.first_at
        if number == signal.SIGALRM:
            self.first_alarm_at = now if self.first_alarm_at is None else self.first_alarm_at
            self.alarm_seen = True
        else:
            self.first_cancel_at = now if self.first_cancel_at is None else self.first_cancel_at
            self.cancellation_requests += 1
            self.requested_signal = self.requested_signal or number

    def handle(self, number, frame):
        self.record(number)
        if self.phase == 'NORMAL' and not self.raised:
            self.raised = True
            self.phase = 'FAILURE'
            raise Stop('Lifetime wall alarm' if number == signal.SIGALRM else 'Cancellation latched',
                       'wall_guard' if number == signal.SIGALRM else 'cancelled')

    def __call__(self):
        self.phase = 'DEFER' if self.phase != 'FAILURE' else 'FAILURE'

    def check(self):
        if self.first_cancel_at is not None and (self.first_alarm_at is None or self.first_cancel_at <= self.first_alarm_at):
            raise Stop('Cancellation latched', 'cancelled')
        if self.alarm_seen or time.monotonic() >= self.deadline:
            raise Stop('Lifetime wall deadline reached', 'wall_guard')

    def pending_once(self):
        pending = signal.sigpending() & OWNED
        for number in sorted(pending):
            signal.sigwait({number})
            self.record(number)


def start_thread(thread):
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, OWNED)
    try:
        thread.start()
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)


def final_exit(code, latch, deadline, failed=lambda: False):
    """Finite leaf. No caller finally, IO, unmask, restore or flush follows D."""
    signal.pthread_sigmask(signal.SIG_BLOCK, OWNED)
    signal.setitimer(signal.ITIMER_REAL, 0)
    latch.pending_once()
    bad = bool(latch.cancellation_requests or latch.alarm_seen or failed())
    bad |= time.monotonic() >= deadline
    os._exit(1 if bad else code)


def pair():
    return socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)


class Channel:
    def __init__(self, sock, t0=None):
        if not stat.S_ISSOCK(os.fstat(sock.fileno()).st_mode):
            raise Stop('Private inherited socket required')
        if sock.family != socket.AF_UNIX or sock.type & socket.SOCK_DGRAM != socket.SOCK_DGRAM:
            raise Stop('Private datagram endpoint required')
        self.sock, self.t0 = sock, t0
        self.lock = threading.RLock()
        self.sent = self.received = 0

    @classmethod
    def inherited(cls, fd):
        if fd is None or fd <= 2:
            raise Stop('Missing private inherited FD')
        return cls(socket.socket(fileno=fd))

    def send(self, value, deadline, fd=None):
        with self.lock:
            self.sock.settimeout(remaining(deadline, .2))
            self.sent += 1
            packet = dict(schema='long_d2_owned_ipc_v1', sender=os.getpid(), seq=self.sent, **value)
            raw = json.dumps(packet, sort_keys=True, allow_nan=False).encode()
            if len(raw) > 60000:
                raise Stop('Owned IPC packet too large')
            ancillary = [] if fd is None else [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [fd]))]
            if self.sock.sendmsg([raw], ancillary) != len(raw):
                raise Stop('Partial owned IPC write')
            remaining(deadline)

    def receive(self, deadline, sender=None):
        self.sock.settimeout(remaining(deadline, .2))
        raw, ancillary, flags, _ = self.sock.recvmsg(60001, socket.CMSG_SPACE(4))
        remaining(deadline)
        if not raw or len(raw) > 60000 or flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
            raise Stop('Truncated owned IPC packet')
        def unique(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise Stop('Duplicate owned IPC key')
                result[key] = value
            return result
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(Stop('Nonfinite owned IPC')))
        if value.get('schema') != 'long_d2_owned_ipc_v1' or value.get('seq') != self.received + 1:
            raise Stop('Owned IPC sequence/schema mismatch')
        if sender is not None and value.get('sender') != sender:
            raise Stop('Owned IPC sender mismatch')
        self.received += 1
        fds = array.array('i')
        for level, kind, data in ancillary:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                fds.frombytes(data[:len(data) - len(data) % fds.itemsize])
        if len(fds) > 1:
            for fd in fds:
                os.close(fd)
            raise Stop('Unexpected inherited endpoint inventory')
        return value, list(fds)


def notify_failure(error, at=None):
    """ACK before failure persistence. Never creates a second cleanup pool."""
    if POOL is None:
        raise Stop('Failure without owned cleanup pool')
    now = time.monotonic()
    descriptor = getattr(error, 'first_failure_descriptor', None)
    if at is None and descriptor is not None:
        at = descriptor.get('timestamp')  # already-observed failure keeps its own time
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
