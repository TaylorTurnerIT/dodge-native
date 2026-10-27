"""One registered launch, direct wait, independent deadline and retained raw evidence."""
import datetime, hashlib, json, os, pathlib, signal, subprocess, time
ROOT = pathlib.Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
OWN = pathlib.Path(__file__).parent
REG = ROOT / 'learning/runs/v2/critic-diagnostic-parent-prepare-20261025-r1/registration-r2.json'
SHA = 'bd1031e98bc4ea94b8fb5c4b0a726c8bf513651ac607e571194c04246c87232d'
COMMAND = [str(ROOT / 'python/.venv/bin/python'), '-B', str(ROOT / 'learning/runs/v2/critic-diagnostic-runner-prepare-20261025-r2/execute_once.py'), '--registration', str(REG), '--registration-sha256', SHA]
def save(name, value):
    (OWN / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
def ps(pid):
    r = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'pid=,ppid=,pgid=,lstart=,command='], capture_output=True, text=True)
    return {'returncode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}
def group_present(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
reg = json.loads(REG.read_bytes())
accept_path = REG.parent / 'parent-acceptance-r2.json'
accept = json.loads(accept_path.read_bytes())
state_path = pathlib.Path(reg['state_path'])
state_bytes = state_path.read_bytes()
state = json.loads(state_bytes)
out = pathlib.Path(reg['output'])
checks = {'registration_sha256': hashlib.sha256(REG.read_bytes()).hexdigest(), 'acceptance_sha256': hashlib.sha256(accept_path.read_bytes()).hexdigest(), 'lease_exact': state['active_long_campaign'] == reg['expected_lease'], 'output_absent': not os.path.lexists(out), 'run_seed': reg['run_seed'], 'state_sha256_before': hashlib.sha256(state_bytes).hexdigest()}
save('prelaunch.json', checks)
assert checks['registration_sha256'] == SHA
assert accept['registration_sha256'] == SHA and accept['review_verdict'] == 'No findings' and accept['all_hashes_match'] is True
assert checks['lease_exact'] and checks['output_absent'] and checks['run_seed'] == 3192039780
assert reg['limits'] == {'MPS_bytes': 6442450944, 'RSS_bytes': 6442450944, 'eval_updates': [0,24,48], 'max_updates': 48, 'retries': 0, 'total_seconds': 1800, 'work_seconds': 1680}
record = {'command': COMMAND, 'registration': str(REG), 'registration_sha256': SHA, 'actual_outer_launch_count': 0, 'observer_pid': os.getpid(), 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'cleanup': [], 'timed_out': False, 'cancelled': False}
with (OWN / 'stdout.log').open('xb') as stdout, (OWN / 'stderr.log').open('xb') as stderr:
    started = time.monotonic()
    process = subprocess.Popen(COMMAND, cwd=ROOT, stdout=stdout, stderr=stderr)
    record.update(actual_outer_launch_count=1, outer_pid=process.pid, started_monotonic=started, outer_ownership=ps(process.pid))
    save('launch.json', record)
    try:
        raw_exit = process.wait(timeout=max(0, 1800 - (time.monotonic() - started)))
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        record['timed_out'] = isinstance(error, subprocess.TimeoutExpired)
        record['cancelled'] = isinstance(error, KeyboardInterrupt)
        worker = json.loads((out / 'worker-launch.json').read_bytes()) if (out / 'worker-launch.json').is_file() else None
        worker_before = ps(worker['worker_pid']) if worker else None
        if process.poll() is None:
            process.terminate()
            record['cleanup'].append('SIGTERM sent to directly owned live outer process; launcher allowed 15s for normal cleanup')
        try:
            raw_exit = process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                process.kill()
                record['cleanup'].append('SIGKILL sent to directly owned live outer process')
            raw_exit = process.wait(timeout=5)
        if worker and group_present(worker['owned_pgid']):
            current = ps(worker['worker_pid'])
            if worker_before and current == worker_before and current['returncode'] == 0 and str(worker['worker_pid']) in current['stdout'] and reg['runner_path'] in current['stdout']:
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    if ps(worker['worker_pid']) != worker_before:
                        break
                    os.kill(worker['worker_pid'], sig)
                    record['cleanup'].append({'exact_worker_pid': worker['worker_pid'], 'signal': int(sig)})
                    time.sleep(1)
            else:
                record['cleanup'].append({'worker_cleanup_refused_identity_mismatch': current})
    record.update(outer_raw_exit=raw_exit, observed_inclusive_process_wall_seconds=time.monotonic()-started, directly_reaped=True)
record['outer_terminal_ps'] = ps(process.pid)
record['outer_process_absent'] = record['outer_terminal_ps']['returncode'] == 1 and not record['outer_terminal_ps']['stdout'].strip()
for name in ('launch-marker.json', 'worker-launch.json', 'execution-result.json', 'worker-result.json', 'publication-failure.json'):
    path = out / name
    if path.is_file():
        value = json.loads(path.read_bytes())
        save(name, value)
        if name == 'worker-launch.json':
            record['worker_terminal_ps'] = ps(value['worker_pid'])
            record['worker_process_absent'] = record['worker_terminal_ps']['returncode'] == 1 and not record['worker_terminal_ps']['stdout'].strip()
            record['worker_group_absent'] = not group_present(value['owned_pgid'])
record['external_exit_and_wall_accepted'] = raw_exit == 0 and record['observed_inclusive_process_wall_seconds'] <= 1800 and not record['timed_out'] and not record['cancelled']
record['state_sha256_after'] = hashlib.sha256(state_path.read_bytes()).hexdigest()
record['lease_still_exact'] = json.loads(state_path.read_bytes())['active_long_campaign'] == reg['expected_lease']
save('observation.json', record)
print(json.dumps(record, sort_keys=True), flush=True)
