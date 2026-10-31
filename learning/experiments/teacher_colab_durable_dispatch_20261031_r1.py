"""Sole A100 allocator for the separately reviewed DODGE-064 training packet.

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
PARENT = ROOT / 'learning/runs/v2/teacher-cloud-durable-parent-20261031-r1'
BASE = Path(__file__).with_name('coordinator_dispatch_v2.py')
BASE_SHA = '77655f4e200ccce33950cd53201ef509394f8bff81e92fdd208c52668890fa16'
PREREQUISITE_SHA = '1934441413ad7b6128c40cac87160976d1554099a563cb52cf4c64826df10794'
FAILED_REGISTRATION_SHA = 'fc307984b593918c8eac9eda3673c80647940e2db3ef91b12362df3606ef06f9'
FAILED_INCIDENT_SHA = 'cbf08eabd59d53caec630c834126ec2d8eb90bd2a041b30c1c47d33346a14139'


class GuardError(ValueError):
    def __init__(self, reason):
        self.safe_reason=reason
        super().__init__(reason)


def need(ok, message):
    if not ok:
        raise GuardError(message)


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


_base = load(BASE, BASE_SHA, 'dodge064_receipt_base')
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


OLD_PARENT = ROOT/'learning/runs/v2/teacher-cloud-parent-20261031-r1'
OLD_REG_SHA = '822f3359981bb6865fc3f5c4033a31cb4a554d51d9319f7bb4765e8bb737ea67'
OLD_INCIDENT_SHA = 'f790fdba87b77624e49480146ed5276921df0b51fc310fb12ff0ed7502b8538b'


def failed062_disposition():
    path=OLD_PARENT/'DODGE-062-A100-training-registration-r2.json'
    output=OLD_PARENT/'dispatch-DODGE062-A100-training-r2'
    need(sha(path)==OLD_REG_SHA and sha(output/'monitor-blocking-incident.json')==OLD_INCIDENT_SHA,
         'Immutable failed062 identity changed')
    old=read(path);incident=read(output/'monitor-blocking-incident.json')
    for kind in ('source_pins','input_pins'):
        for filename,digest in old[kind].items():
            need(filename!=old['deferred_training_pool']['local'],'Pool forbidden in source pin loop')
            need(sha(filename)==digest,'Failed062 pin changed')
    for filename,digest in incident['evidence_sha256'].items():
        need(sha(output/filename)==digest,'Failed062 terminal evidence changed')
    exited=read(output/'coordinator-exit.json');teardown=read(output/'teardown.json')
    need(exited['directly_reaped'] is True and exited['observed_exit_code']==1
         and exited['local_main_control_caffeinate_and_registered_groups_absent'] is True
         and teardown['assignment_absence_confirmed'] is True
         and incident['campaign_success'] is False and incident['exact_held_lease']==old['expected_lease'],
         'Failed062 disposition incomplete')
    need(not (output/'coordinator-terminal-audit.json').exists()
         and not (output/'lease-release.json').exists() and not list(Path(old['empty_pycache']).iterdir()),
         'Failed062 improperly changed')
    pending=max(0.,teardown['accounted_cost_upper_estimate_CU']-teardown['observed_debit_CU'])
    return dict(status='failed062_preserved_no_success_waiver',record='DODGE-062',
                registration_sha256=OLD_REG_SHA,incident_sha256=OLD_INCIDENT_SHA,
                exact_lease=old['expected_lease'],campaign_success=False,
                assignment_absence_previously_confirmed=True,conservative_unreported_charge_upper_CU=pending)


def validate_plan(plan, *, preparation=False):
    for key in ('registration','authority'):
        need(sha(plan[key+'_path'])==plan[key+'_sha256'],'Plan identity differs')
    reg,authority=read(plan['registration_path']),read(plan['authority_path'])
    need(reg['record']==authority['record']=='DODGE-064'
         and reg['schema']=='dodge_colab_native_training_registration_v1'
         and authority['schema']=='dodge064_durable_authority_v1','Wrong successor identity')
    need(reg['authority_path']==plan['authority_path'] and reg['authority_sha256']==plan['authority_sha256'],
         'Authority binding differs')
    budget=load(reg['budget_path'],reg['source_pins'][reg['budget_path']],'dodge064_budget_validation')
    need(reg['financial_limits']==authority['limits']==vars(budget.Config())
         and authority['allocation_attempts_authorized']==1 and authority['accelerator']==reg['accelerator']=='A100',
         'Allocation or financial limits differ')
    disposition=failed062_disposition()
    need(read(reg['failure_disposition_path'])==disposition
         and sha(reg['failure_disposition_path'])==reg['failure_disposition_sha256']
         and reg['previous_lease']==authority['previous_lease']==disposition['exact_lease']
         and disposition['conservative_unreported_charge_upper_CU']<=3.,'Failed062 exact successor differs')
    need(reg['expected_lease']==authority['expected_lease'] and reg['state_path']==authority['state_path']
         and reg['expected_lease_sha256']==hashlib.sha256(canonical(reg['expected_lease'])).hexdigest(),
         'Exact successor lease binding differs')
    need(str(uuid.UUID(reg['job_nonce']))==reg['job_nonce'],'Canonical persisted nonce required')
    need(reg['output_root']=='/content/dodge064' and reg['runtime_root']=='/content/dodge064/runtime'
         and reg['vendor_root']=='/content/dodge064/vendor','Owned namespace differs')
    need(reg['no_retry'] is reg['no_resume'] is reg['training_stage_authorized'] is True
         and reg['promotion'] is reg['evaluation_authorized'] is False and reg['device']=='cuda:0',
         'Scientific lifecycle differs')
    source=Path(reg['owner_source_root']);recipe=read(source/'scientific_recipe.json')
    for key,value in recipe.items():
        if key not in {'schema','record','launch_authority','pool_path','CUDA_seed_mapping'}:
            need(reg.get(key)==value,'Scientific recipe differs: '+key)
    need(reg['stage_timeout_seconds']=={'preflight':180,'build':1100,'train':21320}
         and reg['campaign_total_seconds']==21320 and reg['native_setup_work_seconds']==900
         and reg['result_safety']==authority['result_safety']
         and reg['result_safety']==dict(challenge_bytes=33554432,chunk_bytes=1048576,
             checkpoint_ack_seconds=60,job_ack_seconds=60,recovery_seconds=180,teardown_seconds=180,
             transfer_request_seconds=15,no_transfer_retry=True), 'Durability/cap contract differs')
    paths=[str(Path(__file__).resolve()),str(BASE.resolve()),reg['adapter_path'],reg['budget_path'],reg['control_channel_path']]
    for path in paths:
        need(reg['coordinator_source_pins'].get(path)==reg['source_pins'].get(path)==sha(path),
             'Unpinned coordinator source')
    if not preparation:
        need(sha(plan['review_path'])==plan['review_sha256'],'Independent review pin differs')
        review=read(plan['review_path'])
        need(review['status']=='no_blocking_findings'
             and review['registration_sha256']==plan['registration_sha256']
             and all(review['coordinator_source_pins'].get(path)==sha(path) for path in paths),
             'Exact independent integration review absent')
    for path,digest in {**reg['source_pins'],**reg['input_pins']}.items():
        need(path!=reg['deferred_training_pool']['local'],'Pool read forbidden before dispatch handoff')
        need(sha(path)==digest,'Registered pin changed: '+path)
    need(not list(Path(reg['empty_pycache']).iterdir()),'Parent cache not empty')
    need(sum(reg['financial_limits'][k] for k in ('setup_seconds','teardown_reserve_seconds'))
         +reg['campaign_total_seconds']==reg['financial_limits']['maximum_assigned_seconds'],
         'Global cap does not include all phases')
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
         'Exact062 lease lost; remote work must stop')


def lease_cas(reg, expected, replacement, *, before=None):
    path = Path(reg['state_path'])
    with (path.parent/'horizon-ledger.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read(path)
        need(state.get('active_long_campaign') == expected, 'Exact shared lease CAS differs')
        if before is not None:
            before()
        state['active_long_campaign'] = replacement
        temporary = path.parent/('.cloud062-state-'+str(os.getpid()))
        with temporary.open('x') as stream:
            json.dump(state, stream, sort_keys=True, allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        _base.fsync_dir(path.parent)


def owner_reader(reg):
    """Owner decoder uses only its pinned stdlib common module."""
    source = Path(reg['owner_source_root'])
    load(source/'common.py', reg['source_pins'][str(source/'common.py')], 'common')
    return load(source/'receipts.py', reg['source_pins'][str(source/'receipts.py')], 'dodge064_decoder')


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
    for job in reg['jobs']:
        backup=docs['outputs/'+job['id']+'/job-backup-complete.json']
        need(backup['status']=='backup_acknowledged_before_next_job'
             and backup['job_nonce']==reg['job_nonce'] and backup['registration_sha256']==reg['registration_sha256']
             and backup['elapsed_including_backup_seconds']<reg['work_seconds']+reg['receipt_seconds'], 'Job backup/exposure wall proof differs')
    return result


class LiveFence:
    """Independent price monitor and serialized control writer; no rearming."""
    def __init__(self, reg, transport, budget, clock, journal, *, lease_check=lease_guard):
        self.reg, self.transport, self.budget, self.clock = reg, transport, budget, clock
        self.journal, self.lease_check = journal, lease_check
        self.stop = threading.Event(); self.work_stop = threading.Event()
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
        need(now-self.budget.allocation_start < 22520, 'Work deadline reached; teardown reserve required')

    def meter_once(self):
        started = self.clock.now()
        snapshot = self.transport.snapshot(timeout=15)
        with self.lock:
            self.lease_check(self.reg)
            result = self.budget.observe(snapshot['raw'], snapshot['assignments'], self.transport.endpoint,
                self.clock.now(), request_started=started, phase=self.phase)
            need(result['receipt_retrieval_admitted'] if self.phase=='retrieval' else result['work_admitted'], 'Financial phase permit absent')
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
            self.transport.put_json('/content/dodge064/control.json', control, timeout=8)

    def loop(self, action):
        while not self.stop.wait(15):
            if action.__name__=='renew_once' and self.work_stop.is_set():break
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

    def quiesce(self):
        self.work_stop.set()
        with self.lock:self.phase='retrieval'

    def close(self):
        self.stop.set()
        for thread in self.threads:
            thread.join(timeout=25)
            need(not thread.is_alive(), 'Control/billing writer did not drain')


def safety_modules(reg):
    import importlib
    root=Path(reg['owner_source_root'])/'result_safety'
    load(root/'__init__.py',reg['source_pins'][str(root/'__init__.py')],'dodge064_safety')
    return tuple(importlib.import_module('dodge064_safety.'+name) for name in ('custody','lifecycle','transport'))


def validate_boundary(reg,files,*,kind,job,update,allow_fixtures=False):
    need(allow_fixtures is False,'Production boundary cannot admit CPU fixtures')
    files=Path(files);spec=next(x for x in reg['jobs'] if x['id']==job)
    owner=owner_reader(reg);common=sys.modules['common']
    need(not any('.partial' in p.name or 'failure' in p.name for p in files.iterdir()),'Failure in backup boundary')
    rows=[json.loads(line) for line in (files/'updates.jsonl').read_text().splitlines()]
    partial=dict(reg,updates=update)
    common.validate_telemetry(rows,partial,spec)
    if kind=='checkpoint':
        descriptor=read(files/'checkpoint-descriptor.json')
        need(descriptor['update']==update and descriptor['sha256']==sha(files/'checkpoint.pt')
             and descriptor['filename']=='checkpoint-%03d.pt'%update,'Checkpoint descriptor/content differs')
        for key in ('model_fingerprint','adam_fingerprint'):
            need(isinstance(descriptor[key],str) and len(descriptor[key])==64,'Checkpoint state fingerprint absent')
    else:
        worker,supervisor=(read(files/name) for name in ('worker-result.json','supervisor-result.json'))
        for body,stage in ((worker,'worker'),(supervisor,'supervisor')):
            need(body['schema']=='dodge_colab_training_stage_v1' and body['stage']==stage
                 and body['status']=='complete' and body['job']==job
                 and all(body[k]==reg[k] for k in ('record','job_nonce','registration_sha256','payload_sha256'))
                 and body['training_frames']==reg['frame_target'] and body['trained_weights_saved'] is True
                 and not body.get('fixture_only',False),'Job boundary identity/exposure differs')
        need(worker['completed_updates']==36 and worker['device']=='cuda' and worker['device_index']==0
             and worker['stream_sha256']==reg['replicas'][spec['replica']]['stream_sha256']
             and supervisor['child_returncode']==0 and supervisor['owned_group_absent'] is True
             and supervisor['worker_result_sha256']==sha(files/'worker-result.json'),'Job exit/stream proof differs')
        for endpoint in worker['checkpoints']:
            need(sha(files/endpoint['filename'])==endpoint['sha256'],'Saved checkpoint changed before job backup')
        need([x['update'] for x in worker['checkpoints']]==[12,24,36],'Job saved endpoints differ')
        for key,cap in [('peak_group_RSS_bytes',reg['rss_bytes']),('peak_CUDA_driver_process_bytes',reg['cuda_driver_bytes'])]:
            need(0<supervisor[key]<cap,'Job observed resource cap exceeded')
        need(supervisor['elapsed_seconds']<reg['work_seconds']+reg['receipt_seconds'],'Job wall cap exceeded')
    return dict(status='boundary_verified')


class Controller:
    def __init__(self,reg,plan,output,transport,budget_class,*,clock=None):
        self.reg,self.plan,self.output,self.transport,self.budget_class=reg,plan,Path(output),transport,budget_class
        self.clock=clock or Clock();self.fence=None;self.process=None;self.endpoint=None
        self.budget=None;self.safe=None;self.receiver=None;self.wire=None
        self.phase='preflight';self.recovering=False;self.release_consumed=False;self.recovery_deadline=None;self._quiesced=False;self.journal=None
        self.custody,self.lifecycle,self.wire_module=safety_modules(reg)

    def owned(self,endpoint):
        owned=read(self.output/'owned-endpoint.json')
        need(endpoint==owned['endpoint'] and owned['notebook_hash']==self.reg['job_nonce']
             and owned['name']==self.reg['session_name'],'Durable exact VM ownership differs')

    def current_session(self):
        from types import SimpleNamespace
        private=read(self.reg['cli_config_path']).get(self.reg['session_name'])
        need(isinstance(private,dict) and private.get('endpoint')==self.endpoint,'Private current session differs')
        return SimpleNamespace(**private)

    def read_guard(self):
        lease_guard(self.reg)
        now=self.clock.now()
        need(now-self.budget.allocation_start<self.reg['financial_limits']['maximum_assigned_seconds']-self.reg['result_safety']['teardown_seconds'],
             'Result retrieval must reserve exact teardown')
        if self.recovering:
            need(now<self.recovery_deadline,'Bounded recovery deadline')
            need(self.fence is None or not self.fence.failed.is_set(),'Monitor failed; only exact cleanup permitted')
        else:self.fence.check()

    def quiesce(self):
        if self._quiesced:return
        self._quiesced=True
        if self.fence is not None:self.fence.quiesce()
        if self.endpoint is not None:
            try:self.transport.put_json('/content/dodge064/cancel.requested',{'requested':True},timeout=8)
            except BaseException:pass
        if self.fence is not None:
            # Join only the renewal writer here; billing keeps its own15s loop.
            for thread in self.fence.threads:
                if thread is self.fence.threads[-1]:thread.join(timeout=25)

    def prepare_receiver(self):
        self.wire=self.wire_module.ContentsTransport(session_provider=self.current_session,
            endpoint=self.endpoint,remote_root='/content/dodge064/exports',verify_owned_endpoint=self.owned,
            guard=self.read_guard,python=self.reg['sdk_python'])
        self.receiver=self.custody.Receiver(self.output/'durable-results',self.reg,
            get_json=self.wire.get_json,get_chunk=self.wire.get_chunk,put_ack=self.wire.put_ack,guard=self.read_guard)
        self.safe=self.lifecycle.StageController(self.receiver,jobs=tuple(x['id'] for x in self.reg['jobs']),
            challenge_sha256=self.reg['storage_challenge']['sha256'],endpoint=self.endpoint,guard=self.read_guard,
            cancel_work=self.quiesce,verify_owned_endpoint=self.owned,release_owned_endpoint=self.release_VM,
            validate_boundary=lambda files,**kw:validate_boundary(self.reg,files,**kw),
            validate_terminal=lambda files,**kw:validate_training(Path(files)/'training-artifacts.tar',self.reg,
                read(self.output/'runtime-admission.json')),
            emergency_authorized=lambda reason:(reason=='recovery_deadline' and self.clock.now()>=self.recovery_deadline)
                or (reason=='guard_failure' and self.fence is not None and self.fence.failed.is_set()))

    def wait_simple_stage(self,stage):
        self.fence.check();self.process=self.transport.start(self.reg['stage_script'],stage,self.reg['stage_timeout_seconds'][stage])
        began=self.clock.now()
        while self.process.poll() is None:
            self.fence.check()
            need(self.clock.now()-began<self.reg['stage_timeout_seconds'][stage],'Stage wall deadline')
            if stage=='preflight' and self.safe.next_sequence==1:
                pointer=self.wire.next_pointer(1)
                if pointer is not None:self.safe.sync(pointer)
            self.fence.failed.wait(.1)
        code=self.process.wait();self.fence.check()
        body=json.loads(self.wire.get_json(stage+'-exit.json'))
        need(code==0 and body['status']=='complete' and body['observed_exit_code']==0
             and body['directly_reaped'] is True and body['owned_group_absent'] is True
             and all(body[k]==self.reg[k] for k in ('record','job_nonce','registration_sha256','expected_lease_sha256')),
             'Remote stage exit proof failed; CLI exit0 is insufficient')
        save(self.output/(stage+'-exit.json'),body)
        if stage=='preflight':need(self.safe.next_sequence==2,'Storage preflight never acknowledged')
        return body

    def release_VM(self,endpoint):
        need(not self.release_consumed,'Sole VM release already consumed');self.owned(endpoint)
        self.release_consumed=True
        if self.fence is not None:self.fence.close()
        self.transport.close_control()
        snapshot=self.transport.snapshot(timeout=15)
        absent_before=not any(a['endpoint']==endpoint for a in snapshot['assignments'])
        if not absent_before:
            save(self.output/'release-requested.json',dict(status='coordinator_release_requested',endpoint=endpoint))
            try:self.transport.unassign(endpoint,timeout=40)
            except BaseException:pass
        started=self.clock.now();final=self.transport.snapshot(timeout=15)
        need(not any(a['endpoint']==endpoint for a in final['assignments']),'Exact owned absence unconfirmed')
        accounting=self.budget.final(final['raw'],final['assignments'],self.clock.now(),request_started=started)
        teardown=dict(accounting,status='owned_assignment_absent',endpoint=endpoint,
            removal_classification='assignment_absent_before_our_release_request' if absent_before else 'coordinator_requested_release',
            provider_termination_reason='unknown' if absent_before else None,release_requested_by_coordinator=not absent_before)
        save(self.output/'teardown.json',teardown)
        if absent_before:raise ValueError('Assignment absent before our request; provider reason unknown')
        return teardown

    def recover(self):
        self.recovering=True
        self.recovery_deadline=min(self.clock.now()+self.reg['result_safety']['recovery_seconds'],
            self.budget.allocation_start+self.reg['financial_limits']['maximum_assigned_seconds']-self.reg['result_safety']['teardown_seconds'])
        self.quiesce()
        if self.process is not None:self.transport.stop_local(self.process)
        recovered=False;attempted=False
        while self.clock.now()<self.recovery_deadline:
            if self.safe is None or not self.safe.training_started:break
            if self.fence is not None and self.fence.failed.is_set():break
            try:
                pointer=self.wire.next_pointer(900000)
                if pointer is not None and not attempted:
                    attempted=True;self.receiver.mirror(pointer)
                    body,files=self.receiver.verify(900000)
                    path=files/'training-artifacts.tar'
                    inventory=owner_reader(self.reg).decode_archive(path,sha(path),self.reg,
                        require_complete=False,allow_fixtures=False)
                    docs=archive_documents(path)
                    supervisors=[body for body in docs.values() if body.get('stage')=='supervisor']
                    need(supervisors and all(body.get('owned_group_absent') is True and type(body.get('child_returncode')) is int for body in supervisors),
                         'Recovery worker process-group proofs incomplete')
                    stage=self.wire.read_stage_exit()
                    proof=json.loads(stage) if stage is not None else {}
                    need(proof.get('directly_reaped') is True and proof.get('owned_group_absent') is True
                         and all(proof.get(k)==self.reg[k] for k in ('record','job_nonce','registration_sha256','expected_lease_sha256')),
                         'Recovery remote direct reap absent')
                    save(self.output/'failure-archive-preserved.json',dict(status='complete_failure_inventory_backed_up',
                        archive_sha256=sha(path),inventory=inventory,campaign_success=False,remote_stage=proof))
                    recovered=True;break
            except BaseException as error:
                if not (self.output/'recovery-first-failure.json').exists():
                    save(self.output/'recovery-first-failure.json',dict(exception_type=type(error).__name__,
                        http_status=getattr(error,'http_status',None),phase='bounded_artifact_recovery',campaign_success=False))
                # No transfer retries; earlier chunk copies and partials remain.
                attempted=True
            time.sleep(.25)
        if self.endpoint is None:return
        if recovered or self.safe is None or not self.safe.training_started:
            save(self.output/'failed-release-permit.json',dict(status='failed_run_backed_up_or_native_work_unopened',
                recovered_archive=recovered,training_ever_admitted=False if self.safe is None else self.safe.training_started,
                campaign_success=False,endpoint=self.endpoint))
            self.release_VM(self.endpoint)
        else:self.safe.emergency_release('guard_failure' if self.fence is not None and self.fence.failed.is_set() else 'recovery_deadline')

    def run(self):
        reg=self.reg
        began=self.clock.now();initial=self.transport.snapshot(timeout=15)
        need(not initial['assignments'] and initial['raw']['assignmentsCount']==0 and initial['session'] is None,
             'Fresh free account and unused session required')
        self.budget_class(initial['raw']['currentBalance'],self.clock.now())
        output_path(self.output,create=True)
        save(self.output/'dispatch.claimed',dict(record=reg['record'],notebook_hash=reg['job_nonce'],
            registration_sha256=reg['registration_sha256'],expected_lease=reg['expected_lease'],
            review_sha256=self.plan['review_sha256'],coordinator_pid=os.getpid()))
        allocation_called=False;failure=None
        try:
            self.phase='lease_acquisition';disposition=failed062_disposition()
            save(self.output/'failure-disposition.json',disposition)
            lease_cas(reg,reg['previous_lease'],reg['expected_lease'])
            save(self.output/'lease-handoff.json',dict(status='exact_non_null_failed_campaign_handoff',
                previous_lease=reg['previous_lease'],replacement_lease=reg['expected_lease'],never_cleared_to_null=True,
                failure_disposition_sha256=sha(self.output/'failure-disposition.json'),registration_sha256=reg['registration_sha256']))
            lease_guard(reg);need(sha(reg['deferred_training_pool']['local'])==reg['pool_sha256'],'Authorized pool changed')
            self.phase='allocation';self.budget=self.budget_class(initial['raw']['currentBalance'],self.clock.now())
            save(self.output/'allocation.claimed',dict(notebook_hash=reg['job_nonce'],session_name=reg['session_name'],started_at=self.budget.allocation_start))
            allocation_called=True;owned=self.transport.allocate(reg['job_nonce'],timeout=45)
            self.endpoint=self.transport.endpoint=owned['endpoint'];self.owned(self.endpoint)
            self.journal=(self.output/'billing.jsonl').open('x');journal=self.journal
            self.transport.prepare_control(timeout=15)
            self.fence=LiveFence(reg,self.transport,self.budget,self.clock,journal);self.fence.start()
            self.prepare_receiver()
            self.phase='upload'
            for remote in ['/content/dodge064','/content/dodge064/inputs','/content/dodge064/inputs/challenge']:
                self.fence.check();self.transport.mkdir(remote,timeout=15)
            for item in reg['uploads']:
                self.fence.check();self.transport.upload(item['local'],item['remote'],timeout=60)
            self.transport.upload(self.plan['registration_path'],'/content/dodge064/registration.json',timeout=15)
            self.process=self.transport.start(reg['unpack_script'],'unpack',60)
            until=self.clock.now()+60
            while self.process.poll() is None:
                self.fence.check();need(self.clock.now()<until,'Source assembly deadline');time.sleep(.1)
            need(self.process.wait()==0,'Source assembler CLI failed')
            self.phase='storage_rehearsal';self.wait_simple_stage('preflight')
            self.phase='build';proof=self.wait_simple_stage('build')
            self.transport.download('/content/dodge064/build-artifacts.tar',self.output/'build-artifacts.tar',timeout=30)
            self.transport.download('/content/dodge064/runtime/dodge_rl/_native.cpython-313-x86_64-linux-gnu.so',self.output/'native-runtime.so',timeout=30)
            need(proof['terminal_export_sha256']==sha(self.output/'build-artifacts.tar'),'Build exit/archive binding differs')
            cert=validate_build(self.output/'build-artifacts.tar',self.output/'native-runtime.so',reg)
            cert_bytes=canonical(cert)
            with tarfile.open(self.output/'build-artifacts.tar','r:') as archive:cert_bytes=archive.extractfile('native-build.json').read()
            admission={k:reg[k] for k in ('record','job_nonce','registration_sha256','expected_lease_sha256')}
            admission.update(status='accepted_preimport_build_certificate',accepted_build_certificate_sha256=hashlib.sha256(cert_bytes).hexdigest(),
                native_imports=0,constructor_calls=0,actual_native_binary_sha256=cert['native_binary_sha256'])
            admission_sha=save(self.output/'runtime-admission.json',admission)
            self.transport.put_json('/content/dodge064/runtime-admission.json',admission,timeout=8,exact_bytes=(self.output/'runtime-admission.json').read_bytes())
            self.fence.train(admission_sha);self.phase='training'
            self.process=self.safe.start_training(lambda:self.transport.start(reg['stage_script'],'train',reg['stage_timeout_seconds']['train']))
            self.safe.wait_stage(self.process,next_pointer=self.wire.next_pointer,read_stage_exit=self.wire.read_stage_exit)
            archive=self.receiver.exports/('%06d'%len(self.safe.steps))/'files/training-artifacts.tar'
            os.link(archive,self.output/'training-artifacts.tar');_base.fsync_dir(self.output)
            self.phase='retrieval';self.quiesce()
            # The normal-release guard now uses the finite retrieval phase.
            self.recovering=True;self.recovery_deadline=min(self.clock.now()+180,self.budget.allocation_start+22820)
            teardown=self.safe.normal_release()
            result=dict(status='training_complete_pending_coordinator_acceptance',record='DODGE-064',
                registration_sha256=reg['registration_sha256'],job_nonce=reg['job_nonce'],
                training_archive_sha256=sha(self.output/'training-artifacts.tar'),teardown_sha256=sha(self.output/'teardown.json'),
                runtime_admission_sha256=sha(self.output/'runtime-admission.json'),durable_terminal_proof_sha256=sha(self.receiver.root/'terminal-backup-verified.json'),
                campaign_success_pending_acceptance=True)
            save(self.output/'parent-terminal-audit.json',result)
            self.journal.close();return result
        except BaseException as error:
            failure=dict(status='first_failure_preserved_lease_held',record='DODGE-064',phase=self.phase,
                exception_type=type(error).__name__,http_status=getattr(error,'http_status',None),
                failure_class=getattr(error,'failure_class',None),safe_reason=getattr(error,'safe_reason',None),monitoring_reason=None if self.fence is None else self.fence.error,
                allocation_called=allocation_called,campaign_success=False)
            save(self.output/'first-failure.json',failure)
            try:
                if self.endpoint is None and (self.output/'owned-endpoint.json').exists():
                    owned=read(self.output/'owned-endpoint.json');self.owned(owned['endpoint'])
                    self.endpoint=self.transport.endpoint=owned['endpoint']
                if self.endpoint is not None and not self.release_consumed:self.recover()
                elif allocation_called and self.endpoint is None:
                    save(self.output/'cleanup-first-failure.json',dict(status='allocation_ambiguous_no_unowned_stop'))
            except BaseException as cleanup:
                save(self.output/'cleanup-first-failure.json',dict(status='cleanup_unconfirmed',exception_type=type(cleanup).__name__))
            finally:
                if self.fence is not None:
                    try:self.fence.close()
                    except BaseException:pass
                try:self.transport.close_control()
                except BaseException:pass
                if self.journal is not None:self.journal.close()
            raise ValueError('DODGE-064 failed; exact lease and all backups preserved; no retry') from None


def accept_terminal(plan, output, transport):
    reg = validate_plan(plan); reg['registration_sha256'] = plan['registration_sha256']
    output = output_path(output)
    need(not (output/'coordinator-terminal-audit.json').exists(), 'Accepted audit already exists; do not rerun')
    need(not any(('failure' in p.name and p.name!='failure-disposition.json') or '.partial' in p.name
                 for p in output.rglob('*')), 'Failure/partial evidence present')
    handoff=read(output/'lease-handoff.json')
    need(handoff['previous_lease']==reg['previous_lease'] and handoff['replacement_lease']==reg['expected_lease']
         and handoff['never_cleared_to_null'] is True
         and handoff['failure_disposition_sha256']==sha(output/'failure-disposition.json')
         and read(output/'failure-disposition.json')==failed062_disposition(), 'Durable exact handoff differs')
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
    channel_rows=[json.loads(line) for line in (output/'control-transport.jsonl').read_text().splitlines()]
    need(not any(row['phase'].endswith('failure') for row in channel_rows),'Control transport failure present')
    closed=[row for row in channel_rows if row['actor']=='parent' and row['phase']=='closed']
    need(len(closed)==1 and closed[0]['directly_reaped'] is True,'Control child direct reap absent')
    try:os.kill(closed[0]['child_pid'],0)
    except ProcessLookupError:pass
    else:raise ValueError('Control child PID still live or reused; inspect without release')
    for key, name in [('training_archive_sha256','training-artifacts.tar'), ('teardown_sha256','teardown.json'),
                      ('runtime_admission_sha256','runtime-admission.json')]:
        need(terminal[key] == sha(output/name), 'Terminal receipt changed')
    custody,lifecycle,_=safety_modules(reg)
    def forbidden(*a,**kw):raise GuardError('Terminal audit cannot fetch missing backups')
    receiver=custody.Receiver(output/'durable-results',reg,get_json=forbidden,get_chunk=forbidden,put_ack=forbidden,guard=lambda:lease_guard(reg))
    for sequence in range(1,len(lifecycle.schedule(tuple(x['id'] for x in reg['jobs']),(12,24,36)))+1):receiver.verify(sequence)
    need(terminal['durable_terminal_proof_sha256']==sha(output/'durable-results/terminal-backup-verified.json')
         and (output/'durable-results/normal-release-permit.json').is_file(),'Durable result/release audit differs')
    validate_build(output/'build-artifacts.tar', output/'native-runtime.so', reg)
    validate_training(output/'training-artifacts.tar', reg, read(output/'runtime-admission.json'))
    need(sha(reg['deferred_training_pool']['local']) == reg['pool_sha256'], 'Training pool postflight differs')
    fresh = transport.snapshot(timeout=15)
    need(not fresh['assignments'] and fresh['raw']['assignmentsCount'] == 0, 'Fresh account absence required')
    audit = dict(status='accepted_training_campaign', record='DODGE-064', campaign_success=True,
                 registration_sha256=reg['registration_sha256'], parent_terminal_sha256=sha(output/'parent-terminal-audit.json'),
                 review_sha256=plan['review_sha256'], evaluation_games=0, promoted=False)
    audit_sha = None
    def durable_acceptance():
        nonlocal audit_sha
        audit_sha = save(output/'coordinator-terminal-audit.json', audit)
    lease_cas(reg, reg['expected_lease'], None, before=durable_acceptance)
    save(output/'lease-release.json', dict(status='coordinator_exact_release_completed', record='DODGE-064',
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
    adapter = load(reg['adapter_path'], reg['source_pins'][reg['adapter_path']], 'dodge064_transport')
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
    budget = load(reg['budget_path'], reg['source_pins'][reg['budget_path']], 'dodge064_budget_run')
    sleeper = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-w', str(os.getpid())],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        print(json.dumps(Controller(reg, plan, args.output, transport, budget.TrainingBudget).run()))
    finally:
        sleeper.terminate(); sleeper.wait(timeout=5)


if __name__ == '__main__':
    main()
