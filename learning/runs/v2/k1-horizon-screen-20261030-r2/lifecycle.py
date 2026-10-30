"""Direct-child non-reaping observation on the verified Darwin arm64 ABI."""
import ctypes
import os
import signal
import subprocess
import sys
import time

import common as c


class DarwinSigval(ctypes.Union):
    _fields_ = [('sival_int', ctypes.c_int), ('sival_ptr', ctypes.c_void_p)]


class DarwinSiginfo(ctypes.Structure):
    _fields_ = [('si_signo', ctypes.c_int), ('si_errno', ctypes.c_int), ('si_code', ctypes.c_int),
                ('si_pid', ctypes.c_int), ('si_uid', ctypes.c_uint32), ('si_status', ctypes.c_int),
                ('si_addr', ctypes.c_void_p), ('si_value', DarwinSigval),
                ('si_band', ctypes.c_long), ('__pad', ctypes.c_ulong * 7)]


def waitid_function():
    c.need(sys.platform == 'darwin' and os.uname().machine == 'arm64' and sys.byteorder == 'little', 'Verified Darwin arm64 required')
    c.need(ctypes.sizeof(DarwinSiginfo) == 104 and ctypes.alignment(DarwinSiginfo) == 8
           and [getattr(DarwinSiginfo, n).offset for n, _ in DarwinSiginfo._fields_] == [0,4,8,12,16,20,24,32,40,48], 'siginfo ABI differs')
    c.need([getattr(os, n, None) for n in ['P_PID','WEXITED','WNOHANG','WNOWAIT']] == [1,4,1,32]
           and signal.SIGCHLD == 20, 'waitid constants differ')
    fn = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True).waitid
    fn.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.POINTER(DarwinSiginfo), ctypes.c_int]
    fn.restype = ctypes.c_int
    return fn


def observe(process, fn):
    info = DarwinSiginfo()
    ctypes.set_errno(0)
    result = fn(os.P_PID, process.pid, ctypes.byref(info), os.WEXITED | os.WNOHANG | os.WNOWAIT)
    if result == -1:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))
    c.need(result == 0, 'waitid return differs')
    if info.si_pid == 0:
        c.need(bytes(info) == bytes(ctypes.sizeof(info)), 'Empty waitid status invalid')
        return None
    c.need(info.si_pid == process.pid and info.si_signo == signal.SIGCHLD and info.si_errno == 0, 'Waitable child identity differs')
    if info.si_code == 1:
        c.need(0 <= info.si_status <= 255, 'Exit status invalid')
        return info.si_status
    c.need(info.si_code in (2,3) and 0 < info.si_status < signal.NSIG, 'Child event invalid')
    return -info.si_status


def group_members(pgid):
    text = subprocess.run(['/bin/ps', '-axo', 'pid=,pgid=,rss='], check=True, text=True,
                          capture_output=True, timeout=3).stdout
    rows = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 3 and int(fields[1]) == pgid:
            rows.append(dict(pid=int(fields[0]), rss_bytes=int(fields[2]) * 1024))
    return rows


def run_child(argv, out, environment, monitor, timeout, cleanup_seconds=10):
    """Never poll/reap before any needed process-group termination."""
    fn = waitid_function()
    started = time.monotonic()
    log = (out / 'worker.log').open('x')
    process = subprocess.Popen(argv, env=environment, stdout=log, stderr=subprocess.STDOUT,
                               start_new_session=True)
    reason = None
    observed = None
    peak = 0
    signals = []
    try:
        c.save(out / 'launch.json', dict(worker_expected_job=out.name, pid=process.pid, pgid=process.pid,
               argv=argv, started_monotonic=started))
        while observed is None:
            members = group_members(process.pid)
            peak = max(peak, sum(x['rss_bytes'] for x in members))
            monitor(members)
            c.need(time.monotonic() - started < timeout, 'Child total deadline')
            observed = observe(process, fn)
            if observed is None:
                time.sleep(.5)
        c.need(observed == 0, 'Worker nonzero exit: ' + str(observed))
        c.need(not [x for x in group_members(process.pid) if x['pid'] != process.pid], 'Descendants remain before reap')
    except BaseException as error:
        reason = repr(error)
        # The root has not been reaped: its PID pins this process group.
        for sig, allowance in [(signal.SIGTERM, cleanup_seconds / 2), (signal.SIGKILL, cleanup_seconds / 2)]:
            observed = observe(process, fn)
            others = [x for x in group_members(process.pid) if x['pid'] != process.pid]
            if observed is not None and not others:
                break
            try:
                os.killpg(process.pid, sig); signals.append(int(sig))
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + allowance
            while time.monotonic() < deadline:
                observed = observe(process, fn)
                others = [x for x in group_members(process.pid) if x['pid'] != process.pid]
                if observed is not None and not others:
                    break
                time.sleep(.1)
            if observed is not None and not others:
                break
    finally:
        try:
            code = process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            code = None
            reason = reason or 'Unable to reap after bounded cleanup'
        log.close()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            absent = True
        else:
            absent = False
        c.save(out / 'exit.json', dict(pid=process.pid, pgid=process.pid, raw_exit_code=code,
               observed_exit_code=observed, directly_reaped=True, group_absent=absent,
               reason=reason, cleanup_signals=signals, peak_group_RSS_bytes=peak,
               elapsed_seconds=time.monotonic() - started))
    c.need(reason is None and code == observed == 0 and absent, 'Child failure preserved: ' + str(reason))
    return c.read(out / 'exit.json')
