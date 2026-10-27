"""One exact registered launch with bounded independent observation."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
OWN = Path(__file__).parent
PREP = ROOT / 'learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r3'
REG = PREP / 'registration-r4.json'
PIN = PREP / 'registration-r4-pin.json'
ACCEPT = PREP / 'parent-acceptance-r4.json'
SHA = '6ae91ee55c4437e01daeff0d9cf6adfdcb01a3e62d977c2074c0cf115c4dab6e'
LIMIT = 1800

def save(name, value):
    (OWN / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def ps(pid):
    r = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'pid=,ppid=,pgid=,rss=,etime=,lstart=,command='], capture_output=True, text=True)
    return {'returncode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}

def group_present(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False

reg_bytes = REG.read_bytes()
pin = json.loads(PIN.read_bytes())
reg = json.loads(reg_bytes)
accept = json.loads(ACCEPT.read_bytes())
state_path = Path(reg['state_path'])
state_bytes = state_path.read_bytes()
state = json.loads(state_bytes)
out = Path(reg['output'])
cache = Path(reg['import_policy']['pycache_prefix'])
command = pin['command']
checks = {
    'registration_sha256': hashlib.sha256(reg_bytes).hexdigest(),
    'pin_registration_sha256': pin['sha256'],
    'accepted_registration_sha256': accept['registration_sha256'],
    'acceptance_sha256': hashlib.sha256(ACCEPT.read_bytes()).hexdigest(),
    'acceptance_review_verdict': accept['review_verdict'],
    'pins_checked': pin['pins_checked'],
    'exact_command': command,
    'lease_exact': state.get('active_long_campaign') == reg['expected_lease'],
    'state_sha256_before': hashlib.sha256(state_bytes).hexdigest(),
    'output_absent': not os.path.lexists(out),
    'cache_prefix': str(cache),
    'cache_prefix_empty_before': cache.is_dir() and not any(cache.iterdir()),
    'run_seed': reg['run_seed'],
    'limits': reg['limits'],
}
save('prelaunch.json', checks)
assert checks['registration_sha256'] == SHA
assert pin['sha256'] == SHA and accept['registration_sha256'] == SHA
assert accept['review_verdict'] == 'no_blocking_findings'
assert accept['output_absent'] is True and accept['cache_prefix_empty'] is True
assert checks['lease_exact'] and checks['output_absent'] and checks['cache_prefix_empty_before']
assert checks['run_seed'] == 3192039780 and checks['pins_checked'] == 13566
assert reg['limits'] == {'MPS_bytes': 6442450944, 'RSS_bytes': 6442450944, 'eval_updates': [0, 24, 48], 'max_updates': 48, 'retries': 0, 'total_seconds': 1800, 'work_seconds': 1680}
assert command == ['/usr/bin/env', 'PYTHONPYCACHEPREFIX=' + str(cache), str(ROOT / 'python/.venv/bin/python'), '-B', str(ROOT / 'learning/runs/v2/critic-diagnostic-runner-prepare-20261025-r3/execute_once.py'), '--registration', str(REG), '--registration-sha256', SHA]

record = {
    'command': command,
    'registration': str(REG),
    'registration_sha256': SHA,
    'launch_count': 0,
    'outer_timeout_seconds': LIMIT,
    'observer_pid': os.getpid(),
    'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'timed_out': False,
    'cancelled': False,
    'cleanup': [],
}
with (OWN / 'stdout.log').open('xb') as stdout, (OWN / 'stderr.log').open('xb') as stderr:
    started = time.monotonic()
    process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
    record.update(launch_count=1, outer_pid=process.pid, started_monotonic=started,
                  outer_initial_ps=ps(process.pid))
    save('launch.json', record)
    with (OWN / 'resources.jsonl').open('x') as samples:
        try:
            while True:
                code = process.poll()
                sample = {'elapsed_seconds': time.monotonic() - started, 'outer': ps(process.pid)}
                worker_path = out / 'worker-launch.json'
                if worker_path.is_file():
                    try:
                        worker = json.loads(worker_path.read_bytes())
                        sample['worker'] = ps(worker['worker_pid'])
                    except Exception as error:
                        sample['worker_observation_error'] = repr(error)
                samples.write(json.dumps(sample, sort_keys=True) + '\n')
                samples.flush()
                if code is not None:
                    break
                remaining = LIMIT - (time.monotonic() - started)
                if remaining <= 0:
                    record['timed_out'] = True
                    process.terminate()
                    record['cleanup'].append('SIGTERM sent to directly owned live outer PID; launcher owns worker cleanup')
                    try:
                        code = process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        if process.poll() is None:
                            process.kill()
                            record['cleanup'].append('SIGKILL sent to directly owned live outer PID')
                        code = process.wait(timeout=5)
                    break
                time.sleep(min(5, remaining))
        except KeyboardInterrupt:
            record['cancelled'] = True
            if process.poll() is None:
                process.terminate()
                record['cleanup'].append('SIGTERM sent to directly owned live outer PID; launcher owns worker cleanup')
            try:
                code = process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    process.kill()
                    record['cleanup'].append('SIGKILL sent to directly owned live outer PID')
                code = process.wait(timeout=5)
    record.update(outer_raw_exit=code, inclusive_process_wall_seconds=time.monotonic()-started,
                  directly_reaped=True)
record['outer_terminal_ps'] = ps(process.pid)
record['outer_process_absent'] = record['outer_terminal_ps']['returncode'] == 1 and not record['outer_terminal_ps']['stdout'].strip()
for name in ('launch-marker.json', 'worker-launch.json', 'execution-result.json', 'worker-result.json', 'publication-failure.json'):
    path = out / name
    if path.is_file():
        try:
            value = json.loads(path.read_bytes())
        except Exception as error:
            value = {'read_error': repr(error)}
        save(name, value)
        if name == 'worker-launch.json' and 'worker_pid' in value:
            record['worker_terminal_ps'] = ps(value['worker_pid'])
            record['worker_process_absent'] = record['worker_terminal_ps']['returncode'] == 1 and not record['worker_terminal_ps']['stdout'].strip()
            record['worker_group_absent'] = not group_present(value['owned_pgid'])
record['publication_failure_present'] = (out / 'publication-failure.json').exists()
record['cache_prefix_empty_after'] = cache.is_dir() and not any(cache.iterdir())
record['state_sha256_after'] = hashlib.sha256(state_path.read_bytes()).hexdigest()
record['lease_still_exact'] = json.loads(state_path.read_bytes()).get('active_long_campaign') == reg['expected_lease']
record['outer_exit_and_wall_accepted'] = code == 0 and record['inclusive_process_wall_seconds'] <= LIMIT and not record['timed_out'] and not record['cancelled']
save('observation.json', record)
print(json.dumps(record, sort_keys=True), flush=True)
