"""Bounded exact-owned process evidence; absence is distinct from reaping."""
import os
import shlex
import signal
import subprocess
import threading
import time
import lifecycle as life


def census(deadline):
    result = subprocess.run(['ps', '-axo', 'pid=,ppid=,pgid=,command='],
                            text=True, capture_output=True,
                            timeout=life.remaining(deadline, .2))
    life.remaining(deadline)
    if result.returncode:
        raise life.Stop('Process census unavailable')
    rows = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 3)
        if len(fields) != 4:
            raise life.Stop('Malformed process census')
        rows.append(dict(pid=int(fields[0]), ppid=int(fields[1]), pgid=int(fields[2]),
                         argv=shlex.split(fields[3])))
    return rows


def absent(pgid, deadline):
    life.remaining(deadline)
    if type(pgid) is not int or pgid <= 1 or pgid == os.getpgrp():
        raise life.Stop('Unsafe owned process group')
    try:
        os.killpg(pgid, 0)
        value = False
    except ProcessLookupError:
        value = True
    except PermissionError:
        value = not any(row['pgid'] == pgid for row in census(deadline))
    life.remaining(deadline)
    return value


def verify_session(pid, parent, command, deadline, *, orphan=False):
    rows = [row for row in census(deadline) if row['pid'] == pid]
    if (len(rows) != 1 or rows[0]['pgid'] != pid or rows[0]['argv'] != command
            or rows[0]['ppid'] not in ({parent, 1} if orphan else {parent})
            or os.getsid(pid) != pid):
        raise life.Stop('Exact owned command/parent/session proof unavailable')
    return dict(pid=pid, pgid=pid, parent_at_registration=rows[0]['ppid'], argv=command,
                new_session_verified=True, ownership='exact_command_parent_T0_capsule_output',
                term_sent=False, kill_sent=False, group_absent=False)


class Child:
    def __init__(self, process):
        self.process = process
        self.lock = threading.RLock()
        self.report = None

    def poll(self):
        with self.lock:
            if self.report is not None:
                return self.report
            pid, status = os.waitpid(self.process.pid, os.WNOHANG)
            if pid:
                code = os.waitstatus_to_exitcode(status)
                self.process.returncode = code
                self.report = dict(pid=pid, raw_wait_status=status, returncode=code,
                                   reaped_by=os.getpid(), direct_child_reaped=True,
                                   observed_monotonic=time.monotonic())
            return self.report


def signal_once(record, number):
    if not record.get('new_session_verified') or record['pid'] != record['pgid']:
        raise life.Stop('Unproven ownership; group signaling forbidden')
    key = 'term_sent' if number == signal.SIGTERM else 'kill_sent'
    if record[key]:
        return
    record[key] = True
    try:
        os.killpg(record['pgid'], number)
    except ProcessLookupError:
        pass
    except PermissionError as error:
        record.setdefault('signal_errors', []).append(repr(error))


def group_rss(pgids, deadline):
    """Observe owned live groups in one census; a vanished leader is not a bad RSS value.

    Empty rows mean no RSS contribution at this sample, never waitpid reaping or
    final positive absence. Descendants in an owned session remain included.
    """
    result = subprocess.run(['ps', '-axo', 'pgid=,rss='], capture_output=True,
                            text=True, timeout=life.remaining(deadline,.2))
    life.remaining(deadline)
    if result.returncode:
        raise life.Stop('Owned group RSS census failed','resource_stop')
    totals = {pgid:0 for pgid in pgids}
    for line in result.stdout.splitlines():
        fields=line.split()
        if len(fields)!=2 or not all(x.isdigit() for x in fields):
            raise life.Stop('Invalid group RSS observation','resource_stop')
        pgid,rss=map(int,fields)
        if pgid in totals:totals[pgid]+=rss*1024
    return max(totals.values(),default=0)
