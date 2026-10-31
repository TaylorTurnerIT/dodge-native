"""Coordinator-owned single A100 compatibility assignment, never a trainer.

The reviewed registration, sole allocation claim and exact shared lease are
required before assignment. SDK responses containing proxy credentials never
enter durable public evidence. The old failed capsule remains read-only.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import signal
import subprocess
import sys
import tarfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / 'learning/runs/v2/teacher-cloud-parent-20261031-r1'
FAILED = Path('/Users/taylor/.t3/worktrees/dodge-native/t3-teacher-ray-geometry-20261030/learning/runs/v2/teacher-ray-screen-20261030-r4')
FAILED_SHA = '1881aad8554a0841246248c2cb0e6ae49dc425716f924b6824b440eeaa53a94e'
BASE = Path(__file__).with_name('coordinator_dispatch_v2.py')
BASE_SHA = '77655f4e200ccce33950cd53201ef509394f8bff81e92fdd208c52668890fa16'
if hashlib.sha256(BASE.read_bytes()).hexdigest() != BASE_SHA:
    raise ValueError('Immutable receipt/lease dependency differs')
_spec = importlib.util.spec_from_file_location('cloud_receipt_dependency', BASE)
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
need, read, sha, save = _base.need, _base.read, _base.sha, _base.save


class Clock:
    """Wall time counts suspend; monotonic time resists backwards clock edits."""
    def __init__(self):
        self.wall = time.time(); self.monotonic = time.monotonic(); self.last = 0.0

    def now(self):
        self.last = max(self.last, time.time() - self.wall, time.monotonic() - self.monotonic)
        return self.last


def load_module(path, digest, name):
    need(sha(path) == digest, 'Imported source hash differs')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def failed056_disposition():
    regpath = FAILED / 'registration-r4.json'
    need(sha(regpath) == FAILED_SHA, 'Failed056 registration changed')
    reg = read(regpath)
    for path, digest in {**reg['source_pins'], **reg['input_pins']}.items():
        need(sha(path) == digest, 'Failed056 pin changed')
    parent = read(FAILED / 'first-failure.json')
    child = read(FAILED / 'outputs/r2-rays/first-failure.json')
    exit_receipt = read(FAILED / 'outputs/r2-rays/exit.json')
    need(parent['status'] == child['status'] == 'first_failure_preserved_lease_held'
         and child['error'] == "ValueError('Counted prefix forecast exceeds work cap; no resize/retry')"
         and child['observed_gameplay_frames'] == 131072, 'Failed056 incident differs')
    need(exit_receipt['raw_exit_code'] == exit_receipt['observed_exit_code'] == 1
         and exit_receipt['directly_reaped'] and exit_receipt['group_absent'],
         'Failed056 child not reaped')
    evidence = []; groups = {read(FAILED / 'launch.claimed')['pid'], exit_receipt['pgid']}
    for job in ['r1-control', 'r1-rays']:
        out = FAILED / 'outputs' / job
        audit = read(out / 'parent-job-audit.json'); e = audit['evidence']
        need(audit['status'] == 'accepted_training_trajectory'
             and audit['registration_sha256'] == FAILED_SHA
             and e['counts']['frames'] == 2359296 and e['counts']['updates'] == 36,
             'Completed056 child receipt differs')
        for filename, key in [('result.json', 'result_sha256'), ('exit.json', 'exit_sha256'),
                              ('prefix-qualification.json', 'prefix_sha256')]:
            need(sha(out / filename) == e[key], 'Completed056 artifact changed')
        need(sha(e['final_checkpoint']['path']) == e['final_checkpoint']['sha256'],
             'Completed056 checkpoint changed')
        evidence.append(e); groups.add(read(out / 'exit.json')['pgid'])
    need(parent['completed_jobs'] == evidence, 'Failed056 completed-child inventory differs')
    need(not (FAILED / 'parent-terminal-audit.json').exists()
         and not (FAILED / 'lease-release.json').exists(), 'Failed056 unexpectedly accepted/released')
    need(not (FAILED / 'outputs/r2-control/worker.claimed').exists(), 'Last056 job was claimed')
    cache = FAILED / 'empty-pycache'
    need(cache.is_dir() and not list(cache.iterdir()), 'Failed056 cache changed')
    rows = subprocess.check_output(['/bin/ps', '-axo', 'pid=,pgid='], text=True, timeout=5)
    need(not any(len(s.split()) == 2 and int(s.split()[1]) in groups for s in rows.splitlines()),
         'Failed056 group remains')
    return dict(status='acknowledged_failed_campaign', record='DODGE-056', campaign_success=False,
        registration_sha256=FAILED_SHA, exact_lease=reg['expected_lease'], state_path=reg['state_path'],
        original_pins_unchanged=True, owned_groups_absent=True,
        first_failure_sha256=sha(FAILED / 'first-failure.json'),
        child_failure_sha256=sha(FAILED / 'outputs/r2-rays/first-failure.json'),
        child_exit_sha256=sha(FAILED / 'outputs/r2-rays/exit.json'))


def validate_plan(plan, *, cleanup=False):
    for kind in ['registration', 'review', 'authority']:
        need(sha(plan[kind + '_path']) == plan[kind + '_sha256'], 'Plan binding differs')
    reg, review, authority = (read(plan[k + '_path']) for k in ['registration', 'review', 'authority'])
    need(reg['record'] == 'DODGE-057' and reg['schema'] == 'dodge_colab_synthetic_registration_v1',
         'Wrong cloud stage')
    need(review['status'] == 'no_blocking_findings'
         and review['registration_sha256'] == plan['registration_sha256'], 'Independent exact review absent')
    for path in [Path(__file__).resolve(), BASE.resolve()]:
        need(review['coordinator_source_pins'].get(str(path)) == sha(path), 'Controller not reviewed')
    need(Path(plan['authority_path']).resolve() == (PARENT / 'authority-r2.json').resolve()
         and authority['record'] == 'DODGE-057' and authority['allocation_attempts_authorized'] == 1
         and authority['limits']['maximum_total_assigned_seconds'] == 900
         and authority['limits']['maximum_existing_compute_units'] == 8.0
         and authority['remote_training_authorized_by_this_document'] is False,
         'Compatibility authority differs')
    need(reg['authority_path'] == plan['authority_path']
         and reg['authority_sha256'] == plan['authority_sha256']
         and reg['expected_lease'] == authority['expected_lease'], 'Authority/lease binding differs')
    need(reg['native_games'] == reg['training_frames'] == 0
         and reg['trained_weights_saved'] is False and reg['accelerator'] == 'A100',
         'Synthetic-only scope differs')
    # An unrelated frozen input/cache fault must not prevent exact owned teardown.
    # Cleanup still requires the pinned plan, registration, review and controller.
    if cleanup:
        return reg
    for path in set(reg['source_pins']) & set(reg['input_pins']):
        need(reg['source_pins'][path] == reg['input_pins'][path], 'Conflicting registered pins')
    for path, digest in {**reg['source_pins'], **reg['input_pins']}.items():
        need(sha(path) == digest, 'Registered source/input changed')
    need(reg['source_pins'].get(str(Path(__file__).resolve())) == sha(__file__)
         and reg['source_pins'].get(str(BASE.resolve())) == BASE_SHA,
         'Controller/base source not registered')
    for path in [reg['cli_path'], reg['sdk_python']]:
        need(reg['input_pins'].get(path) == sha(path), 'CLI/interpreter not input-pinned')
    cache = Path(reg['empty_pycache'])
    need(cache.is_dir() and not list(cache.iterdir()), 'Existing empty cache required')
    config = Path(reg['cli_config_path'])
    if config.exists():
        need(isinstance(read(config), dict), 'Private CLI session store malformed')
    need(reg['cli_path'] == '/tmp/dodge-colab-cli-20261031-venv/bin/colab'
         and sha(reg['cli_path']) == '497f3313e1a1adaaeaf9df0a0ff1d61c1463cd2ce81782b03ca5e658ac60ada1',
         'Official CLI binding differs')
    for asset in reg['uploads']:
        remote = PurePosixPath(asset['remote'])
        need(remote.is_absolute() and remote.parent == PurePosixPath('/content')
             and sha(asset['local']) == asset['sha256']
             and reg['input_pins'].get(asset['local']) == asset['sha256'], 'Upload manifest differs')
    need(len(reg['uploads']) == 2 and {a['remote'] for a in reg['uploads']} == {
        '/content/dodge-ray057-payload.tar', '/content/checkpoint-global-420.pt'}, 'Unexpected upload')
    checkpoint = next(a for a in reg['uploads'] if a['remote'] == '/content/checkpoint-global-420.pt')
    payload = next(a for a in reg['uploads'] if a['remote'] == '/content/dodge-ray057-payload.tar')
    need(checkpoint['sha256'] == '7e0de8640f1337261412d91cde6bc692772ff212fbd360f5aad415dc6bc7ed4b'
         and payload['sha256'] == reg['payload_sha256'], 'Original420/payload binding differs')
    need(sha(reg['exec_script']) == reg['exec_script_sha256'], 'Launcher changed')
    need(reg['download_remote'] == '/content/dodge-ray057-receipts.tar', 'Unexpected download')
    need(reg['source_pins'].get(reg['billing_guard_path']) == reg['billing_guard_sha256']
         and reg['source_pins'].get(reg['exec_script']) == reg['exec_script_sha256'],
         'Billing guard/launcher not registered')
    need(reg['state_path'] == authority['state_path'] and reg['limits'] == authority['limits'],
         'State/limits differ from authority')
    for kind in ['CPU_420_receipt', 'owner_freeze']:
        need(reg['input_pins'].get(reg[kind + '_path']) == reg[kind + '_sha256'],
             'Required readiness input not registered')
    return reg


def validate_receipts(path, nonce, payload_sha, reg=None):
    """Read JSON members without extracting links, paths, or tensor files."""
    needed = {'bootstrap-result.json', 'CUDA-compatibility.json', 'watchdog.json'}
    docs = {}
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        need(len(members) <= 32 and sum(m.size for m in members) <= 4 * 1024 * 1024,
             'Receipt archive too large')
        for member in members:
            name = PurePosixPath(member.name)
            need(not name.is_absolute() and '..' not in name.parts and member.isfile()
                 and name.suffix == '.json' and member.name not in docs, 'Unsafe receipt member')
            docs[member.name] = json.loads(archive.extractfile(member).read())
    need(needed <= set(docs), 'Required receipt missing')
    need(not any('failure' in name for name in docs), 'Failure receipt present')
    schemas = {'bootstrap-result.json': 'dodge_colab_synthetic_receipt_bundle_v1',
               'CUDA-compatibility.json': 'dodge_colab_synthetic_compatibility_result_v1',
               'watchdog.json': 'dodge_colab_synthetic_watchdog_result_v1'}
    for name in needed:
        doc = docs[name]
        need(doc['schema'] == schemas[name] and doc['record'] == 'DODGE-057'
             and doc['job_nonce'] == nonce and doc['payload_sha256'] == payload_sha,
             'Receipt identity differs')
        need(doc['native_games'] == doc['training_frames'] == 0
             and doc['trained_weights_saved'] is False, 'Receipt exceeds synthetic scope')
    need(docs['watchdog.json']['owned_group_absent'] is True, 'Remote group not absent')
    need(docs['bootstrap-result.json']['status'] == 'complete'
         and docs['watchdog.json']['status'] == 'complete'
         and docs['watchdog.json']['child_returncode'] == 0
         and docs['CUDA-compatibility.json']['status'] == 'synthetic_420_migration_passed',
         'Synthetic receipt reports failure')
    result, watchdog = docs['CUDA-compatibility.json'], docs['watchdog.json']
    need(result['device'] == watchdog['device'] == 'cuda' and 'A100' in result['GPU']
         and result['same_device_zero_gate_exact'] is True
         and result['synthetic_optimizer_steps'] == 1
         and result['CPU_device_numeric_tolerance'] == {'atol': 2e-5, 'rtol': 2e-5},
         'CUDA fixture/device contract differs')
    for key in ['peak_RSS_bytes', 'accelerator_peak_reserved_bytes', 'accelerator_peak_allocated_bytes']:
        need(type(result[key]) is int and 0 < result[key] < 6 * 2**30, 'CUDA fixture memory limit differs')
    for key in ['peak_group_RSS_bytes', 'peak_sampled_CUDA_driver_process_bytes']:
        need(type(watchdog[key]) is int and 0 < watchdog[key] < 6 * 2**30,
             'Watchdog memory limit differs')
    if reg is not None:
        cpu = read(reg['CPU_420_receipt_path'])
        need(result['platform'] == 'linux' and result['checkpoint_sha256'] ==
             '7e0de8640f1337261412d91cde6bc692772ff212fbd360f5aad415dc6bc7ed4b'
             and result['source_model_fingerprint'] == cpu['source_model_fingerprint']
             and result['source_Adam_fingerprint'] == cpu['source_Adam_fingerprint']
             and result['migration'] == cpu['migration']
             and result['seed_pool_opened'] is result['heldout_opened'] is
                 result['simulator_restored'] is False,
             'Remote migration/scope receipt differs')
        expected_origins = cpu['runtime_origins']
        need(set(result['runtime_origins']) == set(expected_origins), 'Remote runtime origin set differs')
        for name, origin in result['runtime_origins'].items():
            relative = PurePosixPath(origin['path']).relative_to(PurePosixPath(reg['remote_root']) / 'source')
            local = str(Path(reg['source_root']) / str(relative))
            need(reg['source_pins'].get(local) == origin['sha256'] == expected_origins[name]['sha256'],
                 'Remote runtime source hash differs')
        provenance = docs['CUDA-compatibility.json.runtime-provenance.json']
        need(provenance['record'] == 'DODGE-057' and provenance['job_nonce'] == nonce
             and provenance['package_origins'] == result['package_origins'],
             'Remote pre-work provenance differs')
        need(set(result['package_origins']) == {'python', 'torch_python', 'torch_native',
             'numpy_python', 'numpy_native'}, 'Remote package provenance incomplete')
        for origin in result['package_origins'].values():
            need(PurePosixPath(origin['path']).is_absolute() and len(origin['sha256']) == 64
                 and all(x in '0123456789abcdef' for x in origin['sha256']),
                 'Remote package fingerprint malformed')
        for key in ['torch', 'numpy', 'python', 'cuda_runtime']:
            need(isinstance(result[key], str) and result[key] and provenance[key] == result[key],
                 'Remote version provenance differs')
    return docs


class Controller:
    def __init__(self, reg, plan, output, transport, guard_class, clock=None, sleeper=time.sleep):
        self.reg, self.plan, self.output = reg, plan, Path(output)
        self.transport, self.guard_class = transport, guard_class
        self.clock, self.sleep = clock or Clock(), sleeper
        self.nonce = None; self.endpoint = None; self.process = None
        self.phase = 'preflight'; self.guard_reason = None; self.allocation_called = False

    def lease_guard(self):
        need(read(self.reg['state_path']).get('active_long_campaign') == self.reg['expected_lease'],
             'Exact cloud lease absent/lost')
        need(not (self.output / 'cancel.requested').exists(), 'Coordinator cancellation requested')

    def snapshot(self):
        started = self.clock.now()
        value = self.transport.snapshot(timeout=15)
        return value, started, self.clock.now()

    def metered(self, fixtures_started=False):
        self.lease_guard()
        snapshot, start, end = self.snapshot()
        try:
            result = self.guard.observe(snapshot['raw'], snapshot['assignments'], self.endpoint,
                end, request_started=start, fixtures_started=fixtures_started)
        except ValueError as error:
            self.guard_reason = str(error)  # Pinned pure guard emits fixed safe reasons only.
            raise
        with (self.output / 'billing.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(observed_at=end, **result), allow_nan=False) + '\n')
            stream.flush(); os.fsync(stream.fileno())
        return result

    def run(self, disposition):
        snapshot, _, _ = self.snapshot()
        raw = snapshot['raw']
        need(raw['assignmentsCount'] == 0 and not snapshot['assignments']
             and snapshot.get('session') is None, 'Pre-existing assignment/session prevents allocation')
        need(type(raw['currentBalance']) in (int, float) and math.isfinite(raw['currentBalance'])
             and raw['currentBalance'] >= 8, 'Existing CU balance insufficient')
        need(self.output.parent.resolve() == PARENT.resolve() and not self.output.is_symlink()
             and self.output.resolve().parent == PARENT.resolve(), 'Output must be a real coordinator child')
        self.output.mkdir()
        need(not self.output.is_symlink() and self.output.resolve().parent == PARENT.resolve(),
             'Output changed while creating coordinator directory')
        self.nonce = str(uuid.uuid4())
        save(self.output / 'dispatch.claimed', dict(record='DODGE-057', notebook_hash=self.nonce,
            registration_sha256=self.plan['registration_sha256'],
            review_sha256=self.plan['review_sha256'], expected_lease=self.reg['expected_lease']))
        failure = None; cleanup = None; receipts = None
        try:
            self.phase = 'handoff'
            failure_sha = save(self.output / 'failure-disposition.json', disposition)
            _base.exact_handoff(disposition['state_path'], disposition['exact_lease'], self.reg['expected_lease'])
            save(self.output / 'lease-handoff.json', dict(status='exact_non_null_failed_campaign_handoff',
                previous_lease=disposition['exact_lease'], replacement_lease=self.reg['expected_lease'],
                failure_disposition_sha256=failure_sha,
                registration_sha256=self.plan['registration_sha256'],
                review_sha256=self.plan['review_sha256'], never_cleared_to_null=True))
            self.lease_guard()
            self.phase = 'allocation'
            allocation_start = self.clock.now()
            self.guard = self.guard_class(raw['currentBalance'], allocation_start)
            save(self.output / 'allocation.claimed', dict(notebook_hash=self.nonce,
                 session_name=self.reg['session_name'], started_at=allocation_start))
            self.allocation_called = True
            owned = self.transport.allocate(self.nonce, self.output, timeout=45)
            need(owned['name'] == self.reg['session_name'] and owned['accelerator'] == 'A100'
                 and owned['notebook_hash'] == self.nonce, 'Allocation ownership differs')
            self.endpoint = owned['endpoint']
            self.phase = 'discovery'
            while not self.metered()['fixtures_admitted']:
                self.sleep(15)
            self.phase = 'upload'
            for asset in self.reg['uploads']:
                self.metered()
                self.transport.upload(asset['local'], asset['remote'], timeout=15)
            self.metered()
            self.phase = 'exec'
            execution_started = self.clock.now()
            self.process = self.transport.start(self.nonce, timeout=360)
            while self.transport.poll(self.process) is None:
                need(self.clock.now() - execution_started < 360, 'Local exec deadline reached')
                self.phase = 'billing'
                self.metered(fixtures_started=True)
                need(self.clock.now() - execution_started < 360, 'Local exec deadline reached')
                self.sleep(15)
            execution_code = self.transport.poll(self.process)
            self.phase = 'retrieval'
            self.metered(fixtures_started=True)
            receipt_path = self.output / 'receipts.tar'
            self.transport.download(self.reg['download_remote'], receipt_path, timeout=15)
            receipts = validate_receipts(receipt_path, self.nonce, self.reg['payload_sha256'], self.reg)
            need(execution_code == 0, 'Remote fixture execution failed')
        except BaseException as error:
            failure = dict(status='first_failure_preserved_lease_held', phase=self.phase,
                exception_type=type(error).__name__, billing_guard_reason=self.guard_reason,
                allocation_called=self.allocation_called, endpoint_known=self.endpoint is not None)
        finally:
            self.phase = 'teardown'
            if self.process is not None:
                try:
                    self.transport.stop_local(self.process)
                except BaseException:
                    failure = failure or dict(status='first_failure_preserved_lease_held',
                                              phase='local_client_cleanup')
            # The SDK child persists redacted ownership before saving secret session state.
            owned_path = self.output / 'owned-endpoint.json'
            if self.endpoint is None and owned_path.exists():
                try:
                    owned = read(owned_path)
                    if owned['notebook_hash'] == self.nonce and owned['name'] == self.reg['session_name']:
                        self.endpoint = owned['endpoint']
                except BaseException:
                    failure = failure or dict(status='first_failure_preserved_lease_held',
                                              phase='ownership_receipt')
            if self.endpoint is not None:
                try:
                    if self.process is not None and not (self.output / 'receipts.tar').exists():
                        try:
                            self.transport.download(self.reg['download_remote'],
                                                    self.output / 'receipts.tar', timeout=15)
                        except BaseException:
                            pass  # Retrieval failure never prevents exact endpoint teardown.
                    self.transport.unassign(self.endpoint, self.output, timeout=40)
                    final, started, end = self.snapshot()
                    need(end - started <= 15, 'Final absence request exceeded bound')
                    need(not any(a['endpoint'] == self.endpoint for a in final['assignments']),
                         'Owned assignment remains after unassign')
                    balance = final['raw']['currentBalance']
                    need(type(balance) in (int, float) and math.isfinite(balance), 'Final balance unavailable')
                    debit = raw['currentBalance'] - balance
                    budget_ok = 0 <= debit <= 8 and self.clock.now() - allocation_start <= 900
                    cleanup = dict(status='owned_assignment_absent', endpoint=self.endpoint,
                        final_observed_balance_CU=balance, observed_debit_CU=debit,
                        elapsed_assigned_seconds_upper_bound=self.clock.now() - allocation_start,
                        budget_within_limits=budget_ok,
                        billing_meter_has_no_server_timestamp=True)
                    save(self.output / 'teardown.json', cleanup)
                    if not budget_ok:
                        failure = failure or dict(status='first_failure_preserved_lease_held',
                                                  phase='final_budget')
                except BaseException as error:
                    cleanup = dict(status='teardown_unconfirmed', exception_type=type(error).__name__)
            elif self.allocation_called:
                cleanup = dict(status='allocation_outcome_ambiguous_no_unowned_stop', notebook_hash=self.nonce)
            if cleanup is not None and cleanup['status'] != 'owned_assignment_absent':
                save(self.output / 'cleanup-first-failure.json', cleanup)
                failure = failure or dict(status='first_failure_preserved_lease_held', phase='teardown')
        if failure is not None:
            save(self.output / 'first-failure.json', failure)
            raise ValueError('Compatibility attempt failed; preserve exact lease and first evidence')
        need(receipts is not None and cleanup and cleanup['status'] == 'owned_assignment_absent',
             'Compatibility terminal evidence incomplete')
        return dict(status='compatibility_complete_pending_coordinator_acceptance',
            record='DODGE-057', job_nonce=self.nonce, registration_sha256=self.plan['registration_sha256'],
            receipt_archive_sha256=sha(self.output / 'receipts.tar'),
            teardown_sha256=sha(self.output / 'teardown.json'), lease_released=False)


class SDKTransport:
    """Bounded official CLI operations plus redacted official SDK queries."""
    def __init__(self, plan_path, plan_sha, reg, output):
        self.plan_path, self.plan_sha, self.reg = str(plan_path), plan_sha, reg
        self.output = Path(output)
        self.prefix = [reg['cli_path'], '--auth', 'oauth2', '--config', reg['cli_config_path']]
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
            COLAB_CLI_ASSIGN_RETRIES='0', COLAB_CLI_REQUEST_TIMEOUT='15',
            PYTHONPYCACHEPREFIX=reg['empty_pycache'])

    def sdk(self, mode, timeout, *arguments):
        command = [self.reg['sdk_python'], '-B', str(Path(__file__).resolve()),
            '--plan', self.plan_path, '--plan-sha256', self.plan_sha, '--output', str(self.output),
            '--sdk', mode, *arguments]
        result = subprocess.run(command, env=self.env, capture_output=True, timeout=timeout)
        need(result.returncode == 0 and len(result.stdout) <= 65536, 'SDK adapter failed')
        return json.loads(result.stdout)

    def snapshot(self, timeout):
        return self.sdk('snapshot', timeout)

    def allocate(self, nonce, output, timeout):
        return self.sdk('allocate', timeout, '--nonce', nonce)

    def require_owned_session(self):
        owned = read(self.output / 'owned-endpoint.json')
        session = read(self.reg['cli_config_path']).get(self.reg['session_name'])
        need(isinstance(session, dict) and session.get('name') == owned['name'] == self.reg['session_name']
             and session.get('endpoint') == owned['endpoint']
             and session.get('accelerator') == owned['accelerator'] == 'A100',
             'Local CLI session no longer matches owned endpoint')

    def upload(self, local, remote, timeout):
        self.require_owned_session()
        subprocess.run(self.prefix + ['upload', '-s', self.reg['session_name'], str(local), remote],
            env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=True, timeout=timeout)

    def start(self, nonce, timeout):
        self.require_owned_session()
        command = self.prefix + ['exec', '-s', self.reg['session_name'], '-f', self.reg['exec_script'],
            '--timeout', str(timeout), '--env', 'DODGE057_BILLING_ADMITTED=true',
            '--env', 'DODGE057_JOB_NONCE=' + nonce,
            '--env', 'DODGE057_PAYLOAD_SHA256=' + self.reg['payload_sha256']]
        return subprocess.Popen(command, env=self.env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)

    def poll(self, process):
        return process.poll()

    def stop_local(self, process):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=3)
        else:
            process.wait()

    def download(self, remote, local, timeout):
        self.require_owned_session()
        subprocess.run(self.prefix + ['download', '-s', self.reg['session_name'], remote, str(local)],
            env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=True, timeout=timeout)

    def unassign(self, endpoint, output, timeout):
        self.sdk('unassign', timeout, '--endpoint', endpoint)


def sdk_adapter(reg, output, mode, nonce=None, endpoint=None):
    """Only this child imports OAuth/CLI dependencies; never print their models."""
    os.umask(0o077)
    need(os.environ.get('COLAB_CLI_ASSIGN_RETRIES') == '0'
         and os.environ.get('COLAB_CLI_REQUEST_TIMEOUT') == '15', 'SDK retry/timeout guard differs')
    from colab_cli.common import State
    from colab_cli.auth import AuthProvider
    from colab_cli.client import Accelerator, Variant, Shape
    from colab_cli.consumption import CcuInfo
    from colab_cli.state import SessionState
    state = State(); state.config_path = reg['cli_config_path']; state.auth_provider = AuthProvider.OAUTH2
    def checked_cli_origins():
        origins = {}
        for name, module in list(sys.modules.items()):
            if name.startswith('colab_cli.') and getattr(module, '__file__', None):
                path = str(Path(module.__file__).resolve())
                need(reg['input_pins'].get(path) == sha(path), 'Unregistered loaded CLI module')
                origins[name] = dict(path=path, sha256=sha(path))
        return origins
    if mode == 'snapshot':
        raw = state.client._issue_request(state.client.colab_domain.rstrip('/') + '/tun/m/ccu-info',
                                          schema=CcuInfo).model_dump(by_alias=True)
        assignments = [dict(endpoint=a.endpoint, accelerator=a.accelerator.value)
                       for a in state.client.list_assignments()]
        session = state.store.get(reg['session_name'])
        session = None if session is None else {k: getattr(session, k) for k in
                    ['name', 'endpoint', 'accelerator', 'variant', 'machine_shape']}
        return dict(raw=raw, assignments=assignments, session=session,
                    cli_loaded_origins=checked_cli_origins())
    output = Path(output)
    claim = read(output / 'dispatch.claimed')
    need(claim['expected_lease'] == reg['expected_lease'], 'SDK permit lease differs')
    if mode == 'allocate':
        need(str(uuid.UUID(nonce)) == nonce == claim['notebook_hash']
             and read(output / 'allocation.claimed')['notebook_hash'] == nonce,
             'Allocation UUID/permit differs')
        need(read(reg['state_path']).get('active_long_campaign') == reg['expected_lease'],
             'Allocation requires exact global compatibility lease')
        need(state.store.get(reg['session_name']) is None, 'Session name already consumed')
        checked_cli_origins()
        save(output / 'sdk-allocation.claimed', dict(notebook_hash=nonce))
        response = state.client.assign(uuid.UUID(nonce), variant=Variant.GPU,
                                       accelerator=Accelerator.A100, shape=Shape.STANDARD)
        owned = dict(name=reg['session_name'], endpoint=response.endpoint,
                     accelerator=response.accelerator.value, variant='GPU',
                     machine_shape='STANDARD', notebook_hash=nonce)
        # Ownership survives a later secret-session write error or CLI client loss.
        save(output / 'owned-endpoint.json', owned)
        info = response.runtime_proxy_info
        state.store.add(SessionState(name=reg['session_name'], endpoint=response.endpoint,
            accelerator=response.accelerator.value, variant='GPU', machine_shape='STANDARD',
            token=info.token, url=info.url, token_expires_at=info.expires_at()))
        Path(reg['cli_config_path']).chmod(0o600)
        return owned
    need(mode == 'unassign', 'Unknown SDK operation')
    checked_cli_origins()
    owned = read(output / 'owned-endpoint.json')
    need(owned['endpoint'] == endpoint and owned['name'] == reg['session_name']
         and owned['notebook_hash'] == claim['notebook_hash'], 'Unassign lacks endpoint ownership proof')
    state.client.unassign(endpoint)
    # This is housekeeping only; fresh list_assignments proves teardown later.
    session = state.store.get(reg['session_name'])
    if session is not None and session.endpoint == endpoint: state.store.remove(reg['session_name'])
    return dict(status='unassign_requested', endpoint=endpoint)


def accept_terminal(plan, output, transport):
    """Durable accepted audit, then normal exact compatibility-lease release."""
    reg = validate_plan(plan); output = Path(output)
    need(not (output / 'coordinator-terminal-audit.json').exists(),
         'Accepted audit already exists; verify its release receipt instead of rerunning')
    need(output.parent.resolve() == PARENT.resolve() and not output.is_symlink()
         and output.resolve().parent == PARENT.resolve(), 'Terminal output namespace differs')
    need(not any(('failure' in f.name and f.name != 'failure-disposition.json')
                 or f.name.endswith('.partial') for f in output.iterdir()),
         'Compatibility failure/partial evidence present')
    terminal = read(output / 'parent-terminal-audit.json')
    claim = read(output / 'dispatch.claimed'); owned = read(output / 'owned-endpoint.json')
    disposition = read(output / 'failure-disposition.json')
    handoff = read(output / 'lease-handoff.json')
    need(claim['registration_sha256'] == handoff['registration_sha256'] == plan['registration_sha256']
         and claim['review_sha256'] == handoff['review_sha256'] == plan['review_sha256']
         and claim['expected_lease'] == handoff['replacement_lease'] == reg['expected_lease']
         and handoff['never_cleared_to_null'] is True
         and handoff['failure_disposition_sha256'] == sha(output / 'failure-disposition.json')
         and handoff['previous_lease'] == disposition['exact_lease']
         and disposition['record'] == 'DODGE-056' and disposition['campaign_success'] is False,
         'Failure disposition/handoff identity differs')
    need(terminal['status'] == 'compatibility_complete_pending_coordinator_acceptance'
         and terminal['registration_sha256'] == plan['registration_sha256']
         and terminal['job_nonce'] == claim['notebook_hash'] == owned['notebook_hash'],
         'Compatibility terminal identity differs')
    need(sha(output / 'receipts.tar') == terminal['receipt_archive_sha256']
         and sha(output / 'teardown.json') == terminal['teardown_sha256'], 'Terminal artifact changed')
    validate_receipts(output / 'receipts.tar', terminal['job_nonce'], reg['payload_sha256'], reg)
    cleanup = read(output / 'teardown.json')
    need(cleanup['status'] == 'owned_assignment_absent' and cleanup['budget_within_limits'] is True
         and cleanup['endpoint'] == owned['endpoint'], 'Strict teardown/budget receipt absent')
    snapshot = transport.snapshot(timeout=15)
    need(snapshot['raw']['assignmentsCount'] == 0 and not snapshot['assignments'],
         'Fresh assignment absence not confirmed')
    audit = dict(schema='dodge057_coordinator_terminal_acceptance_v1', record='DODGE-057',
        status='accepted_synthetic_cuda_compatibility', registration_sha256=plan['registration_sha256'],
        job_nonce=terminal['job_nonce'], observer_terminal_sha256=sha(output / 'parent-terminal-audit.json'),
        teardown_sha256=sha(output / 'teardown.json'), native_games=0, training_frames=0,
        promoted=False, exact_lease=reg['expected_lease'], actual_GPU='A100')
    state_path = Path(reg['state_path'])
    import fcntl
    with (state_path.parent / 'horizon-ledger.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read(state_path)
        need(state.get('active_long_campaign') == reg['expected_lease'], 'Exact terminal lease differs')
        # Durable acceptance precedes CAS while the same shared lock remains held.
        audit_sha = save(output / 'coordinator-terminal-audit.json', audit)
        state['active_long_campaign'] = None
        temporary = state_path.parent / ('.cloud-release-' + str(os.getpid()))
        with temporary.open('x') as stream:
            json.dump(state, stream, sort_keys=True, allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, state_path); _base.fsync_dir(state_path.parent)
    save(output / 'lease-release.json', dict(status='coordinator_exact_release_completed',
         record='DODGE-057', accepted_audit_sha256=audit_sha, previous_lease=reg['expected_lease'],
         lease_value_after_release=None))
    return audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True); parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--sdk', choices=['snapshot', 'allocate', 'unassign'])
    parser.add_argument('--nonce'); parser.add_argument('--endpoint')
    parser.add_argument('--accept-terminal', action='store_true')
    args = parser.parse_args()
    need(sha(args.plan) == args.plan_sha256, 'Cloud plan hash differs')
    plan = read(args.plan); reg = validate_plan(plan, cleanup=args.sdk == 'unassign')
    if args.sdk:
        try:
            result = sdk_adapter(reg, args.output, args.sdk, args.nonce, args.endpoint)
            print(json.dumps(result, allow_nan=False))
        except BaseException as error:
            # Exception strings/tracebacks may contain OAuth or proxy credentials.
            print(json.dumps(dict(status='SDK_failure', exception_type=type(error).__name__)))
            raise SystemExit(1)
        return
    transport = SDKTransport(args.plan, args.plan_sha256, reg, args.output)
    if args.accept_terminal:
        print(json.dumps(accept_terminal(plan, args.output, transport), allow_nan=False))
        return
    billing = load_module(reg['billing_guard_path'], reg['billing_guard_sha256'], 'cloud057_billing')
    disposition = failed056_disposition()
    def cancelled(signum, frame):
        for value in [signal.SIGINT, signal.SIGTERM]:
            signal.signal(value, signal.SIG_IGN)
        raise InterruptedError('Coordinator interrupted; exact owned teardown required')
    for signum in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(signum, cancelled)
    controller = Controller(reg, plan, args.output, transport, billing.BillingGuard)
    result = controller.run(disposition)
    save(Path(args.output) / 'parent-terminal-audit.json', result)
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
