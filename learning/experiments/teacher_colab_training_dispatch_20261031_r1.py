"""Sole A100 allocator for the separately reviewed DODGE-058 training packet.

Preparation imports no learning runtime and opens no seed pool. Build admission
does not rewrite registration. Independent billing and control threads fence
remote work while blocking CLI operations run. Failures retain the exact lease.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import signal
import struct
import subprocess
import sys
import tarfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / 'learning/runs/v2/teacher-cloud-parent-20261031-r1'
BASE = Path(__file__).with_name('coordinator_dispatch_v2.py')
BASE_SHA = '77655f4e200ccce33950cd53201ef509394f8bff81e92fdd208c52668890fa16'
PREREQUISITE_SHA = '1934441413ad7b6128c40cac87160976d1554099a563cb52cf4c64826df10794'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def load(path, digest, name):
    need(sha(path) == digest, 'Imported source hash differs')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_base = load(BASE, BASE_SHA, 'dodge058_receipt_base')
save = _base.save


class Clock:
    """Count suspend and resist backwards clock changes."""
    def __init__(self):
        self.wall = time.time()
        self.monotonic = time.monotonic()
        self.last = 0.
        self.lock = threading.Lock()

    def now(self):
        with self.lock:
            self.last = max(self.last, time.time()-self.wall, time.monotonic()-self.monotonic)
            return self.last


def validate_plan(plan, *, preparation=False):
    for key in ('registration', 'authority'):
        need(sha(plan[key+'_path']) == plan[key+'_sha256'], 'Plan binding differs')
    reg, authority = read(plan['registration_path']), read(plan['authority_path'])
    need(reg['schema'] == 'dodge_colab_native_training_registration_v1'
         and reg['record'] == authority['record'] == 'DODGE-058', 'Wrong training registration')
    need(reg['authority_path'] == plan['authority_path']
         and reg['authority_sha256'] == plan['authority_sha256'], 'Authority binding differs')
    need(authority['schema'] == 'dodge058_parent_training_authority_v1'
         and authority['allocation_attempts_authorized'] == 1
         and authority['accelerator'] == reg['accelerator'] == 'A100'
         and authority['limits'] == reg['financial_limits']
         and authority['conditional_training_after_build_admission'] is True,
         'Training authority differs')
    budget = load(reg['budget_path'], reg['source_pins'][reg['budget_path']], 'dodge058_budget_validation')
    need(reg['financial_limits'] == vars(budget.Config()), 'Financial caps differ')
    need(reg['no_retry'] is reg['no_resume'] is reg['training_stage_authorized'] is True
         and reg['promotion'] is False and reg['device'] == 'cuda:0', 'Lifecycle/device differs')
    need(reg['expected_lease'] == authority['expected_lease']
         and reg['expected_lease_sha256'] == hashlib.sha256(canonical(reg['expected_lease'])).hexdigest()
         and reg['state_path'] == authority['state_path'], 'Exact lease binding differs')
    need(str(uuid.UUID(reg['job_nonce'])) == reg['job_nonce'], 'Canonical persisted nonce required')
    need(reg['prerequisite_path'] == str(PARENT/'dispatch-DODGE061-archive-r1/coordinator-terminal-audit.json')
         and reg['prerequisite_sha256'] == PREREQUISITE_SHA
         and sha(reg['prerequisite_path']) == PREREQUISITE_SHA, 'Accepted061 prerequisite differs')
    need(reg['output_root'] == '/content/dodge058' and reg['runtime_root'] == '/content/dodge058/runtime'
         and reg['vendor_root'] == '/content/dodge058/vendor'
         and reg['checkpoint_path'] == '/content/dodge058/inputs/checkpoint420.pt'
         and reg['pool_path'] == '/content/dodge058/inputs/training-pool512.json', 'Remote namespace differs')
    recipe = read(Path(reg['owner_source_root'])/'scientific_recipe.json')
    for key, value in recipe.items():
        if key not in {'schema', 'record', 'launch_authority', 'pool_path', 'CUDA_seed_mapping'}:
            need(reg.get(key) == value, 'Scientific recipe differs: '+key)
    need(reg['stage_timeout_seconds'] == {'build': 1100, 'train': 22320}
         and reg['native_setup_work_seconds'] == 900 and reg['linux_toolchain'] is None,
         'Staged build deadlines/toolchain differ')
    controller_paths = [str(Path(__file__).resolve()), str(BASE.resolve()), reg['adapter_path'], reg['budget_path']]
    for path in controller_paths:
        need(reg['coordinator_source_pins'].get(path) == reg['source_pins'].get(path) == sha(path),
             'Coordinator source not pinned')
    if not preparation:
        need(sha(plan['review_path']) == plan['review_sha256'], 'Independent review hash differs')
        review = read(plan['review_path'])
        need(review['status'] == 'no_blocking_findings'
             and review['registration_sha256'] == plan['registration_sha256']
             and all(review['coordinator_source_pins'].get(p) == sha(p) for p in controller_paths),
             'Fresh exact joint review absent')
    for path in set(reg['source_pins']) & set(reg['input_pins']):
        need(reg['source_pins'][path] == reg['input_pins'][path], 'Conflicting pins')
    # Preparation must not open the fixed training pool. At dispatch it is
    # hashed only after the reviewed exact lease is acquired, before allocation.
    need(reg['deferred_training_pool']['sha256'] == reg['pool_sha256'], 'Deferred pool pin differs')
    for path, digest in {**reg['source_pins'], **reg['input_pins']}.items():
        need(path != reg['deferred_training_pool']['local'], 'Pool read forbidden in ordinary pin loop')
        need(sha(path) == digest, 'Registered source/input changed: '+path)
    cache = Path(reg['empty_pycache'])
    need(cache.is_dir() and not list(cache.iterdir()), 'Existing empty cache required')
    return reg


def output_path(path, *, create=False):
    path = Path(path)
    need(path.parent.resolve() == PARENT.resolve() and not path.is_symlink()
         and path.resolve().parent == PARENT.resolve(), 'Output must be a direct real coordinator child')
    if create:
        path.mkdir()
    need(path.is_dir() and not path.is_symlink(), 'Output directory absent/redirected')
    return path


def lease_guard(reg):
    need(read(reg['state_path']).get('active_long_campaign') == reg['expected_lease'],
         'Exact058 lease lost; remote work must stop')


def lease_cas(reg, expected, replacement, *, before=None):
    path = Path(reg['state_path'])
    with (path.parent/'horizon-ledger.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read(path)
        need(state.get('active_long_campaign') == expected, 'Exact shared lease CAS differs')
        if before is not None:
            before()
        state['active_long_campaign'] = replacement
        temporary = path.parent/('.cloud058-state-'+str(os.getpid()))
        with temporary.open('x') as stream:
            json.dump(state, stream, sort_keys=True, allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        _base.fsync_dir(path.parent)


def owner_reader(reg):
    """Owner decoder uses only its pinned stdlib common module."""
    source = Path(reg['owner_source_root'])
    load(source/'common.py', reg['source_pins'][str(source/'common.py')], 'common')
    return load(source/'receipts.py', reg['source_pins'][str(source/'receipts.py')], 'dodge058_decoder')


def archive_documents(path):
    docs = {}
    with tarfile.open(path, 'r:') as archive:
        for member in archive.getmembers():
            need(member.isfile() and not PurePosixPath(member.name).is_absolute()
                 and '..' not in PurePosixPath(member.name).parts, 'Unsafe archive member')
            if member.name.endswith('.json'):
                need(member.size <= 16*1024*1024, 'Metadata member too large')
                docs[member.name] = json.loads(archive.extractfile(member).read())
    return docs


def validate_build(path, binary_path, reg):
    inventory = owner_reader(reg).decode_archive(path, sha(path), reg, require_complete=False, allow_fixtures=False)
    need(not inventory['failed_paths'] and inventory['checkpoint_files'] == 0, 'Build contains failure/partial/weights')
    docs = archive_documents(path)
    need(not any('failure' in name or '.partial' in name for name in docs), 'Build failure present')
    cert = docs['native-build.json']
    need(cert['status'] == 'complete' and cert['stage'] == 'native_build'
         and cert['native_games'] == cert['training_frames'] == cert['native_imports'] == cert['constructor_calls'] == 0
         and cert['trained_weights_saved'] is False, 'Build scope differs')
    source = Path(reg['owner_source_root'])
    candidate = read(source/'python_runtime_candidate.json')
    need(cert['package_origins'] == candidate['package_origins']
         and cert['Python'] == candidate['python']
         and cert['package_versions'] == dict(torch=candidate['torch'], numpy=candidate['numpy'], CUDA=candidate['cuda_runtime'])
         and cert['interpreter_sha256'] == candidate['package_origins']['python']['sha256'], 'Actual image differs from candidate')
    need(cert['engine_source_manifest_sha256'] == sha(source/'native_source_manifest.json')
         and cert['archived_MachO_sha256'] == 'ae9238670a0beea0951374562fcd5116013b7715b40be2bfc512ca242bdec7b7',
         'Native source lineage differs')
    suffix = '.cpython-313-x86_64-linux-gnu.so'
    relative = 'dodge_rl/_native'+suffix
    expected = {str(Path(p).relative_to(source/'runtime')): digest for p, digest in reg['source_pins'].items()
                if Path(p).is_relative_to(source/'runtime')}
    expected[relative] = sha(binary_path)
    need(cert['SOABI'] == 'cpython-313-x86_64-linux-gnu' and cert['EXT_SUFFIX'] == suffix
         and cert['runtime_root'] == reg['runtime_root']
         and cert['native_binary'] == reg['runtime_root']+'/'+relative
         and cert['native_binary_sha256'] == sha(binary_path)
         and cert['runtime_members'] == expected, 'Built runtime inventory/ABI differs')
    with Path(binary_path).open('rb') as stream:
        header = stream.read(64)
    need(len(header) == 64 and header[:6] == b'\x7fELF\x02\x01'
         and struct.unpack('<HH', header[16:20]) == (3, 62), 'Native binary is not x86_64 shared ELF')
    toolchain = read(source/'linux_toolchain_source.json')
    need(cert['toolchain']['official_component_pins'] == toolchain['components']
         and 'release: 1.97.1' in cert['rustc_version']
         and 'commit-hash: 8bab26f4f68e0e26f0bb7960be334d5b520ea452' in cert['rustc_version']
         and 'host: x86_64-unknown-linux-gnu' in cert['rustc_version']
         and cert['linked_and_framework_libraries'] and 'not found' not in cert['ldd_output'],
         'Toolchain/link certificate differs')
    assembly = docs['source-assembly.json']
    need(assembly['registration_sha256'] == reg['registration_sha256']
         and assembly['payload_sha256'] == reg['payload_sha256'] and assembly['job_nonce'] == reg['job_nonce'],
         'Source assembly binding differs')
    return cert


def validate_training(path, reg, admission):
    result = owner_reader(reg).decode_archive(path, sha(path), reg, require_complete=True, allow_fixtures=False)
    docs = archive_documents(path)
    with tarfile.open(path, 'r:') as archive:
        build_bytes = archive.extractfile('native-build.json').read()
    need(hashlib.sha256(build_bytes).hexdigest() == admission['accepted_build_certificate_sha256'],
         'Training archive build certificate differs from admitted build')
    campaign = docs['campaign-result.json']
    need(campaign['job_order'] == [j['id'] for j in reg['jobs']]
         and campaign['evaluation_games'] == 0 and campaign['no_resume'] is True
         and campaign['promotion'] is False, 'Campaign scope/order differs')
    for job in reg['jobs']:
        prefix = 'outputs/'+job['id']+'/'
        supervisor, worker = (docs[prefix+n] for n in ['supervisor-result.json', 'worker-result.json'])
        for key, cap in [('peak_group_RSS_bytes', reg['rss_bytes']),
                         ('peak_CUDA_driver_process_bytes', reg['cuda_driver_bytes'])]:
            need(type(supervisor[key]) is int and 0 < supervisor[key] < cap, 'Observed supervisor resource cap differs')
        need(supervisor['elapsed_seconds'] < reg['work_seconds']+reg['receipt_seconds'], 'Supervisor wall cap differs')
        need(type(worker['native_games']) is int and worker['native_games'] >= reg['envs'], 'Native game counter absent')
        migration = docs[prefix+'migration.json']
        need(migration['CPU_zero_gate_exact'] is migration['CUDA_zero_gate_exact'] is True
             and migration['source_model'] == reg['model_fingerprint']
             and migration['source_adam'] == reg['adam_fingerprint'], '420 migration proof differs')
    return result


class LiveFence:
    """Independent price monitor and serialized control writer; no rearming."""
    def __init__(self, reg, transport, budget, clock, journal, *, lease_check=lease_guard):
        self.reg, self.transport, self.budget, self.clock = reg, transport, budget, clock
        self.journal, self.lease_check = journal, lease_check
        self.stop = threading.Event()
        self.failed = threading.Event()
        self.lock = threading.RLock()
        self.phase = 'setup'; self.stage = 'build'; self.admission_sha = None
        self.sequence = 0; self.last_issued = 0.; self.permit_at = None
        self.error = None; self.threads = []

    def fail(self, reason):
        with self.lock:
            if self.error is None:
                self.error = reason
        self.failed.set(); self.stop.set()

    def check(self):
        need(not self.failed.is_set(), self.error or 'Live monitoring failed')
        self.lease_check(self.reg)
        now = self.clock.now()
        need(self.permit_at is not None and now-self.permit_at <= 35, 'Financial permit expired')
        if self.phase == 'setup':
            need(now-self.budget.allocation_start < 1200, 'Total native setup cap reached')
        need(now-self.budget.allocation_start < 23520, 'Work deadline reached; teardown reserve required')

    def meter_once(self):
        started = self.clock.now()
        snapshot = self.transport.snapshot(timeout=15)
        with self.lock:
            self.lease_check(self.reg)
            result = self.budget.observe(snapshot['raw'], snapshot['assignments'], self.transport.endpoint,
                self.clock.now(), request_started=started, phase=self.phase)
            need(result['work_admitted'], 'Financial work permit absent')
            self.permit_at = self.clock.now()
            self.journal.write(canonical(dict(result, at=self.permit_at)).decode()+'\n')
            self.journal.flush(); os.fsync(self.journal.fileno())

    def renew_once(self):
        # The same lock drains a pending old-stage PUT before transition.
        with self.lock:
            self.check()
            need(not self.stop.is_set(), 'Control renewal stopped')
            issued = time.time()
            need(issued >= self.last_issued, 'UTC clock reversed')
            self.sequence += 1; self.last_issued = issued
            control = {k: self.reg[k] for k in ['record', 'job_nonce', 'registration_sha256', 'expected_lease_sha256']}
            control.update(issued_at_utc=issued, expires_at_utc=issued+45,
                           sequence=self.sequence, allowed_stage=self.stage)
            if self.stage == 'train':
                need(self.admission_sha is not None, 'Runtime admission absent')
                control['runtime_admission_sha256'] = self.admission_sha
            self.transport.put_json('/content/dodge058/control.json', control, timeout=8)

    def loop(self, action):
        while not self.stop.wait(15):
            try:
                action()
            except BaseException as error:
                # External exception text can contain credentials. Fixed reason only.
                self.fail('Live '+action.__name__+' failed: '+type(error).__name__)

    def start(self):
        self.meter_once(); self.renew_once()
        self.threads = [threading.Thread(target=self.loop, args=(a,), daemon=True)
                        for a in [self.meter_once, self.renew_once]]
        for thread in self.threads:
            thread.start()

    def train(self, admission_sha):
        self.meter_once()
        with self.lock:
            self.check()
            self.stage = 'train'; self.phase = 'training'; self.admission_sha = admission_sha
            self.renew_once()

    def close(self):
        self.stop.set()
        for thread in self.threads:
            thread.join(timeout=25)
            need(not thread.is_alive(), 'Control/billing writer did not drain')


class Controller:
    def __init__(self, reg, plan, output, transport, budget_class, *, clock=None):
        self.reg, self.plan, self.output, self.transport = reg, plan, Path(output), transport
        self.budget_class = budget_class; self.clock = clock or Clock()
        self.fence = None; self.process = None; self.endpoint = None
        self.allocation_called = False; self.phase = 'preflight'

    def wait_stage(self, script, stage, timeout):
        self.fence.check()
        self.process = self.transport.start(script, stage, timeout=timeout)
        began = self.clock.now()
        while self.process.poll() is None:
            self.fence.check()
            need(self.clock.now()-began < timeout, 'Stage CLI deadline exceeded')
            self.fence.failed.wait(.5)
        code = self.process.wait()
        self.fence.check()
        need(code == 0, 'Remote stage failed; preserve first evidence')

    def run(self):
        reg = self.reg
        before = self.clock.now(); initial = self.transport.snapshot(timeout=15)
        need(self.clock.now()-before <= 15 and not initial['assignments']
             and initial['raw']['assignmentsCount'] == 0 and initial['session'] is None,
             'Fresh free account/session proof absent')
        # Validate existing credit balance before taking the global lease.
        self.budget_class(initial['raw']['currentBalance'], self.clock.now())
        output_path(self.output, create=True)
        save(self.output/'dispatch.claimed', dict(record=reg['record'], notebook_hash=reg['job_nonce'],
            registration_sha256=reg['registration_sha256'], expected_lease=reg['expected_lease'],
            review_sha256=self.plan['review_sha256'], coordinator_pid=os.getpid()))
        failure = None; cleanup = None; budget = None; decoded = None
        try:
            self.phase = 'lease_acquisition'
            lease_cas(reg, None, reg['expected_lease'])
            save(self.output/'lease-acquired.json', dict(status='exact_free_lease_acquired',
                 expected_previous_lease=None, replacement_lease=reg['expected_lease'],
                 registration_sha256=reg['registration_sha256']))
            # This is the first authorized pool read. It cannot occur in prepare/review.
            lease_guard(reg)
            need(sha(reg['deferred_training_pool']['local']) == reg['pool_sha256'], 'Authorized fixed pool changed')
            self.phase = 'allocation'
            budget = self.budget_class(initial['raw']['currentBalance'], self.clock.now())
            save(self.output/'allocation.claimed', dict(notebook_hash=reg['job_nonce'],
                 session_name=reg['session_name'], started_at=budget.allocation_start))
            self.allocation_called = True
            owned = self.transport.allocate(reg['job_nonce'], timeout=45)
            need(owned['notebook_hash'] == reg['job_nonce'] and owned['name'] == reg['session_name']
                 and owned['accelerator'] == 'A100', 'Owned A100 response differs')
            self.endpoint = self.transport.endpoint = owned['endpoint']
            self.phase = 'setup'
            self.transport.mkdir('/content/dodge058', timeout=15)
            self.transport.mkdir('/content/dodge058/inputs', timeout=15)
            with (self.output/'billing.jsonl').open('x') as journal:
                self.fence = LiveFence(reg, self.transport, budget, self.clock, journal)
                self.fence.start()
                try:
                    for asset in reg['uploads']:
                        self.fence.check()
                        self.transport.upload(asset['local'], asset['remote'], timeout=60)
                    self.fence.check()
                    self.transport.upload(self.plan['registration_path'], '/content/dodge058/registration.json', timeout=15)
                    self.wait_stage(reg['unpack_script'], 'build', 60)
                    self.wait_stage(reg['stage_script'], 'build', reg['stage_timeout_seconds']['build'])
                    self.transport.download('/content/dodge058/build-artifacts.tar', self.output/'build-artifacts.tar', timeout=60)
                    binary_remote = reg['runtime_root']+'/dodge_rl/_native.cpython-313-x86_64-linux-gnu.so'
                    self.transport.download(binary_remote, self.output/'native-runtime.so', timeout=60)
                    self.fence.check()
                    cert = validate_build(self.output/'build-artifacts.tar', self.output/'native-runtime.so', reg)
                    cert_bytes = None
                    with tarfile.open(self.output/'build-artifacts.tar') as archive:
                        cert_bytes = archive.extractfile('native-build.json').read()
                    admission = {k: reg[k] for k in ['record', 'job_nonce', 'registration_sha256', 'expected_lease_sha256']}
                    admission.update(status='accepted_preimport_build_certificate',
                        accepted_build_certificate_sha256=hashlib.sha256(cert_bytes).hexdigest(),
                        native_imports=0, constructor_calls=0, actual_native_binary_sha256=cert['native_binary_sha256'])
                    admission_sha = save(self.output/'runtime-admission.json', admission)
                    self.fence.check()
                    self.transport.put_json('/content/dodge058/runtime-admission.json', admission, timeout=8,
                                            exact_bytes=(self.output/'runtime-admission.json').read_bytes())
                    self.fence.train(admission_sha)
                    self.phase = 'training'
                    self.wait_stage(reg['stage_script'], 'train', reg['stage_timeout_seconds']['train'])
                    # Stop granting work before receipt retrieval. Never rearm.
                    self.fence.close()
                    self.phase = 'retrieval'
                    self.transport.download('/content/dodge058/training-artifacts.tar', self.output/'training-artifacts.tar', timeout=180)
                    decoded = validate_training(self.output/'training-artifacts.tar', reg, admission)
                finally:
                    self.fence.close()
        except BaseException as error:
            failure = dict(status='first_failure_preserved_lease_held', record='DODGE-058',
                phase=self.phase, exception_type=type(error).__name__,
                monitoring_reason=None if self.fence is None else self.fence.error,
                allocation_called=self.allocation_called, campaign_success=False)
        finally:
            # A crashed renewal thread or CLI must never prevent exact teardown.
            if self.fence is not None:
                try:
                    self.fence.close()
                except BaseException:
                    failure = failure or dict(status='first_failure_preserved_lease_held', phase='control_drain')
            if self.process is not None:
                try:
                    self.transport.stop_local(self.process)
                except BaseException:
                    failure = failure or dict(status='first_failure_preserved_lease_held', phase='local_cleanup')
            owned_path = self.output/'owned-endpoint.json'
            if self.endpoint is None and owned_path.exists():
                try:
                    owned = read(owned_path)
                    if owned.get('notebook_hash') == reg['job_nonce'] and owned.get('name') == reg['session_name']:
                        self.endpoint = self.transport.endpoint = owned['endpoint']
                except BaseException:
                    failure = failure or dict(status='first_failure_preserved_lease_held', phase='ownership_receipt')
            if self.endpoint is not None:
                try:
                    self.transport.put_json('/content/dodge058/cancel.requested', {'requested': True}, timeout=8)
                except BaseException:
                    pass
                # Cancellation is checked by build/train supervision. Give the
                # real writer a bounded grace period to close its first-failure
                # archive before one retrieval attempt. This never reruns work.
                artifact = ('training-artifacts.tar' if self.phase in ['training','retrieval']
                            else 'build-artifacts.tar')
                if not (self.output/artifact).exists():
                    try:
                        time.sleep(5)
                        self.transport.download('/content/dodge058/'+artifact,
                                                self.output/artifact, timeout=60)
                    except BaseException:
                        pass
                absent_before = False
                try:
                    snapshot = self.transport.snapshot(timeout=15)
                    absent_before = not any(a['endpoint'] == self.endpoint for a in snapshot['assignments'])
                except BaseException:
                    pass
                try:
                    if not absent_before:
                        save(self.output/'release-requested.json', dict(status='coordinator_release_requested', endpoint=self.endpoint))
                        try:
                            self.transport.unassign(self.endpoint, timeout=40)
                        except BaseException:
                            # A lost response can follow a successful POST. Do not
                            # retry it; the fresh inventory resolves absence.
                            failure = failure or dict(status='first_failure_preserved_lease_held', phase='release_response')
                    started = self.clock.now(); final = self.transport.snapshot(timeout=15)
                    need(not any(a['endpoint'] == self.endpoint for a in final['assignments']), 'Owned VM absence unconfirmed')
                    accounting = budget.final(final['raw'], final['assignments'], self.clock.now(), request_started=started)
                    cleanup = dict(accounting, status='owned_assignment_absent', endpoint=self.endpoint,
                        removal_classification=('assignment_absent_before_our_release_request' if absent_before
                                                else 'coordinator_requested_release'),
                        provider_termination_reason='unknown' if absent_before else None,
                        release_requested_by_coordinator=not absent_before)
                    save(self.output/'teardown.json', cleanup)
                    if absent_before:
                        failure = failure or dict(status='first_failure_preserved_lease_held', phase='provider_disappearance')
                except BaseException as error:
                    save(self.output/'cleanup-first-failure.json', dict(status='teardown_or_budget_unconfirmed',
                         exception_type=type(error).__name__))
                    failure = failure or dict(status='first_failure_preserved_lease_held', phase='teardown')
            elif self.allocation_called:
                save(self.output/'cleanup-first-failure.json', dict(status='allocation_outcome_ambiguous_no_unowned_stop'))
                failure = failure or dict(status='first_failure_preserved_lease_held', phase='ambiguous_allocation')
        if failure is not None:
            save(self.output/'first-failure.json', failure)
            raise ValueError('DODGE-058 failed; preserve exact lease and all evidence; no retry')
        need(decoded is not None and cleanup is not None, 'Training terminal evidence absent')
        result = dict(status='training_complete_pending_coordinator_acceptance', record='DODGE-058',
            registration_sha256=reg['registration_sha256'], job_nonce=reg['job_nonce'],
            training_archive_sha256=sha(self.output/'training-artifacts.tar'),
            runtime_admission_sha256=sha(self.output/'runtime-admission.json'),
            teardown_sha256=sha(self.output/'teardown.json'), decoded=decoded, lease_released=False)
        save(self.output/'parent-terminal-audit.json', result)
        return result


def accept_terminal(plan, output, transport):
    reg = validate_plan(plan); reg['registration_sha256'] = plan['registration_sha256']
    output = output_path(output)
    need(not (output/'coordinator-terminal-audit.json').exists(), 'Accepted audit already exists; do not rerun')
    need(not any('failure' in p.name or '.partial' in p.name for p in output.rglob('*')), 'Failure/partial evidence present')
    terminal, claim, teardown = (read(output/p) for p in ['parent-terminal-audit.json', 'dispatch.claimed', 'teardown.json'])
    exited = read(output/'coordinator-exit.json')
    need(exited['directly_reaped'] is True and exited['observed_exit_code'] == 0
         and exited['coordinator_pid'] == claim['coordinator_pid'], 'Coordinator direct reap absent')
    try:
        os.kill(claim['coordinator_pid'], 0)
    except ProcessLookupError:
        pass
    else:
        raise ValueError('Coordinator PID still live or reused; inspect without releasing')
    need(terminal['registration_sha256'] == claim['registration_sha256'] == reg['registration_sha256']
         and claim['notebook_hash'] == reg['job_nonce'] and claim['expected_lease'] == reg['expected_lease']
         and claim['review_sha256'] == plan['review_sha256']
         and terminal['status'] == 'training_complete_pending_coordinator_acceptance', 'Terminal identity differs')
    need(teardown['status'] == 'owned_assignment_absent' and teardown['budget_within_limits'] is True
         and teardown['removal_classification'] == 'coordinator_requested_release', 'Teardown not accepted')
    for key, name in [('training_archive_sha256','training-artifacts.tar'), ('teardown_sha256','teardown.json'),
                      ('runtime_admission_sha256','runtime-admission.json')]:
        need(terminal[key] == sha(output/name), 'Terminal receipt changed')
    validate_build(output/'build-artifacts.tar', output/'native-runtime.so', reg)
    validate_training(output/'training-artifacts.tar', reg, read(output/'runtime-admission.json'))
    need(sha(reg['deferred_training_pool']['local']) == reg['pool_sha256'], 'Training pool postflight differs')
    fresh = transport.snapshot(timeout=15)
    need(not fresh['assignments'] and fresh['raw']['assignmentsCount'] == 0, 'Fresh account absence required')
    audit = dict(status='accepted_training_campaign', record='DODGE-058', campaign_success=True,
                 registration_sha256=reg['registration_sha256'], parent_terminal_sha256=sha(output/'parent-terminal-audit.json'),
                 review_sha256=plan['review_sha256'], evaluation_games=0, promoted=False)
    audit_sha = None
    def durable_acceptance():
        nonlocal audit_sha
        audit_sha = save(output/'coordinator-terminal-audit.json', audit)
    lease_cas(reg, reg['expected_lease'], None, before=durable_acceptance)
    save(output/'lease-release.json', dict(status='coordinator_exact_release_completed', record='DODGE-058',
         accepted_audit_sha256=audit_sha, previous_lease=reg['expected_lease'], lease_value_after_release=None))
    return audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True); parser.add_argument('--sha256', required=True)
    parser.add_argument('--output'); parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--accept-terminal', action='store_true')
    args = parser.parse_args()
    need(sha(args.plan) == args.sha256, 'Plan digest differs')
    plan = read(args.plan); reg = validate_plan(plan, preparation=args.check_only)
    if args.check_only:
        print(json.dumps(dict(status='CPU_preparation_pins_verified', pool_opened=False, execution_authorized=False)))
        return
    reg['registration_sha256'] = plan['registration_sha256']
    adapter = load(reg['adapter_path'], reg['source_pins'][reg['adapter_path']], 'dodge058_transport')
    transport = adapter.Transport(args.plan, args.sha256, reg, args.output)
    if args.accept_terminal:
        print(json.dumps(accept_terminal(plan, args.output, transport)))
        return
    def interrupted(*_):
        for sig in [signal.SIGINT, signal.SIGTERM]:
            signal.signal(sig, signal.SIG_IGN)
        raise InterruptedError('Coordinator interrupted; teardown required')
    for sig in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(sig, interrupted)
    budget = load(reg['budget_path'], reg['source_pins'][reg['budget_path']], 'dodge058_budget_run')
    sleeper = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-w', str(os.getpid())],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        print(json.dumps(Controller(reg, plan, args.output, transport, budget.TrainingBudget).run()))
    finally:
        sleeper.terminate(); sleeper.wait(timeout=5)


if __name__ == '__main__':
    main()
