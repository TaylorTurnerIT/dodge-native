"""058 receipt writers and decoder share a versioned stage contract.

Workers own exposure and checkpoint declarations. Supervisors own process exits
and sampled driver/RSS observations; they never invent missing worker counters.
Archives preserve claims, stdout/stderr, failures and partial checkpoint files.
"""
from pathlib import Path, PurePosixPath
import hashlib
import io
import json
import tarfile

import common as c

SCHEMA = 'dodge_colab_training_stage_v1'
IDENTITY = ('record', 'job_nonce', 'registration_sha256', 'payload_sha256')
STAGES = {'native_build', 'runtime_import', 'worker', 'supervisor', 'campaign'}


def identity(reg):
    return {key: reg[key] for key in IDENTITY}


def write_stage(path, reg, stage, status, *, job=None, **fields):
    c.need(stage in STAGES and status in ('complete', 'failed'), 'Unknown receipt stage/status')
    # These fields are explicit even on failure; None means unobserved.
    c.need('trained_weights_saved' in fields and 'training_frames' in fields
           and 'native_games' in fields, 'Stage must own weight/exposure semantics')
    value = dict(fields, **identity(reg), schema=SCHEMA, stage=stage, status=status, job=job)
    c.save(path, value)
    return value


def role(name):
    if '.pt' in Path(name).name: return 'checkpoint_or_partial'
    if '.partial' in Path(name).name:return 'partial'
    if name.endswith('.claimed'): return 'claim'
    if name.endswith(('.stdout', '.stderr', '.jsonl', '.log')): return 'log'
    if name.endswith('.json'): return 'receipt_or_metadata'
    raise ValueError('Unregistered artifact role: ' + name)


def write_archive(root, archive_path, reg):
    """Actual producer inventory; logs/claims/partials are intentionally included."""
    root = Path(root)
    inventory = {}
    with tarfile.open(archive_path, mode='x') as archive:
        for path in sorted(root.rglob('*')):
            c.need(not path.is_symlink(), 'Artifact symlink forbidden')
            if not path.is_file(): continue
            name = path.relative_to(root).as_posix()
            inventory[name] = dict(sha256=c.sha(path), bytes=path.stat().st_size, role=role(name))
            archive.add(path, arcname=name, recursive=False)
        manifest = dict(schema='dodge_colab_training_archive_v1', **identity(reg), members=inventory)
        data = c.canonical(manifest)
        item = tarfile.TarInfo('artifact-manifest.json'); item.size = len(data); item.mode = 0o444
        archive.addfile(item, io.BytesIO(data))
    return dict(path=str(archive_path), sha256=c.sha(archive_path), bytes=Path(archive_path).stat().st_size)


def decode_archive(path, expected_sha, reg, *, require_complete=True, allow_fixtures=False):
    c.need(c.sha(path) == expected_sha, 'Downloaded archive digest differs')
    with tarfile.open(path, mode='r:') as archive:
        entries = archive.getmembers(); names = [item.name for item in entries]
        c.need(len(names) == len(set(names)), 'Duplicate archive member')
        c.need(all(item.isfile() and not PurePosixPath(item.name).is_absolute()
                   and '..' not in PurePosixPath(item.name).parts for item in entries), 'Unsafe archive member')
        manifest = json.loads(archive.extractfile('artifact-manifest.json').read())
        c.need(manifest['schema'] == 'dodge_colab_training_archive_v1', 'Archive schema differs')
        c.need(all(manifest.get(k) == reg[k] for k in IDENTITY), 'Archive identity differs')
        c.need(set(names) == {*manifest['members'], 'artifact-manifest.json'}, 'Archive inventory differs')
        decoded = {}; weights = []; failed_paths = []
        for name, expected in manifest['members'].items():
            data = archive.extractfile(name).read()
            c.need(hashlib.sha256(data).hexdigest() == expected['sha256'] and len(data) == expected['bytes'],
                   'Artifact content differs: ' + name)
            c.need(expected['role'] == role(name), 'Artifact role differs')
            if expected['role'] == 'checkpoint_or_partial': weights.append(name)
            if '.partial' in name or 'first-failure' in name: failed_paths.append(name)
            if name.endswith('.json'):
                try:value = json.loads(data)
                except (ValueError,UnicodeError):
                    failed_paths.append(name)
                    if require_complete:raise ValueError('Malformed JSON artifact: '+name)
                    continue
                if value.get('schema') == SCHEMA:
                    c.need(all(value.get(k) == reg[k] for k in IDENTITY), 'Stage identity differs')
                    c.need(value.get('stage') in STAGES, 'Stage schema ownership differs')
                    for key in ('trained_weights_saved', 'training_frames', 'native_games'):
                        c.need(key in value, 'Missing required stage field: ' + key)
                    c.need(allow_fixtures or not value.get('fixture_only',False),'CPU fixture cannot qualify real training')
                    if value['status'] != 'complete': failed_paths.append(name)
                    decoded[name] = value
        if require_complete:
            c.need(not failed_paths, 'Failed/partial artifacts cannot be accepted')
            campaign = decoded.get('campaign-result.json')
            c.need(campaign is not None and campaign['stage'] == 'campaign', 'Campaign receipt absent')
            c.need(campaign['training_frames'] == reg['total_actual_frames'], 'Campaign exposure differs')
            c.need(campaign['elapsed_seconds'] < reg['campaign_total_seconds'], 'Campaign wall cap exceeded')
            if not allow_fixtures:
                build=decoded.get('native-build.json')
                c.need(build is not None and build['stage']=='native_build' and build['native_imports']==0
                       and build['constructor_calls']==0 and build['trained_weights_saved'] is False,
                       'Pre-import build certificate absent/different')
            declared_weights=set()
            for job in reg['jobs']:
                prefix = 'outputs/' + job['id'] + '/'
                body = decoded.get(prefix + 'worker-result.json')
                supervisor = decoded.get(prefix + 'supervisor-result.json')
                c.need(body is not None and body['stage'] == 'worker' and body['job'] == job['id'], 'Worker body absent')
                c.need(body['training_frames'] == reg['frame_target'] and body['completed_updates'] == reg['updates'],
                       'Worker exposure incomplete')
                c.need(body['trained_weights_saved'] is True and len(body['checkpoints']) == 3, 'Training checkpoint declaration absent')
                c.need([item['update'] for item in body['checkpoints']]==reg['checkpoint_updates'],'Checkpoint endpoints differ')
                c.need(body['elapsed_seconds']<reg['work_seconds']+reg['receipt_seconds'],'Worker work/receipt cap exceeded')
                if not allow_fixtures:
                    c.need(body['device']=='cuda' and body['device_index']==0,'Explicit CUDA0 required')
                    c.need(body['stream_sha256']==reg['replicas'][job['replica']]['stream_sha256'],'Worker training stream differs')
                    imported=decoded.get(prefix+'runtime-import.json')
                    c.need(imported is not None and imported['stage']=='runtime_import'
                           and imported['constructor_calls']==0 and imported['native_games']==imported['training_frames']==0
                           and imported['trained_weights_saved'] is False
                           and imported['binary_sha256']==build['native_binary_sha256']
                           and imported['constructor_type_module']=='dodge_rl._native','Runtime import/ABI boundary receipt differs')
                    c.need(body['budget_reached'] is True and body['observed_native_vectors']==reg['updates']*reg['rollout'],
                           'Native vector exposure differs')
                c.need(supervisor is not None and supervisor['stage'] == 'supervisor'
                       and supervisor['child_returncode'] == 0 and supervisor['owned_group_absent'] is True,
                       'Owned process disposition incomplete')
                c.need(supervisor['worker_result_sha256'] == manifest['members'][prefix+'worker-result.json']['sha256'],
                       'Supervisor worker receipt binding differs')
                c.need(body['training_frames'] == supervisor['training_frames']
                       and body['trained_weights_saved'] == supervisor['trained_weights_saved'], 'Stage ownership counters disagree')
                for endpoint in body['checkpoints']:
                    name = prefix + endpoint['filename']
                    declared_weights.add(name)
                    c.need(name in manifest['members'] and manifest['members'][name]['sha256'] == endpoint['sha256'],
                           'Checkpoint artifact absent/different')
                rows = [json.loads(line) for line in archive.extractfile(prefix+'updates.jsonl').read().splitlines()]
                c.validate_telemetry(rows, reg, job)
                qualification=json.loads(archive.extractfile(prefix+'prefix-qualification.json').read())
                c.need(qualification['updates']==2 and qualification['counted_frames']==2*reg['envs']*reg['rollout']
                       and qualification['passive_GAE_return_checks']==[True,True]
                       and qualification['forecast_seconds']<reg['work_seconds']
                       and qualification['full_path_forecast_seconds']<reg['campaign_total_seconds'],'Prefix qualification differs')
                c.need(manifest['members'][prefix+'prefix-qualification.json']['sha256']==body['prefix_sha256'],
                       'Worker prefix receipt binding differs')
                for row in rows:
                    c.need(0<=row['resources']['peak_rss_bytes']<reg['rss_bytes']
                           and 0<=row['resources']['peak_cuda_reserved_bytes']<reg['cuda_driver_bytes'],
                           'Update resource observations differ')
            c.need(set(weights)==declared_weights,'Undeclared/partial checkpoint artifacts')
            c.need(campaign['trained_weights_saved'] is bool(weights), 'Campaign saved-weights inventory differs')
    return dict(status='complete_archive_verified' if require_complete else 'failure_inventory_preserved',
                stages=len(decoded), members=len(names), checkpoint_files=len(weights), failed_paths=failed_paths)
