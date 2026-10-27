"""One-shot stdlib wrapper for the parent's immutable M3 device-probe plan."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
import traceback

ROOT = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-c8044e79')
EVIDENCE = ROOT / 'learning/runs/v2/milestone3-probe-execution-r1'
PLAN = ROOT / 'learning/runs/v2-orchestration/milestone3_device_probe_r1-plan.json'
STATE = ROOT / 'learning/runs/v2-orchestration/state.json'
PINS = {
    'plan': '1348ba10f8e0f4ea05afde19babda635f758f094e742cb846f1d6e77e3d6c315',
    'identity': '82ad7e95ed3b1a780a826b44d603e2ef2cecc5c1e4057f6ceec4e0ebc3b92267',
    'config': 'aa14a822cd8d1cd559d385501c65a93ad828897f1125d071bb90f2d9f06b28b5',
    'semantic': 'c712523fbb96db069ac2c41235bb233d92954e3ceec7fe12a6b9666bc40a0fee',
    'native': '967c7249acd52339d1818dcbe94e63ee734aea914c3497eb59a7e945a6e95583',
    'acceptance': '673658a1b4d70bbf14e73ac54fc18d918b317490bd14e3c97dcd49a13db94ad9',
    'capsule': '86b5477f5e6811c81ecc87f8f4f48129c74ae8a888e80b12aa0f57ca2ff3d431',
}


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + x)))


def save(name, value):
    with (EVIDENCE / name).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')


def event(kind, **fields):
    with (EVIDENCE / 'wrapper-events.jsonl').open('a') as f:
        f.write(json.dumps(dict(at_utc=utc(), kind=kind, **fields), sort_keys=True, allow_nan=False) + '\n')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def capture(relative, destination):
    source = ROOT / relative
    target = EVIDENCE / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as f:
        f.write(source.read_bytes())


def process_table():
    raw = subprocess.check_output(['ps', '-axo', 'pid=,ppid=,pgid=,lstart=,rss=,command='], text=True, timeout=5)
    rows = {}
    for line in raw.splitlines():
        v = line.split(None, 9)
        if len(v) == 10:
            rows[int(v[0])] = dict(pid=int(v[0]), ppid=int(v[1]), pgid=int(v[2]),
                                  lstart=' '.join(v[3:8]), rss_bytes=int(v[8]) * 1024, command=v[9])
    return raw, rows


def source_inventory():
    paths = set()
    for base in (ROOT / 'python/dodge_rl', ROOT / 'python/tests', ROOT / 'crates'):
        for p in base.rglob('*'):
            if p.is_file() and not {'__pycache__', '.pytest_cache', 'target', 'build'}.intersection(p.relative_to(base).parts):
                if base.name == 'dodge_rl' or p.suffix in {'.py', '.rs', '.toml', '.lock'}:
                    paths.add(p)
    for name in ('Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml', '.cargo/config.toml', 'assets/dodge.p8',
                 'python/pyproject.toml', 'python/requirements-local-mac.txt', 'docs/SPEC_PRIVILEGED_VIT_RL.md',
                 'docs/implementation-plan-v2.md', 'docs/v2-environment-contract.md', 'docs/v2-teacher-training-plan.md',
                 'docs/v2-m3-component-contract.md', 'docs/teacher-qualification-v2.json', 'docs/v2-m3-run-protocol.json'):
        paths.add(ROOT / name)
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)}


def verify_lease(plan):
    lease = load(STATE)['active_long_campaign']
    for k, expected in dict(run_id=plan['run_id'], phase='probe', kind='M3_teacher',
                            authorization='frozen_reviewed_M3_teacher', identity_sha256=PINS['identity'],
                            config_sha256=PINS['config'], plan_sha256=PINS['plan'],
                            output=plan['run_dir'], execution_evidence=plan['execution_evidence'],
                            planned_budget_seconds=180, receipt_reserve_seconds=600, parent_owned=True).items():
        require(lease.get(k) == expected, 'Lease mismatch: ' + k)
    require('parent_terminal_receipt' not in lease, 'Fresh probe has unexpected parent receipt')
    return lease


def inspect_owned(pid, expected, rows):
    current = rows.get(pid)
    return current is not None and all(current.get(k) == expected.get(k) for k in ('pid', 'pgid', 'lstart', 'command'))


def signal_exact(pid, expected, sig, label):
    _, rows = process_table()
    if pid not in rows:
        event('signal_race_process_already_gone', label=label, pid=pid, signal=sig)
        return
    require(inspect_owned(pid, expected, rows) and expected['pgid'] == pid,
            'Refusing signal: process identity/group changed: ' + label)
    try:
        os.killpg(pid, sig)
        event('signal_sent', label=label, pid=pid, pgid=pid, signal=sig)
    except ProcessLookupError:
        event('signal_race_group_already_gone', label=label, pid=pid, signal=sig)


def cleanup(proc, supervisor, worker):
    if proc.poll() is None:
        signal_exact(proc.pid, supervisor, signal.SIGTERM, 'supervisor')
        try:
            proc.wait(timeout=12)
        except subprocess.TimeoutExpired:
            event('supervisor_cleanup_grace_expired', seconds=12)
    if worker is not None:
        _, rows = process_table()
        if worker['pid'] in rows:
            signal_exact(worker['pid'], worker, signal.SIGTERM, 'worker')
            until = time.monotonic() + 5
            while time.monotonic() < until:
                _, rows = process_table()
                if worker['pid'] not in rows:
                    break
                time.sleep(0.2)
            if worker['pid'] in rows:
                signal_exact(worker['pid'], worker, signal.SIGKILL, 'worker')
    if proc.poll() is None:
        signal_exact(proc.pid, supervisor, signal.SIGKILL, 'supervisor')
    proc.wait(timeout=5)


def main():
    began = time.monotonic()
    result = dict(run_id='v2-m3-probe-20261024-r1', task_first_utc='2026-10-24T11:12:15Z',
                  wrapper_started_at_utc=utc(), status='failed', stage='preflight', command_launch_count=0,
                  automatic_retries=0, limits_relaxed=False, parent_independent_acceptance_pending=True,
                  training_qualification=False, probe_weights_excluded_from_pilot_initialization=True,
                  B_E_opened=False, pins=PINS)
    plan = identity = proc = supervisor = worker = None
    command = None
    try:
        require(set(p.name for p in EVIDENCE.iterdir()) == {'execute_once.py'}, 'Execution directory already contains receipts; refusing repeat')
        require(digest(PLAN) == PINS['plan'], 'Immutable plan hash mismatch')
        plan = load(PLAN)
        run = ROOT / plan['run_dir']
        require(not run.exists(), 'Runner directory exists; refusing repeat')
        require(plan['cwd'] == str(ROOT) and Path.cwd() == ROOT, 'Cwd mismatch')
        require(plan['environment'] == {'PYTHONPATH': 'python', 'PYTHONDONTWRITEBYTECODE': '1'}, 'Environment mismatch')
        require(plan['argv'] == [str(ROOT / 'python/.venv/bin/python'), '-B', '-m', 'dodge_rl.train_teacher', 'probe',
                                '--config', str(ROOT / plan['config']), '--identity', str(ROOT / plan['identity']),
                                '--run-dir', str(run), '--run-id', result['run_id']], 'Plan argv mismatch')
        require(plan['run_id'] == result['run_id'] and plan['phase'] == 'probe', 'Plan run/phase mismatch')
        require(plan['planned_budget_seconds'] == 180 and plan['receipt_reserve_seconds'] == 600
                and plan['outer_process_timeout_seconds'] == 210, 'Plan time limits mismatch')
        require(plan['RSS_limit_bytes'] == plan['MPS_driver_limit_bytes'] == 6442450944, 'Plan resource limits mismatch')
        for k in ('identity', 'config'):
            require(plan[k + '_sha256'] == PINS[k] and digest(ROOT / plan[k]) == PINS[k], 'Input hash mismatch: ' + k)
        identity, config = load(ROOT / plan['identity']), load(ROOT / plan['config'])
        require(type(config['phase_settings']['run_seed']) is int and config['phase_settings']['run_seed'] == 5562878279179977985, 'Exact u64 seed mismatch')
        require(identity['config'] == config and canonical(config) == identity['config_sha256'] == plan['semantic_config_sha256'] == PINS['semantic'], 'Semantic config mismatch')
        require(config['phase_settings']['budget_seconds'] == 180 and config['probe_devices'] == ['cpu', 'mps'], 'Probe config mismatch')
        lease = verify_lease(plan)
        acceptance_path = ROOT / 'learning/runs/v2-orchestration' / plan['runtime_acceptance']
        require(digest(acceptance_path) == plan['runtime_acceptance_sha256'] == PINS['acceptance'], 'Acceptance hash mismatch')
        accepted = load(acceptance_path)
        require(accepted['status'] == 'accepted_M3_runtime_for_first_bounded_device_probe_only', 'Runtime not accepted for this probe')
        require(accepted['identity_sha256'] == PINS['identity'] and accepted['raw_config_sha256'] == PINS['config']
                and accepted['semantic_config_sha256'] == PINS['semantic'] and accepted['source_pins_rechecked'] == 75, 'Acceptance pins mismatch')
        for field in ('runtime_control_review', 'identity_review'):
            path = Path('learning/runs/v2-orchestration') / accepted[field]
            review = load(ROOT / path)
            require(review['status'] == 'completed' and review['parent_reconciliation']['status'].startswith('accepted_no_findings'), 'Review not parent accepted: ' + field)
            capture(path, 'provenance/' + path.name)
        require(digest(ROOT / accepted['evidence_audit']) == accepted['evidence_audit_sha256'], 'Accepted evidence audit changed')
        manifest_path = ROOT / 'learning/.cache/v2-m3-runtime-review-r3/manifest.json'
        require(digest(manifest_path) == plan['capsule_manifest_sha256'] == PINS['capsule'], 'Reviewed capsule manifest mismatch')
        manifest = load(manifest_path)
        before = source_inventory()
        require(len(before) == len(identity['sources']) == 75 and before == identity['sources'], 'Original 75 source inventory differs')
        capsule_sources = {}
        for name, h in before.items():
            require(manifest['files'].get(name) == h, 'Reviewed source manifest mismatch: ' + name)
            capsule_sources[name] = digest(manifest_path.parent / name)
            require(capsule_sources[name] == h, 'Reviewed source bytes mismatch: ' + name)
            capture(name, 'source-before/' + name)
        foundation = identity['foundation']
        require(digest(foundation['extension_path']) == foundation['extension_sha256'] == PINS['native'], 'Native binary changed')
        binaries = {name: digest(name) for name in foundation['binary_and_receipt_sha256']}
        require(binaries == foundation['binary_and_receipt_sha256'], 'Accepted binary/build receipt changed')
        require(digest(identity['runtime']['interpreter']) == identity['runtime']['interpreter_sha256'], 'Interpreter changed')
        raw, rows = process_table()
        (EVIDENCE / 'process-inventory-before.log').write_text(raw)
        active = [v for v in rows.values() if re.search(r'(?:^|\s)\S*python\S*\s+(?:-B\s+)?-m\s+dodge_rl\.train_teacher\s+', v['command'])]
        save('process-ownership-before.json', dict(wrapper_pid=os.getpid(), wrapper_pgid=os.getpgrp(),
                                                active_teacher_processes=active, owned_supervisor=None, owned_worker=None))
        require(not active, 'Another teacher supervisor/worker exists')
        cutoff = dt.datetime.fromisoformat(plan['cutoff_utc'].replace('Z', '+00:00'))
        remaining = (cutoff - dt.datetime.now(dt.timezone.utc)).total_seconds()
        require(remaining >= 780, 'Full 180 seconds plus 600-second receipt reserve does not fit cutoff')
        for path in (PLAN, STATE, ROOT / plan['config'], ROOT / plan['identity'], acceptance_path, manifest_path, ROOT / accepted['evidence_audit']):
            capture(path, 'provenance/' + path.name)
        save('source-provenance-before.json', dict(at_utc=utc(), source_count=75, sources=before,
             reviewed_capsule_sources=capsule_sources, binary_and_receipt_sha256=binaries,
             exact_run_seed=config['phase_settings']['run_seed'], config_semantic_sha256=canonical(config),
             lease=lease, seconds_to_cutoff=remaining, output_directories_absent_before_wrapper_creation=True))
        require(digest(PLAN) == PINS['plan'] and digest(ROOT / plan['config']) == PINS['config']
                and digest(ROOT / plan['identity']) == PINS['identity'], 'Input changed before launch')
        verify_lease(plan)
        require(source_inventory() == before and not run.exists(), 'Sources/output changed before launch')
        require((cutoff - dt.datetime.now(dt.timezone.utc)).total_seconds() >= 780, 'Launch no longer fits cutoff')
        result['stage'] = 'supervisor_command'
        environment = dict(os.environ, **plan['environment'])
        command = dict(argv=plan['argv'], cwd=plan['cwd'], environment_overrides=plan['environment'],
                       inherited_environment=True, command_shell_rendering=shlex.join(plan['argv']),
                       outer_timeout_seconds=210, started_at_utc=utc(), timed_out=False,
                       wrapper_argv=sys.argv, wrapper_interpreter=sys.executable, wrapper_pid=os.getpid())
        started = time.monotonic()
        with (EVIDENCE / 'supervisor-stdout.log').open('xb') as out, (EVIDENCE / 'supervisor-stderr.log').open('xb') as err:
            proc = subprocess.Popen(plan['argv'], cwd=plan['cwd'], env=environment,
                                    stdout=out, stderr=err, start_new_session=True)
            result['command_launch_count'] = 1
            _, rows = process_table()
            supervisor = rows.get(proc.pid)
            require(supervisor is not None and supervisor['pgid'] == proc.pid, 'Cannot pin owned supervisor group')
            command.update(supervisor_pid=proc.pid, supervisor_pgid=proc.pid, supervisor_identity=supervisor)
            save('command-start.json', command)
            event('command_launched_once', supervisor_pid=proc.pid, supervisor_pgid=proc.pid)
            while proc.poll() is None:
                if time.monotonic() - started >= 210:
                    command['timed_out'] = True
                    event('outer_timeout', elapsed_seconds=time.monotonic() - started)
                    cleanup(proc, supervisor, worker)
                    break
                _, rows = process_table()
                ownership_path = run / 'owned-process.json'
                if worker is None and ownership_path.exists():
                    owner = load(ownership_path)
                    candidate = rows.get(owner['owned_pid'])
                    if candidate is not None:
                        require(owner['owned_pid'] == owner['owned_pgid'] == candidate['pgid']
                                and candidate['ppid'] == proc.pid and 'dodge_rl.train_teacher _worker' in candidate['command']
                                and plan['run_id'] in candidate['command'], 'Worker ownership differs')
                        worker = candidate
                        save('worker-ownership-observed.json', dict(at_utc=utc(), runner_ownership=owner, process=worker))
                event('status_sample', elapsed_seconds=time.monotonic() - started, supervisor_poll=proc.poll(),
                      supervisor=rows.get(proc.pid), worker=None if worker is None else rows.get(worker['pid']),
                      runner_receipts_present={n: (run / n).exists() for n in ('owned-process.json', 'worker-result.json', 'run-result.json')})
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            command.update(supervisor_exit_code=proc.wait(timeout=5), ended_at_utc=utc(),
                           duration_seconds=time.monotonic() - started)
            save('command-terminal.json', command)
        result['supervisor_exit_code'] = command['supervisor_exit_code']
        result['outer_timed_out'] = command['timed_out']
        result['stage'] = 'postflight_evidence'
    except BaseException as error:
        result.update(error=repr(error), traceback=traceback.format_exc())
        event('wrapper_exception', stage=result['stage'], error=repr(error))
        if proc is not None and proc.poll() is None and supervisor is not None:
            try:
                cleanup(proc, supervisor, worker)
            except BaseException as cleanup_error:
                result['cleanup_error'] = repr(cleanup_error)
        if proc is not None:
            result['supervisor_exit_code'] = proc.poll()
            if command is not None and not (EVIDENCE / 'command-terminal.json').exists():
                command.update(supervisor_exit_code=proc.poll(), ended_at_utc=utc(), duration_seconds=time.monotonic() - started)
                save('command-terminal.json', command)
    finally:
        failures = []
        try:
            if identity is not None:
                after = source_inventory()
                save('source-provenance-after.json', dict(at_utc=utc(), sources=after, source_count=len(after),
                     matches_original=after == identity['sources']))
                if after != identity['sources']:
                    failures.append('Original source inventory changed')
                result['source_pins_unchanged'] = after == identity['sources']
                result['source_pin_count'] = len(after)
            if plan is not None:
                for k in ('identity', 'config'):
                    if digest(ROOT / plan[k]) != PINS[k]:
                        failures.append(k + ' hash changed')
                if digest(PLAN) != PINS['plan']:
                    failures.append('Plan hash changed')
                result['final_lease'] = verify_lease(plan)
                run = ROOT / plan['run_dir']
                hashes = {str(p.relative_to(run)): digest(p) for p in sorted(run.rglob('*')) if p.is_file()} if run.exists() else {}
                save('runner-artifacts-observed.json', hashes)
                declared = load(run / 'artifact-sha256.json') if (run / 'artifact-sha256.json').exists() else {}
                mismatches = {n: dict(declared=h, observed=hashes.get(n)) for n, h in declared.items() if hashes.get(n) != h}
                if result['command_launch_count'] and (not declared or mismatches):
                    failures.append('Runner declared artifact manifest missing or mismatched')
                result['runner_artifact_verification'] = dict(observed_files=len(hashes), declared_files=len(declared), mismatches=mismatches)
                rr = load(run / 'run-result.json') if (run / 'run-result.json').exists() else None
                wr = load(run / 'worker-result.json') if (run / 'worker-result.json').exists() else None
                result['runner_status'] = None if rr is None else rr.get('status')
                result['worker_status'] = None if wr is None else wr.get('status')
                result['runner_error'] = None if rr is None else rr.get('error')
                result['worker_error'] = None if wr is None else wr.get('error')
                for label, receipt in (('supervisor', rr), ('worker', wr)):
                    if receipt is not None and (receipt.get('identity_sha256') != PINS['identity'] or receipt.get('config_sha256') != PINS['config']):
                        failures.append(label + ' receipt identity/config mismatch')
                if rr is not None and wr is not None and rr.get('status') == 'passed' and rr.get('worker_result') != wr:
                    failures.append('Supervisor embedded worker result differs')
                if (run / 'identity.json').exists() and load(run / 'identity.json') != identity:
                    failures.append('Runner frozen identity differs')
                if (run / 'registered-config.json').exists() and canonical(load(run / 'registered-config.json')) != PINS['semantic']:
                    failures.append('Runner semantic config differs')
                diagnostics = {n: h for n, h in hashes.items() if n.endswith('.pt') or n.endswith('.partial')}
                if wr is not None:
                    for file_key, hash_key in (('initial_checkpoint', 'initial_checkpoint_sha256'), ('frozen_rollout', 'frozen_rollout_sha256'), ('checkpoint', 'checkpoint_sha256')):
                        if file_key in wr and hashes.get(wr[file_key]) != wr[hash_key]:
                            failures.append('Diagnostic hash differs: ' + file_key)
                    for row in wr.get('measurements', []):
                        if row.get('checkpoint') and hashes.get(row['checkpoint']) != row['checkpoint_sha256']:
                            failures.append('Updated diagnostic checkpoint hash differs: ' + row['device'])
                result['diagnostic_artifacts_sha256'] = diagnostics
                result['actual_measurements'] = [] if wr is None else wr.get('measurements', [])
                result['selected_device'] = None if wr is None else wr.get('selected_device')
                result['frozen_rollout_collection_wall_seconds'] = None if wr is None else wr.get('frozen_rollout_collection_wall_seconds')
                resource_summary = {}
                for name in ('supervisor-resources.jsonl', 'worker-resources.jsonl'):
                    path = run / name
                    series = [json.loads(line, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x))) for line in path.read_text().splitlines()] if path.exists() else []
                    resource_summary[name] = dict(samples=len(series), **{
                        'maximum_' + key: max((row.get(key, 0) for row in series), default=0)
                        for key in ('rss_bytes', 'self_peak_rss_bytes', 'worker_rss_bytes', 'mps_driver_bytes')})
                result['actual_resource_series_maxima'] = resource_summary
                result['memory_accounting'] = 'RSS, self peak RSS, external worker RSS, and MPS driver bytes remain separate; overlapping values are never added.'
                result['guard_limits_bytes'] = dict(RSS=6442450944, MPS_driver=6442450944)
                result['runner_reported_resource_maxima'] = None if wr is None else {k: wr.get(k) for k in ('maximum_observed_RSS_bytes', 'maximum_MPS_driver_bytes')}
                raw, rows = process_table()
                (EVIDENCE / 'process-inventory-after.log').write_text(raw)
                remaining_owned = [rows[p] for p in (None if proc is None else proc.pid, None if worker is None else worker['pid']) if p in rows]
                save('process-ownership-after.json', dict(at_utc=utc(), remaining_owned=remaining_owned,
                     supervisor_reaped=proc is not None and proc.poll() is not None))
                if remaining_owned:
                    failures.append('Owned process remains after command terminal')
                if result.get('supervisor_exit_code') == 0 and not result.get('outer_timed_out') and rr is not None and wr is not None and rr.get('status') == wr.get('status') == 'passed' and not failures and 'error' not in result:
                    result['status'] = 'probe_completed_pending_parent_independent_audit'
                else:
                    result['status'] = 'retained_failure'
        except BaseException as error:
            failures.append('Postflight evidence error: ' + repr(error))
            result['postflight_traceback'] = traceback.format_exc()
        result.update(evidence_verification_failures=failures, finished_at_utc=utc(), wrapper_duration_seconds=time.monotonic() - began)
        save('result.json', result)
        manifest = {str(p.relative_to(EVIDENCE)): digest(p) for p in sorted(EVIDENCE.rglob('*')) if p.is_file() and p != EVIDENCE / 'artifact-sha256.json'}
        save('artifact-sha256.json', manifest)
        print(json.dumps({k: result.get(k) for k in ('status', 'stage', 'command_launch_count', 'supervisor_exit_code', 'runner_status', 'worker_status', 'selected_device', 'error', 'worker_error', 'evidence_verification_failures', 'finished_at_utc')}), flush=True)
    return 0 if result['status'] == 'probe_completed_pending_parent_independent_audit' else 1


if __name__ == '__main__':
    sys.exit(main())
