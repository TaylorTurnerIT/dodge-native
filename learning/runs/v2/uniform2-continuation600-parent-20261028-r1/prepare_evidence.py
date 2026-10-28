"""Reserve the continuation development cohort and register the read-only restore qualification."""
from pathlib import Path
import datetime
import hashlib
import json
import struct
import sys

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
EVALUATOR = V2 / 'fullgame-priority-D4-last-three-evaluator-sonnet-20261028-r1'
sys.path.insert(0, str(EVALUATOR))
import binding as b


def main():
    selection_path = V2 / 'fullgame-priority-D4-last-three-parent-validation-20261028-r1/lower-quarter-selection.json'
    selected = b.read(selection_path)
    b.need(selected['selected_model'] == 'replica-2-uniform', 'selected model changed')
    policy = selected['selected_policy']
    import merge
    merge.verify_producer(policy)
    producer = b.read(policy['producer']['registration_path'])
    closure_path = V2 / 'progressive1000-seed-history-closure-sol-20261026-r2/merged-conservative-seeds.json'
    reconciliation_path = V2 / 'rl-followup-seed-reservation-parent-20261027-r1/seed-reconciliation.json'
    historical = set(b.read(closure_path)['sorted_unique_seed_values'])
    reconciliation = b.read(reconciliation_path)
    for row in reconciliation['postclosure_actual_constructors']:
        historical.update(row['actual_seeds_sorted'])
    pool = b.read(producer['training_pool_path'])
    historical.update(row['seed'] for row in pool['seeds'])
    first = b.read(b.FIRST_PART / 'registration-final.json')
    last = b.read(EVALUATOR / 'registration-final.json')
    for part in (first, last):
        historical.update(part['seeds'])
    seeds = list(range(0xD6000000, 0xD6000400))
    b.need(not (set(seeds) & historical), 'proposed D6 cohort intersects recorded history')
    b.need(all(not (lo <= seeds[-1] and hi >= seeds[0]) for lo, hi in producer['exclusion_union']),
           'D6 overlaps an already reserved range')
    # Newer runs use only the frozen training pool or the recorded D4 evaluation vector.
    # Verify those exact six producer chains rather than claim universal workspace nonuse.
    identities = [merge.verify_producer(p) for part in (first, last) for p in part['policies']]
    for part in (first, last):
        for p in part['policies']:
            registration = b.read(p['producer']['registration_path'])
            b.need(registration['training_pool_file_sha256'] == producer['training_pool_file_sha256'],
                   'recent producer used another training pool')
    exclusion_union = sorted([*producer['exclusion_union'], [seeds[0], seeds[-1]]])
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    pins = {str(path): b.sha(path) for path in (selection_path, closure_path, reconciliation_path,
        Path(producer['training_pool_path']), b.FIRST_PART / 'parent-terminal-audit.json',
        EVALUATOR / 'parent-terminal-audit.json')}
    b.save(HERE / 'development-cohort-reservation.json', dict(
        schema='dodge_uniform2_continuation600_development_cohort_v1', status='parent_reserved_and_scope_accepted',
        name='D6', seeds=seeds, range=[seeds[0], seeds[-1]], count=1024,
        seed_vector_sha256_u32be=hashlib.sha256(b''.join(struct.pack('>I', seed) for seed in seeds)).hexdigest(),
        role='Repeated development evaluation for starting model and ten fixed 60-update boundaries; not confirmation.',
        policies=11, total_episodes=11264, evaluation_rng_seed=2026102803,
        selection='Largest Q1 bottom-quarter mean; then overall mean; exact remaining tie retains earlier checkpoint.',
        exclusion_union=exclusion_union, history_unique_seed_count=len(historical), historical_overlap=0,
        claim_scope=reconciliation['scope'], universal_workspace_nonuse_claim=False,
        inherited_history_limits=reconciliation['remaining_limits'], recent_six_producers=identities,
        d5_b_e_opened=False, outcomes_read=False, reserved_at_utc=now, pins=pins))
    authorization = dict(schema='dodge_uniform2_continuation600_user_authorization_v1',
        status='authorized_preparation_and_exactly_one_reviewed_campaign',
        user_reply='Go', accepted_proposal='600 updates, evaluating every60, saving best worst-quarter model',
        model='replica-2-uniform', parent_checkpoint_path=policy['checkpoint_path'],
        parent_checkpoint_sha256=policy['checkpoint_sha256'], updates=600, evaluation_updates=list(range(0,601,60)),
        decisions=600*64*256, unchanged_reward=True, unchanged_architecture=True, unchanged_uniform_pool=True,
        optimizer='restore selected Adam state', rng='restore selected complete RNG; evaluations restore learner RNG exactly',
        official_retained_parent=324, automatic_official_promotion=False,
        launch_requires='registered frozen source/runtime, independent source review, restore qualification, cohort exclusions, resource and power checks, exact-once marker and resource lease',
        maximum_work_seconds=28800, cleanup_seconds=10, postflight_seconds=120,
        max_rss_bytes=6*1024**3, max_mps_bytes=6*1024**3, retries=0,
        no_new_training_launched=True, recorded_at_utc=now)
    b.save(HERE / 'user-authorization.json', authorization)
    b.save(HERE / 'restore-qualification-registration.json', dict(
        schema='dodge_uniform2_restore_qualification_registration_v1', status='parent_registered_readonly_qualification',
        checkpoint_path=policy['checkpoint_path'], checkpoint_sha256=policy['checkpoint_sha256'],
        expected_identity=policy['producer']['expected_identity'], producer=policy['producer'],
        runtime_root=producer['runtime_root'], runtime_manifest_sha256=producer['runtime_manifest_sha256'],
        runtime_manifest_path=str(Path(producer['runtime_root']).parent / 'runtime-manifest.json'),
        runtime_versions=producer['runtime_versions'], ppo=producer['ppo'], backend='mps',
        allowed_operations=['load hash-pinned checkpoint', 'construct same model and Adam',
                            'restore model/Adam/RNG and verify fingerprints', 'capture metadata and free objects'],
        environment_constructors=0, game_steps=0, optimizer_steps=0, evaluation_episodes=0,
        output=str(HERE / 'restore-qualification.json'), wall_seconds=60, rss_bytes=6*1024**3,
        mps_bytes=6*1024**3, retries=0))
    print('reserved_D6_and_registered_readonly_restore_qualification_no_training')


if __name__ == '__main__':
    main()
