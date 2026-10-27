"""One-shot external observer for the registered retained BEST276 LR3e-5 D2 continuation."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
OWN = ROOT / 'learning/runs/v2/D2-retained276-lr3em5-execution-observer-luna-20261026-r1'
REG_PATH = ROOT / 'learning/runs/v2/D2-retained276-lr3em5-prepare-luna-20261026-r1/registration.json'
REG_SHA = '9e754cb96fa3d53fec3da58f225ef775158fbb2705bcbbaf5b1d05220cf9a869'
WALL_LIMIT = 1800.0
WORK_LIMIT = 1790.0
RSS_LIMIT = MPS_LIMIT = 6442450944


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(name, value):
    (OWN / name).write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def check_pins(reg):
    checked = 0
    failures = []
    for path, expected in reg['pins'].items():
        try:
            actual = digest(path)
        except BaseException as e:
            actual = 'ERROR:' + repr(e)
        checked += 1
        if actual != expected:
            failures.append({'path': path, 'expected': expected, 'actual': actual})
    return {'checked': checked, 'expected': len(reg['pins']), 'failures': failures}


def state_check(reg):
    state = json.loads(Path(reg['state_path']).read_text())
    return {
        'active_long_campaign_exact': state.get('active_long_campaign') == reg['expected_lease'],
        'active_long_campaign': state.get('active_long_campaign'),
        'active_inference_campaign': state.get('active_inference_campaign'),
        'active_inference_diagnostic': state.get('active_inference_diagnostic'),
        'active_inference_lease': state.get('active_inference_lease'),
        'state_sha256': digest(reg['state_path']),
    }


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


def worker_resources(out):
    path = out / 'resources.jsonl'
    if not path.is_file():
        return {'present': False, 'samples': 0, 'peak_rss_bytes': None, 'peak_mps_driver_bytes': None}
    peak_rss = peak_mps = 0
    count = 0
    with path.open() as f:
        for line in f:
            if not line.strip():
                continue
            if not line.endswith('\n'):
                break
            row = json.loads(line)
            count += 1
            peak_rss = max(peak_rss, int(row.get('peak_rss_bytes', 0)))
            peak_mps = max(peak_mps, int(row.get('mps_driver_bytes', 0)))
    return {'present': True, 'samples': count, 'peak_rss_bytes': peak_rss,
            'peak_mps_driver_bytes': peak_mps}


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


def main():
    # O_EXCL marker makes this observer non-retryable, including preflight failures.
    with (OWN / 'one-launch-marker.json').open('x') as marker:
        marker.write(json.dumps({'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                 'registration_sha256': REG_SHA, 'single_attempt': True}) + '\n')
    reg_bytes = REG_PATH.read_bytes()
    reg = json.loads(reg_bytes)
    out = Path(reg['output'])
    cache = Path(reg['import_policy']['pycache_prefix'])
    interpreter_real = Path(reg['interpreter']).resolve(strict=True)
    cmd = ['/usr/bin/env', 'PYTHONPYCACHEPREFIX=' + str(cache), 'PYTHONDONTWRITEBYTECODE=1',
           reg['interpreter'], '-B', reg['launcher_path'], '--registration', str(REG_PATH),
           '--registration-sha256', REG_SHA]
    pre = {
        'registration_sha256': hashlib.sha256(reg_bytes).hexdigest(),
        'pins': check_pins(reg),
        'lease': state_check(reg),
        'output_absent': not os.path.lexists(out),
        'cancel_absent': not os.path.lexists(reg['cancel_path']),
        'cache_path': str(cache),
        'cache_empty_before': cache.is_dir() and not any(cache.iterdir()),
        'interpreter_lexical': reg['interpreter'],
        'interpreter_resolved': str(interpreter_real),
        'interpreter_resolved_sha256': digest(interpreter_real),
        'interpreter_pin_sha256': reg['pins'].get(str(interpreter_real)),
        'command': cmd,
        'cwd': str(ROOT),
        'limits': reg['limits'],
        'registration_pins_expected': 13800,
    }
    save('prelaunch.json', pre)
    assert pre['registration_sha256'] == REG_SHA
    assert pre['pins']['checked'] == pre['pins']['expected'] == 13800 and not pre['pins']['failures']
    assert pre['lease']['active_long_campaign_exact'] and pre['lease']['active_inference_campaign'] is None
    assert pre['lease']['active_inference_lease'] is None
    assert pre['lease']['active_inference_diagnostic'] is None
    assert pre['output_absent'] and pre['cancel_absent'] and pre['cache_empty_before']
    assert pre['interpreter_resolved_sha256'] == pre['interpreter_pin_sha256']
    assert reg['limits'] == {'MPS_bytes': MPS_LIMIT, 'RSS_bytes': RSS_LIMIT,
                             'eval_updates': [276, 288, 300, 312, 324, 336],
                             'max_updates': 60, 'retries': 0,
                             'total_seconds': 1800, 'work_seconds': 1790}
    assert cmd[3] == reg['interpreter'] and cmd[5] == reg['launcher_path']

    record = {'registration_sha256': REG_SHA, 'command': cmd, 'cwd': str(ROOT),
              'observer_pid': os.getpid(), 'observer_started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'outer_limit_seconds': WALL_LIMIT, 'work_limit_seconds': WORK_LIMIT,
              'cleanup_window_seconds': WALL_LIMIT - WORK_LIMIT, 'aggregate_rss_limit_bytes': RSS_LIMIT,
              'mps_limit_bytes': MPS_LIMIT, 'launch_count': 1, 'prelaunch': pre,
              'cleanup_signals': [], 'first_event': None}
    outer_start = time.monotonic()
    record['outer_started_monotonic'] = outer_start
    record['outer_started_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    stdout_path, stderr_path = OWN / 'stdout.log', OWN / 'stderr.log'
    with stdout_path.open('x') as stdout, stderr_path.open('x') as stderr, (OWN / 'resources.jsonl').open('x') as samples:
        env = os.environ.copy()
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
        record['outer_pid'] = proc.pid
        record['outer_process_initial'] = process_rows().get(proc.pid)
        record['outer_process_group'] = record['outer_process_initial']['pgid'] if record['outer_process_initial'] else None
        save('launch.json', record)
        peak_aggregate = peak_sample = 0
        term_at = outer_start + WORK_LIMIT
        hard_at = outer_start + WALL_LIMIT
        while True:
            now = time.monotonic()
            code = proc.poll()
            rows = process_rows()
            owned = descendants(rows, proc.pid)
            observer_row = rows.get(os.getpid())
            aggregate = sum(x['rss_bytes'] for x in owned) + (observer_row['rss_bytes'] if observer_row else 0)
            sample = {'monotonic': now, 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      'elapsed_outer_seconds': now - outer_start, 'outer_pid': proc.pid,
                      'owned_processes': owned, 'observer_process': observer_row,
                      'aggregate_rss_bytes': aggregate}
            sample['lease_observation'] = state_check(reg)
            worker_launch_path = out / 'worker-launch.json'
            worker_pid = None
            worker_prior = None
            if worker_launch_path.is_file():
                try:
                    wl = json.loads(worker_launch_path.read_text())
                    worker_pid = wl.get('worker_pid')
                    worker_prior = rows.get(worker_pid)
                    sample['worker_launch'] = wl
                    sample['worker_process'] = worker_prior
                    sample['worker_group'] = wl.get('owned_pgid')
                except BaseException as e:
                    sample['worker_observation_error'] = repr(e)
            wr = worker_resources(out)
            sample['worker_resources'] = wr
            if aggregate > peak_aggregate:
                peak_aggregate, peak_sample = aggregate, sample
            samples.write(json.dumps(sample, sort_keys=True) + '\n')
            samples.flush()
            record.update(max_aggregate_rss_bytes=peak_aggregate, max_aggregate_sample=peak_sample,
                          latest_worker_resources=wr)
            if aggregate > RSS_LIMIT and record['first_event'] is None:
                record['first_event'] = {'kind': 'aggregate_rss_limit', 'bytes': aggregate,
                                         'monotonic': now}
            if os.path.lexists(reg['cancel_path']) and record['first_event'] is None:
                record['first_event'] = {'kind': 'cancel_marker', 'monotonic': now}
            if not sample['lease_observation']['active_long_campaign_exact'] and record['first_event'] is None:
                record['first_event'] = {'kind': 'lease_identity_changed', 'monotonic': now,
                                         'lease': sample['lease_observation']}
            if (now >= term_at or record['first_event'] is not None) and code is None:
                if record['first_event'] is None:
                    record['first_event'] = {'kind': 'external_work_deadline', 'monotonic': now}
                if worker_pid is not None:
                    exact_signal(rows, worker_pid, worker_prior, worker_pid, signal.SIGTERM, record)
                try:
                    proc.wait(timeout=max(0.1, min(5.0, hard_at - time.monotonic() - 1.0)))
                except subprocess.TimeoutExpired:
                    outer_prior = record.get('outer_process_initial')
                    exact_signal(rows, proc.pid, outer_prior, record.get('outer_process_group'), signal.SIGTERM, record)
                    try:
                        proc.wait(timeout=max(0.1, hard_at - time.monotonic() - 0.5))
                    except subprocess.TimeoutExpired:
                        current_rows = process_rows()
                        current_worker = current_rows.get(worker_pid) if worker_pid else None
                        if current_worker and worker_prior and current_worker['start_identity'] == worker_prior['start_identity'] and current_worker['pgid'] == worker_pid:
                            exact_signal(current_rows, worker_pid, worker_prior, worker_pid, signal.SIGKILL, record)
                        current_outer = current_rows.get(proc.pid)
                        if current_outer and outer_prior and current_outer['start_identity'] == outer_prior['start_identity']:
                            exact_signal(current_rows, proc.pid, outer_prior, record.get('outer_process_group'), signal.SIGKILL, record)
                code = proc.poll()
            if code is not None:
                code = proc.wait()
                break
            if time.monotonic() >= hard_at:
                current_rows = process_rows()
                current_worker = current_rows.get(worker_pid) if worker_pid else None
                if current_worker and current_worker['pgid'] == worker_pid:
                    exact_signal(current_rows, worker_pid, current_worker, worker_pid, signal.SIGKILL, record)
                current_outer = current_rows.get(proc.pid)
                if current_outer:
                    exact_signal(current_rows, proc.pid, current_outer,
                                 record.get('outer_process_group'), signal.SIGKILL, record)
                while proc.poll() is None:
                    time.sleep(0.1)
                code = proc.wait()
                break
            time.sleep(min(1.0, max(0.02, hard_at - now)))
        ended = time.monotonic()
        record.update(outer_raw_exit=code, outer_ended_monotonic=ended,
                      outer_ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      outer_inclusive_wall_seconds=ended - outer_start,
                      max_aggregate_rss_bytes=peak_aggregate, max_aggregate_sample=peak_sample)

    # Log writers are closed. Full postflight pin checks stay outside the timed monitor.
    post_rows = process_rows()
    record['outer_process_absent'] = proc.pid not in post_rows
    worker_result_path = out / 'execution-result.json'
    worker_launch_path = out / 'worker-launch.json'
    record['execution_result'] = json.loads(worker_result_path.read_text()) if worker_result_path.is_file() else None
    record['worker_launch'] = json.loads(worker_launch_path.read_text()) if worker_launch_path.is_file() else None
    record['worker_result'] = json.loads((out / 'worker-result.json').read_text()) if (out / 'worker-result.json').is_file() else None
    record['worker_raw_exit'] = (record['execution_result'] or {}).get('observed_worker_raw_exit')
    record['worker_resources'] = worker_resources(out)
    worker_pid = (record['worker_launch'] or {}).get('worker_pid')
    worker_group = (record['worker_launch'] or {}).get('owned_pgid')
    post_rows = process_rows()
    record['worker_process_absent'] = worker_pid is None or worker_pid not in post_rows
    record['worker_group_absent'] = worker_group is None or not any(row['pgid'] == worker_group for row in post_rows.values())
    state_after = state_check(reg)
    pins_after = check_pins(reg)
    record['postflight'] = {'lease': state_after, 'pins': pins_after,
                            'cache_empty_after': cache.is_dir() and not any(cache.iterdir()),
                            'publication_failure_absent': not os.path.lexists(out / 'publication-failure.json'),
                            'stdout_sha256': digest(stdout_path), 'stderr_sha256': digest(stderr_path),
                            'resources_sha256': digest(OWN / 'resources.jsonl')}
    record['success_authoritative'] = (
        record['outer_raw_exit'] == 0 and record['worker_raw_exit'] == 0
        and record['outer_inclusive_wall_seconds'] <= WALL_LIMIT
        and record['first_event'] is None and record['outer_process_absent']
        and record['worker_process_absent'] and record['worker_group_absent']
        and record['postflight']['lease']['active_long_campaign_exact']
        and record['postflight']['lease']['active_inference_campaign'] is None
        and record['postflight']['lease']['active_inference_lease'] is None
        and record['postflight']['lease']['active_inference_diagnostic'] is None
        and record['postflight']['pins']['checked'] == 13800
        and not record['postflight']['pins']['failures']
        and record['postflight']['cache_empty_after']
        and record['postflight']['publication_failure_absent']
        and record['max_aggregate_rss_bytes'] <= RSS_LIMIT
        and record['worker_resources']['peak_rss_bytes'] <= RSS_LIMIT
        and record['worker_resources']['peak_mps_driver_bytes'] <= MPS_LIMIT)
    record['observer_ended_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save('observation.json', record)
    print(json.dumps({'outer_raw_exit': record['outer_raw_exit'], 'worker_raw_exit': record['worker_raw_exit'],
                      'outer_wall_seconds': record['outer_inclusive_wall_seconds'],
                      'peak_aggregate_rss_bytes': record['max_aggregate_rss_bytes'],
                      'worker_peak_rss_bytes': record['worker_resources']['peak_rss_bytes'],
                      'worker_peak_mps_driver_bytes': record['worker_resources']['peak_mps_driver_bytes'],
                      'success_authoritative': record['success_authoritative']}, sort_keys=True), flush=True)
    return 0 if record['success_authoritative'] else 1


if __name__ == '__main__':
    try:
        exit_code = main()
    except BaseException as e:
        (OWN / 'observer-error.json').write_text(json.dumps({'error': repr(e),
            'traceback': __import__('traceback').format_exc(),
            'at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}, indent=2) + '\n')
        raise

    raise SystemExit(exit_code)
