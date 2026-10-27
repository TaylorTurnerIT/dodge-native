#!/usr/bin/env python3
"""External one-shot boundary monitor for the registered paired-eval supervisor."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
OWN = ROOT / 'learning/runs/v2/latest-best-paired-eval-execution-observer-luna-20261026-r2'
PREP = ROOT / 'learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r2'
CAMPAIGN = PREP / 'campaign-output'
RUNTIME = ROOT / 'learning/runs/v2/D2-gradient-capsule-parent-freeze-20261025-r5/own/runtime'
PYTHON = ROOT / 'python/.venv/bin/python'
SUPERVISOR = PREP / 'supervisor.py'
TOTAL = 600.0
SHUTDOWN_START = 590.0
RSS_CAP = 6 * 1024**3
MPS_CAP = 6 * 1024**3
stop_request = []

def utc():
    return datetime.now(timezone.utc).isoformat()

def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def process_row(pid):
    r = subprocess.run(['/bin/ps', '-o', 'pid=,ppid=,pgid=,rss=,stat=,command=', '-p', str(pid)],
                       capture_output=True, text=True, timeout=1, check=False)
    if r.returncode or not r.stdout.strip():
        return None
    fields = r.stdout.strip().split(None, 5)
    if len(fields) < 6:
        return None
    return {'pid': int(fields[0]), 'ppid': int(fields[1]), 'pgid': int(fields[2]),
            'rss_bytes': int(fields[3]) * 1024, 'stat': fields[4], 'command': fields[5]}

def process_table():
    r = subprocess.run(['/bin/ps', '-axo', 'pid=,ppid=,pgid=,rss=,stat=,command='],
                       capture_output=True, text=True, timeout=2, check=False)
    if r.returncode:
        raise RuntimeError('process table sample failed: ' + r.stderr.strip())
    rows = []
    for line in r.stdout.splitlines():
        f = line.strip().split(None, 5)
        if len(f) == 6 and f[0].isdigit():
            rows.append({'pid': int(f[0]), 'ppid': int(f[1]), 'pgid': int(f[2]),
                         'rss_bytes': int(f[3]) * 1024, 'stat': f[4], 'command': f[5]})
    return rows

def latest_mps():
    p = CAMPAIGN / 'resources.jsonl'
    if not p.is_file():
        return None
    lines = p.read_text().splitlines()
    if not lines:
        return None
    return int(json.loads(lines[-1])['mps_driver_bytes'])

def exact_worker(rows, supervisor_pid):
    matches = [r for r in rows if r['ppid'] == supervisor_pid and r['pgid'] == r['pid']
               and 'worker.py' in r['command'] and '--worker' in r['command']]
    return matches[0] if len(matches) == 1 else None

def exact_supervisor(pid):
    row = process_row(pid)
    return bool(row and row['pid'] == pid and row['pgid'] == pid
                and str(SUPERVISOR) in row['command'] and '--output' in row['command']
                and str(CAMPAIGN) in row['command']), row

def signal_exact_worker(pid, supervisor_pid, sig, lineage):
    rows = process_table()
    row = exact_worker(rows, supervisor_pid)
    if not row or row['pid'] != pid or row['ppid'] != supervisor_pid or row['pgid'] != pid:
        lineage.append({'at_utc': utc(), 'target': 'worker', 'pid': pid,
                        'action': 'not_signalled_identity_absent_or_changed'})
        return False
    os.kill(pid, sig)
    lineage.append({'at_utc': utc(), 'target': 'worker', 'pid': pid,
                    'verified_identity': row, 'signal': signal.Signals(sig).name})
    return True

def on_signal(signum, _frame):
    stop_request.append({'signal': signal.Signals(signum).name, 'at_utc': utc()})

for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, on_signal)

marker = OWN / 'launch-marker.json'
fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
argv = [str(PYTHON), '-B', str(SUPERVISOR), '--output', str(CAMPAIGN)]
env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'LANG',
       'DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH') if k in os.environ}
env.update({'PYTHONPYCACHEPREFIX': str(OWN / 'outer-pycache'), 'PYTHONPATH': str(RUNTIME),
            'PYTHONUNBUFFERED': '1', 'PYTHONHASHSEED': '0', 'OMP_NUM_THREADS': '4',
            'MKL_NUM_THREADS': '4', 'T3_PAIRED_EVAL_SUPERVISED': '1'})
identity = {'lexical_interpreter': str(PYTHON), 'resolved_interpreter': str(PYTHON.resolve()),
            'interpreter_sha256': sha(PYTHON.resolve()), 'argv': argv, 'cwd': str(ROOT),
            'environment': env, 'launch_count': 1, 'launch_started_utc': utc(),
            'observer_pid': os.getpid(), 'campaign_output_absent_at_launch': not CAMPAIGN.exists()}
os.write(fd, (json.dumps(identity, sort_keys=True, indent=2) + '\n').encode())
os.fsync(fd)
os.close(fd)
(OWN / 'outer-pycache').mkdir()
(OWN / 'outer.stdout.log').open('xb').close()
(OWN / 'outer.stderr.log').open('xb').close()
(OWN / 'samples.jsonl').open('xb').close()
lineage = []
start = time.monotonic()
outer_out = (OWN / 'outer.stdout.log').open('ab', buffering=0)
outer_err = (OWN / 'outer.stderr.log').open('ab', buffering=0)
proc = subprocess.Popen(argv, cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
                        stdout=outer_out, stderr=outer_err, start_new_session=True, close_fds=True)
identity.update({'outer_pid': proc.pid, 'outer_pgid': proc.pid, 'outer_launch_utc': utc()})
write_json(marker, identity)
peak_owned_rss = peak_mps = 0
worker_identity = None
termination_reason = None
raw_exit = None
with (OWN / 'samples.jsonl').open('a', buffering=1) as samples:
    while proc.poll() is None:
        elapsed = time.monotonic() - start
        rows = process_table()
        sup = next((r for r in rows if r['pid'] == proc.pid), None)
        worker = exact_worker(rows, proc.pid)
        if worker:
            current_worker_identity = {'pid': worker['pid'], 'ppid': worker['ppid'], 'pgid': worker['pgid']}
            if worker_identity is None:
                worker_identity = current_worker_identity
        mps = latest_mps()
        owned_rss = (sup['rss_bytes'] if sup else 0) + (worker['rss_bytes'] if worker else 0)
        peak_owned_rss = max(peak_owned_rss, owned_rss)
        if mps is not None:
            peak_mps = max(peak_mps, mps)
        samples.write(json.dumps({'at_utc': utc(), 'elapsed_seconds': elapsed,
            'outer': sup, 'worker': worker, 'owned_rss_bytes': owned_rss,
            'worker_mps_driver_bytes': mps, 'peak_owned_rss_bytes': peak_owned_rss,
            'peak_worker_mps_driver_bytes': peak_mps}, sort_keys=True) + '\n')
        if stop_request:
            termination_reason = 'observer_signal'
        elif owned_rss > RSS_CAP:
            termination_reason = 'aggregate_owned_rss_cap'
        elif mps is not None and mps > MPS_CAP:
            termination_reason = 'worker_mps_cap'
        elif elapsed >= SHUTDOWN_START:
            termination_reason = 'external_590_second_work_deadline'
        if termination_reason:
            if worker:
                signal_exact_worker(worker['pid'], proc.pid, signal.SIGTERM, lineage)
                until = time.monotonic() + 2.0
                while time.monotonic() < until:
                    time.sleep(0.1)
                    refreshed = process_table()
                    same = exact_worker(refreshed, proc.pid)
                    if not same or same['pid'] != worker['pid']:
                        break
                else:
                    signal_exact_worker(worker['pid'], proc.pid, signal.SIGKILL, lineage)
            lineage.append({'at_utc': utc(), 'target': 'supervisor', 'pid': proc.pid,
                            'action': 'allowed_to_publish_and_reap_after_worker_shutdown',
                            'reason': termination_reason})
            break
        time.sleep(0.5)
    if termination_reason:
        remaining = max(0.0, TOTAL - (time.monotonic() - start))
        try:
            raw_exit = proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            ok, row = exact_supervisor(proc.pid)
            if ok:
                os.kill(proc.pid, signal.SIGTERM)
                lineage.append({'at_utc': utc(), 'target': 'supervisor', 'pid': proc.pid,
                                'verified_identity': row, 'signal': 'SIGTERM',
                                'reason': 'external_600_second_deadline'})
            try:
                raw_exit = proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                ok, row = exact_supervisor(proc.pid)
                if ok:
                    os.kill(proc.pid, signal.SIGKILL)
                    lineage.append({'at_utc': utc(), 'target': 'supervisor', 'pid': proc.pid,
                                    'verified_identity': row, 'signal': 'SIGKILL',
                                    'reason': 'external_600_second_deadline'})
                raw_exit = proc.wait(timeout=2.0)
    else:
        raw_exit = proc.wait()
end = time.monotonic()
outer_out.flush(); outer_out.close()
outer_err.flush(); outer_err.close()
rows = process_table()
outer_absent = not any(r['pid'] == proc.pid for r in rows)
worker_group_absent = not any(worker_identity and r['pgid'] == worker_identity['pgid'] for r in rows)
outer_group_absent = not any(r['pgid'] == proc.pid for r in rows)
# Full read-only pinned postflight after the supervisor and its worker have exited.
postflight_started = time.monotonic()
postflight_env = env.copy()
postflight_env['PYTHONPYCACHEPREFIX'] = str(OWN / 'postflight-pycache')
(OWN / 'postflight-pycache').mkdir()
check = subprocess.run([str(PYTHON), '-B', '-c',
    "import json,sys; from pathlib import Path; root=Path(sys.argv[1]); sys.path.insert(0,str(root/'learning/runs/v2/latest-best-paired-eval-prepare-luna-20261026-r2')); import worker; from supervisor import _lease_check; m=worker.verify_inputs(); p=worker.load_json(worker.PROTOCOL_PATH); _lease_check(p,worker.sha256(worker.PROTOCOL_PATH),p['harness_sha256'],worker.sha256(worker.INPUT_MANIFEST_PATH),worker.STATE_PATH); print(json.dumps({'status':'passed','dependency_pin_count':13513,'module_origins':worker.verify_module_origins(),'manifest_sha256':worker.sha256(worker.INPUT_MANIFEST_PATH),'protocol_sha256':worker.sha256(worker.PROTOCOL_PATH)}))",
    str(ROOT)], cwd=str(ROOT), env=postflight_env, stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30, check=False)
postflight = {'returncode': check.returncode, 'stdout': check.stdout, 'stderr': check.stderr,
              'wall_seconds': time.monotonic()-postflight_started,
              'process_absence': {'outer_direct_process_absent': outer_absent,
                                  'outer_process_group_absent': outer_group_absent,
                                  'worker_process_group_absent': worker_group_absent},
              'passed': check.returncode == 0 and outer_absent and outer_group_absent and worker_group_absent}
write_json(OWN / 'postflight.json', postflight)
result_path = CAMPAIGN / 'run-result.json'
result = json.loads(result_path.read_text()) if result_path.is_file() else None
summary = {'schema':'paired_eval_external_execution_observer_v1','status':'observed',
    'launch_count':1,'outer_pid':proc.pid,'outer_pgid':proc.pid,'worker_identity':worker_identity,
    'raw_outer_exit':raw_exit,'full_outer_wall_seconds':end-start,
    'outer_process_absent':outer_absent,'outer_process_group_absent':outer_group_absent,
    'worker_process_group_absent':worker_group_absent,'termination_reason':termination_reason,
    'observer_signals':stop_request,'termination_lineage':lineage,
    'peak_aggregate_owned_rss_bytes':peak_owned_rss,'peak_worker_mps_driver_bytes':peak_mps,
    'resource_caps_bytes':{'aggregate_owned_rss':RSS_CAP,'worker_mps':MPS_CAP},
    'postflight_passed':postflight['passed'],'postflight_failure':None if postflight['passed'] else postflight,
    'supervisor_result':result,'supervisor_result_present':result is not None,
    'episode_rows':None,'campaign_output':str(CAMPAIGN)}
# Derive row counts only after all campaign writers exited.
if result:
    episode_files = list(CAMPAIGN.rglob('episodes.jsonl'))
    summary['episode_files'] = [str(p.relative_to(CAMPAIGN)) for p in episode_files]
    rows = []
    for p in episode_files:
        rows.extend(json.loads(line) for line in p.read_text().splitlines() if line.strip())
    summary['episode_rows'] = len(rows)
    summary['episode_rows_by_checkpoint_mode'] = {}
    for row in rows:
        key = f"{row.get('checkpoint')}:{row.get('mode')}"
        summary['episode_rows_by_checkpoint_mode'][key] = summary['episode_rows_by_checkpoint_mode'].get(key, 0) + 1
# Hash closed observer logs and campaign artifacts, excluding mutable final receipts.
summary['observer_artifact_sha256'] = {}
for p in sorted(OWN.rglob('*')):
    if p.is_file() and p.name not in {'observer-result.json'}:
        summary['observer_artifact_sha256'][str(p.relative_to(OWN))] = sha(p)
write_json(OWN / 'observer-result.json', summary)
print(json.dumps({'status':summary['status'],'raw_outer_exit':raw_exit,
    'full_outer_wall_seconds':summary['full_outer_wall_seconds'],'termination_reason':termination_reason,
    'postflight_passed':postflight['passed'],'campaign_status':None if result is None else result.get('status'),
    'episode_rows':summary['episode_rows']},sort_keys=True))
