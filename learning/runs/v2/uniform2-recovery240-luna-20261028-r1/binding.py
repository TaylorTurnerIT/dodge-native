"""Fail-closed contracts for the isolated 240-update Uniform2 recovery; stdlib only.

One campaign: restore the selected terminal60 Uniform2 learner (model, Adam, RNG), train ten fresh-environment
segments of 60 updates (the accepted producer unit), and evaluate the saved starting model and each saved
boundary model on the fresh development cohort D6. Adapts the accepted last-three evaluator binding (watchdog
adapter interface) and the accepted seed-priority training contracts; frozen predecessors are only read and
hash-pinned. Nothing here is launch authority.
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
RUN_ID = 'uniform2-recovery240-luna-20261028-r1'
STUDY_ID = 'uniform2-recovery240-20261028-r1'
PRODUCER_STUDY = 'fullgame-seed-priority-luna-20261027-r1'
PRODUCER_RUN = PRODUCER_STUDY+'-replica-2-uniform'
LEASE_KIND = 'uniform2_recovery240_attempt'
SCHEMA = 'uniform2_recovery240_registration_v1'
ENVELOPE_SCHEMA = 'uniform2_recovery240_envelope_v1'
GATE_SCHEMA = 'uniform2_recovery240_gate_acceptance_v1'
CHECKPOINT_SCHEMA = 'uniform2_recovery240_checkpoint_v1'
IDENTITY_SCHEMA = 'uniform2_recovery240_learner_identity_v1'
MARKER_SCHEMA = 'uniform2_recovery240_spent_marker_v1'
ATTEMPT_SCHEMA = 'uniform2_recovery240_attempt_v1'
AUDIT_SCHEMA = 'uniform2_recovery240_terminal_audit_v1'
DRAFT_STATUS, FINAL_STATUS = 'source_review_pending', 'parent_registered'

# ---- frozen predecessors (read-only, hash-pinned) ----
PRODUCER_PKG = V2/'fullgame-seed-priority-experiment-luna-20261027-r3'
PRODUCER_SOURCE_SHA = 'a29e25b285d2d4651a2d74699929a27578860cfdd9a8d7980ca47c72824d41e2'
RUNTIME_SHA = 'e032a5ab1d609512461e287d372375f1bf28800fb2b13d9c5cf98e20768de986'
EVAL_SOURCE = V2/'progressive1000-opening-maintenance-runtime-parent-20261027-r1'
EVAL_SOURCE_SHA = '51aa867e43b3a047f057ef07069c9939615d4a1db2939e484d0f974cac87b85e'
EXPANDED_EVAL_SHA = '3fd6c1e25b11c7214eff5d4d83ae7a18e3c2b109ce1750db634196075cfc56a0'
LAST3 = V2/'fullgame-priority-D4-last-three-evaluator-sonnet-20261028-r1'
FIRST3 = V2/'fullgame-priority-D4-first-three-evaluator-sonnet-20261028-r1'
HISTORICAL_COPIES = {'observe.py': '95b8758eea4607f5f0812064f44ad5a26615a8a455ec0bf43d9c65bae991f81d',
                     'execute_once.py': '484405674d981ea7db6b5c940d70ffe353a89cff4c3a9f9a810fb25dc219aa3d',
                     'dependency-binding.json': None}
HISTORICAL_POWER_GUARD_SHA = '83a410ae62f813a68d392b6e1eae0a3f47df1a37ea33dba0b34554bbf01c4efb'

# ---- parent inputs ----
PARENT = V2/'uniform2-recovery240-parent-20261028-r1'
PARENT_REPAIR = V2/'uniform2-recovery240-parent-20261028-r1'
STREAM_AUDITOR = HERE/'audit_streams.py'
AUTHORIZATION = PARENT/'user-authorization.json'
INCIDENT_AUDIT = PARENT/'incident-audit.json'
CALIBRATION_ACCEPTANCE = PARENT/'calibration-acceptance.json'
PREDECESSOR = V2/'uniform2-continuation600-luna-20261028-r2'
PREDECESSOR_REG = PREDECESSOR/'registration-final.json'
PREDECESSOR_CHECKPOINT = PREDECESSOR/'worker-output/checkpoint-global-360.pt'
BATTERY_OVERRIDE = V2/'uniform2-continuation600-parent-20261028-r1/battery-power-override.json'
COHORT = V2/'uniform2-continuation600-parent-20261028-r1/development-cohort-reservation.json'
RESTORE_REG = PARENT/'restore-qualification-registration.json'
RESTORE_QUAL = PARENT/'restore-qualification.json'
RESTORE_SOURCE = PARENT/'qualify_restore.py'
PREFIX_AUDIT = PARENT/'original-prefix-stream-audit.json'
PREFIX_AUDITOR = PARENT/'audit_original_prefix.py'
PRODUCER_HOME = V2/'fullgame-priority-remaining-r3-bindings-sonnet-20261027-r1'/PRODUCER_RUN
PARENT_CHECKPOINT = PREDECESSOR_CHECKPOINT
POOL = V2/'rl-next-experiments-parent-20261027-r1/training-pool512-accepted.json'
MAIN_STATE = ROOT/'learning/runs/v2-orchestration/state.json'
PINNED = {  # path -> sha256, every external input the draft binds
    AUTHORIZATION: 'd7a89bfe90705d91b45b26696cdb66d3d76ea305378774560ef36099d608178b',
    BATTERY_OVERRIDE: '58085a78814ca5d595c1220d5ea2c4bf185a8c1a64a87e1e1ebbdc175958b29d',
    COHORT: 'e817dba9ee6e546ccaa425d0dc599cda1894427e6a2eb14df0680a65371bd3c8',
    RESTORE_REG: '8338dadb6ce55dc38cdc2a92e031c926720faa50ffde3e859a6e416f515d715b',
    RESTORE_QUAL: 'ae4a6cec59e1039226c2436390ee3e1c261ef13f235daa1bdcea7fbd0f42ba2c',
    RESTORE_SOURCE: 'f6b574c30c1b5299da405d75ae07b492cc6d74f7c45312dca82343ac72c436a2',
    INCIDENT_AUDIT: '470210f49c28d3a231410c8e1b5556fdfa23f68aef7291fd41caf9df72104898',
    PREFIX_AUDIT: '4f764ab467ffccc8c51556be68e9a15b1bb513e28bc0282536a1758ab7a7b008',
    PREFIX_AUDITOR: '0cd612d133e12fa0530f7ce8719390c8fb8710fdcfa06ec0c60592fc3bcb6f1d',
    PREDECESSOR_REG: '5d3032f30a6793f3322beb30bafe904859424975a551d80127a3e1fa85602d97',
    PARENT_CHECKPOINT: 'f0f651b8aa87c73b64b9f855c794925a278bb7fac82b7b05ae6f6918cd9898bb',
    Path(str(PARENT_CHECKPOINT)+'.json'): 'b3649e41acde86724c82107af5ce2deba1ad5c2eada1e0e0ed8e79f27f334f6a',
    PRODUCER_HOME/'parent-terminal-audit.json': '2a9f1125a4567048e7b332fce481582cd0b8ee86fdfc5bce6a8611a4471cca47',
    PRODUCER_HOME/'registration-final.json': '6b52eab9d2e01e81fded6b3a89a95ff53ded6711ef87c8214d09ca573c78ef59',
    PRODUCER_HOME/'lease-release.json': '2bd08d7d8b3b45209e43c387c1e15b1c01c4cb113aa6ed81bb7f8994826fb34f',
    PRODUCER_HOME/'dispatch/artifact-manifest.json': '4d21d9f976fdc2dadd6cb2ff29ebd832b6d01c9aaa4a262b7feab73e17878017',
    PRODUCER_HOME/'worker-output/worker-result.json': '596302d59f781b91ce5e927e8269f8d75571f0fa6d1ac57c489f78df887298c5',
    POOL: '5093727c2fdabd794267ccbc44a43b1fb29747b545cff645b66b0ad578180f04',
    PRODUCER_PKG/'source-manifest.json': PRODUCER_SOURCE_SHA,
    PRODUCER_PKG/'runtime-manifest.json': RUNTIME_SHA,
    EVAL_SOURCE/'source-manifest.json': EVAL_SOURCE_SHA,
    EVAL_SOURCE/'expanded_eval.py': EXPANDED_EVAL_SHA,
}

# ---- fixed experiment definition ----
CAP = 6*1024**3
UPDATES, SEGMENT_UPDATES = 240, 60
CAMPAIGN_BASE = 360
SEGMENTS = UPDATES//SEGMENT_UPDATES
SLOTS, ROLLOUT = 64, 256
DECISIONS_PER_UPDATE = SLOTS*ROLLOUT
DECISIONS = UPDATES*DECISIONS_PER_UPDATE
PHASE_BASE, CUMULATIVE_BASE = 384, 432
EVAL_UPDATES = [360, 420, 480, 540, 600]
NEW_EVAL_UPDATES = EVAL_UPDATES[1:]
CHECKPOINT_UPDATES = EVAL_UPDATES[1:]
EVAL_RNG_SEED = 2026102803
COHORT_RANGE = (0xD6000000, 0xD60003FF)
SEEDS = list(range(COHORT_RANGE[0], COHORT_RANGE[1]+1))
D4, D5 = (0xD4000000, 0xD40003FF), (0xD5000000, 0xD50007FF)
EPISODES_PER_EVAL = 1024
EVAL_EPISODES = len(EVAL_UPDATES)*EPISODES_PER_EVAL
NEURAL_INPUTS = ('global_feats', 'entity_feats', 'entity_types', 'entity_mask')
PPO = dict(gamma=.995, gae_lambda=.95, learning_rate=3e-5, adam_eps=1e-5, clip_coef=.2, vf_coef=.5, ent_coef=.01,
           max_grad_norm=.5, update_epochs=4, minibatch_size=512, target_kl=.03, reward_scale=.1)
ENVIRONMENT = dict(action_repeat=4, cutoff_enabled=False, difficulty=2, normal_start=True, patterns_enabled=True,
                   powerups_enabled=True, raw_frame_cap=18000)
STARTUP = 13
WORK_SECONDS, CLEANUP_SECONDS, POSTFLIGHT_SECONDS = 14400, 10, 120
TOTAL_SECONDS = WORK_SECONDS+CLEANUP_SECONDS+POSTFLIGHT_SECONDS
# Role budgets. Structural ceilings, not expected cost: a training decision costs <=4 gameplay frames and every
# slot-decision may end an episode (13 startup frames); an evaluation episode costs <=18000 frames + 13 startup.
TRAINING_LIMITS = dict(raw_frames=DECISIONS*(4+STARTUP)+SEGMENTS*SLOTS*STARTUP, constructors=SEGMENTS,
                       native_steps=UPDATES*ROLLOUT, resets=DECISIONS)
EVALUATION_LIMITS = dict(raw_frames=EVAL_EPISODES*(18000+STARTUP), constructors=EVAL_EPISODES,
                         native_steps=EVAL_EPISODES*18000, resets=0)
LIMIT_FIELDS = {'work_seconds', 'total_seconds', 'cleanup_seconds', 'postflight_seconds', 'rss_bytes', 'mps_bytes',
                'retries', 'training', 'evaluation'}
SCHEDULE = dict(updates=UPDATES, global_start=CAMPAIGN_BASE, global_end=CAMPAIGN_BASE+UPDATES, segments=SEGMENTS, segment_updates=SEGMENT_UPDATES,
    decisions_per_update=DECISIONS_PER_UPDATE, decisions_total=DECISIONS, cumulative_first=CUMULATIVE_BASE+CAMPAIGN_BASE+1,
    cumulative_last=CUMULATIVE_BASE+CAMPAIGN_BASE+UPDATES, phase_first=PHASE_BASE+CAMPAIGN_BASE+1, phase_last=PHASE_BASE+CAMPAIGN_BASE+UPDATES,
    checkpoint_global_updates=CHECKPOINT_UPDATES, evaluation_global_updates=EVAL_UPDATES,
    fresh_environment_per_segment=True, constant_learning_rate=3e-5, final_drain=False, promotion=False)
GATES = ('independent_source_review', 'incident_and_original_prefix_audit', 'restore_qualification', 'cohort_reservation_and_freshness',
         'seed_stream_extension', 'selection_rule', 'battery_override_and_native_root_caffeinate',
         'resource_calibration', 'main_lease_and_ledger', 'supervisor_cleanup', 'registration', 'exactly_once')
PROVENANCE = dict(scope='parent_accepted_recorded_accepted324_learner_family_history',
    claim='D6 is disjoint from the recorded accepted324 entity-teacher lineage, related recorded attempts and '
          'checkpoint selection/evaluation history (including D4, which informed the selection). Not a universal '
          'workspace nonuse claim.', universal_workspace_nonuse_claim=False,
    d6_role='exposed development evaluation of global360 and four recovery boundaries; not confirmation',
    d5_b_e='closed; no qualification or promotion')
EVALUATOR_SOURCE = dict(path=str(EVAL_SOURCE), note='accepted _production_rows, byte-identical to the producer package copy')
EVALUATION = dict(action_mode='sampled_categorical', normal_start=True, cutoff_enabled=False, rng_seed=EVAL_RNG_SEED,
    rng_semantics='Before each policy: random, numpy, torch and torch.mps are reseeded with rng_seed; categorical '
                  'sampling uses the global MPS stream in fixed seed-batch order. The learner RNG, python/numpy/torch '
                  'CPU+MPS states, gradient mode and every learner module train/eval flag are captured before and '
                  'restored exactly after every evaluation; the evaluated model is a separate instance loaded from '
                  'the immutable saved checkpoint.',
    policies=len(EVAL_UPDATES), episodes_per_policy=EPISODES_PER_EVAL, milestones=[1000, 2000, 4000, 8000, 12000, 18000],
    metrics=['Worst', 'Q1', 'Mean', 'Q4', 'Best', 'milestone success'],
    selection='largest Q1 (bottom-256 mean), then largest Mean, exact tie keeps earlier; global360 through 600 remain one exposed D6 development cohort; no official parent324 promotion',
    comparison='global360 baseline and four fixed recovery boundaries on same exposed D6 development cohort; no confirmation claim')


class Cancelled(RuntimeError):
    pass


def need(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


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
        need(sha(path) == digest, 'pin drift: '+str(path))


def identity_hash(identity):
    return hashlib.sha256(canonical(identity)).hexdigest()


# ---- frozen-module loading ----
def frozen():
    """Authenticate the producer package, then import its stdlib helpers (origin-checked)."""
    manifest = read(PRODUCER_PKG/'source-manifest.json')
    need(sha(PRODUCER_PKG/'source-manifest.json') == PRODUCER_SOURCE_SHA, 'producer source manifest differs')
    for name, digest in manifest['files'].items():
        member = PRODUCER_PKG/name
        need(member.resolve().is_relative_to(PRODUCER_PKG) and not member.is_symlink() and sha(member) == digest,
             'producer source differs: '+name)
    need(sha(EVAL_SOURCE/'source-manifest.json') == EVAL_SOURCE_SHA, 'clean evaluator source manifest differs')
    need(manifest['files']['expanded_eval.py'] == EXPANDED_EVAL_SHA == sha(EVAL_SOURCE/'expanded_eval.py'),
         'accepted _production_rows source differs between producer package and clean evaluator')
    if str(PRODUCER_PKG) not in sys.path:
        sys.path.append(str(PRODUCER_PKG))   # last: the producer package has same-named binding/terminal/launch/audit modules
    modules = {}
    for name in ('contracts', 'driver_binding', 'fingerprints', 'seed_priority', 'expanded_eval', 'death_telemetry',
                 'successor_identity', 'runtime_adapter', 'progress_monitor'):
        module = importlib.import_module(name)
        need(Path(module.__file__).resolve() == PRODUCER_PKG/(name+'.py'), 'frozen module origin differs: '+name)
        modules[name] = module
    return modules


def check_owned_source():
    manifest = read(HERE/'source-manifest.json')
    for name, digest in manifest['files'].items():
        need(sha(HERE/name) == digest, 'owned source differs: '+name)
    for name, digest in HISTORICAL_COPIES.items():
        if digest is not None:
            need(sha(HERE/name) == digest, 'historical copy is not byte-identical: '+name)
    need(sha(HERE/'dependency-binding.json') == sha(LAST3/'dependency-binding.json'), 'dependency binding differs')
    need(sha(HERE/'power_guard.py') != HISTORICAL_POWER_GUARD_SHA, 'historical power_guard.py must not be reused')
    need(sha(LAST3/'power_guard.py') == HISTORICAL_POWER_GUARD_SHA, 'historical power guard was modified')
    return manifest


# ---- derived values ----
def cohort_union():
    """Exclusion union for training: all historical ranges plus D4/D5/D6, from the parent reservation."""
    return [list(r) for r in read(COHORT)['exclusion_union']]


def eval_excluded(union):
    """Union minus the evaluated cohort, as in the accepted evaluator."""
    excluded = []
    for low, high in union:
        if low < SEEDS[0]:
            excluded.append((low, min(high, SEEDS[0]-1)))
        if high > SEEDS[-1]:
            excluded.append((max(low, SEEDS[-1]+1), high))
    return excluded


def covers(union, low, high):
    return any(lo <= low and hi >= high for lo, hi in union)


def stream_identity(vector):
    return dict(study_id=PRODUCER_STUDY, replica=2, master=vector['seeds']['env_master_seed'])


def calibration_values(inputs):
    """Evidence-based projections. Derived fields must equal this recomputation."""
    train = inputs['training_seconds_per_60_updates']/SEGMENT_UPDATES*UPDATES
    rate = inputs['evaluation_prior_seconds']/inputs['evaluation_prior_raw_frames']
    expected_frames = EVAL_EPISODES*(inputs['expected_mean_alive_frames']+STARTUP)
    expected_eval = rate*expected_frames
    worst_eval = rate*EVALUATION_LIMITS['raw_frames']
    return dict(projected_training_seconds=math.ceil(train),
        evaluation_seconds_per_raw_frame=rate, expected_evaluation_raw_frames=math.ceil(expected_frames),
        projected_evaluation_seconds_expected=math.ceil(expected_eval),
        projected_evaluation_seconds_every_episode_capped=math.ceil(worst_eval),
        projected_total_expected_seconds=math.ceil(train+expected_eval),
        projected_total_worst_case_seconds=math.ceil(train+worst_eval),
        margin_over_expected=WORK_SECONDS/(train+expected_eval))


# ---- registration ----
REG_FIELDS = {'schema', 'status', 'run_id', 'study_id', 'backend', 'source_manifest_sha256', 'frozen_source',
    'runtime_root', 'runtime_manifest_sha256', 'runtime_versions', 'evaluator_source', 'parent', 'recipe', 'schedule',
    'streams', 'cohort', 'exclusion_union', 'evaluation', 'limits', 'calibration', 'output', 'attempt_claim_path',
    'launch_marker_path', 'state_path', 'expected_lease', 'interpreter', 'import_policy', 'input_pins',
    'authorization', 'power', 'provenance', 'restore_qualification', 'no_promotion', 'launch_authority', 'interruption'}
BACKEND = 'mps'


def validate_limits(limits):
    need(type(limits) is dict and set(limits) == LIMIT_FIELDS, 'limit fields differ')
    need(limits['work_seconds'] == WORK_SECONDS and limits['cleanup_seconds'] == CLEANUP_SECONDS
         and limits['postflight_seconds'] == POSTFLIGHT_SECONDS and limits['total_seconds'] == TOTAL_SECONDS,
         'wall/cleanup/postflight bounds differ')
    need(limits['rss_bytes'] == limits['mps_bytes'] == CAP and limits['retries'] == 0, 'memory/retry bounds differ')
    need(limits['training'] == TRAINING_LIMITS and limits['evaluation'] == EVALUATION_LIMITS,
         'training/evaluation raw-frame/constructor/step/reset budgets differ')


def validate_static(reg, *, require_registered=True, streams=False, startup=False):
    need(type(reg) is dict and set(reg) == REG_FIELDS, 'registration field set differs')
    need(reg['schema'] == SCHEMA and reg['run_id'] == RUN_ID and reg['study_id'] == STUDY_ID
         and reg['backend'] == BACKEND, 'schema/run identity differs')
    need(reg['launch_authority'] is False, 'registration carries no launch authority; the parent gates do')
    need(reg['status'] == (FINAL_STATUS if require_registered else reg['status'])
         and reg['status'] in (DRAFT_STATUS, FINAL_STATUS), 'registration status differs')
    check_pins(reg['input_pins'])
    need(all(reg['input_pins'].get(str(p)) == d for p, d in PINNED.items()), 'registration omits a required pin')
    need(reg['no_promotion'] == dict(official_parent324_promotion=False, automatic_selection=False,
         d5_b_e_opened=False, training_eligible=False), 'promotion flags differ')
    manifest = check_owned_source()
    need(sha(HERE/'source-manifest.json') == reg['source_manifest_sha256'], 'owned source manifest pin differs')
    modules = frozen(); c = modules['contracts']; c.verify_inputs()
    need(reg['frozen_source'] == dict(path=str(PRODUCER_PKG), source_manifest_sha256=PRODUCER_SOURCE_SHA,
         evaluator_source=str(EVAL_SOURCE), evaluator_source_manifest_sha256=EVAL_SOURCE_SHA,
         expanded_eval_sha256=EXPANDED_EVAL_SHA), 'frozen source pins differ')
    need(reg['runtime_root'] == str(PRODUCER_PKG/'runtime') and reg['runtime_manifest_sha256'] == RUNTIME_SHA,
         'runtime pins differ')
    c.verify_manifest(PRODUCER_PKG/'runtime-manifest.json', RUNTIME_SHA, PRODUCER_PKG/'runtime', exact=True)
    need(reg['runtime_versions'] == c.read(PRODUCER_PKG/'input-manifest.json')['runtime_versions'], 'versions differ')
    # parent evidence
    restore, qual = read(RESTORE_REG), read(RESTORE_QUAL)
    need(qual['status'] == 'passed_exact_selected_model_Adam_RNG_restore_readonly'
         and qual['registration_sha256'] == PINNED[RESTORE_REG] and qual['checkpoint_sha256'] == PINNED[PARENT_CHECKPOINT]
         and qual['environment_constructors'] == 0 and qual['game_steps'] == 0 and qual['optimizer_steps'] == 0
         and qual['readback_fingerprints'] == qual['fingerprints']
         and (qual['global_update'], qual['phase_update'], qual['cumulative_update']) == (360, 744, 792), 'restore qualification not an exact pass')
    need(reg['parent'] == dict(model='replica-2-uniform', run_id='uniform2-continuation600-luna-20261028-r2', checkpoint_path=str(PARENT_CHECKPOINT),
         checkpoint_sha256=PINNED[PARENT_CHECKPOINT], expected_identity=restore['expected_identity'],
         identity_sha256=qual['identity_sha256'], restore_fingerprints=qual['fingerprints'],
         counters=qual['counters'], initial_episode_indices=qual['next_episode_indices'],
         abandoned_current_episodes_sha256=hashlib.sha256(canonical(qual['abandoned_current_episodes'])).hexdigest(),
         global_update=360, phase_update=744, cumulative_update=792,
         schema='uniform2_continuation600_checkpoint_v1', official_retained_parent=324),
         'parent restore binding differs')
    need(identity_hash(restore['expected_identity']) == qual['identity_sha256'], 'parent identity hash differs')
    need(reg['restore_qualification'] == dict(path=str(RESTORE_QUAL), sha256=PINNED[RESTORE_QUAL],
         registration_path=str(RESTORE_REG), registration_sha256=PINNED[RESTORE_REG],
         source_path=str(RESTORE_SOURCE), source_sha256=PINNED[RESTORE_SOURCE]), 'restore qualification pins differ')
    # recipe / schedule
    expected_identity = restore['expected_identity']
    need(reg['recipe'] == dict(ppo=PPO, environment=ENVIRONMENT, learning_rate=3e-5, reset_optimizer=False,
         restore_optimizer=True, restore_rng=True, batch_size=SLOTS, rollout_steps=ROLLOUT,
         shared_config=restore['shared_config'], reward=restore['shared_config']['reward'],
         architecture='accepted OmniscientEntityTeacher, unchanged'), 'recipe differs')
    need(reg['schedule'] == SCHEDULE, 'schedule differs')
    # cohort
    cohort = read(COHORT)
    need(cohort['name'] == 'D6' and cohort['range'] == list(COHORT_RANGE) and cohort['seeds'] == SEEDS
         and cohort['count'] == 1024 and cohort['evaluation_rng_seed'] == EVAL_RNG_SEED and cohort['policies'] == 11
         and cohort['historical_overlap'] == 0 and cohort['d5_b_e_opened'] is False
         and cohort['outcomes_read'] is False and cohort['universal_workspace_nonuse_claim'] is False,
         'development cohort reservation differs')
    need(reg['cohort'] == dict(name='D6', range=list(COHORT_RANGE), count=1024, reservation_path=str(COHORT),
         reservation_sha256=PINNED[COHORT], seed_vector_sha256_u32be=cohort['seed_vector_sha256_u32be'],
         evaluation_rng_seed=EVAL_RNG_SEED, policies=len(EVAL_UPDATES), total_episodes=EVAL_EPISODES),
         'cohort binding differs')
    union = cohort['exclusion_union']
    c.validate_union(union)
    need(reg['exclusion_union'] == union and all(covers(union, *r) for r in (D4, D5, COHORT_RANGE)),
         'exclusion union differs or omits D4/D5/D6')
    need(reg['evaluation'] == EVALUATION and reg['provenance'] == PROVENANCE and reg['evaluator_source'] == EVALUATOR_SOURCE,
         'evaluation/provenance/evaluator source differs')
    # limits, calibration
    validate_limits(reg['limits'])
    cal = reg['calibration']
    need(cal['derived'] == calibration_values(cal['inputs']) and cal['proposed_work_seconds'] == WORK_SECONDS
         and cal['derived']['projected_total_worst_case_seconds'] <= WORK_SECONDS
         and set(cal) == {'inputs', 'derived', 'proposed_work_seconds', 'basis', 'parent_accepted',
                          'parent_acceptance_path', 'parent_acceptance_sha256'}, 'calibration arithmetic differs')
    if require_registered:
        need(cal['parent_accepted'] is True, 'parent resource calibration acceptance missing')
    # incident, authorization and power
    incident = read(INCIDENT_AUDIT)
    need(incident['status'] == 'interrupted_incomplete_not_qualified' and incident['completed_updates'] == 400
         and incident['completed_collections'] == 401 and incident['lost_completed_updates'] == 40
         and incident['latest_durable_checkpoint']['global_update'] == CAMPAIGN_BASE
         and incident['latest_durable_checkpoint']['sha256'] == PINNED[PARENT_CHECKPOINT]
         and incident['evaluation_scores_read'] is False and incident['training_eligible'] is False,
         'predecessor interruption audit differs')
    need(reg['interruption'] == dict(path=str(INCIDENT_AUDIT), sha256=PINNED[INCIDENT_AUDIT],
         original_prefix_audit_path=str(PREFIX_AUDIT), original_prefix_audit_sha256=PINNED[PREFIX_AUDIT]),
         'interruption and original-prefix audit pins differ')
    auth = read(AUTHORIZATION)
    need(auth['status'] == 'authorized_preparation_and_exactly_one_reviewed_recovery' and auth['updates'] == UPDATES
         and auth['retries'] == 0 and auth['maximum_work_seconds'] == WORK_SECONDS and auth['cleanup_seconds'] == CLEANUP_SECONDS
         and auth['postflight_seconds'] == POSTFLIGHT_SECONDS and auth['segments'] == SEGMENTS and auth['segment_updates'] == SEGMENT_UPDATES and auth['decisions'] == DECISIONS and auth['total_attempted_completed_updates_if_recovery_finishes'] == 640
         and auth['parent_checkpoint_sha256'] == PINNED[PARENT_CHECKPOINT] and auth['resume_original_global_update'] == CAMPAIGN_BASE and auth['evaluation_updates'] == EVAL_UPDATES
         and auth['automatic_official_promotion'] is False and auth['no_score_driven_checkpoint_choice'] is True and auth['lost_completed_updates'] == 40, 'user authorization differs')
    import power_guard
    power_guard.validate_override(read(BATTERY_OVERRIDE))
    need(reg['authorization'] == dict(user_authorization_path=str(AUTHORIZATION), user_authorization_sha256=PINNED[AUTHORIZATION],
         battery_override_path=str(BATTERY_OVERRIDE), battery_override_sha256=PINNED[BATTERY_OVERRIDE]),
         'authorization pins differ')
    need(reg['power'] == dict(guard='power_guard.py (owned successor; historical guard unmodified)',
         native_root_command_prefix='/usr/bin/caffeinate -ims', helper_ownership='direct child of dispatcher, same process group',
         on_ac_assertions=list(power_guard.AC_ASSERTIONS), on_battery_assertions=list(power_guard.BATTERY_ASSERTIONS),
         ac_required=False, battery_override_pinned=True, scope='this campaign only', os_power_settings_changed=False),
         'power policy differs')
    # paths, lease, interpreter, cache
    need(Path(reg['output']) == HERE/'worker-output' and reg['attempt_claim_path'] == str(HERE/'attempt.claimed')
         and reg['launch_marker_path'] == str(HERE/'launch.claimed') and reg['state_path'] == str(MAIN_STATE),
         'fixed owned paths differ')
    lease = reg['expected_lease']
    need(type(lease) is dict and lease.get('kind') == LEASE_KIND and lease.get('run_id') == RUN_ID
         and lease.get('study_id') == STUDY_ID and type(lease.get('owner_token')) is str and len(lease['owner_token']) == 32
         and lease.get('RSS_bytes') == lease.get('MPS_driver_bytes') == CAP and set(lease) == {
             'kind', 'run_id', 'study_id', 'owner_token', 'RSS_bytes', 'MPS_driver_bytes'}, 'exact resource lease missing')
    c.cache_check(reg)
    verify_dependencies(reg)
    if streams:
        verify_streams(reg, modules)
    if startup:
        need(not any(os.path.lexists(reg[k]) for k in ('output', 'attempt_claim_path', 'launch_marker_path')),
             'one-shot output/claim/marker spent')
    return reg


def verify_dependencies(reg):
    anchor = read(HERE/'dependency-binding.json')
    check_pins({anchor['registration_path']: anchor['registration_sha256'], anchor['inventory_path']: anchor['inventory_sha256']})
    old, inventory = read(anchor['registration_path']), read(anchor['inventory_path'])
    need(reg['interpreter'] == old['interpreter'], 'dependency interpreter differs')
    for path, item in inventory['pins'].items():
        need(old['pins'].get(path) == item['sha256'] == sha(path), 'dependency drift: '+path)
    executable = str(Path(reg['interpreter']).resolve(strict=True))
    need(sha(executable) == old['pins'][executable], 'interpreter bytes differ')
    return dict(checked=len(inventory['pins']), scope=inventory['scope'])


def verify_streams(reg, modules=None):
    """Pool/cohort disjointness and the first segment's per-slot stream digests (about 1M hashes)."""
    import seeds
    modules = modules or frozen()
    pool_doc = read(POOL); pool = modules['seed_priority'].validate_pool(pool_doc)
    s = reg['streams']
    need(sha(POOL) == PINNED[POOL] and pool['pool_sha256'] == s['training_pool_sha256']
         and pool_doc['excluded_seed_ranges'] == read(PRODUCER_HOME/'registration-final.json')['exclusion_union'],
         'training pool identity differs')
    union = reg['exclusion_union']
    need(not any(lo <= seed <= hi for seed in pool['all'] for lo, hi in union), 'training pool intersects the exclusion union')
    vector = read(RESTORE_REG)['original_seed_vector']
    identity = stream_identity(vector)
    need(s['identity'] == identity, 'stream identity differs')
    values, components = seeds.segment_streams(list(pool['all']), identity, reg['parent']['initial_episode_indices'],
                                               frozen=modules['seed_priority'])
    seed_digests, component_digests = seeds.digests(values, components)
    need(s['first_segment_slot_stream_sha256'] == seed_digests and s['first_segment_slot_component_sha256'] == component_digests,
         'first-segment per-slot stream digests differ')
    return seed_digests


# ---- main-ledger lease, envelope, watchdog interface ----
def check_lease(reg):
    state = read(reg['state_path'])
    need(state.get('active_long_campaign') == reg['expected_lease'], 'exact resource lease changed')


def expected_envelope_fields():
    return {'schema', 'status', 'registration', 'registration_sha256', 'launch_approval', 'launch_approval_sha256',
            'source_acceptance', 'source_acceptance_sha256', 'control', 'cancel_path', 'started', 'pins',
            'interpreter_resolved', 'interpreter_sha256'}


LIMITS = {}


def load_envelope(path, digest):
    need(sha(path) == digest, 'envelope external SHA differs')
    e = read(path)
    need(set(e) == expected_envelope_fields() and e['schema'] == ENVELOPE_SCHEMA
         and e['status'] == 'parent_bound_exactly_one_run', 'inert envelope')
    reg = read(e['registration']); validate_limits(reg['limits'])
    LIMITS.clear(); LIMITS.update({k: v for k, v in reg['limits'].items() if k not in ('training', 'evaluation')})
    need(Path(e['control']) == HERE/'dispatch'/reg['run_id'], 'owned dispatch path differs')
    need(Path(e['cancel_path']) == HERE/'cancel', 'fixed cancel path differs')
    need(type(e['started']) in (int, float) and math.isfinite(e['started']), 'finite start required')
    e['self_path'] = str(Path(path).resolve()); e['self_sha256'] = digest
    return e, reg


def approval_document(registration_sha, source_manifest_sha, pins):
    return dict(schema=GATE_SCHEMA, status='approved_exactly_once_uniform2_recovery240',
        registration_sha256=registration_sha, source_manifest_sha256=source_manifest_sha,
        gates=dict.fromkeys(GATES, 'passed'), pins=pins)


def source_acceptance_document(source_manifest_sha):
    return dict(schema='uniform2_recovery240_source_acceptance_v1', status='accepted_source_review_only',
                source_manifest_sha256=source_manifest_sha)


def verify_bound(e, reg, *, preflight):
    check_pins(e['pins'])
    check_pins({e['registration']: e['registration_sha256'], e['launch_approval']: e['launch_approval_sha256'],
                e['source_acceptance']: e['source_acceptance_sha256']})
    validate_static(reg)
    gates = read(e['launch_approval'])
    need(gates == approval_document(e['registration_sha256'], reg['source_manifest_sha256'], gates.get('pins')),
         'external parent gates missing')
    need(read(e['source_acceptance']) == source_acceptance_document(reg['source_manifest_sha256']),
         'independent source acceptance differs')
    check_lease(reg); need(not os.path.lexists(e['cancel_path']), 'parent cancellation present')
    need(str(Path(reg['interpreter']).resolve()) == e['interpreter_resolved']
         and sha(e['interpreter_resolved']) == e['interpreter_sha256'], 'executable differs')
    if preflight:
        need(not os.path.lexists(reg['output']) and not os.path.lexists(reg['attempt_claim_path']), 'worker attempt already spent')
    need(read(reg['launch_marker_path']) == dict(schema=MARKER_SCHEMA, registration_sha256=e['registration_sha256'],
         run_id=reg['run_id'], started=e['started']), 'parent spent marker differs')


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
        need(all(type(row[k]) is int and row[k] >= 0 for k in ('rss_bytes', 'mps_driver_bytes')), 'invalid resource row')
        value['samples'] += 1
        value['peak_rss_bytes'] = max(value['peak_rss_bytes'] or 0, row['rss_bytes'])
        value['peak_mps_driver_bytes'] = max(value['peak_mps_driver_bytes'] or 0, row['mps_driver_bytes'])
    return value


def learner_identity(reg, registration_sha):
    """Identity stored in every continuation checkpoint; reproducible from the registration alone."""
    return dict(schema=IDENTITY_SCHEMA, run_id=reg['run_id'], study_id=reg['study_id'], backend=reg['backend'],
        registration_sha256=registration_sha,
        parent=dict(checkpoint_sha256=reg['parent']['checkpoint_sha256'], identity_sha256=reg['parent']['identity_sha256'],
                    restore_fingerprints=reg['parent']['restore_fingerprints'], run_id=reg['parent']['run_id']),
        successor_runtime=dict(runtime_manifest_sha256=reg['runtime_manifest_sha256'],
            source_manifest_sha256=reg['source_manifest_sha256'], runtime_versions=reg['runtime_versions']),
        recipe=reg['recipe'], streams=reg['streams'], exclusion_union=reg['exclusion_union'],
        cohort=reg['cohort'], schedule=reg['schedule'], neural_inputs=list(NEURAL_INPUTS),
        native_seed_mode='evaluation_explicit_seed_list', training_pool_role='training_only')
