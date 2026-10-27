"""One-shot stdlib wrapper for the parent's immutable M3 registered D2 curriculum plan."""
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
EVIDENCE = ROOT / 'learning/runs/v2/milestone3-D2-execution-r1'
PLAN = ROOT / 'learning/runs/v2-orchestration/milestone3_D2_curriculum_r1-plan.json'
STATE = ROOT / 'learning/runs/v2-orchestration/state.json'
PINS = {
    'plan': '05a5d54b275ebab0be4719faf40357a4aa5cc09719386adc179257d725c002de',
    'identity': '56dcf1ba848c2e2acdca967ce8ed5bca9457551659421a9070c2f7c5ba2bc14f',
    'config': '2d8eb5626d0debdf5416d0b89610d78ddd56011c3238a82fec72efabe1bd7fe3',
    'semantic': '3cfd4f945ff366aa0fa9b1404e6bfb36cb85af8a97ebf9ac7d3a0d0c91487329',
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
    for k, expected in dict(run_id=plan['run_id'], phase='D2', kind='M3_teacher',
                            authorization='frozen_reviewed_M3_teacher', identity_sha256=PINS['identity'],
                            config_sha256=PINS['config'], plan_sha256=PINS['plan'],
                            output=plan['run_dir'], execution_evidence=plan['execution_evidence'],
                            planned_budget_seconds=1800, receipt_reserve_seconds=600, parent_owned=True).items():
        require(lease.get(k) == expected, 'Lease mismatch: ' + k)
    require(lease.get('parent_terminal_receipt') == plan['parent_terminal_receipt'] and len(lease['parent_terminal_receipt']) == 8, 'Eight-field parent anchor differs')
    return lease


def verify_parent(plan):
    anchor = plan['parent_terminal_receipt']
    expected = {
        'checkpoint_sha256': 'ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f',
        'config_sha256': '624c491ce59881e232ff25750a5a13e312b08bfdea39cc4c86bd17149a19f789',
        'evaluation_sha256': '17b253b9d32e70b875bca8b496348e313568a82b3e8f431fa4a905bf720ccad7',
        'identity_sha256': '7df70937ae7ced6f993277dae2d02f22c6ffee4a0ddfa0fcb26ef8388e6f1e63',
        'phase': 'D1', 'run_id': 'v2-m3-D1-20261024-r1',
        'run_result_sha256': '3475d2b86c935e219c4729a13f448330b2bb2c395617ed07381cb79c00a7aa18',
        'supervisor_exit_code': 0,
    }
    require(anchor == expected, 'Exact eight-field accepted anchor mismatch')
    parent = ROOT / plan['parent_checkpoint']
    audit_path = ROOT / plan['parent_D1_audit']
    require(digest(audit_path) == plan['parent_D1_audit_sha256'] == 'b0816410dbe1e6672ee44f0e339731b9342f932084e5eda13923967b690b3c08', 'Accepted D1 audit differs')
    audit = load(audit_path)
    require(audit['status'] == 'passed' and not audit['findings'] and audit['parent_terminal_receipt'] == anchor, 'D1 audit/anchor not accepted')
    require(load(ROOT / 'learning/runs/v2/milestone3-D2-freeze-r1/accepted-parent-anchor.json') == anchor, 'Frozen accepted anchor differs')
    require(digest(parent) == anchor['checkpoint_sha256'], 'Exact parent checkpoint changed')
    require(digest(parent.parent / 'run-result.json') == anchor['run_result_sha256'], 'Parent terminal receipt changed')
    require(digest(Path(str(parent) + '.evaluation.json')) == anchor['evaluation_sha256'], 'Parent evaluation changed')
    parent_identity = ROOT / 'learning/runs/v2/milestone3-D1-freeze-r1/D1-frozen-identity.json'
    parent_config = ROOT / 'learning/runs/v2/milestone3-D1-freeze-r1/D1-config.json'
    require(digest(parent_identity) == anchor['identity_sha256'] and digest(parent_config) == anchor['config_sha256'], 'Parent raw source identity/config changed')
    rr = load(parent.parent / 'run-result.json')
    wr = load(parent.parent / 'worker-result.json')
    require(rr['status'] == wr['status'] == 'passed' and rr['worker_exit_code'] == 0 and rr['worker_result'] == wr, 'Parent terminal worker differs')
    for name in ('run_id', 'phase', 'identity_sha256', 'config_sha256'):
        require(rr[name] == anchor[name], 'Parent terminal field changed: ' + name)
    require(wr['checkpoint'] == parent.name and wr['checkpoint_sha256'] == anchor['checkpoint_sha256'], 'Parent is not exact terminal checkpoint')
    proof = load(Path(str(parent) + '.evaluation.json'))
    require(proof == wr['evaluation'] and proof['complete'] is True and proof['passed'] is True, 'Parent complete successful evaluation differs')
    source_command = ROOT / 'learning/runs/v2/milestone3-D1-execution-r1/command-terminal.json'
    require(load(source_command)['supervisor_exit_code'] == anchor['supervisor_exit_code'] == 0, 'Observed parent supervisor exit differs')
    require(load(parent.parent / 'identity.json') == load(parent_identity) and load(parent.parent / 'registered-config.json') == load(parent_config), 'Parent copied semantic identity/config differs')
    declared = load(parent.parent / 'artifact-sha256.json')
    parent_files = {str(p): digest(p) for p in sorted(parent.parent.rglob('*')) if p.is_file()}
    require(all(parent_files.get(str(parent.parent / name)) == h for name, h in declared.items()), 'Parent declared artifacts changed')
    extra = [audit_path, parent_identity, parent_config, source_command,
             ROOT / 'learning/runs/v2/milestone3-D2-freeze-r1/accepted-parent-anchor.json',
             ROOT / 'learning/runs/v2/milestone3-D2-freeze-r1/transition-validation-receipt.json',
             ROOT / 'learning/runs/v2/milestone3-D2-freeze-r1/validate-transition.py']
    transition = load(ROOT / 'learning/runs/v2/milestone3-D2-freeze-r1/transition-validation-receipt.json')
    require(transition['exit_status'] == 0, 'Actual read-only transition validation failed')
    require(digest(ROOT / 'learning/runs/v2/milestone3-D2-freeze-r1/transition-validation.log') == transition['log_sha256'], 'Transition validation log changed')
    for name in ('transition-validation.log', 'preparation-result.json', 'preparation-plan.json', 'freeze-receipt.json', 'config-receipt.json'):
        extra.append(ROOT / 'learning/runs/v2/milestone3-D2-freeze-r1' / name)
    return {'anchor': anchor, 'files': {**parent_files, **{str(p): digest(p) for p in extra}}}


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
        signal_exact(proc.pid, supervisor, signal.SIGKILL, 'supervisor_after_bounded_cleanup')
    proc.wait(timeout=5)


def main():
    began = time.monotonic()
    result = dict(run_id='v2-m3-D2-20261024-r1', task_first_utc='2026-10-24T12:12:18Z',
                  wrapper_started_at_utc=utc(), status='failed', stage='preflight', command_launch_count=0,
                  automatic_retries=0, limits_relaxed=False, parent_independent_acceptance_pending=True,
                  training_qualification=False, registered_curriculum_transition=True, same_phase_resume=False,
                  B_E_opened=False, pins=PINS)
    plan = identity = proc = supervisor = worker = None
    command = None
    try:
        require(set(p.name for p in EVIDENCE.iterdir()) == {'execute_once.py', 'wrapper-adaptation.json'}, 'Execution directory already contains receipts; refusing repeat')
        require(digest(PLAN) == PINS['plan'], 'Immutable plan hash mismatch')
        plan = load(PLAN)
        run = ROOT / plan['run_dir']
        require(not run.exists(), 'Runner directory exists; refusing repeat')
        require(plan['cwd'] == str(ROOT) and Path.cwd() == ROOT, 'Cwd mismatch')
        require(plan['environment'] == {'PYTHONPATH': 'python', 'PYTHONDONTWRITEBYTECODE': '1'}, 'Environment mismatch')
        require(plan['argv'] == [str(ROOT / 'python/.venv/bin/python'), '-B', '-m', 'dodge_rl.train_teacher', 'stage', '--stage', 'D2',
                                '--config', str(ROOT / plan['config']), '--identity', str(ROOT / plan['identity']),
                                '--run-dir', str(run), '--run-id', result['run_id'], '--parent-checkpoint', str(ROOT / plan['parent_checkpoint'])], 'Plan argv mismatch')
        require(plan['run_id'] == result['run_id'] and plan['phase'] == 'D2', 'Plan run/phase mismatch')
        require(plan['planned_budget_seconds'] == 1800 and plan['receipt_reserve_seconds'] == 600
                and plan['outer_process_timeout_seconds'] == 1830, 'Plan time limits mismatch')
        require(plan['RSS_limit_bytes'] == plan['MPS_driver_limit_bytes'] == 6442450944, 'Plan resource limits mismatch')
        for k in ('identity', 'config'):
            require(plan[k + '_sha256'] == PINS[k] and digest(ROOT / plan[k]) == PINS[k], 'Input hash mismatch: ' + k)
        identity, config = load(ROOT / plan['identity']), load(ROOT / plan['config'])
        require(type(config['phase_settings']['run_seed']) is int and config['phase_settings']['run_seed'] == 5562881586070242562, 'Exact u64 seed mismatch')
        require(identity['config'] == config and canonical(config) == identity['config_sha256'] == plan['semantic_config_sha256'] == PINS['semantic'], 'Semantic config mismatch')
        require(config['phase_settings'] == {'budget_seconds': 1800, 'difficulty': 2, 'initialization': 'transition_from_successful_D1', 'patterns_enabled': True, 'run_seed': 5562881586070242562}, 'D2 phase settings mismatch')
        require(config['phase'] == 'D2' and config['device'] == 'mps' and config['probe_devices'] == [] and config['powerups_enabled'] is True, 'D2 config mismatch')
        require(config['parent_checkpoint_sha256'] == plan['parent_checkpoint_sha256'] == 'ce9c03c8d476f58d5edec9f95946fa808d1d65890728528f9a44993eb0f0544f', 'Parent checkpoint pin mismatch')
        require(plan['same_phase_resume'] is False and plan['progress_gate'] == {'mean_score_at_least': 50, 'mean_alive_frames_at_least': 3060, 'development_seeds': 64, 'raw_frame_cap': 18000, 'at_entry': True, 'every_completed_updates': 16, 'end_immediately_on_pass': True}, 'Registered transition/gate mismatch')
        parent_provenance = verify_parent(plan)
        save('parent-provenance-before.json', parent_provenance)
        for parent_file in parent_provenance['files']:
            if not parent_file.endswith('.pt'):
                capture(parent_file, 'provenance/parent/' + str(Path(parent_file).relative_to(ROOT / 'learning/runs/v2')))

        lease = verify_lease(plan)
        acceptance_path = ROOT / 'learning/runs/v2-orchestration/milestone3-runtime-acceptance-r3.json'
        require(digest(acceptance_path) == PINS['acceptance'], 'Acceptance hash mismatch')
        accepted = load(acceptance_path)
        require(accepted['status'] == 'accepted_M3_runtime_for_first_bounded_device_probe_only', 'Runtime not accepted for this probe')
        require(accepted['source_pins_rechecked'] == 75, 'Runtime acceptance source count mismatch')
        probe_audit_path = ROOT / 'learning/runs/v2/milestone3-probe-parent-audit-r1/audit.json'
        require(digest(probe_audit_path) == '215f9c7b57109a5d293c6cfa8e520b5f76e68156cda8a93a8808a36e39641ee7', 'Probe audit hash mismatch')
        probe_audit = load(probe_audit_path)
        require(probe_audit['status'] == 'passed' and not probe_audit['findings'] and probe_audit['verified']['selected_device'] == 'mps', 'Probe not accepted for MPS')
        capture(probe_audit_path, 'provenance/probe-acceptance-audit.json')
        for field in ('runtime_control_review', 'identity_review'):
            path = Path('learning/runs/v2-orchestration') / accepted[field]
            review = load(ROOT / path)
            require(review['status'] == 'completed' and review['parent_reconciliation']['status'].startswith('accepted_no_findings'), 'Review not parent accepted: ' + field)
            capture(path, 'provenance/' + path.name)
        require(digest(ROOT / accepted['evidence_audit']) == accepted['evidence_audit_sha256'], 'Accepted evidence audit changed')
        manifest_path = ROOT / 'learning/.cache/v2-m3-runtime-review-r3/manifest.json'
        require(digest(manifest_path) == PINS['capsule'], 'Reviewed capsule manifest mismatch')
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
        require(remaining >= 2400, 'Full 1800 seconds plus 600-second receipt reserve does not fit cutoff')
        for path in (PLAN, STATE, ROOT / plan['config'], ROOT / plan['identity'], acceptance_path, manifest_path, ROOT / accepted['evidence_audit']):
            capture(path, 'provenance/' + path.name)
        save('source-provenance-before.json', dict(at_utc=utc(), source_count=75, sources=before,
             reviewed_capsule_sources=capsule_sources, binary_and_receipt_sha256=binaries,
             exact_run_seed=config['phase_settings']['run_seed'], config_semantic_sha256=canonical(config),
             lease=lease, seconds_to_cutoff=remaining, output_directories_absent_before_wrapper_creation=load(EVIDENCE / 'wrapper-adaptation.json')['output_directories_absent_before_creation']))
        require(digest(PLAN) == PINS['plan'] and digest(ROOT / plan['config']) == PINS['config']
                and digest(ROOT / plan['identity']) == PINS['identity'], 'Input changed before launch')
        verify_lease(plan)
        require(verify_parent(plan) == parent_provenance, 'Parent changed before launch')
        require(source_inventory() == before and not run.exists(), 'Sources/output changed before launch')
        require((cutoff - dt.datetime.now(dt.timezone.utc)).total_seconds() >= 2400, 'Launch no longer fits cutoff')
        result['stage'] = 'supervisor_command'
        environment = dict(os.environ, **plan['environment'])
        command = dict(argv=plan['argv'], cwd=plan['cwd'], environment_overrides=plan['environment'],
                       inherited_environment=True, command_shell_rendering=shlex.join(plan['argv']),
                       outer_timeout_seconds=1830, started_at_utc=utc(), timed_out=False,
                       seconds_to_cutoff_at_launch=(cutoff - dt.datetime.now(dt.timezone.utc)).total_seconds(),
                       wrapper_argv=sys.argv, wrapper_interpreter=sys.executable, wrapper_pid=os.getpid(), wrapper_source_sha256=digest(Path(__file__)))
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
                if time.monotonic() - started >= 1830:
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
                parent_after = verify_parent(plan)
                save('parent-provenance-after.json', parent_after)
                require(parent_after == load(EVIDENCE / 'parent-provenance-before.json'), 'Parent provenance changed')
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
                result['terminal_D2_evaluation'] = None if wr is None else wr.get('evaluation')
                result['completed_update_counters'] = None if wr is None else wr.get('counters')
                result['consumed_phase_wall_seconds'] = None if rr is None else rr.get('consumed_phase_wall_seconds')
                result['registered_criterion'] = plan['progress_gate']
                result['actual_measurements'] = [] if wr is None else wr.get('measurements', [])
                result['selected_device'] = config['device']
                result['frozen_rollout_collection_wall_seconds'] = None if wr is None else wr.get('frozen_rollout_collection_wall_seconds')
                resource_summary = {}
                for name in ('supervisor-resources.jsonl', 'worker-resources.jsonl'):
                    path = run / name
                    series = [json.loads(line, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x))) for line in path.read_text().splitlines()] if path.exists() else []
                    resource_summary[name] = dict(samples=len(series), **{
                        'maximum_' + key: max((row.get(key, 0) for row in series), default=0)
                        for key in ('rss_bytes', 'self_peak_rss_bytes', 'worker_rss_bytes', 'mps_driver_bytes')})
                save('resource-summary.json', resource_summary)
                result['actual_resource_series_maxima'] = resource_summary
                result['memory_accounting'] = 'RSS, self peak RSS, external worker RSS, and MPS driver bytes remain separate; overlapping values are never added.'
                result['guard_limits_bytes'] = dict(RSS=6442450944, MPS_driver=6442450944)
                result['runner_reported_resource_maxima'] = None if wr is None else {k: wr.get(k) for k in ('maximum_observed_RSS_bytes', 'maximum_MPS_driver_bytes')}
                raw, rows = process_table()
                (EVIDENCE / 'process-inventory-after.log').write_text(raw)
                remaining_owned = [v for p, v in rows.items() if p in (None if proc is None else proc.pid, None if worker is None else worker['pid']) or ('dodge_rl.train_teacher' in v['command'] and plan['run_id'] in v['command'])]
                save('process-ownership-after.json', dict(at_utc=utc(), remaining_owned=remaining_owned,
                     supervisor_reaped=proc is not None and proc.poll() is not None))
                if remaining_owned:
                    failures.append('Owned process remains after command terminal')
                if result.get('supervisor_exit_code') == 0 and not result.get('outer_timed_out') and rr is not None and wr is not None and rr.get('status') == wr.get('status') == 'passed' and not failures and 'error' not in result:
                    result['status'] = 'D2_completed_pending_parent_independent_audit'
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
    return 0 if result['status'] == 'D2_completed_pending_parent_independent_audit' else 1


if __name__ == '__main__':
    sys.exit(main())
