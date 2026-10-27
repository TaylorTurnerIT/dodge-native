"""Strict source-only registration and read-only input validation."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

import driver_binding as binding
import rng_reference as references
import transition

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
STUDY = 'paired-lr-confirmed324-20261026-r1'
VECTOR_PATH = 'learning/runs/v2/confirmed324-seed-vectors-parent-20261026-r1/seed-vectors.json'
VECTOR_SHA = '33ada951394fd3ce674955d43de1919b1cd3c2192e066722e33d5b49549c070b'
R5_MANIFEST = 'learning/runs/v2/confirmed324-private-bindings-r5-parent-validation-20261026-r1/source-manifest.json'
R5_MANIFEST_SHA = '2b0caf00a5d5e765726d080fd5647211190e472d74ffb33b3466e477cb2906a9'
REF_ROOT = 'learning/runs/v2/confirmed324-rng-reference-parent-20261026-r3'
REF_REG_SHA = '0150cfcdbec53ff4322f72e5fa224cb6a914f3505ea732c0722511b5e031c398'
PARENT_RECEIPT = 'learning/runs/v2/D2-retained300-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json'
ARMS = tuple(sorted(transition.ARMS))
PPO = dict(gamma=.995, gae_lambda=.95, learning_rate=3e-5, adam_eps=1e-5,
           clip_coef=.2, vf_coef=.5, ent_coef=.01, max_grad_norm=.5,
           update_epochs=4, minibatch_size=512, target_kl=.03, reward_scale=.1)
SCHEDULE = dict(updates=60, cumulative_origin=372, cumulative_first=373,
                cumulative_last=432, phase_start=325, phase_end=384,
                candidate_local_updates=[12,24,36,48,60])
LIMITS = dict(work_seconds=1790, total_seconds=1800, cleanup_seconds=10,
              rss_bytes=6442450944, mps_bytes=6442450944, retries=0)
REG_FIELDS = {'schema','status','study_id','run_id','pair_id','arm','replica','backend',
              'vector','reference','parent_checkpoint_sha256','parent_receipt_sha256',
              'expected_parent_fingerprints','initial_episode_indices','exclusion_union',
              'ppo','schedule','limits','input_manifest_sha256','source_manifest_sha256',
              'runtime_root','runtime_versions','output','attempt_claim_path','interpreter',
              'import_policy','state_path','expected_lease','launch_marker_path'}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def verify_inputs():
    manifest = read(HERE / 'input-manifest.json')
    need(manifest['root'] == str(ROOT), 'checkout binding differs')
    for name, digest in manifest['pins'].items():
        need(sha(ROOT / name) == digest, 'read-only input changed: ' + name)
    need(sha(ROOT / R5_MANIFEST) == R5_MANIFEST_SHA, 'authoritative R5 manifest changed')
    for name, digest in read(ROOT / R5_MANIFEST)['files'].items():
        need(sha(name) == digest, 'authoritative R5 member changed: ' + name)
        if Path(name).name in ('attempt_claim.py','driver_binding.py','fingerprints.py','rng_reference.py','transition.py'):
            need(sha(HERE / Path(name).name) == digest, 'owned R5 copy differs')
    binding.verify_pinned_sources(ROOT)
    runtime = Path(manifest['runtime_root'])
    actual = {str(p.relative_to(ROOT)) for p in runtime.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts}
    expected = {p for p in manifest['pins'] if p.startswith(str(runtime.relative_to(ROOT)) + '/')}
    need(actual == expected, 'runtime member set differs')
    producing_registration = ROOT / 'learning/runs/v2/D2-retained300-continuation-freeze-20261026-r5/registration.json'
    need(sha(producing_registration) == '8a60dc80f1ebe03c43bf18eebf75199e14f207b677570ac2d6d4368ddfcb0f79', 'accepted producing registration differs')
    accepted_runtime = read(producing_registration)
    members = {str((ROOT / path).relative_to(runtime)):manifest['pins'][path] for path in expected}
    need(members == accepted_runtime['runtime_continuity']['member_sha256']
         and manifest['runtime_versions'] == accepted_runtime['runtime_versions']
         and accepted_runtime['runtime_continuity']['source_runtime_root'] == str(runtime)
         and accepted_runtime['runtime_sha256'] == '2cf10e9f056f41b39dc17845192e9adf553a5f699546d4f5dcea764a23e36b31',
         'accepted runtime member/version/lineage binding differs')
    need(sha(ROOT / VECTOR_PATH) == VECTOR_SHA, 'seed-vector source pin differs')
    return manifest


def verify_source_manifest(expected):
    need(sha(HERE / 'source-manifest.json') == expected, 'owned source manifest differs')
    manifest = read(HERE / 'source-manifest.json')
    for name, digest in manifest['files'].items():
        path = HERE / name
        need(path.resolve().parent == HERE and sha(path) == digest, 'owned source changed: ' + name)


def episode_controls(vector):
    """Stdlib transcription of pinned seed.rs wrapping tuple hash; no RNG draw."""
    mask = (1 << 64) - 1
    def mix(value):
        value &= mask
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
        return value ^ (value >> 31)
    rows = []
    ranges = transition.EXPECTED_EXCLUSION_RANGES
    for slot, episode in enumerate(vector['env_control']['episode_indices']):
        base = mix(vector['seeds']['env_master_seed'] ^ 0x444F4447455F5632) ^ mix(slot + 0x9E3779B97F4A7C15) ^ mix(episode + 0xD1B54A32D192ED03)
        counter = 0
        while True:
            seed = mix(base ^ mix(counter + 0x94D049BB133111EB)) >> 32
            if not any(lo <= seed <= hi for lo, hi in ranges):
                break
            counter += 1
        rows.append(dict(slot=slot, episode_index=episode, first_actual_seed=seed, rejection_counter=counter))
    transition.validate_exclusion_controls(ranges, rows)
    need([r['first_actual_seed'] for r in rows[:4]] == vector['env_control']['first_slot_actual_seeds'], 'first seed control differs')
    actual = [row['first_actual_seed'] for row in rows]
    need(hashlib.sha256(b''.join(v.to_bytes(4,'big') for v in actual)).hexdigest() == vector['env_control']['all_slots_actual_seed_sha256'], 'all-slot seed digest differs')
    need(len(set(actual)) == vector['env_control']['distinct_actual_seeds'] == 64 and sum(v == 0 for v in actual) == vector['env_control']['zero_actual_seeds'] == 0, 'seed uniqueness/zero controls differ')
    return rows


def verify_registration(reg):
    need(type(reg) is dict and set(reg) == REG_FIELDS, 'registration schema fields differ')
    need(reg['schema'] == 'paired_confirmed324_worker_registration_v2' and reg['status'] == 'parent_registered', 'unregistered worker refused')
    need(reg['study_id'] == STUDY and reg['backend'] == 'mps', 'study/backend differs')
    need(type(reg['replica']) is int and reg['replica'] in (1,2,3) and reg['arm'] in ARMS, 'replica/arm differs')
    need(reg['pair_id'] == f'{STUDY}-replica-{reg["replica"]}', 'pair identity differs')
    need(reg['run_id'] == reg['pair_id'] + ('-A' if reg['arm'] == ARMS[0] else '-B'), 'run identity differs')
    need(reg['parent_checkpoint_sha256'] == references.ACCEPTED_CHECKPOINT_SHA256 and reg['parent_receipt_sha256'] == references.PARENT_RECEIPT_SHA256, 'parent identity differs')
    need(reg['expected_parent_fingerprints'] == transition.EXPECTED_PARENT, 'parent fingerprints differ')
    need(reg['ppo'] == PPO and reg['schedule'] == SCHEDULE and reg['limits'] == LIMITS, 'learner/schedule/limits differ')
    need(reg['exclusion_union'] == [list(row) for row in transition.EXPECTED_EXCLUSION_RANGES], 'exclusion union differs')
    need(sha(HERE / 'input-manifest.json') == reg['input_manifest_sha256'], 'input manifest differs')
    verify_source_manifest(reg['source_manifest_sha256'])
    manifest = verify_inputs()
    need(reg['runtime_root'] == manifest['runtime_root'] and reg['runtime_versions'] == manifest['runtime_versions'], 'runtime identity differs')
    vectors = read(ROOT / VECTOR_PATH)
    vector = next(v for v in vectors['vectors'] if v['replica'] == reg['replica'])
    need(reg['vector'] == vector, 'full seed vector/control differs')
    transition.validate_seeds(vector['seeds'])
    parent = read(ROOT / PARENT_RECEIPT)
    acceptance_path = ROOT / 'learning/runs/v2/expanded-confirmation-parent-20261026-r1/parent-acceptance.json'
    need(sha(acceptance_path) == '3e84979c4c8da76d0f98666a23f90eb15c1e813ca5edf1001e19daebaf4d5bbd', 'confirmed324 acceptance changed')
    acceptance = read(acceptance_path)
    need(acceptance['checkpoint_sha256'] == references.ACCEPTED_CHECKPOINT_SHA256 and acceptance['candidate_cumulative_counters'] == parent['candidate_cumulative_counters'], 'confirmed parent acceptance binding differs')
    need(reg['initial_episode_indices'] == vector['env_control']['episode_indices'] == parent['next_episode_indices'], 'parent episode indices differ')
    need(parent['checkpoint_sha256'] == reg['parent_checkpoint_sha256'] and parent['candidate_phase_update'] == 324 and parent['candidate_cumulative_counters']['updates'] == 372, 'parent counters differ')
    need(parent['learner_fingerprints'] == dict(model=transition.EXPECTED_PARENT['model'], optimizer=transition.EXPECTED_PARENT['Adam'], rng=transition.EXPECTED_PARENT['RNG']), 'parent receipt fingerprints differ')
    audit = read(ROOT / REF_ROOT / 'parent-terminal-audit.json')
    need(audit['status'] == 'accepted_three_initial_CPU_MPS_generator_references' and audit['registration_sha256'] == REF_REG_SHA, 'reference parent acceptance differs')
    accepted = next(r for r in audit['references'] if r['replica'] == reg['replica'])
    reference = dict(receipt_path=accepted['path'], receipt_sha256=accepted['sha256'], vector_sha256=accepted['vector_sha256'])
    need(reg['reference'] == reference, 'accepted reference binding differs')
    digests = references.load_bound_reference(receipt_path=reference['receipt_path'], expected_receipt_sha256=reference['receipt_sha256'], expected_study_id=STUDY, expected_replica=reg['replica'], expected_seed_vector=vector['seeds'], expected_vector_sha256=vector['vector_sha256'], expected_torch_version=manifest['runtime_versions']['torch'])
    need(set(digests) == {'torch_cpu_global_seed','action_sampler_torch_mps_seed'}, 'exactly two generator digests required')
    controls = episode_controls(vector)
    need(Path(reg['interpreter']) == ROOT / 'python/.venv/bin/python' and Path(sys.executable).resolve() == Path(reg['interpreter']).resolve(), 'project interpreter differs')
    output = Path(reg['output'])
    need(output.is_absolute() and output.resolve() == output and output.parent == ROOT / 'learning/runs/v2' and output.name == reg['run_id'] and not output.exists(), 'destination must be a new run directory')
    claim = Path(reg['attempt_claim_path'])
    need(claim == output.parent / (reg['run_id'] + '.transition.claimed') and not claim.exists(), 'fixed attempt destination missing or spent')
    for key in ('state_path','launch_marker_path'):
        need(Path(reg[key]).is_absolute() and Path(reg[key]).is_file(), 'parent-owned gate missing: ' + key)
    need(type(reg['expected_lease']) is dict and reg['expected_lease'].get('run_id') == reg['run_id'] and reg['expected_lease'].get('study_id') == STUDY and reg['expected_lease'].get('parent_checkpoint_sha256') == reg['parent_checkpoint_sha256'], 'lease identity differs')
    need(read(reg['state_path']).get('active_long_campaign') == reg['expected_lease'], 'exact parent lease differs')
    return dict(manifest=manifest, vector=vector, parent=parent, controls=controls)
