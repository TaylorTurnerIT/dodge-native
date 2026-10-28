"""Hash-only builder. Writes an inert draft; never installs a lease, writes a marker, imports Torch/native modules,
or deserializes the checkpoint. Refuses until every pinned parent artifact is present and exact.

  python -B build_registration.py --check
  python -B build_registration.py --output registration-draft.json
"""
from __future__ import annotations
import argparse
from pathlib import Path
import uuid
import binding as b
import seeds

FIRST3_WORKER = b.FIRST3/'worker-output/worker-result.json'


class NotReady(RuntimeError):
    pass


def readiness():
    missing = [str(p) for p in b.PINNED if not Path(p).is_file()]
    rows = dict(missing_pins=missing, pins_match=not missing and all(b.sha(p) == d for p, d in b.PINNED.items()))
    rows['ready'] = rows['pins_match']
    return rows


def calibration():
    producer = b.read(b.PRODUCER_HOME/'worker-output/worker-result.json')
    first = b.read(FIRST3_WORKER)
    mean = b.ENVIRONMENT['raw_frame_cap']  # capped worst-case planning input; no evaluation scores read
    inputs = dict(training_seconds_per_60_updates=producer['elapsed_seconds'],
        training_source=str(b.PRODUCER_HOME/'worker-output/worker-result.json'),
        training_peak_rss_bytes=producer['peak_rss_bytes'], training_peak_mps_driver_bytes=producer['peak_mps_driver_bytes'],
        evaluation_prior_seconds=first['elapsed_seconds'], evaluation_prior_raw_frames=first['raw_frames_including_startup'],
        evaluation_source=str(FIRST3_WORKER), evaluation_prior_peak_rss_bytes=first['peak_rss_bytes'],
        evaluation_prior_peak_mps_driver_bytes=first['peak_mps_driver_bytes'],
        expected_mean_alive_frames=mean, expected_mean_source='registered 18000 raw-frame cap (conservative planning bound)')
    return dict(inputs=inputs, derived=b.calibration_values(inputs), proposed_work_seconds=b.WORK_SECONDS,
        basis='Work cap is 14,400 s. Training uses the same producer measured 60-update wall time for four recovery segments. '
              'Evaluation uses the accepted D4 evaluator measured seconds per raw frame and the registered 18,000-frame cap '
              'for every episode. No evaluation score enters checkpoint choice or the expected evaluation frame estimate. '
              'Cleanup is 10 s and postflight is 120 s. The observer SIGALRM stops work at the registered cap. '
              'Raw-frame, constructor, step, and reset budgets are structural ceilings; parent acceptance is still required.',
        parent_accepted=False, parent_acceptance_path=str(b.CALIBRATION_ACCEPTANCE), parent_acceptance_sha256=None)


def build():
    state = readiness()
    if not state['ready']:
        raise NotReady('pinned parent artifacts missing/changed: '+', '.join(state['missing_pins']))
    modules = b.frozen(); c = modules['contracts']
    restore, qual, cohort = b.read(b.RESTORE_REG), b.read(b.RESTORE_QUAL), b.read(b.COHORT)
    vector = restore['original_seed_vector']
    pool_doc = b.read(b.POOL); pool = modules['seed_priority'].validate_pool(pool_doc)
    union = cohort['exclusion_union']
    identity = b.stream_identity(vector)
    values, components = seeds.segment_streams(list(pool['all']), identity, qual['next_episode_indices'],
                                               frozen=modules['seed_priority'])
    seed_digests, component_digests = seeds.digests(values, components)
    old = b.read(b.read(b.HERE/'dependency-binding.json')['registration_path'])
    pins = {str(p): d for p, d in b.PINNED.items()}
    pins[str(b.STREAM_AUDITOR)] = b.sha(b.STREAM_AUDITOR)
    pins[str(FIRST3_WORKER)] = b.sha(FIRST3_WORKER)
    
    reg = dict(schema=b.SCHEMA, status=b.DRAFT_STATUS, run_id=b.RUN_ID, study_id=b.STUDY_ID, backend=b.BACKEND,
        source_manifest_sha256=b.sha(b.HERE/'source-manifest.json'),
        frozen_source=dict(path=str(b.PRODUCER_PKG), source_manifest_sha256=b.PRODUCER_SOURCE_SHA,
            evaluator_source=str(b.EVAL_SOURCE), evaluator_source_manifest_sha256=b.EVAL_SOURCE_SHA,
            expanded_eval_sha256=b.EXPANDED_EVAL_SHA),
        runtime_root=str(b.PRODUCER_PKG/'runtime'), runtime_manifest_sha256=b.RUNTIME_SHA,
        runtime_versions=c.read(b.PRODUCER_PKG/'input-manifest.json')['runtime_versions'],
        evaluator_source=b.EVALUATOR_SOURCE, parent=None, recipe=None, schedule=b.SCHEDULE, streams=None, cohort=None,
        exclusion_union=union, evaluation=b.EVALUATION, limits=dict(work_seconds=b.WORK_SECONDS, total_seconds=b.TOTAL_SECONDS,
            cleanup_seconds=b.CLEANUP_SECONDS, postflight_seconds=b.POSTFLIGHT_SECONDS, rss_bytes=b.CAP, mps_bytes=b.CAP,
            retries=0, training=b.TRAINING_LIMITS, evaluation=b.EVALUATION_LIMITS),
        calibration=calibration(), output=str(b.HERE/'worker-output'), attempt_claim_path=str(b.HERE/'attempt.claimed'),
        launch_marker_path=str(b.HERE/'launch.claimed'), state_path=str(b.MAIN_STATE),
        expected_lease=dict(kind=b.LEASE_KIND, run_id=b.RUN_ID, study_id=b.STUDY_ID, owner_token=uuid.uuid4().hex,
                            RSS_bytes=b.CAP, MPS_driver_bytes=b.CAP),
        interpreter=old['interpreter'], import_policy=dict(pycache_prefix=str(b.HERE/'empty-pycache'), dont_write_bytecode=True),
        input_pins=pins,
        authorization=dict(user_authorization_path=str(b.AUTHORIZATION), user_authorization_sha256=b.PINNED[b.AUTHORIZATION],
            battery_override_path=str(b.BATTERY_OVERRIDE), battery_override_sha256=b.PINNED[b.BATTERY_OVERRIDE]),
        power=None, provenance=b.PROVENANCE,
        restore_qualification=dict(path=str(b.RESTORE_QUAL), sha256=b.PINNED[b.RESTORE_QUAL], registration_path=str(b.RESTORE_REG),
            registration_sha256=b.PINNED[b.RESTORE_REG], source_path=str(b.RESTORE_SOURCE), source_sha256=b.PINNED[b.RESTORE_SOURCE]),
        no_promotion=dict(official_parent324_promotion=False, automatic_selection=False, d5_b_e_opened=False, training_eligible=False),
        launch_authority=False, interruption=dict(path=str(b.INCIDENT_AUDIT), sha256=b.PINNED[b.INCIDENT_AUDIT],
            original_prefix_audit_path=str(b.PREFIX_AUDIT), original_prefix_audit_sha256=b.PINNED[b.PREFIX_AUDIT]))
    import hashlib
    reg['parent'] = dict(model='replica-2-uniform', run_id='uniform2-continuation600-luna-20261028-r2', checkpoint_path=str(b.PARENT_CHECKPOINT),
        checkpoint_sha256=b.PINNED[b.PARENT_CHECKPOINT], expected_identity=restore['expected_identity'],
        identity_sha256=qual['identity_sha256'], restore_fingerprints=qual['fingerprints'], counters=qual['counters'],
        initial_episode_indices=qual['next_episode_indices'],
        abandoned_current_episodes_sha256=hashlib.sha256(b.canonical(qual['abandoned_current_episodes'])).hexdigest(),
        global_update=360, phase_update=744, cumulative_update=792,
        schema='uniform2_continuation600_checkpoint_v1', official_retained_parent=324)
    reg['recipe'] = dict(ppo=b.PPO, environment=b.ENVIRONMENT, learning_rate=3e-5, reset_optimizer=False, restore_optimizer=True,
        restore_rng=True, batch_size=b.SLOTS, rollout_steps=b.ROLLOUT, shared_config=restore['shared_config'],
        reward=restore['shared_config']['reward'], architecture='accepted OmniscientEntityTeacher, unchanged')
    reg['streams'] = dict(identity=identity, arm='uniform', recipe_schema=seeds.STREAM_SCHEMA,
        owned_extension='seeds.py: same hash recipe as frozen seed_priority without the 16384 bound; per 60-update segment '
                        'start+15361 entries per slot from the saved next episode indices; frozen helper cross-checked when it fits',
        episodes_per_segment=seeds.EPISODES_PER_SEGMENT, training_pool_path=str(b.POOL), training_pool_file_sha256=b.PINNED[b.POOL],
        training_pool_sha256=pool['pool_sha256'], first_segment_slot_stream_sha256=seed_digests,
        first_segment_slot_component_sha256=component_digests,
        later_segments='derived from the actual saved next episode indices; every segment digest is journaled and re-derived by the audit')
    reg['cohort'] = dict(name='D6', range=list(b.COHORT_RANGE), count=1024, reservation_path=str(b.COHORT),
        reservation_sha256=b.PINNED[b.COHORT], seed_vector_sha256_u32be=cohort['seed_vector_sha256_u32be'],
        evaluation_rng_seed=b.EVAL_RNG_SEED, policies=len(b.EVAL_UPDATES), total_episodes=b.EVAL_EPISODES)
    import power_guard
    reg['power'] = dict(guard='power_guard.py (owned successor; historical guard unmodified)',
        native_root_command_prefix='/usr/bin/caffeinate -ims', helper_ownership='direct child of dispatcher, same process group',
        on_ac_assertions=list(power_guard.AC_ASSERTIONS), on_battery_assertions=list(power_guard.BATTERY_ASSERTIONS),
        ac_required=False, battery_override_pinned=True, scope='this campaign only', os_power_settings_changed=False)
    b.need(set(reg) == b.REG_FIELDS, 'builder field set differs')
    return reg


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--check', action='store_true'); parser.add_argument('--output')
    a = parser.parse_args()
    if a.check or not a.output:
        print(readiness())
    if a.output:
        reg = build(); b.validate_static(reg, require_registered=False, streams=True)
        b.save(Path(a.output), reg); print(b.sha(Path(a.output)))
