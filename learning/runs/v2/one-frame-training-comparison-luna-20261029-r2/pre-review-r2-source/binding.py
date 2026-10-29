"""Fail-closed bindings for the inert DODGE-013 paired training capsule."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PARENT = ROOT/'learning/runs/v2/one-frame-training-comparison-parent-20261029-r2'
DESIGN = PARENT/'registered-design.json'
PREPARATION = PARENT/'preparation-plan.json'
REUSE_AUDIT = PARENT/'training-reuse-audit.json'
PROTOCOL_PATH = PARENT/'protocol.json'  # Parent-owned final protocol; created outside this source task.
RUN_ID = 'one-frame-training-comparison-luna-20261029-r2'
EXPERIMENT_ID = 'DODGE-013'
PACKAGE_SCHEMA = 'one_frame_training_comparison_registration_v1'
ENVELOPE_SCHEMA = 'one_frame_training_comparison_envelope_v1'
GATE_SCHEMA = 'one_frame_training_comparison_gate_acceptance_v1'
ATTEMPT_SCHEMA = 'one_frame_training_comparison_attempt_v1'
AUDIT_SCHEMA = 'one_frame_training_comparison_terminal_audit_v1'
PENDING_STATE = 'state.one-frame-training-comparison.pending.json'
CANCEL = HERE/'cancel'
TRAINING_POOL = ROOT/'learning/runs/v2/rl-next-experiments-parent-20261027-r1/training-pool512-accepted.json'
CHECKPOINT = ROOT/'learning/runs/v2/uniform2-recovery240-luna-20261028-r1/worker-output/checkpoint-global-420.pt'
CHECKPOINT_META = CHECKPOINT.with_name(CHECKPOINT.name+'.json')
CONFIRM_PARENT = ROOT/'learning/runs/v2/control-frequency-confirmation-parent-20261029-r1'
CONFIRM_PACKAGE = ROOT/'learning/runs/v2/control-frequency-confirmation-luna-20261029-r1'
SOURCE_MANIFEST = HERE/'source-manifest-r2.json'
RUNTIME_SOURCE = ROOT/'learning/runs/v2/one-frame-training-comparison-luna-20261029-r1'
RUNTIME_ROOT = RUNTIME_SOURCE/'runtime-clean-r2'
RUNTIME_MANIFEST = RUNTIME_SOURCE/'runtime-clean-r2-manifest.json'


class Cancelled(RuntimeError):
    pass


def need(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def max_updates_for_target(frame_target, rollout_steps, slots=64):
    need(type(frame_target) is int and frame_target > 0 and type(rollout_steps) is int
         and rollout_steps > 0 and slots == 64, 'update-bound inputs differ')
    return (frame_target + slots*rollout_steps - 1)//(slots*rollout_steps) + 1


def expected_update_bounds(design, qualification):
    target=design['gameplay_frame_target_per_arm']
    by_arm={arm['id']:max_updates_for_target(target,arm['rollout_steps']) for arm in design['arms']}
    return dict(schema='one_frame_training_comparison_update_bounds_v1',
        basis='one minimum gameplay frame per slot decision; include one closing update',
        batch_size=64, formal_by_arm=by_arm, formal_max_updates_per_arm=max(by_arm.values()),
        qualification_max_updates_per_arm=qualification['max_PPO_updates_per_arm'],
        qualification_gameplay_frame_target_per_arm=qualification['gameplay_frame_target_per_arm'],
        qualification_gameplay_frame_cap_per_arm=qualification['gameplay_frame_cap_per_arm'])


def read(path):
    def unique(items):
        out = {}
        for key, value in items:
            need(key not in out, 'duplicate JSON field: '+key)
            out[key] = value
        return out
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def save(path, value):
    """Publish a new receipt durably and refuse replacement."""
    path = Path(path)
    fd, staging = tempfile.mkstemp(prefix='.'+path.name+'.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staging, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(staging)


def verify_pins(pins):
    need(type(pins) is dict, 'pins object required')
    for path, digest in pins.items():
        need(sha(path) == digest, 'pin drift: '+str(path))


def validate_runtime_source_acceptance(reg, gate_pins=None):
    path=PARENT/'runtime-acceptance.json'
    need(path.is_file(), 'independent runtime source acceptance is missing')
    digest=sha(path); doc=read(path)
    need(reg['input_pins'].get(str(path))==digest
        and (gate_pins is None or gate_pins.get(str(path))==digest),
        'registration/phase gate does not pin runtime source acceptance')
    need(doc.get('schema')=='one_frame_training_runtime_source_acceptance_v1'
        and doc.get('status')=='accepted'
        and doc.get('scope')=='source_and_native_provenance_only_actual_training_qualification_pending'
        and doc.get('source_manifest_sha256')==reg['source_manifest_sha256']
        and doc.get('runtime_manifest_path')==reg['runtime_manifest_path']
        and doc.get('runtime_manifest_sha256')==reg['runtime_manifest_sha256']
        and doc.get('runtime_root')==reg['runtime_root']
        and doc.get('actual_training_qualification_required_for_formal') is True,
        'runtime source acceptance lineage or scope differs')
    pins=doc.get('pins')
    changed={Path(name).name for name in doc.get('changed_python_members',[])}
    need(type(pins) is dict and pins.get(doc.get('review_path'))==doc.get('review_sha256')
        and pins.get(reg['runtime_manifest_path'])==reg['runtime_manifest_sha256']
        and changed=={'ppo.py','seeded_training.py','curriculum.py'}
        and all(type(doc.get(key)) is str and len(doc[key])==64 for key in
            ('native_binary_sha256','base_runtime_manifest_sha256')),
        'runtime review evidence pin differs')
    verify_pins(pins)
    return doc


def protocol():
    return read(PROTOCOL_PATH)


def design():
    return read(DESIGN)


def runtime_files():
    manifest = read(RUNTIME_MANIFEST)
    root = Path(manifest['runtime_root']).resolve()
    actual = {str(path.relative_to(root)) for path in root.rglob('*')
              if path.is_file() or path.is_symlink()}
    need(actual == set(manifest['files']), 'runtime member set differs')
    for name, digest in manifest['files'].items():
        path = root/name
        need(path.is_file() and not path.is_symlink() and sha(path) == digest,
             'runtime member hash or link differs: '+name)
    return manifest, root


def check_source():
    manifest = read(SOURCE_MANIFEST)
    need(manifest.get('schema') == 'one_frame_training_comparison_source_manifest_v1'
         and manifest.get('run_id') == RUN_ID, 'source manifest identity differs')
    for name, digest in manifest['files'].items():
        path = HERE/name
        need(path.is_file() and not path.is_symlink() and sha(path) == digest,
             'source member differs: '+name)
    return manifest


def check_lease(reg):
    state = read(reg['state_path'])
    need(state.get('active_long_campaign') == reg['expected_lease'],
         'exact training-pair lease changed')
    for key in ('active_inference_diagnostic', 'active_inference_campaign', 'active_inference_lease'):
        need(state.get(key) is None, 'inference lease blocks training pair: '+key)
    need(state.get('training_hold', {}).get('active') is not True, 'training hold is active')
    work = state.get('one_frame_training_comparison_work')
    need(type(work) is dict and all(work.get(key) == value
         for key, value in reg['expected_parent_work_identity'].items()),
         'parent training-comparison work identity changed')
    need(work.get('protocol_path') == str(PROTOCOL_PATH)
         and work.get('protocol_sha256') == reg['protocol_sha256'],
         'main ledger protocol binding changed')
    need(not os.path.lexists(reg.get('cancel_path', CANCEL)), 'parent cancellation marker exists')


def validate_static(reg, *, check_streams=False, require_registered=False, phase=None,
                    require_resource_acceptance=True):
    phase = phase or reg.get('phase', 'formal')
    if phase == 'qualification':
        return validate_qualification_static(reg, require_registered=require_registered)
    need(phase == 'formal', 'registration phase differs')
    p = protocol()
    d = design()
    need(reg.get('schema') == PACKAGE_SCHEMA and reg.get('status') in ('source_review_pending', 'parent_registered'),
         'registration schema/status differs')
    need(reg.get('launch_authority') is False and reg.get('experiment_id') == EXPERIMENT_ID
         and reg.get('run_id') == RUN_ID == p['run_id'], 'run identity or launch boundary differs')
    need(p.get('schema') == 'one_frame_training_comparison_protocol_v1'
         and p.get('status') == 'parent_approved_pre_run_protocol'
         and p.get('launch_authority') is False, 'final parent protocol is not fixed for pre-run use')
    need(reg['protocol_path'] == str(PROTOCOL_PATH) and reg['protocol_sha256'] == sha(PROTOCOL_PATH),
         'parent protocol path/hash differs')
    need(p['design_path'] == str(DESIGN) and p['design_sha256'] == sha(DESIGN)
         and p['preparation_path'] == str(PREPARATION) and p['preparation_sha256'] == sha(PREPARATION)
         and p['reuse_audit_path'] == str(REUSE_AUDIT) and p['reuse_audit_sha256'] == sha(REUSE_AUDIT),
         'parent preparation inputs differ')
    need(reg['design_sha256'] == p['design_sha256']
         and reg['preparation_sha256'] == p['preparation_sha256']
         and reg['reuse_audit_sha256'] == p['reuse_audit_sha256'], 'registration parent inputs differ')
    if require_registered:
        need(reg.get('status') == 'parent_registered', 'parent registration is not accepted')
    need(reg['source_manifest_path'] == str(SOURCE_MANIFEST)
         and reg['source_manifest_sha256'] == sha(SOURCE_MANIFEST), 'source binding differs')
    need(reg['runtime_root'] == str(RUNTIME_ROOT)
         and reg['runtime_manifest_path'] == str(RUNTIME_MANIFEST)
         and reg['runtime_manifest_sha256'] == sha(RUNTIME_MANIFEST), 'runtime binding differs')
    need(reg['checkpoint_path'] == p['checkpoint']['path'] == str(CHECKPOINT)
         and reg['checkpoint_sha256'] == p['checkpoint']['sha256'] == d['checkpoint_sha256']
         and reg['checkpoint_global_update'] == p['checkpoint']['global_update'] == 420
         and reg['checkpoint_phase_update'] == p['checkpoint']['phase_update'] == 804
         and reg['checkpoint_cumulative_update'] == p['checkpoint']['cumulative_update'] == 852,
         'starting checkpoint differs')
    need(reg['arms'] == d['arms'] and reg['gameplay_frame_target_per_arm'] == d['gameplay_frame_target_per_arm'],
         'registered arm or frame contract differs')
    need(reg['recovery_checkpoint_gameplay_interval'] == p['recovery_checkpoint_gameplay_interval'],
         'formal recovery snapshot interval differs from parent protocol')
    need(reg['training_pair_seed'] == d['training_pair_seed'] and reg['evaluation'] == d['evaluation'],
         'registered pair seed or evaluation contract differs')
    qualification=read(PARENT/'qualification-protocol.json')
    need(reg['update_bounds']==expected_update_bounds(d,qualification),
         'formal/qualification update bounds differ from the pinned frame contracts')
    need(reg['limits']['work_seconds'] == d['proposed_full_work_cap_seconds'] == p['limits']['work_seconds']
         and reg['limits']['rss_bytes'] == d['RSS_bytes']
         and reg['limits']['mps_bytes'] == d['MPS_driver_bytes'], 'hard limits differ from parent design')
    need(reg['limits']['per_arm_gameplay_frames'] == p['limits']['per_arm_gameplay_frames']
         and reg['gameplay_frame_target_per_arm'] == p['gameplay_frame_target_per_arm']
         and reg['training_pair_seed'] == p['training_pair_seed'], 'frame/seed contract differs')
    need(reg['limits']['total_seconds'] == p['limits']['total_seconds']
         and reg['limits']['cleanup_seconds'] == p['limits']['cleanup_seconds']
         and reg['limits']['postflight_seconds'] == p['limits']['postflight_seconds']
         and reg['expected_lease'] == p['expected_lease'] and reg['lease_key'] == p['lease_key']
         and reg['state_path'] == p['state_path'], 'parent wall or lease contract differs')
    need(reg['evaluation_seeds'] == p['evaluation']['seeds']
         and reg['evaluation_reservation_sha256'] == p['evaluation']['reservation_sha256'],
         'registered D9 evaluation cohort differs')
    need(all(reg['input_pins'].get(path) == digest for path,digest in p['input_pins'].items()),
         'registration omitted or changed a parent input pin')
    need(all(reg['expected_parent_work_identity'].get(key) == value
         for key,value in p['expected_parent_work_identity'].items()), 'parent ledger identity differs')
    need(reg['no_promotion'] is True and reg['automatic_selection'] is False
         and reg['training_eligible'] is False, 'training authority boundary differs')
    expected_interpreter = ROOT/'python/.venv/bin/python'
    need(Path(reg['interpreter']) == expected_interpreter and expected_interpreter.is_absolute()
         and expected_interpreter.resolve().is_file()
         and sha(expected_interpreter.resolve()) == reg['interpreter_sha256'],
         'actual lexical project venv or interpreter binary differs')
    need(reg['input_pins'].get(str(CHECKPOINT)) == d['checkpoint_sha256']
         and reg['input_pins'].get(str(CHECKPOINT_META)) == p['checkpoint']['metadata_sha256'],
         'checkpoint pins differ')
    verify_pins(reg['input_pins'])
    if require_resource_acceptance and reg.get('status') == 'parent_registered':
        validate_runtime_source_acceptance(reg)
        validate_resource_acceptance(reg)
    if check_streams:
        from seeds import validate_registered_streams
        validate_registered_streams(reg)
    return True


def validate_qualification_static(reg, *, require_registered=False):
    """Validate disposable phase registration against the formal inert draft and q protocol."""
    q = read(PARENT/'qualification-protocol.json')
    need(reg.get('phase') == 'qualification' and reg.get('schema') == PACKAGE_SCHEMA
         and reg.get('run_id') == q['run_id'] and reg.get('formal_run_id') == RUN_ID,
         'qualification phase identity differs')
    need(reg['status'] in ('source_review_pending', 'parent_registered')
         and reg['launch_authority'] is False, 'qualification registration authority differs')
    if require_registered:
        need(reg['status'] == 'parent_registered', 'parent qualification registration is not accepted')
    formal_path = Path(reg['formal_registration_path'])
    need(sha(formal_path) == reg['formal_registration_sha256'], 'formal registration pin differs')
    formal = read(formal_path)
    validate_static(formal, phase='formal',require_resource_acceptance=False)
    need(formal.get('status') in ('source_review_pending','parent_registered')
         and formal.get('launch_authority') is False,
         'formal registration draft is not inert')
    need(q['status'] == 'preparation_pending_source_acceptance' and q['launch_authority'] is False
         and q['no_checkpoint_writes'] is True and q['no_evaluation_seed_use'] is True
         and q['no_formal_weight_reuse'] is True and q['no_retry'] is True,
         'qualification protocol boundary differs')
    need(reg['protocol_path'] == formal['protocol_path']
         and reg['protocol_sha256'] == formal['protocol_sha256']
         and reg['source_manifest_path'] == formal['source_manifest_path']
         and reg['source_manifest_sha256'] == formal['source_manifest_sha256']
         and reg['runtime_manifest_path'] == formal['runtime_manifest_path']
         and reg['runtime_manifest_sha256'] == formal['runtime_manifest_sha256']
         and reg['runtime_root'] == formal['runtime_root']
         and reg['checkpoint_path'] == formal['checkpoint_path']
         and reg['checkpoint_sha256'] == q['checkpoint_sha256'] == formal['checkpoint_sha256']
         and reg['arms'] == formal['arms'] and reg['training_pair_seed'] == q['training_pair_seed']
         and reg['exclusion_union'] == formal['exclusion_union'],
         'qualification common source/runtime/checkpoint/arm pins differ')
    need(reg['gameplay_frame_target_per_arm'] == q['gameplay_frame_target_per_arm']
         and reg['update_bounds'] == formal['update_bounds']
         and reg['streams']['capacity_per_slot'] == q.get('qualification_capacity_per_slot',
             formal['streams']['qualification_capacity_per_slot'])
         and reg['streams']['qualification_slot_stream_digests']
             == formal['streams']['qualification_slot_stream_digests'],
         'qualification target/update/stream contract differs')
    need(reg['limits'] == q['limits'], 'qualification phase limits differ from parent protocol')
    for field in ('expected_lease', 'lease_key', 'state_path', 'expected_parent_work_identity',
                  'execution_root', 'output', 'attempt_claim_path', 'launch_marker_path', 'import_policy'):
        need(reg[field] == q[field], 'qualification phase path/lease differs: '+field)
    root = Path(q['execution_root']).resolve()
    need(reg.get('cancel_path') == str(root/'cancel'), 'qualification cancellation path differs')
    for field in ('output', 'attempt_claim_path', 'launch_marker_path', 'import_policy'):
        values = [reg[field]] if field != 'import_policy' else [reg[field]['pycache_prefix']]
        need(all(Path(value).resolve().is_relative_to(root) for value in values),
             'qualification output/claim/cache escapes execution root')
    need(reg['input_pins'].get(str(PARENT/'qualification-protocol.json')) == sha(PARENT/'qualification-protocol.json'),
         'qualification protocol pin differs')
    verify_pins(reg['input_pins'])
    validate_runtime_source_acceptance(reg)
    return True


def validate_resource_acceptance(reg, gate_pins=None):
    path=PARENT/'resource-acceptance.json'
    need(path.is_file(), 'accepted measured resource projection is missing')
    digest=sha(path); acceptance=read(path); q=read(PARENT/'qualification-protocol.json')
    need(reg['input_pins'].get(str(path))==digest
        and (gate_pins is None or gate_pins.get(str(path))==digest),
        'formal registration/parent gate does not pin resource acceptance')
    need(acceptance.get('schema')=='one_frame_training_comparison_resource_acceptance_v1'
        and acceptance.get('status')=='accepted_measured_projection'
        and acceptance.get('formal_protocol_sha256')==reg['protocol_sha256']
        and acceptance.get('qualification_protocol_sha256')==sha(PARENT/'qualification-protocol.json')
        and acceptance.get('limits')==reg['limits'],
        'measured resource acceptance identity/limits differ')
    need(acceptance.get('accepted_work_seconds')==32400
        and acceptance.get('accepted_total_seconds')==32530
        and type(acceptance.get('margin_included_seconds')) in (int,float)
        and 0<=acceptance['margin_included_seconds']<=32400,
        'measured formal work/total projection exceeds parent limits')
    projection=acceptance.get('projection')
    required=('per_arm_seconds_per_gameplay_frame','training_seconds','evaluation_seconds',
              'checkpoint_seconds','margin_factor','margin_included_seconds')
    need(type(projection) is dict and all(type(projection.get(k)) in (int,float) for k in required)
        and all(projection[k]>=0 for k in required)
        and projection['margin_factor']>=1
        and projection['margin_included_seconds']==acceptance['margin_included_seconds']
        and projection['training_seconds']+projection['evaluation_seconds']
            +projection['checkpoint_seconds']+projection['margin_included_seconds']<=32400,
        'measured projection arithmetic differs or exceeds work cap')
    need('measured' in acceptance.get('claim_scope','').lower()
        and 'final efficacy' in acceptance.get('claim_scope','').lower(),
        'resource acceptance claim scope differs')
    for path_key,sha_key in (('qualification_receipt_path','qualification_receipt_sha256'),
            ('qualification_parent_terminal_audit_path','qualification_parent_terminal_audit_sha256')):
        need(type(acceptance.get(path_key)) is str and sha(acceptance[path_key])==acceptance.get(sha_key),
            'qualification acceptance evidence pin differs: '+path_key)
    receipt=read(acceptance['qualification_receipt_path'])
    parent_audit=read(acceptance['qualification_parent_terminal_audit_path'])
    release=read(Path(acceptance['qualification_parent_terminal_audit_path']).parent/'lease-release.json')
    need(receipt.get('run_id')==q['run_id']
        and receipt.get('registration_sha256')==acceptance.get('qualification_registration_sha256')
        and receipt.get('no_checkpoint_writes') is True and receipt.get('no_evaluation_seed_use') is True
        and receipt.get('checkpoint_writes')==0 and receipt.get('evaluation_calls')==0
        and parent_audit.get('run_id')==q['run_id']
        and parent_audit.get('status')=='parent_terminal_audit_accepted'
        and parent_audit.get('lease_cleared') is False
        and parent_audit.get('evidence',{}).get('status')=='qualification_complete'
        and parent_audit.get('worker_result_sha256')==sha(acceptance['qualification_receipt_path'])
        and release.get('run_id')==q['run_id']
        and release.get('registration_sha256')==acceptance['qualification_registration_sha256']
        and release.get('parent_terminal_audit_sha256')==acceptance['qualification_parent_terminal_audit_sha256']
        and release.get('lease_value_after_release') is None,
        'accepted qualification receipt lineage or disposition differs')
    need(type(acceptance.get('qualification_registration_sha256')) is str
        and len(acceptance['qualification_registration_sha256'])==64,
        'accepted qualification registration digest is malformed')
    need(type(acceptance.get('projection',{}).get('method')) is str
        and acceptance['projection']['method'] and 'measured' in acceptance['claim_scope'].lower()
        and 'final efficacy' in acceptance['claim_scope'].lower(),
        'resource acceptance lacks measured projection method/claim scope')
    return acceptance


def source_acceptance_document(source_manifest_sha256):
    return dict(schema='one_frame_training_comparison_source_acceptance_v1',status='accepted',
        run_id=RUN_ID, source_manifest_sha256=source_manifest_sha256,
        reviewer_independent=True, source_only=True, launch_authority=False,
        training_eligible=False, promoted=False)


def approval_document(registration_sha256, source_manifest_sha256, pins, *, run_id=None):
    return dict(schema='one_frame_training_comparison_gate_acceptance_v1',status='accepted',
        run_id=RUN_ID if run_id is None else run_id, registration_sha256=registration_sha256,
        source_manifest_sha256=source_manifest_sha256, pins=pins,
        launch_authority=False, no_retry=True, no_promotion=True,
        training_eligible=False)


def worker_resources(out, *, strict=False):
    path = Path(out)/'resources.jsonl'
    samples = []
    if path.is_file():
        raw = path.read_bytes()
        need(not strict or (raw and raw.endswith(b'\n')),
             'worker resource journal missing final newline')
        for line in raw.splitlines():
            row = json.loads(line)
            need(type(row.get('rss_bytes')) is int and type(row.get('mps_driver_bytes')) is int,
                 'worker resource sample malformed')
            samples.append(row)
    need(not strict or samples, 'worker resource samples missing')
    return dict(samples=len(samples), peak_rss_bytes=max((x['rss_bytes'] for x in samples), default=0),
        peak_mps_driver_bytes=max((x['mps_driver_bytes'] for x in samples), default=0), rows=samples)


class WorkerResourceTail:
    """Incrementally read complete worker resource rows without rescanning history."""
    def __init__(self, out):
        self.path = Path(out)/'resources.jsonl'
        self.offset = 0
        self.pending = b''
        self.identity = None
        self.samples = 0
        self.peak_rss_bytes = 0
        self.peak_mps_driver_bytes = 0

    def _accept(self, line):
        need(line, 'worker resource journal contains an empty row')
        row = json.loads(line)
        need(type(row.get('rss_bytes')) is int and type(row.get('mps_driver_bytes')) is int,
             'worker resource sample malformed')
        self.samples += 1
        self.peak_rss_bytes = max(self.peak_rss_bytes, row['rss_bytes'])
        self.peak_mps_driver_bytes = max(self.peak_mps_driver_bytes, row['mps_driver_bytes'])

    def poll(self):
        """Read appended bytes; retain a partial final line until newline arrives."""
        try:
            stream = self.path.open('rb')
        except FileNotFoundError:
            need(self.identity is None, 'worker resource journal disappeared after observation')
            return self.summary()
        with stream:
            stat = os.fstat(stream.fileno())
            identity = (stat.st_dev, stat.st_ino)
            need(self.identity is None or identity == self.identity,
                 'worker resource journal inode changed after observation')
            need(stat.st_size >= self.offset,
                 'worker resource journal truncated after observation')
            if self.identity is None:
                self.identity = identity
            stream.seek(self.offset)
            appended = stream.read()
            self.offset += len(appended)
        pieces = (self.pending + appended).split(b'\n')
        self.pending = pieces.pop()
        for line in pieces:
            self._accept(line)
        return self.summary()

    def summary(self, *, strict=False):
        need(not strict or not self.pending, 'worker resource journal ends with a torn row')
        need(not strict or self.samples > 0, 'worker resource samples missing')
        return dict(samples=self.samples, peak_rss_bytes=self.peak_rss_bytes,
            peak_mps_driver_bytes=self.peak_mps_driver_bytes)


def check_pins(pins):
    verify_pins(pins)


LIMITS = {
    'work_seconds': protocol()['limits']['work_seconds'],
    'total_seconds': protocol()['limits']['total_seconds'],
    'cleanup_seconds': protocol()['limits']['cleanup_seconds'],
    'postflight_seconds': protocol()['limits']['postflight_seconds'],
    'rss_bytes': protocol()['limits']['rss_bytes'],
    'mps_bytes': protocol()['limits']['mps_bytes'],
}


def verify_bound(envelope, reg, *, preflight):
    phase=envelope.get('phase',reg.get('phase','formal'))
    validate_static(reg,phase=phase)
    need(envelope['run_id'] == reg['run_id']
         and envelope['registration_sha256'] == sha(envelope['registration']), 'envelope identity differs')
    verify_pins(envelope['pins'])
    source = check_source()
    need(sha(SOURCE_MANIFEST) == reg['source_manifest_sha256'], 'source manifest changed')
    runtime, runtime_root = runtime_files()
    need(str(runtime_root) == reg['runtime_root']
         and sha(RUNTIME_MANIFEST) == reg['runtime_manifest_sha256'], 'runtime manifest/root changed')
    need(source['files'] == reg['source_files'], 'registered source member set differs')
    if preflight:
        check_lease(reg)


def phase_path(reg, name):
    root = Path(reg['execution_root']) if reg.get('phase') == 'qualification' else HERE
    return root/name


def load_envelope(path, digest):
    need(sha(path) == digest, 'envelope hash differs')
    env = read(path)
    reg_path = env['registration']
    need(sha(reg_path) == env['registration_sha256'], 'registration hash differs')
    reg = read(reg_path)
    need(env.get('phase',reg.get('phase','formal')) == reg.get('phase','formal'),
         'envelope/registration phase differs')
    need(env['pins'].get(reg_path) == env['registration_sha256'], 'registration not bound by envelope')
    verify_pins(env['pins'])
    env['path'] = str(Path(path).resolve())
    env['sha256'] = digest
    return env, reg


def worker_command(envelope):
    return [str(ROOT/'python/.venv/bin/python'), '-B', str(HERE/'worker.py'),
            '--envelope', envelope['path'], '--envelope-sha256', envelope['sha256']]
