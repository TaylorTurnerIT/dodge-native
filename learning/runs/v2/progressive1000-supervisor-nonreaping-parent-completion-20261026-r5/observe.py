"""Direct-owner one-shot watchdog, adapted from the retained300 parent observer.

Parent installs marker/lease/approval before invoking this observer. No launch
approval, worker output, lease, checkpoint or source is created or changed here.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
import traceback
import binding as b
from execute_once import group_exists, stop_owned
import terminal

class DarwinSigval(ctypes.Union):
    _fields_ = [('sival_int', ctypes.c_int), ('sival_ptr', ctypes.c_void_p)]


class DarwinSiginfo(ctypes.Structure):
    # macOS 27.0 SDK sys/signal.h: siginfo_t, arm64 LP64. No Linux layout.
    _fields_ = [('si_signo', ctypes.c_int), ('si_errno', ctypes.c_int),
                ('si_code', ctypes.c_int), ('si_pid', ctypes.c_int32),
                ('si_uid', ctypes.c_uint32), ('si_status', ctypes.c_int),
                ('si_addr', ctypes.c_void_p), ('si_value', DarwinSigval),
                ('si_band', ctypes.c_long), ('__pad', ctypes.c_ulong * 7)]


def nonreaping_waitid():
    """Fail closed before Popen unless the narrowly verified Darwin ABI exists."""
    b.need(sys.platform == 'darwin' and os.uname().machine == 'arm64'
           and sys.byteorder == 'little', 'non-reaping waitid requires verified Darwin arm64 ABI')
    b.need([ctypes.sizeof(t) for t in (ctypes.c_int, ctypes.c_uint32,
           ctypes.c_void_p, ctypes.c_long)] == [4, 4, 8, 8]
           and ctypes.sizeof(DarwinSiginfo) == 104 and ctypes.alignment(DarwinSiginfo) == 8
           and [getattr(DarwinSiginfo, n).offset for n, _ in DarwinSiginfo._fields_]
               == [0, 4, 8, 12, 16, 20, 24, 32, 40, 48], 'Darwin siginfo_t ABI differs')
    b.need([getattr(os, n, None) for n in ('P_PID', 'WEXITED', 'WNOHANG', 'WNOWAIT')]
           == [1, 4, 1, 32] and signal.SIGCHLD == 20, 'Darwin waitid constants differ')
    waitid = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True).waitid
    # sys/wait.h: int waitid(idtype_t [enum], id_t [uint32], siginfo_t *, int).
    waitid.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.POINTER(DarwinSiginfo), ctypes.c_int]
    waitid.restype = ctypes.c_int
    return waitid


def observe_exit(process, waitid):
    """Observe only this child, leaving its PID/group pinned until explicit wait."""
    if process.returncode is not None:
        return process.returncode
    b.need(type(process.pid) is int and 1 < process.pid <= 0x7fffffff,
           'invalid direct child PID for waitid')
    info = DarwinSiginfo()  # Zero before every WNOHANG call; never reuse status.
    ctypes.set_errno(0)
    result = waitid(os.P_PID, process.pid, ctypes.byref(info), os.WEXITED | os.WNOHANG | os.WNOWAIT)
    if result == -1:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))
    b.need(result == 0, 'unexpected waitid return')
    if info.si_pid == 0:
        b.need(bytes(info) == bytes(ctypes.sizeof(info)), 'invalid empty waitid status')
        return None
    # Darwin leaves si_uid zero here; it is not an ownership check. P_PID and
    # the kernel's waitable-child relation supply the identity, not a UID guess.
    b.need(info.si_pid == process.pid and info.si_signo == signal.SIGCHLD
           and info.si_errno == 0, 'waitid child identity differs')
    if info.si_code == 1:  # CLD_EXITED, sys/signal.h
        b.need(0 <= info.si_status <= 255, 'invalid waitid exit status')
        return info.si_status
    b.need(info.si_code in (2, 3) and 0 < info.si_status < signal.NSIG,
           'unexpected waitid child event')  # CLD_KILLED / CLD_DUMPED
    return -info.si_status


def process_rows():
    result = subprocess.run(['/bin/ps', '-axo', 'pid=,ppid=,pgid=,rss=,lstart=,command='],
                           capture_output=True, text=True, check=True, timeout=1)
    rows = {}
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 9)
        if len(parts) >= 9:
            try:
                pid, ppid, pgid, rss = map(int, parts[:4])
                rows[pid] = {'pid': pid, 'ppid': ppid, 'pgid': pgid,
                             'rss_bytes': rss * 1024,
                             'start_identity': ' '.join(parts[4:9]),
                             'command': parts[9] if len(parts) > 9 else ''}
            except ValueError:
                pass
    return rows


def descendants(rows, root_pid):
    found = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, row in rows.items():
            if row['ppid'] in found and pid not in found:
                found.add(pid)
                changed = True
    return [rows[p] for p in found if p in rows]


def exact_signal(rows, pid, prior, expected_pgid, sig, record):
    current = process_rows().get(pid)
    if (pid <= 1 or prior is None or current is None
            or current['start_identity'] != prior['start_identity']
            or current['command'] != prior['command']
            or current['pgid'] != expected_pgid):
        record['cleanup_signals'].append({'target_pid': pid, 'signal': signal.Signals(sig).name,
                                          'sent': False, 'reason': 'identity_or_group_not_proven'})
        return False
    os.kill(pid, sig)
    record['cleanup_signals'].append({'target_pid': pid, 'signal': signal.Signals(sig).name,
                                      'sent': True, 'start_identity': current['start_identity'],
                                      'pgid': current['pgid'], 'monotonic': time.monotonic()})
    return True


def signal_group(pgid, anchors, sig, record):
    """Signal only a fresh matching member of an observed owned session group."""
    b.need(type(pgid) is int and pgid > 1 and pgid != os.getpgrp(), 'unsafe observer group')
    current = process_rows()
    members = [row for row in current.values() if row['pgid'] == pgid]
    proven = any(row['pid'] in anchors and row['start_identity'] == anchors[row['pid']]['start_identity']
                 and row['command'] == anchors[row['pid']]['command'] for row in members)
    if members and not proven:
        raise RuntimeError('owned group identity no longer proven; no broad cleanup')
    if not members:
        return
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        return
    record['cleanup_signals'].append(dict(owned_pgid=pgid,signal=signal.Signals(sig).name,
                                           monotonic=time.monotonic(),members=members))


def signal_owned(process, anchors, sig, record):
    """An unreaped direct child pins its PID/group from Popen birth.

    Do not poll here: reaping would discard that kernel ownership proof. Once
    reaped, use the original fresh start/command/group anchor checks instead.
    No launcher-descendant snapshot or launch receipt is an ownership handoff.
    """
    b.need(type(process.pid) is int and process.pid > 1 and process.pid != os.getpgrp(),
           'unsafe direct child group')
    if process.returncode is None:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        record['cleanup_signals'].append(dict(owned_pgid=process.pid,
            signal=signal.Signals(sig).name,monotonic=time.monotonic(),
            ownership='unreaped directly owned Popen with start_new_session=True'))
    else:
        signal_group(process.pid, anchors, sig, record)


def main(envelope_path, envelope_sha, *, popen=None, clock=None, sleep=None):
    use_timer = clock is None
    popen = subprocess.Popen if popen is None else popen
    clock = time.monotonic if clock is None else clock
    sleep = time.sleep if sleep is None else sleep
    envelope, reg = b.load_envelope(envelope_path,envelope_sha)
    control = Path(envelope['control']); out = Path(reg['output'])
    # A failed dispatch is spent. Neither marker is inside the worker output.
    control.mkdir(parents=True,exist_ok=False)
    b.save(control/'dispatch.claimed',dict(envelope_sha256=envelope_sha,observer_pid=os.getpid()))
    b.save(control/'supervisor.claimed',dict(envelope_sha256=envelope_sha,pid=os.getpid()))
    record = dict(status='failed',launch_count=0,actual_worker_launch_count=0,
                  cleanup_signals=[],first_event=None,
                  registration_sha256=envelope['registration_sha256'],envelope_sha256=envelope_sha,
                  training_eligible=False,promoted=False,parent_terminal_audit_required=True,
                  worker_ownership_state='not_launched',lease_clearing_owner='parent')
    proc = None; anchors = {}; cleanup = None
    previous = {n:signal.getsignal(n) for n in (signal.SIGINT,signal.SIGTERM)}
    publication = False
    def latch(kind, **values):
        if record['first_event'] is None:
            record['first_event'] = dict(kind=kind,monotonic=clock(),**values)
    def handle(number,_frame):
        latch('observer_cancelled',signal=number)
        if publication:
            raise b.Cancelled('observer cancellation during terminal publication')
    for n in previous: signal.signal(n,handle)
    started = envelope['started']; term_at = started+b.LIMITS['work_seconds']; hard_at = started+b.LIMITS['total_seconds']
    peak_aggregate = 0; term_sent = None; kill_sent = False
    launching = False
    deadline_consumed = False
    def exhausted():
        nonlocal deadline_consumed
        if clock() >= hard_at:
            deadline_consumed = True
            latch('external_total_deadline')
        return deadline_consumed
    def require_budget():
        if exhausted():
            raise b.Cancelled('absolute supervisor deadline consumed')
    old_alarm = signal.getsignal(signal.SIGALRM)
    old_timer = signal.getitimer(signal.ITIMER_REAL)
    timer_started = time.monotonic()
    def deadline_alarm(_number,_frame):
        nonlocal deadline_consumed
        total = clock() >= hard_at
        if total: deadline_consumed = True
        latch('external_total_deadline' if total else 'external_work_deadline')
        if not total:
            signal.setitimer(signal.ITIMER_REAL,max(.001,hard_at-clock()))
        # Preserve the Popen assignment across a pending deadline signal.
        if not launching:
            raise b.Cancelled('absolute supervisor deadline')
    if use_timer:
        signal.signal(signal.SIGALRM,deadline_alarm)
        signal.setitimer(signal.ITIMER_REAL,max(.001,term_at-clock()))
    try:
        b.verify_bound(envelope,reg,preflight=True)
        b.need(0 <= clock()-started < b.LIMITS['work_seconds'] and record['first_event'] is None,
               'dispatch cancelled or expired')
        waitid = nonreaping_waitid()
        command = b.worker_command(envelope,reg)
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=reg['import_policy']['pycache_prefix'],PYTHONPATH=reg['runtime_root'])
        with (control/'worker.log').open('x') as log, (control/'observer-resources.jsonl').open('x') as samples:
            # The controller receives the worker Popen directly. Signal handlers
            # only latch during launch, so no async exception loses this handle.
            launching = True
            try:
                proc = popen(command,cwd=b.ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            finally:
                launching = False
            record.update(launch_count=1,actual_worker_launch_count=1,worker_pid=proc.pid,
                          owned_pgid=proc.pid,command=command,start_new_session=True,
                          worker_ownership_state='direct_child')
            require_budget()
            b.save(control/'worker-launch.json',dict(worker_pid=proc.pid,owned_pgid=proc.pid,
                launcher_pid=os.getpid(),command=command,start_new_session=True,
                observed_monotonic=clock(),registration_sha256=envelope['registration_sha256']))
            while True:
                now = clock(); current = process_rows()
                # Exit observation never reaps: retain the kernel pin through
                # any surviving original group and required TERM/KILL escalation.
                # Membership derives from the already-owned session, not ancestry.
                members = [row for row in current.values() if row['pgid'] == proc.pid]
                proven = proc.returncode is None or any(
                    row['pid'] in anchors and row['start_identity'] == anchors[row['pid']]['start_identity']
                    and row['command'] == anchors[row['pid']]['command'] for row in members)
                if proven:
                    for row in members: anchors[row['pid']] = row
                code = observe_exit(proc, waitid)
                if code is not None: current = process_rows()
                owned = descendants(current,proc.pid)
                # An exited unreaped leader is still in ps; it cannot fork.
                # Only other original group members require cleanup before wait.
                group_rows = [r for r in current.values() if r['pgid'] == proc.pid
                              and not (code is not None and r['pid'] == proc.pid)]
                own_row = current.get(os.getpid())
                all_owned = {row['pid']:row for row in owned+group_rows}
                aggregate = sum(r['rss_bytes'] for r in all_owned.values())+(own_row['rss_bytes'] if own_row else 0)
                peak_aggregate = max(aggregate,peak_aggregate)
                resources = b.worker_resources(out)
                sample = dict(monotonic=now,elapsed_seconds=now-started,owned_processes=group_rows,
                              observer_process=own_row,aggregate_rss_bytes=aggregate,worker_resources=resources)
                samples.write(json.dumps(sample,sort_keys=True)+'\n'); samples.flush()
                if aggregate > b.LIMITS['rss_bytes']: latch('aggregate_rss_limit',bytes=aggregate)
                if resources['samples'] and resources['peak_mps_driver_bytes'] > b.LIMITS['mps_bytes']: latch('sampled_mps_limit',bytes=resources['peak_mps_driver_bytes'])
                if resources['samples'] and resources['peak_rss_bytes'] > b.LIMITS['rss_bytes']: latch('sampled_worker_rss_limit',bytes=resources['peak_rss_bytes'])
                if os.path.lexists(envelope['cancel_path']): latch('cancel_marker')
                try: b.check_lease(reg)
                except BaseException as error: latch('lease_changed',error=repr(error))
                if code is not None and group_rows: latch('owned_group_survived_worker')
                if now >= term_at: latch('external_work_deadline')
                if record['first_event'] is not None and term_sent is None:
                    signal_owned(proc,anchors,signal.SIGTERM,record)
                    term_sent = clock()
                if ((term_sent is not None and now-term_sent >= 5) or now >= hard_at-.25) and not kill_sent:
                    signal_owned(proc,anchors,signal.SIGKILL,record); kill_sent = True
                if code is not None and not group_rows:
                    record.update(observed_worker_raw_exit=proc.wait(timeout=0),directly_reaped=True,
                                  direct_wait_observed_monotonic=clock())
                    b.need(record['observed_worker_raw_exit'] == code, 'waitid/reap exit differs')
                    break
                cleanup_at = hard_at if term_sent is None else min(hard_at,term_sent+b.LIMITS['cleanup_seconds'])
                if now >= cleanup_at:
                    latch('external_total_deadline' if now >= hard_at else 'cleanup_deadline')
                    # Leave the pin for exceptional stop_owned; it delivers KILL
                    # before its first wait, even at an exhausted deadline.
                    record['observed_worker_raw_exit'] = None
                    break
                sleep(min(.1,max(.001,hard_at-now)))
        if use_timer: signal.setitimer(signal.ITIMER_REAL,max(.001,hard_at-clock()))
        record['max_aggregate_rss_bytes'] = peak_aggregate
        b.need(record['first_event'] is None and record['observed_worker_raw_exit'] == 0,
               'observer event or nonzero worker exit')
        b.need(not group_exists(proc.pid), 'owned group remains after leader reap')
        record['owned_group_absent'] = True
        worker = b.read(out/'worker-result.json')
        record['worker_result'] = worker
        record['evidence_checks'] = terminal.validate_outputs(reg,worker,envelope['registration_sha256'])
        b.verify_bound(envelope,reg,preflight=False)
        b.need(b.sha(envelope_path) == envelope_sha, 'envelope changed during observation')
        record['postflight_inputs_unchanged'] = True
        b.need(clock() < hard_at and record['first_event'] is None, 'observer postflight deadline/cancellation')
        b.save(control/'artifact-manifest.json',{str(p.relative_to(out)):b.sha(p) for p in out.iterdir() if p.is_file()})
        b.need(clock() < hard_at and record['first_event'] is None, 'observer publication deadline/cancellation')
        record['status'] = 'completed_pending_parent_audit'
    except BaseException as error:
        latch('observer_failure',error=repr(error))
        if use_timer and not exhausted():
            signal.setitimer(signal.ITIMER_REAL,max(.001,hard_at-clock()))
        record.update(error=repr(error),traceback=traceback.format_exc())
        if proc is not None and (proc.returncode is None or group_exists(proc.pid)):
            # No poll before this call: even a pre-snapshot error retains the
            # direct unreaped child proof. Cleanup shares the original 5+5 bound.
            cleanup = stop_owned(proc,send=lambda sig:signal_owned(proc,anchors,sig,record),
                                 deadline=min(hard_at,(clock() if term_sent is None else term_sent)+b.LIMITS['cleanup_seconds']))
            record.update(observed_worker_raw_exit=proc.returncode,directly_reaped=proc.returncode is not None)
    finally:
        absent = None
        try:
            publication = True
            absent = None if proc is None else not group_exists(proc.pid)
            record.update(max_aggregate_rss_bytes=peak_aggregate,
                          owned_group_absent=absent,worker_group_absent=absent,cleanup=cleanup)
            if proc is not None:
                record.update(observed_worker_raw_exit=proc.returncode,directly_reaped=proc.returncode is not None)
            try:
                require_budget()
                if 'worker_result' not in record and (out/'worker-result.json').is_file():
                    try: record['worker_result'] = b.read(out/'worker-result.json')
                    except BaseException as error: record['worker_result_read_error'] = repr(error)
                # A read timeout may have been caught above. The consumed total
                # deadline is sticky: never continue into full journal accounting.
                require_budget()
                record['terminal_accounting'] = terminal.accounting(out,record.get('worker_result',{}))
                require_budget()
            except BaseException as error:
                record['accounting_error'] = repr(error)
                if exhausted(): record['terminal_accounting_deferred'] = 'total_deadline_consumed'
            worker_failure = record.get('worker_result',{}).get('first_failure')
            record['raw_worker_first_failure'] = worker_failure
            record['first_observed_failure'] = record['first_event']
            record['final_observer_peak_rss_bytes'] = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform == 'darwin' else 1024)
            record['deadline_consumed'] = exhausted()
            if (record['first_event'] is not None or record['deadline_consumed']
                    or absent is not True or record.get('directly_reaped') is not True
                    or record['final_observer_peak_rss_bytes'] > b.LIMITS['rss_bytes']
                    or 'accounting_error' in record): record['status'] = 'failed'
            if record['deadline_consumed']:
                # Preserve compact partial evidence; do not serialize large
                # worker snapshots or completed accounting after exhaustion.
                for key in ('worker_result','terminal_accounting','evidence_checks'):
                    record.pop(key,None)
            record['elapsed_seconds'] = clock()-started
            record['elapsed_measurement'] = 'after accounting, before receipt I/O'
            b.save(control/'execution-result.json',record)
            # The timer remains active through publication. If it fires in a
            # save, the compact fallback below does no result/journal rereads.
            if exhausted():
                record.update(status='failed',deadline_consumed=True,
                              terminal_accounting_deferred='total_deadline_consumed')
                for key in ('worker_result','terminal_accounting','evidence_checks'):
                    record.pop(key,None)
            record['elapsed_seconds'] = clock()-started
            b.save(control/'observation.json',record)
            final_elapsed = clock()-started
            if exhausted(): record['status'] = 'failed'
            b.save(control/'observer-finalization.json',dict(status=record['status'],
                elapsed_seconds=final_elapsed,deadline_consumed=exhausted(),
                elapsed_measurement='after primary receipts, before this final compact receipt I/O',
                filesystem_limit='Filesystem calls and fsync may overrun; no exact hard real-time I/O guarantee.'))
            return 0 if record['status'] == 'completed_pending_parent_audit' and not exhausted() else 1
        except BaseException as error:
            b.save(control/'observer-publication-failure.json',dict(status='failed',error=repr(error),
                first_event=record['first_event'],raw_worker_first_failure=record.get('raw_worker_first_failure'),
                observed_worker_raw_exit=None if proc is None else proc.returncode,
                directly_reaped=proc is not None and proc.returncode is not None,
                owned_group_absent=absent,deadline_consumed=exhausted(),
                elapsed_seconds=clock()-started,
                elapsed_measurement='before compact failure receipt I/O',
                filesystem_limit='Filesystem calls and fsync may overrun; no exact hard real-time I/O guarantee.'))
            return 1
        finally:
            if use_timer:
                signal.setitimer(signal.ITIMER_REAL,0)
                signal.signal(signal.SIGALRM,old_alarm)
                if old_timer[0] > 0:
                    signal.setitimer(signal.ITIMER_REAL,max(.001,old_timer[0]-(time.monotonic()-timer_started)),old_timer[1])
            for n,handler in previous.items(): signal.signal(n,handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--envelope',required=True)
    parser.add_argument('--envelope-sha256',required=True)
    args = parser.parse_args()
    raise SystemExit(main(args.envelope,args.envelope_sha256))
