#!/usr/bin/env python3
"""Stdlib-only, single-launch outer observer for the registered frozen campaign."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time
import traceback

ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
OUT = ROOT / 'learning/runs/v2/postovernight-action-mode-execution-r1'
CAMPAIGN = ROOT / 'learning/runs/v2/postovernight-action-mode-campaign-r1'
PREP = ROOT / 'learning/runs/v2/postovernight-action-mode-prepare-r3'
CAPSULE = PREP / 'source-snapshot'
PLAN = ROOT / 'learning/runs/v2-orchestration/postovernight-action-mode-execution-r1-plan-r3.json'
STATE = ROOT / 'learning/runs/v2-orchestration/state.json'
PROTOCOL_HASH = '90e3ae1cc8ba253e2e64a708f9b66ed59762e85668a15197d04d9265180ea741'
RUNNER_HASH = '8c4be28db13db8df2c4fb647ea10fdd815ef6612139dc497b04b4b6915f9e329'
CAPSULE_HASH = '1b27ce7ec141a124dc880cddc214eee1788ac503a3951005f1200c1873445e50'

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def save(name, value):
    with (OUT / name).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def checked(pins):
    actual = {str(p): sha(p) for p in pins}
    require(all(actual[str(p)] == digest for p, digest in pins.items()), 'Frozen input hash mismatch')
    return actual

def table():
    p = subprocess.run(['ps', '-axo', 'pid=,ppid=,pgid=,lstart=,rss=,args='],
                       capture_output=True, text=True, timeout=1)
    require(p.returncode == 0, 'Process table observation failed: ' + p.stderr)
    rows = []
    for line in p.stdout.splitlines():
        fields = line.split(None, 9)
        if len(fields) == 10:
            rows.append(dict(pid=int(fields[0]), ppid=int(fields[1]), pgid=int(fields[2]),
                             start_time=' '.join(fields[3:8]), rss_bytes=int(fields[8])*1024,
                             command=fields[9]))
    return rows

def inventory():
    result = {}
    for base in (ROOT / 'learning/runs/v2', ROOT / 'learning/runs/v2-orchestration'):
        for p in sorted(base.rglob('*')):
            if p.is_file() and not p.is_relative_to(OUT) and not p.is_relative_to(CAMPAIGN):
                s = p.stat()
                result[str(p.relative_to(ROOT))] = dict(size=s.st_size, mtime_ns=s.st_mtime_ns,
                                                       mode=s.st_mode, inode=s.st_ino)
    return result

def preflight():
    plan = read(PLAN)
    p = read(plan['protocol'])
    state = read(STATE)
    lease = state['active_long_campaign']
    require(all(lease.get(k) == v for k, v in plan['required_lease'].items()), 'Exact lease mismatch')
    require(lease['parent_owned'] is True and lease['training_authorized'] is False,
            'Lease ownership/authority mismatch')
    require(lease['planned_budget_seconds'] == 600 and lease['cleanup_reserve_seconds'] == 10
            and lease['expected_episodes'] == 768, 'Lease limits mismatch')
    require(sha(PLAN) == lease['execution_plan_sha256'], 'Lease plan hash mismatch')
    acceptance_path = ROOT / lease['review_acceptance_receipt']
    require(sha(acceptance_path) == lease['review_acceptance_sha256'], 'Acceptance hash mismatch')
    acceptance = read(acceptance_path)
    require(acceptance['status'] == 'parent_accepted_for_one_registered_diagnostic_only'
            and acceptance['campaign_invocations_before_acceptance'] == 0
            and acceptance['training_authorized'] is False, 'Acceptance authority mismatch')
    require(sha(ROOT / acceptance['review']) == acceptance['review_sha256'], 'Review hash mismatch')
    review = read(ROOT / acceptance['review'])
    require(review['findings'] == [] and review['status'] == 'no_findings_with_scope_limits', 'Review findings')
    require(sha(plan['protocol']) == PROTOCOL_HASH == lease['protocol_sha256']
            == acceptance['protocol_sha256'], 'Protocol pin mismatch')
    require(sha(plan['command'][2]) == RUNNER_HASH == lease['harness_sha256']
            == acceptance['runner_sha256'], 'Runner pin mismatch')
    require(sha(CAPSULE / 'capsule-manifest.json') == CAPSULE_HASH
            == lease['frozen_capsule_manifest_sha256'] == acceptance['capsule_manifest_sha256'],
            'Capsule manifest mismatch')
    require(not CAMPAIGN.exists(), 'Campaign output already exists; refusing any launch')
    require(not os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK'), 'MPS fallback flag set; no flag mutation authorized')
    manifest = read(CAPSULE / 'capsule-manifest.json')
    require(len(manifest['files']) == 87 and len(p['foundation_sources']) == 75, 'Input counts mismatch')
    pins = {str(CAPSULE / k): v for k, v in manifest['files'].items()}
    pins.update({str(ROOT / k): v for k, v in p['foundation_sources'].items()})
    pins[str(ROOT / p['foundation_identity_path'])] = p['foundation_identity_sha256']
    for checkpoint in p['checkpoints']:
        pins[str(ROOT / checkpoint['path'])] = checkpoint['sha256']
        if checkpoint['control']:
            pins[str(ROOT / checkpoint['control'])] = checkpoint['control_sha256']
    foundation = read(ROOT / p['foundation_identity_path'])
    pins.update(foundation['foundation']['binary_and_receipt_sha256'])
    pins.update(manifest['external_pins'])
    pins[str(CAPSULE / 'capsule-manifest.json')] = CAPSULE_HASH
    pins[plan['protocol']] = PROTOCOL_HASH
    pins[str(PLAN)] = lease['execution_plan_sha256']
    pins[str(acceptance_path)] = lease['review_acceptance_sha256']
    pins[str(ROOT / acceptance['review'])] = acceptance['review_sha256']
    for name, digest in manifest['files'].items():
        path = CAPSULE / name
        require(not path.is_symlink() and path.resolve().is_relative_to(CAPSULE)
                and not path.stat().st_mode & 0o222, 'Writable or escaped capsule file: ' + name)
        for parent in path.parents:
            if not parent.is_relative_to(CAPSULE):
                break
            require(not parent.stat().st_mode & 0o222, 'Writable capsule directory')
    canonical = read(PREP / 'artifact-manifest-final.json')
    pins.update({str(PREP / k): v for k, v in canonical.items()})
    protected_prior = read(PREP / 'protected-before.json')
    pins.update({str(ROOT / k): v for k, v in protected_prior.items()})
    checked(pins)
    require(Path(plan['command'][0]).resolve() == Path(p['foundation_runtime']['interpreter']),
            'Registered interpreter resolves differently')
    require(plan['command'] == read(PREP / 'implementation-result.json')['invocation_after_parent_review_only'],
            'Registered command differs from preparation')
    protected = set(pins) | {str(STATE), str(PREP / 'artifact-manifest-final.json')}
    for base in (ROOT / 'learning/runs/v2/milestone3-D2-curriculum-r1',
                 ROOT / 'learning/runs/v2-orchestration'):
        protected.update(str(f) for f in base.rglob('*') if f.is_file())
    protected.update(str(f) for f in (ROOT / 'learning/runs/v2').rglob('*.pt'))
    before = {path: sha(path) for path in sorted(protected)}
    save('input-inventory.json', {'pins': pins, 'capsule_payload_count': 87,
                                 'original_foundation_count': 75, 'checkpoint_count': 3,
                                 'historical_control_count': 2, 'external_runtime_pins': manifest['external_pins']})
    save('protected-before.json', before)
    save('tree-before.json', inventory())
    save('state-before.json', state)
    save('command.json', plan['command'])
    (OUT / 'command.txt').write_text(shlex.join(plan['command']) + '\n')
    save('preflight.json', dict(status='passed', utc=utc(), exact_lease=lease,
                               full_input_hashes_verified=True, pins_verified=len(pins),
                               protected_files=len(before), canonical_preparation_entries=len(canonical),
                               prior_protected_entries=len(protected_prior), campaign_output_absent=True,
                               environment_flags={k:v for k,v in os.environ.items()
                                                  if k.startswith(('PYTORCH','TORCH','MPS','PYTHON'))},
                               environment_changes=False, gameplay_or_model_imports=0,
                               wrapper_sha256=sha(__file__)))
    return plan, lease

def main():
    process = None
    worker = None
    supervisor = None
    start = None
    receipt = dict(actual_command_launch_count=0, wrapper_pid=os.getpid(), wrapper_pgid=os.getpgrp(),
                   wrapper_started_utc=utc(), wrapper_started_monotonic=time.monotonic(),
                   cleanup_actions=[], observations=[], errors=[], no_retry=True,
                   normal_experiment_budget_seconds=600, separate_cleanup_reserve_seconds=10)
    def observe(stream):
        nonlocal worker, supervisor
        rows = table()
        own = []
        for row in rows:
            if row['pid'] == process.pid:
                require(row['pgid'] == process.pid and row['ppid'] == os.getpid(),
                        'Supervisor process-group identity mismatch')
                if supervisor is None:
                    require(read(PLAN)['command'][2] in row['command'] and '--worker' not in row['command'],
                            'Supervisor command identity mismatch')
                    supervisor = row.copy()
                    receipt['supervisor_identity'] = supervisor
                require(row['start_time'] == supervisor['start_time'], 'Supervisor PID identity changed')
                own.append(row)
            if row['ppid'] == process.pid and row['pgid'] == row['pid'] and '--worker' in row['command']:
                require(read(PLAN)['command'][2] in row['command']
                        and ('--supervisor-pid ' + str(process.pid)) in row['command'], 'Unproved worker candidate')
                if worker is None:
                    worker = row.copy()
                    receipt['worker_identity'] = worker
                    save('worker-identity.json', worker)
                require(row['pid'] == worker['pid'] and row['start_time'] == worker['start_time'],
                        'Worker process identity changed')
                own.append(row)
        record = dict(utc=utc(), monotonic=time.monotonic(), elapsed_seconds=time.monotonic()-start,
                      owned_processes=own)
        stream.write(json.dumps(record, sort_keys=True) + '\n')
        stream.flush()
        return rows

    def cleanup(reason):
        receipt['cleanup_reason'] = reason
        at = time.monotonic()
        end = min(at + 10, start + 610) if start is not None else at + 10
        if process is not None and process.poll() is None:
            require(os.getpgid(process.pid) == process.pid, 'Cannot prove supervisor group at cleanup')
            os.killpg(process.pid, signal.SIGTERM)
            receipt['cleanup_actions'].append(dict(signal='SIGTERM', pgid=process.pid, utc=utc(),
                                                   reason='First cooperative supervisor cleanup'))
            while process.poll() is None and time.monotonic() < end - 2:
                time.sleep(0.05)
        rows = table()
        for identity in (worker, supervisor):
            if identity is None:
                continue
            members = [r for r in rows if r['pgid'] == identity['pgid']]
            if not members:
                continue
            leaders = [r for r in members if r['pid'] == identity['pid']]
            if not leaders or leaders[0]['start_time'] != identity['start_time']:
                receipt['errors'].append('Group identity no longer provable: ' + str(identity['pgid']))
                continue
            os.killpg(identity['pgid'], signal.SIGKILL)
            receipt['cleanup_actions'].append(dict(signal='SIGKILL', pgid=identity['pgid'], utc=utc(),
                                                   reason='Exact proved-owned group remained'))
        if process is not None:
            try:
                process.wait(timeout=max(0.001, end-time.monotonic()))
            except subprocess.TimeoutExpired:
                receipt['errors'].append('Supervisor reap not completed within cleanup reserve')
        receipt['outer_cleanup_seconds'] = time.monotonic()-at

    def cancel(number, frame):
        raise KeyboardInterrupt('Outer observer cancellation signal ' + str(number))

    try:
        plan, lease = preflight()
        print('Preflight passed. Launching exact registered command once.', flush=True)
        signal.signal(signal.SIGTERM, cancel)
        signal.signal(signal.SIGINT, cancel)
        with (OUT / 'supervisor.stdout.log').open('x') as stdout, \
             (OUT / 'supervisor.stderr.log').open('x') as stderr, \
             (OUT / 'outer-resources.jsonl').open('x') as resources:
            require(read(STATE)['active_long_campaign'] == lease, 'Lease changed immediately before launch')
            require(not CAMPAIGN.exists(), 'Campaign output appeared before launch')
            start = time.monotonic()
            receipt.update(launch_utc=utc(), launch_monotonic=start)
            save('before-launch.json', receipt)
            blocked = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
            try:
                receipt['actual_command_launch_count'] = 1
                process = subprocess.Popen(plan['command'], cwd=ROOT, stdout=stdout, stderr=stderr,
                                           start_new_session=True,
                                           preexec_fn=lambda: signal.pthread_sigmask(signal.SIG_SETMASK, blocked))
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, blocked)
            receipt.update(supervisor_pid=process.pid, supervisor_pgid=process.pid,
                           popen_return_monotonic=time.monotonic(), popen_return_utc=utc())
            save('launch.json', receipt)
            while process.poll() is None:
                observe(resources)
                if time.monotonic() - start >= 600:
                    cleanup('Outer original 600-second experiment deadline reached; cleanup only')
                    break
                time.sleep(0.25)
            process.wait(timeout=max(0.001, start+610-time.monotonic()))
            receipt.update(observed_exit_code=process.returncode, exit_observed_monotonic=time.monotonic(),
                           exit_observed_utc=utc(), actual_outer_wall_through_exit_seconds=time.monotonic()-start)
            receipt['final_process_rows'] = [r for r in table()
                                             if r['pid'] in {process.pid, (worker or {}).get('pid')}
                                             or r['pgid'] in {process.pid, (worker or {}).get('pgid')}]
            require(not receipt['final_process_rows'], 'Owned process/group remains after supervisor exit')
    except BaseException as error:
        receipt['errors'].append(repr(error))
        receipt['traceback'] = traceback.format_exc()
        if process is not None:
            try:
                cleanup('Outer exception; retain failure and never retry')
            except BaseException as cleanup_error:
                receipt['errors'].append('Cleanup exception: ' + repr(cleanup_error))
            receipt.update(observed_exit_code=process.poll(), exit_observed_utc=utc(),
                           exit_observed_monotonic=time.monotonic(),
                           actual_outer_wall_through_exit_seconds=time.monotonic()-start)
    finally:
        receipt.update(finished_utc=utc(), supervisor_streams_closed=True,
                       wrapper_source_sha256=sha(__file__), training_launched=False,
                       retry_launched=False, ledger_written=False)
        save('process-exit.json', receipt)
        print(json.dumps({k:receipt.get(k) for k in ('actual_command_launch_count','observed_exit_code',
                                                   'actual_outer_wall_through_exit_seconds','errors')}), flush=True)

if __name__ == '__main__':
    main()
