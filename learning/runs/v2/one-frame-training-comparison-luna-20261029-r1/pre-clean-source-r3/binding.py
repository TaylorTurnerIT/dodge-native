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
PARENT = ROOT/'learning/runs/v2/one-frame-training-comparison-parent-20261029-r1'
DESIGN = PARENT/'registered-design.json'
PREPARATION = PARENT/'preparation-plan.json'
REUSE_AUDIT = PARENT/'training-reuse-audit.json'
PROTOCOL_PATH = PARENT/'protocol.json'  # Parent-owned final protocol; created outside this source task.
RUN_ID = 'one-frame-training-comparison-luna-20261029-r1'
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
SOURCE_MANIFEST = HERE/'source-manifest.json'
RUNTIME_ROOT = HERE/'runtime'
RUNTIME_MANIFEST = HERE/'runtime-manifest.json'


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
    need(not os.path.lexists(CANCEL), 'parent cancellation marker exists')


def validate_static(reg, *, check_streams=False, require_registered=False):
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
    need(reg['training_pair_seed'] == d['training_pair_seed'] and reg['evaluation'] == d['evaluation'],
         'registered pair seed or evaluation contract differs')
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
    if check_streams:
        from seeds import validate_registered_streams
        validate_registered_streams(reg)
    return True


def source_acceptance_document(source_manifest_sha256):
    return dict(schema='one_frame_training_comparison_source_acceptance_v1',status='accepted',
        run_id=RUN_ID, source_manifest_sha256=source_manifest_sha256,
        reviewer_independent=True, source_only=True, launch_authority=False,
        training_eligible=False, promoted=False)


def approval_document(registration_sha256, source_manifest_sha256, pins):
    return dict(schema='one_frame_training_comparison_gate_acceptance_v1',status='accepted',
        run_id=RUN_ID, registration_sha256=registration_sha256,
        source_manifest_sha256=source_manifest_sha256, pins=pins,
        launch_authority=False, no_retry=True, no_promotion=True,
        training_eligible=False)


def worker_resources(out, *, strict=False):
    path = Path(out)/'resources.jsonl'
    samples = []
    if path.is_file():
        for line in path.read_text().splitlines():
            row = json.loads(line)
            need(type(row.get('rss_bytes')) is int and type(row.get('mps_driver_bytes')) is int,
                 'worker resource sample malformed')
            samples.append(row)
    need(not strict or samples, 'worker resource samples missing')
    return dict(samples=len(samples), peak_rss_bytes=max((x['rss_bytes'] for x in samples), default=0),
        peak_mps_driver_bytes=max((x['mps_driver_bytes'] for x in samples), default=0), rows=samples)


def check_pins(pins):
    verify_pins(pins)


def worker_command(envelope, reg=None):
    return [str(ROOT/'python/.venv/bin/python'), '-B', str(HERE/'worker.py'),
            '--envelope', envelope['path'], '--envelope-sha256', envelope['sha256']]


LIMITS = {
    'work_seconds': protocol()['limits']['work_seconds'],
    'total_seconds': protocol()['limits']['total_seconds'],
    'cleanup_seconds': protocol()['limits']['cleanup_seconds'],
    'postflight_seconds': protocol()['limits']['postflight_seconds'],
    'rss_bytes': protocol()['limits']['rss_bytes'],
    'mps_bytes': protocol()['limits']['mps_bytes'],
}


def verify_bound(envelope, reg, *, preflight):
    validate_static(reg)
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


def load_envelope(path, digest):
    need(sha(path) == digest, 'envelope hash differs')
    env = read(path)
    reg_path = env['registration']
    need(sha(reg_path) == env['registration_sha256'], 'registration hash differs')
    reg = read(reg_path)
    need(env['pins'].get(reg_path) == env['registration_sha256'], 'registration not bound by envelope')
    verify_pins(env['pins'])
    env['path'] = str(Path(path).resolve())
    env['sha256'] = digest
    return env, reg


def worker_command(envelope):
    return [str(ROOT/'python/.venv/bin/python'), '-B', str(HERE/'worker.py'),
            '--envelope', envelope['path'], '--envelope-sha256', envelope['sha256']]
