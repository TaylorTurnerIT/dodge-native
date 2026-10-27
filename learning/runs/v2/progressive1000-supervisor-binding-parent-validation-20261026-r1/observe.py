"""External one-shot watchdog, adapted from the retained300 parent observer.

Parent installs marker/lease/approval before invoking this observer. No launch
approval, worker output, lease, checkpoint or source is created or changed here.
"""
import argparse
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
from execute_once import group_exists
import terminal

def process_rows():
    result = subprocess.run(['/bin/ps', '-axo', 'pid=,ppid=,pgid=,rss=,lstart=,command='],
                           capture_output=True, text=True, check=True)
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


def main(envelope_path, envelope_sha):
    envelope, reg = b.load_envelope(envelope_path,envelope_sha)
    control = Path(envelope['control']); out = Path(reg['output'])
    # A failed dispatch is spent. Neither marker is inside the worker output.
    control.mkdir(parents=True,exist_ok=False)
    b.save(control/'dispatch.claimed',dict(envelope_sha256=envelope_sha,observer_pid=os.getpid()))
    record = dict(status='failed',launch_count=0,cleanup_signals=[],first_event=None,
                  registration_sha256=envelope['registration_sha256'],envelope_sha256=envelope_sha,
                  training_eligible=False,promoted=False,parent_terminal_audit_required=True)
    proc = None; worker_pid = None; outer_anchors = {}; worker_anchors = {}
    previous = {n:signal.getsignal(n) for n in (signal.SIGINT,signal.SIGTERM)}
    publication = False
    def latch(kind, **values):
        if record['first_event'] is None:
            record['first_event'] = dict(kind=kind,monotonic=time.monotonic(),**values)
    def handle(number,_frame):
        latch('observer_cancelled',signal=number)
        if publication:
            raise b.Cancelled('observer cancellation during terminal publication')
    for n in previous: signal.signal(n,handle)
    started = envelope['started']; term_at = started+b.LIMITS['work_seconds']; hard_at = started+b.LIMITS['total_seconds']
    peak_aggregate = 0; term_sent = None; kill_sent = False
    try:
        b.verify_bound(envelope,reg,preflight=True)
        b.need(time.monotonic() < term_at and record['first_event'] is None, 'dispatch cancelled or expired')
        command = [reg['interpreter'],'-B',str(b.HERE/'execute_once.py'),'--envelope',str(envelope_path),'--envelope-sha256',envelope_sha]
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONPYCACHEPREFIX=reg['import_policy']['pycache_prefix'],PYTHONPATH=reg['runtime_root'])
        with (control/'stdout.log').open('x') as stdout, (control/'stderr.log').open('x') as stderr, (control/'observer-resources.jsonl').open('x') as samples:
            proc = subprocess.Popen(command,cwd=b.ROOT,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
            record.update(launch_count=1,outer_pid=proc.pid,owned_outer_pgid=proc.pid,command=command)
            b.save(control/'observer-launch.json',record)
            while True:
                now = time.monotonic(); code = proc.poll(); current = process_rows()
                owned = descendants(current,proc.pid)
                for row in owned:
                    if row['pgid'] == proc.pid: outer_anchors[row['pid']] = row
                launch_path = control/'worker-launch.json'
                if launch_path.is_file():
                    launch = b.read(launch_path)
                    b.need(launch['command'] == b.worker_command(envelope,reg) and launch['launcher_pid'] == proc.pid
                           and launch['owned_pgid'] == launch['worker_pid'] and launch['start_new_session'] is True,
                           'worker owned group binding differs')
                    worker_pid = launch['worker_pid']
                    # Only descendants of our Popen are initial ownership anchors.
                    for row in owned:
                        if row['pgid'] == worker_pid: worker_anchors[row['pid']] = row
                group_rows = [r for r in current.values() if r['pgid'] in {proc.pid,worker_pid}]
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
                if code is not None and group_rows: latch('owned_group_survived_launcher')
                if now >= term_at: latch('external_work_deadline')
                if record['first_event'] is not None and term_sent is None:
                    if worker_pid is not None: signal_group(worker_pid,worker_anchors,signal.SIGTERM,record)
                    if code is None: signal_group(proc.pid,outer_anchors,signal.SIGTERM,record)
                    term_sent = time.monotonic()
                if ((term_sent is not None and now-term_sent >= 5) or now >= hard_at-.25) and not kill_sent:
                    if worker_pid is not None: signal_group(worker_pid,worker_anchors,signal.SIGKILL,record)
                    signal_group(proc.pid,outer_anchors,signal.SIGKILL,record); kill_sent = True
                if code is not None and not group_rows:
                    record['outer_raw_exit'] = proc.wait(timeout=0)
                    break
                if now >= hard_at:
                    latch('external_total_deadline')
                    # Bounded reap. A surviving group is explicit failure evidence.
                    try: record['outer_raw_exit'] = proc.wait(timeout=.1)
                    except subprocess.TimeoutExpired: record['outer_raw_exit'] = None
                    break
                time.sleep(min(.1,max(.001,hard_at-now)))
        record['max_aggregate_rss_bytes'] = peak_aggregate
        b.need(record['first_event'] is None and record['outer_raw_exit'] == 0, 'observer event or nonzero launcher exit')
        execution = b.read(control/'execution-result.json')
        record['execution_result'] = execution
        b.need(execution['status'] == 'completed_pending_parent_audit' and execution['observed_worker_raw_exit'] == 0
               and execution['actual_worker_launch_count'] == 1 and execution['directly_reaped'] is True
               and execution['owned_group_absent'] is True and execution['postflight_inputs_unchanged'] is True,
               'launcher terminal evidence differs')
        b.verify_bound(envelope,reg,preflight=False)
        b.need(b.sha(envelope_path) == envelope_sha, 'envelope changed during observation')
        record['postflight_inputs_unchanged'] = True
        b.need(time.monotonic() < hard_at and record['first_event'] is None, 'observer postflight deadline/cancellation')
        record['status'] = 'completed_pending_parent_audit'
    except BaseException as error:
        latch('observer_failure',error=repr(error))
        record.update(error=repr(error),traceback=traceback.format_exc())
        # Exceptional monitor failures still use the same bounded TERM/KILL policy.
        if proc is not None and (proc.poll() is None or group_exists(proc.pid)
                                 or (worker_pid is not None and group_exists(worker_pid))):
            for sig in (signal.SIGTERM,signal.SIGKILL):
                for pgid,anchors in ((worker_pid,worker_anchors),(proc.pid,outer_anchors)):
                    if pgid is None: continue
                    try: signal_group(pgid,anchors,sig,record)
                    except BaseException as cleanup_error:
                        record.setdefault('cleanup_errors',[]).append(repr(cleanup_error))
                        # A still-live Popen child is an independent ownership
                        # proof if ps itself failed before the first snapshot.
                        if pgid == proc.pid and proc.poll() is None:
                            try:
                                os.killpg(proc.pid,sig)
                                record['cleanup_signals'].append(dict(owned_pgid=proc.pid,signal=signal.Signals(sig).name,
                                    ownership='live directly owned Popen with start_new_session=True'))
                            except ProcessLookupError: pass
                try: proc.wait(timeout=min(5,max(.001,hard_at-time.monotonic())))
                except subprocess.TimeoutExpired: pass
            record['outer_raw_exit'] = proc.poll()
    finally:
        try:
            publication = True
            record.update(elapsed_seconds=time.monotonic()-started,max_aggregate_rss_bytes=peak_aggregate,
                          outer_group_absent=proc is None or not group_exists(proc.pid),
                          worker_group_absent=worker_pid is None or not group_exists(worker_pid))
            if proc is not None: record['outer_raw_exit'] = proc.poll()
            for name in ('execution-result.json','publication-failure.json'):
                if (control/name).is_file():
                    try: record[name] = b.read(control/name)
                    except BaseException as error: record[name+'-read-error'] = repr(error)
            if (out/'worker-result.json').is_file():
                try: record['worker_result'] = b.read(out/'worker-result.json')
                except BaseException as error: record['worker_result_read_error'] = repr(error)
            try: record['terminal_accounting'] = terminal.accounting(out,record.get('worker_result',{}))
            except BaseException as error: record['accounting_error'] = repr(error)
            record['final_observer_peak_rss_bytes'] = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*(1 if sys.platform == 'darwin' else 1024)
            if (record['first_event'] is not None or record['elapsed_seconds'] >= b.LIMITS['total_seconds']
                    or not record['outer_group_absent'] or not record['worker_group_absent']
                    or record['final_observer_peak_rss_bytes'] > b.LIMITS['rss_bytes']
                    or (control/'publication-failure.json').exists()): record['status'] = 'failed'
            b.save(control/'observation.json',record)
            if time.monotonic() >= hard_at:
                b.save(control/'observer-publication-failure.json',dict(status='failed',reason='absolute publication deadline'))
                return 1
            return 0 if record['status'] == 'completed_pending_parent_audit' else 1
        except BaseException as error:
            b.save(control/'observer-publication-failure.json',dict(status='failed',error=repr(error),first_event=record['first_event']))
            return 1
        finally:
            for n,handler in previous.items(): signal.signal(n,handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--envelope',required=True)
    parser.add_argument('--envelope-sha256',required=True)
    args = parser.parse_args()
    raise SystemExit(main(args.envelope,args.envelope_sha256))

