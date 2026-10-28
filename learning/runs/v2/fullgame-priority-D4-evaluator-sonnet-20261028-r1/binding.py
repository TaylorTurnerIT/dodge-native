"""D4 terminal60 evaluation adapters for the copied direct-owner watchdog; stdlib only.

Adapted from the proven progressive1000 full-run evaluator. Only the study, cohort,
producer lineage, statistics and limits differ; the clean common evaluator source is reused.
"""
from __future__ import annotations
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
V2 = ROOT/'learning/runs/v2'
SOURCE = V2/'progressive1000-opening-maintenance-runtime-parent-20261027-r1'
SOURCE_SHA = '51aa867e43b3a047f057ef07069c9939615d4a1db2939e484d0f974cac87b85e'
RUNTIME_SHA = '84e730ee638344460fe9bda693bc986879c39621fa7ef99ba35afd50b0f78b69'
STUDY = 'fullgame-seed-priority-luna-20261027-r1'
EVAL_RUN_ID = 'fullgame-priority-D4-terminal60-evaluation-sonnet-20261028-r1'
LEASE_KIND = 'fullgame_priority_d4_terminal60_evaluation'
ARMS = ('uniform', 'opening_priority')
PARENT_ID = 'parent324'
POLICIES = tuple(f'replica-{r}-{arm}' for r in (1, 2, 3) for arm in ARMS)+(PARENT_ID,)
PRODUCER_POLICIES = POLICIES[:-1]
D4 = (0xD4000000, 0xD40003FF)
D5 = (0xD5000000, 0xD50007FF)
SEEDS = list(range(D4[0], D4[1]+1))
EPISODES = len(POLICIES)*len(SEEDS)
MILESTONES = (1000, 2000, 4000, 8000, 12000, 18000)
EVAL_RNG_SEED = 2026102802
BOOTSTRAP = dict(seed=2026102801, draws=2000, confidence=.95, unit='paired_evaluation_seed',
                 training_seed_uncertainty='three_training_pairs_descriptive_only')
RNG_SEMANTICS = ('Before each policy: random, numpy, torch and torch.mps are reseeded with evaluation_rng_seed; '
                 'categorical sampling uses the global MPS stream in fixed seed-batch order. Policies share the '
                 'stream start, not per-seed action draws once trajectories diverge. No action-mode selection.')
SEMANTICS = dict(difficulty=2, normal_start=True, patterns_enabled=True, powerups_enabled=True, action_repeat=4,
                 raw_frame_cap=18000, cutoff_enabled=False, action_mode='sampled_categorical', row_count=1024,
                 parent_evaluations=1, policies=7, planned_episodes=EPISODES, same_reward=True,
                 same_entity_transformer=True, rng_semantics=RNG_SEMANTICS)
CAP = 6*1024**3
RAW_CAP = EPISODES*(18000+13)
STEP_CAP = EPISODES*18000
WALL_FACTOR = 3
LIMITS = {}
LIMIT_FIELDS = {'work_seconds', 'total_seconds', 'cleanup_seconds', 'rss_bytes', 'mps_bytes', 'raw_frames',
                'constructors', 'native_steps', 'resets', 'retries'}
GATES = ('independent_source_review', 'producer_identity', 'inference_compatibility',
         'cohort_reservation_and_freshness', 'provenance_scope', 'd5_unopened', 'resource_calibration',
         'registered_rng', 'supervisor_cleanup', 'registration', 'exactly_once')
NEURAL_INPUTS = ('global_feats', 'entity_feats', 'entity_types', 'entity_mask')
INFERENCE_MEMBERS = ('dodge_rl/__init__.py', 'dodge_rl/_native.cpython-312-darwin.so', 'dodge_rl/checkpoints.py',
                     'dodge_rl/identity.py', 'dodge_rl/models/__init__.py', 'dodge_rl/models/teacher.py')
PRODUCER_ONLY_MEMBERS = {'dodge_rl/ppo.py', 'dodge_rl/seed_priority.py', 'dodge_rl/seeded_training.py'}
REGISTRY = V2/'rl-next-experiments-parent-20261027-r1/seed-priority-parent-registry.json'
FIRST_HOME = V2/'fullgame-seed-priority-fresh-attempt-proposal-parent-20261027-r1'
REMAIN_HOME = V2/'fullgame-priority-remaining-r3-bindings-sonnet-20261027-r1'
PARENT_RECEIPT = 'learning/runs/v2/D2-retained300-parent-terminal-audit-20261026-r1/retained-best-candidate-receipt.json'
PRIOR_EVALUATOR = V2/'progressive1000-full-run-evaluator-parent-20261027-r2'
PROVENANCE = dict(
    scope='parent_accepted_recorded_accepted324_learner_family_history',
    claim='D4 is disjoint from the recorded accepted324 entity-teacher lineage, related recorded attempts and '
          'checkpoint selection/evaluation history. This is not a universal workspace nonuse claim.',
    historical_file_roles_unresolved=122, universal_workspace_nonuse_claim=False,
    live_ledger_pinned_as_immutable_history=False, d4_role='frozen full-run ranking/development cohort; not confirmation',
    d5_range=list(D5), d5_state='unopened')


class Cancelled(RuntimeError):
    pass


def need(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            result.update(block)
    return result.hexdigest()


def read(path):
    def unique(items):
        result = {}
        for key, value in items:
            need(key not in result, 'duplicate JSON field: '+key)
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def save(path, value):
    """Durable exclusive publication used by the accepted supervisor."""
    path = Path(path)
    fd, staging = tempfile.mkstemp(prefix='.'+path.name+'.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.link(staging, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(staging)


def check_pins(pins):
    need(type(pins) is dict, 'pins must be an object')
    for path, digest in pins.items():
        need(sha(path) == digest, 'pin drift: '+path)


def producer_layout(replica, arm):
    """Predeclared producer home and terminal60 paths. Nothing here reads the filesystem."""
    run_id = f'{STUDY}-replica-{replica}-{arm}'
    home = (FIRST_HOME if (replica, arm) == (1, 'uniform') else REMAIN_HOME)/run_id
    checkpoint = home/'worker-output/checkpoint-global-060-integrity.pt'
    return dict(policy_id=f'replica-{replica}-{arm}', run_id=run_id, replica=replica, arm=arm, home=str(home),
        registration_path=str(home/'registration-final.json'), audit_path=str(home/'parent-terminal-audit.json'),
        parent_execution_path=str(home/'parent-execution.json'), execution_exit_path=str(home/'execution-exit.json'),
        lease_release_path=str(home/'lease-release.json'),
        artifact_manifest_path=str(home/'dispatch/artifact-manifest.json'),
        worker_result_path=str(home/'worker-output/worker-result.json'),
        checkpoint_path=str(checkpoint), sidecar_path=str(checkpoint)+'.json')


def predeclared_layouts():
    return [producer_layout(r, arm) for r in (1, 2, 3) for arm in ARMS]


def contracts():
    need(sha(SOURCE/'source-manifest.json') == SOURCE_SHA, 'clean evaluator source manifest differs')
    for name, digest in read(SOURCE/'source-manifest.json')['files'].items():
        path = SOURCE/name
        need(path.resolve().is_relative_to(SOURCE) and not path.is_symlink(), 'source member escapes')
        need(sha(path) == digest, 'clean evaluator source differs: '+name)
    if str(SOURCE) not in sys.path:
        sys.path.insert(0, str(SOURCE))
    c = importlib.import_module('contracts')
    need(Path(c.__file__).resolve() == SOURCE/'contracts.py', 'contracts origin differs')
    return c


def analysis():
    contracts()
    module = importlib.import_module('expanded_eval')
    need(Path(module.__file__).resolve() == SOURCE/'expanded_eval.py', 'analysis origin differs')
    return module


def verify_dependencies(reg):
    anchor = read(HERE/'dependency-binding.json')
    check_pins({anchor['registration_path']: anchor['registration_sha256'],
                anchor['inventory_path']: anchor['inventory_sha256']})
    old = read(anchor['registration_path']); inventory = read(anchor['inventory_path'])
    need(reg['interpreter'] == old['interpreter'], 'dependency interpreter differs')
    for path, item in inventory['pins'].items():
        need(old['pins'].get(path) == item['sha256'] == sha(path), 'dependency drift: '+path)
    executable = str(Path(reg['interpreter']).resolve(strict=True))
    need(sha(executable) == old['pins'][executable], 'interpreter bytes differ')
    return dict(checked=len(inventory['pins']), scope=inventory['scope'])


def projected_work_seconds(elapsed, raw_frames):
    """Prior proven evaluator rate, scaled to the registered raw-frame ceiling with a fixed margin."""
    need(elapsed > 0 and raw_frames > 0, 'positive prior cost required')
    return math.ceil(WALL_FACTOR*elapsed/raw_frames*RAW_CAP+10)


def validate_limits(limits):
    need(type(limits) is dict and set(limits) == LIMIT_FIELDS, 'evaluation limit fields differ')
    need(all(type(value) is int for value in limits.values()), 'integer limits required')
    need(0 < limits['work_seconds'] <= 86400 and limits['total_seconds'] == limits['work_seconds']+10
         and limits['cleanup_seconds'] == 10, 'wall/cleanup bounds differ')
    need(limits['rss_bytes'] == limits['mps_bytes'] == CAP and limits['raw_frames'] == RAW_CAP
         and limits['constructors'] == EPISODES and limits['native_steps'] == STEP_CAP
         and limits['resets'] == 0 and limits['retries'] == 0, 'memory/raw/constructor/step/reset/retry bounds differ')


def check_lease(reg):
    state = read(reg['state_path'])
    need(state.get('active_long_campaign') == reg['expected_lease'], 'exact evaluation lease changed')
    need(all(state.get(key) is None for key in ('active_inference_diagnostic', 'active_inference_campaign',
                                                'active_inference_lease')), 'conflicting inference lease')


def learner_identity(reg, registration_sha, c):
    """Reproduces the producer's matched learner identity from its registration (producer successor_identity)."""
    return dict(schema='dodge_fullgame_seed_priority_learner_identity_v1', study_id=STUDY,
        run_id=reg['run_id'], pair_id=reg['pair_id'], replica=reg['replica'], arm=reg['arm'],
        backend=reg['backend'], parent_lineage=dict(checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256,
            receipt_sha256=c.references.PARENT_RECEIPT_SHA256, phase_update=324, cumulative_update=372,
            fingerprints=dict(c.transition.EXPECTED_PARENT)),
        successor_runtime=dict(runtime_manifest_sha256=reg['runtime_manifest_sha256'],
            source_manifest_sha256=reg['source_manifest_sha256'], runtime_versions=reg['runtime_versions']),
        registration_sha256=registration_sha, shared_config=reg['shared_config'], seed_vector=reg['vector'],
        training_pool_sha256=reg['training_pool_sha256'], slot_stream_sha256=reg['slot_stream_sha256'],
        native_seed_mode='evaluation_explicit_seed_list', training_pool_role='training_only',
        exclusion_union=reg['exclusion_union'], neural_inputs=list(NEURAL_INPUTS), schedule=reg['schedule'])


def identity_hash(identity):
    return hashlib.sha256(canonical(identity)).hexdigest()


def covers(union, low, high):
    return any(lo <= low and hi >= high for lo, hi in union)


def normalize_union(unions):
    """Producers store the same ranges in registry order; the clean validator needs a sorted list."""
    sets = [{tuple(r) for r in union} for union in unions]
    need(sets and all(x == sets[0] for x in sets), 'producers disagree on exclusion union')
    return [list(r) for r in sorted(sets[0])]


def check_runtime_members(actual, clean):
    """Producer runtime may differ from the clean evaluator only outside the inference members."""
    need(all(actual.get(n) is not None and actual[n] == clean.get(n) for n in INFERENCE_MEMBERS),
         'producer inference member bytes differ from clean evaluator')
    changed = {n for n in set(actual)|set(clean) if actual.get(n) != clean.get(n)}
    need(changed <= PRODUCER_ONLY_MEMBERS, 'unexpected producer runtime difference: '+str(sorted(changed-PRODUCER_ONLY_MEMBERS)))
    return sorted(changed)


def producer_policy(policy, c, *, hash_checkpoint=True, verify_runtime_files=True, layout=None):
    """Check one accepted producer, or the shared parent. Every producer requires a durable accepted audit."""
    need(policy['id'] in POLICIES, 'unregistered policy')
    if policy['id'] == PARENT_ID:
        need(policy['checkpoint_sha256'] == c.references.ACCEPTED_CHECKPOINT_SHA256 and policy['producer'] is None,
             'shared parent differs')
    else:
        layout = layout or producer_layout(int(policy['id'].split('-')[1]), policy['id'].split('-', 2)[2])
        p = policy['producer']; check_pins(p['pins'])
        need(policy['checkpoint_path'] == layout['checkpoint_path'] and p['sidecar_path'] == layout['sidecar_path']
             and p['registration_path'] == layout['registration_path'] and p['audit_path'] == layout['audit_path']
             and p['worker_result_path'] == layout['worker_result_path']
             and p['artifact_manifest_path'] == layout['artifact_manifest_path']
             and p['lease_release_path'] == layout['lease_release_path']
             and p['parent_execution_path'] == layout['parent_execution_path']
             and p['execution_exit_path'] == layout['execution_exit_path'],
             'producer path differs from predeclared terminal60 layout')
        reg = read(p['registration_path']); audit = read(p['audit_path']); worker = read(p['worker_result_path'])
        sidecar = read(p['sidecar_path']); manifest = read(p['artifact_manifest_path'])
        digest = sha(p['registration_path'])
        need(reg['schema'] == 'dodge_seed_priority_registration_v1' and reg['status'] == 'parent_registered'
             and reg['study_id'] == STUDY and reg['run_id'] == layout['run_id'] and reg['backend'] == 'mps'
             and reg['replica'] == layout['replica'] and reg['arm'] == layout['arm']
             and reg['training_pool_role'] == 'training_only', 'producer registration identity differs')
        need(audit['schema'] == 'dodge_seed_priority_parent_terminal_audit_v1'
             and audit['status'] == 'accepted_complete_global_update60_training_receipt'
             and audit['registration_sha256'] == digest and audit['parent_raw_observer_exit_code'] == 0
             and audit['observer_observed_worker_raw_exit'] == 0 and audit['observer_directly_reaped'] is True
             and audit['postflight_inputs_unchanged'] is True
             and audit['terminal']['terminal_update'] == 60 and audit['terminal']['comparison_endpoint'] is True
             and all(audit[k] is False for k in ('automatic_selection', 'promoted', 'training_eligible')),
             'producer terminal audit not accepted')
        release = read(p['lease_release_path'])
        need(release['status'] == 'exact_lease_cleared_after_durable_parent_audit'
             and release['audit_sha256'] == sha(p['audit_path']), 'producer lease not released after durable audit')
        need(audit['output_manifest']['path'] == p['artifact_manifest_path']
             and audit['output_manifest']['sha256'] == sha(p['artifact_manifest_path']), 'producer output manifest differs')
        name = Path(policy['checkpoint_path']).name
        need(manifest.get(name) == policy['checkpoint_sha256'] and manifest.get(name+'.json') == sha(p['sidecar_path'])
             and manifest.get('worker-result.json') == sha(p['worker_result_path']),
             'checkpoint/sidecar/worker result not in audited output manifest')
        endpoint = worker['formal_comparison_endpoint']
        expected = learner_identity(reg, digest, c)
        need(expected == p['expected_identity'], 'producer expected learner identity differs')
        need(worker['status'] == 'completed' and worker['updates'] == 60 and worker['run_id'] == reg['run_id']
             and worker['registration_sha256'] == digest and endpoint == sidecar
             and all(worker.get(k) is False for k in ('training_eligible', 'promoted', 'automatic_selection')),
             'producer result/sidecar differ')
        need(endpoint['global_update'] == 60 and endpoint['phase_update'] == 384 and endpoint['cumulative_update'] == 432
             and endpoint['formal_comparison_endpoint'] is True and endpoint['promoted'] is False
             and endpoint['automatic_selection'] is False and endpoint['training_eligible'] is False
             and endpoint['path'] == policy['checkpoint_path'] and endpoint['sha256'] == policy['checkpoint_sha256']
             and endpoint['identity'] == expected and endpoint['identity_sha256'] == identity_hash(expected)
             and endpoint['parent_checkpoint_sha256'] == c.references.ACCEPTED_CHECKPOINT_SHA256,
             'fixed terminal60 endpoint differs')
        source = Path(reg['runtime_root']).parent
        need(p['source_manifest_sha256'] == reg['source_manifest_sha256'] == audit['source_manifest_sha256']
             == sha(source/'source-manifest.json')
             and p['runtime_manifest_sha256'] == reg['runtime_manifest_sha256'] == audit['runtime_manifest_sha256']
             == sha(source/'runtime-manifest.json'), 'actual producer manifest differs')
        actual = read(source/'runtime-manifest.json')['files']; clean = read(SOURCE/'runtime-manifest.json')['files']
        check_runtime_members(actual, clean)
        if verify_runtime_files:
            for member, member_digest in actual.items():
                need(sha(source/'runtime'/member) == member_digest, 'producer registered runtime byte drift: '+member)
        need(covers(reg['exclusion_union'], *D4) and covers(reg['exclusion_union'], *D5),
             'producer did not exclude reserved D4/D5 cohorts')
    if hash_checkpoint:
        need(sha(policy['checkpoint_path']) == policy['checkpoint_sha256'], 'endpoint bytes drift')


def check_cohort(reg_or_none=None):
    """D4 identity, D5 unopened, and training-pool disjointness against the parent-accepted registry."""
    registry = read(REGISTRY)
    need(registry['future_evaluation_ranges'] == {'D4': list(D4), 'D5': list(D5)}
         and registry['freshness_accepted'] is True and registry['universal_workspace_nonuse_claim'] is False
         and registry['history_closure'] == 'parent_accepted_bounded_scope_no_universal_claim',
         'parent registry cohort/history scope differs')
    need(SEEDS[0] == D4[0] and SEEDS[-1] == D4[1] and len(SEEDS) == 1024 and len(set(SEEDS)) == 1024
         and not any(D5[0] <= s <= D5[1] for s in SEEDS), 'D4 seed list differs or opens D5')
    pool = read(registry['training_pool_path'])
    need(sha(registry['training_pool_path']) == registry['training_pool_file_sha256'], 'training pool file drift')
    seeds = [row['seed'] for row in pool['seeds']]
    need(len(seeds) == 512 and not any(lo <= s <= hi for s in seeds for lo, hi in (D4, D5)),
         'training pool intersects D4/D5')
    need(pool['scope_limits']['historical_file_roles_unresolved'] == PROVENANCE['historical_file_roles_unresolved']
         and pool['scope_limits']['universal_workspace_nonuse_claim'] is False, 'provenance limits differ')
    return registry


REG_FIELDS = {'schema', 'status', 'run_id', 'study_id', 'backend', 'source_manifest_sha256', 'evaluator_source',
    'runtime_root', 'runtime_manifest_sha256', 'input_manifest_sha256', 'runtime_versions', 'policies', 'seeds',
    'cohort', 'exclusion_union', 'evaluation_rng_seed', 'bootstrap', 'semantics', 'limits', 'output',
    'attempt_claim_path', 'launch_marker_path', 'state_path', 'expected_lease', 'interpreter', 'import_policy',
    'input_pins', 'calibration', 'cohort_state', 'history_state', 'reservation_state', 'provenance', 'backend_pins'}
BACKEND_PINS = dict(inference_device='mps', native_simulation='cpu_native_single_thread_per_env',
                    sampling_rng='torch.mps_global_generator', torch_cpu_inference=False)


def validate_static(reg, *, require_registered=True, hash_checkpoints=True, runtime_files=True):
    need(type(reg) is dict and set(reg) == REG_FIELDS, 'registration field set differs')
    need(reg['schema'] == 'fullgame_priority_d4_terminal60_registration_v1' and reg['study_id'] == STUDY,
         'evaluation schema/study differs')
    if require_registered:
        need(reg['status'] == 'parent_registered', 'draft is not launch authority')
    need(reg['backend'] == 'mps' and reg['backend_pins'] == BACKEND_PINS and reg['evaluator_source'] == str(SOURCE)
         and reg['runtime_root'] == str(SOURCE/'runtime'), 'clean common evaluator/backend pins required')
    need(reg['seeds'] == SEEDS and reg['cohort'] == dict(name='D4', range=list(D4), count=1024, d5_range=list(D5),
         d5_state='unopened') and reg['semantics'] == SEMANTICS and reg['provenance'] == PROVENANCE,
         'cohort/semantics/provenance differ')
    need(reg['evaluation_rng_seed'] == EVAL_RNG_SEED, 'registered sampling seed differs')
    need(reg['bootstrap'] == BOOTSTRAP, 'bootstrap contract differs')
    need(reg['cohort_state'] == 'reserved_parent_approved' and reg['history_state'] == 'freshness_parent_approved'
         and reg['reservation_state'] == 'parent_reserved', 'cohort history/reservation not bound')
    validate_limits(reg['limits']); check_pins(reg['input_pins'])
    need(reg['limits']['work_seconds'] == reg['calibration']['proposed_work_seconds'], 'work limit differs from projection')
    prior = reg['calibration']['prior_measurement']
    need(projected_work_seconds(prior['elapsed_seconds'], prior['raw_frames']) == reg['calibration']['proposed_work_seconds']
         and reg['calibration']['projection_factor'] == WALL_FACTOR, 'wall projection arithmetic differs')
    manifest = read(HERE/'source-manifest.json')
    need(sha(HERE/'source-manifest.json') == reg['source_manifest_sha256'], 'owned source manifest differs')
    check_pins({str(HERE/name): digest for name, digest in manifest['files'].items()})
    c = contracts(); c.verify_inputs()
    need(reg['runtime_manifest_sha256'] == RUNTIME_SHA, 'common runtime pin differs')
    c.verify_manifest(SOURCE/'runtime-manifest.json', RUNTIME_SHA, SOURCE/'runtime', exact=True)
    need(sha(SOURCE/'input-manifest.json') == reg['input_manifest_sha256'], 'evaluation input manifest differs')
    need(reg['runtime_versions'] == c.read(SOURCE/'input-manifest.json')['runtime_versions'], 'dependency versions differ')
    c.validate_union(reg['exclusion_union'])
    need(covers(reg['exclusion_union'], *D4) and covers(reg['exclusion_union'], *D5), 'D4/D5 not in exclusion union')
    check_cohort()
    need([p['id'] for p in reg['policies']] == list(POLICIES), 'seven fixed policies/order required')
    for p in reg['policies']:
        need(set(p) == {'id', 'checkpoint_path', 'checkpoint_sha256', 'producer'}, 'policy fields differ')
        producer_policy(p, c, hash_checkpoint=hash_checkpoints, verify_runtime_files=runtime_files)
        if p['producer'] is not None:
            need(normalize_union([read(p['producer']['registration_path'])['exclusion_union']]) == reg['exclusion_union'],
                 'registered exclusion union differs from producer union')
    for key in ('output', 'attempt_claim_path', 'launch_marker_path', 'state_path', 'interpreter'):
        need(Path(reg[key]).is_absolute(), 'absolute path required: '+key)
    need(Path(reg['output']) == HERE/'worker-output' and reg['attempt_claim_path'] == str(HERE/'attempt.claimed')
         and reg['launch_marker_path'] == str(HERE/'launch.claimed'), 'fixed owned paths required')
    need(reg['state_path'] == str(ROOT/'learning/runs/v2-orchestration/state.json') and reg['run_id'] == EVAL_RUN_ID,
         'parent ledger/run identity differs')
    lease = reg['expected_lease']
    need(type(lease) is dict and lease.get('kind') == LEASE_KIND and lease.get('run_id') == reg['run_id']
         and type(lease.get('owner_token')) is str and len(lease['owner_token']) == 32
         and lease.get('RSS_bytes') == lease.get('MPS_driver_bytes') == CAP, 'exact resource lease missing')
    c.cache_check(reg)
    verify_dependencies(reg)
    if require_registered:
        need(reg['calibration']['parent_accepted'] is True, 'parent resource calibration acceptance missing')
    return reg


def validate_checkpoint(state, policy):
    if policy['id'] == PARENT_ID:
        need(state.get('phase_update') == 324, 'accepted parent phase differs')
        return
    need(state.get('schema') == 'progressive1000_integrity_checkpoint_v1'
         and state.get('global_update') == 60 and state.get('phase_update') == 384
         and state.get('cumulative_update') == 432, 'terminal checkpoint counters differ')
    expected = policy['producer']['expected_identity']
    need(state.get('identity') == expected and state.get('identity_sha256') == identity_hash(expected),
         'terminal checkpoint differs from its actual producer identity')
    need(state.get('promoted') is False and state.get('automatic_selection') is False
         and state.get('training_eligible') is False and state.get('formal_comparison_endpoint') is True,
         'checkpoint eligibility flags differ')


def load_envelope(path, digest):
    need(sha(path) == digest, 'envelope external SHA differs')
    e = read(path)
    fields = {'schema', 'status', 'registration', 'registration_sha256', 'launch_approval', 'launch_approval_sha256',
        'source_acceptance', 'source_acceptance_sha256', 'control', 'cancel_path', 'started', 'pins',
        'interpreter_resolved', 'interpreter_sha256'}
    need(set(e) == fields and e['schema'] == 'fullgame_priority_d4_evaluation_envelope_v1'
         and e['status'] == 'parent_bound_exactly_one_run', 'inert envelope')
    reg = read(e['registration']); validate_limits(reg['limits'])
    LIMITS.clear(); LIMITS.update(reg['limits'])
    need(Path(e['control']) == HERE/'dispatch'/reg['run_id'], 'owned dispatch path differs')
    need(Path(e['cancel_path']) == HERE/'cancel', 'fixed cancel path differs')
    need(type(e['started']) in (int, float) and math.isfinite(e['started']), 'finite start required')
    e['self_path'] = str(Path(path).resolve()); e['self_sha256'] = digest
    return e, reg


def approval_document(registration_sha, source_manifest_sha, pins):
    return dict(schema='fullgame_priority_d4_evaluation_gate_acceptance_v1',
        status='approved_exactly_once_fixed_terminal60_d4_evaluation', registration_sha256=registration_sha,
        gates=dict.fromkeys(GATES, 'passed'), pins=pins)


def verify_bound(e, reg, *, preflight):
    check_pins(e['pins'])
    check_pins({e['registration']: e['registration_sha256'], e['launch_approval']: e['launch_approval_sha256'],
                e['source_acceptance']: e['source_acceptance_sha256']})
    validate_static(reg)
    gates = read(e['launch_approval'])
    need(gates['schema'] == 'fullgame_priority_d4_evaluation_gate_acceptance_v1'
         and gates['status'] == 'approved_exactly_once_fixed_terminal60_d4_evaluation'
         and gates['registration_sha256'] == e['registration_sha256']
         and gates['gates'] == dict.fromkeys(GATES, 'passed'), 'external parent gates missing')
    need(read(e['source_acceptance'])['source_manifest_sha256'] == reg['source_manifest_sha256'],
         'independent reviewed source manifest differs')
    check_lease(reg); need(not os.path.lexists(e['cancel_path']), 'parent cancellation present')
    need(str(Path(reg['interpreter']).resolve()) == e['interpreter_resolved']
         and sha(e['interpreter_resolved']) == e['interpreter_sha256'], 'executable differs')
    if preflight:
        need(not os.path.lexists(reg['output']) and not os.path.lexists(reg['attempt_claim_path']),
             'worker attempt already spent')
    need(read(reg['launch_marker_path']) == dict(schema='fullgame_priority_d4_evaluation_spent_marker_v1',
        registration_sha256=e['registration_sha256'], run_id=reg['run_id'], started=e['started']),
        'parent spent marker differs')


def worker_command(envelope, reg):
    return [reg['interpreter'], '-B', str(HERE/'worker.py'), '--envelope', envelope['self_path'],
            '--envelope-sha256', envelope['self_sha256']]


def worker_resources(out, *, strict=False):
    path = Path(out)/'resources.jsonl'; value = dict(samples=0, peak_rss_bytes=None, peak_mps_driver_bytes=None)
    if not path.is_file():
        return value
    for line in path.read_text().splitlines(keepends=True):
        if not line.endswith('\n'):
            need(not strict, 'torn resource journal'); break
        row = json.loads(line)
        need(all(type(row[k]) is int and row[k] >= 0 for k in ('rss_bytes', 'mps_driver_bytes')),
             'invalid resource row')
        value['samples'] += 1
        value['peak_rss_bytes'] = max(value['peak_rss_bytes'] or 0, row['rss_bytes'])
        value['peak_mps_driver_bytes'] = max(value['peak_mps_driver_bytes'] or 0, row['mps_driver_bytes'])
    return value
